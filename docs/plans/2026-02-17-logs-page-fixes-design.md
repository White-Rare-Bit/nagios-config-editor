# Logs Page Fixes — Design

**Goal:** Fix four data/UI issues identified in the logs page after initial implementation.

**Context:** The logging overhaul replaced the old audit log page with a unified `/logs` page with Audit and Application tabs. Screenshots revealed several issues with the data pipeline and visual presentation.

---

## Fix 1: Suppress werkzeug from app.log

**Problem:** The Application Log tab is flooded with werkzeug HTTP request logs (every `GET /api/...` request), burying actual application events.

**Solution:** In `app.py:_setup_logging()`, set `logging.getLogger("werkzeug").propagate = False`. This prevents Flask's request-level logging from reaching the root logger's file handler. Only application code events (backup, parser, apply, git) will appear in app.log.

**Files:** `app.py`

---

## Fix 2: Correct total count in API

**Problem:** `_read_log_entries()` returns `total = len(lines)` (raw file lines), not the count of successfully parsed entries. The frontend shows "(10000 entries)" and "Showing 1-25 of 10000" which are both wrong.

**Solution:** Parse all entries first, then count. Return the actual number of parsed entries as `total`. Since the frontend now loads all entries for client-side pagination (limit=10000), simplify the API: parse all lines, return the full list, let the frontend handle pagination entirely.

**Files:** `routes/logs.py`

---

## Fix 3: Transaction grouping with gaps

**Problem:** When all rows on a page share one txn (common after a bulk Apply), the blue-border + dimming grouping is invisible because there's no contrast with ungrouped rows.

**Solution:** In `renderAuditRows()`, insert a spacer `<tr class="logs-txn-separator">` between different transaction groups. CSS gives it a small height (~8px) with no background, creating a visual break. Keep the existing blue left border and continuation dimming as secondary cues within each group.

**Files:** `static/js/logs.js`, `static/css/logs.css`

---

## Fix 4: Em dash for empty user

**Problem:** When no identity is configured, the User column shows blank cells — looks broken.

**Solution:** In `renderAuditRow()`, render `—` (em dash) with muted text styling when `entry.user` is empty.

**Files:** `static/js/logs.js`
