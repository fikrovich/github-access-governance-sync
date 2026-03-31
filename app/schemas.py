from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from google.cloud import bigquery


Converter = Callable[[str], Any]


def to_string(value: str) -> str | None:
    return value if value != "" else None


def to_bool(value: str) -> bool | None:
    if value == "":
        return None
    return value.strip().lower() == "true"


def to_int(value: str) -> int | None:
    if value == "":
        return None
    return int(value)


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: str
    converter: Converter = to_string
    mode: str = "NULLABLE"

    def to_schema_field(self) -> bigquery.SchemaField:
        return bigquery.SchemaField(self.name, self.field_type, mode=self.mode)


@dataclass(frozen=True)
class TableSpec:
    name: str
    source_file: str
    fields: tuple[FieldSpec, ...]
    cluster_fields: tuple[str, ...] = ()

    @property
    def schema(self) -> list[bigquery.SchemaField]:
        base_fields = [field.to_schema_field() for field in self.fields]
        return base_fields + [field.to_schema_field() for field in METADATA_FIELDS]

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)


METADATA_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("snapshot_date", "DATE"),
    FieldSpec("snapshot_ts", "TIMESTAMP"),
    FieldSpec("run_id", "STRING"),
    FieldSpec("org", "STRING"),
    FieldSpec("source_file", "STRING"),
)


RAW_TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        name="repos",
        source_file="repos.csv",
        fields=(
            FieldSpec("repo_id", "INT64", converter=to_int),
            FieldSpec("name", "STRING"),
            FieldSpec("full_name", "STRING"),
            FieldSpec("private", "BOOL", converter=to_bool),
            FieldSpec("archived", "BOOL", converter=to_bool),
            FieldSpec("visibility", "STRING"),
            FieldSpec("default_branch", "STRING"),
        ),
    ),
    TableSpec(
        name="org_memberships",
        source_file="org_memberships.csv",
        fields=(
            FieldSpec("user", "STRING"),
            FieldSpec("role", "STRING"),
            FieldSpec("state", "STRING"),
            FieldSpec("type", "STRING"),
        ),
    ),
    TableSpec(
        name="outside_collaborators",
        source_file="outside_collaborators.csv",
        fields=(
            FieldSpec("user", "STRING"),
            FieldSpec("type", "STRING"),
        ),
    ),
    TableSpec(
        name="teams",
        source_file="teams.csv",
        fields=(
            FieldSpec("team_id", "INT64", converter=to_int),
            FieldSpec("slug", "STRING"),
            FieldSpec("name", "STRING"),
            FieldSpec("privacy", "STRING"),
        ),
    ),
    TableSpec(
        name="team_members",
        source_file="team_members.csv",
        fields=(
            FieldSpec("team_slug", "STRING"),
            FieldSpec("user", "STRING"),
            FieldSpec("role", "STRING"),
            FieldSpec("type", "STRING"),
        ),
        cluster_fields=("team_slug", "user"),
    ),
    TableSpec(
        name="team_repo_permissions",
        source_file="team_repo_permissions.csv",
        fields=(
            FieldSpec("team_slug", "STRING"),
            FieldSpec("repo", "STRING"),
            FieldSpec("permission", "STRING"),
        ),
    ),
    TableSpec(
        name="repo_user_permissions",
        source_file="repo_user_permissions.csv",
        fields=(
            FieldSpec("repo", "STRING"),
            FieldSpec("user", "STRING"),
            FieldSpec("permission", "STRING"),
            FieldSpec("role_name", "STRING"),
            FieldSpec("user_type", "STRING"),
            FieldSpec("site_admin", "BOOL", converter=to_bool),
        ),
        cluster_fields=("repo", "user"),
    ),
    TableSpec(
        name="repo_team_permissions",
        source_file="repo_team_permissions.csv",
        fields=(
            FieldSpec("repo", "STRING"),
            FieldSpec("team_slug", "STRING"),
            FieldSpec("team_name", "STRING"),
            FieldSpec("permission", "STRING"),
        ),
        cluster_fields=("repo", "team_slug"),
    ),
    TableSpec(
        name="custom_repository_roles",
        source_file="custom_repository_roles.csv",
        fields=(
            FieldSpec("id", "INT64", converter=to_int),
            FieldSpec("name", "STRING"),
            FieldSpec("description", "STRING"),
            FieldSpec("base_role", "STRING"),
            FieldSpec("organization", "STRING"),
        ),
    ),
)


SYNC_RUNS_SCHEMA: tuple[FieldSpec, ...] = (
    FieldSpec("run_id", "STRING"),
    FieldSpec("org", "STRING"),
    FieldSpec("status", "STRING"),
    FieldSpec("snapshot_date", "DATE"),
    FieldSpec("snapshot_ts", "TIMESTAMP"),
    FieldSpec("started_at", "TIMESTAMP"),
    FieldSpec("ended_at", "TIMESTAMP"),
    FieldSpec("exported_files", "INT64", converter=to_int),
    FieldSpec("loaded_tables", "INT64", converter=to_int),
    FieldSpec("loaded_rows", "INT64", converter=to_int),
    FieldSpec("skipped_items", "INT64", converter=to_int),
    FieldSpec("output_dir", "STRING"),
    FieldSpec("error_message", "STRING"),
)


SYNC_SKIPPED_ITEMS_SCHEMA: tuple[FieldSpec, ...] = (
    FieldSpec("run_id", "STRING"),
    FieldSpec("org", "STRING"),
    FieldSpec("snapshot_date", "DATE"),
    FieldSpec("snapshot_ts", "TIMESTAMP"),
    FieldSpec("raw_message", "STRING"),
    FieldSpec("error_type", "STRING"),
    FieldSpec("item_key", "STRING"),
    FieldSpec("item_value", "STRING"),
)

