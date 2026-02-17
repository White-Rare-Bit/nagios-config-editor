# Logs Page Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix four issues identified in the logs page: werkzeug noise in app log, wrong entry count, invisible transaction grouping, and empty user column.

**Architecture:** Targeted fixes across backend (app.py, routes/logs.py) and frontend (logs.js, logs.css). Each fix is independent and testable in isolation.

**Tech Stack:** Python stdlib logging, Flask, plain JavaScript, CSS.

**Design doc:** `docs/plans/2026-02-17-logs-page-fixes-design.md`

---

## Task 1: Suppress werkzeug from app.log

**Files:**
- Modify: `app.py` (line 67, after `root_logger.addHandler(app_handler)`)

**Step 1: Add werkzeug suppression**

After line 67 (`root_logger.addHandler(app_handler)`), add:

```python
    # Suppress werkzeug request logs from app.log — only errors reach the file
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS (342 tests).

**Step 3: Commit**

```bash
git add app.py
git commit -m "fix: suppress werkzeug request logs from app.log"
```

---

## Task 2: Fix total count in log API

**Files:**
- Modify: `routes/logs.py` (lines 74-106, `_read_log_entries`)
- Modify: `tests/test_log_routes.py` (add tests for `_read_log_entries`)

**Step 1: Write tests for `_read_log_entries`**

Add to `tests/test_log_routes.py`:

```python
import tempfile

from routes.logs import _read_log_entries, parse_audit_line, parse_app_line


class TestReadLogEntries:
    """Test _read_log_entries returns correct total and entries."""

    def test_total_counts_only_parsed_entries(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "Feb 17 14:00:00 AUDIT txn=a user=x action=apply op=create\n"
            "garbage line\n"
            "Feb 17 14:00:01 AUDIT txn=b user=y action=apply op=delete\n"
        )
        entries, total = _read_log_entries(str(log_file), parse_audit_line)
        assert total == 2  # not 3 (skips garbage line)
        assert len(entries) == 2

    def test_returns_entries_newest_first(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "Feb 17 14:00:00 AUDIT txn=a user=x action=first op=create\n"
            "Feb 17 14:00:01 AUDIT txn=b user=y action=second op=delete\n"
        )
        entries, total = _read_log_entries(str(log_file), parse_audit_line)
        assert entries[0]["action"] == "second"
        assert entries[1]["action"] == "first"

    def test_missing_file_returns_empty(self, tmp_path):
        entries, total = _read_log_entries(str(tmp_path / "nope.log"), parse_audit_line)
        assert entries == []
        assert total == 0

    def test_limit_caps_returned_entries(self, tmp_path):
        log_file = tmp_path / "test.log"
        lines = [f"Feb 17 14:00:0{i} AUDIT txn=a user=x action=apply op=create\n" for i in range(5)]
        log_file.write_text("".join(lines))
        entries, total = _read_log_entries(str(log_file), parse_audit_line, limit=2)
        assert len(entries) == 2
        assert total == 5  # total is all parsed entries, not limited
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_log_routes.py::TestReadLogEntries -v`
Expected: `test_total_counts_only_parsed_entries` FAILS (total=3 instead of 2), `test_limit_caps_returned_entries` FAILS (total != 5).

**Step 3: Rewrite `_read_log_entries`**

Replace lines 74-106 in `routes/logs.py`:

```python
def _read_log_entries(log_path, parser_fn, limit=10000, offset=0, filter_key=None, filter_value=None):
    """Read and parse log entries from a .log file.

    Returns (entries, total) where total is the count of all parsed entries
    (not raw lines) and entries is the offset/limit slice in reverse order.
    """
    if not os.path.exists(log_path):
        return [], 0

    try:
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return [], 0

    # Parse all valid entries in reverse order (newest first)
    all_entries = []
    for line in reversed(lines):
        entry = parser_fn(line)
        if entry is None:
            continue
        if filter_key and filter_value:
            if entry.get(filter_key, "").upper() != filter_value.upper():
                continue
        all_entries.append(entry)

    total = len(all_entries)
    entries = all_entries[offset:offset + limit]
    return entries, total
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_log_routes.py -v`
Expected: All PASS.

**Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS.

**Step 6: Commit**

```bash
git add routes/logs.py tests/test_log_routes.py
git commit -m "fix: return parsed entry count instead of raw line count in log API"
```

---

## Task 3: Add transaction group separators and em dash for empty user

**Files:**
- Modify: `static/js/logs.js` (lines 258-273 `renderAuditRows`, line 293 user cell)
- Modify: `static/css/logs.css` (after line 289, add separator style)

**Step 1: Update `renderAuditRows` in `static/js/logs.js`**

Replace lines 258-273:

```javascript
function renderAuditRows(tbody, pageEntries) {
    let lastTxn = null;

    pageEntries.forEach(entry => {
        const txn = entry.txn || '';
        const isContinuation = txn && txn === lastTxn;
        const isGroupStart = txn && txn !== lastTxn;

        // Insert separator between different transaction groups
        if (isGroupStart && lastTxn !== null) {
            tbody.insertAdjacentHTML('beforeend',
                '<tr class="logs-txn-separator"><td colspan="5"></td></tr>');
        }

        lastTxn = txn;

        const classes = [];
        if (isGroupStart || isContinuation) {classes.push('logs-txn-group');}
        if (isContinuation) {classes.push('logs-txn-continuation');}

        tbody.insertAdjacentHTML('beforeend', renderAuditRow(entry, classes));
    });
}
```

**Step 2: Update user cell in `renderAuditRow`**

In `static/js/logs.js`, change line 293 from:

```javascript
        <td class="logs-col-user">${escapeHtml(entry.user || '')}</td>
```

To:

```javascript
        <td class="logs-col-user">${entry.user ? escapeHtml(entry.user) : '<span class="logs-text-muted">\u2014</span>'}</td>
```

**Step 3: Add separator CSS to `static/css/logs.css`**

After the transaction grouping section (after line 289), add:

```css
.logs-txn-separator td {
    height: var(--nbe-space-sm);
    padding: 0;
    border: none;
    background: transparent;
}

.logs-txn-separator + tr td:first-child {
    border-left: 3px solid var(--nbe-dark-accent-primary);
}

.logs-text-muted {
    color: var(--nbe-dark-text-muted);
}
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS (frontend-only changes, no backend tests affected).

**Step 5: Commit**

```bash
git add static/js/logs.js static/css/logs.css
git commit -m "fix: add transaction group separators and em dash for empty user"
```

---

## Task 4: Verify all fixes

**Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All PASS.

**Step 2: Manual verification checklist**

Start app: `python3 app.py`

- [ ] Application Log tab no longer shows werkzeug request logs
- [ ] Entry count badge shows actual parsed entry count
- [ ] Pagination "Showing X-Y of Z" matches real numbers
- [ ] Audit log rows with empty user show "—" (em dash)
- [ ] Multiple transactions on same page show gap separators between groups
- [ ] Continuation rows within a group still have dimmed timestamp/user/action

**Step 3: Commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration fixes for logs page"
```
