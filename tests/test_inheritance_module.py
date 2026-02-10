"""Tests for the unified inheritance module."""

from dataclasses import dataclass, field

from inheritance import (
    INHERITANCE_META,
    build_template_index,
    build_template_lookup,
    build_template_names_set,
    build_type_template_lookup,
    detect_template_cycles,
    find_invalid_use_refs,
    find_unused_templates,
    format_cycle_issues,
    get_template_chain,
    has_attr_in_chain,
    resolve_chain,
    resolve_inherited_attrs,
    walk_inheritance_chain,
)


# ─────────────────────────────────────────────────────────────────────
# Minimal NagiosObject stub for unit tests
# ─────────────────────────────────────────────────────────────────────

@dataclass
class _Obj:
    """Minimal stub matching NagiosObject interface used by inheritance."""
    object_type: str
    attributes: dict = field(default_factory=dict)
    source_file: str = "test.cfg"

    def get_name(self):
        from nagios_model import NAME_FIELDS
        nf = NAME_FIELDS.get(self.object_type)
        return self.attributes.get(nf) if nf else self.attributes.get("name")

    def to_dict(self):
        return {
            "object_type": self.object_type,
            "attributes": dict(self.attributes),
            "source_file": self.source_file,
        }


def _host(**attrs):
    return _Obj(object_type="host", attributes=attrs)


def _tmpl(obj_type, name, **attrs):
    return _Obj(object_type=obj_type, attributes={"name": name, "register": "0", **attrs})


# ─────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────

class TestInheritanceMeta:
    def test_contains_expected_keys(self):
        assert INHERITANCE_META == {"use", "name", "register"}

    def test_is_frozenset(self):
        assert isinstance(INHERITANCE_META, frozenset)


# ─────────────────────────────────────────────────────────────────────
# Lookup builders
# ─────────────────────────────────────────────────────────────────────

class TestBuildTemplateLookup:
    def test_maps_by_type_and_name(self):
        t = _tmpl("host", "base-host", max_check_attempts="5")
        lookup = build_template_lookup([t])
        assert ("host", "base-host") in lookup
        assert lookup[("host", "base-host")] is t

    def test_skips_objects_without_name(self):
        obj = _host(host_name="web-01")
        lookup = build_template_lookup([obj])
        assert len(lookup) == 0

    def test_multiple_types(self):
        t1 = _tmpl("host", "base-host")
        t2 = _tmpl("service", "base-svc")
        lookup = build_template_lookup([t1, t2])
        assert ("host", "base-host") in lookup
        assert ("service", "base-svc") in lookup


class TestBuildTypeTemplateLookup:
    def test_filters_by_type(self):
        t1 = _tmpl("host", "base-host")
        t2 = _tmpl("service", "base-svc")
        lookup = build_type_template_lookup([t1, t2], "host")
        assert "base-host" in lookup
        assert "base-svc" not in lookup

    def test_includes_objects_with_name_attr(self):
        # Objects with a "name" attr are templates regardless of register
        obj = _Obj(object_type="host", attributes={"name": "my-tmpl"})
        lookup = build_type_template_lookup([obj], "host")
        assert "my-tmpl" in lookup


class TestBuildTemplateNamesSet:
    def test_only_register_0(self):
        t = _tmpl("host", "base-host")
        regular = _host(host_name="web-01")
        result = build_template_names_set([t, regular])
        assert ("host", "base-host") in result
        assert len(result) == 1

    def test_skips_register_0_without_name(self):
        obj = _Obj(object_type="host", attributes={"register": "0"})
        result = build_template_names_set([obj])
        assert len(result) == 0


class TestBuildTemplateIndex:
    def test_returns_by_type_and_all(self):
        t1 = _tmpl("host", "base-host")
        t2 = _tmpl("service", "base-svc")
        by_type, all_tmpls = build_template_index([t1, t2])
        assert "base-host" in by_type["host"]
        assert "base-svc" in by_type["service"]
        assert ("host", "base-host") in all_tmpls
        assert ("service", "base-svc") in all_tmpls


# ─────────────────────────────────────────────────────────────────────
# Attribute resolution
# ─────────────────────────────────────────────────────────────────────

class TestResolveInheritedAttrs:
    def test_single_template(self):
        tmpl = _tmpl("host", "base", max_check_attempts="5", notification_interval="30")
        obj = _host(host_name="web-01", use="base")
        lookup = build_template_lookup([tmpl, obj])
        resolved = resolve_inherited_attrs(obj, lookup)
        assert resolved["max_check_attempts"] == "5"
        assert resolved["host_name"] == "web-01"

    def test_object_attrs_override_template(self):
        tmpl = _tmpl("host", "base", max_check_attempts="5")
        obj = _host(host_name="web-01", use="base", max_check_attempts="3")
        lookup = build_template_lookup([tmpl, obj])
        resolved = resolve_inherited_attrs(obj, lookup)
        assert resolved["max_check_attempts"] == "3"

    def test_first_template_wins(self):
        """Correct Nagios precedence: first template in use list wins."""
        t1 = _tmpl("host", "first", max_check_attempts="5")
        t2 = _tmpl("host", "second", max_check_attempts="10")
        obj = _host(host_name="web-01", use="first,second")
        lookup = build_template_lookup([t1, t2, obj])
        resolved = resolve_inherited_attrs(obj, lookup)
        assert resolved["max_check_attempts"] == "5"

    def test_deep_chain(self):
        grandparent = _tmpl("host", "grandparent", notification_interval="60")
        parent = _tmpl("host", "parent", use="grandparent", max_check_attempts="5")
        obj = _host(host_name="web-01", use="parent")
        lookup = build_template_lookup([grandparent, parent, obj])
        resolved = resolve_inherited_attrs(obj, lookup)
        assert resolved["notification_interval"] == "60"
        assert resolved["max_check_attempts"] == "5"

    def test_cycle_detection(self):
        """Cycle A->B->A should not infinite loop."""
        a = _tmpl("host", "A", use="B")
        b = _tmpl("host", "B", use="A")
        lookup = build_template_lookup([a, b])
        # Should not raise — cycle is silently broken
        resolved = resolve_inherited_attrs(a, lookup)
        assert isinstance(resolved, dict)

    def test_sibling_branch_reuse(self):
        """A uses B,C; both B and C use D. D should resolve in both branches."""
        d = _tmpl("host", "D", notification_interval="60")
        b = _tmpl("host", "B", use="D", max_check_attempts="5")
        c = _tmpl("host", "C", use="D", check_command="check-alive")
        a = _host(host_name="web-01", use="B,C")
        lookup = build_template_lookup([d, b, c, a])
        resolved = resolve_inherited_attrs(a, lookup)
        # B is first, so B's attrs (and D's via B) take precedence
        assert resolved["notification_interval"] == "60"
        assert resolved["max_check_attempts"] == "5"
        # C's unique attr should also be present
        assert resolved["check_command"] == "check-alive"

    def test_missing_template_skipped(self):
        obj = _host(host_name="web-01", use="nonexistent")
        lookup = build_template_lookup([obj])
        resolved = resolve_inherited_attrs(obj, lookup)
        assert resolved["host_name"] == "web-01"

    def test_excludes_inheritance_meta(self):
        tmpl = _tmpl("host", "base", max_check_attempts="5")
        obj = _host(host_name="web-01", use="base")
        lookup = build_template_lookup([tmpl, obj])
        resolved = resolve_inherited_attrs(obj, lookup)
        # 'name' and 'register' from template should not be in resolved
        # (they ARE in the template's own attrs, but filtered during inheritance)
        # Object's own 'use' IS in resolved since we copy all obj attrs at the end
        assert "name" not in resolved or resolved.get("name") != "base"

    def test_first_template_wins_in_deep_chain(self):
        """When first template's parent and second template both set same attr,
        first template's parent wins."""
        gp = _tmpl("host", "gp", check_command="check-gp")
        t1 = _tmpl("host", "first", use="gp")
        t2 = _tmpl("host", "second", check_command="check-second")
        obj = _host(host_name="web-01", use="first,second")
        lookup = build_template_lookup([gp, t1, t2, obj])
        resolved = resolve_inherited_attrs(obj, lookup)
        assert resolved["check_command"] == "check-gp"

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


class TestHasAttrInChain:
    def test_direct_attr(self):
        obj = _host(host_name="web-01", check_command="check-alive")
        lookup = build_template_lookup([obj])
        assert has_attr_in_chain(obj, "check_command", lookup) is True

    def test_inherited_attr(self):
        tmpl = _tmpl("host", "base", check_command="check-alive")
        obj = _host(host_name="web-01", use="base")
        lookup = build_template_lookup([tmpl, obj])
        assert has_attr_in_chain(obj, "check_command", lookup) is True

    def test_missing_attr(self):
        tmpl = _tmpl("host", "base", max_check_attempts="5")
        obj = _host(host_name="web-01", use="base")
        lookup = build_template_lookup([tmpl, obj])
        assert has_attr_in_chain(obj, "check_command", lookup) is False

    def test_cycle_safe(self):
        a = _tmpl("host", "A", use="B")
        b = _tmpl("host", "B", use="A")
        lookup = build_template_lookup([a, b])
        assert has_attr_in_chain(a, "check_command", lookup) is False

    def test_sibling_branch_reuse(self):
        d = _tmpl("host", "D", check_command="check-alive")
        b = _tmpl("host", "B", use="D")
        c = _tmpl("host", "C", use="D")
        a = _host(host_name="web-01", use="B,C")
        lookup = build_template_lookup([d, b, c, a])
        assert has_attr_in_chain(a, "check_command", lookup) is True

    def test_null_value_returns_false(self):
        """Attribute set to 'null' should be treated as not present."""
        tmpl = _tmpl("host", "base", notification_period="24x7")
        obj = _host(host_name="web-01", use="base", notification_period="null")
        lookup = build_template_lookup([tmpl, obj])
        assert has_attr_in_chain(obj, "notification_period", lookup) is False


# ─────────────────────────────────────────────────────────────────────
# Chain walking
# ─────────────────────────────────────────────────────────────────────

class TestWalkInheritanceChain:
    def test_single_object(self):
        obj = _host(host_name="web-01")
        chain = walk_inheritance_chain(obj, {})
        assert len(chain) == 1
        assert chain[0]["attributes"]["host_name"] == "web-01"

    def test_with_template(self):
        tmpl = _tmpl("host", "base", max_check_attempts="5")
        obj = _host(host_name="web-01", use="base")
        templates = {"base": tmpl}
        chain = walk_inheritance_chain(obj, templates)
        assert len(chain) == 2
        assert chain[1]["attributes"]["name"] == "base"

    def test_cycle_safe(self):
        a = _tmpl("host", "A", use="B")
        b = _tmpl("host", "B", use="A")
        templates = {"A": a, "B": b}
        chain = walk_inheritance_chain(a, templates)
        # Should not infinite loop
        assert len(chain) >= 1


class TestResolveChain:
    def test_single_template(self):
        tmpl = _tmpl("host", "base", max_check_attempts="5")
        obj = _host(host_name="web-01", use="base")
        type_lookup = {"base": tmpl}
        chain, inherited, errors = resolve_chain(obj, "host", type_lookup)
        assert len(chain) == 1
        assert chain[0]["name"] == "base"
        assert inherited["host_name"]["source"] == "web-01"
        assert inherited["max_check_attempts"]["value"] == "5"
        assert len(errors) == 0

    def test_first_template_wins(self):
        t1 = _tmpl("host", "first", max_check_attempts="5")
        t2 = _tmpl("host", "second", max_check_attempts="10")
        obj = _host(host_name="web-01", use="first,second")
        type_lookup = {"first": t1, "second": t2}
        chain, inherited, errors = resolve_chain(obj, "host", type_lookup)
        # Object's own attrs override everything
        assert inherited["host_name"]["source"] == "web-01"
        # First template wins for inherited attrs
        assert inherited["max_check_attempts"]["value"] == "5"
        assert inherited["max_check_attempts"]["source"] == "first"

    def test_missing_template_error(self):
        obj = _host(host_name="web-01", use="nonexistent")
        chain, inherited, errors = resolve_chain(obj, "host", {})
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_circular_dependency_error(self):
        a = _tmpl("host", "A", use="B")
        b = _tmpl("host", "B", use="A")
        type_lookup = {"A": a, "B": b}
        _chain, _inherited, errors = resolve_chain(a, "host", type_lookup)
        assert any("Circular" in e or "circular" in e.lower() for e in errors)

    def test_sibling_branch_reuse(self):
        d = _tmpl("host", "D", notification_interval="60")
        b = _tmpl("host", "B", use="D")
        c = _tmpl("host", "C", use="D", check_command="check-alive")
        obj = _host(host_name="web-01", use="B,C")
        type_lookup = {"D": d, "B": b, "C": c}
        chain, inherited, errors = resolve_chain(obj, "host", type_lookup)
        assert len(errors) == 0
        assert inherited["notification_interval"]["value"] == "60"
        assert inherited["check_command"]["value"] == "check-alive"

    def test_excludes_inheritance_meta_keys(self):
        tmpl = _tmpl("host", "base", max_check_attempts="5")
        obj = _host(host_name="web-01", use="base")
        type_lookup = {"base": tmpl}
        _chain, inherited, _errors = resolve_chain(obj, "host", type_lookup)
        assert "use" not in inherited
        assert "name" not in inherited
        assert "register" not in inherited

    def test_null_cancels_in_chain(self):
        """null value cancels inheritance and is not in resolved chain."""
        tmpl = _tmpl("host", "base", notification_period="24x7", max_check_attempts="5")
        obj = _host(host_name="web-01", use="base", notification_period="null")
        type_lookup = {"base": tmpl}
        chain, inherited, errors = resolve_chain(obj, "host", type_lookup)
        assert "notification_period" not in inherited
        assert inherited["max_check_attempts"]["value"] == "5"


# ─────────────────────────────────────────────────────────────────────
# Template analysis
# ─────────────────────────────────────────────────────────────────────

class TestGetTemplateChain:
    def test_single_template(self):
        by_type = {"host": {"base": _tmpl("host", "base")}}
        chain = get_template_chain(by_type, "host", "base")
        assert chain == [("host", "base")]

    def test_deep_chain(self):
        gp = _tmpl("host", "gp")
        parent = _tmpl("host", "parent", use="gp")
        by_type = {"host": {"gp": gp, "parent": parent}}
        chain = get_template_chain(by_type, "host", "parent")
        assert ("host", "parent") in chain
        assert ("host", "gp") in chain

    def test_cycle_safe(self):
        a = _tmpl("host", "A", use="B")
        b = _tmpl("host", "B", use="A")
        by_type = {"host": {"A": a, "B": b}}
        chain = get_template_chain(by_type, "host", "A")
        assert ("host", "A") in chain
        assert ("host", "B") in chain
        assert len(chain) == 2  # No infinite duplication


class TestDetectTemplateCycles:
    def test_no_cycles(self):
        gp = _tmpl("host", "gp")
        parent = _tmpl("host", "parent", use="gp")
        by_type = {"host": {"gp": gp, "parent": parent}}
        all_tmpls = {("host", "gp"), ("host", "parent")}
        cycles = detect_template_cycles(by_type, all_tmpls)
        assert len(cycles) == 0

    def test_direct_cycle(self):
        a = _tmpl("host", "A", use="B")
        b = _tmpl("host", "B", use="A")
        by_type = {"host": {"A": a, "B": b}}
        all_tmpls = {("host", "A"), ("host", "B")}
        cycles = detect_template_cycles(by_type, all_tmpls)
        assert len(cycles) > 0

    def test_self_cycle(self):
        a = _tmpl("host", "A", use="A")
        by_type = {"host": {"A": a}}
        all_tmpls = {("host", "A")}
        cycles = detect_template_cycles(by_type, all_tmpls)
        assert len(cycles) > 0


class TestFormatCycleIssues:
    def test_deduplicates(self):
        # Same cycle reported from different starting points
        cycles = [
            [("host", "A"), ("host", "B"), ("host", "A")],
            [("host", "B"), ("host", "A"), ("host", "B")],
        ]
        issues = format_cycle_issues(cycles)
        assert len(issues) == 1
        assert "Circular" in issues[0]["message"]


class TestFindInvalidUseRefs:
    def test_finds_missing(self):
        obj = _host(host_name="web-01", use="nonexistent")
        by_type = {}
        issues, refs = find_invalid_use_refs([obj], by_type)
        assert len(issues) == 1
        assert issues[0]["template_name"] == "nonexistent"
        assert ("host", "nonexistent") in refs

    def test_valid_ref_no_issue(self):
        tmpl = _tmpl("host", "base")
        obj = _host(host_name="web-01", use="base")
        by_type = {"host": {"base": tmpl}}
        issues, refs = find_invalid_use_refs([tmpl, obj], by_type)
        assert len(issues) == 0
        assert ("host", "base") in refs


class TestFindUnusedTemplates:
    def test_unused_detected(self):
        all_tmpls = {("host", "base"), ("host", "unused")}
        referenced = {("host", "base")}
        by_type = {"host": {"base": _tmpl("host", "base"), "unused": _tmpl("host", "unused")}}
        issues = find_unused_templates(all_tmpls, referenced, by_type)
        assert len(issues) == 1
        assert issues[0]["template_name"] == "unused"

    def test_transitively_used_not_reported(self):
        gp = _tmpl("host", "gp")
        parent = _tmpl("host", "parent", use="gp")
        all_tmpls = {("host", "gp"), ("host", "parent")}
        referenced = {("host", "parent")}  # Only parent directly referenced
        by_type = {"host": {"gp": gp, "parent": parent}}
        issues = find_unused_templates(all_tmpls, referenced, by_type)
        assert len(issues) == 0  # gp is transitively used via parent
