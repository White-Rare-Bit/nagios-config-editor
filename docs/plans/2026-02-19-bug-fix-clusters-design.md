# Bug-Fix Clusters Design

**Date:** 2026-02-19
**Scope:** E2E test discoveries from `docs/test-discoveries/` — graph subsystem (044–057) excluded (planned separately)
**Total bugs in scope:** ~62
**Approach:** Root-cause cohesion — each cluster shares one underlying root cause, maximising fix efficiency

---

## Clusters

### A — Crashes & null guards (5 bugs)
| Bug | Title |
|-----|-------|
| 018 | Cyclic template inheritance causes stack overflow (backend) |
| 075 | Cyclic template inheritance in staged state (frontend crash) |
| 023 | Null crash in `stageCurrentChanges` for new objects |
| 026 | Drop null object corrupts staged state, crashes renderer |
| 064 | Validation `[object Object]` rendering bug |

Root cause: no cycle detection in `buildParentChain()` + missing null guards before object lookups.

---

### B — Lock enforcement (4 bugs)
| Bug | Title |
|-----|-------|
| 067 | Context menu operations bypass staging lock *(critical)* |
| 042 | Fields not read-only while locked |
| 043 | Editor shows rejected value after lock releases |
| 002-stale | Stale session lock persists across server restart |

Root cause: lock banner is UI-only; mutations proceed regardless; fields lack `disabled` attribute; lock state not cleared on startup.

---

### C — Reference field validation (5 bugs)
| Bug | Title |
|-----|-------|
| 013 | check_command autocomplete resets after `!` |
| 014 | check_command arguments validated as object references *(critical)* |
| 015 | Wildcard `*` rejected as invalid reference *(critical)* |
| 058 | hostgroup_name/service_description missing autocomplete in escalation/dependency objects |
| 016 | Autocomplete hard-capped at 20 suggestions |

Root cause: reference validator doesn't split on `!` separator, doesn't whitelist Nagios special keywords, and field-type mapping is incomplete for some object types.

---

### D — Duplicate validation at creation (3 bugs)
| Bug | Title |
|-----|-------|
| 009 | Service duplicate check ignores host_name (composite key) |
| 022 | No duplicate name validation at creation time |
| 035 | Clone accepts duplicate name without error |

Root cause: duplicate detection is post-hoc (suggestions panel only) and uses single-field key instead of composite key for services.

---

### E — Staged state not reflected in UI (6 bugs)
| Bug | Title |
|-----|-------|
| 039 | Editor shows original values (not staged) when reopening object |
| 040 | Status badges missing on session restore |
| 019 | Resolved attributes ignore staged template edits |
| 017 | Template warning badges not updated after cascade change |
| 002-badge | Broken reference badge persists after undo |
| 003-relationships | Stale impact/relationships panel after tab switch |

Root cause: UI components read from committed `allObjects`, not from the staging layer; no re-render triggered on staging state changes.

---

### F — Rename cascade & reference integrity (5 bugs)
| Bug | Title |
|-----|-------|
| 001-rename | Rename does not cascade to hostgroup references |
| 003-bulk-rename | Bulk rename only renames single object |
| 029 | Rename host does not update service `host_name` references |
| 030 | Bulk rename has no reference-update option |
| 076 | Rename without reference update can commit broken config |

Root cause: rename API has cascade logic but it is not exposed in the rename dialog UI; bulk rename iterates incorrectly.

---

### G — Destructive operation safety (3 bugs)
| Bug | Title |
|-----|-------|
| 003-delete | File deletion has no confirmation dialog |
| 038 | Delete file with objects shows no object-count warning |
| 065 | Context menu delete has no confirmation |

Root cause: destructive operations staged immediately with no secondary confirmation or object-count feedback.

---

### H — Undo stack (4 bugs)
| Bug | Title |
|-----|-------|
| 005 | Ctrl+Z fires API even when undo button is disabled |
| 020 | Ctrl+Z undoes multiple operations per keystroke |
| 027 | Undo description shows "Unknown" |
| 028 | Concurrent undo race condition |

Root cause: keyboard handler ignores button disabled state; undo stack pop logic is mis-grouped; object name resolution fails in description generation; no request queuing for concurrent calls.

---

### I — Multi-select & bulk edit (4 bugs)
| Bug | Title |
|-----|-------|
| 031 | Right-click during multi-select navigates to clicked object |
| 032 | Bulk edit count mismatch with no explanation |
| 033 | Mixed-type bulk edit applies invalid attributes to all types |
| 034 | Select-by-type dialog throws InvalidStateError |

Root cause: right-click handler does not check multi-select mode; bulk edit applies fields without type-compatibility check; dialog state error in context menu handler.

---

### J — Staging system integrity (3 bugs)
| Bug | Title |
|-----|-------|
| 001-staging | Staging state carries stale file paths when config is copied |
| 021 | Move-to-file dialog ignores object type compatibility |
| 025 | Drag allowed to staged-deleted file |

Root cause: staging state not validated against current file tree; move/drag targets not checked against `stagedFileDeletions`.

---

### K — Object creation & cloning (7 bugs)
| Bug | Title |
|-----|-------|
| 001-inline-comments | Inline comments not visible in object preview |
| 001-plus | Plus button wrong default type for file context |
| 002-inline | Inline object creation has no cancel mechanism |
| 003-clone | Clone drops inline comments |
| 007 | Plus button inherits type from previous form |
| 010 | Name field primary key desyncs after initial auto-fill |
| 036 | Clone dialog has no target file selection |

Root cause: creation path has several independent gaps — form state leaks, missing `inline_comments` in clone/preview, no cancel path, no file selector in clone.

---

### L — Search, filter & orphan visibility (5 bugs)
| Bug | Title |
|-----|-------|
| 059 | Search shows no empty-state message when results are zero |
| 060 | Search has no match highlighting |
| 061 | Orphan services invisible to both filter checkboxes |
| 062 | Combined filters use AND logic instead of OR |
| 063 | "Create missing host" defaults to services.cfg instead of hosts.cfg |

Root cause: filter logic uses intersection instead of union; `orphan_service` API type not mapped to UI filter; no empty-state or highlighting in search results.

---

### M — Audit log & commit accuracy (6 bugs)
| Bug | Title |
|-----|-------|
| 068 | Audit log action always shows "edit" for all operation types |
| 069 | Audit log move stores absolute paths |
| 071 | File/folder operations missing from audit log filters |
| 072 | No external file modification conflict detection |
| 073 | Commit diff preview excludes external modifications |
| 074 | Commit dialog switches between staging preview and full git diff |

Root cause: action field hardcoded as `"edit"`; paths not normalized before logging; filter value format mismatch; commit dialog does not always show full git diff; no mtime/hash freshness check before write.

---

## Execution Order

| # | Cluster | Rationale |
|---|---------|-----------|
| 1 | A — Crashes & null guards | Server crashes and state corruption block everything |
| 2 | B — Lock enforcement | Lock bypass is a critical safety violation |
| 3 | C — Reference field validation | Blocking basic editing (check_command, wildcards) |
| 4 | D — Duplicate validation | Data integrity at creation time |
| 5 | E — Staged state display | Users think edits are lost; high confusion factor |
| 6 | F — Rename cascade | Broken references left behind after rename |
| 7 | G — Destructive safety | One-click config destruction with no confirmation |
| 8 | H — Undo stack | Correctness of primary safety mechanism |
| 9 | I — Multi-select & bulk edit | Bulk ops apply wrong changes silently |
| 10 | J — Staging integrity | Edge cases in drag/move that corrupt state |
| 11 | K — Object creation & cloning | UX gaps in creation flow |
| 12 | L — Search & filter | Discoverability improvements |
| 13 | M — Audit log & commit | Accuracy and observability |

---

## Per-Session Workflow (each cluster)

1. **Analyse with Playwright** — reproduce each bug in the browser before touching code; confirm exact failure mode
2. **Identify root cause** — read relevant source files; propose a minimal fix that resolves multiple bugs in the cluster
3. **Implement fix** — edit backend and/or frontend; no speculative changes outside cluster scope
4. **Validate with Playwright** — reproduce each bug again to confirm resolution; check for regressions
5. **Lint** — run `ruff check` for Python changes, `npx eslint` for JS changes; fix any new issues
