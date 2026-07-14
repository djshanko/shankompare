"""Synchronization planning: turn a comparison result into file operations.

Pure logic (no Qt, no I/O): walks the ``NodeResult`` tree that a completed
comparison produced and emits the ``FileOp`` batch that would bring the two
sides in sync. The UI shows the plan for confirmation, then feeds it to the
existing background operations queue.
"""

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from shankompare.vfs.ops import FileOp, OpKind

from .folder import NodeResult, Status

# mtime deltas at or below this are too close to call for "update both"
_UPDATE_TOLERANCE_SECONDS = 2.0


@dataclass(frozen=True)
class SyncPlan:
    ops: list[FileOp] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        counts: dict[OpKind, int] = {}
        for op in self.ops:
            counts[op.kind] = counts.get(op.kind, 0) + 1
        labels = {
            OpKind.COPY_LTR: "copy to right",
            OpKind.COPY_RTL: "copy to left",
            OpKind.DELETE_LEFT: "delete on left",
            OpKind.DELETE_RIGHT: "delete on right",
        }
        parts = [f"{count} × {labels[kind]}" for kind, count in counts.items()]
        return ", ".join(parts) if parts else "nothing to do"


def plan_mirror(root: NodeResult, direction: str) -> SyncPlan:
    """Make the target side an exact copy of the source side.

    ``direction`` is ``"ltr"`` (right becomes a copy of left) or ``"rtl"``.
    """
    if direction not in ("ltr", "rtl"):
        raise ValueError(f"direction must be 'ltr' or 'rtl', not {direction!r}")
    ltr = direction == "ltr"
    copy_kind = OpKind.COPY_LTR if ltr else OpKind.COPY_RTL
    delete_kind = OpKind.DELETE_RIGHT if ltr else OpKind.DELETE_LEFT
    source_only = Status.LEFT_ONLY if ltr else Status.RIGHT_ONLY
    target_only = Status.RIGHT_ONLY if ltr else Status.LEFT_ONLY

    ops: list[FileOp] = []
    warnings: list[str] = []

    def walk(node: NodeResult, path: PurePosixPath) -> None:
        for child in node.children:
            child_path = str(path / child.name)
            if child.status is Status.SAME:
                continue
            if child.status is source_only:
                ops.append(FileOp(copy_kind, child_path))  # dirs copy recursively
            elif child.status is target_only:
                ops.append(FileOp(delete_kind, child_path))
            elif child.status is Status.DIFFERENT:
                if child.error is not None:
                    warnings.append(f"skipped (needs attention): {child_path} — {child.error}")
                elif child.is_dir:
                    walk(child, path / child.name)
                else:
                    ops.append(FileOp(copy_kind, child_path))
            else:  # UNKNOWN
                warnings.append(f"skipped (not compared): {child_path}")

    walk(root, PurePosixPath("."))
    return SyncPlan(ops, warnings)


def plan_update_both(root: NodeResult) -> SyncPlan:
    """Copy everything missing to the other side; for changed file pairs,
    the newer file wins. Pairs whose mtimes are too close to call are
    skipped with a warning rather than guessed at."""
    ops: list[FileOp] = []
    warnings: list[str] = []

    def walk(node: NodeResult, path: PurePosixPath) -> None:
        for child in node.children:
            child_path = str(path / child.name)
            if child.status is Status.SAME:
                continue
            if child.status is Status.LEFT_ONLY:
                ops.append(FileOp(OpKind.COPY_LTR, child_path))
            elif child.status is Status.RIGHT_ONLY:
                ops.append(FileOp(OpKind.COPY_RTL, child_path))
            elif child.status is Status.DIFFERENT:
                if child.error is not None:
                    warnings.append(f"skipped (needs attention): {child_path} — {child.error}")
                elif child.is_dir:
                    walk(child, path / child.name)
                else:
                    delta = (child.left.mtime - child.right.mtime).total_seconds()
                    if delta > _UPDATE_TOLERANCE_SECONDS:
                        ops.append(FileOp(OpKind.COPY_LTR, child_path))
                    elif delta < -_UPDATE_TOLERANCE_SECONDS:
                        ops.append(FileOp(OpKind.COPY_RTL, child_path))
                    else:
                        warnings.append(
                            f"skipped (same modification time but different): {child_path}"
                        )
            else:  # UNKNOWN
                warnings.append(f"skipped (not compared): {child_path}")

    walk(root, PurePosixPath("."))
    return SyncPlan(ops, warnings)
