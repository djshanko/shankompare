"""Comparison engines: folder tree compare and text diff."""

from .folder import (
    CompareCancelled,
    CompareDone,
    CompareEvent,
    CompareOptions,
    ContentChecked,
    ContentMode,
    DirScanned,
    NodeResult,
    Status,
    compare_folders,
)
from .text import (
    BlockKind,
    DecodedText,
    DiffBlock,
    Row,
    TextDiffOptions,
    compute_rows,
    condense_rows,
    decode_bytes,
    diff_lines,
    diff_run_starts,
)

__all__ = [
    "BlockKind",
    "CompareCancelled",
    "CompareDone",
    "CompareEvent",
    "CompareOptions",
    "ContentChecked",
    "ContentMode",
    "DecodedText",
    "DiffBlock",
    "DirScanned",
    "NodeResult",
    "Row",
    "Status",
    "TextDiffOptions",
    "compare_folders",
    "compute_rows",
    "condense_rows",
    "decode_bytes",
    "diff_lines",
    "diff_run_starts",
]
