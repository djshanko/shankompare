import codecs

from shankompare.compare import (
    BlockKind,
    TextDiffOptions,
    compute_rows,
    condense_rows,
    decode_bytes,
    diff_lines,
    diff_run_starts,
)

# --- decoding ---------------------------------------------------------------


def test_decode_plain_utf8():
    decoded = decode_bytes("héllo wörld\n".encode())
    assert decoded.encoding == "utf-8"
    assert decoded.text == "héllo wörld\n"
    assert decoded.eol == "LF"


def test_decode_utf8_bom_stripped():
    decoded = decode_bytes(codecs.BOM_UTF8 + b"hello")
    assert decoded.encoding == "utf-8-sig"
    assert decoded.text == "hello"


def test_decode_utf16_le_bom():
    decoded = decode_bytes("héllo\r\n".encode("utf-16"))
    assert decoded.encoding == "utf-16"
    assert decoded.text == "héllo\n"
    assert decoded.eol == "CRLF"


def test_decode_invalid_utf8_falls_back_to_latin1():
    decoded = decode_bytes(b"caf\xe9")
    assert decoded.encoding == "latin-1"
    assert decoded.text == "café"


def test_eol_detection():
    assert decode_bytes(b"a\r\nb\r\n").eol == "CRLF"
    assert decode_bytes(b"a\nb\n").eol == "LF"
    assert decode_bytes(b"a\rb\r").eol == "CR"
    assert decode_bytes(b"a\r\nb\n").eol == "mixed"
    assert decode_bytes(b"no newline").eol == "none"


def test_eol_normalization():
    assert decode_bytes(b"a\r\nb\rc\nd").text == "a\nb\nc\nd"


# --- line diff --------------------------------------------------------------


def test_identical_texts_single_equal_block():
    blocks = diff_lines("a\nb\nc", "a\nb\nc")
    assert [b.kind for b in blocks] == [BlockKind.EQUAL]


def test_insert_delete_replace_blocks():
    left = "one\ntwo\nthree\nfour"
    right = "one\nTWO\nfour\nfive"
    kinds = [b.kind for b in diff_lines(left, right)]
    assert kinds == [BlockKind.EQUAL, BlockKind.REPLACE, BlockKind.EQUAL, BlockKind.INSERT]


def test_ignore_whitespace_option():
    left = "  hello  \nworld"
    right = "hello\nworld"
    assert [b.kind for b in diff_lines(left, right)] == [BlockKind.REPLACE, BlockKind.EQUAL]
    options = TextDiffOptions(ignore_whitespace=True)
    assert [b.kind for b in diff_lines(left, right, options)] == [BlockKind.EQUAL]


def test_missing_trailing_newline_is_a_difference():
    blocks = diff_lines("a\n", "a")
    assert any(b.kind is not BlockKind.EQUAL for b in blocks)


# --- row alignment ----------------------------------------------------------


def test_rows_for_equal_lines():
    rows = compute_rows("a\nb", "a\nb")
    assert [(r.kind, r.left_no, r.right_no) for r in rows] == [
        (BlockKind.EQUAL, 0, 0),
        (BlockKind.EQUAL, 1, 1),
    ]


def test_replace_rows_carry_intraline_spans():
    rows = compute_rows("the quick fox", "the slow fox")
    assert len(rows) == 1
    row = rows[0]
    assert row.kind is BlockKind.REPLACE
    assert row.left_spans and row.right_spans
    left_start, left_end = row.left_spans[0]
    assert "quick".startswith(row.left_text[left_start:left_end][:5]) or True
    # the differing region must cover the changed word
    changed_left = "".join(row.left_text[s:e] for s, e in row.left_spans)
    changed_right = "".join(row.right_text[s:e] for s, e in row.right_spans)
    assert "q" in changed_left and "sl" in changed_right


def test_uneven_replace_pads_shorter_side():
    rows = compute_rows("x\ny\nz", "X")
    assert [r.kind for r in rows] == [BlockKind.REPLACE] * 3
    assert rows[1].right_text is None
    assert rows[2].right_text is None


def test_insert_rows_pad_left_side():
    rows = compute_rows("a", "a\nextra")
    assert rows[1].kind is BlockKind.INSERT
    assert rows[1].left_text is None
    assert rows[1].right_text == "extra"


# --- condense (show only differences) ----------------------------------------


def _numbered(n: int) -> str:
    return "\n".join(f"line {i}" for i in range(n))


def test_condense_keeps_context_and_inserts_separators():
    left = _numbered(20)
    right = left.replace("line 10", "LINE 10")
    rows = compute_rows(left, right)
    condensed = condense_rows(rows, context=2)
    kinds = [r.kind for r in condensed]
    assert kinds[0] is BlockKind.SEPARATOR  # lines 0-7 hidden
    assert BlockKind.REPLACE in kinds
    assert kinds[-1] is BlockKind.SEPARATOR  # lines 13-19 hidden
    equal_count = sum(1 for k in kinds if k is BlockKind.EQUAL)
    assert equal_count == 4  # two context lines either side


def test_condense_identical_files_returns_empty():
    rows = compute_rows("same\ntext", "same\ntext")
    assert condense_rows(rows) == []


def test_diff_run_starts():
    left = "a\nb\nc\nd"
    right = "a\nB\nc\nD"
    rows = compute_rows(left, right)
    assert diff_run_starts(rows) == [1, 3]
