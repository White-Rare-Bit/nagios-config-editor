# L14: `static/js/CLAUDE.md` -- MODIFY

**Layer:** 14 -- Documentation Updates
**Action:** MODIFY
**Path:** `static/js/CLAUDE.md`
**Dependencies:** L06-candidate-api.md (candidate-api.js created), L09-lock-manager.md (lock-manager.js updated), L06-api-client.md (api-client.js updated)
**Goal:** Add candidate-api.js to the Core Modules table and update stale staging terminology in existing module descriptions. This is a documentation-only change -- no code is modified.

---

## Preconditions

Before this plan executes, the following L-plans must be complete:

- L06-candidate-api.md: `candidate-api.js` exists and is loaded on every page
- L06-api-client.md: `api-client.js` updated (staging headers removed, session headers added)
- L09-lock-manager.md: `lock-manager.js` updated (staging lock polling replaced with candidate session polling)

This plan is purely a documentation update. No JavaScript code, CSS, templates, or backend files are modified.

---

## Functionality Migration Checklist

This plan documents module description changes that reflect functionality migrations completed in prior layers:

| Old Description | New Description | Migration Done In |
|-----------------|-----------------|-------------------|
| `api-client.js`: "staging headers" | `api-client.js`: "session headers" | L06-api-client.md |
| `lock-manager.js`: "Staging lock polling" | `lock-manager.js`: "Candidate session polling" | L09-lock-manager.md |
| (no entry) | `candidate-api.js`: CandidateApi wrapper | L06-candidate-api.md |

No functionality is removed or degraded. All changes are terminology updates in documentation to match already-migrated code.

---

## Removal Audit

Staging terminology removed from `static/js/CLAUDE.md`:

| Location | Old Text | New Text | Reason |
|----------|----------|----------|--------|
| `api-client.js` row | "staging headers" | "session headers" | api-client.js no longer sends staging headers (L06) |
| `lock-manager.js` row | "Staging lock polling and banner" | "Candidate session polling and lock banner" | lock-manager.js polls candidate session, not staging lock (L09) |

No content is deleted without replacement. One new row is added (`candidate-api.js`).

---

## Changes

### Step 1: Add `candidate-api.js` to Core Modules table

Add new row after `api-client.js`:
```markdown
| `candidate-api.js` | CandidateApi wrapper for candidate session operations |
```

### Step 2: Update `api-client.js` description

Before:
```markdown
| `api-client.js` | Fetch wrapper, staging headers, `{success, data, error}` format |
```

After:
```markdown
| `api-client.js` | Fetch wrapper, session headers, `{success, data, error}` format |
```

### Step 3: Update `lock-manager.js` description

Before:
```markdown
| `lock-manager.js` | Staging lock polling and banner |
```

After:
```markdown
| `lock-manager.js` | Candidate session polling and lock banner |
```

### Step 4: Verify `session-manager.js` needs no change

```markdown
<!-- Current (already generic, no change needed) -->
| `session-manager.js` | Session ID and user identity management |
```

No edit required -- description is already implementation-agnostic.

---

## Change Tracking

| # | Change | Status |
|---|--------|--------|
| 1 | Add `candidate-api.js` row to Core Modules table | [ ] |
| 2 | Update `api-client.js` description: "staging headers" to "session headers" | [ ] |
| 3 | Update `lock-manager.js` description: "Staging lock polling" to "Candidate session polling" | [ ] |
| 4 | Confirm `session-manager.js` row needs no change | [ ] |
| 5 | Run verification grep for stale "staging" references | [ ] |

---

## Verification

```bash
# 1. No stale staging references in the file
grep -i "staging" static/js/CLAUDE.md && echo "FAIL: stale staging references" || echo "PASS: no staging references"

# 2. Confirm candidate-api.js is documented
grep "candidate-api.js" static/js/CLAUDE.md && echo "PASS: candidate-api.js present" || echo "FAIL: candidate-api.js missing"

# 3. Confirm session headers terminology
grep "session headers" static/js/CLAUDE.md && echo "PASS: session headers present" || echo "FAIL: session headers missing"

# 4. Confirm candidate session polling terminology
grep "Candidate session polling" static/js/CLAUDE.md && echo "PASS: candidate session polling present" || echo "FAIL: candidate session polling missing"

# 5. Validate markdown structure (no broken table formatting)
python3 -c "
with open('static/js/CLAUDE.md') as f:
    lines = f.readlines()
table_rows = [l for l in lines if l.startswith('|')]
for i, row in enumerate(table_rows):
    cols = row.strip().split('|')
    assert len(cols) >= 3, f'Broken table row {i+1}: {row.strip()}'
print('Table structure valid')
print('OK')
"
```

---

## Playwright Validation

This plan modifies only a markdown documentation file (`static/js/CLAUDE.md`). It does not change any JavaScript code, HTML templates, CSS, or backend logic. No UI rendering, API behavior, or user-visible functionality is affected.

**Playwright applicability:** Not applicable. Documentation-only changes have no runtime behavior to validate with Playwright. No existing tests can break from this change since CLAUDE.md is not served to users or parsed at runtime.

---

## Commandments Compliance

| # | Commandment | Status | Notes |
|---|------------|--------|-------|
| 1 | No live config mutation until Apply | COMPLIANT | Documentation-only change. No code is modified. No mutation paths are added, removed, or altered. |
| 2 | UI visual parity | COMPLIANT | No UI changes. This modifies a developer documentation file, not any user-facing template, CSS, or JavaScript. |
| 3 | Full audit logging | COMPLIANT | No operations are introduced or modified. Audit logging is not applicable to markdown documentation changes. |
| 4 | Proper error handling | COMPLIANT | No code paths are changed. No error handling is added, removed, or degraded. |
| 5 | Dead code deletion | COMPLIANT | Stale "staging" terminology in module descriptions is replaced with accurate "candidate"/"session" terminology. No dead documentation is left behind. Removal Audit section above tracks each replacement. |
| 6 | Full functionality migration | COMPLIANT | Functionality Migration Checklist above confirms every description change reflects a real code migration completed in a prior L-plan (L06, L09). New `candidate-api.js` module is documented. Nothing is dropped. |
| 7 | Palo Alto candidate model | COMPLIANT | Updated terminology reflects the Palo Alto copy-edit-apply model: "staging headers" becomes "session headers", "staging lock" becomes "candidate session". |
| 8 | Change tracking document | COMPLIANT | Change Tracking table with 5 items and completion checkboxes included above. |
| 9 | Complete planning before implementation | COMPLIANT | Plan is fully specified with exact before/after text, preconditions, removal audit, functionality migration checklist, and verification scripts. No ambiguity remains. |
| 10 | Linting enforcement | COMPLIANT | Not directly applicable (markdown file, not code). Verification section includes structural validation of markdown table formatting to ensure the edit does not break the document. |
| 11 | Playwright validation | COMPLIANT | Addressed in Playwright Validation section. Documentation-only change has no runtime behavior -- Playwright tests are not applicable. |
