# BUG 011 — Multiple Identical Warning Toasts Stack Simultaneously

**Phase:** 4 — Create Objects (Compound Creation)
**Severity:** Minor
**Category:** Notification UX

## Description

When validation warnings fire (e.g., "Warning: 'service_description' is required"), multiple identical toasts appear stacked on top of each other simultaneously rather than deduplicating or replacing the previous instance.

## Steps to Reproduce

1. Create a new service form
2. Trigger required-field validation multiple times in quick succession (e.g., by rapidly clicking between fields without filling in `service_description`)

## Expected Behavior

At most one toast per message should be visible. If the same warning fires again while a toast is already shown, it should reset the timer rather than create a second identical toast.

## Actual Behavior

Two (or more) identical "Warning: 'service_description' is required" toasts appear stacked, creating visual noise.

## Impact

Low — cosmetic/UX issue. Does not affect functionality, but makes the interface feel noisy and unpolished.
