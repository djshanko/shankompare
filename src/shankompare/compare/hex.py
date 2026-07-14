"""Hex comparison engine: byte-aligned rows for a side-by-side hex view.

Comparison is offset-aligned (no insertion detection) — the standard model
for binary diffs. Pure Python; the UI renders the rows.
"""

from dataclasses import dataclass

HEX_WIDTH = 16  # bytes per row

# line layout: "oooooooo  xx xx … xx  |aaaa…|"
_OFFSET_CHARS = 8
_HEX_START = _OFFSET_CHARS + 2
_ASCII_START = _HEX_START + HEX_WIDTH * 3 - 1 + 3  # hex block, two spaces, "|"


@dataclass(frozen=True)
class HexRow:
    offset: int
    left: bytes  # up to HEX_WIDTH bytes; shorter/empty past EOF
    right: bytes
    diff_bytes: tuple[int, ...]  # in-row byte indexes that differ (incl. length overhang)

    @property
    def is_diff(self) -> bool:
        return bool(self.diff_bytes)


def hex_rows(left: bytes, right: bytes) -> list[HexRow]:
    rows: list[HexRow] = []
    length = max(len(left), len(right))
    for offset in range(0, length, HEX_WIDTH):
        left_chunk = left[offset : offset + HEX_WIDTH]
        right_chunk = right[offset : offset + HEX_WIDTH]
        span = max(len(left_chunk), len(right_chunk))
        diffs = tuple(
            i
            for i in range(span)
            if i >= len(left_chunk) or i >= len(right_chunk) or left_chunk[i] != right_chunk[i]
        )
        rows.append(HexRow(offset, left_chunk, right_chunk, diffs))
    return rows


def format_hex_line(offset: int, data: bytes) -> str:
    hex_part = " ".join(f"{b:02x}" for b in data).ljust(HEX_WIDTH * 3 - 1)
    ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in data).ljust(HEX_WIDTH)
    return f"{offset:08x}  {hex_part}  |{ascii_part}|"


def hex_char_span(byte_index: int) -> tuple[int, int]:
    """Character range of one byte's two hex digits within a formatted line."""
    start = _HEX_START + byte_index * 3
    return start, start + 2


def ascii_char_span(byte_index: int) -> tuple[int, int]:
    """Character range of one byte's ASCII cell within a formatted line."""
    start = _ASCII_START + byte_index
    return start, start + 1


def count_differing_bytes(rows: list[HexRow]) -> int:
    return sum(len(row.diff_bytes) for row in rows)
