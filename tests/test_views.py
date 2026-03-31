from __future__ import annotations

from app.bigquery_sync import BigQueryManager
from app.config import Settings


def test_latest_view_query_uses_max_snapshot() -> None:
    manager = BigQueryManager(Settings(), client=object())

    query = manager._latest_view_query("repo_user_permissions")

    assert "MAX(snapshot_ts)" in query
    assert "repo_user_permissions" in query


def test_current_access_matrix_query_references_latest_views() -> None:
    manager = BigQueryManager(Settings(), client=object())

    query = manager._current_access_matrix_query()

    assert "latest_repo_user_permissions" in query
    assert "latest_team_repo_permissions" in query
    assert "latest_org_memberships" in query
