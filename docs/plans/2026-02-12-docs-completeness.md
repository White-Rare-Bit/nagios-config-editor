# Documentation Completeness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fill all documentation gaps in the /docs page by adding 7 new user guide pages and expanding the quick-start page.

**Architecture:** Each doc page is an HTML partial in `templates/docs/`, served by `/api/docs/<slug>`, and registered in `APP_DOCS_TREE` in `static/js/docs.js`. No backend changes needed — just create HTML files and update the tree.

**Tech Stack:** HTML (docs-prose pattern), vanilla JS (docs.js tree config)

---

### Task 1: Register new pages in APP_DOCS_TREE

**Files:**
- Modify: `static/js/docs.js:18-27` (User Guide items array)

**Step 1: Add 7 new slugs to the User Guide section**

Replace the User Guide items array (lines 18-27) with:

```javascript
        { section: 'User Guide', items: [
            { slug: 'explorer-navigation', label: 'Explorer & Navigation' },
            { slug: 'editing-objects', label: 'Editing Objects' },
            { slug: 'bulk-operations', label: 'Bulk Operations' },
            { slug: 'staging-system', label: 'Staging System' },
            { slug: 'file-folder-management', label: 'File & Folder Management' },
            { slug: 'git-integration', label: 'Git Integration' },
            { slug: 'validation', label: 'Validation' },
            { slug: 'backups', label: 'Backups' },
            { slug: 'search-filtering', label: 'Search & Filtering' },
            { slug: 'inheritance-viewer', label: 'Inheritance Viewer' },
            { slug: 'dependency-graph', label: 'Dependency Graph' },
            { slug: 'analysis-tools', label: 'Analysis Tools' },
            { slug: 'audit-log', label: 'Audit Log' },
            { slug: 'settings', label: 'Settings' },
            { slug: 'keyboard-shortcuts', label: 'Keyboard Shortcuts' }
        ]},
```

**Step 2: Verify the docs page loads without errors**

Open `http://localhost:8080/docs` and confirm:
- All 15 User Guide items appear in the sidebar tree
- Clicking a new slug shows "Page not found" (expected until we create the templates)
- Existing pages still load correctly

**Step 3: Commit**

```bash
git add static/js/docs.js
git commit -m "docs: register 7 new user guide pages in docs tree"
```

---

### Task 2: Create validation page

**Files:**
- Create: `templates/docs/validation.html`

**Step 1: Create the HTML template**

```html
<div class="docs-prose">
    <h2>Validation</h2>

    <p>
        The Validation page lets you run <code>nagios -v</code> directly from the browser
        to verify that your Nagios configuration is syntactically correct and internally
        consistent. This is the same preflight check that Nagios performs before starting
        or reloading.
    </p>

    <h3>Requirements</h3>

    <p>
        Validation requires two things to be configured in
        <a href="#app/settings">Settings</a>:
    </p>

    <ul>
        <li><strong>Nagios binary path</strong> &mdash; the path to the <code>nagios</code>
            executable (e.g. <code>/usr/local/nagios/bin/nagios</code>). You can also set
            this via the <code>NAGIOS_BIN</code> environment variable.</li>
        <li><strong>Nagios config file</strong> &mdash; the path to your main
            <code>nagios.cfg</code> file, which Nagios uses as the entry point for
            validation.</li>
    </ul>

    <p>
        When the page loads, it checks whether the Nagios binary is available. If not,
        a message explains what to configure. If the binary is found, the
        <strong>Run Validation</strong> button is enabled.
    </p>

    <h3>Running Validation</h3>

    <p>
        Click <strong>Run Validation</strong> to execute <code>nagios -v</code> against
        your configuration. The button shows a spinner while the check runs. Validation
        has a 60-second timeout &mdash; large configurations may take several seconds.
    </p>

    <p>
        When validation completes, the results panel shows:
    </p>

    <ul>
        <li>A <strong>status banner</strong> &mdash; green "Configuration is valid!" or
            red "Configuration has errors!"</li>
        <li><strong>Error count</strong> and <strong>warning count</strong> badges in the
            panel header.</li>
        <li>An <strong>Errors section</strong> listing each error with its source file,
            line number, and message.</li>
        <li>A <strong>Warnings section</strong> listing each warning message.</li>
        <li>The <strong>raw output</strong> from <code>nagios -v</code> in a scrollable
            monospace block for full context.</li>
    </ul>

    <h3>Typical Workflow</h3>

    <ol>
        <li>Make your edits in the <a href="#app/explorer-navigation">Object Explorer</a>.</li>
        <li>Apply staged changes via the <a href="#app/staging-system">Commit dialog</a>.</li>
        <li>Navigate to the Validation page and click <strong>Run Validation</strong>.</li>
        <li>If errors appear, return to the explorer to fix them, then re-apply and
            re-validate.</li>
        <li>Once valid, optionally commit to Git from the
            <a href="#app/git-integration">Git page</a>.</li>
    </ol>

    <div class="docs-note">
        Validation runs against the files on disk, not your staged changes. You must
        apply your changes before validating. If you have pending staged changes, the
        validation result reflects the previous on-disk state.
    </div>
</div>
```

**Step 2: Verify the page loads**

Open `http://localhost:8080/docs#app/validation` and confirm the content renders correctly with proper styling.

**Step 3: Commit**

```bash
git add templates/docs/validation.html
git commit -m "docs: add validation page to user guide"
```

---

### Task 3: Create backups page

**Files:**
- Create: `templates/docs/backups.html`

**Step 1: Create the HTML template**

```html
<div class="docs-prose">
    <h2>Backups</h2>

    <p>
        The Backups page manages snapshots of your Nagios configuration. Backups are
        zip archives of every <code>.cfg</code> file in your config directory. The app
        creates backups automatically before any apply or restore operation, and you can
        create manual backups at any time.
    </p>

    <h3>Backup List</h3>

    <p>
        The main table shows all existing backups with these columns:
    </p>

    <table>
        <thead>
            <tr>
                <th>Column</th>
                <th>Description</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Date/Time</strong></td>
                <td>When the backup was created. Click the column header to sort.</td>
            </tr>
            <tr>
                <td><strong>Description</strong></td>
                <td>A label describing the backup. Automatic backups are labeled with the
                    operation that triggered them (e.g. "pre_apply"). Manual backups show
                    whatever description you entered.</td>
            </tr>
            <tr>
                <td><strong>Files</strong></td>
                <td>The number of config files captured in the archive. Click the column
                    header to sort.</td>
            </tr>
            <tr>
                <td><strong>User</strong></td>
                <td>The name and email of the user who created the backup, based on the
                    identity configured in <a href="#app/settings">Settings</a>.</td>
            </tr>
            <tr>
                <td><strong>Actions</strong></td>
                <td>Restore and Delete buttons for each backup.</td>
            </tr>
        </tbody>
    </table>

    <p>
        The list is paginated at 25 backups per page. A badge in the page header shows
        the total backup count.
    </p>

    <h3>Creating a Manual Backup</h3>

    <p>
        Enter an optional description in the text field at the top of the page and click
        <strong>Create Backup</strong>. The backup is created immediately and appears in
        the list. Manual backups capture the current on-disk state of all config files.
    </p>

    <h3>Restoring from a Backup</h3>

    <p>
        Click <strong>Restore</strong> on any backup row. A confirmation dialog appears
        explaining what will happen. When you confirm:
    </p>

    <ol>
        <li>A <strong>safety backup</strong> is created automatically, capturing your
            current config files before the restore overwrites them.</li>
        <li>All config files are replaced with the contents of the selected backup.</li>
        <li>The app reloads the configuration from disk.</li>
    </ol>

    <div class="docs-warning">
        Restoring a backup replaces your entire configuration directory. Any changes made
        since the backup was created will be lost. The automatic safety backup lets you
        undo the restore if needed.
    </div>

    <h3>Deleting Backups</h3>

    <p>
        Click <strong>Delete</strong> on a backup row to remove a single backup. A
        confirmation dialog appears since deletions cannot be undone.
    </p>

    <p>
        The <strong>Delete All Backups</strong> button in the danger zone at the bottom
        removes every backup in a single operation. Use this to reclaim disk space when
        you no longer need historical snapshots.
    </p>

    <h3>Automatic Backups</h3>

    <p>
        The app creates backups automatically in these situations:
    </p>

    <ul>
        <li><strong>Before apply</strong> &mdash; when you apply staged changes from the
            commit dialog, a backup is created first.</li>
        <li><strong>Before restore</strong> &mdash; when you restore from a backup, a
            safety backup is created of the current state.</li>
    </ul>

    <p>
        Automatic backups are labeled with the operation name (e.g. "pre_apply",
        "pre_restore") so you can identify them in the list.
    </p>

    <h3>Backup Storage</h3>

    <p>
        Backups are stored as zip files in the backup directory configured in
        <a href="#app/settings">Settings</a>. By default this is a <code>backups/</code>
        subdirectory inside your Nagios config path. Each backup file is named with a
        timestamp for easy identification.
    </p>
</div>
```

**Step 2: Verify the page loads**

Open `http://localhost:8080/docs#app/backups` and confirm the content renders correctly.

**Step 3: Commit**

```bash
git add templates/docs/backups.html
git commit -m "docs: add backups page to user guide"
```

---

### Task 4: Create audit log page

**Files:**
- Create: `templates/docs/audit-log.html`

**Step 1: Create the HTML template**

```html
<div class="docs-prose">
    <h2>Audit Log</h2>

    <p>
        The Audit Log page shows a chronological record of every action performed in
        the application. Each entry captures the operation type, affected objects, the
        user who made the change, and a timestamp.
    </p>

    <h3>Viewing Entries</h3>

    <p>
        Entries are displayed newest-first. Each entry shows:
    </p>

    <ul>
        <li>A <strong>timestamp</strong> for when the action occurred.</li>
        <li>The <strong>user</strong> name and email (from the identity configured in
            <a href="#app/settings">Settings</a>).</li>
        <li><strong>Badges</strong> summarizing what changed &mdash; object creations,
            attribute edits, moves, deletions, file/folder operations, and any errors
            that occurred.</li>
        <li>For git and backup operations, a <strong>labeled badge</strong> describing
            the action (e.g. "git commit", "backup created", "backup restored").</li>
    </ul>

    <h3>Filtering</h3>

    <p>
        Filter chips at the top of the page let you narrow the log to a specific
        operation type:
    </p>

    <table>
        <thead>
            <tr>
                <th>Filter</th>
                <th>Shows</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>All</strong></td>
                <td>Every entry (default).</td>
            </tr>
            <tr>
                <td><strong>Creates</strong></td>
                <td>Entries that include object, file, or folder creations.</td>
            </tr>
            <tr>
                <td><strong>Attributes</strong></td>
                <td>Entries that include attribute edits on existing objects.</td>
            </tr>
            <tr>
                <td><strong>Moves</strong></td>
                <td>Entries that include object, file, or folder relocations.</td>
            </tr>
            <tr>
                <td><strong>Deletes</strong></td>
                <td>Entries that include deletions of any kind.</td>
            </tr>
            <tr>
                <td><strong>Git</strong></td>
                <td>Git operations: commits, discards, history clears, initializations,
                    and restores to previous commits.</td>
            </tr>
            <tr>
                <td><strong>Backups</strong></td>
                <td>Backup operations: created, restored, and deleted.</td>
            </tr>
        </tbody>
    </table>

    <p>
        Only one filter is active at a time. Selecting a new filter replaces the
        previous one. The entry count at the top updates to reflect the filtered result.
    </p>

    <h3>Searching</h3>

    <p>
        The search box performs a full-text search across all entry fields: timestamps,
        usernames, emails, action types, object names, file paths, git commit hashes,
        commit messages, and backup names. The search is case-insensitive and filters
        in real time as you type.
    </p>

    <p>
        Search and filter chips work together &mdash; you can search within a filtered
        view.
    </p>

    <h3>Archives</h3>

    <p>
        The sidebar shows archived audit logs. When the active log exceeds 1000 entries,
        older entries are automatically moved to a timestamped archive file. Click any
        archive in the sidebar to load and view its entries. The file size is shown next
        to each archive name.
    </p>

    <h3>Clearing the Log</h3>

    <div class="docs-warning">
        The <strong>Clear Log</strong> button at the bottom of the page permanently
        deletes all entries in the current log. This cannot be undone. Archived logs
        are not affected.
    </div>
</div>
```

**Step 2: Verify the page loads**

Open `http://localhost:8080/docs#app/audit-log` and confirm the content renders correctly.

**Step 3: Commit**

```bash
git add templates/docs/audit-log.html
git commit -m "docs: add audit log page to user guide"
```

---

### Task 5: Create settings page

**Files:**
- Create: `templates/docs/settings.html`

**Step 1: Create the HTML template**

```html
<div class="docs-prose">
    <h2>Settings</h2>

    <p>
        The Settings page lets you configure application paths, logging, and your
        personal identity. It is accessible from the navbar at the top-right of
        every page.
    </p>

    <h3>Server Settings</h3>

    <p>
        The Server Settings tab configures where the app reads Nagios configuration
        and how it logs operations. Changes here are saved to
        <code>config/settings.json</code> on the server.
    </p>

    <table>
        <thead>
            <tr>
                <th>Setting</th>
                <th>Description</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Nagios Config Path</strong></td>
                <td>The directory containing your <code>.cfg</code> files. Changing this
                    reloads all objects from the new path.</td>
            </tr>
            <tr>
                <td><strong>Backup Path</strong></td>
                <td>Where backup zip files are stored. Defaults to a <code>backups/</code>
                    subdirectory inside the config path.</td>
            </tr>
            <tr>
                <td><strong>Nagios Binary</strong></td>
                <td>Path to the <code>nagios</code> executable, used by the
                    <a href="#app/validation">Validation</a> page. Can also be set via the
                    <code>NAGIOS_BIN</code> environment variable.</td>
            </tr>
            <tr>
                <td><strong>Nagios Config File</strong></td>
                <td>Path to your main <code>nagios.cfg</code> file, used as the entry
                    point for <code>nagios -v</code> validation.</td>
            </tr>
        </tbody>
    </table>

    <p>
        Each path field has a <strong>Browse</strong> button that opens a filesystem
        browser. Navigate directories or type a path directly in the browser's path
        bar. Path inputs are validated against traversal attacks and invalid characters
        before saving.
    </p>

    <h4>Logging</h4>

    <p>
        The logging section controls operation logging &mdash; structured JSON logs
        of backend operations for debugging and auditing.
    </p>

    <table>
        <thead>
            <tr>
                <th>Setting</th>
                <th>Description</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Logging Enabled</strong></td>
                <td>Toggle operation logging on or off.</td>
            </tr>
            <tr>
                <td><strong>Log Level</strong></td>
                <td>Minimum severity to log: DEBUG, INFO, WARNING, or ERROR.</td>
            </tr>
            <tr>
                <td><strong>Max File Size</strong></td>
                <td>Maximum log file size in MB (1&ndash;100) before rotation.</td>
            </tr>
            <tr>
                <td><strong>Max Backup Files</strong></td>
                <td>Number of rotated log files to retain (1&ndash;20).</td>
            </tr>
        </tbody>
    </table>

    <p>
        A <strong>Download Log</strong> button lets you download the current operation
        log file for offline review.
    </p>

    <h4>Current Status</h4>

    <p>
        The status panel on the right shows the currently loaded config path, total
        object count, and number of config files. This updates after saving new
        settings.
    </p>

    <h3>Your Identity</h3>

    <p>
        The Identity tab configures your name and email address. These are used for:
    </p>

    <ul>
        <li><strong>Git commits</strong> &mdash; your name and email appear as the
            commit author.</li>
        <li><strong>Audit log entries</strong> &mdash; your identity is recorded with
            each action.</li>
        <li><strong>Backup metadata</strong> &mdash; backups are tagged with who
            created them.</li>
    </ul>

    <p>
        Identity is stored in your browser's local storage, not on the server. Each
        user sets their own identity independently. A badge next to the Settings
        link in the navbar shows whether your identity is configured.
    </p>

    <div class="docs-note">
        If your identity is not set, the app prompts you to configure it the first
        time you try to commit changes via Git. You can also set it proactively from
        the Settings page at any time.
    </div>

    <h3>Lock Behavior</h3>

    <p>
        Server settings cannot be saved while another user has pending staged changes.
        This prevents config path changes from conflicting with in-progress edits. If
        a lock is active, the save button is disabled and a message indicates who holds
        the lock.
    </p>
</div>
```

**Step 2: Verify the page loads**

Open `http://localhost:8080/docs#app/settings` and confirm the content renders correctly.

**Step 3: Commit**

```bash
git add templates/docs/settings.html
git commit -m "docs: add settings page to user guide"
```

---

### Task 6: Create inheritance viewer page

**Files:**
- Create: `templates/docs/inheritance-viewer.html`

**Step 1: Create the HTML template**

```html
<div class="docs-prose">
    <h2>Inheritance Viewer</h2>

    <p>
        The Inheritance Viewer visualizes Nagios template inheritance chains. Select
        any object to see which templates it inherits from, what attributes each
        template contributes, and what the final resolved attribute set looks like
        after all inheritance is applied.
    </p>

    <h3>Selecting an Object</h3>

    <p>
        The left panel provides two controls for finding objects:
    </p>

    <ul>
        <li><strong>Object type dropdown</strong> &mdash; select the Nagios object type
            (host, service, contact, etc.) to populate the object list.</li>
        <li><strong>Search box</strong> &mdash; filters the object list by name as you
            type.</li>
    </ul>

    <p>
        The object list sorts templates first (marked with a yellow "template" badge),
        then regular objects alphabetically. Each list item shows the object name and,
        if it uses templates, a "uses:" label with the template names.
    </p>

    <h3>Inheritance Chain</h3>

    <p>
        When you click an object, the right panel shows its inheritance chain as a
        vertical tree. The selected object appears at the top, followed by its parent
        templates, their parents, and so on up to the root template.
    </p>

    <p>
        Each node in the chain shows:
    </p>

    <ul>
        <li>The object or template name (bold).</li>
        <li>A <strong>template badge</strong> for objects with <code>register 0</code>.</li>
        <li>Up to <strong>5 sample attributes</strong> with their values, plus a count
            of additional attributes if there are more.</li>
    </ul>

    <p>
        If a template referenced in the <code>use</code> directive does not exist, the
        chain shows an error indicator at that point.
    </p>

    <h3>Resolved Attributes</h3>

    <p>
        Below the chain, a table shows the <strong>final resolved attribute set</strong>
        after all inheritance is applied. This is what Nagios will actually use at
        runtime. The table has three columns:
    </p>

    <table>
        <thead>
            <tr>
                <th>Column</th>
                <th>Description</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Attribute</strong></td>
                <td>The directive name, sorted alphabetically.</td>
            </tr>
            <tr>
                <td><strong>Value</strong></td>
                <td>The resolved value that Nagios will use.</td>
            </tr>
            <tr>
                <td><strong>Source</strong></td>
                <td>Which object or template provides this value. Attributes defined
                    directly on the object show "self" (highlighted); inherited values
                    show the template name.</td>
            </tr>
        </tbody>
    </table>

    <div class="docs-note">
        Nagios inheritance uses a "first match wins" rule: if both a child and a parent
        template define the same attribute, the child's value takes precedence. The
        resolved attributes table reflects this behavior.
    </div>

    <h3>Use Cases</h3>

    <ul>
        <li><strong>Debugging inheritance issues</strong> &mdash; see exactly which
            template provides a specific value and whether the child overrides it.</li>
        <li><strong>Understanding template structure</strong> &mdash; visualize
            multi-level template chains before making changes.</li>
        <li><strong>Identifying missing templates</strong> &mdash; the chain flags
            templates that are referenced but do not exist.</li>
    </ul>
</div>
```

**Step 2: Verify the page loads**

Open `http://localhost:8080/docs#app/inheritance-viewer` and confirm the content renders correctly.

**Step 3: Commit**

```bash
git add templates/docs/inheritance-viewer.html
git commit -m "docs: add inheritance viewer page to user guide"
```

---

### Task 7: Create dependency graph page

**Files:**
- Create: `templates/docs/dependency-graph.html`

**Step 1: Create the HTML template**

```html
<div class="docs-prose">
    <h2>Dependency Graph</h2>

    <p>
        The Graph View page (accessible from the navbar as "Graph View") visualizes
        relationships between Nagios objects as an interactive node-and-edge diagram.
        It uses the Cytoscape.js library to render a zoomable, pannable graph where
        each node represents a Nagios object and each edge represents a reference
        between them.
    </p>

    <h3>Adding Nodes</h3>

    <p>
        The graph starts empty. Use the search box in the left sidebar to find an
        object by name, then click it to add it to the graph. You can add as many
        nodes as you like.
    </p>

    <h3>Quick Views</h3>

    <p>
        When you select a node, <strong>quick view buttons</strong> appear in the
        sidebar. These expand the graph to show related objects using a layout
        appropriate for the relationship type. The available views depend on the
        selected object type:
    </p>

    <table>
        <thead>
            <tr>
                <th>View</th>
                <th>Available For</th>
                <th>Shows</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Inheritance</strong></td>
                <td>All types</td>
                <td>Template chain &mdash; parent templates and objects that inherit
                    from the selected template.</td>
            </tr>
            <tr>
                <td><strong>Network</strong></td>
                <td>Hosts</td>
                <td>Host parent/child topology and bound services.</td>
            </tr>
            <tr>
                <td><strong>Services</strong></td>
                <td>Hosts</td>
                <td>All services monitoring this host.</td>
            </tr>
            <tr>
                <td><strong>Notifications</strong></td>
                <td>Hosts, services</td>
                <td>Notification routing to contacts and contact groups.</td>
            </tr>
            <tr>
                <td><strong>Members</strong></td>
                <td>Groups</td>
                <td>All members of the selected group.</td>
            </tr>
            <tr>
                <td><strong>Notified By</strong></td>
                <td>Contacts</td>
                <td>Objects that send notifications to this contact.</td>
            </tr>
            <tr>
                <td><strong>Used By</strong></td>
                <td>Commands, timeperiods</td>
                <td>All objects that reference this command or timeperiod.</td>
            </tr>
            <tr>
                <td><strong>Monitoring</strong></td>
                <td>Hosts, services</td>
                <td>Check commands and time periods assigned to this object.</td>
            </tr>
            <tr>
                <td><strong>Escalations</strong></td>
                <td>Hosts, services</td>
                <td>Escalation rules and their contacts.</td>
            </tr>
            <tr>
                <td><strong>Dependencies</strong></td>
                <td>Hosts, services</td>
                <td>Dependency rules (master/dependent relationships).</td>
            </tr>
            <tr>
                <td><strong>Full Graph</strong></td>
                <td>All types</td>
                <td>Every relationship involving the selected object.</td>
            </tr>
        </tbody>
    </table>

    <h3>Filtering</h3>

    <p>
        The <strong>Custom Filters</strong> section in the sidebar offers two ways
        to control what the graph displays:
    </p>

    <ul>
        <li><strong>Object type checkboxes</strong> &mdash; show or hide nodes by type
            (host, service, contact, command, etc.). Unchecking a type hides those
            nodes and their edges.</li>
        <li><strong>Edge category checkboxes</strong> &mdash; show or hide edges by
            relationship category:
            <ul>
                <li><em>Dependencies</em> &mdash; host parents, host/service dependencies</li>
                <li><em>Templates</em> &mdash; inheritance via <code>use</code></li>
                <li><em>Groups</em> &mdash; group membership</li>
                <li><em>Contacts</em> &mdash; notification routing</li>
                <li><em>Commands</em> &mdash; check commands, event handlers</li>
                <li><em>Schedules</em> &mdash; time periods, escalation periods</li>
            </ul>
        </li>
    </ul>

    <h3>Layout Options</h3>

    <p>
        The layout dropdown controls how nodes are arranged:
    </p>

    <ul>
        <li><strong>Force-Directed</strong> &mdash; nodes repel each other and edges
            act as springs. Good for exploring general relationships.</li>
        <li><strong>Hierarchical (Top-Bottom)</strong> &mdash; edges flow top to bottom.
            Good for inheritance chains and network topology.</li>
        <li><strong>Hierarchical (Left-Right)</strong> &mdash; edges flow left to right.
            Good for notification routing and escalation paths.</li>
    </ul>

    <p>
        Quick views automatically select the layout that best fits the relationship
        type.
    </p>

    <h3>Graph Interaction</h3>

    <ul>
        <li><strong>Pan</strong> &mdash; click and drag the canvas background.</li>
        <li><strong>Zoom</strong> &mdash; scroll wheel or pinch gesture.</li>
        <li><strong>Select</strong> &mdash; click a node. Shift+click for multi-select.
            Shift+drag for box selection.</li>
        <li><strong>Delete</strong> &mdash; press Delete or Backspace to remove selected
            nodes.</li>
        <li><strong>Fit to View</strong> &mdash; button in the sidebar to auto-zoom
            so all nodes are visible.</li>
        <li><strong>Toggle Edge Labels</strong> &mdash; show or hide relationship labels
            on edges.</li>
    </ul>

    <h4>Context Menu</h4>

    <p>
        Right-click any node to access:
    </p>

    <ul>
        <li><strong>Expand connections</strong> &mdash; add all directly connected
            objects to the graph.</li>
        <li><strong>Show only connections</strong> &mdash; isolate this node and its
            immediate connections, removing everything else.</li>
        <li><strong>Center on node</strong> &mdash; pan and zoom to this node.</li>
        <li><strong>Set as layout center</strong> &mdash; use this node as the root
            for hierarchical layouts.</li>
        <li><strong>Remove from graph</strong> &mdash; remove just this node.</li>
        <li><strong>Remove disconnected</strong> &mdash; remove all nodes that have
            no edges.</li>
        <li><strong>Open in Explorer</strong> &mdash; navigate to this object in the
            <a href="#app/explorer-navigation">Object Explorer</a>.</li>
    </ul>

    <h3>Node Appearance</h3>

    <p>
        Each object type has a distinct color and icon. A collapsible legend overlay
        in the bottom-right corner of the graph shows all type colors. Templates are
        drawn with a dashed border. Objects that are referenced but do not exist in
        your configuration appear with a red indicator.
    </p>

    <h3>State Persistence</h3>

    <p>
        The graph state &mdash; nodes, edges, layout, and filter settings &mdash; is
        saved to your browser's local storage. When you return to the Graph View page,
        it restores your previous graph. Use the <strong>Clear</strong> button in the
        nodes list to start fresh.
    </p>

    <div class="docs-note">
        You can link directly to the graph with a specific object pre-loaded using the
        URL parameter <code>?node=type:name&amp;expand=true</code>. For example,
        <code>/dependencies?node=host:web-server&amp;expand=true</code> opens the graph
        with that host and its connections expanded.
    </div>
</div>
```

**Step 2: Verify the page loads**

Open `http://localhost:8080/docs#app/dependency-graph` and confirm the content renders correctly.

**Step 3: Commit**

```bash
git add templates/docs/dependency-graph.html
git commit -m "docs: add dependency graph page to user guide"
```

---

### Task 8: Create analysis tools page

**Files:**
- Create: `templates/docs/analysis-tools.html`

**Step 1: Create the HTML template**

```html
<div class="docs-prose">
    <h2>Analysis Tools</h2>

    <p>
        Nagios Bulk Editor includes several analysis features that help you understand
        and improve your configuration. These tools detect common issues, suggest
        organizational improvements, and trace notification escalation paths.
    </p>

    <h3>Health Check</h3>

    <p>
        The health check scans your configuration for common problems. It is accessible
        from the Object Explorer's right panel. Issues found include:
    </p>

    <ul>
        <li><strong>Missing required fields</strong> &mdash; objects that lack mandatory
            directives (e.g. a host without <code>host_name</code>).</li>
        <li><strong>Invalid references</strong> &mdash; attributes that point to objects
            that do not exist (e.g. a service with a <code>check_command</code> that
            references an undefined command).</li>
        <li><strong>Circular template dependencies</strong> &mdash; inheritance chains
            that loop back on themselves.</li>
        <li><strong>Unused templates</strong> &mdash; templates (<code>register 0</code>
            objects) that no other object inherits from.</li>
        <li><strong>Duplicate names</strong> &mdash; multiple objects of the same type
            with the same name.</li>
    </ul>

    <p>
        Objects with issues are flagged with badges in the explorer tree. The "Issues"
        filter checkbox in the left pane lets you view only objects with problems.
    </p>

    <h3>Orphan Detection</h3>

    <p>
        Orphan objects are those that no other object references. These are cleanup
        candidates &mdash; for example, a command that no service uses, or a contact
        group that no notification rule references.
    </p>

    <p>
        Use the <strong>Orphans</strong> filter checkbox in the
        <a href="#app/explorer-navigation">Object Explorer</a> left pane to show only
        orphan objects. Combine it with the search box to narrow results by type
        (e.g. type "command" with the Orphans filter to find unused commands).
    </p>

    <h3>Object References</h3>

    <p>
        The Impact &amp; Relationships section in the
        <a href="#app/editing-objects">object editor</a> shows every relationship
        involving the selected object. This includes:
    </p>

    <ul>
        <li><strong>Outgoing references</strong> &mdash; objects that this object
            points to (e.g. a service's check command, host, or contact groups).</li>
        <li><strong>Incoming references</strong> &mdash; objects that point to this
            object (e.g. services that monitor a host, or objects that inherit from
            a template).</li>
        <li><strong>Group membership</strong> &mdash; groups this object belongs to
            and members of this object (for group types).</li>
        <li><strong>Dependency rules</strong> &mdash; host or service dependency
            relationships where this object acts as master or dependent.</li>
        <li><strong>Escalation rules</strong> &mdash; escalation definitions that
            apply to this object.</li>
        <li><strong>Template inheritance</strong> &mdash; the inheritance chain and
            which templates this object uses.</li>
        <li><strong>Transitive impact</strong> &mdash; for templates, shows how many
            objects would be affected by a change, including objects that inherit
            indirectly through intermediate templates.</li>
    </ul>

    <h3>Escalation Path Analysis</h3>

    <p>
        The escalation path traces the full notification chain for a host or service.
        It shows:
    </p>

    <ul>
        <li><strong>Base contacts</strong> &mdash; who gets notified initially, including
            contacts assigned directly and via contact groups. Each contact shows their
            notification commands and periods.</li>
        <li><strong>Escalation levels</strong> &mdash; subsequent notification tiers,
            sorted by the <code>first_notification</code> count. Each level shows the
            notification range, interval, escalation period, and the contacts who are
            notified at that level.</li>
    </ul>

    <p>
        This is useful for verifying that the right people are notified at the right
        time, especially in complex escalation setups.
    </p>

    <h3>Smart Grouping Suggestions</h3>

    <p>
        The smart grouping feature analyzes your hosts and suggests hostgroups you
        might want to create. Suggestions are based on patterns found in your
        configuration:
    </p>

    <table>
        <thead>
            <tr>
                <th>Pattern</th>
                <th>Description</th>
                <th>Example</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>IP subnet</strong></td>
                <td>Hosts in the same /24 subnet.</td>
                <td>3 hosts in 192.168.1.0/24 &rarr; suggest "subnet-192-168-1"</td>
            </tr>
            <tr>
                <td><strong>Hostname prefix</strong></td>
                <td>Hosts whose names share a common prefix.</td>
                <td>web-01, web-02, web-03 &rarr; suggest "web-servers"</td>
            </tr>
            <tr>
                <td><strong>Hostname suffix</strong></td>
                <td>Hosts whose names share a common suffix.</td>
                <td>db-prod, app-prod, cache-prod &rarr; suggest "prod-systems"</td>
            </tr>
            <tr>
                <td><strong>Check command</strong></td>
                <td>Hosts using the same check command.</td>
                <td>Hosts checked by check-ssh &rarr; suggest "ssh-checked"</td>
            </tr>
            <tr>
                <td><strong>Network parent</strong></td>
                <td>Hosts behind the same parent host.</td>
                <td>Hosts parented to "core-switch" &rarr; suggest "behind-core-switch"</td>
            </tr>
            <tr>
                <td><strong>Ungrouped</strong></td>
                <td>Hosts not in any hostgroup.</td>
                <td>Orphan hosts &rarr; suggest "ungrouped-hosts"</td>
            </tr>
        </tbody>
    </table>

    <p>
        Each suggestion includes a confidence score based on the number of matching
        hosts and the pattern type. You can create a new hostgroup directly from a
        suggestion or add the suggested hosts to an existing group.
    </p>

    <h3>Template Issues</h3>

    <p>
        The template issues analyzer checks for problems in your template hierarchy:
    </p>

    <ul>
        <li><strong>Invalid <code>use</code> references</strong> &mdash; objects
            referencing templates that do not exist.</li>
        <li><strong>Circular dependencies</strong> &mdash; template chains that
            create loops (e.g. template A uses template B, which uses template A).</li>
        <li><strong>Unused templates</strong> &mdash; templates that no object
            inherits from, which may be candidates for cleanup.</li>
    </ul>

    <p>
        These issues are surfaced in the
        <a href="#app/inheritance-viewer">Inheritance Viewer</a> and as badges in the
        explorer tree.
    </p>
</div>
```

**Step 2: Verify the page loads**

Open `http://localhost:8080/docs#app/analysis-tools` and confirm the content renders correctly.

**Step 3: Commit**

```bash
git add templates/docs/analysis-tools.html
git commit -m "docs: add analysis tools page to user guide"
```

---

### Task 9: Expand quick-start page

**Files:**
- Modify: `templates/docs/quick-start.html`

**Step 1: Add references to newly-documented features**

The current quick-start has 6 steps. Add a "What's Next" section after the final `<hr>` and warning div. Replace the closing `</div>` section (after the `<hr>`) with:

```html
    <hr>

    <div class="docs-warning">
        Until you click Apply, no changes are written to disk. You can undo individual changes
        or clear all staging at any time.
    </div>

    <h3>What Else Can You Do?</h3>

    <p>
        Beyond the basic workflow above, Nagios Bulk Editor offers several tools for
        working with your configuration:
    </p>

    <ul>
        <li><a href="#app/bulk-operations">Bulk Operations</a> &mdash; select multiple
            objects and edit, move, clone, rename, or delete them in one step.</li>
        <li><a href="#app/dependency-graph">Graph View</a> &mdash; visualize
            relationships between objects as an interactive diagram.</li>
        <li><a href="#app/inheritance-viewer">Inheritance Viewer</a> &mdash; trace
            template inheritance chains and see resolved attribute values.</li>
        <li><a href="#app/analysis-tools">Analysis Tools</a> &mdash; detect
            configuration issues, find orphan objects, and get smart grouping
            suggestions.</li>
        <li><a href="#app/backups">Backups</a> &mdash; create manual snapshots and
            restore from any previous backup.</li>
        <li><a href="#app/settings">Settings</a> &mdash; configure paths, logging,
            and your identity.</li>
    </ul>
</div>
```

**Step 2: Verify the page loads**

Open `http://localhost:8080/docs#app/quick-start` and confirm the "What Else Can You Do?" section appears at the bottom with working links.

**Step 3: Commit**

```bash
git add templates/docs/quick-start.html
git commit -m "docs: expand quick-start with links to new guide pages"
```

---

### Task 10: Final verification

**Step 1: Verify all 25 doc pages load**

Open `http://localhost:8080/docs` and click through every item in the sidebar tree:

**Getting Started (3 pages):**
- Overview
- Installation & Setup
- Quick Start Guide (verify new "What Else Can You Do?" section)

**User Guide (15 pages):**
- Explorer & Navigation
- Editing Objects
- Bulk Operations
- Staging System
- File & Folder Management
- Git Integration
- Validation (NEW)
- Backups (NEW)
- Search & Filtering
- Inheritance Viewer (NEW)
- Dependency Graph (NEW)
- Analysis Tools (NEW)
- Audit Log (NEW)
- Settings (NEW)
- Keyboard Shortcuts

**Developer Guide (7 pages):**
- Architecture Overview
- Backend Services
- API Reference
- Frontend Architecture
- Data Flow & Staging Internals
- Configuration System
- Contributing

For each new page, verify:
- Content renders inside the `.docs-prose` container
- Tables are styled correctly
- Internal links (e.g. `#app/settings`) navigate to the correct page
- `docs-note` and `docs-warning` callouts render with proper styling

**Step 2: Verify deep links work**

Test these URLs directly in the browser:
- `http://localhost:8080/docs#app/validation`
- `http://localhost:8080/docs#app/backups`
- `http://localhost:8080/docs#app/audit-log`
- `http://localhost:8080/docs#app/settings`
- `http://localhost:8080/docs#app/inheritance-viewer`
- `http://localhost:8080/docs#app/dependency-graph`
- `http://localhost:8080/docs#app/analysis-tools`

**Step 3: Verify sidebar search finds new pages**

Type each of these into the docs sidebar search box and confirm the matching page appears:
- "validation" → Validation
- "backup" → Backups
- "audit" → Audit Log
- "settings" → Settings
- "inheritance" → Inheritance Viewer
- "graph" → Dependency Graph
- "analysis" → Analysis Tools

**Step 4: Commit (if any fixes were needed)**

```bash
git add -A
git commit -m "docs: fix any issues found during verification"
```
