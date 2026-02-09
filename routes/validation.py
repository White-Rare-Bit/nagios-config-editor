"""Validation and health-check routes."""

import re

from flask import Blueprint, jsonify
from nagios_model import NAME_FIELDS, REFERENCE_FIELDS, REQUIRED_FIELDS
from validator import NagiosValidator
from .helpers import get_service, get_config

bp = Blueprint('validation', __name__)


@bp.route('/api/reload', methods=['POST'])
def api_reload():
    """Reload configuration from disk."""
    service = get_service()
    p = service.reload()
    return jsonify({
        'success': True,
        'objects': len(service.get_objects()),
        'files': len(p.files_parsed)
    })


@bp.route('/api/summary')
def api_summary():
    """Get configuration summary."""
    service = get_service()
    p = service.parser
    return jsonify({
        'summary': p.get_summary(),
        'files': p.get_files(),
        'total_objects': len(service.get_objects())
    })


@bp.route('/api/validate', methods=['POST'])
def api_validate():
    """Validate Nagios configuration."""
    config = get_config()
    validator = NagiosValidator(config['nagios_bin'], config['nagios_cfg'])
    result = validator.validate()
    return jsonify(result.to_dict())


@bp.route('/api/validate/check', methods=['GET'])
def api_validate_check():
    """Check if Nagios binary is available and valid.

    Returns verification status including:
    - Whether binary exists and is executable
    - Whether binary is actually Nagios (verified via version check)
    - Version string if verification succeeded
    """
    config = get_config()
    validator = NagiosValidator(config['nagios_bin'], config['nagios_cfg'])

    # First check existence
    exists, exists_message = validator.check_binary_exists()

    # If binary exists, verify it's actually Nagios
    verified = False
    version = None
    verify_message = exists_message

    if exists:
        result = validator.verify_binary()
        verified = result.success
        version = result.data
        verify_message = result.error if result.error else "Valid Nagios binary"

    return jsonify({
        'available': exists,
        'verified': verified,
        'version': version,
        'message': verify_message,
        'nagios_bin': config['nagios_bin'],
        'nagios_cfg': config['nagios_cfg']
    })


@bp.route('/api/constants')
def api_constants():
    """Return domain metadata constants (single source of truth)."""
    # Convert REQUIRED_FIELDS tuples to lists for JSON serialization
    required_fields_json = {}
    for obj_type, reqs in REQUIRED_FIELDS.items():
        converted = []
        for req in reqs:
            if isinstance(req, tuple):
                converted.append(list(req))  # OR condition
            else:
                converted.append(req)
        required_fields_json[obj_type] = converted

    return jsonify({
        'name_fields': NAME_FIELDS,
        'required_fields': required_fields_json,
        'reference_fields': REFERENCE_FIELDS,
    })


@bp.route('/api/health-check')
def api_health_check():
    """Analyze configuration for potential issues."""
    from .health_checks import run_all_checks, build_template_lookup

    service = get_service()
    p = service.parser
    objects = p.objects

    obj_to_index = {id(obj): idx for idx, obj in enumerate(objects)}
    template_lookup = build_template_lookup(objects)

    issues = run_all_checks(objects, obj_to_index, template_lookup)

    summary = {
        'total_issues': len(issues),
        'errors': len([i for i in issues if i['severity'] == 'error']),
        'warnings': len([i for i in issues if i['severity'] == 'warning']),
        'info': len([i for i in issues if i['severity'] == 'info']),
    }

    return jsonify({
        'issues': issues,
        'summary': summary
    })


@bp.route('/api/analysis/orphans')
def api_analysis_orphans():
    """Detect orphan objects - objects not referenced by any other object.

    An orphan is a non-template object whose name does not appear in any
    reference field of any other object. Special cases:
    - Hosts with 'hostgroups' attr (direct or inherited) are considered in-use
    - Services with 'host_name' or 'hostgroup_name' (direct or inherited) are in-use
    - Services with 'servicegroups' attr (direct or inherited) are in-use
    - Templates (register=0) are excluded from analysis entirely
    """
    service = get_service()
    objects = service.get_objects()

    # Build template lookup for inheritance resolution
    template_lookup = {}
    for obj in objects:
        tmpl_name = obj.attributes.get('name')
        if tmpl_name:
            template_lookup[(obj.object_type, tmpl_name)] = obj

    def has_attr_in_chain(obj, attr_name, visited=None):
        """Check if attribute exists in object or its template chain."""
        if visited is None:
            visited = set()
        if attr_name in obj.attributes:
            return True
        use_val = obj.attributes.get('use', '')
        if not use_val:
            return False
        for tmpl_name in [t.strip() for t in use_val.split(',') if t.strip()]:
            if tmpl_name in visited:
                continue
            visited.add(tmpl_name)
            tmpl = template_lookup.get((obj.object_type, tmpl_name))
            if tmpl and has_attr_in_chain(tmpl, attr_name, visited):
                return True
        return False

    def strip_prefix(s):
        """Strip +/! prefixes used in Nagios additive/exclusion syntax."""
        return s.strip().lstrip('+!').strip()

    # Phase 1: Build reference sets using REFERENCE_FIELDS as single source of truth
    command_fields = {f for f, t in REFERENCE_FIELDS.items() if t == 'command'}

    referenced_names = {
        'host': set(), 'hostgroup': set(), 'service': set(),
        'servicegroup': set(), 'contact': set(), 'contactgroup': set(),
        'command': set(), 'timeperiod': set()
    }

    for obj in objects:
        attrs = obj.attributes
        own_name_field = NAME_FIELDS.get(obj.object_type)

        for field, target_type in REFERENCE_FIELDS.items():
            if field not in attrs:
                continue

            value = attrs[field]

            # Resolve target type for context-dependent fields
            if field == 'use':
                resolved_type = obj.object_type
            elif field == 'members':
                if obj.object_type == 'hostgroup':
                    resolved_type = 'host'
                elif obj.object_type == 'contactgroup':
                    resolved_type = 'contact'
                elif obj.object_type == 'servicegroup':
                    resolved_type = 'service'
                else:
                    continue
            else:
                resolved_type = target_type

            if resolved_type not in referenced_names:
                continue

            # Skip identity fields (e.g. host_name ON a host is its own name)
            if field == own_name_field:
                continue

            # Parse the value: comma-separated, with optional +/! prefixes
            for part in value.split(','):
                part = part.strip().lstrip('+!').strip()
                if not part:
                    continue
                # For command fields, strip arguments after !
                if field in command_fields:
                    part = part.split('!')[0].strip()
                if part:
                    referenced_names[resolved_type].add(part)

        # Auto-reference: hosts with hostgroups attr are in use
        if obj.object_type == 'host' and has_attr_in_chain(obj, 'hostgroups'):
            host_name = obj.get_name()
            if host_name:
                referenced_names['host'].add(host_name.strip())

        # Auto-reference: services with host_name/hostgroup_name are in use
        if obj.object_type == 'service':
            if (has_attr_in_chain(obj, 'host_name') or
                    has_attr_in_chain(obj, 'hostgroup_name')):
                svc_name = obj.get_name()
                if svc_name:
                    referenced_names['service'].add(svc_name.strip())

        # Auto-reference: services with servicegroups are in use
        if obj.object_type == 'service' and has_attr_in_chain(
                obj, 'servicegroups'):
            svc_name = obj.get_name()
            if svc_name:
                referenced_names['service'].add(svc_name.strip())

    # Phase 2: Find orphans
    orphan_indices = []
    by_type = {}
    for global_idx, obj in enumerate(objects):
        # Skip templates
        if obj.attributes.get('register', '1') == '0':
            continue

        obj_name = obj.get_name()
        attr_name = obj.attributes.get('name')
        refs = referenced_names.get(obj.object_type)
        if refs is None:
            continue

        is_referenced = ((obj_name and obj_name in refs) or
                         (attr_name and attr_name in refs))
        if not is_referenced:
            orphan_indices.append(global_idx)
            by_type[obj.object_type] = by_type.get(obj.object_type, 0) + 1

    return jsonify({
        'orphan_indices': orphan_indices,
        'summary': {
            'total_orphans': len(orphan_indices),
            'by_type': by_type
        }
    })


@bp.route('/api/analysis/template-suggestions')
def api_analysis_template_suggestions():
    """Suggest template consolidation opportunities.

    Finds groups of 3+ objects of the same type that share identical
    non-identity attributes and don't already use a template.
    """
    service = get_service()
    objects = service.get_objects()

    identity_fields = {
        'host_name', 'service_description', 'name', 'contact_name',
        'alias', 'address', 'hostgroup_name', 'servicegroup_name',
        'contactgroup_name', 'command_name', 'timeperiod_name'
    }

    # Group objects by type, tracking global indices
    objects_by_type = {}  # type -> [(global_index, obj)]
    for idx, obj in enumerate(objects):
        objects_by_type.setdefault(obj.object_type, []).append((idx, obj))

    suggestions = []

    for obj_type, type_entries in objects_by_type.items():
        if len(type_entries) < 3:
            continue
        if obj_type in ('timeperiod', 'command'):
            continue

        # Build signatures
        signatures = {}  # signature -> [(global_index, obj)]

        for idx, obj in type_entries:
            if obj.attributes.get('use') or obj.attributes.get('register') == '0':
                continue

            attr_pairs = []
            for key, value in sorted(obj.attributes.items()):
                if key not in identity_fields and key != 'register':
                    attr_pairs.append(f'{key}={value}')

            if not attr_pairs:
                continue

            signature = '|'.join(attr_pairs)

            if signature not in signatures:
                signatures[signature] = []
            signatures[signature].append((idx, obj))

        for signature, matching_entries in signatures.items():
            if len(matching_entries) < 3:
                continue

            # Parse signature back to attributes
            attrs = {}
            for pair in signature.split('|'):
                eq_idx = pair.index('=')
                key = pair[:eq_idx]
                value = pair[eq_idx + 1:]
                attrs[key] = value

            matching_objects = [obj for _, obj in matching_entries]
            suggested_name = _generate_template_name(obj_type, matching_objects, attrs)

            suggestions.append({
                'type': obj_type,
                'suggested_name': suggested_name,
                'attributes': attrs,
                'object_indices': [idx for idx, _ in matching_entries],
                'count': len(matching_entries),
                'attr_count': len(attrs)
            })

    # Sort by impact (count * attr_count) descending
    suggestions.sort(key=lambda s: s['count'] * s['attr_count'], reverse=True)

    return jsonify({
        'suggestions': suggestions
    })


def _generate_template_name(obj_type, objects, attrs):
    """Generate a suggested template name from object patterns."""
    from nagios_model import NAME_FIELDS

    # Try common prefix from object names
    name_field = NAME_FIELDS.get(obj_type)
    names = []
    for obj in objects:
        n = obj.attributes.get(name_field, '') if name_field else ''
        if not n:
            n = obj.attributes.get('name', '')
        if n:
            names.append(n)

    if names:
        prefix = names[0]
        for name in names[1:]:
            while prefix and not name.startswith(prefix):
                prefix = prefix[:-1]
        if prefix and len(prefix) >= 3:
            # Clean trailing dashes, underscores, digits
            prefix = re.sub(r'[-_\d]+$', '', prefix)
            if len(prefix) >= 3:
                return f'{prefix}-{obj_type}-template'

    # Fallback: use check_command name
    if 'check_command' in attrs:
        cmd = attrs['check_command'].split('!')[0]
        return f'{cmd}-{obj_type}-template'

    return f'common-{obj_type}-template'
