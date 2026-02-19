# Cluster L — Search, Filter & Orphan Visibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 search/filter bugs: empty-state message for zero results, match highlighting, orphan service visibility, AND-vs-OR filter logic, and "create missing host" default file.

**Architecture:** All frontend fixes live in the search/filter JS. The filter bug (062) changes filter composition from AND (intersection) to OR (union). The orphan mapping (061) adds `orphan_service` to the "services without hosts" checkbox. The "create missing host" default (063) selects `hosts.cfg` over `services.cfg` by preferring files whose name or contents match the object type being created.

**Tech Stack:** JavaScript. Key files: `static/js/explorer/app.js`, `static/js/explorer/search.js` (or wherever search/filter logic lives), `static/js/explorer/object-list.js` (or tree rendering code).

---

## Task 1: Reproduce all 5 bugs with Playwright

**Step 1:** Start the app.

```bash
python3 app.py
```

Navigate to http://localhost:8080. Take a screenshot to `.playwright-mcp/repro-059-start.png`.

**Step 2:** Reproduce 059 — no empty-state message when search returns zero results.

In the search box, type a query that will return no matches (e.g., `zzz_no_match_xyz`). Observe the results area — it will be blank with no message explaining there are no results. Take a screenshot to `.playwright-mcp/repro-059.png`.

**Step 3:** Reproduce 060 — search results show no match highlighting.

Clear the previous search. Type `prod` (or any string that appears in some object names). Observe that matching results are shown but the matched substring is not highlighted/emphasized within each object name. Take a screenshot to `.playwright-mcp/repro-060.png`.

**Step 4:** Reproduce 061 — orphan services invisible to "services without a host" checkbox.

Open the filter panel. Check the "services without a host" (or equivalent) checkbox. Observe that objects with `object_type === 'orphan_service'` do not appear in the filtered list — only zero or incorrect results show. Take a screenshot to `.playwright-mcp/repro-061.png`.

**Step 5:** Reproduce 062 — combined filters use AND logic instead of OR.

Enable two different type filter checkboxes (e.g., "hosts" and "services"). Observe that only objects matching BOTH conditions appear, producing an empty or incorrect set rather than the union of both sets. Take a screenshot to `.playwright-mcp/repro-062.png`.

**Step 6:** Reproduce 063 — "Create missing host" defaults to services.cfg.

Right-click an orphan service (a service with no valid host). Click "Create missing host". Observe that the file picker in the dialog defaults to `services.cfg` or some non-host file rather than `hosts.cfg`. Take a screenshot to `.playwright-mcp/repro-063.png`.

---

## Task 2: Fix 062 — Change filter composition from AND to OR

**Step 1:** Read the filter application function. Search for where multiple active filters are combined:

```bash
grep -n "filter" static/js/explorer/app.js | head -60
grep -rn "activeFilters\|applyFilters\|filterObjects" static/js/explorer/
```

**Step 2:** Find the code that chains `.filter()` calls in sequence (AND logic). It will look like:

```javascript
// AND pattern (current, wrong):
let result = allObjects;
activeFilters.forEach(f => result = result.filter(o => f(o)));
```

**Step 3:** Replace with OR (union) logic. Objects matching ANY active filter are included. Preserve the original order from `allObjects`:

```javascript
// OR pattern (correct):
if (activeFilters.length === 0) {
    result = allObjects; // no filters active → show all
} else {
    const matchingKeys = new Set(
        activeFilters.flatMap(f =>
            allObjects
                .filter(o => f(o))
                .map(o => o.stable_key ?? o.global_index)
        )
    );
    result = allObjects.filter(o =>
        matchingKeys.has(o.stable_key ?? o.global_index)
    );
}
```

**Step 4:** Ensure the special case is preserved — if no filters are active, all objects are shown (behavior unchanged from before).

**Step 5:** Validate with Playwright. Enable two type-filter checkboxes. Both sets of objects should now be visible simultaneously. Take a screenshot to `.playwright-mcp/validate-062.png`.

**Step 6:** Run ESLint:

```bash
npx eslint static/js/explorer/
```

Fix any reported issues.

**Step 7:** Commit:

```bash
git add static/js/explorer/app.js  # (or whichever file was changed)
git commit -m "$(cat <<'EOF'
fix(filter): change filter composition from AND to OR (union)

Multiple active type-filter checkboxes now show the union of matching
objects rather than the intersection, matching user expectation that
enabling "hosts" AND "services" shows both, not neither.

Fixes bug 062.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Fix 061 — Map orphan_service to the "services without a host" filter checkbox

**Step 1:** Find the filter checkbox handler for "services without a host". Search for where `object_type` values are compared in filter logic:

```bash
grep -rn "orphan\|without.*host\|host.*without\|orphan_service" static/js/explorer/
```

**Step 2:** Find the predicate function for the "services without a host" checkbox. It likely checks `object_type === 'service'` and some orphan condition, but misses `object_type === 'orphan_service'`.

**Step 3:** Add `orphan_service` to the predicate so the checkbox reveals both conventional orphan flags and the dedicated orphan type:

```javascript
// Before:
const isServicesWithoutHost = o =>
    o.object_type === 'service' && isOrphan(o);

// After:
const isServicesWithoutHost = o =>
    o.object_type === 'orphan_service' ||
    (o.object_type === 'service' && isOrphan(o));
```

**Step 4:** Also ensure that the regular "services" checkbox includes `orphan_service` objects. An orphan service IS a service — hiding it from the "services" filter would be a separate usability problem. Find the "services" checkbox predicate and add `orphan_service`:

```javascript
// Before:
const isService = o => o.object_type === 'service';

// After:
const isService = o =>
    o.object_type === 'service' || o.object_type === 'orphan_service';
```

**Step 5:** Validate with Playwright. Toggle the "services without a host" checkbox — orphan_service objects should now appear. Take a screenshot to `.playwright-mcp/validate-061.png`.

**Step 6:** Run ESLint:

```bash
npx eslint static/js/explorer/
```

**Step 7:** Commit:

```bash
git add static/js/explorer/  # stage changed files
git commit -m "$(cat <<'EOF'
fix(filter): map orphan_service type to 'services without a host' checkbox

Objects returned by the API with object_type 'orphan_service' were
invisible to both filter checkboxes. They now appear when either
'services' or 'services without a host' is checked.

Fixes bug 061.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Fix 059 and 060 — Empty-state message and match highlighting in search

**Step 1:** Find the search results rendering function:

```bash
grep -rn "renderSearch\|searchResults\|displayResults\|renderResults" static/js/explorer/
grep -rn "search" static/js/explorer/search.js | head -40
```

**Step 2:** Fix 059 — empty-state message. After filtering, when `results.length === 0`, render an informative message rather than an empty list. Find the point where the results list is populated and add:

```javascript
function renderSearchResults(results, query) {
    const container = document.getElementById('search-results'); // adjust selector
    if (results.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                No results for &ldquo;${escapeHtml(query)}&rdquo;
            </div>`;
        return;
    }
    // ... existing render logic ...
}
```

Add a minimal CSS rule if the `.empty-state` class does not already exist. Check `static/css/` for existing empty-state styles before adding new ones:

```bash
grep -rn "empty-state" static/css/
```

If not found, add to the appropriate CSS file:

```css
.empty-state {
    padding: var(--nbe-spacing-md, 16px);
    color: var(--nbe-text-secondary, #666);
    font-style: italic;
    text-align: center;
}
```

**Step 3:** Fix 060 — match highlighting. Write (or locate) a helper that wraps the matched substring in `<mark>`:

```javascript
function highlightMatch(text, query) {
    if (!query) return escapeHtml(text);
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return escapeHtml(text);
    return (
        escapeHtml(text.slice(0, idx)) +
        '<mark>' + escapeHtml(text.slice(idx, idx + query.length)) + '</mark>' +
        escapeHtml(text.slice(idx + query.length))
    );
}
```

Call `highlightMatch(object.name, query)` (or the relevant display field) when building each result item's inner HTML. Use `element.innerHTML = highlightMatch(...)` only on trusted/escaped output — the helper above escapes all non-match text.

**Step 4:** Ensure `escapeHtml` is available. If it isn't already defined, add:

```javascript
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
```

**Step 5:** Validate with Playwright.
- Search for a term with no matches → "No results for..." message appears. Take a screenshot to `.playwright-mcp/validate-059.png`.
- Search for `prod` (or a real substring) → matched text is highlighted in each result. Take a screenshot to `.playwright-mcp/validate-060.png`.

**Step 6:** Run ESLint:

```bash
npx eslint static/js/explorer/
```

Fix any issues.

**Step 7:** Commit:

```bash
git add static/js/explorer/ static/css/
git commit -m "$(cat <<'EOF'
fix(search): add empty-state message and match highlighting

Zero-result searches now show 'No results for "<query>"' instead of
a blank list. Matching substrings in search results are wrapped in
<mark> for visual emphasis.

Fixes bugs 059 and 060.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Fix 063 — "Create missing host" defaults to hosts.cfg

**Step 1:** Read the discovery file to understand where the dialog is triggered:

```bash
cat docs/test-discoveries/063-create-missing-host-defaults-to-services-cfg.md
```

**Step 2:** Find the "Create missing host" context menu action and the dialog initialization code:

```bash
grep -rn "create.*missing.*host\|missing.*host\|createMissingHost" static/js/explorer/
```

**Step 3:** Find where the target file is selected as the default. Look for logic that iterates available files or builds a `<select>` dropdown and picks a default option. The bug is that the first file in the list (alphabetically or by insertion order) is selected, which happens to be `services.cfg` before `hosts.cfg`.

**Step 4:** Replace the naive default with a heuristic that prefers a file appropriate for the object type being created:

```javascript
function getDefaultFileForType(objectType, allObjects, fileList) {
    // 1. Prefer files whose filename contains the object type
    const namedMatch = fileList.find(f =>
        f.toLowerCase().includes(objectType.toLowerCase())
    );
    if (namedMatch) return namedMatch;

    // 2. Prefer files that already contain objects of that type
    const withType = fileList.find(f =>
        allObjects.some(o => o.source_file === f && o.object_type === objectType)
    );
    if (withType) return withType;

    // 3. Fallback to first file
    return fileList[0];
}
```

Call this function with `objectType = 'host'` when building the "Create missing host" dialog.

**Step 5:** Apply the default to the file picker `<select>` element so `hosts.cfg` is pre-selected when the dialog opens.

**Step 6:** Validate with Playwright. Right-click an orphan service → "Create missing host" → confirm the dialog's file dropdown defaults to `hosts.cfg` (or another host-appropriate file). Take a screenshot to `.playwright-mcp/validate-063.png`.

**Step 7:** Run ESLint:

```bash
npx eslint static/js/explorer/
```

**Step 8:** Commit:

```bash
git add static/js/explorer/
git commit -m "$(cat <<'EOF'
fix(dialog): 'Create missing host' defaults to hosts.cfg not services.cfg

When creating a missing host from an orphan service context menu, the
file picker now defaults to a file whose name or contents match 'host'
rather than the first file alphabetically.

Fixes bug 063.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Final Playwright validation

**Step 1:** Run the full Playwright validation pass. Navigate to http://localhost:8080 and verify each fix in sequence:

- 059: Search for a non-existent term → "No results for..." message appears.
- 060: Search for a real substring → matched text is highlighted with `<mark>` in results.
- 061: Enable "services without a host" checkbox → orphan_service objects appear.
- 062: Enable two type checkboxes simultaneously → objects from both types are visible (union, not intersection).
- 063: Right-click orphan service → "Create missing host" → dialog defaults to `hosts.cfg`.

Take a final composite screenshot to `.playwright-mcp/validate-cluster-l-final.png`.

**Step 2:** Run the Python test suite to confirm no regressions:

```bash
python3 -m pytest tests/ -v
```

All tests must pass before this cluster is considered complete.
