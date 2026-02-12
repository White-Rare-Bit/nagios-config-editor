# Nagios 4 Spec Compliance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the application fully compliant with three Nagios 4 specs (object definitions, object inheritance, object tricks) — including the dependency graph quick views and health checks — and eliminate false positives.

**Architecture:** Changes span the domain model (`nagios_model.py`), health checks (`routes/health_checks.py`), graph backend (`routes/analysis.py`), graph frontend config (`static/js/dependencies-config.js`), editor frontend (`constants.js`, `object-editor.js`), and tests. The inheritance module is already fully compliant — no changes needed there.

**Tech Stack:** Python/Flask backend, vanilla JS frontend, pytest

**Specs:**
- [Object Definitions](https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/objectdefinitions.html)
- [Object Inheritance](https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/objectinheritance.html)
- [Object Tricks](https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/objecttricks.html)

---

## Summary of Issues Found

### A. VALID_ATTRIBUTES gaps (nagios_model.py)

| Object Type | Missing Attribute | Spec Reference |
|---|---|---|
| host | `importance` | Integer, notification filtering |
| host | `obsess` | Alias for `obsess_over_host` |
| service | `importance` | Integer, notification filtering |
| service | `obsess` | Alias for `obsess_over_service` |
| service | `parents` | Comma-delimited service descriptions (Nagios 4) |
| contact | `address1`..`address6` | Individual contact address fields (currently `addressx` placeholder) |
| servicedependency | `servicegroup_name` | Comma-delimited servicegroup names |
| servicedependency | `dependent_servicegroup_name` | Comma-delimited servicegroup names |

### B. REFERENCE_FIELDS gaps (nagios_model.py)

| Field | Missing Entry | Target Type |
|---|---|---|
| `parents` | Currently hardcoded to `"host"` — but service `parents` references services | Change to `None` (context-dependent) |
| `dependent_servicegroup_name` | Not in REFERENCE_FIELDS at all | `"servicegroup"` |

### C. REQUIRED_FIELDS over-strictness (nagios_model.py)

Per the Nagios spec, required fields are minimal. Everything else can be inherited or has defaults.

| Object Type | Current | Spec Says |
|---|---|---|
| host | `host_name`, `address`, `max_check_attempts`, `(contacts\|contact_groups)` | Only `host_name`. `address` defaults to host_name. |
| service | `service_description`, `(host_name\|hostgroup_name)`, `check_command`, `max_check_attempts`, `(contacts\|contact_groups)` | `service_description`, `(host_name\|hostgroup_name)`, `check_command` |
| contact | `contact_name`, complex notification OR-tuples | Only `contact_name` |
| hostdependency | `(host_name\|hostgroup_name)`, `(dependent_host_name\|dependent_hostgroup_name)` | No required fields (failure criteria needed but that's a different check) |
| servicedependency | `service_description`, `(host_name\|hostgroup_name)`, `dependent_service_description`, `(dependent_host_name\|dependent_hostgroup_name)` | No required fields per tricks spec (same-host trick allows empty dependent_host/hostgroup) |

### D. NOTIFICATION_OPTIONS gaps (nagios_model.py)

| Gap | Detail |
|---|---|
| Missing `host_stalking_options` | Values: o, d, u, N (N = log on notification, Nagios 4) |
| Missing `service_stalking_options` | Values: o, w, u, c, N |
| Missing `host_flap_detection_options` | Values: o, d, u |
| Missing `service_flap_detection_options` | Values: o, w, u, c |
| Missing `host_escalation_options` | Values: d, u, r (subset of notification_options) |
| Missing `service_escalation_options` | Values: w, u, c, r (subset of notification_options) |
| `flap_detection_options` not in `notification_option_attrs` | Frontend doesn't offer value suggestions |

### E. Health check false positives (routes/health_checks.py)

| Check | Issue | Lines |
|---|---|---|
| `check_long_host_lists` | Counts `!HOST` exclusions in host count | 1371 |
| `check_services_on_empty_hostgroups` | Uses manual `lstrip("+!")` instead of `strip_prefix()` | 1539, 1565 |
| `check_missing_parents` | Doesn't strip `+` prefix from additive parents | 200 |
| `check_host_reachability` | Doesn't strip `+` prefix from parent names | 1790 |
| `_build_host_to_hostgroups` | Uses `lstrip("+")` — doesn't strip `!` exclusions | 616 |
| `_build_hostgroup_to_hosts` | Doesn't strip `+`/`!` from member names at all | 630 |
| `_expand_contacts` | Uses manual `.lstrip("+!")` instead of `strip_prefix()` | 859, 863 |

### F. Frontend editor issues

| File | Issue | Lines |
|---|---|---|
| `object-editor.js` | `escalation_options` maps to full notification options — spec says d,u,r for host / w,u,c,r for service | 314-319 |
| `object-editor.js` | `stalking_options` values hardcoded, missing N option | 320-326 |
| `object-editor.js` | No `flap_detection_options` handling at all | after 326 |
| `constants.js` | Missing stalking/flap detection/escalation option constants | 52-57 |

### G. Dependency graph / quick view issues

| Component | Issue | Location |
|---|---|---|
| `_RELATIONSHIP_FIELDS` | Missing `contactgroups` → `"contactgroup"` — contact→contactgroup membership not graphed | analysis.py:36-71 |
| `_RELATIONSHIP_FIELDS` | Missing `dependent_servicegroup_name` → `"servicegroup"` — new servicedependency field | analysis.py:36-71 |
| `_RELATIONSHIP_FIELDS` | `parents` always maps to `"host"` — wrong for service objects where it references services | analysis.py:60 |
| `_compute_target_node_id` | No special case for service `parents` (generates `host:` prefix instead of `service:`) | analysis.py:171-191 |
| `_build_parent_tree` | Doesn't strip `+`/`!` prefixes from parent names — `+hostA` won't resolve | analysis.py:1095 |
| `edgeCategories.contacts` | Missing `contactgroups` field — contact→contactgroup edges not shown | dependencies-config.js:73-81 |
| `edgeCategories.dependencies` | Missing `dependent_servicegroup_name` field | dependencies-config.js:29-39 |
| expansion rules | servicedependency network preset missing `servicegroup_name` and `dependent_servicegroup_name` | dependencies-config.js:477-495 |
| expansion rules | service network preset missing `parents` for service-to-service dependencies | dependencies-config.js |

---

## Task 1: Update VALID_ATTRIBUTES and REFERENCE_FIELDS

**Files:**
- Modify: `nagios_model.py:126-384`

**Step 1: Add missing host attributes**

In VALID_ATTRIBUTES `"host"` list (line 127-139), add `importance` after `parents` and `obsess` after `obsess_over_host`:

```python
"host": [
    "host_name", "alias", "display_name", "address", "parents", "importance",
    "hostgroups", "check_command", "initial_state", "max_check_attempts",
    "check_interval", "retry_interval", "active_checks_enabled",
    "passive_checks_enabled", "check_period", "obsess_over_host", "obsess",
    "check_freshness", "freshness_threshold",
    "event_handler", "event_handler_enabled", "low_flap_threshold",
    "high_flap_threshold", "flap_detection_enabled", "flap_detection_options",
    "process_perf_data", "retain_status_information", "retain_nonstatus_information",
    "contacts", "contact_groups", "notification_interval", "first_notification_delay",
    "notification_period", "notification_options", "notifications_enabled",
    "stalking_options", "notes", "notes_url", "action_url", "icon_image",
    "icon_image_alt", "vrml_image", "statusmap_image", "2d_coords", "3d_coords",
    "use", "name", "register",
],
```

**Step 2: Add missing service attributes**

In VALID_ATTRIBUTES `"service"` list (line 145-157), add `parents` after `display_name`, `importance` after `is_volatile`, and `obsess` after `obsess_over_service`:

```python
"service": [
    "host_name", "hostgroup_name", "service_description", "display_name",
    "parents", "servicegroups", "is_volatile", "importance", "check_command",
    "initial_state", "max_check_attempts", "check_interval", "retry_interval",
    "active_checks_enabled", "passive_checks_enabled", "check_period",
    "obsess_over_service", "obsess", "check_freshness", "freshness_threshold",
    "event_handler", "event_handler_enabled", "low_flap_threshold",
    "high_flap_threshold", "flap_detection_enabled", "flap_detection_options",
    "process_perf_data", "retain_status_information", "retain_nonstatus_information",
    "notification_interval", "first_notification_delay", "notification_period",
    "notification_options", "notifications_enabled", "contacts", "contact_groups",
    "stalking_options", "notes", "notes_url", "action_url", "icon_image",
    "icon_image_alt", "use", "name", "register",
],
```

**Step 3: Fix contact address fields**

In VALID_ATTRIBUTES `"contact"` list (line 163-172), replace `"addressx"` with individual fields:

```python
"contact": [
    "contact_name", "alias", "contactgroups", "minimum_importance",
    "host_notifications_enabled", "service_notifications_enabled",
    "host_notification_period", "service_notification_period",
    "host_notification_options", "service_notification_options",
    "host_notification_commands", "service_notification_commands",
    "email", "pager", "address1", "address2", "address3",
    "address4", "address5", "address6", "can_submit_commands",
    "retain_status_information", "retain_nonstatus_information",
    "use", "name", "register",
],
```

**Step 4: Add missing servicedependency attributes**

In VALID_ATTRIBUTES `"servicedependency"` list (line 184-188), add `servicegroup_name` and `dependent_servicegroup_name`:

```python
"servicedependency": [
    "dependent_host_name", "dependent_hostgroup_name", "dependent_service_description",
    "dependent_servicegroup_name", "host_name", "hostgroup_name",
    "service_description", "servicegroup_name", "inherits_parent",
    "execution_failure_criteria", "notification_failure_criteria",
    "dependency_period", "use", "name", "register",
],
```

**Step 5: Fix REFERENCE_FIELDS**

In REFERENCE_FIELDS (line 320-384):

Change `parents` from `"host"` to `None` (context-dependent — references hosts on host objects, services on service objects):

```python
"parents": None,
```

Add `dependent_servicegroup_name` entry after the servicegroup section:

```python
"dependent_servicegroup_name": "servicegroup",
```

**Step 6: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass (may need to fix `test_reference_fields_synchronized` if it exists)

**Step 7: Commit**

```
feat: add missing VALID_ATTRIBUTES and REFERENCE_FIELDS per Nagios 4 spec

Add importance and obsess alias for host/service, parents for service,
address1-address6 for contact, servicegroup fields for servicedependency.
Fix parents REFERENCE_FIELDS to be context-dependent (hosts on hosts,
services on services). Add dependent_servicegroup_name reference.
```

---

## Task 2: Update REQUIRED_FIELDS to match spec

**Files:**
- Modify: `nagios_model.py:34-69`
- Modify: `tests/test_health_check.py` (multiple tests)

**Step 1: Update REQUIRED_FIELDS**

Replace the current REQUIRED_FIELDS (lines 34-69) with spec-compliant values:

```python
REQUIRED_FIELDS: dict[str, list] = {
    "host": [
        "host_name",
    ],
    "hostgroup": ["hostgroup_name"],
    "service": [
        "service_description",
        ("host_name", "hostgroup_name"),
        "check_command",
    ],
    "servicegroup": ["servicegroup_name"],
    "contact": [
        "contact_name",
    ],
    "contactgroup": ["contactgroup_name"],
    "command": ["command_name", "command_line"],
    "timeperiod": ["timeperiod_name"],
    "hostdependency": [("host_name", "hostgroup_name")],
    "servicedependency": [
        "service_description",
        ("host_name", "hostgroup_name"),
        "dependent_service_description",
    ],
    "hostescalation": [("host_name", "hostgroup_name")],
    "serviceescalation": ["service_description", ("host_name", "hostgroup_name")],
}
```

Key changes:
- **host**: Remove `address` (defaults to host_name), `max_check_attempts`, `(contacts, contact_groups)`
- **service**: Remove `max_check_attempts`, `(contacts, contact_groups)`
- **contact**: Remove all notification OR-tuples (only `contact_name` required per spec)
- **hostdependency**: Remove `(dependent_host_name, dependent_hostgroup_name)` — "same host" trick allows both empty
- **servicedependency**: Remove `(dependent_host_name, dependent_hostgroup_name)` — same reason

**Step 2: Update test `test_required_fields_host_includes_address`**

In `tests/test_health_check.py`, rename and update the test at ~line 260:

```python
def test_required_fields_host_only_requires_host_name():
    """REQUIRED_FIELDS for host should only require host_name per Nagios spec."""
    host_fields = REQUIRED_FIELDS.get("host", [])
    flat = []
    for f in host_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert "host_name" in flat
    # Per spec: address defaults to host_name, others can be inherited
    assert "address" not in flat
    assert "max_check_attempts" not in flat
```

**Step 3: Update test `test_required_fields_contact_includes_notification_fields`**

In `tests/test_health_check.py`, rename and update the contact test at ~line 287:

```python
def test_required_fields_contact_only_requires_contact_name():
    """REQUIRED_FIELDS for contact should only require contact_name per Nagios spec."""
    contact_fields = REQUIRED_FIELDS.get("contact", [])
    flat = []
    for f in contact_fields:
        if isinstance(f, tuple):
            flat.extend(f)
        else:
            flat.append(f)
    assert "contact_name" in flat
    assert len(flat) == 1, f"Only contact_name should be required, got: {contact_fields}"
```

**Step 4: Update test `test_constants_returns_required_fields`**

In `tests/test_health_check.py`, update the constants endpoint test at ~line 1571:

```python
def test_constants_returns_required_fields(self, health_client):
    """Endpoint should return required_fields with OR conditions as lists."""
    resp = health_client.get("/api/constants")
    assert resp.status_code == 200
    data = resp.json

    assert "required_fields" in data
    rf = data["required_fields"]

    # host should only require host_name per spec
    assert "host_name" in rf["host"]
    assert "address" not in rf["host"]

    # service should have at least one OR condition (host_name|hostgroup_name)
    or_conditions = [r for r in rf["service"] if isinstance(r, list)]
    assert len(or_conditions) >= 1, \
        f"Expected at least one OR condition in service required_fields, got: {rf['service']}"
```

**Step 5: Update test `test_required_field_missing_despite_template`**

In `tests/test_health_check.py`, update the inheritance test at ~line 2106:

```python
def test_required_field_missing_despite_template(self, app_with_templates):
    """Host inheriting from empty template should only be flagged for truly missing required fields."""
    client = app_with_templates.test_client()
    resp = client.get("/api/health-check")
    assert resp.status_code == 200
    data = resp.get_json()

    missing_req = [
        i for i in data["issues"]
        if i["type"] == "missing_required_field" and i["object"] == "bad-host"
    ]
    # Per spec, only host_name is required; address defaults to host_name,
    # max_check_attempts and contacts can be inherited
    # bad-host has host_name defined, so no required field should be missing
    assert len(missing_req) == 0, \
        f"bad-host with host_name should have no missing required fields per spec, got: {missing_req}"
```

**Step 6: Run tests, fix any other failures**

Run: `python3 -m pytest tests/ -v`

**Step 7: Commit**

```
fix: align REQUIRED_FIELDS with Nagios 4 spec

Per spec: host only requires host_name (address defaults to it),
service requires description/host/check_command, contact only
requires contact_name. Dependencies allow empty dependent_host for
same-host trick.
```

---

## Task 3: Update NOTIFICATION_OPTIONS and notification_option_attrs

**Files:**
- Modify: `nagios_model.py:275-295`

**Step 1: Add all missing option value lists**

Replace the NOTIFICATION_OPTIONS dict with complete spec-compliant version:

```python
NOTIFICATION_OPTIONS: dict[str, list] = {
    "host_notification_options": [
        "d - Down", "u - Unreachable", "r - Recovery",
        "f - Flapping", "s - Scheduled Downtime", "n - None",
    ],
    "service_notification_options": [
        "w - Warning", "u - Unknown", "c - Critical", "r - Recovery",
        "f - Flapping", "s - Scheduled Downtime", "n - None",
    ],
    "host_failure_criteria": [
        "o - Up (OK)", "d - Down", "u - Unreachable", "p - Pending", "n - None",
    ],
    "service_failure_criteria": [
        "o - OK", "w - Warning", "u - Unknown", "c - Critical", "p - Pending", "n - None",
    ],
    "host_stalking_options": [
        "o - Up", "d - Down", "u - Unreachable", "N - Log on Notification",
    ],
    "service_stalking_options": [
        "o - OK", "w - Warning", "u - Unknown", "c - Critical", "N - Log on Notification",
    ],
    "host_flap_detection_options": [
        "o - Up", "d - Down", "u - Unreachable",
    ],
    "service_flap_detection_options": [
        "o - OK", "w - Warning", "u - Unknown", "c - Critical",
    ],
    "host_escalation_options": [
        "d - Down", "u - Unreachable", "r - Recovery",
    ],
    "service_escalation_options": [
        "w - Warning", "u - Unknown", "c - Critical", "r - Recovery",
    ],
    "notification_option_attrs": [
        "notification_options", "host_notification_options", "service_notification_options",
        "execution_failure_criteria", "notification_failure_criteria",
        "escalation_options", "stalking_options", "flap_detection_options",
    ],
}
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```
feat: add complete option value metadata per Nagios 4 spec

Add host/service stalking_options (including N for log-on-notification),
flap_detection_options, and escalation_options (correct subsets, not
full notification options). Add flap_detection_options to
notification_option_attrs.
```

---

## Task 4: Fix health check false positives for object tricks

**Files:**
- Modify: `routes/health_checks.py`

**Step 1: Fix `check_missing_parents` — strip `+` prefix (line 200)**

Change:
```python
parent = parent.strip()
if parent and parent not in hosts:
```
to:
```python
parent = strip_prefix(parent)
if parent and parent not in hosts:
```

**Step 2: Fix `check_long_host_lists` — exclude exclusions (line 1371)**

Change:
```python
host_list = [h.strip() for h in host_ref.split(",") if h.strip()]
```
to:
```python
host_list = [h.strip() for h in host_ref.split(",") if h.strip() and not h.strip().startswith("!")]
```

**Step 3: Fix `check_services_on_empty_hostgroups` — use `strip_prefix()` (lines 1539, 1565)**

At line 1539, change:
```python
hg = hg.strip().lstrip("+!")
```
to:
```python
hg = strip_prefix(hg)
```

At line 1565, same change:
```python
hg = hg.strip().lstrip("+!")
```
to:
```python
hg = strip_prefix(hg)
```

**Step 4: Fix `check_host_reachability` — strip `+` prefix (line 1790)**

Change:
```python
parent_list = [p.strip() for p in parents.split(",") if p.strip()]
```
to:
```python
parent_list = [strip_prefix(p) for p in parents.split(",") if strip_prefix(p)]
```

**Step 5: Fix `_build_host_to_hostgroups` — use `strip_prefix()` (line 616)**

Change:
```python
host_to_hg[hname] = {
    g.strip().lstrip("+").strip()
    for g in hgs.split(",") if g.strip()
}
```
to:
```python
host_to_hg[hname] = {
    strip_prefix(g)
    for g in hgs.split(",") if strip_prefix(g)
}
```

**Step 6: Fix `_build_hostgroup_to_hosts` — strip prefixes (line 630)**

Change:
```python
hg_to_hosts[gname] = {
    h.strip() for h in obj.attributes["members"].split(",") if h.strip()
}
```
to:
```python
hg_to_hosts[gname] = {
    strip_prefix(h) for h in obj.attributes["members"].split(",") if strip_prefix(h)
}
```

**Step 7: Fix `_expand_contacts` — use `strip_prefix()` (lines 859, 863)**

At line 859, change:
```python
c = c.strip().lstrip("+!")
```
to:
```python
c = strip_prefix(c)
```

At line 863, change:
```python
cg_name = cg_name.strip().lstrip("+!")
```
to:
```python
cg_name = strip_prefix(cg_name)
```

**Step 8: Run tests**

Run: `python3 -m pytest tests/ -v`
Expected: All pass

**Step 9: Commit**

```
fix: eliminate health check false positives for object tricks

Use strip_prefix() consistently in check_missing_parents,
check_host_reachability, _build_host_to_hostgroups,
_build_hostgroup_to_hosts, and _expand_contacts. Exclude ! exclusions
from check_long_host_lists count. Replace manual lstrip("+!") with
strip_prefix() in check_services_on_empty_hostgroups.
```

---

## Task 5: Fix dependency graph for spec compliance

**Files:**
- Modify: `routes/analysis.py:36-71, 171-191, 1094-1096`
- Modify: `static/js/dependencies-config.js:29-39, 73-81, 477-495`

### Part A: Backend — `_RELATIONSHIP_FIELDS` and graph building (analysis.py)

**Step 1: Add missing relationship fields**

In `_RELATIONSHIP_FIELDS` (line 36-71), add after the existing servicegroup entries:

```python
"dependent_servicegroup_name": "servicegroup",
```

Add in the contact section (after `contactgroup_members`):

```python
"contactgroups": "contactgroup",
```

**Step 2: Handle `parents` context-dependently in `_compute_target_node_id`**

Service `parents` references service descriptions (not hosts). Add a special case in `_compute_target_node_id` (line 171-191).

After the template/member handling (line 178), before the service_description special case (line 180), add:

```python
# parents: hosts reference hosts, services reference services
if field == "parents" and obj.object_type == "service":
    t_type = "service"
    svc_context = resolved_attrs.get("host_name", "")
    svc_context = ",".join([t.strip().lstrip("+").strip() for t in svc_context.split(",")
                            if not t.strip().startswith("!")])
    if svc_context:
        return f"service:{svc_context}:{target}", t_type
    return f"service:{target}", t_type
```

**Step 3: Fix `_build_parent_tree` — strip prefixes (line 1095)**

Change:
```python
parent_names = [p.strip() for p in p_attr.split(",") if p.strip()]
```
to:
```python
parent_names = [p.strip().lstrip("+").strip() for p in p_attr.split(",")
                if p.strip() and not p.strip().startswith("!")]
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -v`

### Part B: Frontend — edge categories and expansion rules (dependencies-config.js)

**Step 5: Add `dependent_servicegroup_name` to dependencies edge category**

In `edgeCategories.dependencies` (line 29-39), add after `master_service_description`:

```javascript
'dependent_servicegroup_name'  // Service dependency dependent via servicegroup
```

**Step 6: Add `contactgroups` to contacts edge category**

In `edgeCategories.contacts` (line 73-81), add after `contactgroup_members`:

```javascript
'contactgroups'               // Contact -> Contact group membership
```

**Step 7: Update servicedependency expansion rules**

In `expansionRules.servicedependency.network` (line 483-488), add `servicegroup_name` and `dependent_servicegroup_name` to the forward array:

```javascript
network: {
    forward: ['dependent_service_description', 'dependent_host_name', 'dependent_hostgroup_name',
              'dependent_servicegroup_name', 'service_description', 'host_name', 'hostgroup_name',
              'servicegroup_name', 'master_service_description', 'master_host_name', 'master_hostgroup_name'],
    backward: [],
    stopAt: []
},
```

**Step 8: Add service `parents` to service expansion rules**

In `expansionRules.service.network`, add `parents` to the forward array so service-to-service parent edges are followed:

```javascript
network: {
    forward: ['host_name', 'hostgroup_name', 'parents'],
    backward: ['host_name'],
    ...
},
```

**Step 9: Add `contactgroups` to contact expansion rules**

In `expansionRules.contact`, add `contactgroups` to the notifications preset forward array so contact→contactgroup membership edges are followed:

```javascript
notifications: {
    forward: ['contact_groups', 'contactgroups'],
    ...
},
```

And in the `notifiedBy` preset for contact (if it exists), add `contactgroups` to forward.

**Step 10: Commit**

```
feat: update dependency graph for Nagios 4 spec compliance

Add contactgroups and dependent_servicegroup_name to relationship
fields. Handle service parents as service-to-service references
(context-dependent, not always host). Fix _build_parent_tree to
strip +/! prefixes. Update edge categories and expansion rules for
new servicedependency fields and service parents.
```

---

## Task 6: Update frontend editor for new metadata

**Files:**
- Modify: `static/js/explorer/constants.js:52-57, 86-92`
- Modify: `static/js/explorer/object-editor.js:14-18, 314-326`

**Step 1: Add new constants to constants.js**

Add initial empty arrays at ~line 57 (inside Explorer.constants):
```javascript
HOST_STALKING_OPTIONS: [],
SERVICE_STALKING_OPTIONS: [],
HOST_FLAP_DETECTION_OPTIONS: [],
SERVICE_FLAP_DETECTION_OPTIONS: [],
HOST_ESCALATION_OPTIONS: [],
SERVICE_ESCALATION_OPTIONS: [],
```

Populate them in `applyMetadata` at ~line 92 (after SERVICE_FAILURE_CRITERIA):
```javascript
c.HOST_STALKING_OPTIONS = opts.host_stalking_options || [];
c.SERVICE_STALKING_OPTIONS = opts.service_stalking_options || [];
c.HOST_FLAP_DETECTION_OPTIONS = opts.host_flap_detection_options || [];
c.SERVICE_FLAP_DETECTION_OPTIONS = opts.service_flap_detection_options || [];
c.HOST_ESCALATION_OPTIONS = opts.host_escalation_options || [];
c.SERVICE_ESCALATION_OPTIONS = opts.service_escalation_options || [];
```

**Step 2: Add constant references in object-editor.js**

At ~line 18 (after NOTIFICATION_OPTION_ATTRS), add:
```javascript
const HOST_STALKING_OPTIONS = constants.HOST_STALKING_OPTIONS;
const SERVICE_STALKING_OPTIONS = constants.SERVICE_STALKING_OPTIONS;
const HOST_FLAP_DETECTION_OPTIONS = constants.HOST_FLAP_DETECTION_OPTIONS;
const SERVICE_FLAP_DETECTION_OPTIONS = constants.SERVICE_FLAP_DETECTION_OPTIONS;
const HOST_ESCALATION_OPTIONS = constants.HOST_ESCALATION_OPTIONS;
const SERVICE_ESCALATION_OPTIONS = constants.SERVICE_ESCALATION_OPTIONS;
```

**Step 3: Fix escalation_options, replace hardcoded stalking_options, add flap_detection_options**

Replace the escalation_options + stalking_options + add flap_detection_options block (~line 314-326):
```javascript
} else if (attrName === 'escalation_options') {
    if (objectType === 'hostescalation') {
        return HOST_ESCALATION_OPTIONS;
    } else {
        return SERVICE_ESCALATION_OPTIONS;
    }
} else if (attrName === 'stalking_options') {
    if (objectType === 'host') {
        return HOST_STALKING_OPTIONS;
    } else {
        return SERVICE_STALKING_OPTIONS;
    }
} else if (attrName === 'flap_detection_options') {
    if (objectType === 'host') {
        return HOST_FLAP_DETECTION_OPTIONS;
    } else {
        return SERVICE_FLAP_DETECTION_OPTIONS;
    }
}
```

**Step 4: Commit**

```
feat: serve all option-type field metadata from backend

Replace hardcoded stalking_options and over-broad escalation_options
in object-editor.js with spec-correct metadata-driven constants.
Add flap_detection_options context-aware suggestions. Escalation
options now correctly show d,u,r for host / w,u,c,r for service
instead of the full notification options set.
```

---

## Task 7: Update remaining tests

**Files:**
- Modify: `tests/test_health_check.py` (any remaining failures)

**Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`

Fix any remaining test failures related to:
- REQUIRED_FIELDS changes (tests asserting old required fields)
- Health check output changes (tests expecting issues that are no longer flagged)
- REFERENCE_FIELDS changes (parents now maps to None)

**Step 2: Commit**

```
test: update tests for Nagios 4 spec compliance changes
```

---

## Task 8: Final verification

**Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass, 0 failures

**Step 2: Verify metadata endpoint**

Run: `python3 -c "from app import create_app; app = create_app(); c = app.test_client(); import json; r = c.get('/api/metadata'); d = r.json; opts = d.get('notification_options', {}); print('stalking:', 'host_stalking_options' in opts); print('flap:', 'host_flap_detection_options' in opts); print('escalation:', 'host_escalation_options' in opts); print('importance in host:', 'importance' in d.get('valid_attributes', {}).get('host', [])); print('obsess in host:', 'obsess' in d.get('valid_attributes', {}).get('host', [])); print('parents in service:', 'parents' in d.get('valid_attributes', {}).get('service', []))"`

Expected: All True

**Step 3: Verify graph endpoint includes new fields**

Run: `python3 -c "from routes.analysis import _RELATIONSHIP_FIELDS; print('contactgroups:', 'contactgroups' in _RELATIONSHIP_FIELDS); print('dependent_servicegroup_name:', 'dependent_servicegroup_name' in _RELATIONSHIP_FIELDS)"`

Expected: All True

**Step 4: Commit (if any final fixes needed)**
