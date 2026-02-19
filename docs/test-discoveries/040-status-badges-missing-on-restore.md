# 040 — Status Badges Not Rendered When Object Is Auto-Restored on Page Load

**Phase:** 17 — State Persistence  
**Severity:** Minor  
**Category:** UI / State Restoration

## Steps to Reproduce

1. Open `web-prod-01` host — observe red **"NOTIFICATION UNREACHABLE"** badge in breadcrumb header
2. Refresh the page (F5) — object is auto-restored as active tab
3. Observe the breadcrumb header

## Actual Behavior

The **"NOTIFICATION UNREACHABLE"** badge is absent after auto-restore.  
The breadcrumb shows only: `hosts.cfg > web-prod-01 [HOST]`

## Verification

The badge reappears correctly when:
- Clicking another object, then clicking back to web-prod-01
- Cross-page navigation and re-selecting the object manually

Same behavior on cross-page navigation: navigating to `/dependencies` and back produces the same missing badge.

## Expected Behavior

Status badges should be computed and displayed whenever an object is loaded into the editor — including during session state restoration.

## Screenshots

- Badge present (fresh select): `.playwright-mcp/phase17-01-web-prod-01-selected.png`
- Badge absent (post-refresh restore): `.playwright-mcp/phase17-03-after-refresh.png`
- Badge present (re-select after navigate away): `.playwright-mcp/phase17-04-web-prod-01-reselected.png`
- Badge absent (post cross-page nav restore): `.playwright-mcp/phase17-05-back-from-dependencies.png`
