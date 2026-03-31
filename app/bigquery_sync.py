from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from .config import Settings
from .loader import write_jsonl
from .schemas import RAW_TABLE_SPECS, SYNC_RUNS_SCHEMA, SYNC_SKIPPED_ITEMS_SCHEMA, TableSpec


LOGGER = logging.getLogger(__name__)


class BigQueryManager:
    def __init__(self, settings: Settings, client: bigquery.Client | None = None) -> None:
        self.settings = settings
        self.client = client or bigquery.Client(project=settings.bq_project)
        self.dataset_ref = bigquery.DatasetReference(settings.bq_project, settings.bq_dataset)

    def ensure_resources(self) -> None:
        self.ensure_dataset()
        for table_spec in RAW_TABLE_SPECS:
            self.ensure_partitioned_table(table_spec)
        self.ensure_standard_table("sync_runs", SYNC_RUNS_SCHEMA)
        self.ensure_standard_table("sync_skipped_items", SYNC_SKIPPED_ITEMS_SCHEMA)
        self.refresh_views()

    def ensure_dataset(self) -> None:
        try:
            self.client.get_dataset(self.dataset_ref)
            return
        except NotFound:
            dataset = bigquery.Dataset(self.dataset_ref)
            dataset.location = self.settings.bq_location
            dataset.description = "Daily GitHub access audit snapshots."
            self.client.create_dataset(dataset)
            LOGGER.info("Created dataset %s", dataset.full_dataset_id)

    def ensure_partitioned_table(self, table_spec: TableSpec) -> None:
        table_id = self._table_id(table_spec.name)
        try:
            self.client.get_table(table_id)
            return
        except NotFound:
            table = bigquery.Table(table_id, schema=table_spec.schema)
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="snapshot_date",
            )
            if table_spec.cluster_fields:
                table.clustering_fields = list(table_spec.cluster_fields)
            self.client.create_table(table)
            LOGGER.info("Created table %s", table_id)

    def ensure_standard_table(
        self,
        table_name: str,
        schema_fields,
        cluster_fields: tuple[str, ...] = (),
    ) -> None:
        table_id = self._table_id(table_name)
        try:
            self.client.get_table(table_id)
            return
        except NotFound:
            table = bigquery.Table(
                table_id,
                schema=[field.to_schema_field() for field in schema_fields],
            )
            if cluster_fields:
                table.clustering_fields = list(cluster_fields)
            self.client.create_table(table)
            LOGGER.info("Created table %s", table_id)

    def load_rows(self, table_spec: TableSpec, rows: list[dict]) -> int:
        if not rows:
            return 0

        table_id = self._table_id(table_spec.name)
        job_config = bigquery.LoadJobConfig(
            schema=table_spec.schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        with tempfile.NamedTemporaryFile(
            mode="w+b",
            suffix=".jsonl",
            delete=False,
        ) as temp_handle:
            temp_path = Path(temp_handle.name)

        try:
            write_jsonl(rows, temp_path)
            with temp_path.open("rb") as handle:
                job = self.client.load_table_from_file(handle, table_id, job_config=job_config)
            job.result()
            return len(rows)
        finally:
            temp_path.unlink(missing_ok=True)

    def load_json_rows(self, table_name: str, schema_fields, rows: list[dict]) -> int:
        if not rows:
            return 0

        table_id = self._table_id(table_name)
        job_config = bigquery.LoadJobConfig(
            schema=[field.to_schema_field() for field in schema_fields],
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        with tempfile.NamedTemporaryFile(
            mode="w+b",
            suffix=".jsonl",
            delete=False,
        ) as temp_handle:
            temp_path = Path(temp_handle.name)

        try:
            write_jsonl(rows, temp_path)
            with temp_path.open("rb") as handle:
                job = self.client.load_table_from_file(handle, table_id, job_config=job_config)
            job.result()
            return len(rows)
        finally:
            temp_path.unlink(missing_ok=True)

    def refresh_views(self) -> None:
        for table_spec in RAW_TABLE_SPECS:
            self._create_or_replace_view(
                view_name=f"latest_{table_spec.name}",
                query=self._latest_view_query(table_spec.name),
            )
        self._create_or_replace_view(
            view_name="current_access_matrix",
            query=self._current_access_matrix_query(),
        )

    def insert_sync_run(self, row: dict) -> None:
        errors = self.client.insert_rows_json(self._table_id("sync_runs"), [row])
        if errors:
            raise RuntimeError(f"Failed to insert sync run: {errors}")

    def load_skipped_items(self, rows: list[dict]) -> int:
        return self.load_json_rows("sync_skipped_items", SYNC_SKIPPED_ITEMS_SCHEMA, rows)

    def _create_or_replace_view(self, view_name: str, query: str) -> None:
        view_id = self._quoted_table(view_name)
        statement = f"CREATE OR REPLACE VIEW {view_id} AS\n{query}"
        self.client.query(statement).result()

    def _latest_view_query(self, table_name: str) -> str:
        table_ref = self._quoted_table(table_name)
        return f"""
SELECT *
FROM {table_ref}
WHERE snapshot_ts = (
  SELECT MAX(snapshot_ts)
  FROM {table_ref}
)
""".strip()

    def _current_access_matrix_query(self) -> str:
        latest_team_members = self._quoted_table("latest_team_members")
        latest_team_repo_permissions = self._quoted_table("latest_team_repo_permissions")
        latest_repo_team_permissions = self._quoted_table("latest_repo_team_permissions")
        latest_org_memberships = self._quoted_table("latest_org_memberships")
        latest_outside_collaborators = self._quoted_table("latest_outside_collaborators")
        latest_repo_user_permissions = self._quoted_table("latest_repo_user_permissions")
        return f"""
WITH team_grants AS (
  SELECT
    tr.repo,
    tm.user,
    tr.team_slug,
    COALESCE(rtp.team_name, tr.team_slug) AS team_name,
    tr.permission AS team_permission,
    tm.role AS team_membership_role,
    tm.type AS team_member_type
  FROM {latest_team_members} AS tm
  JOIN {latest_team_repo_permissions} AS tr
    ON tm.team_slug = tr.team_slug
  LEFT JOIN {latest_repo_team_permissions} AS rtp
    ON tr.repo = rtp.repo
   AND tr.team_slug = rtp.team_slug
),
org_context AS (
  SELECT
    COALESCE(om.user, oc.user) AS user,
    om.role AS org_role,
    om.state AS org_state,
    COALESCE(om.type, oc.type) AS org_user_type,
    oc.user IS NOT NULL AS is_outside_collaborator
  FROM {latest_org_memberships} AS om
  FULL OUTER JOIN {latest_outside_collaborators} AS oc
    ON om.user = oc.user
)
SELECT
  COALESCE(ru.repo, tg.repo) AS repo,
  COALESCE(ru.user, tg.user) AS user,
  ru.permission AS direct_permission,
  ru.role_name AS direct_role_name,
  tg.team_slug,
  tg.team_name,
  tg.team_permission,
  tg.team_membership_role,
  COALESCE(ru.user_type, tg.team_member_type, oc.org_user_type) AS user_type,
  ru.site_admin,
  oc.org_role,
  oc.org_state,
  IFNULL(oc.is_outside_collaborator, FALSE) AS is_outside_collaborator
FROM {latest_repo_user_permissions} AS ru
FULL OUTER JOIN team_grants AS tg
  ON ru.repo = tg.repo
 AND ru.user = tg.user
LEFT JOIN org_context AS oc
  ON COALESCE(ru.user, tg.user) = oc.user
""".strip()

    def _quoted_table(self, table_name: str) -> str:
        return f"`{self.settings.bq_project}.{self.settings.bq_dataset}.{table_name}`"

    def _table_id(self, table_name: str) -> str:
        return f"{self.settings.bq_project}.{self.settings.bq_dataset}.{table_name}"
