"""Diagnose SFTP clock-offset correction against a real server.

Run it with the project venv active:

    python scripts/diagnose_clock_offset.py --host HOST --user USER --root PATH

It connects the same way the app does, measures the clock offset, and then
lists the root showing each file's RAW server mtime next to the OFFSET-ADJUSTED
mtime the comparison actually uses. That makes it obvious whether (a) the probe
works, (b) the measured offset matches your real skew, and (c) the adjusted
times line up with your local copies.

By default it can load a saved profile by name (--profile NAME); otherwise pass
--host/--port/--user/--root and it will prompt for the password.
"""

import argparse
import getpass
import sys
import time
from datetime import UTC, datetime

from shankompare.sessions.profiles import ProfileStore
from shankompare.vfs import LocalFileSystem, SftpFileSystem, VfsError


def _local(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).astimezone().isoformat(timespec="seconds")


def _hms(dt) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S") if dt else "—"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", help="name of a saved connection profile")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--user")
    ap.add_argument("--root", default=".", help="remote folder to inspect")
    ap.add_argument("--local", help="local folder to line up against (same file names)")
    ap.add_argument("--limit", type=int, default=10, help="files to list (default 10)")
    args = ap.parse_args()

    if args.profile:
        store = ProfileStore()
        prof = next((p for p in store.load() if p.name == args.profile), None)
        if prof is None:
            print(
                f"No saved profile named {args.profile!r}. Saved: {[p.name for p in store.load()]}"
            )
            return 2
        secret = ProfileStore.get_secret(prof.name) or getpass.getpass("Secret: ")
        kwargs = prof.to_sftp_kwargs(secret)
        host, root = prof.host, kwargs["root"]
    else:
        if not args.host:
            ap.error("give --profile NAME, or --host (with --user/--root)")
        secret = getpass.getpass("Password: ")
        host, root = args.host, args.root
        kwargs = {"port": args.port, "username": args.user, "password": secret, "root": root}

    print(f"Connecting to {host} (root={root!r}) ...")
    print(f"Local time now:  {_local(time.time())}")

    # First WITHOUT measurement, to show raw server times.
    with SftpFileSystem(host, **kwargs, measure_clock_offset=False) as raw_fs:
        raw = {e.name: e for e in raw_fs.listdir(".")}

    # Then WITH measurement — this runs the probe and prints its log line
    # (logging is configured to INFO below).
    with SftpFileSystem(host, **kwargs, measure_clock_offset=True) as fs:
        print()
        if fs.clock_offset_known:
            print(
                f"PROBE OK. Measured offset: {fs.clock_offset.total_seconds():+.1f} s "
                "(positive = server clock ahead of local)"
            )
        else:
            print("PROBE FAILED or offset unknown — remote mtimes are NOT being adjusted.")
            print("Most likely the remote root is not writable. See the WARNING above.")
        print()

        adjusted = {e.name: e for e in fs.listdir(".") if not e.is_dir}
        offset_s = fs.clock_offset.total_seconds()

    local_entries: dict[str, object] = {}
    if args.local:
        with LocalFileSystem(args.local) as lfs:
            local_entries = {e.name: e for e in lfs.listdir(".") if not e.is_dir}

    print(
        f"{'name':<28} {'LOCAL mtime':<21} {'remote RAW':<21} {'remote ADJ (used)':<21} "
        f"{'ADJ−LOCAL':>10} {'RAW−LOCAL':>10}"
    )
    print("-" * 116)
    aligned_by_adj = aligned_by_raw = compared = shown = 0
    for name, entry in adjusted.items():
        raw_e = raw.get(name)
        loc_e = local_entries.get(name)
        adj_local = raw_local = ""
        if loc_e is not None:
            compared += 1
            d_adj = (entry.mtime - loc_e.mtime).total_seconds()
            d_raw = (raw_e.mtime - loc_e.mtime).total_seconds() if raw_e else float("nan")
            adj_local = f"{d_adj:+.0f}s"
            raw_local = f"{d_raw:+.0f}s"
            if abs(d_adj) <= 2:
                aligned_by_adj += 1
            if abs(d_raw) <= 2:
                aligned_by_raw += 1
        print(
            f"{name[:27]:<28} {_hms(getattr(loc_e, 'mtime', None)):<21} "
            f"{_hms(getattr(raw_e, 'mtime', None)):<21} {_hms(entry.mtime):<21} "
            f"{adj_local:>10} {raw_local:>10}"
        )
        shown += 1
        if shown >= args.limit:
            break
    if shown == 0:
        print("(no files in the remote root; point --root at a folder that has files)")

    if compared:
        print()
        print(f"Compared {compared} same-named file(s). Offset applied: {offset_s:+.0f}s.")
        print(f"  aligned after correction (|ADJ−LOCAL| ≤ 2s): {aligned_by_adj}/{compared}")
        print(
            f"  already aligned BEFORE correction (|RAW−LOCAL| ≤ 2s): {aligned_by_raw}/{compared}"
        )
        if aligned_by_raw > aligned_by_adj:
            print("  >>> Remote mtimes already matched local; the offset is making them differ.")
            print("  >>> This is case B — correction should be OFF for this pair.")
        elif aligned_by_adj > aligned_by_raw:
            print("  >>> Correction is doing its job (raw was skewed by the server clock).")
        else:
            print("  >>> Inconclusive — inspect the columns above.")
    elif args.local:
        print("\n(no file names matched between remote and --local; check the folders)")
    return 0


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        raise SystemExit(main())
    except VfsError as exc:
        print(f"\nConnection/VFS error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
