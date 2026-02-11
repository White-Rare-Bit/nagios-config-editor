"""Analysis and dependency routes."""

import logging
import os
from collections import defaultdict

from flask import Blueprint, jsonify, request

from inheritance import (
    build_template_index,
    build_template_lookup,
    build_template_names_set,
    detect_template_cycles,
    find_invalid_use_refs,
    find_unused_templates,
    format_cycle_issues,
    resolve_chain,
    resolve_inherited_attrs,
    walk_inheritance_chain,
)
from nagios_model import NagiosObject
from nagios_writer import NagiosConfigWriter

from .helpers import (
    get_backup_manager,
    get_config_path,
    get_parser_for_modification,
    get_service,
)

bp = Blueprint("analysis", __name__)
logger = logging.getLogger("nagios_bulk_editor.analysis")

# --- Shared constants ---

_RELATIONSHIP_FIELDS = {
    "host_name": "host",
    "hostgroup_name": "hostgroup",
    "hostgroups": "hostgroup",
    "hostgroup_members": "hostgroup",
    "service_description": "service",
    "dependent_service_description": "service",
    "dependent_host_name": "host",
    "dependent_hostgroup_name": "hostgroup",
    "master_host_name": "host",
    "master_hostgroup_name": "hostgroup",
    "master_service_description": "service",
    "servicegroup_name": "servicegroup",
    "servicegroups": "servicegroup",
    "servicegroup_members": "servicegroup",
    "dependent_servicegroup_name": "servicegroup",
    "contact_name": "contact",
    "contacts": "contact",
    "contact_groups": "contactgroup",
    "contactgroup_name": "contactgroup",
    "contactgroup_members": "contactgroup",
    "contactgroups": "contactgroup",
    "escalation_contacts": "contact",
    "escalation_contact_groups": "contactgroup",
    "use": "template",
    "members": "member",
    "parents": "host",
    "check_command": "command",
    "event_handler": "command",
    "host_notification_commands": "command",
    "service_notification_commands": "command",
    "check_period": "timeperiod",
    "notification_period": "timeperiod",
    "host_notification_period": "timeperiod",
    "service_notification_period": "timeperiod",
    "escalation_period": "timeperiod",
    "dependency_period": "timeperiod",
    "exclude": "timeperiod",
}

_TYPE_COLORS = {
    "host": "#4CAF50",
    "hostgroup": "#8BC34A",
    "service": "#2196F3",
    "servicegroup": "#03A9F4",
    "contact": "#FF9800",
    "contactgroup": "#FFC107",
    "command": "#9C27B0",
    "timeperiod": "#607D8B",
    "servicedependency": "#E91E63",
    "hostdependency": "#F44336",
    "serviceescalation": "#00BCD4",
    "hostescalation": "#009688",
}

_IDENTITY_FIELDS = {
    "host": "host_name",
    "hostgroup": "hostgroup_name",
    "servicegroup": "servicegroup_name",
    "contact": "contact_name",
    "contactgroup": "contactgroup_name",
}

_REVERSE_EDGE_FIELDS = {
    "parents",  # Network topology: parent reaches child
}

_GROUPING_TYPE_WEIGHTS = {
    "ip-subnet": 1.5,
    "hostname-prefix": 1.3,
    "hostname-suffix": 1.2,
    "network-parent": 1.4,
    "check-command": 1.0,
    "common-services": 0.9,
    "ungrouped": 0.5,
}

# Minimum members required for a hostgroup suggestion
_MIN_GROUP_SUGGESTION_SIZE = 3
# Minimum members for parent-based or ungrouped suggestions
_MIN_PARENT_GROUP_SIZE = 2


# ─────────────────────────────────────────────────────────────────────
# api_dependencies helpers
# ─────────────────────────────────────────────────────────────────────

def _make_service_node_id(obj):
    """Compute the node ID for a service object."""
    target = obj.attributes.get("hostgroup_name") or obj.attributes.get("host_name", "")
    target = ",".join([t.strip().lstrip("+").strip() for t in target.split(",")
                       if not t.strip().startswith("!")])
    if target:
        return f"service:{target}:{obj.get_name()}"
    return f"service:{obj.get_name()}"


def _add_or_update_node(obj, node_id, template_names, graph_state):
    """Add a new node or update an existing one for an object.

    graph_state is a dict with keys: nodes, node_ids, defined_node_ids.
    """
    nodes = graph_state["nodes"]
    node_ids = graph_state["node_ids"]

    if node_id not in node_ids:
        is_template = (obj.object_type, obj.get_name()) in template_names
        node_data = {
            "id": node_id,
            "label": obj.get_name(),
            "type": obj.object_type,
            "color": _TYPE_COLORS.get(obj.object_type, "#999999"),
            "exists": True,
        }
        if is_template:
            node_data["is_template"] = True
        nodes.append(node_data)
        node_ids.add(node_id)
    else:
        for existing_node in nodes:
            if existing_node["id"] == node_id:
                existing_node["exists"] = True
                if (obj.object_type, obj.get_name()) in template_names:
                    existing_node["is_template"] = True
                break
    graph_state["defined_node_ids"].add(node_id)


def _parse_relationship_targets(field, target_type, raw_value):
    """Parse the target values from a relationship field value."""
    if target_type == "command":
        command_name = raw_value.split("!")[0].strip()
        return [command_name] if command_name else []
    return [t.strip().lstrip("+").strip() for t in raw_value.split(",")
            if t.strip() and not t.strip().startswith("!")]


def _compute_target_node_id(field, target_type, target, obj, resolved_attrs):
    """Compute the node ID for a relationship target."""
    if target_type == "template":
        t_type = obj.object_type
    elif target_type == "member":
        t_type = obj.object_type.replace("group", "")
    else:
        t_type = target_type

    # parents: hosts reference hosts, services reference services
    if field == "parents" and obj.object_type == "service":
        t_type = "service"
        svc_context = resolved_attrs.get("host_name", "")
        svc_context = ",".join([t.strip().lstrip("+").strip() for t in svc_context.split(",")
                                if not t.strip().startswith("!")])
        if svc_context:
            return f"service:{svc_context}:{target}", t_type
        return f"service:{target}", t_type

    if t_type == "service" and field in ("service_description", "dependent_service_description"):
        if field == "dependent_service_description":
            svc_context = resolved_attrs.get("dependent_hostgroup_name") or resolved_attrs.get("dependent_host_name", "")
        else:
            svc_context = resolved_attrs.get("hostgroup_name") or resolved_attrs.get("host_name", "")
        svc_context = ",".join([t.strip().lstrip("+").strip() for t in svc_context.split(",")
                                if not t.strip().startswith("!")])
        if svc_context:
            return f"service:{svc_context}:{target}", t_type
        return f"service:{target}", t_type

    return f"{t_type}:{target}", t_type


def _process_obj_relationships(obj, node_id, resolved_attrs, graph_state):
    """Process all relationship fields for one object, adding edges and target nodes.

    graph_state is a dict with keys: nodes, node_ids, edges.
    """
    nodes = graph_state["nodes"]
    node_ids = graph_state["node_ids"]
    edges = graph_state["edges"]

    for field, target_type in _RELATIONSHIP_FIELDS.items():
        if field not in resolved_attrs:
            continue
        if _IDENTITY_FIELDS.get(obj.object_type) == field:
            continue

        raw_value = resolved_attrs[field]
        targets = _parse_relationship_targets(field, target_type, raw_value)

        for target in targets:
            if not target:
                continue
            target_id, t_type = _compute_target_node_id(field, target_type, target, obj, resolved_attrs)
            if target_id == node_id:
                continue

            if target_id not in node_ids:
                nodes.append({
                    "id": target_id,
                    "label": target,
                    "type": t_type,
                    "color": _TYPE_COLORS.get(t_type, "#999999"),
                    "exists": False,
                })
                node_ids.add(target_id)

            if field in _REVERSE_EDGE_FIELDS:
                edges.append({"from": target_id, "to": node_id, "label": field, "arrows": "to"})
            else:
                edges.append({"from": node_id, "to": target_id, "label": field, "arrows": "to"})


# ─────────────────────────────────────────────────────────────────────
# api_smart_grouping_suggest helpers
# ─────────────────────────────────────────────────────────────────────

def _collect_subnet_suggestions(hosts, existing_groups):
    """Collect suggestions based on IP subnet grouping."""
    subnet_groups = defaultdict(list)
    for host in hosts:
        addr = host.attributes.get("address", "")
        if addr and "." in addr:
            parts = addr.rsplit(".", 1)
            if len(parts) == 2:  # noqa: PLR2004
                subnet_groups[parts[0]].append(host.get_name())

    suggestions = []
    for subnet, members in subnet_groups.items():
        if len(members) >= _MIN_GROUP_SUGGESTION_SIZE:
            suggested_name = f"subnet-{subnet.replace('.', '-')}"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    "type": "ip-subnet",
                    "name": suggested_name,
                    "description": f"Hosts in {subnet}.0/24 subnet",
                    "members": sorted(members),
                    "count": len(members),
                    "pattern": f"{subnet}.x",
                })
    return suggestions


def _collect_prefix_suggestions(hosts, existing_groups):
    """Collect suggestions based on hostname prefix grouping."""
    prefix_groups = defaultdict(list)
    for host in hosts:
        name = host.get_name()
        if name and "-" in name:
            prefix_groups[name.split("-")[0]].append(name)

    suggestions = []
    for prefix, members in prefix_groups.items():
        if len(members) >= _MIN_GROUP_SUGGESTION_SIZE:
            suggested_name = f"{prefix}-servers"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    "type": "hostname-prefix",
                    "name": suggested_name,
                    "description": f'Hosts with prefix "{prefix}-"',
                    "members": sorted(members),
                    "count": len(members),
                    "pattern": f"{prefix}-*",
                })
    return suggestions


def _collect_suffix_suggestions(hosts, existing_groups):
    """Collect suggestions based on hostname suffix grouping."""
    suffix_groups = defaultdict(list)
    for host in hosts:
        name = host.get_name()
        if name and "-" in name:
            suffix_groups[name.split("-")[-1]].append(name)

    suggestions = []
    for suffix, members in suffix_groups.items():
        if len(members) >= _MIN_GROUP_SUGGESTION_SIZE:
            suggested_name = f"{suffix}-systems"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    "type": "hostname-suffix",
                    "name": suggested_name,
                    "description": f'Hosts with suffix "-{suffix}"',
                    "members": sorted(members),
                    "count": len(members),
                    "pattern": f"*-{suffix}",
                })
    return suggestions


def _collect_command_suggestions(hosts, existing_groups):
    """Collect suggestions based on check command grouping."""
    command_groups = defaultdict(list)
    for host in hosts:
        name = host.get_name()
        check_cmd = host.attributes.get("check_command", "")
        if name and check_cmd:
            command_groups[check_cmd.split("!")[0]].append(name)

    suggestions = []
    for cmd, members in command_groups.items():
        if len(members) >= _MIN_GROUP_SUGGESTION_SIZE:
            suggested_name = f"{cmd.replace('check_', '').replace('check-', '')}-checked"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    "type": "check-command",
                    "name": suggested_name,
                    "description": f'Hosts using check command "{cmd}"',
                    "members": sorted(members),
                    "count": len(members),
                    "pattern": cmd,
                })
    return suggestions


def _collect_parent_suggestions(hosts, existing_groups):
    """Collect suggestions based on network parent grouping."""
    parent_groups = defaultdict(list)
    for host in hosts:
        name = host.get_name()
        parents = host.attributes.get("parents", "")
        if name and parents:
            for parent in parents.split(","):
                parent = parent.strip()
                if parent:
                    parent_groups[parent].append(name)

    suggestions = []
    for parent, members in parent_groups.items():
        if len(members) >= _MIN_PARENT_GROUP_SIZE:
            suggested_name = f"behind-{parent}"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    "type": "network-parent",
                    "name": suggested_name,
                    "description": f'Hosts behind "{parent}"',
                    "members": sorted(members),
                    "count": len(members),
                    "pattern": f"parents={parent}",
                })
    return suggestions


def _find_ungrouped_hosts(hosts, service_objects):
    """Find hosts not in any hostgroup and return as a suggestion (or empty list)."""
    hosts_in_groups = set()
    for obj in service_objects:
        if obj.object_type == "hostgroup":
            members = obj.attributes.get("members", "")
            for m in members.split(","):
                m = m.strip()
                if m.startswith("!"):
                    continue
                m = m.lstrip("+").strip()
                if m:
                    hosts_in_groups.add(m)

    for host in hosts:
        if "hostgroups" in host.attributes:
            hosts_in_groups.add(host.get_name())

    ungrouped = [h.get_name() for h in hosts if h.get_name() and h.get_name() not in hosts_in_groups]
    if len(ungrouped) >= _MIN_PARENT_GROUP_SIZE:
        return [{
            "type": "ungrouped",
            "name": "ungrouped-hosts",
            "description": "Hosts not currently in any hostgroup",
            "members": sorted(ungrouped),
            "count": len(ungrouped),
            "pattern": "No hostgroup membership",
        }]
    return []


def _score_and_rank_suggestions(suggestions):
    """Compute confidence scores and overlap info for suggestions."""
    host_suggestion_counts = defaultdict(int)
    for suggestion in suggestions:
        for member in suggestion["members"]:
            host_suggestion_counts[member] += 1

    for suggestion in suggestions:
        base_score = suggestion["count"]
        type_weight = _GROUPING_TYPE_WEIGHTS.get(suggestion["type"], 1.0)
        overlap_bonus = sum(0.1 for m in suggestion["members"] if host_suggestion_counts[m] > 1)
        overlap_bonus = min(overlap_bonus, suggestion["count"] * 0.3)
        suggestion["confidence"] = round((base_score * type_weight) + overlap_bonus, 2)

        overlap_types = set()
        for other in suggestions:
            if other is not suggestion:
                shared = set(suggestion["members"]) & set(other["members"])
                if len(shared) >= _MIN_PARENT_GROUP_SIZE:
                    overlap_types.add(other["type"])
        suggestion["overlaps_with"] = list(overlap_types)

    suggestions.sort(key=lambda x: x["confidence"], reverse=True)


# ─────────────────────────────────────────────────────────────────────
# api_smart_grouping_create helpers
# ─────────────────────────────────────────────────────────────────────

def _find_hostgroup_target_file(objects, config_path):
    """Find the best target file for a new hostgroup."""
    for obj in objects:
        if obj.object_type == "hostgroup":
            return obj.source_file
    for obj in objects:
        if obj.object_type == "host":
            return obj.source_file.replace(".cfg", "-hostgroups.cfg")
    return os.path.join(config_path, "hostgroups.cfg")


# ─────────────────────────────────────────────────────────────────────
# api_add_to_group helpers
# ─────────────────────────────────────────────────────────────────────

def _merge_hosts_into_member_list(hosts_to_add, current_list):
    """Add hosts to member list, skipping duplicates. Returns (updated_list, added_count)."""
    current_normalized = [m.lstrip("+!").strip() for m in current_list]
    added_count = 0
    for host in hosts_to_add:
        if host not in current_normalized:
            current_list.append(host)
            current_normalized.append(host)
            added_count += 1
    return current_list, added_count


def _update_host_hostgroups_attr(hosts_to_add, group_name, objects):
    """Update the hostgroups attribute on each host object to include the group."""
    for host_name in hosts_to_add:
        for obj in objects:
            if obj.object_type == "host" and obj.get_name() == host_name:
                current_hostgroups = obj.attributes.get("hostgroups", "")
                hostgroups_list = [hg.strip() for hg in current_hostgroups.split(",") if hg.strip()]
                hostgroups_normalized = [hg.lstrip("+!").strip() for hg in hostgroups_list]
                if group_name not in hostgroups_normalized:
                    hostgroups_list.append(group_name)
                    obj.attributes["hostgroups"] = ",".join(hostgroups_list)
                    logger.debug("Updated host %s hostgroups: %s", host_name, obj.attributes["hostgroups"])
                break


# ─────────────────────────────────────────────────────────────────────
# get_template_issues helpers
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# api_escalation_path helpers
# ─────────────────────────────────────────────────────────────────────

def _find_escalation_target(objects, object_type, name, service_desc):
    """Find the target host or service object."""
    for obj in objects:
        if object_type == "host":
            if obj.object_type == "host" and obj.get_name() == name:
                return obj
        elif object_type == "service" and service_desc and obj.object_type == "service":
            host_attr = obj.attributes.get("host_name", "")
            svc_desc = obj.attributes.get("service_description", "")
            if name in [h.strip() for h in host_attr.split(",")] and svc_desc == service_desc:
                return obj
    return None


def _build_escalation_lookups(objects):
    """Build template, contact, and contactgroup lookups."""
    template_lookup = build_template_lookup(objects)
    contact_objects = {}
    cg_objects = {}
    for obj in objects:
        if obj.object_type == "contact" and obj.attributes.get("register", "1") != "0":
            contact_objects[obj.attributes.get("contact_name", "")] = obj
        elif obj.object_type == "contactgroup":
            cg_objects[obj.attributes.get("contactgroup_name", "")] = obj
    return template_lookup, contact_objects, cg_objects


def _resolve_cg_members(cg_name, cg_objects):
    """Resolve contactgroup to individual contact names."""
    cg = cg_objects.get(cg_name)
    if not cg:
        return []
    members = []
    if "members" in cg.attributes:
        members.extend([m.strip() for m in cg.attributes["members"].split(",") if m.strip()])
    return members


def _get_contact_info(cname, contact_objects, template_lookup):
    """Get contact notification info."""
    cobj = contact_objects.get(cname)
    if not cobj:
        return {"name": cname, "exists": False}
    resolved = resolve_inherited_attrs(cobj, template_lookup)
    return {
        "name": cname,
        "exists": True,
        "host_notification_commands": resolved.get("host_notification_commands", ""),
        "service_notification_commands": resolved.get("service_notification_commands", ""),
        "host_notification_period": resolved.get("host_notification_period", ""),
        "service_notification_period": resolved.get("service_notification_period", ""),
    }


def _resolve_base_contacts(resolved_target, cg_objects, contact_objects, template_lookup):
    """Resolve the base contacts for a target object."""
    base_contact_names = set()
    if "contacts" in resolved_target:
        for c in resolved_target["contacts"].split(","):
            c = c.strip().lstrip("+!")
            if c:
                base_contact_names.add(c)
    if "contact_groups" in resolved_target:
        for cg in resolved_target["contact_groups"].split(","):
            cg = cg.strip().lstrip("+!")
            for m in _resolve_cg_members(cg, cg_objects):
                base_contact_names.add(m)
    return [_get_contact_info(c, contact_objects, template_lookup) for c in sorted(base_contact_names)]


def _escalation_matches_target(obj, object_type, name, service_desc):
    """Check if an escalation object matches the target host/service."""
    if object_type == "host":
        esc_hosts = obj.attributes.get("host_name", "")
        return name in [h.strip() for h in esc_hosts.split(",")]
    esc_hosts = obj.attributes.get("host_name", "")
    esc_svc = obj.attributes.get("service_description", "")
    if service_desc and esc_svc == service_desc:
        return name in [h.strip() for h in esc_hosts.split(",")]
    return False


def _collect_escalation_contacts(obj, cg_objects):
    """Collect all contact names from an escalation object."""
    esc_contact_names = set()
    if "contact_groups" in obj.attributes:
        for cg in obj.attributes["contact_groups"].split(","):
            for m in _resolve_cg_members(cg.strip(), cg_objects):
                esc_contact_names.add(m)
    if "contacts" in obj.attributes:
        for c in obj.attributes["contacts"].split(","):
            c = c.strip()
            if c:
                esc_contact_names.add(c)
    return esc_contact_names


def _find_matching_escalations(objects, object_type, name, service_desc, lookups):
    """Find all escalations matching target, return sorted list.

    lookups is a dict with keys: cg_objects, contact_objects, template_lookup.
    """
    cg_objects = lookups["cg_objects"]
    contact_objects = lookups["contact_objects"]
    template_lookup = lookups["template_lookup"]

    esc_type = "hostescalation" if object_type == "host" else "serviceescalation"
    escalations = []
    for obj in objects:
        if obj.object_type != esc_type:
            continue
        if not _escalation_matches_target(obj, object_type, name, service_desc):
            continue
        esc_contact_names = _collect_escalation_contacts(obj, cg_objects)
        escalations.append({
            "first_notification": int(obj.attributes.get("first_notification", 0)),
            "last_notification": int(obj.attributes.get("last_notification", 0)),
            "notification_interval": int(obj.attributes.get("notification_interval", 0)),
            "escalation_period": obj.attributes.get("escalation_period", ""),
            "contacts": [_get_contact_info(c, contact_objects, template_lookup) for c in sorted(esc_contact_names)],
            "source_file": obj.source_file,
        })
    escalations.sort(key=lambda e: e["first_notification"])
    return escalations


# ─────────────────────────────────────────────────────────────────────
# api_object_references helpers
# ─────────────────────────────────────────────────────────────────────

def _strip_prefix(s):
    """Strip leading whitespace, '+', '!' from a value."""
    return s.strip().lstrip("+!").strip()


_COMMAND_FIELDS = [
    "check_command", "event_handler", "notification_commands",
    "host_notification_commands", "service_notification_commands",
    "obsess_over_host_command", "obsess_over_service_command",
    "global_host_event_handler", "global_service_event_handler",
]


def _obj_summary(o, idx):
    """Return a summary dict for an object."""
    return {
        "global_index": idx,
        "object_type": o.object_type,
        "name": o.get_name() or o.get_display_name(),
        "file": o.source_file,
    }


def _collect_outgoing_refs(obj, global_index, objects, reference_fields):
    """Collect outgoing references from obj to other objects."""
    outgoing = []
    for field, ref_type in reference_fields.items():
        val = obj.attributes.get(field)
        if not val:
            continue
        actual_type = ref_type or obj.object_type
        for v in val.split(","):
            v = _strip_prefix(v)
            if not v or v == "*":
                continue
            lookup_val = v.split("!")[0] if field in _COMMAND_FIELDS else v
            for idx, o in enumerate(objects):
                if o.object_type != actual_type:
                    continue
                o_name = o.get_name() or o.get_display_name()
                o_template = o.attributes.get("name")
                if o_name == lookup_val or o_template == lookup_val:
                    if idx != global_index:
                        outgoing.append({**_obj_summary(o, idx), "field": field})
                    break
    return outgoing


def _classify_ref_severity(ref_obj, field, _target_obj_type):
    """Classify the severity if the target object were deleted.

    Returns "error", "warning", or "info":
    - error: would break the referring object (orphan service, broken inheritance)
    - warning: escalations, dependencies, contact_groups membership
    - info: minor reference updates
    """
    ref_type = ref_obj.object_type

    # Template inheritance — deleting breaks the inheriting object
    if field == "use":
        return "error"

    # Service bound to host/hostgroup — deleting orphans the service
    if ref_type == "service" and field in ("host_name", "hostgroup_name"):
        return "error"

    # Host parent — deleting breaks parent chain
    if ref_type == "host" and field == "parents":
        return "error"

    # Group members, escalations, dependencies, contact refs
    warning_types = (
        "hostescalation", "serviceescalation",
        "hostdependency", "servicedependency",
    )
    warning_member_types = ("hostgroup", "contactgroup", "servicegroup")

    if field == "members" and ref_type in warning_member_types:
        return "warning"
    if ref_type in warning_types:
        return "warning"
    if field in ("contact_groups", "contacts"):
        return "warning"

    return "info"


def _collect_incoming_refs(obj, obj_identity, global_index, objects, reference_fields):
    """Collect incoming references from other objects to obj.

    obj_identity is a dict with keys: name, template_name.
    """
    obj_name = obj_identity["name"]
    obj_template_name = obj_identity["template_name"]

    incoming = []
    for idx, o in enumerate(objects):
        if idx == global_index:
            continue
        for field, ref_type in reference_fields.items():
            val = o.attributes.get(field)
            if not val:
                continue
            actual_type = ref_type or o.object_type
            is_escalation_ref = (
                o.object_type in ("hostescalation", "serviceescalation") and
                obj.object_type in ("contact", "contactgroup") and
                field in ("escalation_contacts", "escalation_contact_groups", "contacts", "contact_groups")
            )
            if actual_type != obj.object_type and ref_type is not None and not is_escalation_ref:
                continue
            values = [_strip_prefix(v) for v in val.split(",")]
            if field in _COMMAND_FIELDS:
                values = [v.split("!")[0] if "!" in v else v for v in values]
            if obj_name in values or (obj_template_name and obj_template_name in values):
                severity = _classify_ref_severity(
                    o, field, obj.object_type,
                )
                incoming.append({
                    **_obj_summary(o, idx),
                    "field": field,
                    "severity": severity,
                })
    return incoming


def _collect_host_dependency_rules(obj_name, global_index, objects):
    """Collect dependency rules for a host object."""
    outgoing = []
    incoming = []
    for idx, o in enumerate(objects):
        if o.object_type != "hostdependency":
            continue
        master_hosts = [h.strip() for h in o.attributes.get("host_name", "").split(",") if h.strip()]
        dependent_hosts = [h.strip() for h in o.attributes.get("dependent_host_name", "").split(",") if h.strip()]
        if obj_name in master_hosts:
            outgoing.append({
                **_obj_summary(o, idx), "field": "dependency_rule",
                "is_dependency_rule": True, "role": "master_of",
            })
        if obj_name in dependent_hosts:
            incoming.append({
                **_obj_summary(o, idx), "field": "dependency_rule",
                "is_dependency_rule": True, "role": "dependent_of",
            })
    return outgoing, incoming


def _collect_service_dependency_rules(obj_name, host_name, objects):
    """Collect dependency rules for a service object."""
    outgoing = []
    incoming = []
    for idx, o in enumerate(objects):
        if o.object_type != "servicedependency":
            continue
        master_svc = o.attributes.get("service_description", "")
        master_hosts = [h.strip() for h in o.attributes.get("host_name", "").split(",") if h.strip()]
        dep_svc = o.attributes.get("dependent_service_description", "")
        dep_hosts = [h.strip() for h in o.attributes.get("dependent_host_name", "").split(",") if h.strip()]
        if master_svc == obj_name and (not master_hosts or host_name in master_hosts):
            outgoing.append({
                **_obj_summary(o, idx), "field": "dependency_rule",
                "is_dependency_rule": True, "role": "master_of",
            })
        if dep_svc == obj_name and (not dep_hosts or host_name in dep_hosts):
            incoming.append({
                **_obj_summary(o, idx), "field": "dependency_rule",
                "is_dependency_rule": True, "role": "dependent_of",
            })
    return outgoing, incoming


def _is_host_in_hostgroup(host_name, hostgroup_name, objects, visited=None):
    """Check if a host belongs to a hostgroup (directly or via nesting)."""
    if visited is None:
        visited = set()
    if hostgroup_name in visited:
        return False
    visited.add(hostgroup_name)
    for o in objects:
        if o.object_type != "hostgroup":
            continue
        if (o.get_name() or "") != hostgroup_name:
            continue
        members = [m.strip() for m in o.attributes.get("members", "").split(",") if m.strip()]
        if host_name in members:
            return True
        if _host_in_group_via_attr(host_name, hostgroup_name, objects):
            return True
        nested = [g.strip().lstrip("+!").strip() for g in o.attributes.get("hostgroup_members", "").split(",") if g.strip()]
        for ng in nested:
            if _is_host_in_hostgroup(host_name, ng, objects, visited):
                return True
    return False


def _host_in_group_via_attr(host_name, hostgroup_name, objects):
    """Check if a host has the hostgroup in its hostgroups attribute."""
    for ho in objects:
        if ho.object_type == "host" and (ho.get_name() or "") == host_name:
            hgs = [g.strip().lstrip("+!").strip() for g in ho.attributes.get("hostgroups", "").split(",") if g.strip()]
            return hostgroup_name in hgs
    return False


def _collect_host_escalation_rules(obj_name, objects):
    """Collect escalation rules that apply to a host."""
    incoming = []
    for idx, o in enumerate(objects):
        if o.object_type != "hostescalation":
            continue
        esc_host = o.attributes.get("host_name", "")
        esc_hg = o.attributes.get("hostgroup_name", "")
        if esc_host and obj_name in [h.strip() for h in esc_host.split(",")]:
            incoming.append({**_obj_summary(o, idx), "field": "escalation_rule", "is_escalation_rule": True})
        elif esc_hg:
            for g in [g.strip() for g in esc_hg.split(",") if g.strip()]:
                if _is_host_in_hostgroup(obj_name, g, objects):
                    incoming.append({**_obj_summary(o, idx), "field": "escalation_rule", "is_escalation_rule": True})
                    break
    return incoming


def _collect_service_escalation_rules(obj_name, host_name, objects):
    """Collect escalation rules that apply to a service."""
    incoming = []
    for idx, o in enumerate(objects):
        if o.object_type != "serviceescalation":
            continue
        esc_svc = o.attributes.get("service_description", "")
        esc_host = o.attributes.get("host_name", "")
        esc_hg = o.attributes.get("hostgroup_name", "")
        if not esc_svc or obj_name not in [s.strip() for s in esc_svc.split(",")]:
            continue
        if _service_escalation_matches(host_name, esc_host, esc_hg, objects):
            incoming.append({**_obj_summary(o, idx), "field": "escalation_rule", "is_escalation_rule": True})
    return incoming


def _service_escalation_matches(host_name, esc_host, esc_hg, objects):
    """Check if a service escalation matches via host_name, hostgroup, or wildcard."""
    if esc_host and host_name in [h.strip() for h in esc_host.split(",")]:
        return True
    if esc_hg:
        for g in [g.strip() for g in esc_hg.split(",") if g.strip()]:
            if _is_host_in_hostgroup(host_name, g, objects):
                return True
        return False
    return bool(not esc_host and not esc_hg)


def _collect_hostgroup_service_bindings(obj_name, objects):
    """Collect services bound to a hostgroup."""
    incoming = []
    for idx, o in enumerate(objects):
        if o.object_type != "service":
            continue
        hg_name = o.attributes.get("hostgroup_name", "")
        if hg_name:
            groups = [g.strip().lstrip("+!").strip() for g in hg_name.split(",")]
            if obj_name in groups:
                incoming.append({**_obj_summary(o, idx), "field": "hostgroup_name", "is_service_binding": True})
    return incoming


def _collect_host_service_bindings_via_hostgroup(obj_name, objects):
    """Collect services bound to a host via hostgroup_name (no direct host_name)."""
    incoming = []
    for idx, o in enumerate(objects):
        if o.object_type != "service":
            continue
        if o.attributes.get("host_name"):
            continue
        hg_name = o.attributes.get("hostgroup_name", "")
        if hg_name:
            for g in [g.strip().lstrip("+!").strip() for g in hg_name.split(",") if g.strip()]:
                if _is_host_in_hostgroup(obj_name, g, objects):
                    incoming.append({**_obj_summary(o, idx), "field": "hostgroup_name", "is_service_binding": True, "via_group": g})
                    break
    return incoming


def _collect_group_members(obj, obj_name, global_index, objects):
    """Collect members for a group or template object.

    Returns:
        Tuple of (members_list, transitive_summary_or_none).
    """
    if obj.object_type == "hostgroup":
        return _collect_hostgroup_members(obj, obj_name, objects), None
    if obj.object_type == "contactgroup":
        return _collect_contactgroup_members(obj, obj_name, objects), None
    if obj.object_type == "servicegroup":
        return _collect_servicegroup_members(obj, obj_name, objects), None
    if obj.attributes.get("register", "1") == "0":
        return _collect_template_inheritors(obj, global_index, objects)
    return [], None


def _collect_hostgroup_members(obj, obj_name, objects):
    """Collect host members of a hostgroup."""
    direct = [m.strip() for m in obj.attributes.get("members", "").split(",") if m.strip()]
    members = []
    for idx, o in enumerate(objects):
        if o.object_type != "host":
            continue
        h_name = o.get_name() or ""
        if h_name in direct:
            members.append({**_obj_summary(o, idx), "via": "members"})
        else:
            hgs = [g.strip().lstrip("+!").strip() for g in o.attributes.get("hostgroups", "").split(",") if g.strip()]
            if obj_name in hgs:
                members.append({**_obj_summary(o, idx), "via": "hostgroups attr"})
    return members


def _collect_contactgroup_members(obj, obj_name, objects):
    """Collect contact members of a contactgroup."""
    direct = [m.strip().lstrip("+!").strip() for m in obj.attributes.get("members", "").split(",") if m.strip()]
    members = []
    for idx, o in enumerate(objects):
        if o.object_type != "contact":
            continue
        c_name = o.get_name() or ""
        if c_name in direct:
            members.append({**_obj_summary(o, idx), "via": "members"})
        else:
            cgs = [g.strip().lstrip("+!").strip() for g in o.attributes.get("contactgroups", "").split(",") if g.strip()]
            if obj_name in cgs:
                members.append({**_obj_summary(o, idx), "via": "contactgroups attr"})
    return members


def _collect_servicegroup_members(obj, obj_name, objects):
    """Collect service members of a servicegroup."""
    direct = [m.strip().lstrip("+!").strip() for m in obj.attributes.get("members", "").split(",") if m.strip()]
    members = []
    for idx, o in enumerate(objects):
        if o.object_type != "service":
            continue
        s_name = o.get_name() or ""
        if s_name in direct:
            members.append({**_obj_summary(o, idx), "via": "members"})
        else:
            sgs = [g.strip().lstrip("+!").strip() for g in o.attributes.get("servicegroups", "").split(",") if g.strip()]
            if obj_name in sgs:
                members.append({**_obj_summary(o, idx), "via": "servicegroups attr"})
    return members


def _collect_template_inheritors(obj, global_index, objects):
    """Collect objects that inherit from this template, with transitive counts."""
    template_name = obj.attributes.get("name", "")
    if not template_name:
        return [], None
    members = []
    for idx, o in enumerate(objects):
        if idx == global_index:
            continue
        uses = [u.strip() for u in o.attributes.get("use", "").split(",") if u.strip()]
        if template_name in uses:
            members.append({**_obj_summary(o, idx), "via": "inherits"})

    # Compute transitive impact
    transitive_summary = _count_transitive_inheritors(
        template_name, obj.object_type, global_index, objects,
    )

    return members, transitive_summary


def _count_transitive_inheritors(template_name, _obj_type, exclude_idx, objects):
    """Count all objects that transitively inherit from this template.

    Uses BFS to walk through intermediate templates.

    Returns:
        Dict with direct_count, transitive_count, intermediate_templates.
        None if no transitive impact beyond direct inheritors.
    """
    # BFS: find all direct inheritors of the template
    def find_inheritors(name):
        """Find objects that directly use the given template name."""
        result = []
        for idx, o in enumerate(objects):
            if idx == exclude_idx:
                continue
            use_val = o.attributes.get("use", "")
            uses = [u.strip() for u in use_val.split(",") if u.strip()]
            if name in uses:
                result.append((idx, o))
        return result

    def is_template(o):
        """Check if an object is itself a template."""
        return "name" in o.attributes or o.attributes.get("register", "1") == "0"

    direct = find_inheritors(template_name)
    direct_count = len(direct)

    if direct_count == 0:
        return None

    # BFS through intermediate templates
    visited_names = {template_name}
    queue = []
    intermediate_templates = []
    transitive_total = 0

    for _idx, o in direct:
        transitive_total += 1
        if is_template(o):
            tmpl_name = o.attributes.get("name", "")
            if tmpl_name and tmpl_name not in visited_names:
                queue.append(tmpl_name)
                visited_names.add(tmpl_name)
                intermediate_templates.append(tmpl_name)

    while queue:
        current_name = queue.pop(0)
        children = find_inheritors(current_name)
        for _idx, o in children:
            transitive_total += 1
            if is_template(o):
                tmpl_name = o.attributes.get("name", "")
                if tmpl_name and tmpl_name not in visited_names:
                    queue.append(tmpl_name)
                    visited_names.add(tmpl_name)
                    intermediate_templates.append(tmpl_name)

    # Only return summary if there's transitive impact beyond direct
    if transitive_total <= direct_count:
        return None

    return {
        "direct_count": direct_count,
        "transitive_count": transitive_total,
        "intermediate_templates": intermediate_templates,
    }


def _collect_host_member_of(obj, obj_name, objects):
    """Collect hostgroups that a host belongs to."""
    member_of = []
    hgs = [g.strip().lstrip("+!").strip() for g in obj.attributes.get("hostgroups", "").split(",") if g.strip()]
    for idx, o in enumerate(objects):
        if o.object_type == "hostgroup" and (o.get_name() or "") in hgs:
            member_of.append({**_obj_summary(o, idx), "via": "hostgroups"})
    for idx, o in enumerate(objects):
        if o.object_type != "hostgroup":
            continue
        direct = [m.strip() for m in o.attributes.get("members", "").split(",") if m.strip()]
        if obj_name in direct:
            g_name = o.get_name() or ""
            if not any(m["name"] == g_name for m in member_of):
                member_of.append({**_obj_summary(o, idx), "via": "members"})
    return member_of


def _collect_service_member_of(obj, objects):
    """Collect servicegroups that a service belongs to."""
    member_of = []
    sgs = [g.strip().lstrip("+!").strip() for g in obj.attributes.get("servicegroups", "").split(",") if g.strip()]
    for idx, o in enumerate(objects):
        if o.object_type == "servicegroup" and (o.get_name() or "") in sgs:
            member_of.append({**_obj_summary(o, idx), "via": "servicegroups"})
    return member_of


def _collect_contact_member_of(obj, objects):
    """Collect contactgroups that a contact belongs to."""
    member_of = []
    cgs = [g.strip().lstrip("+!").strip() for g in obj.attributes.get("contactgroups", "").split(",") if g.strip()]
    for idx, o in enumerate(objects):
        if o.object_type == "contactgroup" and (o.get_name() or "") in cgs:
            member_of.append({**_obj_summary(o, idx), "via": "contactgroups"})
    return member_of


def _build_parent_tree(host_obj, objects, obj_to_index, visited=None):
    """Build the parent host tree recursively."""
    if visited is None:
        visited = set()
    h_idx = obj_to_index.get(id(host_obj))
    h_name = host_obj.get_name() or host_obj.get_display_name()
    if h_idx in visited:
        return {"name": h_name, "global_index": h_idx, "circular": True}
    visited.add(h_idx)
    p_attr = host_obj.attributes.get("parents", "")
    parent_names = [p.strip().lstrip("+").strip() for p in p_attr.split(",")
                    if p.strip() and not p.strip().startswith("!")]
    parent_nodes = []
    for pn in parent_names:
        parent_obj = _find_host_by_name(pn, objects)
        if parent_obj:
            parent_nodes.append(_build_parent_tree(parent_obj, objects, obj_to_index, set(visited)))
        else:
            parent_nodes.append({"name": pn, "missing": True})
    return {
        "name": h_name,
        "global_index": h_idx,
        "file": host_obj.source_file,
        "parents": parent_nodes,
    }


def _find_host_by_name(name, objects):
    """Find a host object by name."""
    for o in objects:
        if o.object_type == "host" and (o.get_name() or "") == name:
            return o
    return None


# ═══════════════════════════════════════════════════════════════════════
# Route handlers
# ═══════════════════════════════════════════════════════════════════════

@bp.route("/api/dependencies")
def api_dependencies():
    """Get object dependencies for graph visualization."""
    service = get_service()
    p = service.parser
    object_type = request.args.get("type")

    graph = {"nodes": [], "edges": [], "node_ids": set(), "defined_node_ids": set()}

    template_lookup = build_template_lookup(service.get_objects())
    template_names = build_template_names_set(service.get_objects())

    for obj in p.objects:
        if object_type and obj.object_type != object_type:
            continue
        obj_name = obj.get_name()
        if not obj_name:
            continue

        if obj.object_type == "service":
            node_id = _make_service_node_id(obj)
        else:
            node_id = f"{obj.object_type}:{obj_name}"

        _add_or_update_node(obj, node_id, template_names, graph)

        resolved_attrs = resolve_inherited_attrs(obj, template_lookup)
        _process_obj_relationships(obj, node_id, resolved_attrs, graph)

    return jsonify({"nodes": graph["nodes"], "edges": graph["edges"]})


@bp.route("/api/inheritance/list/<object_type>")
def api_inheritance_list(object_type):
    """List all templates for a given object type."""
    service = get_service()
    templates = []
    for obj in service.get_objects():
        if obj.object_type == object_type and obj.attributes.get("register", "1") == "0":
            templates.append(obj.to_dict())
    return jsonify(templates)


@bp.route("/api/inheritance/<object_type>/<name>")
def api_inheritance_chain(object_type, name):
    """Get the inheritance chain for an object."""
    service = get_service()

    target = None
    for obj in service.get_objects():
        if obj.object_type == object_type and obj.get_name() == name:
            target = obj
            break

    if not target:
        return jsonify({"error": "Object not found"}), 404

    templates = {}
    for obj in service.get_objects():
        if obj.object_type == object_type and "name" in obj.attributes:
            templates[obj.attributes["name"]] = obj

    chain_list, inherited, errors = resolve_chain(target, object_type, templates)
    # Include the target object itself at the start for backward compatibility
    full_chain = [target.to_dict()] + chain_list
    result = {"chain": full_chain, "depth": len(full_chain)}
    if errors:
        result["errors"] = errors
    return jsonify(result)


@bp.route("/api/smart-grouping/suggest")
def api_smart_grouping_suggest():
    """Suggest hostgroups based on common patterns."""
    service = get_service()
    MAX_SUGGESTIONS = 20

    hosts = [obj for obj in service.get_objects()
             if obj.object_type == "host" and obj.attributes.get("register", "1") != "0"]

    if not hosts:
        return jsonify({"suggestions": [], "total_hosts": 0})

    existing_groups = set()
    for obj in service.get_objects():
        if obj.object_type == "hostgroup":
            name = obj.get_name()
            if name:
                existing_groups.add(name.lower())

    suggestions = []
    suggestions.extend(_collect_subnet_suggestions(hosts, existing_groups))
    suggestions.extend(_collect_prefix_suggestions(hosts, existing_groups))
    suggestions.extend(_collect_suffix_suggestions(hosts, existing_groups))
    suggestions.extend(_collect_command_suggestions(hosts, existing_groups))
    suggestions.extend(_collect_parent_suggestions(hosts, existing_groups))
    suggestions.extend(_find_ungrouped_hosts(hosts, service.get_objects()))

    _score_and_rank_suggestions(suggestions)
    limited_suggestions = suggestions[:MAX_SUGGESTIONS]

    return jsonify({
        "suggestions": limited_suggestions,
        "total_hosts": len(hosts),
        "existing_groups": len(existing_groups),
        "suggestions_truncated": len(suggestions) > MAX_SUGGESTIONS,
    })


@bp.route("/api/smart-grouping/create", methods=["POST"])
def api_smart_grouping_create():
    """Create a hostgroup from a suggestion."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    group_name = data.get("name", "").strip()
    members = data.get("members", [])
    alias = data.get("alias", "")

    if not group_name:
        return jsonify({"error": "Group name required"}), 400
    if not members:
        return jsonify({"error": "At least one member required"}), 400

    with get_parser_for_modification() as p:
        for obj in p.objects:
            if obj.object_type == "hostgroup" and obj.get_name() == group_name:
                return jsonify({"error": f'Hostgroup "{group_name}" already exists'}), 400

        backup_path = bm.create_backup("create_hostgroup")
        target_file = _find_hostgroup_target_file(p.objects, get_config_path())

        new_group = NagiosObject(
            object_type="hostgroup",
            attributes={
                "hostgroup_name": group_name,
                "alias": alias or group_name,
                "members": ",".join(members),
            },
            source_file=target_file,
            line_number=0,
        )

        p.objects.append(new_group)

        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(p.objects)

    get_service().reload()

    return jsonify({
        "success": True,
        "group_name": group_name,
        "members_count": len(members),
        "file": target_file,
        "backup": backup_path,
    })


@bp.route("/api/smart-grouping/add-to-group", methods=["POST"])
def api_add_to_group():
    """Add hosts to an existing hostgroup."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    group_name = data.get("group_name", "").strip()
    hosts_to_add = data.get("hosts", [])

    if not group_name:
        return jsonify({"error": "Group name required"}), 400
    if not hosts_to_add:
        return jsonify({"error": "At least one host required"}), 400

    with get_parser_for_modification() as p:
        hostgroup = None
        for obj in p.objects:
            if obj.object_type == "hostgroup" and obj.get_name() == group_name:
                hostgroup = obj
                break

        if not hostgroup:
            return jsonify({"error": f'Hostgroup "{group_name}" not found'}), 404

        backup_path = bm.create_backup("add_to_hostgroup")

        current_members = hostgroup.attributes.get("members", "")
        current_list = [m.strip() for m in current_members.split(",") if m.strip()]
        logger.debug("Current members of %s: %s", group_name, current_list)

        current_list, added_count = _merge_hosts_into_member_list(hosts_to_add, current_list)

        new_members = ",".join(current_list)
        hostgroup.attributes["members"] = new_members
        logger.debug("New members: %s", new_members)

        _update_host_hostgroups_attr(hosts_to_add, group_name, p.objects)

        writer = NagiosConfigWriter()
        files_written = writer.write_objects_to_original_files(p.objects)
        logger.debug("Files written: %s", files_written)

    get_service().reload()

    service = get_service()
    for obj in service.get_objects():
        if obj.object_type == "hostgroup" and obj.get_name() == group_name:
            logger.debug("Verified members after reload: %s", obj.attributes.get("members", ""))
            break

    final_members = ""
    for obj in service.get_objects():
        if obj.object_type == "hostgroup" and obj.get_name() == group_name:
            final_members = obj.attributes.get("members", "")
            break

    return jsonify({
        "success": True,
        "group_name": group_name,
        "added_count": added_count,
        "total_members": len(current_list),
        "members": final_members,
        "backup": backup_path,
    })


@bp.route("/api/templates/issues")
def get_template_issues():
    """Get template-specific validation issues.

    Returns three categories of issues:
    - invalid_use: Objects referencing non-existent templates
    - circular_dependencies: Circular template inheritance chains
    - unused_templates: Templates not used by any object (directly or transitively)
    """
    service = get_service()
    objects = service.get_objects()

    templates_by_type, all_templates = build_template_index(objects)
    invalid_use, referenced_templates = find_invalid_use_refs(objects, templates_by_type)
    detected_cycles = detect_template_cycles(templates_by_type, all_templates)
    circular_deps = format_cycle_issues(detected_cycles)
    unused = find_unused_templates(all_templates, referenced_templates, templates_by_type)

    return jsonify({
        "invalid_use": invalid_use,
        "circular_dependencies": circular_deps,
        "unused_templates": unused,
    })


@bp.route("/api/escalation-path/<object_type>/<name>")
@bp.route("/api/escalation-path/<object_type>/<name>/<service_desc>")
def api_escalation_path(object_type, name, service_desc=None):
    """Get escalation path for a host or service.

    Returns base contacts and escalation levels in notification order.
    """
    service = get_service()
    objects = service.get_objects()

    target = _find_escalation_target(objects, object_type, name, service_desc)
    if not target:
        return jsonify({"error": "Object not found"}), 404

    template_lookup, contact_objects, cg_objects = _build_escalation_lookups(objects)
    resolved_target = resolve_inherited_attrs(target, template_lookup)
    base_contacts = _resolve_base_contacts(resolved_target, cg_objects, contact_objects, template_lookup)
    lookups = {
        "cg_objects": cg_objects,
        "contact_objects": contact_objects,
        "template_lookup": template_lookup,
    }
    escalations = _find_matching_escalations(
        objects, object_type, name, service_desc, lookups,
    )

    return jsonify({
        "object_type": object_type,
        "name": name,
        "service_description": service_desc,
        "base_contacts": base_contacts,
        "escalations": escalations,
    })


@bp.route("/api/object-references/<int:global_index>")
def api_object_references(global_index):
    """Return all relationships for an object by global_index."""
    service = get_service()
    p = service.parser
    objects = list(p.objects)

    if global_index < 0 or global_index >= len(objects):
        return jsonify({"error": "Object not found"}), 404

    obj = objects[global_index]
    obj_name = obj.get_name() or obj.get_display_name()
    obj_template_name = obj.attributes.get("name")

    from nagios_model import REFERENCE_FIELDS

    obj_to_index = {id(o): idx for idx, o in enumerate(objects)}

    # --- Outgoing / Incoming references ---
    outgoing = _collect_outgoing_refs(obj, global_index, objects, REFERENCE_FIELDS)
    obj_identity = {"name": obj_name, "template_name": obj_template_name}
    incoming = _collect_incoming_refs(obj, obj_identity, global_index,
                                     objects, REFERENCE_FIELDS)

    # --- Dependency rules ---
    dep_out, dep_in = _collect_dependency_rules(obj, obj_name, global_index, objects)
    outgoing.extend(dep_out)
    incoming.extend(dep_in)

    # --- Escalation rules ---
    incoming.extend(_collect_escalation_rules(obj, obj_name, objects))

    # --- Services via hostgroup ---
    incoming.extend(_collect_service_bindings(obj, obj_name, objects))

    # --- Members ---
    members, transitive_summary = _collect_group_members(
        obj, obj_name, global_index, objects,
    )

    # --- Member-of ---
    member_of = _collect_member_of(obj, obj_name, objects)

    # --- Parent hosts ---
    parent_hosts = None
    if obj.object_type == "host" and obj.attributes.get("parents", "").strip():
        parent_hosts = _build_parent_tree(obj, objects, obj_to_index)

    result = {
        "outgoing": outgoing,
        "incoming": incoming,
        "members": members,
        "member_of": member_of,
        "parent_hosts": parent_hosts,
    }
    if transitive_summary:
        result["transitive_summary"] = transitive_summary

    return jsonify(result)


def _collect_dependency_rules(obj, obj_name, global_index, objects):
    """Dispatch to host or service dependency rule collectors."""
    if obj.object_type == "host":
        return _collect_host_dependency_rules(obj_name, global_index, objects)
    if obj.object_type == "service":
        host_name = obj.attributes.get("host_name")
        if host_name:
            return _collect_service_dependency_rules(obj_name, host_name, objects)
    return [], []


def _collect_escalation_rules(obj, obj_name, objects):
    """Dispatch to host or service escalation rule collectors."""
    if obj.object_type == "host":
        return _collect_host_escalation_rules(obj_name, objects)
    if obj.object_type == "service":
        host_name = obj.attributes.get("host_name")
        if host_name:
            return _collect_service_escalation_rules(obj_name, host_name, objects)
    return []


def _collect_service_bindings(obj, obj_name, objects):
    """Dispatch to hostgroup or host service binding collectors."""
    if obj.object_type == "hostgroup":
        return _collect_hostgroup_service_bindings(obj_name, objects)
    if obj.object_type == "host":
        return _collect_host_service_bindings_via_hostgroup(obj_name, objects)
    return []


def _collect_member_of(obj, obj_name, objects):
    """Dispatch to the appropriate member-of collector by object type."""
    if obj.object_type == "host":
        return _collect_host_member_of(obj, obj_name, objects)
    if obj.object_type == "service":
        return _collect_service_member_of(obj, objects)
    if obj.object_type == "contact":
        return _collect_contact_member_of(obj, objects)
    return []
