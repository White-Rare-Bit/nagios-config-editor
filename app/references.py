"""Which objects refer to a given object, and how to rewrite those references.

Used by rename (``POST /api/objects/rename``) and by the delete warning
(``GET /api/objects/referenced-by``). A reference is a typed thing: renaming
one "PING" service must not touch another service whose own description is
PING, and renaming hostgroup "web" must not touch contactgroup "web".

The rules, for a target of type T named N (its ``NAME_FIELDS[T]`` value):

- A field refers to T when ``REFERENCE_FIELDS`` maps it to T, except an
  object's own identity field when that object is itself of type T.
- ``use`` names templates by their ``name`` attribute, which rename does not
  change, so rename never edits it. ``referenced_by`` reports it separately
  (``include_template_uses``) so deleting a template still warns.
- ``members`` counts only on the group type whose member type is T
  (``GROUP_STRUCTURE``). Servicegroup ``members`` are ``host,service`` pairs:
  the host halves refer to hosts, the service halves to services.
- ``parents`` counts only between hosts.
- Service references are scoped to a host: a ``*service_description`` field
  counts only when its paired ``*host_name`` shares a host with the target
  service, or its paired ``*hostgroup_name`` shares a hostgroup with it
  (``!`` exclusions ignored). A servicedependency with no dependent host or
  hostgroup depends on a service of the master host, as in Nagios.
- Command references carry arguments (``check_ping!100``); only the part
  before the first ``!`` is the command name, and the arguments are kept.

Matching compares whole list items with ``+``/``!`` prefixes and whitespace
stripped, never substrings.
"""

from __future__ import annotations

from collections.abc import Iterable

from .nagios_model import GROUP_STRUCTURE, NAME_FIELDS, REFERENCE_FIELDS, NagiosObject

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
    """Split one list item into [prefix, name, suffix]; only name is compared."""
    text = text.strip()
    name = text.lstrip(_PREFIX_CHARS).strip()
    prefix = text[: text.index(name)] if name else text
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
    """The names in a host/hostgroup list, leaving out ``!`` exclusions."""
    if not value:
        return set()
    return {
        name for prefix, name, _ in (_parse_item(p, False) for p in value.split(","))
        if name and "!" not in prefix
    }


def replace_reference(value: str, old: str, new: str) -> str:
    """Replace list items naming ``old`` with ``new``, keeping +/! prefixes.

    Items are compared whole, with prefixes and whitespace stripped, so
    "web-010" is not a match for "web-01". Items come back trimmed and joined
    by ",".
    """
    items = [_parse_item(part, False) for part in value.split(",")]
    for item in items:
        if item[1] == old:
            item[1] = new
    return _render(items)


# -- matching ------------------------------------------------------------------


def name_field(obj: NagiosObject) -> str | None:
    """The attribute that names this object, if the object has one."""
    field = NAME_FIELDS.get(obj.object_type)
    if field and obj.attributes.get(field, "").strip():
        return field
    return None


class _Target:
    """What is needed to recognise references to one object."""

    def __init__(self, obj: NagiosObject):
        self.obj = obj
        self.type = obj.object_type
        field = name_field(obj)
        self.name = obj.attributes[field].strip() if field else ""
        self.hosts = _names(obj.attributes.get("host_name"))
        self.hostgroups = _names(obj.attributes.get("hostgroup_name"))

    def same_host(self, obj: NagiosObject, field: str) -> bool:
        """Whether ``field`` (a *service_description) is paired with the target's hosts."""
        pair = field[: -len(_SERVICE_FIELD)]
        attrs = obj.attributes
        hosts = _names(attrs.get(pair + "host_name"))
        groups = _names(attrs.get(pair + "hostgroup_name"))
        if pair == "dependent_" and not hosts and not groups:
            hosts, groups = _names(attrs.get("host_name")), _names(attrs.get("hostgroup_name"))
        return bool(hosts & self.hosts or groups & self.hostgroups)


def _matching(items: list[list[str]], name: str, positions: Iterable[int]) -> list[int]:
    return [i for i in positions if items[i][1] == name]


def _hits(obj: NagiosObject, target: _Target) -> list[tuple[str, list[int]]]:
    """(field, item positions) in ``obj`` that refer to ``target``."""
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
            if target.type == "service" and not target.same_host(obj, field):
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


def _candidates(objects: Iterable[NagiosObject], exclude: set[int]) -> Iterable[NagiosObject]:
    return (o for o in objects if id(o) not in exclude and not o.is_commented_out)


def referenced_by(
    objects: Iterable[NagiosObject],
    target: NagiosObject,
    exclude: set[int] | None = None,
    include_template_uses: bool = False,
) -> list[tuple[NagiosObject, list[str]]]:
    """Objects that refer to ``target``, each with the fields that do.

    The target itself and objects whose ``id`` is in ``exclude`` are left out.
    With ``include_template_uses``, objects that ``use`` the target as a
    template are reported too (field "use"); rename does not change those.
    """
    skip = {id(target), *(exclude or ())}
    info = _Target(target)
    result = []
    for obj in _candidates(objects, skip):
        fields = [field for field, _ in _hits(obj, info)] if info.name else []
        if include_template_uses and _uses(obj, target):
            fields.append("use")
        if fields:
            result.append((obj, fields))
    return result


def reference_edits(
    objects: Iterable[NagiosObject],
    renames: list[tuple[NagiosObject, str]],
    exclude: set[int],
) -> list[tuple[NagiosObject, dict[str, str]]]:
    """The new attributes of every object that refers to a renamed object.

    ``renames`` is a list of (object, new name). All renames are matched
    against the current values, so renaming a→b and b→c together does not
    turn a into c. An object referring to several renamed objects, or in
    several fields, gets one merged attributes dict. Objects whose ``id`` is
    in ``exclude`` (normally the renamed objects) are left alone.
    """
    targets = [(_Target(obj), new) for obj, new in renames]
    edits = []
    for obj in _candidates(objects, exclude):
        changes: dict[str, dict[int, str]] = {}
        for target, new in targets:
            if not target.name or obj is target.obj:
                continue
            for field, positions in _hits(obj, target):
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
