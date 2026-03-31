from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .bigquery_sync import BigQueryManager
from .config import Settings
from .loader import LoadMetadata, build_skipped_item_record, csv_rows_with_metadata, parse_skipped_items
from .schemas import RAW_TABLE_SPECS


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    run_id: str
    status: str
    snapshot_date: str
    snapshot_ts: str
    exported_files: int
    loaded_tables: int
    loaded_rows: int
    skipped_items: int
    output_dir: str
    error_message: str | None = None

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "snapshot_date": self.snapshot_date,
            "snapshot_ts": self.snapshot_ts,
            "exported_files": self.exported_files,
            "loaded_tables": self.loaded_tables,
            "loaded_rows": self.loaded_rows,
            "skipped_items": self.skipped_items,
            "output_dir": self.output_dir,
            "error_message": self.error_message,
        }


class SyncService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self) -> SyncResult:
        bigquery = BigQueryManager(self.settings)
        started_at = datetime.now(UTC)
        run_id = self._build_run_id(started_at)
        snapshot_ts = started_at.isoformat()
        snapshot_date = started_at.date().isoformat()
        metadata = LoadMetadata(
            snapshot_date=snapshot_date,
            snapshot_ts=snapshot_ts,
            run_id=run_id,
            org=self.settings.org,
        )
        output_dir = Path(tempfile.mkdtemp(prefix=f"github-access-{run_id}-"))
        status = "success"
        error_message = None
        exported_files = 0
        loaded_tables = 0
        loaded_rows = 0
        skipped_items_count = 0

        bigquery.ensure_resources()

        try:
            self._run_export(output_dir)
            exported_files = len(list(output_dir.glob("*.csv")))

            for table_spec in RAW_TABLE_SPECS:
                rows = csv_rows_with_metadata(output_dir / table_spec.source_file, table_spec, metadata)
                loaded_count = bigquery.load_rows(table_spec, rows)
                if loaded_count > 0:
                    loaded_tables += 1
                    loaded_rows += loaded_count

            skipped_items = self._collect_skipped_items(output_dir, metadata)
            skipped_items_count = bigquery.load_skipped_items(skipped_items)
            bigquery.refresh_views()
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            LOGGER.exception("Sync failed for run %s", run_id)
            skipped_items = self._collect_skipped_items(output_dir, metadata)
            skipped_items_count = bigquery.load_skipped_items(skipped_items)
        finally:
            ended_at = datetime.now(UTC)
            bigquery.insert_sync_run(
                {
                    "run_id": run_id,
                    "org": self.settings.org,
                    "status": status,
                    "snapshot_date": snapshot_date,
                    "snapshot_ts": snapshot_ts,
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                    "exported_files": exported_files,
                    "loaded_tables": loaded_tables,
                    "loaded_rows": loaded_rows,
                    "skipped_items": skipped_items_count,
                    "output_dir": str(output_dir),
                    "error_message": error_message,
                }
            )
            shutil.rmtree(output_dir, ignore_errors=True)

        if status != "success":
            raise RuntimeError(error_message or "GitHub access sync failed")

        return SyncResult(
            run_id=run_id,
            status=status,
            snapshot_date=snapshot_date,
            snapshot_ts=snapshot_ts,
            exported_files=exported_files,
            loaded_tables=loaded_tables,
            loaded_rows=loaded_rows,
            skipped_items=skipped_items_count,
            output_dir=str(output_dir),
            error_message=error_message,
        )

    def _run_export(self, output_dir: Path) -> None:
        command = [self.settings.export_script_path, self.settings.org, str(output_dir)]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Exporter failed")

    def _collect_skipped_items(self, output_dir: Path, metadata: LoadMetadata) -> list[dict]:
        skipped_items = parse_skipped_items(output_dir / "skipped_items.log", metadata)
        custom_roles_note = output_dir / "custom_repository_roles.txt"
        if custom_roles_note.exists():
            note = custom_roles_note.read_text(encoding="utf-8").strip()
            if note:
                skipped_items.append(build_skipped_item_record(note, metadata))
        return skipped_items

    @staticmethod
    def _build_run_id(started_at: datetime) -> str:
        return f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
