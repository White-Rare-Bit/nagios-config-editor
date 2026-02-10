"""Health check functions extracted from api_health_check.

Each check_* function takes a context dict and returns a list of issue dicts.
The run_all_checks() orchestrator calls them all.
"""

import re

from inheritance import has_attr_in_chain, resolve_inherited_attrs
from nagios_model import NAME_FIELDS, REFERENCE_FIELDS

# Minimum common prefix length for auto-generating template names
_MIN_PREFIX_LENGTH = 3
# Minimum hosts in a service host_name list to suggest using hostgroups
_LONG_HOST_LIST_THRESHOLD = 10
# Minimum objects sharing identical attrs to suggest template consolidation
_MIN_TEMPLATE_CONSOLIDATION_GROUP = 3

# ---------------------------------------------------------------------------
# Shared utilities (used by both health checks and validation routes)
# ---------------------------------------------------------------------------

def _generate_template_name(obj_type, objects, attrs):
    """Generate a suggested template name from object patterns."""
    # Try common prefix from object names
    name_field = NAME_FIELDS.get(obj_type)
    names = []
    for obj in objects:
        n = obj.attributes.get(name_field, "") if name_field else ""
        if not n:
            n = obj.attributes.get("name", "")
        if n:
            names.append(n)

    if names:
        prefix = names[0]
        for name in names[1:]:
            while prefix and not name.startswith(prefix):
                prefix = prefix[:-1]
        if prefix and len(prefix) >= _MIN_PREFIX_LENGTH:
            # Clean trailing dashes, underscores, digits
            prefix = re.sub(r"[-_\d]+$", "", prefix)
            if len(prefix) >= _MIN_PREFIX_LENGTH:
                return f"{prefix}-{obj_type}-template"

    # Fallback: use check_command name
    if "check_command" in attrs:
        cmd = attrs["check_command"].split("!")[0]
        return f"{cmd}-{obj_type}-template"

    return f"common-{obj_type}-template"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def strip_prefix(s):
    """Strip +/! prefixes used in Nagios additive/exclusion syntax."""
    return s.strip().lstrip("+!").strip()


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_context(objects, obj_to_index, template_lookup):
    """Build lookup sets and shared data used by multiple checks."""
    ctx = {
        "objects": objects,
        "obj_to_index": obj_to_index,
        "template_lookup": template_lookup,
        "hosts": set(),
        "hostgroups": set(),
        "services": set(),
        "servicegroups": set(),
        "contacts": set(),
        "contactgroups": set(),
        "commands": set(),
        "timeperiods": set(),
        "templates": {},
        "command_arg_counts": {},
        "contact_objects": {},
        "contactgroup_objects": {},
    }

    for obj in objects:
        name = obj.get_name()
        if not name:
            continue
        is_template = obj.attributes.get("register", "1") == "0"
        if not is_template:
            _add_to_lookup_set(ctx, obj.object_type, name)
            if obj.object_type == "contact":
                ctx["contact_objects"][obj.attributes.get("contact_name", "")] = obj
        if obj.object_type == "contactgroup":
            ctx["contactgroup_objects"][obj.attributes.get("contactgroup_name", "")] = obj
        if "name" in obj.attributes:
            ctx["templates"].setdefault(obj.object_type, set()).add(obj.attributes["name"])

    # Build command arg count map
    for obj in objects:
        if obj.object_type == "command":
            cmd_name = obj.attributes.get("command_name", "")
            cmd_line = obj.attributes.get("command_line", "")
            arg_matches = re.findall(r"\$ARG(\d+)\$", cmd_line)
            max_arg = max((int(n) for n in arg_matches), default=0)
            ctx["command_arg_counts"][cmd_name] = max_arg

    return ctx


def _add_to_lookup_set(ctx, object_type, name):
    """Add a name to the appropriate lookup set."""
    lookup_map = {
        "host": "hosts", "hostgroup": "hostgroups",
        "service": "services", "servicegroup": "servicegroups",
        "contact": "contacts", "contactgroup": "contactgroups",
        "command": "commands", "timeperiod": "timeperiods",
    }
    key = lookup_map.get(object_type)
    if key:
        ctx[key].add(name)


# ---------------------------------------------------------------------------
# Check 1: Orphan services (referencing non-existent hosts/hostgroups)
# ---------------------------------------------------------------------------

def check_orphan_services(ctx):
    """Check 1/1b: Services referencing non-existent hosts or hostgroups."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    hosts = ctx["hosts"]
    hostgroups = ctx["hostgroups"]

    for obj in ctx["objects"]:
        if obj.object_type != "service":
            continue
        obj_name = obj.get_name() or obj.get_display_name()

        # 1a: Check host_name references
        host_ref = obj.attributes.get("host_name", "")
        if host_ref and host_ref != "*":
            for h in host_ref.split(","):
                h = h.strip()
                if h.startswith("!"):
                    continue
                if h and h not in hosts:
                    issues.append({
                        "type": "orphan_service",
                        "severity": "error",
                        "object": obj_name,
                        "object_type": obj.object_type,
                        "file": obj.source_file,
                        "global_index": obj_to_index.get(id(obj)),
                        "message": f"Service references non-existent host: {h}",
                    })

        # 1b: Check hostgroup_name references
        hostgroup_ref = obj.attributes.get("hostgroup_name", "")
        if hostgroup_ref:
            for hg in hostgroup_ref.split(","):
                hg = strip_prefix(hg)
                if hg and hg not in hostgroups:
                    issues.append({
                        "type": "missing_hostgroup",
                        "severity": "error",
                        "object": obj_name,
                        "object_type": obj.object_type,
                        "file": obj.source_file,
                        "global_index": obj_to_index.get(id(obj)),
                        "message": f"Service references non-existent hostgroup: {hg}",
                    })
    return issues


# ---------------------------------------------------------------------------
# Check 1c: Missing parent hosts
# ---------------------------------------------------------------------------

def check_missing_parents(ctx):
    """Check 1c: Hosts referencing non-existent parent hosts."""
    issues = []
    hosts = ctx["hosts"]
    missing_parents = {}

    for obj in ctx["objects"]:
        if obj.object_type != "host":
            continue
        if obj.attributes.get("register", "1") == "0":
            continue
        obj_name = obj.get_name() or obj.get_display_name()
        parents_ref = obj.attributes.get("parents", "")
        if parents_ref:
            for parent in parents_ref.split(","):
                parent = parent.strip()
                if parent and parent not in hosts:
                    missing_parents.setdefault(parent, []).append(
                        (obj_name, obj.source_file),
                    )

    for parent_name, host_refs in missing_parents.items():
        host_names = [h for h, _ in host_refs]
        first_file = host_refs[0][1]
        if len(host_names) <= 3:  # noqa: PLR2004
            host_list = ", ".join(host_names)
        else:
            host_list = f'{", ".join(host_names[:3])} and {len(host_names) - 3} more'
        issues.append({
            "type": "missing_parent",
            "severity": "warning",
            "object": parent_name,
            "object_type": "host",
            "file": first_file,
            "global_index": None,
            "message": f"Non-existent parent host referenced by: {host_list}",
        })
    return issues


# ---------------------------------------------------------------------------
# Check 2: Missing templates
# ---------------------------------------------------------------------------

def check_missing_templates(ctx):
    """Check 2: Objects referencing undefined templates."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    templates = ctx["templates"]

    for obj in ctx["objects"]:
        if "use" not in obj.attributes:
            continue
        obj_name = obj.get_name() or obj.get_display_name()
        template_refs = [t.strip() for t in obj.attributes["use"].split(",")]
        type_templates = templates.get(obj.object_type, set())
        for t in template_refs:
            if t and t not in type_templates:
                issues.append({
                    "type": "missing_template",
                    "severity": "error",
                    "object": obj_name,
                    "object_type": obj.object_type,
                    "file": obj.source_file,
                    "global_index": obj_to_index.get(id(obj)),
                    "message": f"References undefined {obj.object_type} template: {t}",
                })
    return issues


# ---------------------------------------------------------------------------
# Check 3: Missing commands
# ---------------------------------------------------------------------------

def check_missing_commands(ctx):
    """Check 3: Objects referencing non-existent commands."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    commands = ctx["commands"]

    for obj in ctx["objects"]:
        obj_name = obj.get_name() or obj.get_display_name()

        # Single-command fields
        for cmd_field in ["check_command", "event_handler"]:
            if cmd_field in obj.attributes:
                cmd_ref = obj.attributes[cmd_field].split("!")[0].strip()
                if cmd_ref and cmd_ref not in commands:
                    issues.append({
                        "type": "missing_command",
                        "severity": "error",
                        "object": obj_name,
                        "object_type": obj.object_type,
                        "file": obj.source_file,
                        "global_index": obj_to_index.get(id(obj)),
                        "message": f"References non-existent command: {cmd_ref}",
                    })

        # Comma-separated notification command fields
        for cmd_field in ["host_notification_commands", "service_notification_commands"]:
            if cmd_field in obj.attributes:
                for cmd_full in obj.attributes[cmd_field].split(","):
                    cmd_ref = cmd_full.strip().split("!")[0]
                    if cmd_ref and cmd_ref not in commands:
                        issues.append({
                            "type": "missing_command",
                            "severity": "error",
                            "object": obj_name,
                            "object_type": obj.object_type,
                            "file": obj.source_file,
                            "global_index": obj_to_index.get(id(obj)),
                            "message": f"References non-existent command: {cmd_ref}",
                        })
    return issues


# ---------------------------------------------------------------------------
# Check 4: Missing timeperiods
# ---------------------------------------------------------------------------

def check_missing_timeperiods(ctx):
    """Check 4: Objects referencing non-existent timeperiods."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    timeperiods = ctx["timeperiods"]

    for obj in ctx["objects"]:
        obj_name = obj.get_name() or obj.get_display_name()
        for tp_field in ["check_period", "notification_period"]:
            if tp_field in obj.attributes:
                tp_ref = obj.attributes[tp_field]
                if tp_ref and tp_ref not in timeperiods:
                    issues.append({
                        "type": "missing_timeperiod",
                        "severity": "warning",
                        "object": obj_name,
                        "object_type": obj.object_type,
                        "file": obj.source_file,
                        "global_index": obj_to_index.get(id(obj)),
                        "message": f"References non-existent timeperiod: {tp_ref}",
                    })
    return issues


# ---------------------------------------------------------------------------
# Check 5: Missing contacts/contactgroups
# ---------------------------------------------------------------------------

def check_missing_contacts(ctx):
    """Check 5: Objects referencing non-existent contacts or contactgroups."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    contacts = ctx["contacts"]
    contactgroups = ctx["contactgroups"]

    for obj in ctx["objects"]:
        obj_name = obj.get_name() or obj.get_display_name()

        if "contacts" in obj.attributes:
            for c in obj.attributes["contacts"].split(","):
                c = strip_prefix(c)
                if c and c not in contacts:
                    issues.append({
                        "type": "missing_contact",
                        "severity": "warning",
                        "object": obj_name,
                        "object_type": obj.object_type,
                        "file": obj.source_file,
                        "global_index": obj_to_index.get(id(obj)),
                        "message": f"References non-existent contact: {c}",
                    })

        if "contact_groups" in obj.attributes:
            for cg in obj.attributes["contact_groups"].split(","):
                cg = strip_prefix(cg)
                if cg and cg not in contactgroups:
                    issues.append({
                        "type": "missing_contactgroup",
                        "severity": "warning",
                        "object": obj_name,
                        "object_type": obj.object_type,
                        "file": obj.source_file,
                        "global_index": obj_to_index.get(id(obj)),
                        "message": f"References non-existent contact group: {cg}",
                    })
    return issues


# ---------------------------------------------------------------------------
# Check 6: Missing hostgroups/servicegroups
# ---------------------------------------------------------------------------

def check_missing_groups(ctx):
    """Check 6: Objects referencing non-existent hostgroups or servicegroups."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    hostgroups = ctx["hostgroups"]
    servicegroups = ctx["servicegroups"]

    for obj in ctx["objects"]:
        obj_name = obj.get_name() or obj.get_display_name()

        if "hostgroups" in obj.attributes:
            for hg in obj.attributes["hostgroups"].split(","):
                hg = strip_prefix(hg)
                if hg and hg not in hostgroups:
                    issues.append({
                        "type": "missing_hostgroup",
                        "severity": "warning",
                        "object": obj_name,
                        "object_type": obj.object_type,
                        "file": obj.source_file,
                        "global_index": obj_to_index.get(id(obj)),
                        "message": f"References non-existent hostgroup: {hg}",
                    })

        if "servicegroups" in obj.attributes:
            for sg in obj.attributes["servicegroups"].split(","):
                sg = strip_prefix(sg)
                if sg and sg not in servicegroups:
                    issues.append({
                        "type": "missing_servicegroup",
                        "severity": "warning",
                        "object": obj_name,
                        "object_type": obj.object_type,
                        "file": obj.source_file,
                        "global_index": obj_to_index.get(id(obj)),
                        "message": f"References non-existent servicegroup: {sg}",
                    })
    return issues


# ---------------------------------------------------------------------------
# Check 7: Empty groups
# ---------------------------------------------------------------------------

def check_empty_groups(ctx):
    """Check 7: Groups with no members that are not referenced."""
    issues = []
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]

    for obj in objects:
        if obj.object_type not in ["hostgroup", "servicegroup", "contactgroup"]:
            continue
        has_members = "members" in obj.attributes
        if obj.object_type == "hostgroup":
            has_members = has_members or "hostgroup_members" in obj.attributes
        elif obj.object_type == "servicegroup":
            has_members = has_members or "servicegroup_members" in obj.attributes
        elif obj.object_type == "contactgroup":
            has_members = has_members or "contactgroup_members" in obj.attributes

        if has_members:
            continue

        group_name = obj.get_name()
        ref_fields = _get_group_ref_fields(obj.object_type)
        is_used = _is_group_referenced(obj, group_name, ref_fields, objects)

        if not is_used:
            issues.append({
                "type": "empty_group",
                "severity": "warning",
                "object": obj.get_name() or obj.get_display_name(),
                "object_type": obj.object_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": "Group has no members and is not referenced",
            })
    return issues


def _get_group_ref_fields(object_type):
    """Return fields that can reference a given group type."""
    if object_type == "hostgroup":
        return ["hostgroups", "hostgroup_name", "hostgroup_members"]
    if object_type == "servicegroup":
        return ["servicegroups", "servicegroup_name", "servicegroup_members"]
    return ["contact_groups", "contactgroup_name", "contactgroup_members"]


def _is_group_referenced(obj, group_name, ref_fields, objects):
    """Check if a group is referenced by any other object."""
    for other_obj in objects:
        if other_obj is obj:
            continue
        for field in ref_fields:
            if field in other_obj.attributes:
                referenced = [strip_prefix(g) for g in other_obj.attributes[field].split(",")]
                if group_name in referenced:
                    return True
    return False


# ---------------------------------------------------------------------------
# Check 8: Unused templates
# ---------------------------------------------------------------------------

def check_unused_templates(ctx):
    """Check 8: Templates not used by any object."""
    issues = []
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]
    templates = ctx["templates"]

    for obj_type, tmpl_names in templates.items():
        for tmpl_name in tmpl_names:
            if _is_template_used(tmpl_name, obj_type, objects):
                continue
            tmpl_obj = _find_template_object(tmpl_name, obj_type, objects)
            if tmpl_obj:
                issues.append({
                    "type": "unused_template",
                    "severity": "warning",
                    "object": tmpl_name,
                    "object_type": obj_type,
                    "file": tmpl_obj.source_file,
                    "global_index": obj_to_index.get(id(tmpl_obj)),
                    "message": f"Template is not used by any {obj_type}",
                })
    return issues


def _is_template_used(tmpl_name, obj_type, objects):
    """Check if a template is used by any object of the given type."""
    for obj in objects:
        if (obj.object_type == obj_type and "use" in obj.attributes and
                tmpl_name in [t.strip() for t in obj.attributes["use"].split(",")]):
            return True
    return False


def _find_template_object(tmpl_name, obj_type, objects):
    """Find the template object by name and type."""
    for obj in objects:
        if obj.object_type == obj_type and obj.attributes.get("name") == tmpl_name:
            return obj
    return None


# ---------------------------------------------------------------------------
# Check 9: Duplicate dependencies
# ---------------------------------------------------------------------------

def check_duplicate_dependencies(ctx):
    """Check 9: Duplicate host/service dependency definitions."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    dep_signatures = {}
    dep_fields = [
        "dependent_host_name", "dependent_hostgroup_name",
        "dependent_service_description", "host_name",
        "hostgroup_name", "service_description",
    ]

    for obj in ctx["objects"]:
        if obj.object_type not in ["hostdependency", "servicedependency"]:
            continue
        sig_parts = []
        for field in dep_fields:
            val = obj.attributes.get(field, "")
            if val:
                sig_parts.append(f"{field}={val}")
        sig = "|".join(sorted(sig_parts))

        if sig in dep_signatures:
            orig = dep_signatures[sig]
            issues.append({
                "type": "duplicate_dependency",
                "severity": "warning",
                "object": obj.get_name() or obj.get_display_name(),
                "object_type": obj.object_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": f'Duplicate dependency rule (also defined in {orig["file"]})',
            })
        else:
            dep_signatures[sig] = {"file": obj.source_file, "obj": obj}
    return issues


# ---------------------------------------------------------------------------
# Check 10: Hosts without services
# ---------------------------------------------------------------------------

def check_hosts_without_services(ctx):
    """Check 10: Non-template hosts that have no services assigned."""
    issues = []
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]
    hosts = ctx["hosts"]

    host_to_hostgroups = _build_host_to_hostgroups(objects)
    hostgroup_to_hosts = _build_hostgroup_to_hosts(objects)
    hosts_with_services = _find_hosts_with_services(
        objects, hosts, host_to_hostgroups, hostgroup_to_hosts,
    )

    for obj in objects:
        if obj.object_type != "host" or obj.attributes.get("register", "1") == "0":
            continue
        hname = obj.get_name()
        if hname and hname not in hosts_with_services:
            issues.append({
                "type": "host_without_services",
                "severity": "warning",
                "object": hname,
                "object_type": "host",
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": "Host has no services assigned (directly or via hostgroup)",
            })
    return issues


def _build_host_to_hostgroups(objects):
    """Map host names to their hostgroup memberships."""
    host_to_hg = {}
    for obj in objects:
        if obj.object_type == "host" and obj.attributes.get("register", "1") != "0":
            hname = obj.get_name()
            if hname:
                hgs = obj.attributes.get("hostgroups", "")
                if hgs:
                    host_to_hg[hname] = {
                        g.strip().lstrip("+").strip()
                        for g in hgs.split(",") if g.strip()
                    }
    return host_to_hg


def _build_hostgroup_to_hosts(objects):
    """Map hostgroup names to their explicit members."""
    hg_to_hosts = {}
    for obj in objects:
        if obj.object_type == "hostgroup":
            gname = obj.get_name()
            if gname and "members" in obj.attributes:
                hg_to_hosts[gname] = {
                    h.strip() for h in obj.attributes["members"].split(",") if h.strip()
                }
    return hg_to_hosts


def _find_hosts_with_services(objects, hosts, host_to_hg, hg_to_hosts):
    """Find all hosts that have at least one service assigned."""
    hosts_with_services = set()
    for obj in objects:
        if obj.object_type != "service" or obj.attributes.get("register", "1") == "0":
            continue
        host_ref = obj.attributes.get("host_name", "")
        if host_ref == "*":
            return hosts.copy()
        if host_ref:
            for h in host_ref.split(","):
                h = h.strip()
                if h and not h.startswith("!"):
                    hosts_with_services.add(h)
        hg_ref = obj.attributes.get("hostgroup_name", "")
        if hg_ref:
            _add_hosts_from_hostgroups(hg_ref, host_to_hg, hg_to_hosts, hosts_with_services)
    return hosts_with_services


def _add_hosts_from_hostgroups(hg_ref, host_to_hg, hg_to_hosts, result):
    """Add hosts to result set based on hostgroup references."""
    for hg in hg_ref.split(","):
        hg = strip_prefix(hg)
        if not hg:
            continue
        for hname, hg_set in host_to_hg.items():
            if hg in hg_set:
                result.add(hname)
        if hg in hg_to_hosts:
            result.update(hg_to_hosts[hg])


# ---------------------------------------------------------------------------
# Check 11: Services missing check_command
# ---------------------------------------------------------------------------

def check_missing_check_command(ctx):
    """Check 11: Services missing check_command (including via inheritance)."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    template_lookup = ctx["template_lookup"]

    for obj in ctx["objects"]:
        if obj.object_type != "service":
            continue
        if obj.attributes.get("register", "1") == "0":
            continue
        resolved = resolve_inherited_attrs(obj, template_lookup)
        if "check_command" not in resolved:
            obj_name = obj.get_name() or "unnamed"
            host = resolved.get("host_name", resolved.get("hostgroup_name", ""))
            issues.append({
                "type": "missing_check_command",
                "severity": "error",
                "object": f"{obj_name} on {host}" if host else obj_name,
                "object_type": "service",
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": "Service has no check_command (directly or through template inheritance)",
            })
    return issues


# ---------------------------------------------------------------------------
# Check 12: Command argument count mismatches
# ---------------------------------------------------------------------------

def check_command_arg_mismatch(ctx):
    """Check 12: Services/hosts with wrong number of command arguments."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    template_lookup = ctx["template_lookup"]
    command_arg_counts = ctx["command_arg_counts"]

    for obj in ctx["objects"]:
        if obj.object_type not in ("service", "host"):
            continue
        if obj.attributes.get("register", "1") == "0":
            continue
        resolved = resolve_inherited_attrs(obj, template_lookup)
        check_cmd = resolved.get("check_command", "")
        if not check_cmd:
            continue
        parts = check_cmd.split("!")
        cmd_name = parts[0].strip()
        provided_args = len(parts) - 1
        expected_args = command_arg_counts.get(cmd_name)
        if expected_args is None:
            continue
        if provided_args != expected_args:
            obj_name = obj.get_name() or "unnamed"
            issues.append({
                "type": "command_arg_mismatch",
                "severity": "warning",
                "object": obj_name,
                "object_type": obj.object_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": f"Command {cmd_name} expects {expected_args} arg(s) but {provided_args} provided",
            })
    return issues


# ---------------------------------------------------------------------------
# Check 13: Template attribute conflicts in multi-template inheritance
# ---------------------------------------------------------------------------

def check_template_conflicts(ctx):
    """Check 13: Conflicting attributes from multiple templates."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    template_lookup = ctx["template_lookup"]

    for obj in ctx["objects"]:
        if obj.attributes.get("register", "1") == "0":
            continue
        use_value = obj.attributes.get("use", "")
        if not use_value:
            continue
        tmpl_names = [t.strip() for t in use_value.split(",") if t.strip()]
        if len(tmpl_names) < 2:  # noqa: PLR2004
            continue
        conflicts = _find_template_conflicts(obj, tmpl_names, template_lookup)
        if conflicts:
            obj_name = obj.get_name() or "unnamed"
            issues.append({
                "type": "template_conflict",
                "severity": "warning",
                "object": obj_name,
                "object_type": obj.object_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": f'Template inheritance conflict (first template wins): {"; ".join(conflicts[:3])}',
            })
    return issues


def _find_template_conflicts(obj, tmpl_names, template_lookup):
    """Find attribute conflicts between multiple templates."""
    tmpl_attr_sets = []
    for tmpl_name in tmpl_names:
        tmpl = template_lookup.get((obj.object_type, tmpl_name))
        if tmpl:
            resolved_tmpl = resolve_inherited_attrs(tmpl, template_lookup)
            cleaned = {k: v for k, v in resolved_tmpl.items()
                       if k not in ("use", "name", "register")}
            tmpl_attr_sets.append((tmpl_name, cleaned))
    if len(tmpl_attr_sets) < 2:  # noqa: PLR2004
        return []

    conflicts = []
    seen_attrs = {}
    for tmpl_name, attrs in tmpl_attr_sets:
        for attr, value in attrs.items():
            if attr in obj.attributes:
                continue
            if attr in seen_attrs:
                prev_value, prev_tmpl = seen_attrs[attr]
                if value != prev_value:
                    conflicts.append(
                        f"{attr} differs: {prev_tmpl}={prev_value}, {tmpl_name}={value}",
                    )
            else:
                seen_attrs[attr] = (value, tmpl_name)
    return conflicts


# ---------------------------------------------------------------------------
# Check 14: Notification chain validation
# ---------------------------------------------------------------------------

def check_notification_chain(ctx):
    """Check 14: Contact notification chain gaps."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    template_lookup = ctx["template_lookup"]
    contact_objects = ctx["contact_objects"]

    for cname, contact_obj in contact_objects.items():
        if not cname:
            continue
        all_problems = []
        for check_type in ("host", "service"):
            all_problems.extend(
                _check_contact_notification(cname, check_type, contact_objects, template_lookup),
            )
        if all_problems:
            issues.append({
                "type": "notification_gap",
                "severity": "warning",
                "object": cname,
                "object_type": "contact",
                "file": contact_obj.source_file,
                "global_index": obj_to_index.get(id(contact_obj)),
                "message": f'Notification chain broken: {"; ".join(all_problems)}',
            })
    return issues


def _check_contact_notification(contact_name, check_type, contact_objects, template_lookup):
    """Check if a contact can deliver notifications for host or service."""
    problems = []
    contact_obj = contact_objects.get(contact_name)
    if not contact_obj:
        return []
    resolved_contact = resolve_inherited_attrs(contact_obj, template_lookup)
    cmd_field = f"{check_type}_notification_commands"
    period_field = f"{check_type}_notification_period"
    if cmd_field not in resolved_contact:
        problems.append(f"{contact_name} has no {cmd_field}")
    if period_field not in resolved_contact:
        problems.append(f"{contact_name} has no {period_field}")
    return problems


# ---------------------------------------------------------------------------
# Check 14b: Service/host-side notification reachability
# ---------------------------------------------------------------------------

def _expand_contacts(resolved_attrs, ctx):
    """Expand contacts and contact_groups to a set of contact names."""
    names = set()
    for c in resolved_attrs.get("contacts", "").split(","):
        c = c.strip().lstrip("+!")
        if c:
            names.add(c)
    for cg_name in resolved_attrs.get("contact_groups", "").split(","):
        cg_name = cg_name.strip().lstrip("+!")
        cg_obj = ctx["contactgroup_objects"].get(cg_name)
        if cg_obj and "members" in cg_obj.attributes:
            for m in cg_obj.attributes["members"].split(","):
                m = m.strip()
                if m:
                    names.add(m)
    return names


def check_service_host_notification_reachability(ctx):
    """Check 14b: Services/hosts with no reachable notification path."""
    issues = []
    obj_to_index = ctx["obj_to_index"]
    template_lookup = ctx["template_lookup"]
    contact_objects = ctx["contact_objects"]

    for obj in ctx["objects"]:
        if obj.object_type not in ("host", "service"):
            continue
        if obj.attributes.get("register", "1") == "0":
            continue

        resolved = resolve_inherited_attrs(obj, template_lookup)
        contact_names = _expand_contacts(resolved, ctx)

        if not contact_names:
            continue

        check_type = obj.object_type if obj.object_type == "host" else "service"
        broken = []
        for cname in contact_names:
            contact_obj = contact_objects.get(cname)
            if not contact_obj:
                broken.append(cname)
                continue
            resolved_contact = resolve_inherited_attrs(contact_obj, template_lookup)
            cmd_field = f"{check_type}_notification_commands"
            period_field = f"{check_type}_notification_period"
            if cmd_field not in resolved_contact or period_field not in resolved_contact:
                broken.append(cname)

        if not broken:
            continue

        obj_name = obj.get_name() or obj.get_display_name()
        total = len(contact_names)
        n_broken = len(broken)

        if n_broken == total:
            issues.append({
                "type": "notification_unreachable",
                "severity": "error",
                "object": obj_name,
                "object_type": obj.object_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": f"All {total} contact(s) have broken notification chains",
            })
        else:
            issues.append({
                "type": "notification_unreachable",
                "severity": "warning",
                "object": obj_name,
                "object_type": obj.object_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": f"{n_broken} of {total} contacts have broken notification chains",
            })
    return issues


# ---------------------------------------------------------------------------
# Check 15: Unused commands
# ---------------------------------------------------------------------------

def check_unused_commands(ctx):
    """Check 15: Commands not referenced by any object."""
    issues = []
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]
    used_commands = _collect_used_commands(objects)

    for obj in objects:
        if obj.object_type == "command":
            cmd_name = obj.attributes.get("command_name", "")
            if cmd_name and cmd_name not in used_commands:
                issues.append({
                    "type": "unused_command",
                    "severity": "warning",
                    "object": cmd_name,
                    "object_type": "command",
                    "file": obj.source_file,
                    "global_index": obj_to_index.get(id(obj)),
                    "message": "Command is not referenced by any object",
                })
    return issues


def _collect_used_commands(objects):
    """Collect the set of all referenced command names."""
    used = set()
    for obj in objects:
        for cmd_field in ["check_command", "event_handler",
                          "global_host_event_handler", "global_service_event_handler"]:
            if cmd_field in obj.attributes:
                cmd_ref = obj.attributes[cmd_field].split("!")[0].strip()
                if cmd_ref:
                    used.add(cmd_ref)
        for cmd_field in ["host_notification_commands", "service_notification_commands"]:
            if cmd_field in obj.attributes:
                for cmd_full in obj.attributes[cmd_field].split(","):
                    cmd_ref = cmd_full.strip().split("!")[0].strip()
                    if cmd_ref:
                        used.add(cmd_ref)
    return used


# ---------------------------------------------------------------------------
# Check 16: Unused contacts
# ---------------------------------------------------------------------------

def check_unused_contacts(ctx):
    """Check 16: Contacts not referenced by any non-template object or contactgroup."""
    issues = []
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]
    used_contacts = _collect_used_contacts(objects)

    for obj in objects:
        if obj.object_type == "contact" and obj.attributes.get("register", "1") != "0":
            contact_name = obj.attributes.get("contact_name", "")
            if contact_name and contact_name not in used_contacts:
                issues.append({
                    "type": "unused_contact",
                    "severity": "warning",
                    "object": contact_name,
                    "object_type": "contact",
                    "file": obj.source_file,
                    "global_index": obj_to_index.get(id(obj)),
                    "message": "Contact is not referenced by any object",
                })
    return issues


def _collect_used_contacts(objects):
    """Collect the set of all referenced contact names."""
    used = set()
    for obj in objects:
        if obj.attributes.get("register", "1") == "0":
            continue
        if "contacts" in obj.attributes:
            for c in obj.attributes["contacts"].split(","):
                c = strip_prefix(c)
                if c:
                    used.add(c)
    for obj in objects:
        if obj.object_type == "contactgroup" and "members" in obj.attributes:
            for m in obj.attributes["members"].split(","):
                m = strip_prefix(m)
                if m:
                    used.add(m)
    return used


# ---------------------------------------------------------------------------
# Check 17: Unused contactgroups
# ---------------------------------------------------------------------------

def check_unused_contactgroups(ctx):
    """Check 17: Contact groups not referenced by any object."""
    issues = []
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]
    used_contactgroups = _collect_used_contactgroups(objects)

    for obj in objects:
        if obj.object_type == "contactgroup":
            cg_name = obj.attributes.get("contactgroup_name", "")
            if cg_name and cg_name not in used_contactgroups:
                issues.append({
                    "type": "unused_contactgroup",
                    "severity": "warning",
                    "object": cg_name,
                    "object_type": "contactgroup",
                    "file": obj.source_file,
                    "global_index": obj_to_index.get(id(obj)),
                    "message": "Contact group is not referenced by any object",
                })
    return issues


def _collect_used_contactgroups(objects):
    """Collect the set of all referenced contactgroup names."""
    used = set()
    for obj in objects:
        _collect_cg_refs_from_object(obj, used)
    return used


def _collect_cg_refs_from_object(obj, used):
    """Collect contactgroup references from a single object."""
    is_template = obj.attributes.get("register", "1") == "0"
    if not is_template and "contact_groups" in obj.attributes:
        for cg in obj.attributes["contact_groups"].split(","):
            cg = strip_prefix(cg)
            if cg:
                used.add(cg)
    if obj.object_type == "contactgroup" and "contactgroup_members" in obj.attributes:
        for cg in obj.attributes["contactgroup_members"].split(","):
            cg = strip_prefix(cg)
            if cg:
                used.add(cg)
    if obj.object_type == "contact" and "contactgroups" in obj.attributes:
        for cg in obj.attributes["contactgroups"].split(","):
            cg = strip_prefix(cg)
            if cg:
                used.add(cg)


# ---------------------------------------------------------------------------
# Check 18: Unused timeperiods
# ---------------------------------------------------------------------------

def check_unused_timeperiods(ctx):
    """Check 18: Time periods not referenced by any non-template object."""
    issues = []
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]
    used_timeperiods = _collect_used_timeperiods(objects)

    for obj in objects:
        if obj.object_type == "timeperiod" and obj.attributes.get("register", "1") != "0":
            tp_name = obj.attributes.get("timeperiod_name", "")
            if tp_name and tp_name not in used_timeperiods:
                issues.append({
                    "type": "unused_timeperiod",
                    "severity": "warning",
                    "object": tp_name,
                    "object_type": "timeperiod",
                    "file": obj.source_file,
                    "global_index": obj_to_index.get(id(obj)),
                    "message": "Time period is not referenced by any object",
                })
    return issues


def _collect_used_timeperiods(objects):
    """Collect the set of all referenced timeperiod names."""
    tp_fields_single = [
        "check_period", "notification_period",
        "host_notification_period", "service_notification_period",
        "dependency_period", "escalation_period",
    ]
    used = set()
    for obj in objects:
        if obj.attributes.get("register", "1") == "0":
            continue
        for tp_field in tp_fields_single:
            if tp_field in obj.attributes:
                tp_ref = strip_prefix(obj.attributes[tp_field])
                if tp_ref:
                    used.add(tp_ref)
        if "exclude" in obj.attributes:
            for tp in obj.attributes["exclude"].split(","):
                tp = strip_prefix(tp)
                if tp:
                    used.add(tp)
    return used


# ---------------------------------------------------------------------------
# Check 19: Duplicate object definitions
# ---------------------------------------------------------------------------

def check_duplicate_objects(ctx):
    """Check 19: Non-template objects with duplicate names."""
    issues = []
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]

    # Object types where identity is scoped by host (not just name)
    host_scoped_types = {"service", "serviceescalation", "servicedependency"}

    identity_map = {}
    for obj in objects:
        if obj.attributes.get("register", "1") == "0":
            continue
        name = obj.get_name()
        if not name:
            continue
        key = f"{obj.object_type}:{name}"
        # Services are unique per (host, service_description), not just service_description
        if obj.object_type in host_scoped_types:
            host_scope = obj.attributes.get("host_name") or obj.attributes.get("hostgroup_name", "")
            key = f"{obj.object_type}:{host_scope}:{name}"
        identity_map.setdefault(key, []).append(obj)

    for key, objs in identity_map.items():
        if len(objs) <= 1:
            continue
        obj_type, identity = key.split(":", 1)
        related_objects = [
            {
                "global_index": obj_to_index.get(id(o)),
                "file": o.source_file,
                "line": o.line_number,
            }
            for o in objs
        ]
        files = [o.source_file.rsplit("/", 1)[-1] for o in objs]
        for obj in objs:
            other_files = [f for f, o in zip(files, objs, strict=True) if o is not obj]
            issues.append({
                "type": "duplicate",
                "severity": "error",
                "object": identity,
                "object_type": obj_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "related_objects": related_objects,
                "message": f'Duplicate {obj_type} definition (also in {", ".join(other_files)})',
            })
    return issues


# ---------------------------------------------------------------------------
# Check 20: Orphan detection
# ---------------------------------------------------------------------------

def detect_orphans(objects, template_lookup):
    """Shared orphan detection logic used by both health check and analysis endpoint.

    Returns:
        tuple: (orphan_indices, by_type, orphan_objects)
            - orphan_indices: list of global indices of orphan objects
            - by_type: dict mapping object_type -> count
            - orphan_objects: list of (global_index, obj) tuples for orphan objects

    """
    command_fields = {f for f, t in REFERENCE_FIELDS.items() if t == "command"}
    referenced_names = {
        "host": set(), "hostgroup": set(), "service": set(),
        "servicegroup": set(), "contact": set(), "contactgroup": set(),
        "command": set(), "timeperiod": set(),
    }

    for obj in objects:
        _collect_references(obj, referenced_names, command_fields, template_lookup)

    orphan_indices = []
    by_type = {}
    orphan_objects = []
    for global_idx, obj in enumerate(objects):
        if obj.attributes.get("register", "1") == "0":
            continue
        obj_name = obj.get_name()
        refs = referenced_names.get(obj.object_type)
        if refs is None:
            continue
        attr_name = obj.attributes.get("name")
        is_referenced = ((obj_name and obj_name in refs) or
                         (attr_name and attr_name in refs))
        if not is_referenced:
            orphan_indices.append(global_idx)
            by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1
            orphan_objects.append((global_idx, obj))

    return orphan_indices, by_type, orphan_objects


def check_orphan_objects(ctx):
    """Check 20: Non-template objects not referenced by any other object."""
    objects = ctx["objects"]
    obj_to_index = ctx["obj_to_index"]
    template_lookup = ctx["template_lookup"]

    _, _, orphan_objects = detect_orphans(objects, template_lookup)

    issues = []
    for _global_idx, obj in orphan_objects:
        obj_name = obj.get_name()
        issues.append({
            "type": "orphan",
            "severity": "info",
            "object": obj_name or obj.get_display_name(),
            "object_type": obj.object_type,
            "file": obj.source_file,
            "global_index": obj_to_index.get(id(obj)),
            "message": f"{obj.object_type} is not referenced by any other object",
        })
    return issues


def _collect_references(obj, referenced_names, command_fields, template_lookup):
    """Collect all outgoing references from an object into referenced_names sets."""
    _collect_field_references(obj, referenced_names, command_fields)
    _collect_auto_references(obj, referenced_names, template_lookup)


def _collect_field_references(obj, referenced_names, command_fields):
    """Collect explicit field references from an object."""
    attrs = obj.attributes
    own_name_field = NAME_FIELDS.get(obj.object_type)

    for ref_field, target_type in REFERENCE_FIELDS.items():
        if ref_field not in attrs:
            continue
        value = attrs[ref_field]
        resolved_type = _resolve_ref_type(ref_field, target_type, obj.object_type)
        if resolved_type is None or resolved_type not in referenced_names:
            continue
        if ref_field == own_name_field:
            continue
        for part in value.split(","):
            part = strip_prefix(part)
            if not part:
                continue
            if ref_field in command_fields:
                part = part.split("!")[0].strip()
            if part:
                referenced_names[resolved_type].add(part)


def _collect_auto_references(obj, referenced_names, template_lookup):
    """Collect auto-references (objects that reference themselves via membership)."""
    if obj.object_type == "host" and has_attr_in_chain(obj, "hostgroups", template_lookup):
        host_name_val = obj.get_name()
        if host_name_val:
            referenced_names["host"].add(host_name_val.strip())

    if (obj.object_type == "service" and
            (has_attr_in_chain(obj, "host_name", template_lookup) or
             has_attr_in_chain(obj, "hostgroup_name", template_lookup))):
        svc_name = obj.get_name()
        if svc_name:
            referenced_names["service"].add(svc_name.strip())

    if obj.object_type == "service" and has_attr_in_chain(obj, "servicegroups", template_lookup):
        svc_name = obj.get_name()
        if svc_name:
            referenced_names["service"].add(svc_name.strip())


def _resolve_ref_type(ref_field, target_type, obj_type):
    """Resolve the target type for a reference field."""
    if ref_field == "use":
        return obj_type
    if ref_field == "members":
        member_type_map = {
            "hostgroup": "host",
            "contactgroup": "contact",
            "servicegroup": "service",
        }
        return member_type_map.get(obj_type)
    return target_type


# ---------------------------------------------------------------------------
# Check 21: Notification gap detection for hosts/services
# ---------------------------------------------------------------------------

def check_missing_contacts_on_objects(ctx):
    """Check 21: Hosts/services with no contacts, contact_groups, or template."""
    issues = []
    obj_to_index = ctx["obj_to_index"]

    for obj in ctx["objects"]:
        if obj.object_type not in ("host", "service"):
            continue
        if obj.attributes.get("register", "1") == "0":
            continue
        has_contacts = "contacts" in obj.attributes
        has_contact_groups = "contact_groups" in obj.attributes
        has_use = "use" in obj.attributes
        if not has_contacts and not has_contact_groups and not has_use:
            obj_name = obj.get_name() or obj.get_display_name()
            issues.append({
                "type": "missing_contacts",
                "severity": "warning",
                "object": obj_name,
                "object_type": obj.object_type,
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "message": f"{obj.object_type.title()} has no contacts, contact_groups, or template (use) defined",
            })
    return issues


# ---------------------------------------------------------------------------
# Check 22: Long host list detection
# ---------------------------------------------------------------------------

def check_long_host_lists(ctx):
    """Check 22: Services with 10+ hosts in host_name list."""
    issues = []
    obj_to_index = ctx["obj_to_index"]

    for obj in ctx["objects"]:
        if obj.object_type != "service":
            continue
        if obj.attributes.get("register", "1") == "0":
            continue
        host_ref = obj.attributes.get("host_name", "")
        if not host_ref:
            continue
        host_list = [h.strip() for h in host_ref.split(",") if h.strip()]
        host_count = len(host_list)
        if host_count >= _LONG_HOST_LIST_THRESHOLD:
            obj_name = obj.get_name() or obj.get_display_name()
            issues.append({
                "type": "long_host_list",
                "severity": "info",
                "object": obj_name,
                "object_type": "service",
                "file": obj.source_file,
                "global_index": obj_to_index.get(id(obj)),
                "host_count": host_count,
                "message": f"Service has {host_count} hosts in host_name list (consider using a hostgroup)",
            })
    return issues


# ---------------------------------------------------------------------------
# Check 23: Template consolidation detection
# ---------------------------------------------------------------------------

def check_template_opportunities(ctx):
    """Check 23: Groups of 3+ objects sharing identical non-identity attributes."""
    issues = []
    objects = ctx["objects"]

    identity_fields_set = set(NAME_FIELDS.values()) | {
        "name", "register", "alias", "address", "display_name",
    }

    objects_by_type = {}
    for idx, obj in enumerate(objects):
        objects_by_type.setdefault(obj.object_type, []).append((idx, obj))

    for obj_type, type_entries in objects_by_type.items():
        if len(type_entries) < _MIN_TEMPLATE_CONSOLIDATION_GROUP:
            continue
        if obj_type in ("timeperiod", "command"):
            continue
        _check_type_for_consolidation(
            obj_type, type_entries, identity_fields_set, issues,
        )
    return issues


def _check_type_for_consolidation(obj_type, type_entries, identity_fields_set, issues):
    """Check a single object type for template consolidation opportunities."""
    signatures = {}
    for idx, obj in type_entries:
        if obj.attributes.get("use") or obj.attributes.get("register") == "0":
            continue
        attr_pairs = []
        for k, v in sorted(obj.attributes.items()):
            if k not in identity_fields_set:
                attr_pairs.append(f"{k}={v}")
        if not attr_pairs:
            continue
        signature = "|".join(attr_pairs)
        signatures.setdefault(signature, []).append((idx, obj))

    for signature, matching_entries in signatures.items():
        if len(matching_entries) < _MIN_TEMPLATE_CONSOLIDATION_GROUP:
            continue
        attrs = {}
        for pair in signature.split("|"):
            eq_idx = pair.index("=")
            k = pair[:eq_idx]
            v = pair[eq_idx + 1:]
            attrs[k] = v

        matching_objects = [obj for _, obj in matching_entries]
        suggested_name = _generate_template_name(obj_type, matching_objects, attrs)

        suggestion = {
            "suggested_name": suggested_name,
            "type": obj_type,
            "attributes": attrs,
            "object_indices": [idx for idx, _ in matching_entries],
            "count": len(matching_entries),
            "attr_count": len(attrs),
        }
        issues.append({
            "type": "template_opportunity",
            "severity": "info",
            "object": suggested_name,
            "object_type": obj_type,
            "file": matching_entries[0][1].source_file,
            "global_index": None,
            "suggestion": suggestion,
            "message": f"{len(matching_entries)} {obj_type} objects share {len(attrs)} identical attributes",
        })


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

# Ordered list of all check functions
ALL_CHECKS = [
    check_orphan_services,          # 1, 1b
    check_missing_parents,          # 1c
    check_missing_templates,        # 2
    check_missing_commands,         # 3
    check_missing_timeperiods,      # 4
    check_missing_contacts,         # 5
    check_missing_groups,           # 6
    check_empty_groups,             # 7
    check_unused_templates,         # 8
    check_duplicate_dependencies,   # 9
    check_hosts_without_services,   # 10
    check_missing_check_command,    # 11
    check_command_arg_mismatch,     # 12
    check_template_conflicts,       # 13
    check_notification_chain,       # 14
    check_service_host_notification_reachability,  # 14b
    check_unused_commands,          # 15
    check_unused_contacts,          # 16
    check_unused_contactgroups,     # 17
    check_unused_timeperiods,       # 18
    check_duplicate_objects,        # 19
    check_orphan_objects,           # 20
    check_missing_contacts_on_objects,  # 21
    check_long_host_lists,          # 22
    check_template_opportunities,   # 23
]


def run_all_checks(objects, obj_to_index, template_lookup):
    """Run all health checks and return combined issues list."""
    ctx = build_context(objects, obj_to_index, template_lookup)
    issues = []
    for check_fn in ALL_CHECKS:
        issues.extend(check_fn(ctx))
    return issues
