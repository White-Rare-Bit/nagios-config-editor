"""Validation and health-check routes."""

import re

from flask import Blueprint, jsonify
from nagios_model import NAME_FIELDS, REFERENCE_FIELDS
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

    # Build object-to-index map for global_index on every issue
    obj_to_index = {id(obj): idx for idx, obj in enumerate(p.objects)}

    def strip_prefix(s):
        """Strip +/! prefixes used in Nagios additive/exclusion syntax."""
        return s.strip().lstrip('+!').strip()

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

    # Build template lookup for inheritance resolution
    template_lookup = {}
    for obj in service.get_objects():
        tmpl_name = obj.attributes.get('name')
        if tmpl_name:
            template_lookup[(obj.object_type, tmpl_name)] = obj

    def resolve_inherited_attrs(obj, visited=None):
        """Resolve attributes including inherited ones from templates."""
        if visited is None:
            visited = set()
        resolved = {}
        use_templates = obj.attributes.get('use', '')
        if use_templates:
            for tmpl_name in [t.strip() for t in use_templates.split(',') if t.strip()]:
                if tmpl_name not in visited:
                    visited.add(tmpl_name)
                    tmpl = template_lookup.get((obj.object_type, tmpl_name))
                    if tmpl:
                        tmpl_attrs = resolve_inherited_attrs(tmpl, visited)
                        for key, value in tmpl_attrs.items():
                            if key not in ('use', 'name', 'register'):
                                resolved[key] = value
        for key, value in obj.attributes.items():
            resolved[key] = value
        return resolved

    # Build command arg count map: command_name -> max ARG number used
    command_arg_counts = {}
    for obj in service.get_objects():
        if obj.object_type == 'command':
            cmd_name = obj.attributes.get('command_name', '')
            cmd_line = obj.attributes.get('command_line', '')
            arg_matches = re.findall(r'\$ARG(\d+)\$', cmd_line)
            max_arg = max((int(n) for n in arg_matches), default=0)
            command_arg_counts[cmd_name] = max_arg

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
    missing_parents = {}  # parent_name -> [(host_name, file)]
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
                            'global_index': obj_to_index.get(id(obj)),
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
                            'global_index': obj_to_index.get(id(obj)),
                            'message': f'Service references non-existent hostgroup: {hg}'
                        })

        # 1c. Collect missing parent references (consolidated after loop)
        if obj.object_type == 'host':
            if obj.attributes.get('register', '1') != '0':
                parents_ref = obj.attributes.get('parents', '')
                if parents_ref:
                    for parent in parents_ref.split(','):
                        parent = parent.strip()
                        if parent and parent not in hosts:
                            missing_parents.setdefault(parent, []).append(
                                (obj_name, obj.source_file)
                            )

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
                        'global_index': obj_to_index.get(id(obj)),
                        'message': f'References undefined {obj.object_type} template: {t}'
                    })

        # 3. Check for missing commands
        # Severity: error (missing command would cause Nagios config verification failure)
        # check_command/event_handler: single command, args via ! (e.g. check_ping!100.0,20%!500.0,60%)
        # notification_commands: comma-separated list, each can have ! args
        for cmd_field in ['check_command', 'event_handler']:
            if cmd_field in obj.attributes:
                cmd_ref = obj.attributes[cmd_field].split('!')[0].strip()
                if cmd_ref and cmd_ref not in commands:
                    issues.append({
                        'type': 'missing_command',
                        'severity': 'error',
                        'object': obj_name,
                        'object_type': obj.object_type,
                        'file': obj.source_file,
                        'global_index': obj_to_index.get(id(obj)),
                        'message': f'References non-existent command: {cmd_ref}'
                    })

        for cmd_field in ['host_notification_commands', 'service_notification_commands']:
            if cmd_field in obj.attributes:
                for cmd_full in obj.attributes[cmd_field].split(','):
                    cmd_ref = cmd_full.strip().split('!')[0]
                    if cmd_ref and cmd_ref not in commands:
                        issues.append({
                            'type': 'missing_command',
                            'severity': 'error',
                            'object': obj_name,
                            'object_type': obj.object_type,
                            'file': obj.source_file,
                            'global_index': obj_to_index.get(id(obj)),
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
                        'global_index': obj_to_index.get(id(obj)),
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
                        'global_index': obj_to_index.get(id(obj)),
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
                        'global_index': obj_to_index.get(id(obj)),
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
                        'global_index': obj_to_index.get(id(obj)),
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
                        'global_index': obj_to_index.get(id(obj)),
                        'message': f'References non-existent servicegroup: {sg}'
                    })

    # 1c (consolidated). Emit missing parent issues (one per missing parent)
    for parent_name, host_refs in missing_parents.items():
        host_names = [h for h, _ in host_refs]
        first_file = host_refs[0][1]
        if len(host_names) <= 3:
            host_list = ', '.join(host_names)
        else:
            host_list = f'{", ".join(host_names[:3])} and {len(host_names) - 3} more'
        issues.append({
            'type': 'missing_parent',
            'severity': 'warning',
            'object': parent_name,
            'object_type': 'host',
            'file': first_file,
            'global_index': None,  # Consolidated issue, not tied to a single object
            'message': f'Non-existent parent host referenced by: {host_list}'
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
                        'global_index': obj_to_index.get(id(obj)),
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
                            'global_index': obj_to_index.get(id(obj)),
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
                    'global_index': obj_to_index.get(id(obj)),
                    'message': f'Duplicate dependency rule (also defined in {orig["file"]})'
                })
            else:
                dep_signatures[sig] = {'file': obj.source_file, 'obj': obj}

    # 10. Check for hosts without any services
    # Build set of hosts that have at least one service (direct or via hostgroup)
    hosts_with_services = set()

    # Collect hostgroup memberships: host -> set of hostgroups
    host_to_hostgroups = {}
    for obj in p.objects:
        if obj.object_type == 'host' and obj.attributes.get('register', '1') != '0':
            hname = obj.get_name()
            if hname:
                hgs = obj.attributes.get('hostgroups', '')
                if hgs:
                    host_to_hostgroups[hname] = {
                        g.strip().lstrip('+').strip()
                        for g in hgs.split(',') if g.strip()
                    }

    # Also check hostgroup 'members' directives
    hostgroup_to_hosts = {}
    for obj in p.objects:
        if obj.object_type == 'hostgroup':
            gname = obj.get_name()
            if gname and 'members' in obj.attributes:
                hostgroup_to_hosts[gname] = {
                    h.strip() for h in obj.attributes['members'].split(',') if h.strip()
                }

    for obj in p.objects:
        if obj.object_type == 'service' and obj.attributes.get('register', '1') != '0':
            # Direct host_name references
            host_ref = obj.attributes.get('host_name', '')
            if host_ref and host_ref != '*':
                for h in host_ref.split(','):
                    h = h.strip()
                    if h and not h.startswith('!'):
                        hosts_with_services.add(h)
            elif host_ref == '*':
                # Wildcard means all hosts have this service
                hosts_with_services = hosts.copy()
                break

            # Hostgroup-based service assignment
            hg_ref = obj.attributes.get('hostgroup_name', '')
            if hg_ref:
                for hg in hg_ref.split(','):
                    hg = hg.strip().lstrip('+!').strip()
                    if hg:
                        # All hosts in this hostgroup get this service
                        # Check hosts that declared membership via 'hostgroups' attr
                        for hname, hg_set in host_to_hostgroups.items():
                            if hg in hg_set:
                                hosts_with_services.add(hname)
                        # Check hostgroup 'members' directive
                        if hg in hostgroup_to_hosts:
                            hosts_with_services.update(hostgroup_to_hosts[hg])

    # Flag non-template hosts without services
    for obj in p.objects:
        if obj.object_type == 'host' and obj.attributes.get('register', '1') != '0':
            hname = obj.get_name()
            if hname and hname not in hosts_with_services:
                issues.append({
                    'type': 'host_without_services',
                    'severity': 'warning',
                    'object': hname,
                    'object_type': 'host',
                    'file': obj.source_file,
                    'global_index': obj_to_index.get(id(obj)),
                    'message': 'Host has no services assigned (directly or via hostgroup)'
                })

    # 11. Check for services missing check_command (including inheritance)
    for obj in service.get_objects():
        if obj.object_type != 'service':
            continue
        if obj.attributes.get('register', '1') == '0':
            continue  # Skip templates

        resolved = resolve_inherited_attrs(obj)
        if 'check_command' not in resolved:
            obj_name = obj.get_name() or 'unnamed'
            host = resolved.get('host_name', resolved.get('hostgroup_name', ''))
            issues.append({
                'type': 'missing_check_command',
                'severity': 'error',
                'object': f'{obj_name} on {host}' if host else obj_name,
                'object_type': 'service',
                'file': obj.source_file,
                'global_index': obj_to_index.get(id(obj)),
                'message': 'Service has no check_command (directly or through template inheritance)'
            })

    # 12. Check for command argument count mismatches
    for obj in service.get_objects():
        if obj.object_type not in ('service', 'host'):
            continue
        if obj.attributes.get('register', '1') == '0':
            continue

        resolved = resolve_inherited_attrs(obj)
        check_cmd = resolved.get('check_command', '')
        if not check_cmd:
            continue

        parts = check_cmd.split('!')
        cmd_name = parts[0].strip()
        provided_args = len(parts) - 1  # Everything after first !

        expected_args = command_arg_counts.get(cmd_name)
        if expected_args is None:
            continue  # Command not found — already reported by missing_command check

        if provided_args != expected_args:
            obj_name = obj.get_name() or 'unnamed'
            issues.append({
                'type': 'command_arg_mismatch',
                'severity': 'warning',
                'object': obj_name,
                'object_type': obj.object_type,
                'file': obj.source_file,
                'global_index': obj_to_index.get(id(obj)),
                'message': f'Command {cmd_name} expects {expected_args} arg(s) but {provided_args} provided'
            })

    # 13. Check for template attribute conflicts in multi-template inheritance
    for obj in service.get_objects():
        if obj.attributes.get('register', '1') == '0':
            continue
        use_value = obj.attributes.get('use', '')
        if not use_value:
            continue

        tmpl_names = [t.strip() for t in use_value.split(',') if t.strip()]
        if len(tmpl_names) < 2:
            continue  # Single template — no conflicts possible

        # Resolve each template's full attribute set independently
        tmpl_attr_sets = []
        for tmpl_name in tmpl_names:
            tmpl = template_lookup.get((obj.object_type, tmpl_name))
            if tmpl:
                resolved_tmpl = resolve_inherited_attrs(tmpl)
                # Remove system fields
                cleaned = {k: v for k, v in resolved_tmpl.items()
                           if k not in ('use', 'name', 'register')}
                tmpl_attr_sets.append((tmpl_name, cleaned))

        if len(tmpl_attr_sets) < 2:
            continue

        # Find attributes defined in multiple templates with different values
        # that are NOT overridden by the object itself
        conflicts = []
        seen_attrs = {}  # attr -> (first_value, first_template)
        for tmpl_name, attrs in tmpl_attr_sets:
            for attr, value in attrs.items():
                if attr in obj.attributes:
                    continue  # Object overrides this — no conflict
                if attr in seen_attrs:
                    prev_value, prev_tmpl = seen_attrs[attr]
                    if value != prev_value:
                        conflicts.append(
                            f'{attr} differs: {prev_tmpl}={prev_value}, {tmpl_name}={value}'
                        )
                else:
                    seen_attrs[attr] = (value, tmpl_name)

        if conflicts:
            obj_name = obj.get_name() or 'unnamed'
            issues.append({
                'type': 'template_conflict',
                'severity': 'warning',
                'object': obj_name,
                'object_type': obj.object_type,
                'file': obj.source_file,
                'global_index': obj_to_index.get(id(obj)),
                'message': f'Template inheritance conflict (first template wins): {"; ".join(conflicts[:3])}'
            })

    # 14. Notification chain validation (SAFETY-2)
    # Trace: host/service -> contacts/contact_groups -> contact members ->
    #   contact's notification commands -> notification periods

    # Build contact and contactgroup lookups
    contact_objects = {}   # contact_name -> NagiosObject
    cg_objects = {}        # contactgroup_name -> NagiosObject
    for obj in service.get_objects():
        if obj.object_type == 'contact' and obj.attributes.get('register', '1') != '0':
            contact_objects[obj.attributes.get('contact_name', '')] = obj
        elif obj.object_type == 'contactgroup':
            cg_objects[obj.attributes.get('contactgroup_name', '')] = obj

    def resolve_contact_names(obj_or_resolved):
        """Get all contact names for a host/service (direct + via contactgroups)."""
        attrs = obj_or_resolved if isinstance(obj_or_resolved, dict) else obj_or_resolved.attributes
        result = set()
        # Direct contacts
        if 'contacts' in attrs:
            for c in attrs['contacts'].split(','):
                c = c.strip().lstrip('+!')
                if c:
                    result.add(c)
        # Via contact groups
        if 'contact_groups' in attrs:
            for cg_name in attrs['contact_groups'].split(','):
                cg_name = cg_name.strip().lstrip('+!')
                cg = cg_objects.get(cg_name)
                if cg and 'members' in cg.attributes:
                    for m in cg.attributes['members'].split(','):
                        m = m.strip()
                        if m:
                            result.add(m)
        return result

    def check_contact_notification(contact_name, check_type):
        """Check if a contact can deliver notifications for host or service.

        check_type is 'host' or 'service'.
        Returns list of problem descriptions (empty = OK).
        """
        problems = []
        contact_obj = contact_objects.get(contact_name)
        if not contact_obj:
            return []  # Contact not found -- already reported by missing_contact check

        resolved_contact = resolve_inherited_attrs(contact_obj)

        cmd_field = f'{check_type}_notification_commands'
        period_field = f'{check_type}_notification_period'

        if cmd_field not in resolved_contact:
            problems.append(f'{contact_name} has no {cmd_field}')

        if period_field not in resolved_contact:
            problems.append(f'{contact_name} has no {period_field}')

        return problems

    # Check each contact for notification gaps (one issue per contact)
    for cname, contact_obj in contact_objects.items():
        if not cname:
            continue
        all_problems = []
        for check_type in ('host', 'service'):
            all_problems.extend(check_contact_notification(cname, check_type))
        if all_problems:
            issues.append({
                'type': 'notification_gap',
                'severity': 'warning',
                'object': cname,
                'object_type': 'contact',
                'file': contact_obj.source_file,
                'global_index': obj_to_index.get(id(contact_obj)),
                'message': f'Notification chain broken: {"; ".join(all_problems)}'
            })

    # 15. Check for unused commands
    # A command is "used" if any object references it via check_command,
    # event_handler, host_notification_commands, service_notification_commands,
    # global_host_event_handler, or global_service_event_handler.
    used_commands = set()
    for obj in service.get_objects():
        # Single-command fields: command name is before the first '!'
        for cmd_field in ['check_command', 'event_handler',
                          'global_host_event_handler', 'global_service_event_handler']:
            if cmd_field in obj.attributes:
                cmd_ref = obj.attributes[cmd_field].split('!')[0].strip()
                if cmd_ref:
                    used_commands.add(cmd_ref)

        # Comma-separated command fields: each entry can have '!' args
        for cmd_field in ['host_notification_commands', 'service_notification_commands']:
            if cmd_field in obj.attributes:
                for cmd_full in obj.attributes[cmd_field].split(','):
                    cmd_ref = cmd_full.strip().split('!')[0].strip()
                    if cmd_ref:
                        used_commands.add(cmd_ref)

    for obj in service.get_objects():
        if obj.object_type == 'command':
            cmd_name = obj.attributes.get('command_name', '')
            if cmd_name and cmd_name not in used_commands:
                issues.append({
                    'type': 'unused_command',
                    'severity': 'warning',
                    'object': cmd_name,
                    'object_type': 'command',
                    'file': obj.source_file,
                    'global_index': obj_to_index.get(id(obj)),
                    'message': f'Command is not referenced by any object'
                })

    # 16. Check for unused contacts
    # A contact is "used" if any non-template object has it in 'contacts' attribute,
    # or any contactgroup has it in 'members' attribute.
    used_contacts = set()
    for obj in service.get_objects():
        is_template = obj.attributes.get('register', '1') == '0'
        if is_template:
            continue

        # Direct contacts attribute on any object
        if 'contacts' in obj.attributes:
            for c in obj.attributes['contacts'].split(','):
                c = c.strip().lstrip('+!').strip()
                if c:
                    used_contacts.add(c)

    # Also check contactgroup 'members' attribute (contactgroups are not templates)
    for obj in service.get_objects():
        if obj.object_type == 'contactgroup' and 'members' in obj.attributes:
            for m in obj.attributes['members'].split(','):
                m = m.strip().lstrip('+!').strip()
                if m:
                    used_contacts.add(m)

    for obj in service.get_objects():
        if obj.object_type == 'contact' and obj.attributes.get('register', '1') != '0':
            contact_name = obj.attributes.get('contact_name', '')
            if contact_name and contact_name not in used_contacts:
                issues.append({
                    'type': 'unused_contact',
                    'severity': 'warning',
                    'object': contact_name,
                    'object_type': 'contact',
                    'file': obj.source_file,
                    'global_index': obj_to_index.get(id(obj)),
                    'message': 'Contact is not referenced by any object'
                })

    # 17. Check for unused contactgroups
    # A contactgroup is "used" if any non-template object has it in 'contact_groups',
    # any contactgroup has it in 'contactgroup_members', or any contact has it in 'contactgroups'.
    used_contactgroups = set()
    for obj in service.get_objects():
        is_template = obj.attributes.get('register', '1') == '0'

        # contact_groups attribute on any non-template object
        if not is_template and 'contact_groups' in obj.attributes:
            for cg in obj.attributes['contact_groups'].split(','):
                cg = cg.strip().lstrip('+!').strip()
                if cg:
                    used_contactgroups.add(cg)

        # contactgroup_members on contactgroups
        if obj.object_type == 'contactgroup' and 'contactgroup_members' in obj.attributes:
            for cg in obj.attributes['contactgroup_members'].split(','):
                cg = cg.strip().lstrip('+!').strip()
                if cg:
                    used_contactgroups.add(cg)

        # contactgroups attribute on contacts
        if obj.object_type == 'contact' and 'contactgroups' in obj.attributes:
            for cg in obj.attributes['contactgroups'].split(','):
                cg = cg.strip().lstrip('+!').strip()
                if cg:
                    used_contactgroups.add(cg)

    for obj in service.get_objects():
        if obj.object_type == 'contactgroup':
            cg_name = obj.attributes.get('contactgroup_name', '')
            if cg_name and cg_name not in used_contactgroups:
                issues.append({
                    'type': 'unused_contactgroup',
                    'severity': 'warning',
                    'object': cg_name,
                    'object_type': 'contactgroup',
                    'file': obj.source_file,
                    'global_index': obj_to_index.get(id(obj)),
                    'message': 'Contact group is not referenced by any object'
                })

    # 18. Check for unused timeperiods
    # A timeperiod is "used" if any non-template object references it in:
    # check_period, notification_period, host_notification_period,
    # service_notification_period, dependency_period, or exclude (comma-separated).
    used_timeperiods = set()
    tp_fields_single = [
        'check_period', 'notification_period',
        'host_notification_period', 'service_notification_period',
        'dependency_period',
    ]
    for obj in service.get_objects():
        is_template = obj.attributes.get('register', '1') == '0'
        if is_template:
            continue

        for tp_field in tp_fields_single:
            if tp_field in obj.attributes:
                tp_ref = obj.attributes[tp_field].strip().lstrip('+!').strip()
                if tp_ref:
                    used_timeperiods.add(tp_ref)

        # 'exclude' is comma-separated on timeperiod objects
        if 'exclude' in obj.attributes:
            for tp in obj.attributes['exclude'].split(','):
                tp = tp.strip().lstrip('+!').strip()
                if tp:
                    used_timeperiods.add(tp)

    for obj in service.get_objects():
        if obj.object_type == 'timeperiod' and obj.attributes.get('register', '1') != '0':
            tp_name = obj.attributes.get('timeperiod_name', '')
            if tp_name and tp_name not in used_timeperiods:
                issues.append({
                    'type': 'unused_timeperiod',
                    'severity': 'warning',
                    'object': tp_name,
                    'object_type': 'timeperiod',
                    'file': obj.source_file,
                    'global_index': obj_to_index.get(id(obj)),
                    'message': 'Time period is not referenced by any object'
                })

    # 19. Check for duplicate object definitions
    identity_map = {}  # "type:name" -> [obj, ...]
    for obj in p.objects:
        if obj.attributes.get('register', '1') == '0':
            continue
        name = obj.get_name()
        if not name:
            continue
        key = f'{obj.object_type}:{name}'
        identity_map.setdefault(key, []).append(obj)

    for key, objs in identity_map.items():
        if len(objs) <= 1:
            continue
        obj_type, identity = key.split(':', 1)
        # Build related_objects list with global_index, file, line for each copy
        related_objects = [
            {
                'global_index': obj_to_index.get(id(o)),
                'file': o.source_file,
                'line': o.line_number,
            }
            for o in objs
        ]
        files = [o.source_file.rsplit('/', 1)[-1] for o in objs]
        for obj in objs:
            other_files = [f for f, o in zip(files, objs) if o is not obj]
            issues.append({
                'type': 'duplicate',
                'severity': 'error',
                'object': identity,
                'object_type': obj_type,
                'file': obj.source_file,
                'global_index': obj_to_index.get(id(obj)),
                'related_objects': related_objects,
                'message': f'Duplicate {obj_type} definition (also in {", ".join(other_files)})'
            })

    # 20. Orphan detection
    # Build referenced-names sets by type, scanning all reference fields
    command_fields = {f for f, t in REFERENCE_FIELDS.items() if t == 'command'}
    referenced_names = {
        'host': set(), 'hostgroup': set(), 'service': set(),
        'servicegroup': set(), 'contact': set(), 'contactgroup': set(),
        'command': set(), 'timeperiod': set()
    }

    def has_attr_in_chain(obj, attr_name, visited=None):
        """Check if attribute exists in object or its template chain."""
        if visited is None:
            visited = set()
        if attr_name in obj.attributes:
            return True
        use_val = obj.attributes.get('use', '')
        if not use_val:
            return False
        for t_name in [t.strip() for t in use_val.split(',') if t.strip()]:
            if t_name not in visited:
                visited.add(t_name)
                tmpl = template_lookup.get((obj.object_type, t_name))
                if tmpl and has_attr_in_chain(tmpl, attr_name, visited):
                    return True
        return False

    for obj in p.objects:
        attrs = obj.attributes
        own_name_field = NAME_FIELDS.get(obj.object_type)

        for ref_field, target_type in REFERENCE_FIELDS.items():
            if ref_field not in attrs:
                continue
            value = attrs[ref_field]

            # Resolve target type for context-dependent fields
            if ref_field == 'use':
                resolved_type = obj.object_type
            elif ref_field == 'members':
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
            if ref_field == own_name_field:
                continue

            for part in value.split(','):
                part = strip_prefix(part)
                if not part:
                    continue
                if ref_field in command_fields:
                    part = part.split('!')[0].strip()
                if part:
                    referenced_names[resolved_type].add(part)

        # Auto-reference: hosts with hostgroups attr are in use
        if obj.object_type == 'host' and has_attr_in_chain(obj, 'hostgroups'):
            host_name_val = obj.get_name()
            if host_name_val:
                referenced_names['host'].add(host_name_val.strip())

        # Auto-reference: services with host_name/hostgroup_name are in use
        if obj.object_type == 'service':
            if (has_attr_in_chain(obj, 'host_name') or
                    has_attr_in_chain(obj, 'hostgroup_name')):
                svc_name = obj.get_name()
                if svc_name:
                    referenced_names['service'].add(svc_name.strip())

        # Auto-reference: services with servicegroups are in use
        if obj.object_type == 'service' and has_attr_in_chain(obj, 'servicegroups'):
            svc_name = obj.get_name()
            if svc_name:
                referenced_names['service'].add(svc_name.strip())

    for obj in p.objects:
        if obj.attributes.get('register', '1') == '0':
            continue
        obj_name = obj.get_name()
        refs = referenced_names.get(obj.object_type)
        if refs is None:
            continue
        attr_name = obj.attributes.get('name')
        is_referenced = ((obj_name and obj_name in refs) or
                         (attr_name and attr_name in refs))
        if not is_referenced:
            issues.append({
                'type': 'orphan',
                'severity': 'info',
                'object': obj_name or obj.get_display_name(),
                'object_type': obj.object_type,
                'file': obj.source_file,
                'global_index': obj_to_index.get(id(obj)),
                'message': f'{obj.object_type} is not referenced by any other object'
            })

    # 21. Notification gap detection for hosts/services
    # Flag hosts/services that have no contacts, no contact_groups, AND no use template
    for obj in p.objects:
        if obj.object_type not in ('host', 'service'):
            continue
        if obj.attributes.get('register', '1') == '0':
            continue
        has_contacts = 'contacts' in obj.attributes
        has_contact_groups = 'contact_groups' in obj.attributes
        has_use = 'use' in obj.attributes
        if not has_contacts and not has_contact_groups and not has_use:
            obj_name = obj.get_name() or obj.get_display_name()
            issues.append({
                'type': 'notification_gap',
                'severity': 'warning',
                'object': obj_name,
                'object_type': obj.object_type,
                'file': obj.source_file,
                'global_index': obj_to_index.get(id(obj)),
                'message': f'{obj.object_type.title()} has no contacts, contact_groups, or template (use) defined'
            })

    # 22. Long host list detection
    for obj in p.objects:
        if obj.object_type != 'service':
            continue
        if obj.attributes.get('register', '1') == '0':
            continue
        host_ref = obj.attributes.get('host_name', '')
        if not host_ref:
            continue
        host_list = [h.strip() for h in host_ref.split(',') if h.strip()]
        host_count = len(host_list)
        if host_count >= 10:
            obj_name = obj.get_name() or obj.get_display_name()
            issues.append({
                'type': 'long_host_list',
                'severity': 'info',
                'object': obj_name,
                'object_type': 'service',
                'file': obj.source_file,
                'global_index': obj_to_index.get(id(obj)),
                'host_count': host_count,
                'message': f'Service has {host_count} hosts in host_name list (consider using a hostgroup)'
            })

    # 23. Template consolidation detection
    # Find groups of 3+ non-templated objects sharing identical non-identity attributes
    identity_fields_set = set(NAME_FIELDS.values()) | {
        'name', 'register', 'alias', 'address', 'display_name'
    }

    objects_by_type = {}
    for idx, obj in enumerate(p.objects):
        objects_by_type.setdefault(obj.object_type, []).append((idx, obj))

    for obj_type, type_entries in objects_by_type.items():
        if len(type_entries) < 3:
            continue
        if obj_type in ('timeperiod', 'command'):
            continue

        signatures = {}
        for idx, obj in type_entries:
            if obj.attributes.get('use') or obj.attributes.get('register') == '0':
                continue
            attr_pairs = []
            for k, v in sorted(obj.attributes.items()):
                if k not in identity_fields_set:
                    attr_pairs.append(f'{k}={v}')
            if not attr_pairs:
                continue
            signature = '|'.join(attr_pairs)
            signatures.setdefault(signature, []).append((idx, obj))

        for signature, matching_entries in signatures.items():
            if len(matching_entries) < 3:
                continue
            # Parse signature back to attributes
            attrs = {}
            for pair in signature.split('|'):
                eq_idx = pair.index('=')
                k = pair[:eq_idx]
                v = pair[eq_idx + 1:]
                attrs[k] = v

            matching_objects = [obj for _, obj in matching_entries]
            suggested_name = _generate_template_name(
                obj_type, matching_objects, attrs)

            suggestion = {
                'suggested_name': suggested_name,
                'type': obj_type,
                'attributes': attrs,
                'object_indices': [idx for idx, _ in matching_entries],
                'count': len(matching_entries),
                'attr_count': len(attrs),
            }
            issues.append({
                'type': 'template_opportunity',
                'severity': 'info',
                'object': suggested_name,
                'object_type': obj_type,
                'file': matching_entries[0][1].source_file,
                'global_index': None,
                'suggestion': suggestion,
                'message': f'{len(matching_entries)} {obj_type} objects share {len(attrs)} identical attributes'
            })

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
