"""Unified Nagios template inheritance resolution.

Single source of truth for template lookup, attribute resolution,
chain walking, and template analysis. All modules that need inheritance
logic import from here instead of maintaining independent implementations.

Key design choices:
- Correct Nagios precedence: first template in 'use' list wins
- Cycle detection via visited set (prevents infinite loops)
- Sibling-branch reuse via visited.discard (A uses B,C both using D works)
- Error reporting for missing templates and cycles
- Source tracking in resolve_chain for UI display
"""

# Attributes excluded from inheritance resolution
INHERITANCE_META = frozenset({"use", "name", "register"})

# Sentinel for null cancellation: when an attribute is set to the literal
# string "null", it blocks inheriting that field from templates.
_NULL_SENTINEL = object()


# ─────────────────────────────────────────────────────────────────────
# Template lookup builders
# ─────────────────────────────────────────────────────────────────────

def build_template_lookup(objects):
    """Build (object_type, template_name) -> obj lookup.

    Used by health_checks, validation, analysis (dependency graph, escalation).
    """
    lookup = {}
    for obj in objects:
        tmpl_name = obj.attributes.get("name")
        if tmpl_name:
            lookup[(obj.object_type, tmpl_name)] = obj
    return lookup


def build_type_template_lookup(objects, obj_type):
    """Build name -> obj lookup for templates of a given type.

    Used by templates.py for type-scoped inheritance resolution.
    """
    lookup = {}
    for obj in objects:
        if obj.object_type == obj_type and obj.attributes.get("name"):
            lookup[obj.attributes["name"]] = obj
    return lookup


def build_template_names_set(objects):
    """Build set of (object_type, name) for template objects (register=0)."""
    template_names = set()
    for obj in objects:
        if obj.attributes.get("register", "1") == "0":
            obj_name = obj.attributes.get("name")
            if obj_name:
                template_names.add((obj.object_type, obj_name))
    return template_names


def build_template_index(objects):
    """Build templates_by_type dict and all_templates set.

    Returns:
        Tuple of (templates_by_type, all_templates) where:
        - templates_by_type: dict[obj_type][name] -> obj
        - all_templates: set of (obj_type, name) tuples
    """
    templates_by_type = {}
    all_templates = set()
    for obj in objects:
        if obj.attributes.get("register", "1") == "0":
            obj_type = obj.object_type
            if obj_type not in templates_by_type:
                templates_by_type[obj_type] = {}
            name = obj.attributes.get("name")
            if name:
                templates_by_type[obj_type][name] = obj
                all_templates.add((obj_type, name))
    return templates_by_type, all_templates


# ─────────────────────────────────────────────────────────────────────
# Attribute resolution (correct Nagios precedence + cycle detection)
# ─────────────────────────────────────────────────────────────────────

def resolve_inherited_attrs(obj, template_lookup, visited=None):
    """Resolve attributes including inherited ones from templates.

    Nagios precedence: object's own attrs > first template > second > ... > last.
    Uses visited set for cycle detection and discard for sibling-branch reuse.

    Args:
        obj: NagiosObject to resolve
        template_lookup: dict of (obj_type, tmpl_name) -> obj
        visited: set of template names already in the current resolution path

    Returns:
        dict[attr_name, value] — flat resolved attributes
    """
    if visited is None:
        visited = set()
    resolved = {}
    use_templates = obj.attributes.get("use", "")
    if use_templates:
        for tmpl_name in (t.strip() for t in use_templates.split(",") if t.strip()):
            if tmpl_name not in visited:
                visited.add(tmpl_name)
                tmpl = template_lookup.get((obj.object_type, tmpl_name))
                if tmpl:
                    tmpl_attrs = resolve_inherited_attrs(tmpl, template_lookup, visited)
                    for key, value in tmpl_attrs.items():
                        if key not in INHERITANCE_META and key not in resolved:
                            resolved[key] = value
                visited.discard(tmpl_name)
    # Object's own attributes always override;
    # "null" values become sentinels to block inheritance;
    # "+" prefix on non-custom vars appends to inherited value
    for key, value in obj.attributes.items():
        if value == "null":
            resolved[key] = _NULL_SENTINEL
        elif (
            value.startswith("+")
            and not key.startswith("_")
            and key not in INHERITANCE_META
        ):
            stripped = value[1:]
            existing = resolved.get(key)
            if existing is not None and existing is not _NULL_SENTINEL:
                resolved[key] = f"{existing},{stripped}"
            else:
                resolved[key] = stripped
        else:
            resolved[key] = value
    # Strip null-cancelled keys from the result
    return {k: v for k, v in resolved.items() if v is not _NULL_SENTINEL}


def has_attr_in_chain(obj, attr_name, template_lookup, visited=None):
    """Check if attribute exists in object or its template chain.

    Short-circuits on first hit. Uses visited set for cycle detection
    and discard for sibling-branch reuse.
    """
    if visited is None:
        visited = set()
    if attr_name in obj.attributes:
        # "null" cancels the attribute — treat as not present
        return obj.attributes[attr_name] != "null"
    use_val = obj.attributes.get("use", "")
    if not use_val:
        return False
    for t_name in (t.strip() for t in use_val.split(",") if t.strip()):
        if t_name not in visited:
            visited.add(t_name)
            tmpl = template_lookup.get((obj.object_type, t_name))
            if tmpl and has_attr_in_chain(tmpl, attr_name, template_lookup, visited):
                return True
            visited.discard(t_name)
    return False


# ─────────────────────────────────────────────────────────────────────
# Chain walking
# ─────────────────────────────────────────────────────────────────────

def walk_inheritance_chain(obj, templates, visited=None):
    """Walk the template inheritance chain recursively.

    Args:
        obj: NagiosObject to start from
        templates: dict[name] -> obj (type-scoped lookup)
        visited: set of template names for cycle detection

    Returns:
        list of obj.to_dict() entries in chain order
    """
    if visited is None:
        visited = set()
    chain = [obj.to_dict()]
    uses = obj.attributes.get("use", "")
    if uses:
        for tmpl_name in (t.strip() for t in uses.split(",") if t.strip()):
            if tmpl_name in templates and tmpl_name not in visited:
                visited.add(tmpl_name)
                chain.extend(walk_inheritance_chain(templates[tmpl_name], templates, visited))
    return chain


def resolve_chain(obj, obj_type, template_lookup, visited=None):
    """Resolve template inheritance chain with source tracking.

    Correct Nagios precedence: first template's values win over later templates.
    Object's own attributes always override inherited ones.

    Args:
        obj: NagiosObject to resolve
        obj_type: object type string
        template_lookup: dict[name] -> obj (type-scoped lookup)
        visited: set of template names for cycle detection

    Returns:
        Tuple of (chain, inherited, errors) where:
        - chain: list of template dicts in resolution order
        - inherited: dict[attr] -> {"value": ..., "source": ...}
        - errors: list of error message strings
    """
    if visited is None:
        visited = set()

    chain = []
    inherited = {}
    errors = []

    use_value = obj.attributes.get("use", "")
    if use_value:
        template_names = [t.strip() for t in use_value.split(",") if t.strip()]
        for tmpl_name in template_names:
            if tmpl_name not in template_lookup:
                errors.append(f"Template '{tmpl_name}' not found for type '{obj_type}'")
                continue
            if tmpl_name in visited:
                errors.append(f"Circular dependency: {' -> '.join(visited)} -> {tmpl_name}")
                continue

            visited.add(tmpl_name)
            tmpl_obj = template_lookup[tmpl_name]
            tmpl_chain, tmpl_inherited, tmpl_errors = resolve_chain(
                tmpl_obj, obj_type, template_lookup, visited,
            )

            # First template to set a key wins (correct Nagios precedence)
            for key, entry in tmpl_inherited.items():
                if key not in INHERITANCE_META and key not in inherited:
                    inherited[key] = entry

            chain.append({"name": tmpl_name, "type": obj_type, "attributes": tmpl_obj.attributes})
            chain.extend(tmpl_chain)
            errors.extend(tmpl_errors)

            # Allow reuse in sibling branches (A uses B,C where both use D)
            visited.discard(tmpl_name)

    # Object's own attributes override inherited;
    # "null" values cancel the attribute entirely;
    # "+" prefix on non-custom vars appends to inherited value
    obj_name = obj.get_name() or obj.attributes.get("name", "(unknown)")
    for key, value in obj.attributes.items():
        if key not in INHERITANCE_META:
            if value == "null":
                inherited.pop(key, None)
            elif (
                value.startswith("+")
                and not key.startswith("_")
            ):
                stripped = value[1:]
                existing = inherited.get(key)
                if existing is not None:
                    inherited[key] = {
                        "value": f"{existing['value']},{stripped}",
                        "source": f"{existing['source']},{obj_name}",
                    }
                else:
                    inherited[key] = {"value": stripped, "source": obj_name}
            else:
                inherited[key] = {"value": value, "source": obj_name}

    return chain, inherited, errors


# ─────────────────────────────────────────────────────────────────────
# Template analysis
# ─────────────────────────────────────────────────────────────────────

def get_template_chain(templates_by_type, obj_type, tmpl_name, visited=None):
    """Iteratively get all templates in chain to avoid recursion limits.

    Uses a stack-based approach for deep chains.
    """
    if visited is None:
        visited = set()
    chain = []
    stack = [(obj_type, tmpl_name)]
    while stack:
        curr_type, curr_name = stack.pop()
        if (curr_type, curr_name) in visited:
            continue
        visited.add((curr_type, curr_name))
        chain.append((curr_type, curr_name))
        if curr_type in templates_by_type and curr_name in templates_by_type[curr_type]:
            tmpl_obj = templates_by_type[curr_type][curr_name]
            use_value = tmpl_obj.attributes.get("use", "")
            if use_value:
                for parent_name in (t.strip() for t in use_value.split(",") if t.strip()):
                    stack.append((curr_type, parent_name))
    return chain


def detect_template_cycles(templates_by_type, all_templates):
    """Detect circular template dependencies using DFS with 3-color path tracking."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {}
    cycles = []

    def dfs(node, path):
        if color.get(node) == BLACK:
            return
        if color.get(node) == GRAY:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        color[node] = GRAY
        path.append(node)
        obj_type, tmpl_name = node
        if obj_type in templates_by_type and tmpl_name in templates_by_type[obj_type]:
            tmpl_obj = templates_by_type[obj_type][tmpl_name]
            use_value = tmpl_obj.attributes.get("use", "")
            if use_value:
                for parent_name in (t.strip() for t in use_value.split(",") if t.strip()):
                    parent_node = (obj_type, parent_name)
                    if obj_type in templates_by_type and parent_name in templates_by_type[obj_type]:
                        dfs(parent_node, path)
        path.pop()
        color[node] = BLACK

    for node in all_templates:
        if color.get(node) == WHITE or node not in color:
            dfs(node, [])
    return cycles


def format_cycle_issues(detected_cycles):
    """Convert raw cycle data into issue dicts, deduplicating."""
    issues = []
    seen_cycles = set()
    for cycle in detected_cycles:
        cycle_key = tuple(sorted(cycle[:-1]))
        if cycle_key not in seen_cycles:
            seen_cycles.add(cycle_key)
            cycle_names = [name for _, name in cycle]
            issues.append({
                "cycle": cycle_names,
                "object_type": cycle[0][0],
                "message": f"Circular template inheritance: {' -> '.join(cycle_names)}",
            })
    return issues


def find_invalid_use_refs(objects, templates_by_type):
    """Find objects referencing non-existent templates.

    Returns:
        Tuple of (issues, referenced_templates) where:
        - issues: list of issue dicts
        - referenced_templates: set of (obj_type, tmpl_name) tuples
    """
    issues = []
    referenced_templates = set()
    for obj in objects:
        use_value = obj.attributes.get("use", "")
        if not use_value:
            continue
        obj_type = obj.object_type
        for tmpl_name in (t.strip() for t in use_value.split(",") if t.strip()):
            referenced_templates.add((obj_type, tmpl_name))
            if obj_type not in templates_by_type or tmpl_name not in templates_by_type[obj_type]:
                issues.append({
                    "object_name": obj.get_name(),
                    "object_type": obj_type,
                    "source_file": obj.source_file,
                    "template_name": tmpl_name,
                    "message": f"{obj_type.capitalize()} '{obj.get_name()}' references unknown template '{tmpl_name}'",
                })
    return issues, referenced_templates


def find_unused_templates(all_templates, referenced_templates, templates_by_type):
    """Find templates not referenced by any object (directly or transitively)."""
    indirect_refs = set()
    for obj_type, tmpl_name in referenced_templates:
        chain = get_template_chain(templates_by_type, obj_type, tmpl_name)
        indirect_refs.update(chain)
    all_refs = referenced_templates | indirect_refs

    issues = []
    for obj_type, tmpl_name in all_templates:
        if (obj_type, tmpl_name) not in all_refs:
            issues.append({
                "template_name": tmpl_name,
                "object_type": obj_type,
                "message": f"Template '{tmpl_name}' is not used by any {obj_type}",
            })
    return issues
