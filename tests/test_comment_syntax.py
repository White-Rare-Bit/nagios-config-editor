"""Comment text must never act as config syntax.

Nagios ignores comments: a line starting with # or ;, or anything after an
unquoted ;. Breaks caught: comments that create phantom objects, cut a real
object short, or (via an apostrophe) make a real object disappear; and edits
or deletes that compute the wrong block end around such comments.
"""

import pytest

from app.file_operations import delete_object_from_file, edit_object_in_file
from app.nagios_parser import NagiosConfigParser

WEB_02 = "define host {\n    host_name web-02\n}\n"


def _parse(tmp_path, text):
    (tmp_path / "x.cfg").write_text(text)
    return NagiosConfigParser(str(tmp_path)).parse_all()


def _summary(objects):
    return [(o.line_number, o.attributes, o.is_commented_out) for o in objects]


class TestParserIgnoresCommentText:

    def test_prose_comment_mentioning_define_is_not_an_object(self, tmp_path):
        objs = _parse(tmp_path, "# copy the define host { block below\n" + WEB_02)
        assert _summary(objs) == [(2, {"host_name": "web-02"}, False)]

    def test_one_line_commented_block_is_not_a_live_object(self, tmp_path):
        objs = _parse(tmp_path, "#define host { host_name old }\n" + WEB_02)
        assert _summary(objs) == [(2, {"host_name": "web-02"}, False)]

    def test_comment_inside_block_mentioning_define_does_not_cut_it_short(self, tmp_path):
        objs = _parse(tmp_path, "define host {\n    host_name web-01\n    # was: define host { web-old }\n"
                                "    address 10.0.0.1\n}\n" + WEB_02)
        assert _summary(objs) == [(1, {"host_name": "web-01", "address": "10.0.0.1"}, False),
                                  (6, {"host_name": "web-02"}, False)]

    @pytest.mark.parametrize("comment_line", [
        "    # don't page at night",
        "    ; Bob's notes",
        "    # unbalanced { brace",
        "    # unbalanced } brace",
        '    # stray " quote',
    ])
    def test_full_line_comment_inside_block_is_ignored(self, tmp_path, comment_line):
        objs = _parse(tmp_path, f"define host {{\n    host_name web-01\n{comment_line}\n"
                                f"    address 10.0.0.1\n}}\n" + WEB_02)
        assert _summary(objs) == [(1, {"host_name": "web-01", "address": "10.0.0.1"}, False),
                                  (6, {"host_name": "web-02"}, False)]

    def test_apostrophe_in_inline_comment(self, tmp_path):
        objs = _parse(tmp_path, "define host {\n    host_name web-01 ; Bob's box\n    address 10.0.0.1\n}\n" + WEB_02)
        assert _summary(objs) == [(1, {"host_name": "web-01", "address": "10.0.0.1"}, False),
                                  (5, {"host_name": "web-02"}, False)]
        assert objs[0].inline_comments == {"host_name": "Bob's box"}

    @pytest.mark.parametrize("inline", ["; see {wiki", "; was define host {", "; ends with }"])
    def test_braces_and_define_in_inline_comment_are_ignored(self, tmp_path, inline):
        objs = _parse(tmp_path, f"define host {{\n    host_name web-01 {inline}\n    address 10.0.0.1\n}}\n" + WEB_02)
        assert _summary(objs) == [(1, {"host_name": "web-01", "address": "10.0.0.1"}, False),
                                  (5, {"host_name": "web-02"}, False)]

    def test_apostrophe_in_value(self, tmp_path):
        objs = _parse(tmp_path, "define host {\n    host_name web-01\n    alias Bob's server\n}\n" + WEB_02)
        assert _summary(objs) == [(1, {"host_name": "web-01", "alias": "Bob's server"}, False),
                                  (5, {"host_name": "web-02"}, False)]

    def test_braces_inside_quotes_still_ignored(self, tmp_path):
        objs = _parse(tmp_path, 'define command {\n    command_name c1\n    command_line /bin/echo "} {"\n}\n' + WEB_02)
        assert [o.get_name() for o in objs] == ["c1", "web-02"]
        assert objs[0].attributes["command_line"] == '/bin/echo "} {"'

    # Commented-out objects (an existing feature) must keep working

    def test_block_commented_line_by_line_is_a_commented_out_object(self, tmp_path):
        objs = _parse(tmp_path, "#define host {\n#    host_name old\n#}\n" + WEB_02)
        assert _summary(objs) == [(1, {}, True), (4, {"host_name": "web-02"}, False)]
        assert objs[0].commented_attributes == {"host_name": "old"}

    def test_live_braces_with_commented_attributes_is_a_commented_out_object(self, tmp_path):
        objs = _parse(tmp_path, "define host {\n    #host_name old\n}\n" + WEB_02)
        assert _summary(objs) == [(1, {}, True), (4, {"host_name": "web-02"}, False)]


class TestEditsFindTheRightBlockEnd:
    """Once such objects are visible they can be edited; the edit must replace
    exactly that block and leave the following object alone."""

    # One apostrophe (odd, so it can't cancel out) and unbalanced braces, all in comments
    TEXT = ("define host {\n    host_name web-01\n    # don't page at night {\n"
            "    address 10.0.0.1 ; see {wiki\n}\n\n" + WEB_02)

    def test_edit_replaces_only_its_own_block(self, tmp_path):
        cfg = tmp_path / "x.cfg"
        cfg.write_text(self.TEXT)
        web01 = NagiosConfigParser(str(tmp_path)).parse_all()[0]

        result = edit_object_in_file(str(cfg), web01.line_number,
                                     {**web01.attributes, "alias": "Edited"}, "host",
                                     inline_comments=web01.inline_comments)

        assert result.success, result.error
        objs = NagiosConfigParser(str(tmp_path)).parse_all()
        assert [(o.get_name(), o.attributes.get("alias")) for o in objs] == [("web-01", "Edited"), ("web-02", None)]

    def test_delete_removes_only_its_own_block(self, tmp_path):
        cfg = tmp_path / "x.cfg"
        cfg.write_text(self.TEXT)
        web01 = NagiosConfigParser(str(tmp_path)).parse_all()[0]

        result = delete_object_from_file(str(cfg), web01.line_number)

        assert result.success, result.error
        assert [o.get_name() for o in NagiosConfigParser(str(tmp_path)).parse_all()] == ["web-02"]
        assert "don't page" not in cfg.read_text()
        assert cfg.read_text().count("define host") == 1
