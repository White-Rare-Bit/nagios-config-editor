# 042 — Editor Fields Not Read-Only While Staging Is Locked

**Phase:** 18 — Multi-Tab Lock  
**Severity:** Major  
**Category:** Locking / UX

## Steps to Reproduce

1. Tab 1: Open an object and make an edit (acquires session lock)
2. Tab 2: Open the same explorer (different session ID) — lock banner appears
3. Tab 2: Select an object, click into a field (e.g., `alias`), type a value
4. Tab 2: Tab out of the field to trigger save

## Actual Behavior

- The field accepts input — the typed value appears in the editor
- On save, the server returns 423 and a toast fires: "Staging is locked by another user"
- The field **still displays the typed (rejected) value** — there is no rollback to the original

## Expected Behavior

- Input fields should be **disabled or read-only** while staging is locked by another session
- The user should not be able to type at all, preventing false impressions of editing
- Alternatively, clicking a field should immediately show an inline message explaining the lock

## Impact

An admin on a locked Tab 2 can freely type changes across multiple fields. Each field change is silently rejected on blur (with a toast). If the admin types several edits quickly without reading toasts, they may believe all changes are staged. This is a data-loss risk — the admin thinks they edited, but nothing was saved.

## Screenshots

- `.playwright-mcp/phase18-02-tab2-edit-blocked-toast.png` — alias shows "Tab2 attempt" after rejected save
