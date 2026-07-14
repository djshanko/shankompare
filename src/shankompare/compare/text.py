"""Text diff engine: decoding, line diff, intra-line spans, row alignment.

Pure Python (no Qt). The UI renders the ``Row`` list produced here; each Row
is one display line in a side-by-side view, with padding rows inserted so
both panes stay aligned.
"""

import codecs
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

Span = tuple[int, int]  # [start, end) character range within a line


class BlockKind(Enum):
    EQUAL = "equal"
    REPLACE = "replace"
    DELETE = "delete"  # present only on the left
    INSERT = "insert"  # present only on the right
    SEPARATOR = "separator"  # display-only, produced by condense_rows


@dataclass(frozen=True)
class DecodedText:
    text: str  # line endings normalized to "\n"
    encoding: str
    eol: str  # "LF", "CRLF", "CR", "mixed", or "none"


def decode_bytes(data: bytes) -> DecodedText:
    """BOM sniff, then strict UTF-8, then Latin-1 fallback; normalize EOLs."""
    try:
        if data.startswith(codecs.BOM_UTF8):
            text, encoding = data.decode("utf-8-sig"), "utf-8-sig"
        elif data[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
            text, encoding = data.decode("utf-16"), "utf-16"
        else:
            text, encoding = data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        text, encoding = data.decode("latin-1"), "latin-1"

    crlf = text.count("\r\n")
    lone_cr = text.count("\r") - crlf
    lone_lf = text.count("\n") - crlf
    present = [name for name, count in (("CRLF", crlf), ("LF", lone_lf), ("CR", lone_cr)) if count]
    if not present:
        eol = "none"
    elif len(present) == 1:
        eol = present[0]
    else:
        eol = "mixed"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return DecodedText(text, encoding, eol)


@dataclass(frozen=True)
class TextDiffOptions:
    ignore_whitespace: bool = False  # ignore leading/trailing whitespace per line


@dataclass(frozen=True)
class DiffBlock:
    """One opcode over line ranges: left[left_start:left_end] vs right[...]."""

    kind: BlockKind
    left_start: int
    left_end: int
    right_start: int
    right_end: int


@dataclass(frozen=True)
class Row:
    """One display line of a side-by-side view. ``None`` text means padding."""

    kind: BlockKind
    left_no: int | None  # 0-based source line number, None for padding/separator
    right_no: int | None
    left_text: str | None
    right_text: str | None
    left_spans: tuple[Span, ...] = ()  # differing character ranges (REPLACE rows)
    right_spans: tuple[Span, ...] = ()


_SEPARATOR_ROW = Row(BlockKind.SEPARATOR, None, None, "⋯", "⋯")

_TAG_TO_KIND = {
    "equal": BlockKind.EQUAL,
    "replace": BlockKind.REPLACE,
    "delete": BlockKind.DELETE,
    "insert": BlockKind.INSERT,
}


def split_lines(text: str) -> list[str]:
    # split("\n") (not splitlines) so a missing newline at EOF shows as a difference
    return text.split("\n")


def diff_lines(left: str, right: str, options: TextDiffOptions | None = None) -> list[DiffBlock]:
    options = options or TextDiffOptions()
    left_lines, right_lines = split_lines(left), split_lines(right)
    if options.ignore_whitespace:
        left_keys = [line.strip() for line in left_lines]
        right_keys = [line.strip() for line in right_lines]
    else:
        left_keys, right_keys = left_lines, right_lines
    matcher = SequenceMatcher(None, left_keys, right_keys, autojunk=False)
    return [
        DiffBlock(_TAG_TO_KIND[tag], i1, i2, j1, j2)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
    ]


def intraline_spans(left: str, right: str) -> tuple[tuple[Span, ...], tuple[Span, ...]]:
    """Character ranges that differ between two paired lines."""
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    left_spans: list[Span] = []
    right_spans: list[Span] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 > i1:
            left_spans.append((i1, i2))
        if j2 > j1:
            right_spans.append((j1, j2))
    return tuple(left_spans), tuple(right_spans)


def align_rows(left: str, right: str, blocks: list[DiffBlock]) -> list[Row]:
    """Expand diff blocks into aligned display rows with padding."""
    left_lines, right_lines = split_lines(left), split_lines(right)
    rows: list[Row] = []
    for block in blocks:
        left_count = block.left_end - block.left_start
        right_count = block.right_end - block.right_start
        if block.kind is BlockKind.EQUAL:
            for k in range(left_count):
                i, j = block.left_start + k, block.right_start + k
                rows.append(Row(BlockKind.EQUAL, i, j, left_lines[i], right_lines[j]))
        elif block.kind is BlockKind.REPLACE:
            for k in range(max(left_count, right_count)):
                i = block.left_start + k if k < left_count else None
                j = block.right_start + k if k < right_count else None
                left_text = left_lines[i] if i is not None else None
                right_text = right_lines[j] if j is not None else None
                if left_text is not None and right_text is not None:
                    left_spans, right_spans = intraline_spans(left_text, right_text)
                else:
                    left_spans, right_spans = (), ()
                rows.append(
                    Row(BlockKind.REPLACE, i, j, left_text, right_text, left_spans, right_spans)
                )
        elif block.kind is BlockKind.DELETE:
            for k in range(left_count):
                i = block.left_start + k
                rows.append(Row(BlockKind.DELETE, i, None, left_lines[i], None))
        else:  # INSERT
            for k in range(right_count):
                j = block.right_start + k
                rows.append(Row(BlockKind.INSERT, None, j, None, right_lines[j]))
    return rows


def compute_rows(left: str, right: str, options: TextDiffOptions | None = None) -> list[Row]:
    return align_rows(left, right, diff_lines(left, right, options))


def condense_rows(rows: list[Row], context: int = 3) -> list[Row]:
    """Keep only rows near differences, separating hidden runs with ⋯ rows.

    Returns an empty list when there are no differences at all.
    """
    keep = [False] * len(rows)
    for idx, row in enumerate(rows):
        if row.kind is not BlockKind.EQUAL:
            for k in range(max(0, idx - context), min(len(rows), idx + context + 1)):
                keep[k] = True

    out: list[Row] = []
    pending_gap = False
    for idx, row in enumerate(rows):
        if keep[idx]:
            if pending_gap or (not out and idx > 0):
                out.append(_SEPARATOR_ROW)
            pending_gap = False
            out.append(row)
        elif out:
            pending_gap = True
    if pending_gap:
        out.append(_SEPARATOR_ROW)
    return out


def diff_run_starts(rows: list[Row]) -> list[int]:
    """Indices where a run of consecutive difference rows begins."""
    starts: list[int] = []
    in_run = False
    for idx, row in enumerate(rows):
        is_diff = row.kind in (BlockKind.REPLACE, BlockKind.DELETE, BlockKind.INSERT)
        if is_diff and not in_run:
            starts.append(idx)
        in_run = is_diff
    return starts
