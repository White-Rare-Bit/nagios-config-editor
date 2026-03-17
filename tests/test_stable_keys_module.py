import pytest
from app.stable_keys import generate_stable_key, parse_stable_key, generate_stable_key_for_object


def test_generate_stable_key():
    key = generate_stable_key("hosts.cfg", "host", "webserver1")
    assert key == "hosts.cfg|host|webserver1"


def test_parse_stable_key():
    result = parse_stable_key("hosts.cfg|host|webserver1")
    assert result["source_file"] == "hosts.cfg"
    assert result["object_type"] == "host"
    assert result["name"] == "webserver1"


def test_generate_stable_key_for_object():
    class FakeObj:
        source_file = "hosts.cfg"
        object_type = "host"
        def get_display_name(self):
            return "webserver1"

    key = generate_stable_key_for_object(FakeObj())
    assert key == "hosts.cfg|host|webserver1"


def test_parse_stable_key_with_pipes_in_name():
    result = parse_stable_key("hosts.cfg|host|name|with|pipes")
    assert result["source_file"] == "hosts.cfg"
    assert result["object_type"] == "host"
    assert result["name"] == "name|with|pipes"
