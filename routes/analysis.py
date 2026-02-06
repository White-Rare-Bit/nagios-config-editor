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

        if uses:
            template_names = [t.strip() for t in uses.split(',') if t.strip()]
            for tmpl_name in template_names:
                if tmpl_name in templates and tmpl_name not in visited:
                    visited.add(tmpl_name)
                    chain.extend(get_chain(templates[tmpl_name], visited))

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
                    'type': 'ip-subnet',
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
                    'type': 'hostname-prefix',
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
                    'type': 'hostname-suffix',
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
                    'type': 'check-command',
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
                    'type': 'network-parent',
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
        'ip-subnet': 1.5,
        'hostname-prefix': 1.3,
        'hostname-suffix': 1.2,
        'network-parent': 1.4,
        'check-command': 1.0,
        'common-services': 0.9,
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
                continue  # Already processed (cycle detection is separate)

            visited.add((curr_type, curr_name))
            chain.append((curr_type, curr_name))

            if curr_type in templates_by_type and curr_name in templates_by_type[curr_type]:
                tmpl_obj = templates_by_type[curr_type][curr_name]
                use_value = tmpl_obj.attributes.get('use', '')
                if use_value:
                    for parent_name in [t.strip() for t in use_value.split(',') if t.strip()]:
                        stack.append((curr_type, parent_name))

        return chain

    # N-02: Detect circular dependencies using DFS with path tracking
    # A cycle exists when we revisit a node that's still in the current traversal path
    def detect_cycles():
        """Detect circular template dependencies using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {}  # node -> color
        cycles = []  # List of detected cycles

        def dfs(node, path):
            """DFS with path tracking for cycle detection."""
            if color.get(node) == BLACK:
                return  # Already fully processed
            if color.get(node) == GRAY:
                # Found a cycle - extract the cycle from path
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return

            color[node] = GRAY
            path.append(node)

            obj_type, tmpl_name = node
            if obj_type in templates_by_type and tmpl_name in templates_by_type[obj_type]:
                tmpl_obj = templates_by_type[obj_type][tmpl_name]
                use_value = tmpl_obj.attributes.get('use', '')
                if use_value:
                    for parent_name in [t.strip() for t in use_value.split(',') if t.strip()]:
                        parent_node = (obj_type, parent_name)
                        # Only follow edges to existing templates
                        if obj_type in templates_by_type and parent_name in templates_by_type[obj_type]:
                            dfs(parent_node, path)

            path.pop()
            color[node] = BLACK

        # Run DFS from all templates
        for node in all_templates:
            if color.get(node) == WHITE or node not in color:
                dfs(node, [])

        return cycles

    # Detect and report circular dependencies
    detected_cycles = detect_cycles()
    seen_cycles = set()  # Track unique cycles (avoid duplicates)
    for cycle in detected_cycles:
        # Create a canonical representation for deduplication
        cycle_key = tuple(sorted(cycle[:-1]))  # Exclude duplicate end node
        if cycle_key not in seen_cycles:
            seen_cycles.add(cycle_key)
            cycle_names = [name for _, name in cycle]
            issues['circular_dependencies'].append({
                'cycle': cycle_names,
                'object_type': cycle[0][0],
                'message': f"Circular template inheritance: {' -> '.join(cycle_names)}"
            })

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


@bp.route('/api/escalation-path/<object_type>/<name>')
@bp.route('/api/escalation-path/<object_type>/<name>/<service_desc>')
def api_escalation_path(object_type, name, service_desc=None):
    """Get escalation path for a host or service.

    Returns base contacts and escalation levels in notification order.
    """
    service = get_service()

    # Find target object
    target = None
    for obj in service.get_objects():
        if object_type == 'host':
            if obj.object_type == 'host' and obj.get_name() == name:
                target = obj
                break
        elif object_type == 'service' and service_desc:
            if obj.object_type == 'service':
                host_attr = obj.attributes.get('host_name', '')
                svc_desc = obj.attributes.get('service_description', '')
                if name in [h.strip() for h in host_attr.split(',')] and svc_desc == service_desc:
                    target = obj
                    break

    if not target:
        return jsonify({'error': 'Object not found'}), 404

    # Build lookups
    template_lookup = {}
    contact_objects = {}
    cg_objects = {}
    for obj in service.get_objects():
        tmpl_name = obj.attributes.get('name')
        if tmpl_name:
            template_lookup[(obj.object_type, tmpl_name)] = obj
        if obj.object_type == 'contact' and obj.attributes.get('register', '1') != '0':
            contact_objects[obj.attributes.get('contact_name', '')] = obj
        elif obj.object_type == 'contactgroup':
            cg_objects[obj.attributes.get('contactgroup_name', '')] = obj

    def resolve_attrs(obj, visited=None):
        if visited is None:
            visited = set()
        resolved = {}
        use_templates = obj.attributes.get('use', '')
        if use_templates:
            for t in [t.strip() for t in use_templates.split(',') if t.strip()]:
                if t not in visited:
                    visited.add(t)
                    tmpl = template_lookup.get((obj.object_type, t))
                    if tmpl:
                        for k, v in resolve_attrs(tmpl, visited).items():
                            if k not in ('use', 'name', 'register'):
                                resolved[k] = v
        for k, v in obj.attributes.items():
            resolved[k] = v
        return resolved

    def resolve_cg_members(cg_name):
        """Resolve contactgroup to individual contact names."""
        cg = cg_objects.get(cg_name)
        if not cg:
            return []
        members = []
        if 'members' in cg.attributes:
            members.extend([m.strip() for m in cg.attributes['members'].split(',') if m.strip()])
        return members

    def contact_info(cname):
        """Get contact notification info."""
        cobj = contact_objects.get(cname)
        if not cobj:
            return {'name': cname, 'exists': False}
        resolved = resolve_attrs(cobj)
        return {
            'name': cname,
            'exists': True,
            'host_notification_commands': resolved.get('host_notification_commands', ''),
            'service_notification_commands': resolved.get('service_notification_commands', ''),
            'host_notification_period': resolved.get('host_notification_period', ''),
            'service_notification_period': resolved.get('service_notification_period', ''),
        }

    # Resolve base contacts
    resolved_target = resolve_attrs(target)
    base_contact_names = set()
    if 'contacts' in resolved_target:
        for c in resolved_target['contacts'].split(','):
            c = c.strip().lstrip('+!')
            if c:
                base_contact_names.add(c)
    if 'contact_groups' in resolved_target:
        for cg in resolved_target['contact_groups'].split(','):
            cg = cg.strip().lstrip('+!')
            for m in resolve_cg_members(cg):
                base_contact_names.add(m)

    base_contacts = [contact_info(c) for c in sorted(base_contact_names)]

    # Find matching escalations
    esc_type = 'hostescalation' if object_type == 'host' else 'serviceescalation'
    escalations = []
    for obj in service.get_objects():
        if obj.object_type != esc_type:
            continue

        # Check if escalation matches our target
        matches = False
        if object_type == 'host':
            esc_hosts = obj.attributes.get('host_name', '')
            if name in [h.strip() for h in esc_hosts.split(',')]:
                matches = True
        else:
            esc_hosts = obj.attributes.get('host_name', '')
            esc_svc = obj.attributes.get('service_description', '')
            if service_desc and esc_svc == service_desc:
                if name in [h.strip() for h in esc_hosts.split(',')]:
                    matches = True

        if not matches:
            continue

        # Resolve escalation contacts
        esc_contact_names = set()
        if 'contact_groups' in obj.attributes:
            for cg in obj.attributes['contact_groups'].split(','):
                cg = cg.strip()
                for m in resolve_cg_members(cg):
                    esc_contact_names.add(m)
        if 'contacts' in obj.attributes:
            for c in obj.attributes['contacts'].split(','):
                c = c.strip()
                if c:
                    esc_contact_names.add(c)

        escalations.append({
            'first_notification': int(obj.attributes.get('first_notification', 0)),
            'last_notification': int(obj.attributes.get('last_notification', 0)),
            'notification_interval': int(obj.attributes.get('notification_interval', 0)),
            'escalation_period': obj.attributes.get('escalation_period', ''),
            'contacts': [contact_info(c) for c in sorted(esc_contact_names)],
            'source_file': obj.source_file,
        })

    # Sort escalations by first_notification
    escalations.sort(key=lambda e: e['first_notification'])

    return jsonify({
        'object_type': object_type,
        'name': name,
        'service_description': service_desc,
        'base_contacts': base_contacts,
        'escalations': escalations,
    })


@bp.route('/api/object-references/<int:global_index>')
def api_object_references(global_index):
    """Return all relationships for an object by global_index."""
    service = get_service()
    p = service.parser
    objects = list(p.objects)

    if global_index < 0 or global_index >= len(objects):
        return jsonify({'error': 'Object not found'}), 404

    obj = objects[global_index]
    obj_name = obj.get_name() or obj.get_display_name()
    obj_template_name = obj.attributes.get('name')

    from nagios_model import REFERENCE_FIELDS, NAME_FIELDS

    def strip_prefix(s):
        return s.strip().lstrip('+!').strip()

    command_fields = [
        'check_command', 'event_handler', 'notification_commands',
        'host_notification_commands', 'service_notification_commands',
        'obsess_over_host_command', 'obsess_over_service_command',
        'global_host_event_handler', 'global_service_event_handler'
    ]

    def obj_summary(o, idx):
        return {
            'global_index': idx,
            'object_type': o.object_type,
            'name': o.get_name() or o.get_display_name(),
            'file': o.source_file,
        }

    obj_to_index = {id(o): idx for idx, o in enumerate(objects)}

    # --- Outgoing references ---
    outgoing = []
    for field, ref_type in REFERENCE_FIELDS.items():
        val = obj.attributes.get(field)
        if not val:
            continue
        actual_type = ref_type if ref_type else obj.object_type
        for v in val.split(','):
            v = strip_prefix(v)
            if not v or v == '*':
                continue
            lookup_val = v.split('!')[0] if field in command_fields else v
            for idx, o in enumerate(objects):
                if o.object_type != actual_type:
                    continue
                o_name = o.get_name() or o.get_display_name()
                o_template = o.attributes.get('name')
                if o_name == lookup_val or o_template == lookup_val:
                    if idx != global_index:
                        outgoing.append({**obj_summary(o, idx), 'field': field})
                    break

    # --- Incoming references ---
    incoming = []
    for idx, o in enumerate(objects):
        if idx == global_index:
            continue
        for field, ref_type in REFERENCE_FIELDS.items():
            val = o.attributes.get(field)
            if not val:
                continue
            actual_type = ref_type if ref_type else o.object_type
            is_escalation_ref = (
                o.object_type in ('hostescalation', 'serviceescalation') and
                obj.object_type in ('contact', 'contactgroup') and
                field in ('escalation_contacts', 'escalation_contact_groups', 'contacts', 'contact_groups')
            )
            if actual_type != obj.object_type and ref_type is not None and not is_escalation_ref:
                continue
            values = [strip_prefix(v) for v in val.split(',')]
            if field in command_fields:
                values = [v.split('!')[0] if '!' in v else v for v in values]
            if obj_name in values or (obj_template_name and obj_template_name in values):
                incoming.append({**obj_summary(o, idx), 'field': field})

    # --- Dependency rules ---
    # master_of = this object is the master → goes in outgoing (object depends on this rule)
    # dependent_of = this object is the dependent → goes in incoming
    if obj.object_type == 'host':
        for idx, o in enumerate(objects):
            if o.object_type != 'hostdependency':
                continue
            master_hosts = [h.strip() for h in o.attributes.get('host_name', '').split(',') if h.strip()]
            dependent_hosts = [h.strip() for h in o.attributes.get('dependent_host_name', '').split(',') if h.strip()]
            if obj_name in master_hosts:
                outgoing.append({
                    **obj_summary(o, idx), 'field': 'dependency_rule',
                    'is_dependency_rule': True, 'role': 'master_of',
                })
            if obj_name in dependent_hosts:
                incoming.append({
                    **obj_summary(o, idx), 'field': 'dependency_rule',
                    'is_dependency_rule': True, 'role': 'dependent_of',
                })
    elif obj.object_type == 'service':
        host_name = obj.attributes.get('host_name')
        if host_name:
            svc_name = obj_name
            for idx, o in enumerate(objects):
                if o.object_type != 'servicedependency':
                    continue
                master_svc = o.attributes.get('service_description', '')
                master_hosts = [h.strip() for h in o.attributes.get('host_name', '').split(',') if h.strip()]
                dep_svc = o.attributes.get('dependent_service_description', '')
                dep_hosts = [h.strip() for h in o.attributes.get('dependent_host_name', '').split(',') if h.strip()]
                if master_svc == svc_name and (not master_hosts or host_name in master_hosts):
                    outgoing.append({
                        **obj_summary(o, idx), 'field': 'dependency_rule',
                        'is_dependency_rule': True, 'role': 'master_of',
                    })
                if dep_svc == svc_name and (not dep_hosts or host_name in dep_hosts):
                    incoming.append({
                        **obj_summary(o, idx), 'field': 'dependency_rule',
                        'is_dependency_rule': True, 'role': 'dependent_of',
                    })

    # --- Escalation rules ---
    def is_host_in_hostgroup(host_name, hostgroup_name, visited=None):
        if visited is None:
            visited = set()
        if hostgroup_name in visited:
            return False
        visited.add(hostgroup_name)
        for o in objects:
            if o.object_type != 'hostgroup':
                continue
            if (o.get_name() or '') != hostgroup_name:
                continue
            members = [m.strip() for m in o.attributes.get('members', '').split(',') if m.strip()]
            if host_name in members:
                return True
            for ho in objects:
                if ho.object_type == 'host' and (ho.get_name() or '') == host_name:
                    hgs = [g.strip().lstrip('+!').strip() for g in ho.attributes.get('hostgroups', '').split(',') if g.strip()]
                    if hostgroup_name in hgs:
                        return True
                    break
            nested = [g.strip().lstrip('+!').strip() for g in o.attributes.get('hostgroup_members', '').split(',') if g.strip()]
            for ng in nested:
                if is_host_in_hostgroup(host_name, ng, visited):
                    return True
        return False

    if obj.object_type == 'host':
        for idx, o in enumerate(objects):
            if o.object_type != 'hostescalation':
                continue
            esc_host = o.attributes.get('host_name', '')
            esc_hg = o.attributes.get('hostgroup_name', '')
            if esc_host and obj_name in [h.strip() for h in esc_host.split(',')]:
                incoming.append({**obj_summary(o, idx), 'field': 'escalation_rule', 'is_escalation_rule': True})
            elif esc_hg:
                for g in [g.strip() for g in esc_hg.split(',') if g.strip()]:
                    if is_host_in_hostgroup(obj_name, g):
                        incoming.append({**obj_summary(o, idx), 'field': 'escalation_rule', 'is_escalation_rule': True})
                        break
    elif obj.object_type == 'service':
        host_name = obj.attributes.get('host_name')
        if host_name:
            for idx, o in enumerate(objects):
                if o.object_type != 'serviceescalation':
                    continue
                esc_svc = o.attributes.get('service_description', '')
                esc_host = o.attributes.get('host_name', '')
                esc_hg = o.attributes.get('hostgroup_name', '')
                if not esc_svc or obj_name not in [s.strip() for s in esc_svc.split(',')]:
                    continue
                if esc_host and host_name in [h.strip() for h in esc_host.split(',')]:
                    incoming.append({**obj_summary(o, idx), 'field': 'escalation_rule', 'is_escalation_rule': True})
                elif esc_hg:
                    for g in [g.strip() for g in esc_hg.split(',') if g.strip()]:
                        if is_host_in_hostgroup(host_name, g):
                            incoming.append({**obj_summary(o, idx), 'field': 'escalation_rule', 'is_escalation_rule': True})
                            break
                elif not esc_host and not esc_hg:
                    incoming.append({**obj_summary(o, idx), 'field': 'escalation_rule', 'is_escalation_rule': True})

    # --- Services via hostgroup (for hosts and hostgroups) ---
    if obj.object_type == 'hostgroup':
        for idx, o in enumerate(objects):
            if o.object_type != 'service':
                continue
            hg_name = o.attributes.get('hostgroup_name', '')
            if hg_name:
                groups = [g.strip().lstrip('+!').strip() for g in hg_name.split(',')]
                if obj_name in groups:
                    incoming.append({**obj_summary(o, idx), 'field': 'hostgroup_name', 'is_service_binding': True})
    elif obj.object_type == 'host':
        for idx, o in enumerate(objects):
            if o.object_type != 'service':
                continue
            if o.attributes.get('host_name'):
                continue
            hg_name = o.attributes.get('hostgroup_name', '')
            if hg_name:
                for g in [g.strip().lstrip('+!').strip() for g in hg_name.split(',') if g.strip()]:
                    if is_host_in_hostgroup(obj_name, g):
                        incoming.append({**obj_summary(o, idx), 'field': 'hostgroup_name', 'is_service_binding': True, 'via_group': g})
                        break

    # --- Members ---
    members = []
    member_of = []

    if obj.object_type == 'hostgroup':
        direct = [m.strip() for m in obj.attributes.get('members', '').split(',') if m.strip()]
        for idx, o in enumerate(objects):
            if o.object_type == 'host':
                h_name = o.get_name() or ''
                if h_name in direct:
                    members.append({**obj_summary(o, idx), 'via': 'members'})
                else:
                    hgs = [g.strip().lstrip('+!').strip() for g in o.attributes.get('hostgroups', '').split(',') if g.strip()]
                    if obj_name in hgs:
                        members.append({**obj_summary(o, idx), 'via': 'hostgroups attr'})
    elif obj.object_type == 'contactgroup':
        direct = [m.strip().lstrip('+!').strip() for m in obj.attributes.get('members', '').split(',') if m.strip()]
        for idx, o in enumerate(objects):
            if o.object_type == 'contact':
                c_name = o.get_name() or ''
                if c_name in direct:
                    members.append({**obj_summary(o, idx), 'via': 'members'})
                else:
                    cgs = [g.strip().lstrip('+!').strip() for g in o.attributes.get('contactgroups', '').split(',') if g.strip()]
                    if obj_name in cgs:
                        members.append({**obj_summary(o, idx), 'via': 'contactgroups attr'})
    elif obj.object_type == 'servicegroup':
        direct = [m.strip().lstrip('+!').strip() for m in obj.attributes.get('members', '').split(',') if m.strip()]
        for idx, o in enumerate(objects):
            if o.object_type == 'service':
                s_name = o.get_name() or ''
                if s_name in direct:
                    members.append({**obj_summary(o, idx), 'via': 'members'})
                else:
                    sgs = [g.strip().lstrip('+!').strip() for g in o.attributes.get('servicegroups', '').split(',') if g.strip()]
                    if obj_name in sgs:
                        members.append({**obj_summary(o, idx), 'via': 'servicegroups attr'})
    elif obj.attributes.get('register', '1') == '0':
        template_name = obj.attributes.get('name', '')
        if template_name:
            for idx, o in enumerate(objects):
                if idx == global_index:
                    continue
                uses = [u.strip() for u in o.attributes.get('use', '').split(',') if u.strip()]
                if template_name in uses:
                    members.append({**obj_summary(o, idx), 'via': 'inherits'})

    # Member-of
    if obj.object_type == 'host':
        hgs = [g.strip().lstrip('+!').strip() for g in obj.attributes.get('hostgroups', '').split(',') if g.strip()]
        for idx, o in enumerate(objects):
            if o.object_type == 'hostgroup' and (o.get_name() or '') in hgs:
                member_of.append({**obj_summary(o, idx), 'via': 'hostgroups'})
        for idx, o in enumerate(objects):
            if o.object_type != 'hostgroup':
                continue
            direct = [m.strip() for m in o.attributes.get('members', '').split(',') if m.strip()]
            if obj_name in direct:
                g_name = o.get_name() or ''
                if not any(m['name'] == g_name for m in member_of):
                    member_of.append({**obj_summary(o, idx), 'via': 'members'})
    elif obj.object_type == 'service':
        sgs = [g.strip().lstrip('+!').strip() for g in obj.attributes.get('servicegroups', '').split(',') if g.strip()]
        for idx, o in enumerate(objects):
            if o.object_type == 'servicegroup' and (o.get_name() or '') in sgs:
                member_of.append({**obj_summary(o, idx), 'via': 'servicegroups'})
    elif obj.object_type == 'contact':
        cgs = [g.strip().lstrip('+!').strip() for g in obj.attributes.get('contactgroups', '').split(',') if g.strip()]
        for idx, o in enumerate(objects):
            if o.object_type == 'contactgroup' and (o.get_name() or '') in cgs:
                member_of.append({**obj_summary(o, idx), 'via': 'contactgroups'})

    # --- Parent hosts (for hosts only) ---
    parent_hosts = None
    if obj.object_type == 'host':
        parents_attr = obj.attributes.get('parents', '').strip()
        if parents_attr:
            def build_parent_tree(host_obj, visited=None):
                if visited is None:
                    visited = set()
                h_idx = obj_to_index.get(id(host_obj))
                h_name = host_obj.get_name() or host_obj.get_display_name()
                if h_idx in visited:
                    return {'name': h_name, 'global_index': h_idx, 'circular': True}
                visited.add(h_idx)
                p_attr = host_obj.attributes.get('parents', '')
                parent_names = [p.strip() for p in p_attr.split(',') if p.strip()]
                parent_nodes = []
                for pn in parent_names:
                    parent_obj = None
                    for o in objects:
                        if o.object_type == 'host' and (o.get_name() or '') == pn:
                            parent_obj = o
                            break
                    if parent_obj:
                        parent_nodes.append(build_parent_tree(parent_obj, set(visited)))
                    else:
                        parent_nodes.append({'name': pn, 'missing': True})
                return {
                    'name': h_name,
                    'global_index': h_idx,
                    'file': host_obj.source_file,
                    'parents': parent_nodes,
                }
            parent_hosts = build_parent_tree(obj)

    return jsonify({
        'outgoing': outgoing,
        'incoming': incoming,
        'members': members,
        'member_of': member_of,
        'parent_hosts': parent_hosts,
    })
