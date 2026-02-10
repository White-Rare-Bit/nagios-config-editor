# NAGIOS BULK EDITOR - COMPREHENSIVE TESTING PROMPT

**CRITICAL: DO NOT MAKE ANY CODE CHANGES. THIS IS A READ-ONLY TESTING SESSION.**

## Mission

You are conducting a comprehensive end-to-end test of the Nagios Bulk Editor staging system using the Chrome extension for browser automation. Your goal is to systematically verify all functionality described in `test-plan.txt`.

## Prerequisites Before Starting

1. **Verify the app is running**: Navigate to `http://localhost:8080`
2. **Verify Chrome extension works**: Use `tabs_context_mcp` to get tab context
3. **Verify sample-config exists**: The `./sample-config` directory should contain Nagios config files

## Browser Automation Guidelines

Per CLAUDE.md instructions:
- Use `read_page` to get element refs from the accessibility tree
- Use `find` to locate elements by description
- Click/interact using `ref`, not coordinates
- NEVER take screenshots unless explicitly requested by the user

## Testing Process

### Phase Execution Pattern

For EACH phase (1-27) in `test-plan.txt`:

1. **Read the phase steps** from test-plan.txt
2. **Execute each step** using the Chrome extension
3. **Verify expected outcomes** match actual results
4. **Document any failures** immediately to `./<phase-number>-failure.txt`

### Failure Documentation Format

When a test step fails, create/append to a failure file:

```
File: ./<phase-number>-failure.txt
Example: ./phase-1-failure.txt

---
STEP: <step number and title>
EXPECTED: <what should have happened>
ACTUAL: <what actually happened>
EVIDENCE: <relevant details, error messages, observed behavior>
POSSIBLE CAUSE: <initial hypothesis of why it failed>
---
```

### Success Tracking

Keep mental track of passed steps. At the end, if all steps in a phase pass, no failure file is needed for that phase.

## Phase Quick Reference

| Phase | Focus Area | Steps |
|-------|------------|-------|
| 1 | Basic Object Operations | 1-5 |
| 2 | Folder Operations | 6-8 |
| 3 | Bulk Move Operations | 9-10 |
| 4 | Bulk Edit and Rename | 11-12 |
| 5 | Deletion Operations | 13-15 |
| 6 | Verify Staged Changes | 16 |
| 7 | Conflict Detection | 17 |
| 8 | Undo/Discard/Redo | 18-21 |
| 9 | Final Verification | 22-27 |
| 10 | Session and Lock Management | 28-29 |
| 11 | State Persistence | 30-31 |
| 12 | Compound Operations | 32-33 |
| 13 | Error Handling | 34-36 |
| 14 | Edge Cases | 37-39 |
| 15 | Filter and Search | 40-41 |
| 16 | Keyboard Shortcuts | 42-45 |
| 17 | Dependencies Interaction | 46-47 |
| 18 | Dialog Cancellation | 48-51 |
| 19 | Drag and Drop | 52-54 |
| 20 | Template Inheritance | 55-56 |
| 21 | Attribute Handling | 57-59 |
| 22 | Comments Preservation | 60-61 |
| 23 | Recovery Scenarios | 62-63 |
| 24 | Audit Trail | 64-65 |
| 25 | Performance and Stress | 66-67 |
| 26 | Suggestions Panel | 68 |
| 27 | Context Menu Behavior | 69-70 |

## Post-Testing Actions

### After All Phases Complete

1. **List all failure files** created during testing
2. **For each failure file**, invoke the `debugger` skill to analyze the root cause
3. **Compile all debug results** into `./test-debug-result.txt`

### Debug Result File Format

```
File: ./test-debug-result.txt

================================================================================
NAGIOS BULK EDITOR - TEST DEBUG RESULTS
================================================================================
Date: <date>
Tester: Claude (Chrome Extension Automation)

================================================================================
SUMMARY
================================================================================
Total Phases: 27
Phases with Failures: <count>
Total Step Failures: <count>

================================================================================
PHASE X: <Phase Name>
================================================================================
### Step N: <Step Title>

**Failure Description:**
<from failure file>

**Root Cause Analysis:**
<from debugger skill>

**Recommended Fix:**
<from debugger skill>

**Code Location:**
<file:line if applicable>

---
[Repeat for each failure]
```

## Important Reminders

1. **NO CODE CHANGES** - Only observe and document
2. **Be systematic** - Follow the test plan step by step
3. **Document thoroughly** - Better to over-document than miss details
4. **Use sample-config** - The `./sample-config` directory is your test environment
5. **Clean up after testing** - If possible, note objects created during testing for cleanup

## Starting the Test

Begin by:
1. Getting the browser tab context
2. Navigating to `http://localhost:8080`
3. Reading the current state of the Explorer view
4. Starting Phase 1, Step 1

## Resume Instructions

If context is lost mid-testing:
1. Read this file (`TESTING_PROMPT.md`) first
2. Check which `phase-*-failure.txt` files exist to see progress
3. Resume from the next untested phase
4. At completion, run debugger on all failure files and write to `test-debug-result.txt`

---

**BEGIN TESTING NOW**
