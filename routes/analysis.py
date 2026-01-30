"""Analysis and dependency routes."""

import os
from collections import defaultdict
from flask import Blueprint, request, jsonify

from .helpers import (
    get_service,
    get_parser_for_modification,
    get_backup_manager,
    get_config_path
)
from nagios_model import NagiosObject
from nagios_writer import NagiosConfigWriter

bp = Blueprint('analysis', __name__)


@bp.route('/api/dependencies')
def api_dependencies():
    """Get object dependencies for graph visualization."""
    service = get_service()
    p = service.parser
    object_type = request.args.get('type')

    nodes = []
    edges = []
    node_ids = set()
    defined_node_ids = set()  # Track nodes that have actual object definitions

    template_lookup = {}
    for obj in service.get_objects():
        template_name = obj.attributes.get('name')
        if template_name:
            template_lookup[(obj.object_type, template_name)] = obj

    def resolve_inherited_attributes(obj):
        """Resolve attributes including inherited ones from templates."""
        resolved = {}

        use_templates = obj.attributes.get('use', '')
        if use_templates:
            template_names = [t.strip() for t in use_templates.split(',') if t.strip()]
            for tmpl_name in template_names:
                tmpl = template_lookup.get((obj.object_type, tmpl_name))
                if tmpl:
                    tmpl_attrs = resolve_inherited_attributes(tmpl)
                    for key, value in tmpl_attrs.items():
                        if key not in ['use', 'name', 'register']:
                            resolved[key] = value

        for key, value in obj.attributes.items():
            resolved[key] = value

        return resolved

    relationship_fields = {
        'host_name': 'host',
        'hostgroup_name': 'hostgroup',
        'hostgroups': 'hostgroup',
        'hostgroup_members': 'hostgroup',
        'service_description': 'service',
        'dependent_service_description': 'service',
        'dependent_host_name': 'host',
        'dependent_hostgroup_name': 'hostgroup',
        'master_host_name': 'host',
        'master_hostgroup_name': 'hostgroup',
        'master_service_description': 'service',
        'servicegroup_name': 'servicegroup',
        'servicegroups': 'servicegroup',
        'servicegroup_members': 'servicegroup',
        'contact_name': 'contact',
        'contacts': 'contact',
        'contact_groups': 'contactgroup',
        'contactgroup_name': 'contactgroup',
        'contactgroup_members': 'contactgroup',
        'escalation_contacts': 'contact',
        'escalation_contact_groups': 'contactgroup',
        'use': 'template',
        'members': 'member',
        'parents': 'host',
        'check_command': 'command',
        'event_handler': 'command',
        'host_notification_commands': 'command',
        'service_notification_commands': 'command',
        'check_period': 'timeperiod',
        'notification_period': 'timeperiod',
        'host_notification_period': 'timeperiod',
        'service_notification_period': 'timeperiod',
        'escalation_period': 'timeperiod',
        'dependency_period': 'timeperiod',
        'exclude': 'timeperiod',
    }

    type_colors = {
        'host': '#4CAF50',
        'hostgroup': '#8BC34A',
        'service': '#2196F3',
        'servicegroup': '#03A9F4',
        'contact': '#FF9800',
        'contactgroup': '#FFC107',
        'command': '#9C27B0',
        'timeperiod': '#607D8B',
        'servicedependency': '#E91E63',
        'hostdependency': '#F44336',
        'serviceescalation': '#00BCD4',
        'hostescalation': '#009688',
    }

    # Build template lookup for marking template nodes
    template_names = set()
    for obj in service.get_objects():
        if obj.attributes.get('register', '1') == '0':
            obj_name = obj.attributes.get('name')
            if obj_name:
                template_names.add((obj.object_type, obj_name))

    for obj in p.objects:
        if object_type and obj.object_type != object_type:
            continue

        obj_name = obj.get_name()
        if not obj_name:
            continue

        if obj.object_type == 'service':
            target = obj.attributes.get('hostgroup_name') or obj.attributes.get('host_name', '')
            target = ','.join([t.strip().lstrip('+').strip() for t in target.split(',') if not t.strip().startswith('!')])
            if target:
                node_id = f"service:{target}:{obj_name}"
            else:
                node_id = f"service:{obj_name}"
        else:
            node_id = f"{obj.object_type}:{obj_name}"
        if node_id not in node_ids:
            is_template = (obj.object_type, obj_name) in template_names
            node_data = {
                'id': node_id,
                'label': obj_name,
                'type': obj.object_type,
                'color': type_colors.get(obj.object_type, '#999999'),
                'exists': True  # This node has an actual object definition
            }
            if is_template:
                node_data['is_template'] = True
            nodes.append(node_data)
            node_ids.add(node_id)
            defined_node_ids.add(node_id)
        else:
            # Node was already created (possibly as orphan reference) - update it
            # to mark it as existing and set template flag if applicable
            for existing_node in nodes:
                if existing_node['id'] == node_id:
                    existing_node['exists'] = True
                    if (obj.object_type, obj_name) in template_names:
                        existing_node['is_template'] = True
                    break
            defined_node_ids.add(node_id)

        resolved_attrs = resolve_inherited_attributes(obj)

        for field, target_type in relationship_fields.items():
            if field in resolved_attrs:
                identity_fields = {
                    'host': 'host_name',
                    'hostgroup': 'hostgroup_name',
                    'servicegroup': 'servicegroup_name',
                    'contact': 'contact_name',
                    'contactgroup': 'contactgroup_name',
                }
                if identity_fields.get(obj.object_type) == field:
                    continue

                raw_value = resolved_attrs[field]

                # Command fields use ! to separate command name from arguments
                # e.g., check_ping!100.0,20%!500.0,60% - only the part before first ! is the command
                if target_type == 'command':
                    command_name = raw_value.split('!')[0].strip()
                    targets = [command_name] if command_name else []
                else:
                    targets = [t.strip().lstrip('+').strip() for t in raw_value.split(',')
                              if t.strip() and not t.strip().startswith('!')]
                for target in targets:
                    if not target:
                        continue

                    if target_type == 'template':
                        # Template relationships use the object's type for the target node ID
                        t_type = obj.object_type
                    elif target_type == 'member':
                        t_type = obj.object_type.replace('group', '')
                    else:
                        t_type = target_type

                    if t_type == 'service' and field in ('service_description', 'dependent_service_description'):
                        if field == 'dependent_service_description':
                            svc_context = resolved_attrs.get('dependent_hostgroup_name') or resolved_attrs.get('dependent_host_name', '')
                        else:
                            svc_context = resolved_attrs.get('hostgroup_name') or resolved_attrs.get('host_name', '')
                        svc_context = ','.join([t.strip().lstrip('+').strip() for t in svc_context.split(',') if not t.strip().startswith('!')])
                        if svc_context:
                            target_id = f"service:{svc_context}:{target}"
                        else:
                            target_id = f"service:{target}"
                    else:
                        target_id = f"{t_type}:{target}"

                    if target_id == node_id:
                        continue

                    if target_id not in node_ids:
                        nodes.append({
                            'id': target_id,
                            'label': target,
                            'type': t_type,
                            'color': type_colors.get(t_type, '#999999'),
                            'exists': False  # Referenced but not defined - orphan reference
                        })
                        node_ids.add(target_id)

                    # Fields where edge direction is reversed (target points to source)
                    # - parents: parent → child shows reachability path (network topology)
                    # Note: Most fields use standard direction (source depends on target)
                    # - 'use': object → template (object depends on template)
                    # - 'host_name': service → host (service depends on host)
                    # - 'check_command': object → command (object uses command)
                    reverse_edge_fields = {
                        'parents'  # Network topology: parent reaches child
                    }

                    if field in reverse_edge_fields:
                        edges.append({
                            'from': target_id,
                            'to': node_id,
                            'label': field,
                            'arrows': 'to'
                        })
                    else:
                        edges.append({
                            'from': node_id,
                            'to': target_id,
                            'label': field,
                            'arrows': 'to'
                        })

    return jsonify({
        'nodes': nodes,
        'edges': edges
    })


@bp.route('/api/inheritance/list/<object_type>')
def api_inheritance_list(object_type):
    """List all templates for a given object type."""
    service = get_service()
    templates = []
    for obj in service.get_objects():
        if obj.object_type == object_type and obj.attributes.get('register', '1') == '0':
            templates.append(obj.to_dict())
    return jsonify(templates)


@bp.route('/api/inheritance/<object_type>/<name>')
def api_inheritance_chain(object_type, name):
    """Get the inheritance chain for an object."""
    service = get_service()

    target = None
    for obj in service.get_objects():
        if obj.object_type == object_type and obj.get_name() == name:
            target = obj
            break

    if not target:
        return jsonify({'error': 'Object not found'}), 404

    templates = {}
    for obj in service.get_objects():
        if obj.object_type == object_type and 'name' in obj.attributes:
            templates[obj.attributes['name']] = obj

    def get_chain(obj, visited=None):
        if visited is None:
            visited = set()

        chain = [obj.to_dict()]
        uses = obj.attributes.get('use', '')

        if uses and uses in templates and uses not in visited:
            visited.add(uses)
            chain.extend(get_chain(templates[uses], visited))

        return chain

    chain = get_chain(target)

    return jsonify({
        'chain': chain,
        'depth': len(chain)
    })


@bp.route('/api/smart-grouping/suggest')
def api_smart_grouping_suggest():
    """Suggest hostgroups based on common patterns."""
    service = get_service()

    MAX_SUGGESTIONS = 20

    hosts = [obj for obj in service.get_objects()
             if obj.object_type == 'host' and obj.attributes.get('register', '1') != '0']

    if not hosts:
        return jsonify({'suggestions': [], 'total_hosts': 0})

    existing_groups = set()
    for obj in service.get_objects():
        if obj.object_type == 'hostgroup':
            name = obj.get_name()
            if name:
                existing_groups.add(name.lower())

    suggestions = []

    subnet_groups = defaultdict(list)
    for host in hosts:
        addr = host.attributes.get('address', '')
        if addr and '.' in addr:
            parts = addr.rsplit('.', 1)
            if len(parts) == 2:
                subnet_groups[parts[0]].append(host.get_name())

    for subnet, members in subnet_groups.items():
        if len(members) >= 3:
            suggested_name = f"subnet-{subnet.replace('.', '-')}"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    'type': 'ip_subnet',
                    'name': suggested_name,
                    'description': f'Hosts in {subnet}.0/24 subnet',
                    'members': sorted(members),
                    'count': len(members),
                    'pattern': f'{subnet}.x'
                })

    prefix_groups = defaultdict(list)
    for host in hosts:
        name = host.get_name()
        if name and '-' in name:
            prefix = name.split('-')[0]
            prefix_groups[prefix].append(name)

    for prefix, members in prefix_groups.items():
        if len(members) >= 3:
            suggested_name = f"{prefix}-servers"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    'type': 'hostname_prefix',
                    'name': suggested_name,
                    'description': f'Hosts with prefix "{prefix}-"',
                    'members': sorted(members),
                    'count': len(members),
                    'pattern': f'{prefix}-*'
                })

    suffix_groups = defaultdict(list)
    for host in hosts:
        name = host.get_name()
        if name and '-' in name:
            suffix = name.split('-')[-1]
            suffix_groups[suffix].append(name)

    for suffix, members in suffix_groups.items():
        if len(members) >= 3:
            suggested_name = f"{suffix}-systems"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    'type': 'hostname_suffix',
                    'name': suggested_name,
                    'description': f'Hosts with suffix "-{suffix}"',
                    'members': sorted(members),
                    'count': len(members),
                    'pattern': f'*-{suffix}'
                })

    command_groups = defaultdict(list)
    for host in hosts:
        name = host.get_name()
        check_cmd = host.attributes.get('check_command', '')
        if name and check_cmd:
            cmd_name = check_cmd.split('!')[0]
            command_groups[cmd_name].append(name)

    for cmd, members in command_groups.items():
        if len(members) >= 3:
            suggested_name = f"{cmd.replace('check_', '').replace('check-', '')}-checked"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    'type': 'check_command',
                    'name': suggested_name,
                    'description': f'Hosts using check command "{cmd}"',
                    'members': sorted(members),
                    'count': len(members),
                    'pattern': cmd
                })

    parent_groups = defaultdict(list)
    for host in hosts:
        name = host.get_name()
        parents = host.attributes.get('parents', '')
        if name and parents:
            for parent in parents.split(','):
                parent = parent.strip()
                if parent:
                    parent_groups[parent].append(name)

    for parent, members in parent_groups.items():
        if len(members) >= 2:
            suggested_name = f"behind-{parent}"
            if suggested_name.lower() not in existing_groups:
                suggestions.append({
                    'type': 'network_parent',
                    'name': suggested_name,
                    'description': f'Hosts behind "{parent}"',
                    'members': sorted(members),
                    'count': len(members),
                    'pattern': f'parents={parent}'
                })

    hosts_in_groups = set()
    for obj in service.get_objects():
        if obj.object_type == 'hostgroup':
            members = obj.attributes.get('members', '')
            for m in members.split(','):
                m = m.strip()
                if m.startswith('!'):
                    continue
                m = m.lstrip('+').strip()
                if m:
                    hosts_in_groups.add(m)

    for host in hosts:
        if 'hostgroups' in host.attributes:
            hosts_in_groups.add(host.get_name())

    ungrouped = [h.get_name() for h in hosts if h.get_name() and h.get_name() not in hosts_in_groups]
    if len(ungrouped) >= 2:
        suggestions.append({
            'type': 'ungrouped',
            'name': 'ungrouped-hosts',
            'description': 'Hosts not currently in any hostgroup',
            'members': sorted(ungrouped),
            'count': len(ungrouped),
            'pattern': 'No hostgroup membership'
        })

    type_weights = {
        'ip_subnet': 1.5,
        'hostname_prefix': 1.3,
        'hostname_suffix': 1.2,
        'network_parent': 1.4,
        'check_command': 1.0,
        'common_services': 0.9,
        'ungrouped': 0.5,
    }

    host_suggestion_counts = defaultdict(int)
    for suggestion in suggestions:
        for member in suggestion['members']:
            host_suggestion_counts[member] += 1

    for suggestion in suggestions:
        base_score = suggestion['count']
        type_weight = type_weights.get(suggestion['type'], 1.0)

        overlap_bonus = 0
        for member in suggestion['members']:
            if host_suggestion_counts[member] > 1:
                overlap_bonus += 0.1

        overlap_bonus = min(overlap_bonus, suggestion['count'] * 0.3)

        confidence = (base_score * type_weight) + overlap_bonus
        suggestion['confidence'] = round(confidence, 2)

        overlap_types = set()
        for other in suggestions:
            if other is suggestion:
                continue
            shared = set(suggestion['members']) & set(other['members'])
            if len(shared) >= 2:
                overlap_types.add(other['type'])

        suggestion['overlaps_with'] = list(overlap_types)

    suggestions.sort(key=lambda x: x['confidence'], reverse=True)

    limited_suggestions = suggestions[:MAX_SUGGESTIONS]

    return jsonify({
        'suggestions': limited_suggestions,
        'total_hosts': len(hosts),
        'existing_groups': len(existing_groups),
        'suggestions_truncated': len(suggestions) > MAX_SUGGESTIONS
    })


@bp.route('/api/smart-grouping/create', methods=['POST'])
def api_smart_grouping_create():
    """Create a hostgroup from a suggestion."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    group_name = data.get('name', '').strip()
    members = data.get('members', [])
    alias = data.get('alias', '')

    if not group_name:
        return jsonify({'error': 'Group name required'}), 400
    if not members:
        return jsonify({'error': 'At least one member required'}), 400

    with get_parser_for_modification() as p:
        for obj in p.objects:
            if obj.object_type == 'hostgroup' and obj.get_name() == group_name:
                return jsonify({'error': f'Hostgroup "{group_name}" already exists'}), 400

        backup_path = bm.create_backup("create_hostgroup")

        target_file = None
        for obj in p.objects:
            if obj.object_type == 'hostgroup':
                target_file = obj.source_file
                break

        if not target_file:
            for obj in p.objects:
                if obj.object_type == 'host':
                    target_file = obj.source_file.replace('.cfg', '-hostgroups.cfg')
                    break

        if not target_file:
            target_file = os.path.join(get_config_path(), 'hostgroups.cfg')

        new_group = NagiosObject(
            object_type='hostgroup',
            attributes={
                'hostgroup_name': group_name,
                'alias': alias or group_name,
                'members': ','.join(members)
            },
            source_file=target_file,
            line_number=0
        )

        p.objects.append(new_group)

        writer = NagiosConfigWriter()
        writer.write_objects_to_original_files(p.objects)

    get_service().reload()

    return jsonify({
        'success': True,
        'group_name': group_name,
        'members_count': len(members),
        'file': target_file,
        'backup': backup_path
    })


@bp.route('/api/smart-grouping/add-to-group', methods=['POST'])
def api_add_to_group():
    """Add hosts to an existing hostgroup."""
    bm = get_backup_manager()
    data = request.get_json() or {}

    group_name = data.get('group_name', '').strip()
    hosts_to_add = data.get('hosts', [])

    if not group_name:
        return jsonify({'error': 'Group name required'}), 400
    if not hosts_to_add:
        return jsonify({'error': 'At least one host required'}), 400

    with get_parser_for_modification() as p:
        hostgroup = None
        for obj in p.objects:
            if obj.object_type == 'hostgroup' and obj.get_name() == group_name:
                hostgroup = obj
                break

        if not hostgroup:
            return jsonify({'error': f'Hostgroup "{group_name}" not found'}), 404

        backup_path = bm.create_backup("add_to_hostgroup")

        current_members = hostgroup.attributes.get('members', '')
        current_list = [m.strip() for m in current_members.split(',') if m.strip()]
        print(f"[add-to-group] Current members of {group_name}: {current_list}")

        current_normalized = [m.lstrip('+!').strip() for m in current_list]
        added_count = 0
        for host in hosts_to_add:
            if host not in current_normalized:
                current_list.append(host)
                current_normalized.append(host)
                added_count += 1

        new_members = ','.join(current_list)
        hostgroup.attributes['members'] = new_members
        print(f"[add-to-group] New members: {new_members}")

        for host_name in hosts_to_add:
            for obj in p.objects:
                if obj.object_type == 'host' and obj.get_name() == host_name:
                    current_hostgroups = obj.attributes.get('hostgroups', '')
                    hostgroups_list = [hg.strip() for hg in current_hostgroups.split(',') if hg.strip()]
                    hostgroups_normalized = [hg.lstrip('+!').strip() for hg in hostgroups_list]
                    if group_name not in hostgroups_normalized:
                        hostgroups_list.append(group_name)
                        obj.attributes['hostgroups'] = ','.join(hostgroups_list)
                        print(f"[add-to-group] Updated host {host_name} hostgroups: {obj.attributes['hostgroups']}")
                    break

        writer = NagiosConfigWriter()
        files_written = writer.write_objects_to_original_files(p.objects)
        print(f"[add-to-group] Files written: {files_written}")

    get_service().reload()

    service = get_service()
    for obj in service.get_objects():
        if obj.object_type == 'hostgroup' and obj.get_name() == group_name:
            print(f"[add-to-group] Verified members after reload: {obj.attributes.get('members', '')}")
            break

    final_members = ''
    for obj in service.get_objects():
        if obj.object_type == 'hostgroup' and obj.get_name() == group_name:
            final_members = obj.attributes.get('members', '')
            break

    return jsonify({
        'success': True,
        'group_name': group_name,
        'added_count': added_count,
        'total_members': len(current_list),
        'members': final_members,
        'backup': backup_path
    })


@bp.route('/api/templates/issues')
def get_template_issues():
    """Get template-specific validation issues.

    Returns three categories of issues:
    - invalid_use: Objects referencing non-existent templates
    - circular_dependencies: Circular template inheritance chains
    - unused_templates: Templates not used by any object (directly or transitively)
    """
    service = get_service()
    issues = {
        'invalid_use': [],
        'circular_dependencies': [],
        'unused_templates': []
    }

    # Build template lookup by type
    templates_by_type = {}
    all_templates = set()
    for obj in service.get_objects():
        if obj.attributes.get('register', '1') == '0':
            obj_type = obj.object_type
            if obj_type not in templates_by_type:
                templates_by_type[obj_type] = {}
            name = obj.attributes.get('name')
            if name:
                templates_by_type[obj_type][name] = obj
                all_templates.add((obj_type, name))

    # Track all referenced templates
    referenced_templates = set()

    # Check for invalid use references and track referenced templates
    for obj in service.get_objects():
        use_value = obj.attributes.get('use', '')
        if use_value:
            obj_type = obj.object_type
            template_names = [t.strip() for t in use_value.split(',') if t.strip()]

            for tmpl_name in template_names:
                # Track reference
                referenced_templates.add((obj_type, tmpl_name))

                # Check if template exists
                if obj_type not in templates_by_type or tmpl_name not in templates_by_type[obj_type]:
                    issues['invalid_use'].append({
                        'object_name': obj.get_name(),
                        'object_type': obj_type,
                        'source_file': obj.source_file,
                        'template_name': tmpl_name,
                        'message': f"{obj_type.capitalize()} '{obj.get_name()}' references unknown template '{tmpl_name}'"
                    })

    def get_template_chain(obj_type, tmpl_name, visited=None):
        """Iteratively get all templates in chain to avoid recursion limits."""
        if visited is None:
            visited = set()

        chain = []
        stack = [(obj_type, tmpl_name)]

        while stack:
            curr_type, curr_name = stack.pop()

            if (curr_type, curr_name) in visited:
                continue  # Circular dependency or already processed

            visited.add((curr_type, curr_name))
            chain.append((curr_type, curr_name))

            if curr_type in templates_by_type and curr_name in templates_by_type[curr_type]:
                tmpl_obj = templates_by_type[curr_type][curr_name]
                use_value = tmpl_obj.attributes.get('use', '')
                if use_value:
                    for parent_name in [t.strip() for t in use_value.split(',') if t.strip()]:
                        stack.append((curr_type, parent_name))

        return chain

    # Expand referenced_templates to include indirect references
    # Unused template definition: template not in ANY inheritance chain (direct or transitive)
    # Example: A uses B, B uses C -> all three are "used" even if only A is directly referenced
    indirect_refs = set()
    for obj_type, tmpl_name in referenced_templates:
        chain = get_template_chain(obj_type, tmpl_name)
        indirect_refs.update(chain)

    referenced_templates.update(indirect_refs)

    # Find unused templates (not in any inheritance chain)
    for obj_type, tmpl_name in all_templates:
        if (obj_type, tmpl_name) not in referenced_templates:
            issues['unused_templates'].append({
                'template_name': tmpl_name,
                'object_type': obj_type,
                'message': f"Template '{tmpl_name}' is not used by any {obj_type}"
            })

    return jsonify(issues)
