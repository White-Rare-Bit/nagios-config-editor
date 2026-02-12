# Nagios Inheritance Completeness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fully implement all Nagios 4 object inheritance features (null cancellation, additive `+`, important `!`, implied cross-object inheritance) and fix health checks to account for them.

**Architecture:** All value-level inheritance logic (`null`, `+`, `!`) lives in `inheritance.py`'s `resolve_inherited_attrs()` and `resolve_chain()`. A new `resolve_implied_attrs()` handles cross-object-type inheritance (services from hosts, escalations from hosts/services). A combined `resolve_all_attrs()` does both steps. Health checks switch from `resolve_inherited_attrs` to `resolve_all_attrs` where implied inheritance matters.

**Tech Stack:** Python, Flask, pytest

---

## Background: Nagios Inheritance Rules

Per https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/objectinheritance.html:

1. **null cancellation**: Setting a value to literal `null` prevents inheriting that field from templates
2. **Additive `+`**: Prefixing a value with `+` appends it to (rather than replaces) the inherited value
3. **Important `!`**: Prefixing a template value with `!` forces it to override children's local values
4. **Implied inheritance**: Services auto-inherit `contacts`, `contact_groups`, `notification_interval`, `notification_period` from their host. Host escalations inherit `contact_groups`, `notification_interval`, `escalation_period` (from host's `notification_period`). Service escalations inherit the same from their service.

Priority order: object's own attrs > template attrs (first wins) > implied attrs from associated object.

---

### Task 1: null Cancellation in Template Inheritance

**Files:**
- Modify: `inheritance.py:85-117` (`resolve_inherited_attrs`)
- Modify: `inheritance.py:170-230` (`resolve_chain`)
- Test: `tests/test_inheritance_module.py`

**Context:** When an object sets `notification_period null`, Nagios treats it as "do not inherit this field." Currently our resolver treats `"null"` as a regular string value.

**Step 1: Write failing tests for null cancellation**

Add to `tests/test_inheritance_module.py` in `TestResolveInheritedAttrs`:

```python
def test_null_cancels_inheritance(self):
    """Setting a value to 'null' prevents inheriting from template."""
    tmpl = _tmpl("host", "base", notification_period="24x7", max_check_attempts="5")
    obj = _host(host_name="web-01", use="base", notification_period="null")
    lookup = build_template_lookup([tmpl, obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    assert "notification_period" not in resolved
    assert resolved["max_check_attempts"] == "5"

def test_null_in_template_cancels_grandparent(self):
    """null in a template blocks inheritance from further up the chain."""
    grandparent = _tmpl("host", "gp", notification_period="24x7")
    parent = _tmpl("host", "parent", use="gp", notification_period="null")
    obj = _host(host_name="web-01", use="parent")
    lookup = build_template_lookup([grandparent, parent, obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    assert "notification_period" not in resolved
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_null_cancels_inheritance tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_null_in_template_cancels_grandparent -v`
Expected: FAIL — `notification_period` will be `"null"` instead of absent

**Step 3: Implement null cancellation in resolve_inherited_attrs**

In `inheritance.py`, modify `resolve_inherited_attrs()`. The sentinel approach:
- During template resolution, if a value is `"null"`, store it as a sentinel
- At the end, strip sentinel entries from the final result

```python
# At top of inheritance.py, after INHERITANCE_META:
_NULL_SENTINEL = object()  # Unique sentinel for null cancellation


def resolve_inherited_attrs(obj, template_lookup, visited=None):
    if visited is None:
        visited = set()
    resolved = {}
    use_templates = obj.attributes.get("use", "")
    if use_templates:
        for tmpl_name in (t.strip() for t in use_templates.split(",") if t.strip()):
            if tmpl_name not in visited:
                visited.add(tmpl_name)
                tmpl = template_lookup.get((obj.object_type, tmpl_name))
                if tmpl:
                    tmpl_attrs = resolve_inherited_attrs(tmpl, template_lookup, visited)
                    for key, value in tmpl_attrs.items():
                        if key not in INHERITANCE_META and key not in resolved:
                            resolved[key] = value
                visited.discard(tmpl_name)
    # Object's own attributes always override
    for key, value in obj.attributes.items():
        if value == "null":
            resolved[key] = _NULL_SENTINEL
        else:
            resolved[key] = value
    # Strip null-cancelled keys from final result
    return {k: v for k, v in resolved.items() if v is not _NULL_SENTINEL}
```

Note: The sentinel approach means that when a mid-chain template sets `null`, it stores the sentinel, and the parent's value won't override it (because `key not in resolved` is False). At the end, sentinels are stripped.

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_inheritance_module.py -v`
Expected: ALL PASS

**Step 5: Write failing test for null in resolve_chain**

Add to `TestResolveChain`:

```python
def test_null_cancels_in_chain(self):
    """null value cancels inheritance and is not in resolved chain."""
    tmpl = _tmpl("host", "base", notification_period="24x7", max_check_attempts="5")
    obj = _host(host_name="web-01", use="base", notification_period="null")
    type_lookup = {"base": tmpl}
    chain, inherited, errors = resolve_chain(obj, "host", type_lookup)
    assert "notification_period" not in inherited
    assert inherited["max_check_attempts"]["value"] == "5"
```

**Step 6: Implement null cancellation in resolve_chain**

In `resolve_chain()`, apply same logic:

```python
# In the "Object's own attributes override inherited" block (line 224-228):
obj_name = obj.get_name() or obj.attributes.get("name", "(unknown)")
for key, value in obj.attributes.items():
    if key not in INHERITANCE_META:
        if value == "null":
            inherited.pop(key, None)  # Remove if inherited, don't add
        else:
            inherited[key] = {"value": value, "source": obj_name}
```

And in the template resolution loop, propagate null sentinels:

```python
# In the template loop (line 212-215), filter out null-cancelled keys:
for key, entry in tmpl_inherited.items():
    if key not in INHERITANCE_META and key not in inherited:
        inherited[key] = entry
```

But we need to handle the case where a template set null — when `resolve_chain` recurses into a template that has `null`, the template's own resolution should exclude that key entirely. Since `resolve_chain` returns `inherited` dict, a `null` value should result in the key being absent from `inherited`. The same logic applies: if the template's own attribute is `"null"`, pop it from inherited rather than adding it.

**Step 7: Run full test suite**

Run: `python3 -m pytest tests/test_inheritance_module.py -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add inheritance.py tests/test_inheritance_module.py
git commit -m "feat: implement null cancellation in template inheritance"
```

---

### Task 2: Additive Inheritance (`+` prefix)

**Files:**
- Modify: `inheritance.py:85-117` (`resolve_inherited_attrs`)
- Modify: `inheritance.py:170-230` (`resolve_chain`)
- Test: `tests/test_inheritance_module.py`

**Context:** When an object sets `hostgroups +linux-servers,web-servers`, the `+` means append to the inherited value rather than replace. Only standard (non-custom `_` prefixed) variables support this per the Nagios spec.

**Step 1: Write failing tests for additive inheritance**

Add to `tests/test_inheritance_module.py` in `TestResolveInheritedAttrs`:

```python
def test_additive_prefix_appends(self):
    """+ prefix appends to inherited value instead of replacing."""
    tmpl = _tmpl("host", "base", hostgroups="base-group")
    obj = _host(host_name="web-01", use="base", hostgroups="+linux-servers")
    lookup = build_template_lookup([tmpl, obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    assert "base-group" in resolved["hostgroups"]
    assert "linux-servers" in resolved["hostgroups"]

def test_additive_prefix_no_inherited_value(self):
    """+ prefix with no inherited value just uses the local value (stripped)."""
    obj = _host(host_name="web-01", hostgroups="+linux-servers")
    lookup = build_template_lookup([obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    assert resolved["hostgroups"] == "linux-servers"

def test_additive_not_applied_to_custom_vars(self):
    """+ prefix on custom variables (_underscore) is NOT additive — treated as literal."""
    tmpl = _tmpl("host", "base", _NOTES="base-note")
    obj = _host(host_name="web-01", use="base", _NOTES="+extra-note")
    lookup = build_template_lookup([tmpl, obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    assert resolved["_NOTES"] == "+extra-note"

def test_additive_with_multiple_templates(self):
    """+ prefix works correctly with multi-template inheritance."""
    t1 = _tmpl("host", "first", contact_groups="admins")
    t2 = _tmpl("host", "second", contact_groups="ops")
    obj = _host(host_name="web-01", use="first,second", contact_groups="+devs")
    lookup = build_template_lookup([t1, t2, obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    # First template wins for base, then +devs appended
    assert "admins" in resolved["contact_groups"]
    assert "devs" in resolved["contact_groups"]
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_additive_prefix_appends tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_additive_prefix_no_inherited_value tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_additive_not_applied_to_custom_vars tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_additive_with_multiple_templates -v`
Expected: FAIL

**Step 3: Implement additive inheritance in resolve_inherited_attrs**

In the "Object's own attributes always override" section, detect `+` prefix:

```python
# Object's own attributes always override (or append with +)
for key, value in obj.attributes.items():
    if value == "null":
        resolved[key] = _NULL_SENTINEL
    elif (value.startswith("+") and not key.startswith("_")
          and key not in INHERITANCE_META):
        # Additive: append to inherited value
        stripped = value[1:].strip()
        existing = resolved.get(key, "")
        if existing is _NULL_SENTINEL or not existing:
            resolved[key] = stripped
        else:
            resolved[key] = f"{existing},{stripped}"
    else:
        resolved[key] = value
# Strip null-cancelled keys from final result
return {k: v for k, v in resolved.items() if v is not _NULL_SENTINEL}
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_inheritance_module.py -v`
Expected: ALL PASS

**Step 5: Write failing test for additive in resolve_chain**

Add to `TestResolveChain`:

```python
def test_additive_in_chain(self):
    """+ prefix resolves additively in chain with source tracking."""
    tmpl = _tmpl("host", "base", contact_groups="admins")
    obj = _host(host_name="web-01", use="base", contact_groups="+devs")
    type_lookup = {"base": tmpl}
    chain, inherited, errors = resolve_chain(obj, "host", type_lookup)
    assert "admins" in inherited["contact_groups"]["value"]
    assert "devs" in inherited["contact_groups"]["value"]
```

**Step 6: Implement additive in resolve_chain**

In `resolve_chain`, the "Object's own attributes override inherited" block:

```python
obj_name = obj.get_name() or obj.attributes.get("name", "(unknown)")
for key, value in obj.attributes.items():
    if key not in INHERITANCE_META:
        if value == "null":
            inherited.pop(key, None)
        elif value.startswith("+") and not key.startswith("_"):
            stripped = value[1:].strip()
            existing = inherited.get(key)
            if existing:
                inherited[key] = {
                    "value": f"{existing['value']},{stripped}",
                    "source": f"{existing['source']}+{obj_name}",
                }
            else:
                inherited[key] = {"value": stripped, "source": obj_name}
        else:
            inherited[key] = {"value": value, "source": obj_name}
```

**Step 7: Run full test suite**

Run: `python3 -m pytest tests/test_inheritance_module.py -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add inheritance.py tests/test_inheritance_module.py
git commit -m "feat: implement additive (+) inheritance for template resolution"
```

---

### Task 3: Important Values (`!` prefix)

**Files:**
- Modify: `inheritance.py:85-117` (`resolve_inherited_attrs`)
- Modify: `inheritance.py:170-230` (`resolve_chain`)
- Test: `tests/test_inheritance_module.py`

**Context:** When a template sets `!check_ping!100!500`, the `!` prefix means "important" — child objects cannot override this value with their own local value. The `!` is stripped from the final resolved value. Note: the `!` prefix is only the first character; subsequent `!` are command argument separators.

**Step 1: Write failing tests for important values**

Add to `tests/test_inheritance_module.py` in `TestResolveInheritedAttrs`:

```python
def test_important_prefix_overrides_child(self):
    """! prefix in template forces value, child cannot override."""
    tmpl = _tmpl("service", "base", check_command="!check_ping!100!500")
    obj = _Obj(object_type="service", attributes={
        "service_description": "PING", "use": "base",
        "check_command": "check_local_ping!200!600",
    })
    lookup = build_template_lookup([tmpl, obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    assert resolved["check_command"] == "check_ping!100!500"

def test_important_prefix_stripped_from_value(self):
    """! prefix is stripped from the resolved value."""
    tmpl = _tmpl("service", "base", check_command="!check_ping!100!500")
    obj = _Obj(object_type="service", attributes={
        "service_description": "PING", "use": "base",
    })
    lookup = build_template_lookup([tmpl, obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    assert resolved["check_command"] == "check_ping!100!500"

def test_important_not_applied_to_custom_vars(self):
    """! prefix on custom variables is treated as literal."""
    tmpl = _tmpl("host", "base", _SNMP="!public")
    obj = _host(host_name="web-01", use="base", _SNMP="private")
    lookup = build_template_lookup([tmpl, obj])
    resolved = resolve_inherited_attrs(obj, lookup)
    assert resolved["_SNMP"] == "private"
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_important_prefix_overrides_child tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_important_prefix_stripped_from_value tests/test_inheritance_module.py::TestResolveInheritedAttrs::test_important_not_applied_to_custom_vars -v`
Expected: FAIL

**Step 3: Implement important values in resolve_inherited_attrs**

This requires a two-pass approach. The important `!` prefix means "this template value cannot be overridden by the child." So during template resolution, we need to track which keys are "locked" by important values.

```python
def resolve_inherited_attrs(obj, template_lookup, visited=None):
    if visited is None:
        visited = set()
    resolved = {}
    important_keys = set()  # Keys locked by ! prefix
    use_templates = obj.attributes.get("use", "")
    if use_templates:
        for tmpl_name in (t.strip() for t in use_templates.split(",") if t.strip()):
            if tmpl_name not in visited:
                visited.add(tmpl_name)
                tmpl = template_lookup.get((obj.object_type, tmpl_name))
                if tmpl:
                    tmpl_attrs, tmpl_important = _resolve_with_important(
                        tmpl, template_lookup, visited,
                    )
                    for key, value in tmpl_attrs.items():
                        if key not in INHERITANCE_META and key not in resolved:
                            resolved[key] = value
                    important_keys |= tmpl_important
                visited.discard(tmpl_name)
    # Object's own attributes — respect important locks
    for key, value in obj.attributes.items():
        if key in important_keys and not key.startswith("_"):
            continue  # Locked by template ! — skip child's value
        if value == "null":
            resolved[key] = _NULL_SENTINEL
        elif value.startswith("+") and not key.startswith("_") and key not in INHERITANCE_META:
            stripped = value[1:].strip()
            existing = resolved.get(key, "")
            if existing is _NULL_SENTINEL or not existing:
                resolved[key] = stripped
            else:
                resolved[key] = f"{existing},{stripped}"
        else:
            resolved[key] = value
    return {k: v for k, v in resolved.items() if v is not _NULL_SENTINEL}


def _resolve_with_important(obj, template_lookup, visited):
    """Resolve attrs and return (resolved_dict, important_keys_set).

    important_keys are keys whose values started with ! in this template
    or any ancestor template. These keys cannot be overridden by children.
    """
    resolved = {}
    important_keys = set()
    use_templates = obj.attributes.get("use", "")
    if use_templates:
        for tmpl_name in (t.strip() for t in use_templates.split(",") if t.strip()):
            if tmpl_name not in visited:
                visited.add(tmpl_name)
                tmpl = template_lookup.get((obj.object_type, tmpl_name))
                if tmpl:
                    tmpl_attrs, tmpl_important = _resolve_with_important(
                        tmpl, template_lookup, visited,
                    )
                    for key, value in tmpl_attrs.items():
                        if key not in INHERITANCE_META and key not in resolved:
                            resolved[key] = value
                    important_keys |= tmpl_important
                visited.discard(tmpl_name)
    # This template's own attributes
    for key, value in obj.attributes.items():
        if key in important_keys and not key.startswith("_"):
            continue  # Locked by parent template
        if value == "null":
            resolved[key] = _NULL_SENTINEL
        elif (isinstance(value, str) and value.startswith("!")
              and not key.startswith("_") and key not in INHERITANCE_META):
            resolved[key] = value[1:]  # Strip ! prefix
            important_keys.add(key)
        elif value.startswith("+") and not key.startswith("_") and key not in INHERITANCE_META:
            stripped = value[1:].strip()
            existing = resolved.get(key, "")
            if existing is _NULL_SENTINEL or not existing:
                resolved[key] = stripped
            else:
                resolved[key] = f"{existing},{stripped}"
        else:
            resolved[key] = value
    result = {k: v for k, v in resolved.items() if v is not _NULL_SENTINEL}
    return result, important_keys
```

**Important design note:** `resolve_inherited_attrs` is the public API. Internally it now calls `_resolve_with_important` for templates to track important keys. The public function's signature is unchanged — callers are unaffected.

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_inheritance_module.py -v`
Expected: ALL PASS (including all existing tests — verify no regressions)

**Step 5: Implement important values in resolve_chain**

Similar logic needed in `resolve_chain`. Template values starting with `!` should:
1. Strip the `!` from the stored value
2. Prevent child objects from overriding that key
3. Track source as the template that set the important value

This is more involved — `resolve_chain` needs to propagate important keys through recursion. Add an `_important_keys` return value:

In the template resolution loop, collect important keys. In the object's own attributes loop, skip keys in `important_keys`.

**Step 6: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add inheritance.py tests/test_inheritance_module.py
git commit -m "feat: implement important (!) value prefix in template inheritance"
```

---

### Task 4: Implied Inheritance (Cross-Object-Type)

**Files:**
- Modify: `inheritance.py` (add `resolve_implied_attrs` and `resolve_all_attrs`)
- Modify: `nagios_model.py` (add `IMPLIED_INHERITANCE` constant)
- Test: `tests/test_inheritance_module.py`

**Context:** Nagios auto-inherits certain fields across object types:
- Services inherit from hosts: `contacts`, `contact_groups`, `notification_interval`, `notification_period`
- Host escalations inherit from hosts: `contact_groups`, `notification_interval`, `escalation_period` (mapped from `notification_period`)
- Service escalations inherit from services: `contact_groups`, `notification_interval`, `escalation_period` (mapped from `notification_period`)

**Step 1: Define IMPLIED_INHERITANCE constant in nagios_model.py**

Add after `SPECIAL_DIRECTIVES`:

```python
# Implied inheritance: fields auto-inherited from associated objects.
# Key: (child_type, parent_type, parent_key_field)
# Value: list of (child_field, parent_field) tuples
# parent_key_field is the attribute on the child that references the parent
IMPLIED_INHERITANCE = {
    ("service", "host", "host_name"): [
        ("contacts", "contacts"),
        ("contact_groups", "contact_groups"),
        ("notification_interval", "notification_interval"),
        ("notification_period", "notification_period"),
    ],
    ("hostescalation", "host", "host_name"): [
        ("contact_groups", "contact_groups"),
        ("notification_interval", "notification_interval"),
        ("escalation_period", "notification_period"),  # Field rename
    ],
    ("serviceescalation", "service", "host_name"): [
        ("contact_groups", "contact_groups"),
        ("notification_interval", "notification_interval"),
        ("escalation_period", "notification_period"),  # Field rename
    ],
}
```

Note: For service escalations, the lookup is more complex — need to match both `host_name` AND `service_description`. The implementation handles this.

**Step 2: Write failing tests for implied inheritance**

Add new test class in `tests/test_inheritance_module.py`:

```python
from inheritance import resolve_implied_attrs, resolve_all_attrs


class TestResolveImpliedAttrs:
    def test_service_inherits_contacts_from_host(self):
        """Service with no contacts inherits from its host."""
        host = _host(host_name="web-01", contacts="admin", notification_period="24x7")
        svc = _Obj(object_type="service", attributes={
            "host_name": "web-01", "service_description": "PING",
            "check_command": "check_ping",
        })
        objects = [host, svc]
        template_lookup = build_template_lookup(objects)
        resolved = resolve_inherited_attrs(svc, template_lookup)
        result = resolve_implied_attrs(resolved, svc.object_type, objects, template_lookup)
        assert result["contacts"] == "admin"
        assert result["notification_period"] == "24x7"

    def test_service_own_contacts_not_overridden(self):
        """Service with its own contacts does NOT inherit from host."""
        host = _host(host_name="web-01", contacts="admin")
        svc = _Obj(object_type="service", attributes={
            "host_name": "web-01", "service_description": "PING",
            "contacts": "svc-contact",
        })
        objects = [host, svc]
        template_lookup = build_template_lookup(objects)
        resolved = resolve_inherited_attrs(svc, template_lookup)
        result = resolve_implied_attrs(resolved, svc.object_type, objects, template_lookup)
        assert result["contacts"] == "svc-contact"

    def test_host_escalation_inherits_from_host(self):
        """Host escalation inherits contact_groups and escalation_period from host."""
        host = _host(
            host_name="web-01", contact_groups="admins",
            notification_interval="30", notification_period="24x7",
        )
        esc = _Obj(object_type="hostescalation", attributes={
            "host_name": "web-01", "first_notification": "3", "last_notification": "5",
        })
        objects = [host, esc]
        template_lookup = build_template_lookup(objects)
        resolved = resolve_inherited_attrs(esc, template_lookup)
        result = resolve_implied_attrs(resolved, esc.object_type, objects, template_lookup)
        assert result["contact_groups"] == "admins"
        assert result["escalation_period"] == "24x7"

    def test_service_escalation_inherits_from_service(self):
        """Service escalation inherits from its service."""
        host = _host(host_name="web-01")
        svc = _Obj(object_type="service", attributes={
            "host_name": "web-01", "service_description": "PING",
            "contact_groups": "svc-admins", "notification_period": "workhours",
        })
        esc = _Obj(object_type="serviceescalation", attributes={
            "host_name": "web-01", "service_description": "PING",
            "first_notification": "3", "last_notification": "5",
        })
        objects = [host, svc, esc]
        template_lookup = build_template_lookup(objects)
        resolved = resolve_inherited_attrs(esc, template_lookup)
        result = resolve_implied_attrs(resolved, esc.object_type, objects, template_lookup)
        assert result["contact_groups"] == "svc-admins"
        assert result["escalation_period"] == "workhours"

    def test_implied_does_not_apply_to_unrelated_types(self):
        """Implied inheritance only applies to specific type combinations."""
        host = _host(host_name="web-01", contacts="admin")
        objects = [host]
        template_lookup = build_template_lookup(objects)
        resolved = resolve_inherited_attrs(host, template_lookup)
        result = resolve_implied_attrs(resolved, host.object_type, objects, template_lookup)
        assert result == resolved  # No change for hosts


class TestResolveAllAttrs:
    def test_combines_template_and_implied(self):
        """resolve_all_attrs does template + implied resolution."""
        tmpl = _tmpl("service", "base-svc", check_command="check_ping", max_check_attempts="3")
        host = _host(host_name="web-01", contacts="admin", notification_period="24x7")
        svc = _Obj(object_type="service", attributes={
            "host_name": "web-01", "service_description": "PING", "use": "base-svc",
        })
        objects = [tmpl, host, svc]
        template_lookup = build_template_lookup(objects)
        resolved = resolve_all_attrs(svc, template_lookup, objects)
        assert resolved["check_command"] == "check_ping"  # From template
        assert resolved["contacts"] == "admin"  # Implied from host
        assert resolved["notification_period"] == "24x7"  # Implied from host

    def test_template_attrs_beat_implied(self):
        """Template-inherited values take priority over implied."""
        tmpl = _tmpl("service", "base-svc", contacts="tmpl-contact")
        host = _host(host_name="web-01", contacts="host-contact")
        svc = _Obj(object_type="service", attributes={
            "host_name": "web-01", "service_description": "PING", "use": "base-svc",
        })
        objects = [tmpl, host, svc]
        template_lookup = build_template_lookup(objects)
        resolved = resolve_all_attrs(svc, template_lookup, objects)
        assert resolved["contacts"] == "tmpl-contact"  # Template wins over implied
```

**Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_inheritance_module.py::TestResolveImpliedAttrs tests/test_inheritance_module.py::TestResolveAllAttrs -v`
Expected: FAIL — functions don't exist yet

**Step 4: Implement resolve_implied_attrs and resolve_all_attrs**

Add to `inheritance.py`:

```python
from nagios_model import IMPLIED_INHERITANCE, NAME_FIELDS


def resolve_implied_attrs(resolved_attrs, obj_type, objects, template_lookup):
    """Fill in missing fields from implied inheritance (cross-object-type).

    Implied inheritance is lowest priority — only fills in fields not already
    set by the object's own attributes or template inheritance.

    Args:
        resolved_attrs: dict of already-resolved attributes (from resolve_inherited_attrs)
        obj_type: the object's type string
        objects: full list of NagiosObject instances
        template_lookup: dict of (obj_type, tmpl_name) -> obj

    Returns:
        dict with implied fields filled in (new dict, doesn't mutate input)
    """
    result = dict(resolved_attrs)

    for (child_type, parent_type, parent_key_field), field_mappings in IMPLIED_INHERITANCE.items():
        if obj_type != child_type:
            continue

        # Find the parent object
        parent_obj = _find_implied_parent(
            result, obj_type, parent_type, parent_key_field, objects,
        )
        if not parent_obj:
            continue

        # Resolve the parent's full attributes (template inheritance)
        parent_resolved = resolve_inherited_attrs(parent_obj, template_lookup)

        # Fill in missing fields
        for child_field, parent_field in field_mappings:
            if child_field not in result and parent_field in parent_resolved:
                result[child_field] = parent_resolved[parent_field]

    return result


def _find_implied_parent(resolved_attrs, obj_type, parent_type, parent_key_field, objects):
    """Find the parent object for implied inheritance.

    For service escalations, matches on both host_name and service_description.
    For other types, matches on the parent_key_field only.
    """
    parent_key = resolved_attrs.get(parent_key_field, "")
    if not parent_key:
        return None

    # For service escalations, need to match service by host_name + service_description
    if obj_type == "serviceescalation" and parent_type == "service":
        svc_desc = resolved_attrs.get("service_description", "")
        for obj in objects:
            if obj.object_type != "service":
                continue
            if obj.attributes.get("register", "1") == "0":
                continue
            obj_host = obj.attributes.get("host_name", "")
            obj_svc = obj.attributes.get("service_description", "")
            if parent_key in (h.strip() for h in obj_host.split(",")) and obj_svc == svc_desc:
                return obj
        return None

    # For hosts, hostescalations, services: match by name field
    name_field = NAME_FIELDS.get(parent_type, "")
    for obj in objects:
        if obj.object_type != parent_type:
            continue
        if obj.attributes.get("register", "1") == "0":
            continue
        obj_name = obj.attributes.get(name_field, "")
        # parent_key can be comma-separated (e.g. host_name on service); use first
        first_parent = parent_key.split(",")[0].strip()
        if obj_name == first_parent:
            return obj
    return None


def resolve_all_attrs(obj, template_lookup, objects):
    """Resolve all attributes: template inheritance + implied inheritance.

    This is the recommended entry point for callers that need fully-resolved
    attributes matching Nagios behavior.

    Args:
        obj: NagiosObject to resolve
        template_lookup: dict of (obj_type, tmpl_name) -> obj
        objects: full list of NagiosObject instances

    Returns:
        dict[attr_name, value] — fully resolved attributes
    """
    resolved = resolve_inherited_attrs(obj, template_lookup)
    return resolve_implied_attrs(resolved, obj.object_type, objects, template_lookup)
```

**Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_inheritance_module.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add inheritance.py nagios_model.py tests/test_inheritance_module.py
git commit -m "feat: implement implied cross-object inheritance (host→service, host/service→escalation)"
```

---

### Task 5: Additive + Implied Inheritance Interaction for Escalations

**Files:**
- Modify: `inheritance.py` (`resolve_implied_attrs`)
- Test: `tests/test_inheritance_module.py`

**Context:** Per the Nagios spec, escalations have a special interaction: if an escalation doesn't inherit `contact_groups`/`contacts` from a template AND its value starts with `+`, the additive value uses the associated host/service's contacts as the base. This is the "implied/additive" combination.

**Step 1: Write failing test**

```python
def test_escalation_additive_with_implied_base(self):
    """Escalation + prefix uses host's contacts as base when no template provides them."""
    host = _host(host_name="web-01", contact_groups="admins")
    esc = _Obj(object_type="hostescalation", attributes={
        "host_name": "web-01", "first_notification": "3",
        "last_notification": "5", "contact_groups": "+managers",
    })
    objects = [host, esc]
    template_lookup = build_template_lookup(objects)
    resolved = resolve_all_attrs(esc, template_lookup, objects)
    assert "admins" in resolved["contact_groups"]
    assert "managers" in resolved["contact_groups"]
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_inheritance_module.py::TestResolveAllAttrs::test_escalation_additive_with_implied_base -v`
Expected: FAIL

**Step 3: Implement additive + implied interaction**

In `resolve_implied_attrs`, when filling in implied fields, check if the child has a `+` prefixed value. If so, the implied value is the base:

```python
# In resolve_implied_attrs, replace the fill-in loop:
for child_field, parent_field in field_mappings:
    if child_field not in result and parent_field in parent_resolved:
        result[child_field] = parent_resolved[parent_field]
```

Wait — the `+` prefix would have already been processed by `resolve_inherited_attrs`. If there's no template to provide a base, the `+` gets stripped and the value is just the stripped local value. But with implied inheritance, we need to use the parent's value as the base.

The fix: in `resolve_inherited_attrs`, when a `+` prefixed value has no base (no inherited value), store a marker so `resolve_implied_attrs` knows to prepend the implied value. Alternative simpler approach: `resolve_implied_attrs` checks if the resolved value looks like it could be an additive result (checking original object attributes for `+` prefix):

Actually, the simplest correct approach: `resolve_all_attrs` passes the original object so `resolve_implied_attrs` can check `obj.attributes` for `+` prefixed values that had no template base.

Update `resolve_implied_attrs` signature to accept the original object:

```python
def resolve_implied_attrs(resolved_attrs, obj_type, obj, objects, template_lookup):
    ...
    for child_field, parent_field in field_mappings:
        if child_field not in result and parent_field in parent_resolved:
            result[child_field] = parent_resolved[parent_field]
        elif child_field in result and parent_field in parent_resolved:
            # Check if original object had + prefix (additive with implied base)
            original_val = obj.attributes.get(child_field, "") if obj else ""
            if original_val.startswith("+") and not child_field.startswith("_"):
                stripped = original_val[1:].strip()
                result[child_field] = f"{parent_resolved[parent_field]},{stripped}"
```

And update `resolve_all_attrs`:

```python
def resolve_all_attrs(obj, template_lookup, objects):
    resolved = resolve_inherited_attrs(obj, template_lookup)
    return resolve_implied_attrs(resolved, obj.object_type, obj, objects, template_lookup)
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_inheritance_module.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add inheritance.py tests/test_inheritance_module.py
git commit -m "feat: implement additive + implied inheritance interaction for escalations"
```

---

### Task 6: Update Health Checks for Correct Inheritance Resolution

**Files:**
- Modify: `routes/health_checks.py` (multiple check functions)
- Test: `tests/test_health_check.py` (add new test cases)

**Context:** Several health checks use `resolve_inherited_attrs()` and need to switch to `resolve_all_attrs()` to account for null cancellation, additive values, and implied inheritance. The `build_context` function also needs the objects list available for implied resolution.

**Step 1: Update imports in health_checks.py**

```python
# Change line 10:
from inheritance import has_attr_in_chain, resolve_all_attrs, resolve_inherited_attrs
```

Note: We keep `resolve_inherited_attrs` imported because some checks only need template resolution (e.g., checking template-specific issues), but notification/contact-related checks switch to `resolve_all_attrs`.

**Step 2: Update build_context to pass template_lookup as (obj_type, name) keyed**

The `build_context` already stores `template_lookup` and `objects` in `ctx`. No changes needed to the context builder — callers already have everything they need.

**Step 3: Update check_missing_check_command (Check 11)**

Line 683: Change `resolve_inherited_attrs(obj, template_lookup)` to `resolve_all_attrs(obj, template_lookup, ctx["objects"])`.

(Note: `check_command` isn't an implied field, but null/additive/important could affect it.)

**Step 4: Update check_command_arg_mismatch (Check 12)**

Line 715: Same change.

**Step 5: Update check_service_host_notification_reachability (Check 14b)**

Line 886: Change to `resolve_all_attrs(obj, template_lookup, ctx["objects"])`. This is the **biggest accuracy fix** — services without template-provided contacts will now correctly fall back to host contacts via implied inheritance.

**Step 6: Update check_missing_contacts_on_objects (Check 21)**

This check currently flags services with no contacts/contact_groups/template. With implied inheritance, it should resolve fully and check whether the service ultimately has contacts. Replace the simple attribute check with full resolution:

```python
def check_missing_contacts_on_objects(ctx):
    """Check 21: Hosts/services with no contacts or contact_groups after full resolution."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    template_lookup = ctx["template_lookup"]
    objects = ctx["objects"]

    for obj in objects:
        if obj.object_type not in ("host", "service"):
            continue
        if obj.attributes.get("register", "1") == "0":
            continue
        resolved = resolve_all_attrs(obj, template_lookup, objects)
        has_contacts = bool(resolved.get("contacts"))
        has_contact_groups = bool(resolved.get("contact_groups"))
        if not has_contacts and not has_contact_groups:
            obj_name = obj.get_name() or obj.get_display_name()
            issues.append({
                "type": "missing_contacts",
                "severity": "warning",
                "object": obj_name,
                "object_type": obj.object_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": f"{obj.object_type.title()} has no contacts or contact_groups (after template and implied inheritance)",
            })
    return issues
```

**Step 7: Update check_required_fields (Check 24)**

Line 1482: Change to `resolve_all_attrs(obj, template_lookup, ctx["objects"])`.

**Step 8: Update check_redundant_escalation_contacts (Check 26)**

The `get_contact_set` inner function on line 1591 should use `resolve_all_attrs`:

```python
def get_contact_set(obj):
    resolved = resolve_all_attrs(obj, template_lookup, objects)
    ...
```

**Step 9: Update check_notification_period_criticality (Check 28)**

Line 1732: Change to `resolve_all_attrs(obj, template_lookup, ctx["objects"])`.

**Step 10: Write tests for health check accuracy**

Add test cases to `tests/test_health_check.py` that verify:
1. A service with no contacts that inherits from its host does NOT get flagged
2. A service that sets `contacts null` DOES get flagged
3. Additive `+` contact_groups resolve correctly in notification checks

**Step 11: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 12: Commit**

```bash
git add routes/health_checks.py tests/test_health_check.py
git commit -m "fix: health checks use full inheritance resolution (null, additive, implied)"
```

---

### Task 7: Update resolve_chain for UI Display

**Files:**
- Modify: `inheritance.py:170-230` (`resolve_chain`)
- Modify: `routes/templates.py` (inheritance endpoint)
- Test: `tests/test_inheritance_module.py`

**Context:** The `resolve_chain` function is used by the UI to display inheritance info with source tracking. It needs to handle null/additive/important correctly and optionally show implied sources.

**Step 1: Write failing tests for resolve_chain with new features**

```python
def test_null_cancels_in_chain(self):
    """null value removes field from resolved chain."""
    tmpl = _tmpl("host", "base", notification_period="24x7", max_check_attempts="5")
    obj = _host(host_name="web-01", use="base", notification_period="null")
    type_lookup = {"base": tmpl}
    chain, inherited, errors = resolve_chain(obj, "host", type_lookup)
    assert "notification_period" not in inherited
    assert inherited["max_check_attempts"]["value"] == "5"

def test_additive_in_chain(self):
    """+ prefix resolves additively in chain with combined source."""
    tmpl = _tmpl("host", "base", contact_groups="admins")
    obj = _host(host_name="web-01", use="base", contact_groups="+devs")
    type_lookup = {"base": tmpl}
    chain, inherited, errors = resolve_chain(obj, "host", type_lookup)
    assert "admins" in inherited["contact_groups"]["value"]
    assert "devs" in inherited["contact_groups"]["value"]

def test_important_in_chain(self):
    """! prefix in template forces value, child's value is ignored."""
    tmpl = _tmpl("service", "base", check_command="!check_ping!100!500")
    obj = _Obj(object_type="service", attributes={
        "service_description": "PING", "use": "base",
        "check_command": "check_local",
    })
    type_lookup = {"base": tmpl}
    chain, inherited, errors = resolve_chain(obj, "service", type_lookup)
    assert inherited["check_command"]["value"] == "check_ping!100!500"
    assert inherited["check_command"]["source"] == "base"
```

**Step 2: Implement in resolve_chain**

Apply the same null/additive/important logic to `resolve_chain`. The changes mirror Task 1-3 but with source tracking.

**Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add inheritance.py tests/test_inheritance_module.py
git commit -m "feat: resolve_chain handles null, additive, and important prefixes"
```

---

### Task 8: Update has_attr_in_chain for null Awareness

**Files:**
- Modify: `inheritance.py:120-140` (`has_attr_in_chain`)
- Test: `tests/test_inheritance_module.py`

**Context:** `has_attr_in_chain` short-circuits on finding an attribute. But if the attribute is `"null"`, it should return False (the attribute is explicitly cancelled).

**Step 1: Write failing test**

```python
def test_null_value_returns_false(self):
    """Attribute set to 'null' should be treated as not present."""
    tmpl = _tmpl("host", "base", notification_period="24x7")
    obj = _host(host_name="web-01", use="base", notification_period="null")
    lookup = build_template_lookup([tmpl, obj])
    assert has_attr_in_chain(obj, "notification_period", lookup) is False
```

**Step 2: Implement**

```python
def has_attr_in_chain(obj, attr_name, template_lookup, visited=None):
    if visited is None:
        visited = set()
    if attr_name in obj.attributes:
        return obj.attributes[attr_name] != "null"
    ...
```

**Step 3: Run tests, commit**

Run: `python3 -m pytest tests/test_inheritance_module.py -v`

```bash
git add inheritance.py tests/test_inheritance_module.py
git commit -m "fix: has_attr_in_chain treats null values as absent"
```

---

### Task 9: Update strip_prefix and _expand_contacts

**Files:**
- Modify: `routes/health_checks.py` (`strip_prefix`, `_expand_contacts`)
- Test: `tests/test_health_check.py`

**Context:** The `_expand_contacts` helper strips `+!` prefixes before looking up contacts. With the new inheritance resolution handling `+` additively, the resolved values will no longer have `+` prefixes (they're processed during resolution). Verify this still works correctly and that `_expand_contacts` handles the new concatenated format.

**Step 1: Verify _expand_contacts works with resolved additive values**

After `resolve_all_attrs`, a value like `contact_groups` would be `"admins,devs"` (already concatenated). `_expand_contacts` splits on `,` and strips whitespace, which is correct.

The `lstrip("+!")` on line 859 is now redundant for properly resolved values but harmless. Leave it as defensive coding.

**Step 2: Write a test confirming the end-to-end flow**

Add to health check tests:

```python
def test_notification_reachability_with_implied_contacts(self):
    """Service inheriting contacts from host should not be flagged."""
    # Create config where service has no contacts but host does
    # Health check should NOT flag this service
    ...
```

**Step 3: Run tests, commit**

```bash
git add routes/health_checks.py tests/test_health_check.py
git commit -m "fix: _expand_contacts works correctly with resolved additive values"
```

---

### Task 10: Integration Test with Real Config Files

**Files:**
- Create: `tests/test_inheritance_integration.py`

**Context:** End-to-end test using actual config files that exercise all four inheritance features together. Uses the Flask test client to verify the inheritance API returns correct results.

**Step 1: Write integration test**

Create `tests/test_inheritance_integration.py` with a fixture that creates config files using:
- Templates with `!` important values
- Objects with `+` additive values
- Objects with `null` cancellation
- Services that rely on implied inheritance from hosts
- Host escalations that inherit from hosts

Verify via the `/api/templates/inheritance/<key>` endpoint and the `/api/health-check` endpoint that:
1. Resolved values are correct
2. Health checks don't produce false positives for implied inheritance
3. Health checks DO flag genuinely missing contacts

**Step 2: Run integration test**

Run: `python3 -m pytest tests/test_inheritance_integration.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_inheritance_integration.py
git commit -m "test: integration tests for full Nagios inheritance feature set"
```

---

### Task 11: Final Verification

**Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 2: Manual smoke test**

Run: `python3 app.py`
- Load sample config
- Navigate to inheritance viewer
- Verify templates with `+`, `null`, `!` display correctly
- Check health check results for accuracy
