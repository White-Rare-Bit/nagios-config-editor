"""
Nagios Domain Model

Single source of truth for domain metadata, object representation,
and shared formatting utilities.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# Canonical object type → primary name field mapping
NAME_FIELDS: Dict[str, str] = {
    'host': 'host_name',
    'hostgroup': 'hostgroup_name',
    'service': 'service_description',
    'servicegroup': 'servicegroup_name',
    'contact': 'contact_name',
    'contactgroup': 'contactgroup_name',
    'command': 'command_name',
    'timeperiod': 'timeperiod_name',
    'servicedependency': 'service_description',
    'hostdependency': 'host_name',
    'serviceescalation': 'service_description',
    'hostescalation': 'host_name',
}

# Attribute sort order for formatting (name fields first, then alphabetical)
ATTRIBUTE_SORT_ORDER: List[str] = [
    'host_name', 'hostgroup_name', 'service_description',
    'servicegroup_name', 'contact_name', 'contactgroup_name',
    'command_name', 'timeperiod_name', 'name', 'use'
]

# Special directive fields with semantic meaning (not references)
# These affect how objects are interpreted by Nagios or this editor
SPECIAL_DIRECTIVES: Dict[str, str] = {
    'register': "If '0', object is a template and won't be registered with Nagios. Default '1'.",
    'name': "Template name for inheritance. Objects with 'name' can be referenced via 'use'.",
    'use': "Comma-separated list of template names to inherit from.",
    'address': "IP address or hostname for hosts. Used by check commands via $HOSTADDRESS$ macro.",
    'alias': "Human-readable description/alias for the object.",
    'notes': "Informational notes about the object.",
    'notes_url': "URL for additional notes about the object.",
    'action_url': "URL for actions related to the object.",
}

# Reference fields mapping: field name → object type it references
# None means type depends on context (template references, group members)
REFERENCE_FIELDS: Dict[str, Optional[str]] = {
    # Host references
    'host_name': 'host',
    'dependent_host_name': 'host',
    'master_host_name': 'host',
    'parents': 'host',

    # Hostgroup references
    'hostgroup_name': 'hostgroup',
    'hostgroups': 'hostgroup',
    'dependent_hostgroup_name': 'hostgroup',
    'master_hostgroup_name': 'hostgroup',
    'hostgroup_members': 'hostgroup',

    # Service references
    'service_description': 'service',
    'dependent_service_description': 'service',
    'master_service_description': 'service',

    # Servicegroup references
    'servicegroup_name': 'servicegroup',
    'servicegroups': 'servicegroup',
    'servicegroup_members': 'servicegroup',

    # Contact references
    'contact_name': 'contact',
    'contacts': 'contact',
    'escalation_contacts': 'contact',

    # Contactgroup references
    'contactgroup_name': 'contactgroup',
    'contact_groups': 'contactgroup',
    'contactgroups': 'contactgroup',
    'escalation_contact_groups': 'contactgroup',
    'contactgroup_members': 'contactgroup',

    # Command references
    'check_command': 'command',
    'event_handler': 'command',
    'notification_commands': 'command',
    'host_notification_commands': 'command',
    'service_notification_commands': 'command',
    'obsess_over_host_command': 'command',
    'obsess_over_service_command': 'command',
    'ocsp_command': 'command',
    'ochp_command': 'command',
    'global_host_event_handler': 'command',
    'global_service_event_handler': 'command',

    # Timeperiod references
    'timeperiod_name': 'timeperiod',
    'check_period': 'timeperiod',
    'notification_period': 'timeperiod',
    'host_notification_period': 'timeperiod',
    'service_notification_period': 'timeperiod',
    'escalation_period': 'timeperiod',
    'dependency_period': 'timeperiod',
    'exclude': 'timeperiod',

    # Template references (type depends on context)
    'use': None,

    # Group members (type depends on context)
    'members': None,
}


@dataclass
class OperationResult:
    """Unified result type for fallible operations."""
    success: bool
    error: Optional[str] = None
    data: Optional[Any] = None


@dataclass
class NagiosObject:
    """Represents a single Nagios configuration object."""
    object_type: str
    attributes: Dict[str, str] = field(default_factory=dict)
    source_file: str = ""
    line_number: int = 0

    def get_name(self) -> Optional[str]:
        """Get the primary name/identifier for this object."""
        name_field = NAME_FIELDS.get(self.object_type)
        if name_field:
            value = self.attributes.get(name_field)
            if value:
                return value
        # Fallback: try 'name' field (used by templates) and other common fields
        for field_name in ['name', 'host_name', 'service_description', 'contact_name']:
            if field_name in self.attributes and self.attributes[field_name]:
                return self.attributes[field_name]
        return None

    def get_display_name(self) -> str:
        """Get a display-friendly name for this object.

        For services and service-related objects, includes context (host/hostgroup)
        to distinguish services with the same service_description on different targets.
        """
        name = self.get_name()

        # For services and service-related objects, include context
        if self.object_type in ('service', 'servicedependency', 'serviceescalation'):
            desc = self.attributes.get('service_description', '')
            if desc:
                # Check for host or hostgroup context
                # Filter out exclusions (items starting with !) from host_name
                host_raw = self.attributes.get('host_name', '')
                hosts = [h.strip() for h in host_raw.split(',') if h.strip() and not h.strip().startswith('!')]
                hostgroup = self.attributes.get('hostgroup_name', '')

                if hosts:
                    # Use actual hosts (not exclusions)
                    return f"{desc} on {','.join(hosts)}"
                elif hostgroup:
                    return f"{desc} on {hostgroup}"
                return desc  # No context available

        if name:
            return name
        return f"[unnamed {self.object_type}]"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'object_type': self.object_type,
            'attributes': self.attributes,
            'source_file': self.source_file,
            'line_number': self.line_number,
            'name': self.get_name(),
            'display_name': self.get_display_name(),
        }


def format_object_block(obj_type: str, attrs: Dict[str, str], indent: str = "    ") -> str:
    """Format a Nagios object definition block.

    Args:
        obj_type: The object type (host, service, etc.)
        attrs: Dictionary of attribute key-value pairs
        indent: Indentation string (default 4 spaces)

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
        lines.append(f"{indent}{key:<{padding}}{value}")

    lines.append("}")
    return '\n'.join(lines)


def get_object_name(obj_type: str, attributes: Dict[str, str]) -> str:
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
    if 'name' in attributes:
        return attributes['name']

    return ''
