# Dashboard Guide

This guide builds a six-page Looker Studio report from the BigQuery views and tables created by this project.

Assumption:
- BigQuery dataset name is `github_access_audit`
- Current-state reporting is based on `current_access_matrix`

## 1. Create Data Sources

Create these BigQuery data sources in Looker Studio:

1. `DS_Current_Access` = `project.github_access_audit.current_access_matrix`
2. `DS_Latest_Repos` = `project.github_access_audit.latest_repos`
3. `DS_Team_Members` = `project.github_access_audit.latest_team_members`
4. `DS_Team_Repo_Permissions` = `project.github_access_audit.latest_team_repo_permissions`
5. `DS_Sync_Runs` = `project.github_access_audit.sync_runs`
6. `DS_Skipped_Items` = `project.github_access_audit.sync_skipped_items`
7. `DS_Access_History` = `project.github_access_audit.repo_user_permissions`

Use owner credentials unless you want every viewer to have direct BigQuery access.

## 2. Add Calculated Fields

Add these fields to `DS_Current_Access`.

### `Repo_User_Key`

```text
CONCAT(repo, " | ", user)
```

### `Effective_Permission`

```text
CASE
  WHEN direct_permission = "admin" OR team_permission = "admin" THEN "admin"
  WHEN direct_permission = "maintain" OR team_permission = "maintain" THEN "maintain"
  WHEN direct_permission = "push" OR team_permission = "push" THEN "push"
  WHEN direct_permission = "triage" OR team_permission = "triage" THEN "triage"
  WHEN direct_permission = "pull" OR team_permission = "pull" THEN "pull"
  ELSE "none"
END
```

### `Privilege_Class`

```text
CASE
  WHEN direct_permission IN ("admin","maintain","push")
    OR team_permission IN ("admin","maintain","push")
  THEN "Privileged"
  ELSE "Non-privileged"
END
```

### `Privileged_Row_Flag`

```text
CASE
  WHEN direct_permission IN ("admin","maintain","push")
    OR team_permission IN ("admin","maintain","push")
  THEN 1
  ELSE 0
END
```

### `Access_Source`

```text
CASE
  WHEN direct_permission IS NOT NULL AND team_slug IS NOT NULL THEN "Direct + Team"
  WHEN direct_permission IS NOT NULL THEN "Direct Only"
  WHEN team_slug IS NOT NULL THEN "Team Only"
  ELSE "Unknown"
END
```

### `User_Category`

```text
CASE
  WHEN is_outside_collaborator THEN "Outside collaborator"
  WHEN org_role = "admin" THEN "Org admin"
  ELSE "Org member"
END
```

### `Non_Active_Org_State_Flag`

```text
CASE
  WHEN org_state = "active" THEN 0
  ELSE 1
END
```

Add these fields to `DS_Access_History`.

### `Repo_User_Key`

```text
CONCAT(repo, " | ", user)
```

### `Historical_Privileged_Row_Flag`

```text
CASE
  WHEN permission IN ("admin","maintain","push") THEN 1
  ELSE 0
END
```

Add these helper fields to team datasets if you want distinct relationship counts:

`DS_Team_Members`

```text
CONCAT(team_slug, " | ", user)
```

`DS_Team_Repo_Permissions`

```text
CONCAT(team_slug, " | ", repo)
```

## 3. Build Pages

Important:
- `current_access_matrix` is row-based, not guaranteed to be one row per repo-user pair
- title charts as `Access Rows` unless you intentionally use distinct keys

### Page 1: Executive Overview

- Scorecard `Repositories`
  - Data source: `DS_Current_Access`
  - Metric: `COUNT_DISTINCT(repo)`
- Scorecard `Users`
  - Data source: `DS_Current_Access`
  - Metric: `COUNT_DISTINCT(user)`
- Scorecard `Privileged Access Rows`
  - Data source: `DS_Current_Access`
  - Metric: `SUM(Privileged_Row_Flag)`
- Scorecard `Outside Collaborators`
  - Data source: `DS_Current_Access`
  - Metric: `COUNT_DISTINCT(user)`
  - Filter: `is_outside_collaborator = true`
- Bar chart `Access Rows by Effective Permission`
  - Dimension: `Effective_Permission`
  - Metric: `Record Count`
- Donut chart `Access Rows by Access Source`
  - Dimension: `Access_Source`
  - Metric: `Record Count`
- Bar chart `Top Repos by Access Rows`
  - Dimension: `repo`
  - Metric: `Record Count`
  - Limit: `15`
- Table `Latest Sync Runs`
  - Data source: `DS_Sync_Runs`
  - Columns: `started_at`, `status`, `loaded_rows`, `skipped_items`, `error_message`

### Page 2: Privileged Access Review

- Filters: `repo`, `user`, `team_name`, `User_Category`, `is_outside_collaborator`
- Scorecard `Privileged Access Rows`
  - Metric: `SUM(Privileged_Row_Flag)`
- Scorecard `Users with Privileged Access`
  - Metric: `COUNT_DISTINCT(user)`
  - Filter: `Privilege_Class = "Privileged"`
- Scorecard `Repos with Privileged Access`
  - Metric: `COUNT_DISTINCT(repo)`
  - Filter: `Privilege_Class = "Privileged"`
- Table `Privileged Access Detail`
  - Columns: `repo`, `user`, `direct_permission`, `direct_role_name`, `team_name`, `team_permission`, `team_membership_role`, `org_role`, `site_admin`, `is_outside_collaborator`
  - Filter: `Privilege_Class = "Privileged"`
- Bar chart `Repos with Most Privileged Access Rows`
  - Dimension: `repo`
  - Metric: `Record Count`
  - Filter: `Privilege_Class = "Privileged"`
- Bar chart `Users with Most Privileged Access Rows`
  - Dimension: `user`
  - Metric: `Record Count`
  - Filter: `Privilege_Class = "Privileged"`

### Page 3: Repository Exposure

- Filters: `repo`, `Effective_Permission`, `Access_Source`, `is_outside_collaborator`
- Stacked bar chart `Access Rows by Repo and Permission`
  - Dimension: `repo`
  - Breakdown: `Effective_Permission`
  - Metric: `Record Count`
- Table `Repository Exposure Detail`
  - Data source: `DS_Current_Access`
  - Columns: `repo`, `user`, `Effective_Permission`, `Access_Source`, `team_name`, `is_outside_collaborator`
- Table `Repository Inventory`
  - Data source: `DS_Latest_Repos`
  - Columns: `full_name`, `visibility`, `private`, `archived`, `default_branch`

### Page 4: Team Governance

- Filters on `DS_Team_Members`: `team_slug`, `user`, `role`
- Filters on `DS_Team_Repo_Permissions`: `team_slug`, `repo`, `permission`
- Scorecard `Teams`
  - Data source: `DS_Team_Members`
  - Metric: `COUNT_DISTINCT(team_slug)`
- Scorecard `Team Member Relationships`
  - Data source: `DS_Team_Members`
  - Metric: `COUNT_DISTINCT(CONCAT(team_slug, " | ", user))`
- Scorecard `Team Repo Grants`
  - Data source: `DS_Team_Repo_Permissions`
  - Metric: `COUNT_DISTINCT(CONCAT(team_slug, " | ", repo))`
- Table `Team Members`
  - Columns: `team_slug`, `user`, `role`, `type`
- Table `Team Repo Grants`
  - Columns: `team_slug`, `repo`, `permission`
- Bar chart `Member Relationships by Team`
  - Dimension: `team_slug`
  - Metric: `COUNT_DISTINCT(CONCAT(team_slug, " | ", user))`
- Bar chart `Repo Grants by Team`
  - Dimension: `team_slug`
  - Metric: `COUNT_DISTINCT(CONCAT(team_slug, " | ", repo))`

### Page 5: Exceptions And External Access

- Filters: `is_outside_collaborator`, `org_role`, `org_state`, `team_name`
- Scorecard `Outside Collaborator Access Rows`
  - Data source: `DS_Current_Access`
  - Metric: `Record Count`
  - Filter: `is_outside_collaborator = true`
- Scorecard `Non-Active Org State Rows`
  - Data source: `DS_Current_Access`
  - Metric: `SUM(Non_Active_Org_State_Flag)`
- Scorecard `Skipped Items`
  - Data source: `DS_Skipped_Items`
  - Metric: `Record Count`
- Table `Outside Collaborator Detail`
  - Data source: `DS_Current_Access`
  - Columns: `repo`, `user`, `direct_permission`, `team_name`, `team_permission`, `org_role`, `user_type`
  - Filter: `is_outside_collaborator = true`
- Table `Non-Active Org State With Access`
  - Data source: `DS_Current_Access`
  - Columns: `repo`, `user`, `org_state`, `direct_permission`, `team_permission`
  - Filter: `Non_Active_Org_State_Flag = 1`
- Bar chart `Skipped Items by Error Type`
  - Data source: `DS_Skipped_Items`
  - Dimension: `error_type`
  - Metric: `Record Count`
- Table `Skipped Item Detail`
  - Data source: `DS_Skipped_Items`
  - Columns: `snapshot_ts`, `error_type`, `item_key`, `item_value`, `raw_message`

### Page 6: Pipeline Health And History

- Time series `Loaded Rows per Run`
  - Data source: `DS_Sync_Runs`
  - Dimension: `started_at`
  - Metric: `loaded_rows`
- Time series `Skipped Items per Run`
  - Data source: `DS_Sync_Runs`
  - Dimension: `started_at`
  - Metric: `skipped_items`
- Table `Recent Runs`
  - Data source: `DS_Sync_Runs`
  - Columns: `run_id`, `started_at`, `ended_at`, `status`, `loaded_tables`, `loaded_rows`, `skipped_items`, `error_message`
- Time series `Total Access Rows by Snapshot Date`
  - Data source: `DS_Access_History`
  - Dimension: `snapshot_date`
  - Metric: `Record Count`
- Time series `Privileged Access Rows by Snapshot Date`
  - Data source: `DS_Access_History`
  - Dimension: `snapshot_date`
  - Metric: `SUM(Historical_Privileged_Row_Flag)`
- Stacked bar `Permission Mix by Snapshot Date`
  - Data source: `DS_Access_History`
  - Dimension: `snapshot_date`
  - Breakdown: `permission`
  - Metric: `Record Count`

## 4. Presentation Guidance

- Keep business-facing pages first: `Executive Overview`, `Privileged Access Review`, `Repository Exposure`
- Keep operational pages later: `Team Governance`, `Exceptions And External Access`, `Pipeline Health And History`
- Label row-based charts as `Access Rows`
- Use `COUNT_DISTINCT(Repo_User_Key)` when you need unique repo-user counts instead of access rows
