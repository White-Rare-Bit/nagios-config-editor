# 060 — Search: No Match Highlighting — Misleading Attribute Hits

**Phase:** 21 — Search, Filter & Analysis
**Severity:** Minor
**Screenshot:** screenshots/phase21-search-web.png

## Steps to Reproduce

1. Search for `web` in the object tree
2. Observe "Security Updates on linux-hosts" (SVC) appearing in services.cfg results
3. Open the service — the display name and visible attributes show no "web" match

## Actual Behavior

"Security Updates on linux-hosts" appears in the "web" search results. The matching attribute is `host_name: "!old-server-decommissioned, !web-dev-01"` — an exclusion operator. No highlighting or tooltip reveals why the result matched.

The same pattern occurs for `db-prod-master` (HOSTDEP) in dependencies.cfg, which appears because `dependent_host_name: "web-prod-01,web-prod-02,web-prod-03"`.

## Expected Behavior

Either:
- Highlight the matched attribute value in the tree item tooltip or detail panel, OR
- Show a "Matched in: host_name" indicator on the tree item

## Admin Impact

Full-text attribute search is genuinely useful (e.g., "find everything touching web-prod-01"), but without match highlighting the admin cannot tell *why* an object appeared. Worse, a match against an exclusion (`!web-dev-01`) is semantically opposite to what the admin is likely looking for — this service does NOT apply to web machines. This can cause an admin to draw incorrect conclusions about object relationships.
