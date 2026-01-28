# UX/UI Implementation Plan Generator

You are a frontend developer and UX specialist tasked with creating an implementation plan for the Nagios Bulk Editor application. Your goal is to analyze the requested UX improvements and produce a detailed, prioritized implementation plan.

## The Fixes to Implement

The following UX/UI improvements have been identified:

### 1. Backups Screen (Critical UX)
- Convert card list to a sortable table with columns: Date/Time (formatted), Type/Tag, User (avatar + name), Actions
- Fix button hierarchy: "Restore" should NOT be green (it's destructive). Make it secondary/gray or warning/orange. Only "Create Backup" should be green.

### 2. Issues/Validation Sidebar
- Reduce visual noise: Replace solid red backgrounds with white backgrounds + red left-border strip or small alert icon
- Add batch actions: "Fix All" or "Create All" button at top of groups (e.g., for 8 missing commands)

### 3. Object Editor
- Use monospace font for command_line input (Fira Code or Roboto Mono)
- Implement basic syntax highlighting for Nagios macros (e.g., $HOSTADDRESS$ in different color)
- Add "Copy" icon inside input field
- (Optional/Advanced) "Test Command" button for modal to run command against dummy host

### 4. Graph View
- Auto-populate graph when object selected in Object Explorer (show object + immediate dependencies)
- Improve legend visibility: make it a collapsible floater with high-contrast colors

### 5. Git & Audit Log
- Hide destructive actions ("Wipe Git Log", "Delete All Backups") in Settings/Advanced dropdown menu
- Color-code change types in Audit Log (Create, Delete, Modify) for quick scanning

### 6. Visual Polish
- Add breadcrumbs in header: `commands.cfg > notify-host-by-email` instead of just `notify-host-by-email COMMAND`
- Increase contrast on section headers (e.g., "ATTRIBUTES") - currently too light gray

## Your Task

Create a comprehensive implementation plan that:

1. **Explores the codebase** to identify all affected files (templates, CSS, JavaScript)
2. **Prioritizes fixes** using this matrix:
   - High Impact + Low Effort = Do First
   - High Impact + High Effort = Plan Carefully
   - Low Impact + Low Effort = Quick Wins
   - Low Impact + High Effort = Defer or Skip
3. **Groups related changes** that can be implemented together efficiently
4. **Provides specific implementation details** for each fix including:
   - Files to modify
   - CSS classes/variables to add or change
   - JavaScript functions to create or modify
   - Template changes needed

## Output Format

Structure your plan as follows:

### Phase 1: Quick Wins (Low Effort)
[List fixes that can be done quickly with specific file changes]

### Phase 2: High-Impact Changes
[List the most impactful fixes with detailed implementation steps]

### Phase 3: Advanced Features
[List features requiring more work, with scope assessment]

### File Change Summary
[Table mapping each fix to the files that need modification]

### Dependencies & Order
[Note any fixes that must be done before others]

## Constraints

- Focus on the existing codebase patterns (Flask templates, vanilla JS, CSS tokens)
- Do NOT suggest major framework changes or new dependencies unless absolutely necessary
- The "Test Command" feature may be deferred if it requires significant backend work
- Prioritize accessibility improvements (contrast, readability)
