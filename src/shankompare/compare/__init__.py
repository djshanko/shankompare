"""Comparison engines (folder tree compare; text diff arrives in M2)."""

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

__all__ = [
    "CompareCancelled",
    "CompareDone",
    "CompareEvent",
    "CompareOptions",
    "ContentChecked",
    "ContentMode",
    "DirScanned",
    "NodeResult",
    "Status",
    "compare_folders",
]
