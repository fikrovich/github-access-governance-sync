from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import TableSpec


@dataclass(frozen=True)
class LoadMetadata:
    snapshot_date: str
    snapshot_ts: str
    run_id: str
    org: str


def csv_rows_with_metadata(
    csv_path: Path,
    table_spec: TableSpec,
    metadata: LoadMetadata,
) -> list[dict[str, Any]]:
    if not csv_path.exists():
        return []

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, Any]] = []
        for raw_row in reader:
            row = {
                field.name: field.converter(raw_row.get(field.name, ""))
                for field in table_spec.fields
            }
            row.update(
                {
                    "snapshot_date": metadata.snapshot_date,
                    "snapshot_ts": metadata.snapshot_ts,
                    "run_id": metadata.run_id,
                    "org": metadata.org,
                    "source_file": table_spec.source_file,
                }
            )
            rows.append(row)
        return rows


def write_jsonl(rows: list[dict[str, Any]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")))
            handle.write("\n")


def parse_skipped_items(log_path: Path, metadata: LoadMetadata) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not log_path.exists():
        return records

    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw_message = line.strip()
            if not raw_message:
                continue
            records.append(build_skipped_item_record(raw_message, metadata))
    return records


def build_skipped_item_record(raw_message: str, metadata: LoadMetadata) -> dict[str, Any]:
    error_type = raw_message
    item_key = None
    item_value = None

    if " failed for " in raw_message:
        error_type, item_fragment = raw_message.split(" failed for ", 1)
        if "=" in item_fragment:
            item_key, item_value = item_fragment.split("=", 1)
    elif raw_message.endswith(" endpoint failed"):
        error_type = raw_message.removesuffix(" endpoint failed")
        item_key = "endpoint"
        item_value = error_type

    return {
        "run_id": metadata.run_id,
        "org": metadata.org,
        "snapshot_date": metadata.snapshot_date,
        "snapshot_ts": metadata.snapshot_ts,
        "raw_message": raw_message,
        "error_type": error_type,
        "item_key": item_key,
        "item_value": item_value,
    }

