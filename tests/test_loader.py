from __future__ import annotations

from pathlib import Path

from app.loader import LoadMetadata, build_skipped_item_record, csv_rows_with_metadata
from app.schemas import RAW_TABLE_SPECS


def test_csv_rows_with_metadata_casts_types(tmp_path: Path) -> None:
    csv_path = tmp_path / "repo_user_permissions.csv"
    csv_path.write_text(
        '"repo","user","permission","role_name","user_type","site_admin"\n'
        '"repo-1","user-1","admin","admin","User",false\n',
        encoding="utf-8",
    )
    metadata = LoadMetadata(
        snapshot_date="2026-03-24",
        snapshot_ts="2026-03-24T08:00:00+00:00",
        run_id="run-1",
        org="example-org",
    )

    rows = csv_rows_with_metadata(csv_path, RAW_TABLE_SPECS[6], metadata)

    assert rows == [
        {
            "repo": "repo-1",
            "user": "user-1",
            "permission": "admin",
            "role_name": "admin",
            "user_type": "User",
            "site_admin": False,
            "snapshot_date": "2026-03-24",
            "snapshot_ts": "2026-03-24T08:00:00+00:00",
            "run_id": "run-1",
            "org": "example-org",
            "source_file": "repo_user_permissions.csv",
        }
    ]


def test_build_skipped_item_record_parses_repo_failure() -> None:
    metadata = LoadMetadata(
        snapshot_date="2026-03-24",
        snapshot_ts="2026-03-24T08:00:00+00:00",
        run_id="run-1",
        org="example-org",
    )

    record = build_skipped_item_record("collaborators failed for repo=sample-repo", metadata)

    assert record["error_type"] == "collaborators"
    assert record["item_key"] == "repo"
    assert record["item_value"] == "sample-repo"
