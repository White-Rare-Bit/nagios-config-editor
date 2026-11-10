"""Graph View data: a node for every object and an edge for every reference.

Served by ``GET /api/dependencies``. Domain logic only, no routes.

Node ids are ``"<type>:<name>"``. A defined service is
``"service:<targets>:<description>"``, where targets is its ``hostgroup_name``
(or else ``host_name``) list as written, so two services with the same
description on different hosts get different nodes. Explorer builds the same
id to open the graph on a service, so it must not change.

A reference to a service is a (host, description) pair: servicedependency and
serviceescalation ``*service_description`` fields (paired with the matching
``*host_name`` / ``*hostgroup_name``), service ``parents`` and servicegroup
``members``. Each pair is resolved to the service object that applies to that
host, directly or through a hostgroup, as Nagios does. Only a pair that no
service matches becomes an undefined node (``"exists": false``).

Edges go from the object that has the field to the object it names, except
``reverse`` fields (``GRAPH_EDGE_FIELDS``). Each edge carries its field
(``label``) and ``category``; the frontend reads labels, colours and
categories from ``/api/metadata``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .inheritance import build_template_lookup, build_template_names_set, resolve_inherited_attrs
from .nagios_model import (
    ADDITIVE_FIELDS,
    GRAPH_EDGE_FIELDS,
    GRAPH_NODE_TYPES,
    NagiosObject,
    graph_edge_category,
    is_template_object,
)
from .references import HostMembership
from .stable_keys import generate_stable_key_for_object

# An object's own name field is not a reference to itself.
_IDENTITY_FIELDS = {
    "host": "host_name",
    "hostgroup": "hostgroup_name",
    "servicegroup": "servicegroup_name",
    "contact": "contact_name",
    "contactgroup": "contactgroup_name",
}

# *service_description fields and the prefix of the host fields they pair with.
_SERVICE_REF_PREFIX = {
    "service_description": "",
    "dependent_service_description": "dependent_",
    "master_service_description": "master_",
}

# A service label lists its hosts/hostgroups only while that stays short;
# longer lists are summarised ("HTTP / 9 hosts") and given in ``detail``.
_MAX_TARGET_LABEL = 32

_UNKNOWN_COLOR = "#999999"


def _names(value: str | None) -> list[str]:
    """List items with ``+`` stripped and ``!`` exclusions left out, in order."""
    out = []
    for part in (value or "").split(","):
        part = part.strip().lstrip("+").strip()
        if part and not part.startswith("!"):
            out.append(part)
    return out


def _service_targets(attrs: dict[str, str]) -> tuple[str, list[str]]:
    """The field a service is bound by (hostgroup_name, else host_name) and its items."""
    if attrs.get("hostgroup_name"):
        return "hostgroup_name", _names(attrs["hostgroup_name"])
    return "host_name", _names(attrs.get("host_name"))


def service_node_id(obj: NagiosObject) -> str:
    """Node id of a defined service (see module docstring)."""
    _, targets = _service_targets(obj.attributes)
    if targets:
        return f"service:{','.join(targets)}:{obj.get_name()}"
    return f"service:{obj.get_name()}"


def _service_label(obj: NagiosObject) -> tuple[str, str | None]:
    """Display label of a service, and the full target list when the label shortens it."""
    field, targets = _service_targets(obj.attributes)
    name = obj.get_name() or ""
    if not targets:
        return name, None
    joined = ",".join(targets)
    if len(targets) == 1 or len(joined) <= _MAX_TARGET_LABEL:
        return f"{name} / {joined}", None
    noun = "hostgroups" if field == "hostgroup_name" else "hosts"
    return f"{name} / {len(targets)} {noun}", joined


class _Graph:
    """Nodes by id (insertion-ordered) and de-duplicated edges."""

    def __init__(self):
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self._edge_index: dict[tuple[str, str, str], dict[str, Any]] = {}

    def node(self, node_id: str, node_type: str, label: str) -> dict[str, Any]:
        """The node with this id, created as undefined if new."""
        existing = self.nodes.get(node_id)
        if existing is not None:
            return existing
        node: dict[str, Any] = {
            "id": node_id,
            "label": label,
            "type": node_type,
            "color": GRAPH_NODE_TYPES.get(node_type, {}).get("color", _UNKNOWN_COLOR),
            "exists": False,
        }
        if "→" in label:
            # Searchable as "->" too (servicedependency names use the arrow).
            node["search_label"] = label.replace("→", "->")
        self.nodes[node_id] = node
        return node

    def edge(self, src: str, dst: str, field: str, category: str, additive: bool) -> None:
        if src == dst:
            return
        if GRAPH_EDGE_FIELDS[field].get("reverse"):
            src, dst = dst, src
        key = (src, dst, field)
        existing = self._edge_index.get(key)
        if existing is not None:
            if additive:
                existing["additive"] = True
            return
        edge: dict[str, Any] = {"from": src, "to": dst, "label": field, "arrows": "to", "category": category}
        if additive:
            edge["additive"] = True
        self._edge_index[key] = edge
        self.edges.append(edge)


class _ServiceIndex:
    """Which service object applies to each (host, description).

    A service bound to a host by ``host_name`` takes precedence over one that
    reaches the host through a hostgroup, as in Nagios.
    """

    def __init__(self, services: Iterable[tuple[str, NagiosObject, dict[str, str]]],
                 hosts: HostMembership):
        self.hosts = hosts
        self._by_host: dict[str, dict[str, tuple[int, str]]] = {}
        self._by_description: dict[str, set[str]] = {}
        for node_id, obj, attrs in services:
            description = obj.get_name() or ""
            self._by_description.setdefault(description, set()).add(node_id)
            direct = set(_names(attrs.get("host_name")))
            for host in hosts.expand(attrs.get("host_name"), attrs.get("hostgroup_name")):
                rank = 1 if host in direct else 0
                current = self._by_host.setdefault(host, {}).get(description)
                if current is None or rank > current[0]:
                    self._by_host[host][description] = (rank, node_id)

    def lookup(self, host: str, description: str) -> list[str]:
        """Node ids of the service(s) ``description`` on ``host``; ``*`` = all of them."""
        services = self._by_host.get(host, {})
        if description == "*":
            return [node_id for _, node_id in services.values()]
        found = services.get(description)
        return [found[1]] if found else []

    def resolve(self, hosts: set[str], description: str) -> tuple[list[str], list[str]]:
        """(node ids found, hosts on which no such service exists)."""
        found: list[str] = []
        missing: list[str] = []
        for host in sorted(hosts):
            ids = self.lookup(host, description)
            if ids:
                found.extend(i for i in ids if i not in found)
            else:
                missing.append(host)
        return found, missing

    def by_description(self, description: str) -> list[str]:
        return sorted(self._by_description.get(description, ()))


class _Builder:
    def __init__(self, objects: list[NagiosObject]):
        self.objects = objects
        lookup = build_template_lookup(objects)
        self.template_names = build_template_names_set(objects)
        self.resolved = {id(o): resolve_inherited_attrs(o, lookup) for o in objects}
        self.hosts = HostMembership(objects, attrs_of=lambda o: self.resolved[id(o)])
        self.graph = _Graph()
        self.node_ids: dict[int, str] = {}
        services = []
        for obj in objects:
            if not obj.get_name():
                continue
            node_id = service_node_id(obj) if obj.object_type == "service" else \
                f"{obj.object_type}:{obj.get_name()}"
            self.node_ids[id(obj)] = node_id
            if (obj.object_type == "service" and not obj.is_commented_out
                    and not is_template_object(obj)):
                services.append((node_id, obj, self.resolved[id(obj)]))
        self.services = _ServiceIndex(services, self.hosts)

    # -- nodes -----------------------------------------------------------------

    def define(self, obj: NagiosObject) -> str:
        node_id = self.node_ids[id(obj)]
        if obj.object_type == "service":
            label, detail = _service_label(obj)
        else:
            label, detail = obj.get_name() or "", None
        node = self.graph.node(node_id, obj.object_type, label)
        if not node["exists"]:
            node["label"] = label
            node["exists"] = True
            node["stable_key"] = generate_stable_key_for_object(obj)
            if detail:
                node["detail"] = detail
        if (obj.object_type, obj.get_name()) in self.template_names:
            node["is_template"] = True
        return node_id

    def _undefined_service(self, context: list[str], description: str) -> str:
        node_id = f"service:{','.join(context)}:{description}" if context else f"service:{description}"
        label = f"{description} / {','.join(context)}" if context else description
        self.graph.node(node_id, "service", label)
        return node_id

    # -- service references ----------------------------------------------------

    def _pair_hosts(self, attrs: dict[str, str], prefix: str) -> tuple[set[str], list[str]] | None:
        """Hosts named by the host fields paired with a *service_description field.

        Returns (expanded hosts, the items as written), or None when the object
        names no host or hostgroup for this pair.
        """
        host_value = attrs.get(prefix + "host_name")
        group_value = attrs.get(prefix + "hostgroup_name")
        if prefix == "dependent_" and not host_value and not group_value:
            # A dependency with no dependent host depends on a service of the master host.
            host_value, group_value = attrs.get("host_name"), attrs.get("hostgroup_name")
        if not host_value and not group_value:
            return None
        written = _names(group_value) or _names(host_value)
        return self.hosts.expand(host_value, group_value), written

    def _service_refs(self, attrs: dict[str, str], field: str, description: str) -> list[str]:
        pair = self._pair_hosts(attrs, _SERVICE_REF_PREFIX[field])
        if pair is None:
            matches = self.services.by_description(description)
            return matches if len(matches) == 1 else [self._undefined_service([], description)]
        hosts, written = pair
        found, missing = self.services.resolve(hosts, description)
        if missing:
            found.append(self._undefined_service(missing, description))
        elif not found:
            # The hosts/hostgroups expand to nothing (unknown or empty groups).
            found.append(self._undefined_service(written, description))
        return found

    def _service_parent_refs(self, attrs: dict[str, str], items: list[str]) -> list[str]:
        """Parents of a service: host,service pairs, else descriptions on its own hosts."""
        if items and len(items) % 2 == 0:
            pairs = [(items[i], items[i + 1]) for i in range(0, len(items), 2)]
            resolved = [self.services.lookup(h, s) for h, s in pairs]
            if all(resolved):
                return [i for ids in resolved for i in ids]
        own_hosts = self.hosts.expand(attrs.get("host_name"), attrs.get("hostgroup_name"))
        out: list[str] = []
        for description in items:
            found, missing = self.services.resolve(own_hosts, description)
            if missing or not found:
                found.append(self._undefined_service(missing or _service_targets(attrs)[1], description))
            out.extend(found)
        return out

    def _servicegroup_member_refs(self, items: list[str]) -> list[str]:
        """Servicegroup members: host,service pairs."""
        out = []
        for i in range(0, len(items) - 1, 2):
            host, description = items[i], items[i + 1]
            out.extend(self.services.lookup(host, description)
                       or [self._undefined_service([host], description)])
        return out

    # -- edges -----------------------------------------------------------------

    def _target(self, obj: NagiosObject, field: str, name: str) -> str:
        target = GRAPH_EDGE_FIELDS[field]["target"]
        if target == "template":
            node_type = obj.object_type
        elif target == "member":
            node_type = obj.object_type.replace("group", "")
        else:
            node_type = target
        node_id = f"{node_type}:{name}"
        self.graph.node(node_id, node_type, name)
        return node_id

    def relationships(self, obj: NagiosObject, node_id: str) -> None:
        attrs = self.resolved[id(obj)]
        for field in GRAPH_EDGE_FIELDS:
            raw_value = attrs.get(field)
            if not raw_value or _IDENTITY_FIELDS.get(obj.object_type) == field:
                continue
            category = graph_edge_category(obj.object_type, field)

            # resolve_inherited_attrs consumes the leading + during the merge, so
            # additive references are found on the object's own attribute.
            additive = set()
            own_value = obj.attributes.get(field, "")
            if own_value.startswith("+") and field in ADDITIVE_FIELDS.get(obj.object_type, set()):
                additive = {t.strip().lstrip("+").strip() for t in own_value.split(",")
                            if t.strip().startswith("+")}

            if GRAPH_EDGE_FIELDS[field]["target"] == "command":
                items = [n for n in (c.split("!")[0].strip() for c in raw_value.split(",")) if n]
                if not field.endswith("notification_commands"):
                    items = items[:1]  # one command; its arguments may contain commas
            else:
                items = _names(raw_value)

            if obj.object_type == "servicegroup" and field == "members":
                for target_id in self._servicegroup_member_refs(items):
                    self.graph.edge(node_id, target_id, field, category, False)
                continue
            if obj.object_type == "service" and field == "parents":
                for target_id in self._service_parent_refs(attrs, items):
                    self.graph.edge(node_id, target_id, field, category, False)
                continue

            for item in items:
                if field in _SERVICE_REF_PREFIX:
                    targets = self._service_refs(attrs, field, item)
                else:
                    targets = [self._target(obj, field, item)]
                is_additive = item in additive
                for target_id in targets:
                    if is_additive:
                        self.graph.nodes[target_id]["additive"] = True
                    self.graph.edge(node_id, target_id, field, category, is_additive)


def build_dependency_graph(objects: list[NagiosObject], object_type: str | None = None) -> dict:
    """``{"nodes": [...], "edges": [...]}`` for the Graph View.

    ``object_type`` limits the objects whose nodes and outgoing references are
    included (the targets they name still appear).
    """
    builder = _Builder(objects)
    included = [o for o in objects
                if o.get_name() and (not object_type or o.object_type == object_type)]
    node_ids = [(obj, builder.define(obj)) for obj in included]
    for obj, node_id in node_ids:
        builder.relationships(obj, node_id)
    return {"nodes": list(builder.graph.nodes.values()), "edges": builder.graph.edges}
