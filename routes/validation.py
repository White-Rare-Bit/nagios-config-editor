"""Validation and health-check routes."""

from flask import Blueprint, jsonify
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


@bp.route('/api/health-check')
def api_health_check():
    """Analyze configuration for potential issues."""
    service = get_service()
    p = service.parser

    issues = []
    reported_missing = set()  # Track reported missing objects to avoid duplicates

    # Build lookup sets for quick reference checking
    hosts = set()
    hostgroups = set()
    services = set()
    servicegroups = set()
    contacts = set()
    contactgroups = set()
    commands = set()
    timeperiods = set()
    templates = {}  # type -> set of template names

    for obj in service.get_objects():
        name = obj.get_name()
        if not name:
            continue

        # Check if this is a template (register=0) - templates should not be in lookup sets
        # because they are not real monitored objects, just configuration blueprints
        is_template = obj.attributes.get('register', '1') == '0'

        # Only add non-template objects to lookup sets for reference validation
        if not is_template:
            if obj.object_type == 'host':
                hosts.add(name)
            elif obj.object_type == 'hostgroup':
                hostgroups.add(name)
            elif obj.object_type == 'service':
                services.add(name)
            elif obj.object_type == 'servicegroup':
                servicegroups.add(name)
            elif obj.object_type == 'contact':
                contacts.add(name)
            elif obj.object_type == 'contactgroup':
                contactgroups.add(name)
            elif obj.object_type == 'command':
                commands.add(name)
            elif obj.object_type == 'timeperiod':
                timeperiods.add(name)

        # Track templates (objects with 'name' attribute and register 0)
        if 'name' in obj.attributes:
            if obj.object_type not in templates:
                templates[obj.object_type] = set()
            templates[obj.object_type].add(obj.attributes['name'])

    # Check for issues
    for obj in p.objects:
        # Use get_name() for stable identity (matches o.name in frontend)
        # This ensures lookups work even if display_name format changes
        obj_name = obj.get_name() or obj.get_display_name()

        # 1. Check for orphan services (referencing non-existent hosts)
        if obj.object_type == 'service':
            host_ref = obj.attributes.get('host_name', '')
            if host_ref and host_ref != '*':
                for h in host_ref.split(','):
                    h = h.strip()
                    # Skip negated hosts (e.g., !exclude_host) - these are exclusions, not references
                    if h.startswith('!'):
                        continue
                    if h and h not in hosts:
                        issues.append({
                            'type': 'orphan_service',
                            'severity': 'error',
                            'object': obj_name,
                            'object_type': obj.object_type,
                            'file': obj.source_file,
                            'message': f'Service references non-existent host: {h}'
                        })

            # 1b. Check for services referencing non-existent hostgroups
            hostgroup_ref = obj.attributes.get('hostgroup_name', '')
            if hostgroup_ref:
                for hg in hostgroup_ref.split(','):
                    hg = hg.strip().lstrip('+!').strip()  # Strip additive/exclusion prefixes
                    if hg and hg not in hostgroups:
                        issues.append({
                            'type': 'missing_hostgroup',
                            'severity': 'error',
                            'object': obj_name,
                            'object_type': obj.object_type,
                            'file': obj.source_file,
                            'message': f'Service references non-existent hostgroup: {hg}'
                        })

        # 1c. Check for hosts with missing parents
        if obj.object_type == 'host':
            # Skip templates
            if obj.attributes.get('register', '1') != '0':
                parents_ref = obj.attributes.get('parents', '')
                if parents_ref:
                    for parent in parents_ref.split(','):
                        parent = parent.strip()
                        if parent and parent not in hosts:
                            issues.append({
                                'type': 'missing_parent',
                                'severity': 'warning',
                                'object': obj_name,
                                'object_type': obj.object_type,
                                'file': obj.source_file,
                                'message': f'Host references non-existent parent: {parent}'
                            })

        # 2. Check for missing templates
        if 'use' in obj.attributes:
            template_refs = [t.strip() for t in obj.attributes['use'].split(',')]
            type_templates = templates.get(obj.object_type, set())
            for t in template_refs:
                if t and t not in type_templates:
                    issues.append({
                        'type': 'missing_template',
                        'severity': 'error',
                        'object': obj_name,
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'message': f'References undefined {obj.object_type} template: {t}'
                    })

        # 3. Check for missing commands
        # Severity: error (missing command would cause Nagios config verification failure)
        for cmd_field in ['check_command', 'event_handler',
                          'host_notification_commands', 'service_notification_commands']:
            if cmd_field in obj.attributes:
                cmd_ref = obj.attributes[cmd_field].split('!')[0]  # Get command without args
                if cmd_ref and cmd_ref not in commands:
                    issues.append({
                        'type': 'missing_command',
                        'severity': 'error',
                        'object': obj_name,
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'message': f'References non-existent command: {cmd_ref}'
                    })

        # 4. Check for missing timeperiods
        for tp_field in ['check_period', 'notification_period']:
            if tp_field in obj.attributes:
                tp_ref = obj.attributes[tp_field]
                if tp_ref and tp_ref not in timeperiods:
                    issues.append({
                        'type': 'missing_timeperiod',
                        'severity': 'warning',
                        'object': obj_name,
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'message': f'References non-existent timeperiod: {tp_ref}'
                    })

        # 5. Check for missing contacts/contactgroups
        if 'contacts' in obj.attributes:
            for c in obj.attributes['contacts'].split(','):
                c = c.strip().lstrip('+!').strip()
                if c and c not in contacts:
                    issues.append({
                        'type': 'missing_contact',
                        'severity': 'warning',
                        'object': obj_name,
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'message': f'References non-existent contact: {c}'
                    })

        if 'contact_groups' in obj.attributes:
            for cg in obj.attributes['contact_groups'].split(','):
                cg = cg.strip().lstrip('+!').strip()
                if cg and cg not in contactgroups:
                    issues.append({
                        'type': 'missing_contactgroup',
                        'severity': 'warning',
                        'object': obj_name,
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'message': f'References non-existent contact group: {cg}'
                    })

        # 6. Check for missing hostgroups/servicegroups
        if 'hostgroups' in obj.attributes:
            for hg in obj.attributes['hostgroups'].split(','):
                hg = hg.strip().lstrip('+!').strip()
                if hg and hg not in hostgroups:
                    issues.append({
                        'type': 'missing_hostgroup',
                        'severity': 'warning',
                        'object': obj_name,
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'message': f'References non-existent hostgroup: {hg}'
                    })

        if 'servicegroups' in obj.attributes:
            for sg in obj.attributes['servicegroups'].split(','):
                sg = sg.strip().lstrip('+!').strip()
                if sg and sg not in servicegroups:
                    issues.append({
                        'type': 'missing_servicegroup',
                        'severity': 'warning',
                        'object': obj_name,
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'message': f'References non-existent servicegroup: {sg}'
                    })

    # 7. Check for empty groups
    for obj in p.objects:
        if obj.object_type in ['hostgroup', 'servicegroup', 'contactgroup']:
            # Check if group has members defined
            has_members = 'members' in obj.attributes
            if obj.object_type == 'hostgroup':
                has_members = has_members or 'hostgroup_members' in obj.attributes
            elif obj.object_type == 'servicegroup':
                has_members = has_members or 'servicegroup_members' in obj.attributes
            elif obj.object_type == 'contactgroup':
                has_members = has_members or 'contactgroup_members' in obj.attributes

            if not has_members:
                # Check if anything references this group
                group_name = obj.get_name()
                is_used = False

                # Fields that can reference this group type (handles +prefix)
                if obj.object_type == 'hostgroup':
                    ref_fields = ['hostgroups', 'hostgroup_name', 'hostgroup_members']
                elif obj.object_type == 'servicegroup':
                    ref_fields = ['servicegroups', 'servicegroup_name', 'servicegroup_members']
                else:  # contactgroup
                    ref_fields = ['contact_groups', 'contactgroup_name', 'contactgroup_members']

                for other_obj in p.objects:
                    # Skip checking the group against itself
                    if other_obj is obj:
                        continue
                    for field in ref_fields:
                        if field in other_obj.attributes:
                            # Strip + prefix and whitespace from each referenced group
                            referenced_groups = [g.strip().lstrip('+!').strip() for g in other_obj.attributes[field].split(',')]
                            if group_name in referenced_groups:
                                is_used = True
                                break
                    if is_used:
                        break

                if not is_used:
                    issues.append({
                        'type': 'empty_group',
                        'severity': 'warning',
                        'object': obj.get_name() or obj.get_display_name(),
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'message': 'Group has no members and is not referenced'
                    })

    # 8. Check for unused templates
    for obj_type, tmpl_names in templates.items():
        for tmpl_name in tmpl_names:
            is_used = False
            for obj in p.objects:
                if obj.object_type == obj_type and 'use' in obj.attributes:
                    if tmpl_name in [t.strip() for t in obj.attributes['use'].split(',')]:
                        is_used = True
                        break
            if not is_used:
                # Find the template object for file info
                for obj in p.objects:
                    if (obj.object_type == obj_type and
                        obj.attributes.get('name') == tmpl_name):
                        issues.append({
                            'type': 'unused_template',
                            'severity': 'warning',
                            'object': tmpl_name,
                            'object_type': obj_type,
                            'file': obj.source_file,
                            'message': f'Template is not used by any {obj_type}'
                        })
                        break

    # 9. Check for duplicate dependencies
    # Build signature for each dependency to detect duplicates
    dep_signatures = {}
    for obj in p.objects:
        if obj.object_type in ['hostdependency', 'servicedependency']:
            # Build a signature from key fields
            sig_parts = []
            for field in ['dependent_host_name', 'dependent_hostgroup_name',
                         'dependent_service_description', 'host_name',
                         'hostgroup_name', 'service_description']:
                val = obj.attributes.get(field, '')
                if val:
                    sig_parts.append(f'{field}={val}')
            sig = '|'.join(sorted(sig_parts))

            if sig in dep_signatures:
                # Found duplicate
                orig = dep_signatures[sig]
                issues.append({
                    'type': 'duplicate_dependency',
                    'severity': 'warning',
                    'object': obj.get_name() or obj.get_display_name(),
                    'object_type': obj.object_type,
                    'file': obj.source_file,
                    'message': f'Duplicate dependency rule (also defined in {orig["file"]})'
                })
            else:
                dep_signatures[sig] = {'file': obj.source_file, 'obj': obj}

    # Summary
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
