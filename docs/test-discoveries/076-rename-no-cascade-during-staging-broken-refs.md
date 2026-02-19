# 076 — Rename Shows BROKEN REFERENCE During Staging; "Update References" Unchecked Commits Broken Config

**Phase:** 28 — Cross-Object Reference Integrity
**Severity:** Major
**Category:** Data Integrity / UX

## Summary

The rename operation (context menu → Rename...) stages only the name field change on the target object. All other objects that reference the old name immediately show **"BROKEN REFERENCE"** badges. The reference cascade is deferred to commit time via an "Update references (N references in other objects)" checkbox in the commit dialog. The checkbox is checked by default — but if unchecked and committed, the resulting config will have broken host references that cause Nagios to fail to start.

## Steps to Reproduce (broken config path)

1. Open `web-prod-01` in the Object Explorer.
2. Right-click → **Rename…** → enter `web-prod-01-renamed` → **Rename**.
3. Stage is updated; `web-prod-01-renamed` now appears in tree.
4. Open "Application Health Check" service → breadcrumb shows **BROKEN REFERENCE** badge.
5. Open "HTTP" servicedependency in dependencies.cfg → also shows **BROKEN REFERENCE**.
6. Click **Commit** → dialog shows `3 files changed ~1 modified 4 ref updates`.
7. **Uncheck** "Update references (4 references in other objects)".
8. Click **Apply Changes**.

## Actual Behavior

- After rename is staged: 2 services/deps immediately show "BROKEN REFERENCE" (correct — references are stale in staging)
- Commit dialog (checkbox **checked**): shows 3 files changed with 4 inline ref updates; all references updated correctly ✓
- Commit dialog (checkbox **unchecked**): shows only 1 file (hosts.cfg); ref updates excluded from diff preview and commit; services still reference `web-prod-01` (no longer exists) ✗

## What the Commit Diff Shows (checkbox checked)

```
# db-prod-master — ref update (web-prod-01 → web-prod-01-renamed)
+ dependent_host_name   web-prod-01-renamed,web-prod-02,web-prod-03

# HTTP on web-prod-01,... → Application Health Check — ref update (web-prod-01 → web-prod-01-renamed)
+ host_name             web-prod-01-renamed,web-prod-02,web-prod-03
+ dependent_host_name   web-prod-01-renamed,web-prod-02,web-prod-03

# Application Health Check on web-prod-01,... — ref update (web-prod-01 → web-prod-01-renamed)
+ host_name             web-prod-01-renamed,web-prod-02,...
```

4 references across `services.cfg` and `dependencies.cfg` — all shown with clear annotations.

## What Works Well

1. The "BROKEN REFERENCE" badge during staging is accurate — it reflects that the staged config is inconsistent
2. The commit dialog detects all 4 cross-file references automatically
3. "Update references" is **checked by default**, protecting most users
4. The diff preview clearly annotates each reference update with the object name and direction (old → new)

## Risk

If an admin unchecks "Update references" and clicks Apply:
- `hosts.cfg`: `host_name` changed to `web-prod-01-renamed` ✓
- `services.cfg`: `Application Health Check` still has `host_name: web-prod-01,...` ✗
- `dependencies.cfg`: servicedependency still has `host_name: web-prod-01,...` and `dependent_host_name: web-prod-01,...` ✗

Nagios will fail to start: `Error: Host 'web-prod-01' specified in service ... not found!`

## Recommendation

1. When the checkbox is unchecked, show a warning: "Committing without updating references will result in a broken configuration. N objects will reference a host that no longer exists."
2. Alternatively, disable the uncheck option (always cascade) and remove the checkbox.
3. During staging, show a tooltip or info badge on "BROKEN REFERENCE" items explaining: "This reference will be updated when you commit with 'Update references' enabled."

## Screenshots

- `phase28-rename-staged.png` — tree showing `web-prod-01-renamed`, BROKEN REFERENCE badge on breadcrumb
- `phase28-broken-reference-after-rename.png` — Application Health Check service showing BROKEN REFERENCE
- `phase28-svcdep-broken-reference.png` — servicedependency showing BROKEN REFERENCE
- `phase28-diff-preview-rename.png` — commit dialog with 4 ref updates (checkbox checked)
- `phase28-diff-refs-unchecked.png` — commit dialog with only 1 file (checkbox unchecked)
