"""Which objects refer to a given object, and how to rewrite those references.

Used by rename (``POST /api/objects/rename``) and by the delete warning
(``GET /api/objects/referenced-by``). A reference is a typed thing: renaming
one "PING" service must not touch another service whose own description is
PING, and renaming hostgroup "web" must not touch contactgroup "web".

What a rename changes (``name_field``):

- A template (``is_template_object``) is renamed by its ``name``. The only
  references to it are ``use`` entries on objects of the same object type.
- A registered object of a ``RENAMEABLE_TYPES`` type is renamed by its
  ``NAME_FIELDS`` field. Other types (dependencies, escalations, extinfo)
  have no name of their own and are not renamed.

The rules for a registered target of type T named N:

- A field refers to T when ``REFERENCE_FIELDS`` maps it to T, except an
  object's own identity field when that object is itself of type T.
- ``use`` names templates, not registered objects, so it is never edited.
  ``referenced_by`` can report it (``include_template_uses``) for an object
  that also has a ``name``, so deleting it still warns.
- ``members`` counts only on the group type whose member type is T
  (``GROUP_STRUCTURE``). Servicegroup ``members`` are ``host,service`` pairs:
  the host halves refer to hosts, the service halves to services.
- ``parents`` counts only between hosts.
- Service references are scoped to hosts: a ``*service_description`` field
  counts only when the hosts named by its paired ``*host_name`` and
  ``*hostgroup_name`` overlap the target service's hosts, or the paired
  hostgroup names include one of the target's (which covers empty
  hostgroups). Both sides are expanded the way Nagios does
  (``expand_service_hosts``): hostgroups to their member hosts, ``*`` to
  every host, ``!`` exclusions removed. A servicedependency with no
  dependent host or hostgroup depends on a service of the master host.
- Command references carry arguments (``check_ping!100``); only the part
  before the first ``!`` is the command name, and the arguments are kept.

Matching compares whole list items with ``+``/``!`` prefixes and whitespace
stripped, never substrings.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .nagios_model import (
    GROUP_STRUCTURE,
    NAME_FIELDS,
    REFERENCE_FIELDS,
    RENAMEABLE_TYPES,
    NagiosObject,
    expand_service_hosts,
    is_template_object,
)

_PREFIX_CHARS = "+!"
_SERVICE_FIELD = "service_description"


# -- list values ---------------------------------------------------------------


def _is_command(field: str) -> bool:
    return REFERENCE_FIELDS.get(field) == "command"


def _is_list(field: str) -> bool:
    """Whether a value is a comma-separated list.

    Every reference field is, except the single-command ones (check_command,
    event_handler, ...), whose arguments may themselves contain commas.
    """
    return not _is_command(field) or field.endswith("notification_commands")


def _parse_item(text: str, command: bool) -> list[str]:
    """Split one list item into [prefix, name, suffix]; only name is compared.

    The prefix keeps only the +/! characters ("+ !web" gives "+!", "web").
    """
    text = text.strip()
    i = 0
    prefix = ""
    while i < len(text) and (text[i] in _PREFIX_CHARS or text[i].isspace()):
        if text[i] in _PREFIX_CHARS:
            prefix += text[i]
        i += 1
    name = text[i:].strip()
    suffix = ""
    if command and "!" in name:
        name, rest = name.split("!", 1)
        suffix = "!" + rest
        name = name.strip()
    return [prefix, name, suffix]


def _items(field: str, value: str) -> list[list[str]]:
    command = _is_command(field)
    parts = value.split(",") if _is_list(field) else [value]
    return [_parse_item(part, command) for part in parts]


def _render(items: list[list[str]]) -> str:
    return ",".join("".join(item) for item in items)


def _names(value: str | None) -> set[str]:
    """The names in a list, leaving out ``!`` exclusions."""
    if not value:
        return set()
    return {
        name for prefix, name, _ in (_parse_item(p, False) for p in value.split(","))
        if name and "!" not in prefix
    }


# -- what a rename changes -----------------------------------------------------


def name_field(obj: NagiosObject) -> str | None:
    """The attribute a rename of this object changes, or None if it can't be renamed.

    ``name`` for a template; the identity field for a registered object of a
    renameable type. None when that attribute is missing or empty.
    """
    if is_template_object(obj):
        field = "name"
    elif obj.object_type in RENAMEABLE_TYPES:
        field = NAME_FIELDS.get(obj.object_type)
    else:
        return None
    if field and obj.attributes.get(field, "").strip():
        return field
    return None


# -- matching ------------------------------------------------------------------


class HostMembership:
    """Every registered host, and the hosts in each hostgroup.

    Hostgroup membership comes from hostgroup ``members`` (``*`` = every
    host), nested ``hostgroup_members``, and host ``hostgroups``.

    ``attrs_of`` returns the attributes to read for an object; the default is
    the object's own attributes. The Graph View passes the inherited
    (template-resolved) attributes instead.
    """

    def __init__(self, objects: Iterable[NagiosObject],
                 attrs_of: Callable[[NagiosObject], dict[str, str]] | None = None):
        self.all: set[str] = set()
        direct: dict[str, set[str]] = {}
        nested: dict[str, set[str]] = {}
        wildcard: set[str] = set()
        for obj in objects:
            if obj.is_commented_out or is_template_object(obj):
                continue
            attrs = attrs_of(obj) if attrs_of else obj.attributes
            if obj.object_type == "host":
                host = attrs.get("host_name", "").strip()
                if host:
                    self.all.add(host)
                    for group in _names(attrs.get("hostgroups")):
                        direct.setdefault(group, set()).add(host)
            elif obj.object_type == "hostgroup":
                group = attrs.get("hostgroup_name", "").strip()
                if not group:
                    continue
                if attrs.get("members", "").strip() == "*":
                    wildcard.add(group)
                direct.setdefault(group, set()).update(_names(attrs.get("members")) - {"*"})
                nested.setdefault(group, set()).update(_names(attrs.get("hostgroup_members")))
        for group in wildcard:
            direct[group] |= self.all

        def resolve(group: str, seen: set[str]) -> set[str]:
            hosts = set(direct.get(group, ()))
            for sub in nested.get(group, ()):
                if sub not in seen:
                    seen.add(sub)
                    hosts |= resolve(sub, seen)
            return hosts

        self.by_group = {g: resolve(g, {g}) for g in direct.keys() | nested.keys()}

    def expand(self, host_value: str | None, hostgroup_value: str | None) -> set[str]:
        return expand_service_hosts(
            (host_value or "").strip().lstrip("+"), hostgroup_value or "",
            self.by_group, self.all,
        )


class _Target:
    """What is needed to recognise references to one object."""

    def __init__(self, obj: NagiosObject, hosts: HostMembership):
        self.obj = obj
        self.type = obj.object_type
        self.template = is_template_object(obj)
        field = name_field(obj)
        self.name = obj.attributes[field].strip() if field else ""
        self.hosts: set[str] = set()
        self.hostgroups: set[str] = set()
        if self.type == "service" and not self.template:
            attrs = obj.attributes
            self.hosts = hosts.expand(attrs.get("host_name"), attrs.get("hostgroup_name"))
            self.hostgroups = _names(attrs.get("hostgroup_name"))

    def same_host(self, obj: NagiosObject, field: str, hosts: HostMembership) -> bool:
        """Whether ``field`` (a *service_description) is paired with the target's hosts."""
        pair = field[: -len(_SERVICE_FIELD)]
        attrs = obj.attributes
        host_value, group_value = attrs.get(pair + "host_name"), attrs.get(pair + "hostgroup_name")
        if pair == "dependent_" and not host_value and not group_value:
            host_value, group_value = attrs.get("host_name"), attrs.get("hostgroup_name")
        return bool(
            hosts.expand(host_value, group_value) & self.hosts
            or _names(group_value) & self.hostgroups
        )


def _matching(items: list[list[str]], name: str, positions: Iterable[int]) -> list[int]:
    return [i for i in positions if items[i][1] == name]


def _hits(obj: NagiosObject, target: _Target, hosts: HostMembership) -> list[tuple[str, list[int]]]:
    """(field, item positions) in ``obj`` that a rename of ``target`` rewrites."""
    if not target.name:
        return []
    if target.template:
        value = obj.attributes.get("use")
        if obj.object_type != target.type or not value:
            return []
        items = _items("use", value)
        positions = _matching(items, target.name, range(len(items)))
        return [("use", positions)] if positions else []

    hits = []
    for field, value in obj.attributes.items():
        if not value or field == "use":
            continue
        items = _items(field, value)
        everything = range(len(items))
        positions: list[int] = []

        if field == "members":
            group = GROUP_STRUCTURE.get(obj.object_type)
            if group is None:
                continue
            if obj.object_type == "servicegroup":
                # host,service,host,service pairs
                if target.type == "host":
                    positions = _matching(items, target.name, range(0, len(items), 2))
                elif target.type == "service":
                    positions = [
                        i for i in range(1, len(items), 2)
                        if items[i][1] == target.name and items[i - 1][1] in target.hosts
                    ]
            elif group["member_type"] == target.type:
                positions = _matching(items, target.name, everything)
        elif field == "parents":
            if target.type == "host" and obj.object_type == "host":
                positions = _matching(items, target.name, everything)
        elif REFERENCE_FIELDS.get(field) == target.type:
            if obj.object_type == target.type and field == NAME_FIELDS.get(obj.object_type):
                continue  # the object's own name, not a reference
            if target.type == "service" and not target.same_host(obj, field, hosts):
                continue
            positions = _matching(items, target.name, everything)

        if positions:
            hits.append((field, positions))
    return hits


def _uses(obj: NagiosObject, template: NagiosObject) -> bool:
    """Whether ``obj`` inherits from ``template`` by its ``name``."""
    name = template.attributes.get("name", "").strip()
    if not name or obj.object_type != template.object_type or not obj.attributes.get("use"):
        return False
    return any(item[1] == name for item in _items("use", obj.attributes["use"]))


def _candidates(objects: list[NagiosObject], exclude: set[int]) -> Iterable[NagiosObject]:
    return (o for o in objects if id(o) not in exclude and not o.is_commented_out)


def referenced_by(
    objects: Iterable[NagiosObject],
    target: NagiosObject,
    exclude: set[int] | None = None,
    include_template_uses: bool = False,
) -> list[tuple[NagiosObject, list[str]]]:
    """Objects that refer to ``target``, each with the fields that do.

    The target itself and objects whose ``id`` is in ``exclude`` are left out.
    For a template these are the ``use`` entries a rename updates. For a
    registered object, ``include_template_uses`` also reports objects that
    ``use`` it by its ``name`` (field "use"), which a rename leaves alone.
    """
    objects = list(objects)
    hosts = HostMembership(objects)
    info = _Target(target, hosts)
    result = []
    for obj in _candidates(objects, {id(target), *(exclude or ())}):
        fields = [field for field, _ in _hits(obj, info, hosts)]
        if include_template_uses and not info.template and _uses(obj, target):
            fields.append("use")
        if fields:
            result.append((obj, fields))
    return result


def reference_edits(
    objects: Iterable[NagiosObject],
    renames: list[tuple[NagiosObject, str]],
    exclude: set[int] | None = None,
) -> list[tuple[NagiosObject, dict[str, str]]]:
    """The new attributes of every object that refers to a renamed object.

    ``renames`` is a list of (object, new name). All renames are matched
    against the current values, so renaming a→b and b→c together does not
    turn a into c. An object referring to several renamed objects, or in
    several fields, gets one merged attributes dict. Renamed objects are
    edited too when they refer to each other (a host's ``parents``, a
    service's ``host_name``); their own name field is never touched here.
    Objects whose ``id`` is in ``exclude`` are left alone.
    """
    objects = list(objects)
    hosts = HostMembership(objects)
    targets = [(_Target(obj, hosts), new) for obj, new in renames]
    edits = []
    for obj in _candidates(objects, set(exclude or ())):
        changes: dict[str, dict[int, str]] = {}
        for target, new in targets:
            if obj is target.obj:
                continue
            for field, positions in _hits(obj, target, hosts):
                for i in positions:
                    changes.setdefault(field, {}).setdefault(i, new)
        if not changes:
            continue
        attrs = dict(obj.attributes)
        for field, by_position in changes.items():
            items = _items(field, attrs[field])
            for i, new in by_position.items():
                items[i][1] = new
            attrs[field] = _render(items)
        edits.append((obj, attrs))
    return edits
