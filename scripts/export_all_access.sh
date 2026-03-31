#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   export GH_TOKEN='your_pat'
#   bash export_all_access.sh example-org [output_dir]

: "${GH_TOKEN:?Set GH_TOKEN to a valid PAT first}"
ORG="${1:?Usage: $0 <org> [output_dir]}"
OUT_DIR="${2:-github_access_export_${ORG}_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT_DIR"

SKIPPED_FILE="$OUT_DIR/skipped_items.log"
: > "$SKIPPED_FILE"

gh_api_retry() {
  local url="$1"
  local max_attempts="${2:-6}"
  local attempt=1
  local delay=2
  local out
  local err_file
  local err

  while true; do
    err_file="$(mktemp)"
    if out="$(gh api "$url" --paginate 2>"$err_file")"; then
      rm -f "$err_file"
      printf '%s' "$out"
      return 0
    fi

    err="$(cat "$err_file")"
    rm -f "$err_file"

    if echo "$err" | grep -Eiq 'HTTP (429|502|503|504)|temporarily unavailable|secondary rate limit|timeout' && [ "$attempt" -lt "$max_attempts" ]; then
      sleep "$delay"
      delay=$((delay * 2))
      attempt=$((attempt + 1))
      continue
    fi

    echo "$err" >&2
    return 1
  done
}

echo "Validating token..."
gh api user --jq '.login' >/dev/null || { echo "Invalid GH_TOKEN"; exit 1; }

echo "Exporting org: $ORG -> $OUT_DIR"

echo '"repo_id","name","full_name","private","archived","visibility","default_branch"' > "$OUT_DIR/repos.csv"
gh_api_retry "orgs/$ORG/repos?per_page=100&type=all" \
| jq -r '.[] | [.id,.name,.full_name,.private,.archived,.visibility,.default_branch] | @csv' \
>> "$OUT_DIR/repos.csv" \
|| echo "repos endpoint failed" >> "$SKIPPED_FILE"

echo '"user","role","state","type"' > "$OUT_DIR/org_memberships.csv"
if members="$(gh_api_retry "orgs/$ORG/members?per_page=100&role=all" | jq -r '.[].login')" ; then
  while IFS= read -r user; do
    [ -z "$user" ] && continue
    if ! gh_api_retry "orgs/$ORG/memberships/$user" \
      | jq -r '[.user.login,.role,.state,.user.type] | @csv' >> "$OUT_DIR/org_memberships.csv"; then
      echo "org membership failed for user=$user" >> "$SKIPPED_FILE"
    fi
  done <<< "$members"
else
  echo "org members endpoint failed" >> "$SKIPPED_FILE"
fi

echo '"user","type"' > "$OUT_DIR/outside_collaborators.csv"
gh_api_retry "orgs/$ORG/outside_collaborators?per_page=100" \
| jq -r '.[] | [.login,.type] | @csv' \
>> "$OUT_DIR/outside_collaborators.csv" \
|| echo "outside collaborators endpoint failed" >> "$SKIPPED_FILE"

echo '"team_id","slug","name","privacy"' > "$OUT_DIR/teams.csv"
gh_api_retry "orgs/$ORG/teams?per_page=100" \
| jq -r '.[] | [.id,.slug,.name,.privacy] | @csv' \
>> "$OUT_DIR/teams.csv" \
|| echo "teams endpoint failed" >> "$SKIPPED_FILE"

TEAM_SLUGS="$(gh_api_retry "orgs/$ORG/teams?per_page=100" | jq -r '.[].slug' 2>/dev/null || true)"

echo '"team_slug","user","role","type"' > "$OUT_DIR/team_members.csv"
while IFS= read -r slug; do
  [ -z "$slug" ] && continue
  if ! gh_api_retry "orgs/$ORG/teams/$slug/members?per_page=100&role=all" \
    | jq -r --arg t "$slug" '.[] | [$t,.login,.role,.type] | @csv' >> "$OUT_DIR/team_members.csv"; then
    echo "team members failed for team=$slug" >> "$SKIPPED_FILE"
  fi
done <<< "$TEAM_SLUGS"

echo '"team_slug","repo","permission"' > "$OUT_DIR/team_repo_permissions.csv"
while IFS= read -r slug; do
  [ -z "$slug" ] && continue
  if ! gh_api_retry "orgs/$ORG/teams/$slug/repos?per_page=100" \
    | jq -r --arg t "$slug" '.[] | [$t,.full_name,.permission] | @csv' >> "$OUT_DIR/team_repo_permissions.csv"; then
    echo "team repos failed for team=$slug" >> "$SKIPPED_FILE"
  fi
done <<< "$TEAM_SLUGS"

REPOS="$(gh_api_retry "orgs/$ORG/repos?per_page=100&type=all" | jq -r '.[].name' 2>/dev/null || true)"

echo '"repo","user","permission","role_name","user_type","site_admin"' > "$OUT_DIR/repo_user_permissions.csv"
while IFS= read -r repo; do
  [ -z "$repo" ] && continue
  if ! gh_api_retry "repos/$ORG/$repo/collaborators?per_page=100&affiliation=all" \
    | jq -r --arg r "$repo" '
        .[] | [
          $r,
          .login,
          (if .permissions.admin then "admin"
           elif .permissions.maintain then "maintain"
           elif .permissions.push then "push"
           elif .permissions.triage then "triage"
           elif .permissions.pull then "pull"
           else "none" end),
          .role_name,
          .type,
          .site_admin
        ] | @csv
      ' >> "$OUT_DIR/repo_user_permissions.csv"; then
    echo "collaborators failed for repo=$repo" >> "$SKIPPED_FILE"
  fi
done <<< "$REPOS"

echo '"repo","team_slug","team_name","permission"' > "$OUT_DIR/repo_team_permissions.csv"
while IFS= read -r repo; do
  [ -z "$repo" ] && continue
  if ! gh_api_retry "repos/$ORG/$repo/teams?per_page=100" \
    | jq -r --arg r "$repo" '.[] | [$r,.slug,.name,.permission] | @csv' >> "$OUT_DIR/repo_team_permissions.csv"; then
    echo "repo teams failed for repo=$repo" >> "$SKIPPED_FILE"
  fi
done <<< "$REPOS"

if gh api "orgs/$ORG/custom-repository-roles?per_page=100" >/dev/null 2>&1; then
  echo '"id","name","description","base_role","organization"' > "$OUT_DIR/custom_repository_roles.csv"
  gh_api_retry "orgs/$ORG/custom-repository-roles?per_page=100" \
  | jq -r '.[] | [.id,.name,.description,.base_role,.organization] | @csv' \
  >> "$OUT_DIR/custom_repository_roles.csv" \
  || echo "custom repository roles endpoint failed" >> "$SKIPPED_FILE"
else
  echo "Custom repository roles endpoint unavailable for this org/token." > "$OUT_DIR/custom_repository_roles.txt"
fi

echo "Done. Files in: $OUT_DIR"
echo "Skipped items log: $SKIPPED_FILE"
ls -1 "$OUT_DIR"
