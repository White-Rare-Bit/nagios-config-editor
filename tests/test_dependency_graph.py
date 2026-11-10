"""Graph View data: app/dependency_graph.py and GET /api/dependencies (GRAPH_REVIEW 3, 8, 10, 18, 21)."""

from app.dependency_graph import build_dependency_graph
from app.nagios_model import GRAPH_EDGE_CATEGORIES, GRAPH_EDGE_FIELDS, GRAPH_NODE_TYPES, NagiosObject


def _obj(object_type, **attrs):
    return NagiosObject(object_type=object_type, attributes=attrs, source_file="/cfg/objects.cfg")


def _graph(*objects):
    graph = build_dependency_graph(list(objects))
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = {(e["from"], e["label"], e["to"]) for e in graph["edges"]}
    return nodes, edges, graph


BASE = [
    _obj("host", host_name="web-01", use="linux-server"),
    _obj("host", host_name="web-02", use="linux-server"),
    _obj("host", name="linux-server", register="0", hostgroups="web"),
    _obj("hostgroup", hostgroup_name="web"),
    _obj("service", hostgroup_name="web", service_description="HTTP", check_command="check_http!80"),
    _obj("service", host_name="web-01", service_description="Health"),
]


def test_service_reference_through_host_list_resolves_to_hostgroup_service():
    dep = _obj("servicedependency", host_name="web-01,web-02", service_description="HTTP",
               dependent_host_name="web-01", dependent_service_description="Health")
    nodes, edges, _ = _graph(*BASE, dep)
    dep_id = f"servicedependency:{dep.get_name()}"
    assert (dep_id, "service_description", "service:web:HTTP") in edges
    assert (dep_id, "dependent_service_description", "service:web-01:Health") in edges
    assert not [n for n in nodes.values() if n["type"] == "service" and not n["exists"]]


def test_hostgroup_membership_inherited_from_a_template_counts():
    # web-01/web-02 are in "web" only through linux-server's hostgroups.
    dep = _obj("serviceescalation", host_name="web-02", service_description="HTTP")
    _, edges, _ = _graph(*BASE, dep)
    assert (f"serviceescalation:{dep.get_name()}", "service_description", "service:web:HTTP") in edges


def test_service_bound_by_host_name_wins_over_hostgroup_service():
    direct = _obj("service", host_name="web-01", service_description="HTTP")
    dep = _obj("servicedependency", host_name="web-01", service_description="HTTP",
               dependent_service_description="Health")
    _, edges, _ = _graph(*BASE, direct, dep)
    dep_id = f"servicedependency:{dep.get_name()}"
    assert (dep_id, "service_description", "service:web-01:HTTP") in edges
    assert (dep_id, "service_description", "service:web:HTTP") not in edges


def test_unmatched_service_reference_is_undefined_and_names_the_missing_hosts():
    dep = _obj("servicedependency", host_name="web-01,web-02", service_description="Health",
               dependent_host_name="web-01", dependent_service_description="HTTP")
    nodes, edges, _ = _graph(*BASE, dep)
    # Health exists on web-01 only.
    dep_id = f"servicedependency:{dep.get_name()}"
    assert (dep_id, "service_description", "service:web-01:Health") in edges
    assert nodes["service:web-02:Health"]["exists"] is False
    assert (dep_id, "service_description", "service:web-02:Health") in edges


def test_servicegroup_members_resolve_host_service_pairs():
    sg = _obj("servicegroup", servicegroup_name="web-checks", members="web-02,HTTP,web-01,Missing")
    nodes, edges, _ = _graph(*BASE, sg)
    assert ("servicegroup:web-checks", "members", "service:web:HTTP") in edges
    assert nodes["service:web-01:Missing"]["exists"] is False


def test_service_parents_as_pairs_and_as_descriptions_on_own_host():
    pair = _obj("service", host_name="web-02", service_description="App", parents="web-01,Health")
    same_host = _obj("service", host_name="web-01", service_description="App", parents="HTTP")
    _, edges, _ = _graph(*BASE, pair, same_host)
    # parents edges run from the parent to the child
    assert ("service:web-01:Health", "parents", "service:web-02:App") in edges
    assert ("service:web:HTTP", "parents", "service:web-01:App") in edges


def test_edge_directions():
    _, edges, _ = _graph(*BASE, _obj("host", host_name="router"), _obj("host", host_name="db", parents="router"))
    assert ("service:web-01:Health", "host_name", "host:web-01") in edges
    assert ("host:web-01", "use", "host:linux-server") in edges
    assert ("host:router", "parents", "host:db") in edges
    assert ("service:web:HTTP", "check_command", "command:check_http") in edges


def test_categories_follow_metadata_and_contactgroup_members_are_contacts():
    objs = [*BASE,
            _obj("hostgroup", hostgroup_name="db", members="web-01"),
            _obj("contactgroup", contactgroup_name="admins", members="alice"),
            _obj("contact", contact_name="alice", contactgroups="admins")]
    _, _, graph = _graph(*objs)
    by_key = {(e["from"], e["label"]): e["category"] for e in graph["edges"]}
    assert by_key[("hostgroup:db", "members")] == "groups"
    assert by_key[("contactgroup:admins", "members")] == "contacts"
    assert by_key[("contact:alice", "contactgroups")] == "contacts"
    for edge in graph["edges"]:
        assert edge["category"] in GRAPH_EDGE_CATEGORIES


def test_no_duplicate_edges():
    dep = _obj("servicedependency", host_name="web-01,web-02", service_description="HTTP",
               dependent_service_description="Health")
    _, edges, graph = _graph(*BASE, dep)
    assert len(edges) == len(graph["edges"])


def test_long_service_target_lists_are_summarised():
    hosts = ",".join(f"app-server-{i:02d}" for i in range(9))
    svc = _obj("service", host_name=hosts, service_description="Disk")
    nodes, _, _ = _graph(svc)
    node = nodes[f"service:{hosts}:Disk"]
    assert node["label"] == "Disk / 9 hosts"
    assert node["detail"] == hosts
    assert node["exists"] is True
    short = _graph(*BASE)[0]["service:web:HTTP"]
    assert short["label"] == "HTTP / web"
    assert "detail" not in short


def test_defined_nodes_carry_a_stable_key_and_undefined_ones_do_not():
    nodes, _, _ = _graph(*BASE, _obj("host", host_name="db", parents="ghost"))
    assert nodes["host:web-01"]["stable_key"] == "/cfg/objects.cfg|host|web-01"
    assert nodes["host:ghost"]["exists"] is False
    assert "stable_key" not in nodes["host:ghost"]


def test_every_edge_field_has_label_colour_and_known_category():
    for field, meta in GRAPH_EDGE_FIELDS.items():
        assert meta["label"] and meta["color"].startswith("#"), field
        assert meta["category"] in GRAPH_EDGE_CATEGORIES, field
        for category in meta.get("category_by_type", {}).values():
            assert category in GRAPH_EDGE_CATEGORIES, field
        assert meta["target"] in GRAPH_NODE_TYPES or meta["target"] in ("template", "member"), field


def test_api_dependencies_on_sample_config(client):
    data = client.get("/api/dependencies").get_json()
    ids = {n["id"] for n in data["nodes"]}
    # Previously drawn as undefined: the dependency names HTTP through a host list.
    assert "service:web-prod-01,web-prod-02,web-prod-03:HTTP" not in ids
    assert "service:web-servers:HTTP" in ids
    undefined_services = [n["id"] for n in data["nodes"] if n["type"] == "service" and not n["exists"]]
    assert undefined_services == []
    fields = set(GRAPH_EDGE_FIELDS)
    assert all(e["label"] in fields for e in data["edges"])


def test_metadata_serves_graph_tables(client):
    graph = client.get("/api/metadata").get_json()["data"]["graph"]
    assert graph["node_types"]["host"]["color"] == GRAPH_NODE_TYPES["host"]["color"]
    assert "dependency_period" in graph["edge_fields"]
    assert graph["edge_category_order"] == list(GRAPH_EDGE_CATEGORIES)
    assert graph["node_type_order"] == list(GRAPH_NODE_TYPES)
