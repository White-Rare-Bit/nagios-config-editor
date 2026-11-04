"""Shared scanning rules for Nagios object definitions.

Used by both the parser (to find objects) and file_operations (to find the
text of an object to edit, move or delete), so the two always agree on where
a block starts and ends.

Comments follow the same rule as NagiosConfigParser._parse_attributes and
Nagios itself: a line whose first non-blank character is # or ;, or anything
after an unquoted ; on a line. Comment text is never syntax: it cannot open
or close a block, start a quoted string, or start a nested define.
"""

import re

# Start of an object definition: "define <type> {"
DEFINE_RE = re.compile(r"define\s+(\w+)\s*\{")

LIVE = "live"            # a real define, not inside a comment
COMMENTED = "commented"  # "#define host {" header of a block commented out line by line
IN_COMMENT = "comment"   # "define ... {" appearing inside comment prose: not a block


def _line_start(content: str, pos: int) -> int:
    return content.rfind("\n", 0, pos) + 1


def _line_end(content: str, pos: int) -> int:
    end = content.find("\n", pos)
    return len(content) if end < 0 else end


def classify_define(content: str, define_pos: int, brace_pos: int) -> str:
    """Classify a "define <type> {" match by the comment around it.

    COMMENTED only for a pure header like "#define host {" or "; define host {"
    with nothing after the brace; this is how a block commented out line by
    line starts. Any other define inside a comment ("# copy the define host {
    block below", "#define host { host_name x }") is IN_COMMENT.
    """
    prefix = content[_line_start(content, define_pos):define_pos]
    stripped = prefix.strip()
    if not (stripped.startswith(("#", ";")) or ";" in prefix):
        return LIVE
    rest_of_line = content[brace_pos + 1:_line_end(content, brace_pos)]
    if set(stripped) <= set("#;") and not rest_of_line.strip():
        return COMMENTED
    return IN_COMMENT


def scan_block(content: str, brace_open: int, comment_aware: bool = True) -> tuple:
    """Scan from an opening brace to its matching closing brace.

    Respects quoted strings and backslash escapes. With comment_aware, comment
    text is skipped and quotes do not run past the end of a line (except over a
    backslash line continuation), so an apostrophe in a comment or value cannot
    swallow the rest of the file. comment_aware=False is the original scan, used
    for blocks commented out line by line, whose closing "#}" is itself a comment.

    Returns:
        (end_pos, brace_depth, nested_define_pos): end_pos is the position after
        the closing brace (or where scanning stopped), brace_depth is 0 when the
        brace was matched, nested_define_pos is the first nested "define" at
        depth 1, or None.

    """
    length = len(content)
    j = brace_open + 1
    brace_depth = 1
    in_double_quote = False
    in_single_quote = False
    nested_define_pos = None

    while j < length and brace_depth > 0:
        char = content[j]
        prev_char = content[j - 1] if j > 0 else ""

        if prev_char == "\\":
            j += 1
            continue

        if comment_aware:
            if char == "\n":
                in_double_quote = in_single_quote = False
                j += 1
                first = j
                while first < length and content[first] in " \t":
                    first += 1
                if first < length and content[first] in "#;":
                    j = _line_end(content, first)
                continue
            if char == ";" and not in_double_quote and not in_single_quote:
                j = _line_end(content, j)
                continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif not in_double_quote and not in_single_quote:
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
            elif (char == "d" and brace_depth == 1 and nested_define_pos is None
                  and content.startswith("define", j) and DEFINE_RE.match(content, j)):
                nested_define_pos = j

        j += 1

    return (j, brace_depth, nested_define_pos)
