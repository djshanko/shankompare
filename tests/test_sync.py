from datetime import UTC, datetime

import pytest
from test_folder_compare import make_fs, run_compare

from shankompare.compare import plan_mirror, plan_update_both
from shankompare.vfs.ops import FileOp, OpKind


def _ops(plan) -> set[tuple[OpKind, str]]:
    return {(op.kind, op.path) for op in plan.ops}


@pytest.fixture
def tree_pair():
    left = make_fs(
        {
            "same.txt": b"same",
            "changed.txt": b"left version",
            "only-left.txt": b"L",
            "only-left-dir": {"inner.txt": b"i"},
            "shared": {"nested-changed.txt": b"left"},
        }
    )
    right = make_fs(
        {
            "same.txt": b"same",
            "changed.txt": b"right version!",
            "only-right.txt": b"R",
            "shared": {"nested-changed.txt": b"RIGHT"},
        }
    )
    return left, right


def test_mirror_ltr(tree_pair):
    root = run_compare(*tree_pair)
    plan = plan_mirror(root, "ltr")
    assert _ops(plan) == {
        (OpKind.COPY_LTR, "changed.txt"),
        (OpKind.COPY_LTR, "only-left.txt"),
        (OpKind.COPY_LTR, "only-left-dir"),
        (OpKind.DELETE_RIGHT, "only-right.txt"),
        (OpKind.COPY_LTR, "shared/nested-changed.txt"),
    }
    assert plan.warnings == []


def test_mirror_rtl(tree_pair):
    root = run_compare(*tree_pair)
    plan = plan_mirror(root, "rtl")
    assert _ops(plan) == {
        (OpKind.COPY_RTL, "changed.txt"),
        (OpKind.DELETE_LEFT, "only-left.txt"),
        (OpKind.DELETE_LEFT, "only-left-dir"),
        (OpKind.COPY_RTL, "only-right.txt"),
        (OpKind.COPY_RTL, "shared/nested-changed.txt"),
    }


def test_mirror_identical_trees_is_empty():
    left = make_fs({"a.txt": b"x", "d": {"b.txt": b"y"}})
    right = make_fs({"a.txt": b"x", "d": {"b.txt": b"y"}})
    plan = plan_mirror(run_compare(left, right), "ltr")
    assert plan.ops == []
    assert plan.summary() == "nothing to do"


def test_mirror_rejects_bad_direction(tree_pair):
    root = run_compare(*tree_pair)
    with pytest.raises(ValueError):
        plan_mirror(root, "sideways")


def test_update_both_copies_missing_and_newer(tree_pair):
    left, right = tree_pair
    left.set_mtime("changed.txt", datetime(2026, 1, 2, tzinfo=UTC))  # left is newer
    right.set_mtime("shared/nested-changed.txt", datetime(2026, 1, 2, tzinfo=UTC))  # right newer
    root = run_compare(left, right)
    plan = plan_update_both(root)
    assert _ops(plan) == {
        (OpKind.COPY_LTR, "changed.txt"),
        (OpKind.COPY_LTR, "only-left.txt"),
        (OpKind.COPY_LTR, "only-left-dir"),
        (OpKind.COPY_RTL, "only-right.txt"),
        (OpKind.COPY_RTL, "shared/nested-changed.txt"),
    }
    assert plan.warnings == []


def test_update_both_skips_ambiguous_mtime(tree_pair):
    # tree_pair stamps everything with the same mtime -> changed files are ambiguous
    root = run_compare(*tree_pair)
    plan = plan_update_both(root)
    assert (OpKind.COPY_LTR, "changed.txt") not in _ops(plan)
    assert any("changed.txt" in w for w in plan.warnings)


def test_type_mismatch_is_skipped_with_warning():
    left = make_fs({"thing": {"inner.txt": b"x"}})
    right = make_fs({"thing": b"a file"})
    plan = plan_mirror(run_compare(left, right), "ltr")
    assert plan.ops == []
    assert any("thing" in w for w in plan.warnings)


def test_summary_counts():
    plan_ops = [
        FileOp(OpKind.COPY_LTR, "a"),
        FileOp(OpKind.COPY_LTR, "b"),
        FileOp(OpKind.DELETE_RIGHT, "c"),
    ]
    from shankompare.compare import SyncPlan

    summary = SyncPlan(plan_ops, []).summary()
    assert "2 × copy to right" in summary
    assert "1 × delete on right" in summary
