# Cluster C — Reference Field Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 reference field validation bugs: check_command autocomplete resets after `!` (013), check_command args validated as object references and field cleared (014), wildcard `*` rejected as invalid reference (015), hostgroup_name/service_description missing autocomplete in escalation/dependency objects (058), autocomplete hard-capped at 20 suggestions (016).

**Architecture:** All fixes are in `object-editor.js` reference validation and autocomplete filtering. The core issue is that reference validators don't handle Nagios special syntax (`!` separator, `*` wildcard) and don't recognise some fields as references in escalation/dependency object types.

**Tech Stack:** JavaScript (ES6+). Key files: `static/js/explorer/object-editor.js`, `static/js/explorer/constants.js`, `nagios_model.py`.

---

### Task 1: Reproduce all 5 bugs with Playwright

**Files:**
- Read: `docs/test-discoveries/013-check-command-autocomplete-resets-after-exclamation.md`
- Read: `docs/test-discoveries/014-check-command-arguments-validated-as-object-references.md`
- Read: `docs/test-discoveries/015-wildcard-star-rejected-as-invalid-reference.md`
- Read: `docs/test-discoveries/058-hostgroup-name-service-description-missing-autocomplete.md`
- Read: `docs/test-discoveries/016-autocomplete-truncated-at-20-suggestions.md`

**Step 1: Start app and navigate to a service**
Navigate to http://localhost:8080 → Explorer → By Type → service → any service

**Step 2: Reproduce 013 — autocomplete resets after !**
1. Click the `check_command` field
2. Type `check_ping` — autocomplete should show just check_ping
3. Type `!` — observe autocomplete dropdown: it should close/stay on check_ping but instead resets to show all commands
4. Take screenshot: `.playwright-mcp/repro-013.png`

**Step 3: Reproduce 014 — args validated as references**
1. Click `check_command`, clear it, type `check_ping!100,20%!500,60%`
2. Click elsewhere (blur the field)
3. Expected: value saved. Actual: toast "\"20%\" does not exist", field cleared
4. Take screenshot: `.playwright-mcp/repro-014.png`

**Step 4: Reproduce 015 — wildcard rejected**
1. Click the `host_name` field of a service
2. Clear it, type `*`
3. Click elsewhere
4. Expected: `*` accepted. Actual: toast "\"*\" does not exist", field cleared
5. Take screenshot

**Step 5: Reproduce 058 — missing autocomplete in escalation/dependency**
1. Navigate to By Type → serviceescalation → any escalation
2. Click the `hostgroup_name` field
3. Type a few chars — observe: no autocomplete dropdown appears
4. Also check `service_description` field
5. Take screenshot

**Step 6: Reproduce 016 — truncated at 20**
1. On a service, click `check_command`
2. Type `check_` — count the number of suggestions
3. Expected: all 30+ commands. Actual: exactly 20, silently truncated

---

### Task 2: Fix 014/015 — Reference validation: allow ! syntax and wildcards

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js`

**Step 1: Find the validateReferenceValue function**
Read `static/js/explorer/object-editor.js`. Search for `validateReferenceValue` (around line 838).

**Step 2: Understand the validation loop**
The function iterates over comma-separated values. For command attrs it already does `v.split('!')[0]`. But verify this is actually working — the bug report says args still get validated. Look carefully at:
1. How `COMMAND_ATTRS` is defined — does it include `check_command`?
2. Whether `parseCommaValues` correctly handles the `!` separator

**Step 3: Fix wildcard handling (015)**
In the validation loop, after stripping prefix, add a wildcard bypass BEFORE the existence check:
```javascript
// After: checkValue = Explorer.stripPrefix(checkValue);
// ADD:
if (checkValue === '*' || checkValue === '') { continue; }
```

**Step 4: Fix check_command argument handling (014)**
Ensure `COMMAND_ATTRS` is correctly defined and includes `check_command`. Find where it is defined and if it is missing the field name, add it:
```javascript
const COMMAND_ATTRS = new Set(['check_command', 'event_handler', 'check_freshness']);
// (adjust to whatever is the correct set)
```

Also ensure the split on `!` only takes index 0:
```javascript
let checkValue = isCommandAttr ? v.split('!')[0].trim() : v;
```

**Step 5: Also fix the Add Attribute dialog validation**
Search for similar validation in the dialog code (around line 986-1005 based on prior analysis). Apply the same wildcard bypass and command split fix.

**Step 6: Validate with Playwright**
Reproduce Task 1 Steps 3 and 4:
- `check_ping!100,20%!500,60%` should be saved without toast
- `*` in host_name should be saved without toast

**Step 7: Run ESLint**

**Step 8: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: allow Nagios special values in reference field validation

Fixes #014, #015 — check_command arguments after ! and wildcard * were
validated as object references and the field was cleared on failure.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Fix 013 — Autocomplete closes/resets after ! character

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js`

**Step 1: Find filterCommaValueSuggestions or autocomplete filtering**
Search `object-editor.js` for where autocomplete suggestions are filtered as the user types. Based on prior analysis, it's around line 712-732. The issue is that `currentPart` after typing `check_ping!` becomes `check_ping!` which doesn't match `check_ping` in the suggestions list.

**Step 2: Extract command name for filtering**
Find the variable that stores the current typed part (the portion being filtered). For command attributes, strip everything after `!`:

```javascript
// Find where currentPart is derived from the input value
// For command fields, strip the arguments:
const isCommandField = /* check if current attribute is a command attr */;
if (isCommandField) {
    currentPart = currentPart.split('!')[0];
}
```

This way, after typing `check_ping!`, the filter uses `check_ping` which matches the suggestion.

**Step 3: Also close/hide autocomplete after ! for command fields**
If the user has already typed past the `!`, the command name is already selected and the autocomplete should close. Add logic:

```javascript
// If command field and value contains !, close autocomplete
if (isCommandField && inputValue.includes('!')) {
    // Check if portion before ! matches a command exactly
    const commandPart = inputValue.split('!')[0].trim();
    const exactMatch = allSuggestions.some(s => s.toLowerCase() === commandPart.toLowerCase());
    if (exactMatch) {
        return []; // Return empty to close/hide dropdown
    }
}
```

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 2. After typing `check_ping`, autocomplete should filter to just `check_ping`. After typing `!`, autocomplete should close or stay filtered to `check_ping` (not reset to all commands).

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: autocomplete for check_command handles ! separator correctly

Fixes #013 — autocomplete reset to all commands after ! was typed,
because the filter treated the ! as part of the search query.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Fix 058 — Add missing autocomplete for escalation/dependency reference fields

**Files:**
- Read: `nagios_model.py` (REFERENCE_FIELDS, NAME_FIELDS)
- Read: `static/js/explorer/constants.js` (how ATTR_REFERENCE_MAP is built from metadata)
- Read + Modify: `static/js/explorer/object-editor.py` (getAttributeSuggestions)

**Step 1: Check what REFERENCE_FIELDS contains in nagios_model.py**
Read `nagios_model.py`. Search for `REFERENCE_FIELDS`. Confirm that `hostgroup_name`, `service_description`, and `host_name` are present with their target types.

**Step 2: Check how frontend receives the reference map**
Read `static/js/explorer/constants.js` around line 163 (`getFieldsForType`). Read how `ATTR_REFERENCE_MAP` or `constants.reference_fields` is populated from the API response. Does it contain `hostgroup_name → hostgroup`?

If not, find the API endpoint that serves metadata (likely `GET /api/metadata` or `GET /api/constants`) and read the route file.

**Step 3: Check getAttributeSuggestions function**
Read `object-editor.js` around line 350-382. Find where `constants.ATTR_REFERENCE_MAP[attrName]` is used. Verify that `hostgroup_name` is in the map.

**Step 4: Fix — ensure ATTR_REFERENCE_MAP is populated from backend metadata**
If `constants.ATTR_REFERENCE_MAP` doesn't include `hostgroup_name: 'hostgroup'`, find where it is built and add the missing entries, OR ensure the backend `nagios_model.py` REFERENCE_FIELDS are being sent to the frontend correctly.

If the metadata IS correct but the frontend `getAttributeSuggestions` isn't using it for escalation/dependency objects, find the type-specific override code and make it fall through to the global reference map.

**Step 5: Validate with Playwright**
Reproduce Task 1 Step 5. Navigate to serviceescalation, click `hostgroup_name` — autocomplete dropdown should appear with hostgroup suggestions.

**Step 6: Run ESLint / ruff as appropriate**

**Step 7: Commit**
```bash
git add static/js/explorer/object-editor.js static/js/explorer/constants.js nagios_model.py
git commit -m "fix: add missing autocomplete for hostgroup_name/service_description in escalation/dependency

Fixes #058 — reference fields in escalation and dependency object types
rendered as plain text inputs with no autocomplete suggestions.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Fix 016 — Remove hard cap of 20 autocomplete suggestions

**Files:**
- Read + Modify: `static/js/explorer/object-editor.js`

**Step 1: Find the limit**
Search `object-editor.js` for `slice(0, 20)` or `.length > 20` or a constant like `MAX_SUGGESTIONS`. This is where suggestions are truncated.

**Step 2: Option A — Remove the cap entirely (scrollable dropdown)**
If the dropdown already scrolls, simply remove or increase the limit:
```javascript
// Change: .slice(0, 20)
// To: (no limit, or .slice(0, 100) for a generous cap)
```

**Step 3: Option B — Add "N more…" indicator**
If the dropdown should remain capped at 20, add a non-selectable footer item showing the count:
```javascript
const MAX = 20;
const allMatches = /* all filtered suggestions */;
const shown = allMatches.slice(0, MAX);
if (allMatches.length > MAX) {
    shown.push({ label: `… and ${allMatches.length - MAX} more`, disabled: true });
}
```

**Step 4: Validate with Playwright**
Reproduce Task 1 Step 6. Type `check_` and verify more than 20 commands appear (or a "N more" indicator is shown).

**Step 5: Run ESLint**

**Step 6: Commit**
```bash
git add static/js/explorer/object-editor.js
git commit -m "fix: remove hard cap of 20 autocomplete suggestions

Fixes #016 — suggestion list was silently truncated at 20 with no indicator
that more matches existed. Now shows all matches or displays a count.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Final Playwright validation — all 5 bugs resolved

Verify:
- [ ] Typing `check_ping!100,20%!500,60%` saves without error (014)
- [ ] Typing `*` in host_name saves without error (015)
- [ ] After typing `check_ping!`, autocomplete shows check_ping or closes (013)
- [ ] serviceescalation hostgroup_name shows autocomplete suggestions (058)
- [ ] Typing `check_` shows more than 20 commands or "N more" indicator (016)

Run: `python3 -m pytest tests/ -v`
