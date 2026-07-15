---
name: qt-threading
description: How to run background work (scans, SFTP, diffs) in shankompare's Qt UI without crashes — worker objects, start_worker, signal rules. Use whenever adding or modifying any long-running operation triggered from the UI.
---

# Background work in the UI (Qt threading)

All long-running work (folder scans, SFTP transfers, file reads, diffs) runs on worker threads. The UI thread only creates workers, connects signals, and updates widgets.

## The pattern (copy an existing worker)

Workers live in `src/shankompare/ui/worker.py`. Each is a `QObject` with:

1. Constructor taking plain-data inputs (`SideSpec`, paths, options) — **never** widgets or live `FileSystem` objects.
2. A `run()` method that does the work and emits signals.
3. Signals for `progress`, results, `finished`, and `failed`.
4. A `threading.Event` named `cancel_event` if cancellable.

Start it with the existing helper — do not hand-roll QThread wiring:

```python
worker = MyWorker(...)
worker.finished.connect(self._on_done)      # bound method of a QObject!
worker.failed.connect(self._on_failed)
start_worker(worker, parent=self, done_signals=[worker.finished, worker.failed])
```

`start_worker` (in `worker.py`) handles moveToThread, keeping the Python wrapper alive (`thread._worker = worker`), quitting the thread on any done signal, and `deleteLater`. Every terminal signal must be listed in `done_signals` or the thread leaks.

## Hard rules

- **Never connect a worker signal to a lambda or `functools.partial`.** A lambda has no receiver QObject, so Qt runs it on the *worker* thread; touching widgets there crashes intermittently. Always connect to a bound method of a QObject living on the UI thread. Lambdas are fine only for UI-thread-to-UI-thread signals (e.g. button clicks).
- **Create `FileSystem` instances on the worker thread**, inside `run()`, via `open_side(spec)` — required by paramiko. Pass a `SideSpec` (`LocalSide` / `SftpSide` dataclasses) into the worker, not an open filesystem.
- `SftpFileSystem` is not thread-safe: one instance per worker thread, never shared.
- `run()` must never let an exception escape the thread. Wrap the body: catch `VfsError` → emit `failed(str(exc))`; catch bare `Exception` → `log.exception(...)` + emit a generic failure message. See `CompareWorker.run` for the template.
- Close filesystems in the worker (use `with open_side(...) as fs:`).
- Cancellation: the UI sets `worker.cancel_event`; the worker checks it between units of work and winds down cleanly (emit `finished(None)` or an errors list — see `CompareWorker` / `FileOpsWorker`).

## Size limits (enforce in workers, not UI)

`worker.py` defines `MAX_TEXT_COMPARE_BYTES` (32 MiB), `MAX_HEX_COMPARE_BYTES` (2 MiB); `vfs/archive.py` defines `MAX_ARCHIVE_BYTES`. Check sizes via `fs.stat()` before reading whole files, and emit `failed` with a message that includes the limit.
