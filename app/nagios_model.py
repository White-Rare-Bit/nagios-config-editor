"""Nagios Domain Model

Single source of truth for domain metadata, object representation,
and shared formatting utilities.
"""

from dataclasses import dataclass, field
from typing import Any

# Canonical object type → primary name field mapping
NAME_FIELDS: dict[str, str] = {
    "host": "host_name",
    "hostgroup": "hostgroup_name",
    "service": "service_description",
    "servicegroup": "servicegroup_name",
    "contact": "contact_name",
    "contactgroup": "contactgroup_name",
    "command": "command_name",
    "timeperiod": "timeperiod_name",
    "servicedependency": "service_description",
    "hostdependency": "host_name",
    "serviceescalation": "service_description",
    "hostescalation": "host_name",
    "hostextinfo": "host_name",
    "serviceextinfo": "service_description",
    "module": "module_name",
}


def is_template_object(obj) -> bool:
    """Check if a NagiosObject is a template.

    An object is a template if:
    - register=0 is set explicitly, OR
    - It has a 'name' attribute but lacks its identity field

    This matches Nagios behavior: objects with 'name' but no identity
    field (e.g. host_name) never enter the registration skiplist.
    """
    if obj.attributes.get("register", "1") == "0":
        return True
    if "name" not in obj.attributes:
        return False
    identity_field = NAME_FIELDS.get(obj.object_type)
    return bool(identity_field and identity_field not in obj.attributes)


# C-05: Required fields per object type for validation
# Each entry is a list of field requirements:
# - String: field is required
# - Tuple of strings: at least one of these fields must be present (OR condition)
# Note: Templates (register=0) require 'name' instead of the type-specific name field
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

# Attribute sort order for formatting (name fields first, then alphabetical)
ATTRIBUTE_SORT_ORDER: list[str] = [
    "host_name", "hostgroup_name", "service_description",
    "servicegroup_name", "contact_name", "contactgroup_name",
    "command_name", "timeperiod_name", "name", "use",
]

# Special directive fields with semantic meaning (not references)
# These affect how objects are interpreted by Nagios or this editor
SPECIAL_DIRECTIVES: dict[str, str] = {
    "register": "If '0', object is a template and won't be registered with Nagios. Default '1'.",
    "name": "Template name for inheritance. Objects with 'name' can be referenced via 'use'.",
    "use": "Comma-separated list of template names to inherit from.",
    "address": "IP address or hostname for hosts. Used by check commands via $HOSTADDRESS$ macro.",
    "alias": "Human-readable description/alias for the object.",
    "notes": "Informational notes about the object.",
    "notes_url": "URL for additional notes about the object.",
    "action_url": "URL for actions related to the object.",
}

# Directive aliases per Nagios Core source (xodtemplate.c).
# Maps (object_type, alias) -> canonical_name. These aliases are context-dependent:
# e.g., "hostgroups" is an alias for "hostgroup_name" on services, but on hosts
# it's a real field meaning "which hostgroups this host belongs to."
_SERVICE_LIKE_TYPES = frozenset({
    "service", "servicedependency", "serviceescalation", "serviceextinfo",
})
_HOST_REF_TYPES = frozenset({
    "service", "servicedependency", "serviceescalation", "serviceextinfo",
    "hostdependency", "hostescalation", "hostextinfo",
})

ATTRIBUTE_ALIASES: dict[tuple[str, str], str] = {}

# host/hosts -> host_name (on services, dependencies, escalations, extinfo)
for _t in _HOST_REF_TYPES:
    ATTRIBUTE_ALIASES[(_t, "host")] = "host_name"
    ATTRIBUTE_ALIASES[(_t, "hosts")] = "host_name"

# hostgroup/hostgroups -> hostgroup_name (on service-like types only)
for _t in _SERVICE_LIKE_TYPES:
    ATTRIBUTE_ALIASES[(_t, "hostgroup")] = "hostgroup_name"
    ATTRIBUTE_ALIASES[(_t, "hostgroups")] = "hostgroup_name"

# description -> service_description (on service-like types)
for _t in _SERVICE_LIKE_TYPES:
    ATTRIBUTE_ALIASES[(_t, "description")] = "service_description"


def normalize_attribute_name(object_type: str, attr_name: str) -> str:
    """Normalize a directive name using Nagios aliases.

    Returns the canonical name if an alias exists for the given object type,
    otherwise returns the original name unchanged.
    """
    return ATTRIBUTE_ALIASES.get((object_type, attr_name), attr_name)


# Implied inheritance: fields auto-inherited from associated objects.
# Key: (child_type, parent_type, parent_key_field)
# Value: list of (child_field, parent_field) tuples
# parent_key_field is the attribute on the child that references the parent
#
# Per the Nagios spec, contact fields are coupled: if a child defines
# EITHER contacts or contact_groups (directly or via template), NEITHER
# is inherited from the parent. This is enforced via IMPLIED_CONTACT_FIELDS.
IMPLIED_INHERITANCE = {
    ("service", "host", "host_name"): [
        ("contacts", "contacts"),
        ("contact_groups", "contact_groups"),
        ("notification_interval", "notification_interval"),
        ("notification_period", "notification_period"),
    ],
    ("hostescalation", "host", "host_name"): [
        ("contacts", "contacts"),
        ("contact_groups", "contact_groups"),
        ("notification_interval", "notification_interval"),
        ("escalation_period", "notification_period"),  # Field rename
    ],
    ("serviceescalation", "service", "host_name"): [
        ("contacts", "contacts"),
        ("contact_groups", "contact_groups"),
        ("notification_interval", "notification_interval"),
        ("escalation_period", "notification_period"),  # Field rename
    ],
}

# Coupled field groups for implied inheritance: if any field in the group
# is present on the child (after template resolution), none of the group's
# fields are inherited from the parent. Per Nagios spec, defining contacts
# suppresses inheritance of contact_groups and vice versa.
IMPLIED_CONTACT_FIELDS = frozenset({"contacts", "contact_groups"})

# Fields that support + additive inheritance per Nagios Core.
# Only these fields use xodtemplate_get_inherited_string() which handles
# the + prefix. Other fields use xod_inherit_str() (simple override).
ADDITIVE_FIELDS: dict[str, set[str]] = {
    "host": {"parents", "hostgroups", "contact_groups", "contacts"},
    "service": {"parents", "host_name", "hostgroup_name", "servicegroups", "contact_groups", "contacts"},
    "contact": {"host_notification_commands", "service_notification_commands", "contactgroups"},
    "hostgroup": {"members", "hostgroup_members"},
    "servicegroup": {"members", "servicegroup_members"},
    "contactgroup": {"members", "contactgroup_members"},
    "hostescalation": {"contacts", "contact_groups", "host_name", "hostgroup_name"},
    "serviceescalation": {"contacts", "contact_groups", "host_name", "hostgroup_name"},
    "hostdependency": {"host_name", "hostgroup_name", "dependent_host_name", "dependent_hostgroup_name"},
    "servicedependency": {
        "host_name", "hostgroup_name", "service_description", "servicegroup_name",
        "dependent_host_name", "dependent_hostgroup_name",
        "dependent_service_description", "dependent_servicegroup_name",
    },
}

VALID_ATTRIBUTES: dict[str, list[str]] = {
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
    "hostgroup": [
        "hostgroup_name", "alias", "members", "hostgroup_members", "notes",
        "notes_url", "action_url", "use", "name", "register",
    ],
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
    "servicegroup": [
        "servicegroup_name", "alias", "members", "servicegroup_members", "notes",
        "notes_url", "action_url", "use", "name", "register",
    ],
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
    "contactgroup": [
        "contactgroup_name", "alias", "members", "contactgroup_members",
        "use", "name", "register",
    ],
    "command": [
        "command_name", "command_line", "use", "name", "register",
    ],
    "timeperiod": [
        "timeperiod_name", "alias", "sunday", "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "exclude", "use", "name", "register",
    ],
    "servicedependency": [
        "dependent_host_name", "dependent_hostgroup_name", "dependent_service_description",
        "dependent_servicegroup_name", "host_name", "hostgroup_name",
        "service_description", "servicegroup_name", "inherits_parent",
        "execution_failure_criteria", "notification_failure_criteria",
        "dependency_period", "use", "name", "register",
    ],
    "hostdependency": [
        "dependent_host_name", "dependent_hostgroup_name", "host_name", "hostgroup_name",
        "inherits_parent", "execution_failure_criteria", "notification_failure_criteria",
        "dependency_period", "use", "name", "register",
    ],
    "serviceescalation": [
        "host_name", "hostgroup_name", "service_description", "contacts", "contact_groups",
        "first_notification", "last_notification", "notification_interval",
        "escalation_period", "escalation_options", "use", "name", "register",
    ],
    "hostescalation": [
        "host_name", "hostgroup_name", "contacts", "contact_groups",
        "first_notification", "last_notification", "notification_interval",
        "escalation_period", "escalation_options", "use", "name", "register",
    ],
    "hostextinfo": [
        "host_name", "notes", "notes_url", "action_url", "icon_image",
        "icon_image_alt", "vrml_image", "statusmap_image", "2d_coords", "3d_coords",
        "use", "name", "register",
    ],
    "serviceextinfo": [
        "host_name", "service_description", "notes", "notes_url", "action_url",
        "icon_image", "icon_image_alt", "use", "name", "register",
    ],
    "module": [
        "module_name", "module_type", "path", "args", "use", "name", "register",
    ],
}

OBJECT_TYPE_LABELS: dict[str, str] = {
    "host": "Hosts",
    "hostgroup": "Host Groups",
    "service": "Services",
    "servicegroup": "Service Groups",
    "contact": "Contacts",
    "contactgroup": "Contact Groups",
    "command": "Commands",
    "timeperiod": "Time Periods",
    "servicedependency": "Service Dependencies",
    "hostdependency": "Host Dependencies",
    "serviceescalation": "Service Escalations",
    "hostescalation": "Host Escalations",
    "hostextinfo": "Host Extended Info",
    "serviceextinfo": "Service Extended Info",
    "module": "Modules",
}

DEFAULT_ATTRIBUTES: dict[str, dict[str, str]] = {
    "host": {
        "host_name": "", "alias": "", "address": "", "hostgroups": "",
    },
    "service": {
        "service_description": "", "host_name": "", "check_command": "",
        "max_check_attempts": "", "check_period": "", "notification_period": "",
        "contact_groups": "",
    },
    "hostgroup": {"hostgroup_name": "", "alias": ""},
    "servicegroup": {"servicegroup_name": "", "alias": ""},
    "contact": {
        "contact_name": "", "alias": "", "email": "",
        "host_notification_period": "", "service_notification_period": "",
        "host_notification_commands": "", "service_notification_commands": "",
        "host_notification_options": "", "service_notification_options": "",
    },
    "contactgroup": {"contactgroup_name": "", "alias": ""},
    "command": {"command_name": "", "command_line": ""},
    "timeperiod": {"timeperiod_name": "", "alias": ""},
    "servicedependency": {
        "host_name": "", "service_description": "",
        "dependent_host_name": "", "dependent_service_description": "",
    },
    "hostdependency": {"host_name": "", "dependent_host_name": ""},
    "serviceescalation": {
        "host_name": "", "service_description": "", "contact_groups": "",
        "first_notification": "", "last_notification": "",
    },
    "hostescalation": {
        "host_name": "", "contact_groups": "",
        "first_notification": "", "last_notification": "",
    },
    "hostextinfo": {"host_name": ""},
    "serviceextinfo": {"host_name": "", "service_description": ""},
    "module": {"module_name": "", "module_type": "", "path": ""},
}

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

GROUP_STRUCTURE: dict[str, dict[str, Any]] = {
    "hostgroup": {
        "name_attr": "hostgroup_name",
        "member_attrs": ["members", "hostgroup_members"],
        "member_of_attr": "hostgroups",
        "member_type": "host",
    },
    "servicegroup": {
        "name_attr": "servicegroup_name",
        "member_attrs": ["members", "servicegroup_members"],
        "member_of_attr": "servicegroups",
        "member_type": "service",
    },
    "contactgroup": {
        "name_attr": "contactgroup_name",
        "member_attrs": ["members", "contactgroup_members"],
        "member_of_attr": "contactgroups",
        "member_type": "contact",
    },
}

# Types whose identity is scoped by host (composite key: host + name)
HOST_SCOPED_TYPES: list[str] = ["service", "serviceescalation", "servicedependency"]

# Attributes that trigger reference/inheritance UI in the editor
REFERENCE_TRIGGER_ATTRS: list[str] = [
    "use", "parents", "hostgroups", "servicegroups", "contactgroups",
    "contact_groups", "host_name", "hostgroup_name", "check_command",
    "event_handler", "check_period", "notification_period", "contacts", "members",
]

# Reference fields mapping: field name → object type it references
# None means type depends on context (template references, group members)
REFERENCE_FIELDS: dict[str, str | None] = {
    # Host references
    "host_name": "host",
    "dependent_host_name": "host",
    "master_host_name": "host",
    "parents": None,  # hosts reference hosts, services reference services

    # Hostgroup references
    "hostgroup_name": "hostgroup",
    "hostgroups": "hostgroup",
    "dependent_hostgroup_name": "hostgroup",
    "master_hostgroup_name": "hostgroup",
    "hostgroup_members": "hostgroup",

    # Service references
    "service_description": "service",
    "dependent_service_description": "service",
    "master_service_description": "service",

    # Servicegroup references
    "servicegroup_name": "servicegroup",
    "servicegroups": "servicegroup",
    "servicegroup_members": "servicegroup",
    "dependent_servicegroup_name": "servicegroup",

    # Contact references
    "contact_name": "contact",
    "contacts": "contact",
    "escalation_contacts": "contact",

    # Contactgroup references
    "contactgroup_name": "contactgroup",
    "contact_groups": "contactgroup",
    "contactgroups": "contactgroup",
    "escalation_contact_groups": "contactgroup",
    "contactgroup_members": "contactgroup",

    # Command references
    "check_command": "command",
    "event_handler": "command",
    "notification_commands": "command",
    "host_notification_commands": "command",
    "service_notification_commands": "command",
    "obsess_over_host_command": "command",
    "obsess_over_service_command": "command",
    "ocsp_command": "command",
    "ochp_command": "command",
    "global_host_event_handler": "command",
    "global_service_event_handler": "command",

    # Timeperiod references
    "timeperiod_name": "timeperiod",
    "check_period": "timeperiod",
    "notification_period": "timeperiod",
    "host_notification_period": "timeperiod",
    "service_notification_period": "timeperiod",
    "escalation_period": "timeperiod",
    "dependency_period": "timeperiod",
    "exclude": "timeperiod",

    # Template references (type depends on context)
    "use": None,

    # Group members (type depends on context)
    "members": None,
}


@dataclass
class OperationResult:
    """Unified result type for fallible operations."""

    success: bool
    error: str | None = None
    data: Any | None = None


@dataclass
class NagiosObject:
    """Represents a single Nagios configuration object."""

    object_type: str
    attributes: dict[str, str] = field(default_factory=dict)
    source_file: str = ""
    line_number: int = 0
    inline_comments: dict[str, str] = field(default_factory=dict)
    is_commented_out: bool = False
    commented_attributes: dict[str, str] = field(default_factory=dict)
    raw_block: str = ""

    def get_name(self) -> str | None:
        """Get the primary name/identifier for this object.

        For escalations and dependencies, includes additional attributes to ensure
        uniqueness when multiple objects target the same service/host.
        """
        name_field = NAME_FIELDS.get(self.object_type)
        base_name = None
        if name_field:
            base_name = self.attributes.get(name_field)

        # For host escalations/dependencies, fall back to hostgroup_name
        if self.object_type in ("hostescalation", "hostdependency"):
            if not base_name:
                base_name = self.attributes.get("hostgroup_name")
            # For hostescalation, append first_notification to ensure uniqueness
            if self.object_type == "hostescalation" and base_name:
                first = self.attributes.get("first_notification", "")
                if first:
                    return f"{base_name}:esc{first}"
            return base_name

        # For service dependencies, append dependent_service_description
        if self.object_type == "servicedependency" and base_name:
            dep_desc = self.attributes.get("dependent_service_description", "")
            if dep_desc:
                return f"{base_name}→{dep_desc}"
            return base_name

        # For service escalations, append first_notification
        if self.object_type == "serviceescalation" and base_name:
            first = self.attributes.get("first_notification", "")
            if first:
                return f"{base_name}:esc{first}"
            return base_name

        if base_name:
            return base_name

        # Fallback: try 'name' field (used by templates) and other common fields
        for field_name in ["name", "host_name", "service_description", "contact_name"]:
            if self.attributes.get(field_name):
                return self.attributes[field_name]
        return None

    def get_display_name(self) -> str:
        """Get a display-friendly name for this object.

        For services and service-related objects, includes context (host/hostgroup)
        to distinguish services with the same service_description on different targets.
        For escalations and dependencies, shows the target host/hostgroup.
        """
        # Commented-out objects: use name from commented attributes if available
        if self.is_commented_out:
            name_field = NAME_FIELDS.get(self.object_type)
            if name_field and self.commented_attributes.get(name_field):
                return f"{self.commented_attributes[name_field]} (commented out)"
            return f"[commented-out {self.object_type}@L{self.line_number}]"

        name = self.get_name()

        # For services and service-related objects, include context
        if self.object_type in ("service", "servicedependency", "serviceescalation"):
            desc = self.attributes.get("service_description", "")
            if desc:
                # Check for host or hostgroup context
                # Filter out exclusions (items starting with !) from host_name
                host_raw = self.attributes.get("host_name", "")
                hosts = [h.strip() for h in host_raw.split(",") if h.strip() and not h.strip().startswith("!")]
                hostgroup = self.attributes.get("hostgroup_name", "")

                # Build base name with context
                if hosts:
                    base = f"{desc} on {','.join(hosts)}"
                elif hostgroup:
                    base = f"{desc} on {hostgroup}"
                else:
                    base = desc

                # Add distinguishing suffix for dependencies and escalations
                if self.object_type == "servicedependency":
                    dep_desc = self.attributes.get("dependent_service_description", "")
                    if dep_desc:
                        return f"{base} → {dep_desc}"
                elif self.object_type == "serviceescalation":
                    first = self.attributes.get("first_notification", "")
                    last = self.attributes.get("last_notification", "0")
                    if first:
                        suffix = f"{first}+" if last == "0" else f"{first}-{last}"
                        return f"{base} (esc {suffix})"

                return base

        # For host escalations and dependencies, show target (host or hostgroup)
        if self.object_type in ("hostescalation", "hostdependency"):
            host = self.attributes.get("host_name", "")
            hostgroup = self.attributes.get("hostgroup_name", "")
            base = host or (f"[{hostgroup}]" if hostgroup else None)
            if base:
                # Add escalation level for hostescalation
                if self.object_type == "hostescalation":
                    first = self.attributes.get("first_notification", "")
                    last = self.attributes.get("last_notification", "0")
                    if first:
                        suffix = f"{first}+" if last == "0" else f"{first}-{last}"
                        return f"{base} (esc {suffix})"
                return base

        if name:
            return name
        return f"[unnamed {self.object_type}]"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "object_type": self.object_type,
            "attributes": self.attributes,
            "source_file": self.source_file,
            "line_number": self.line_number,
            "name": self.get_name(),
            "display_name": self.get_display_name(),
            "is_commented_out": self.is_commented_out,
        }
        if self.inline_comments:
            result["inline_comments"] = self.inline_comments
        if self.commented_attributes:
            result["commented_attributes"] = self.commented_attributes
        return result


def expand_service_hosts(host_name_attr, hostgroup_name_attr, hostgroup_to_hosts, all_hosts=None):
    """Expand a service's effective host list with cross-boundary ! exclusions.

    Matches Nagios Core behavior: ! exclusions in host_name also exclude hosts
    resolved via hostgroup_name. Both fields share a single reject set.

    Args:
        host_name_attr: raw host_name attribute value (comma-separated, may contain ! prefixes)
        hostgroup_name_attr: raw hostgroup_name attribute value (comma-separated, may contain +/! prefixes)
        hostgroup_to_hosts: dict mapping hostgroup name -> set of member host names
        all_hosts: set of all known hosts (required when host_name contains *)

    Returns:
        set of effective host names after applying all exclusions
    """
    included = set()
    excluded = set()

    # Parse host_name: collect inclusions and exclusions
    if host_name_attr:
        if host_name_attr.strip() == "*":
            included = set(all_hosts) if all_hosts else set()
        else:
            for h in host_name_attr.split(","):
                h = h.strip()
                if h.startswith("!"):
                    excluded.add(h[1:].strip())
                elif h:
                    included.add(h)

    # Parse hostgroup_name: expand hostgroups to hosts
    if hostgroup_name_attr:
        for hg in hostgroup_name_attr.split(","):
            hg = hg.strip().lstrip("+!").strip()
            if hg and hg in hostgroup_to_hosts:
                included.update(hostgroup_to_hosts[hg])

    return included - excluded


def format_object_block(obj_type: str, attrs: dict[str, str], indent: str = "    ",
                        inline_comments: dict[str, str] = None) -> str:
    """Format a Nagios object definition block.

    Args:
        obj_type: The object type (host, service, etc.)
        attrs: Dictionary of attribute key-value pairs
        indent: Indentation string (default 4 spaces)
        inline_comments: Optional dict mapping attribute keys to inline comment text.
            When present, the comment is appended as '; comment' after the value.

    Returns:
        Formatted object block string

    """
    lines = [f"define {obj_type} {{"]

    # Sort attributes: name fields first (in canonical order), then alphabetically
    def sort_key(key):
        if key in ATTRIBUTE_SORT_ORDER:
            return (0, ATTRIBUTE_SORT_ORDER.index(key))
        return (1, key)

    sorted_attrs = sorted(attrs.items(), key=lambda x: sort_key(x[0]))

    for key, value in sorted_attrs:
        padding = max(30, len(key) + 1)
        line = f"{indent}{key:<{padding}}{value}"
        if inline_comments and key in inline_comments:
            line += f" ; {inline_comments[key]}"
        lines.append(line)

    lines.append("}")
    return "\n".join(lines)


def get_object_name(obj_type: str, attributes: dict[str, str]) -> str:
    """Get the name of an object based on its type.

    Different object types use different fields for their name.

    Args:
        obj_type: Object type
        attributes: Object attributes dictionary

    Returns:
        Object name, or empty string if not found

    """
    # Try the type-specific field first
    name_field = NAME_FIELDS.get(obj_type)
    if name_field and name_field in attributes:
        return attributes[name_field]

    # Fall back to generic 'name' field (used by templates)
    if "name" in attributes:
        return attributes["name"]

    return ""
