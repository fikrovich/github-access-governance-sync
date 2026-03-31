from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    org: str = "example-org"
    bq_project: str = "example-gcp-project"
    bq_dataset: str = "github_access_audit"
    bq_location: str = "us-central1"
    export_script_path: str = "/app/scripts/export_all_access.sh"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            org=os.getenv("ORG", cls.org),
            bq_project=os.getenv("BQ_PROJECT", cls.bq_project),
            bq_dataset=os.getenv("BQ_DATASET", cls.bq_dataset),
            bq_location=os.getenv("BQ_LOCATION", cls.bq_location),
            export_script_path=os.getenv("EXPORT_SCRIPT_PATH", cls.export_script_path),
        )
