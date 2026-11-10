"""Reference value rewriting used by rename (app/references.py)."""

from app.references import replace_reference


def test_replace_reference_plain():
    assert replace_reference("a,b,c", "b", "x") == "a,x,c"


def test_rename_keeps_prefixes_and_list_order():
    assert replace_reference("a, !web-01 ,+b", "web-01", "web-02") == "a,!web-02,+b"


def test_replace_reference_no_partial_match():
    assert replace_reference("web-010", "web-01", "x") == "web-010"


def test_replace_reference_normalises_prefix_whitespace():
    assert replace_reference("+ !web", "web", "x") == "+!x"
