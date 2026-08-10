"""JSON persistence helpers shared by the profile, session and settings stores.

Two properties matter for these files, all of which load during application
startup:

- **Reads never raise.** A file truncated by a crash or hand-edited into
  invalid JSON must not stop the window from opening — there would be no UI
  left to fix it with. Unparseable content is moved aside rather than
  silently overwritten, so nothing is lost that a user could recover by hand.
- **Writes are atomic.** Content goes to a temp file in the same directory and
  is then renamed over the target, so an interrupted save leaves the previous
  version intact instead of a half-written one.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _set_aside(path: Path) -> None:
    """Rename an unreadable file to ``<name>.bad`` so the next save can't lose it."""
    try:
        os.replace(path, path.with_suffix(path.suffix + ".bad"))
    except OSError as exc:
        log.warning("could not set aside %s: %s", path, exc)


def read_json(path: Path, expected: type) -> Any | None:
    """Parse ``path``, expecting a JSON value of type ``expected``.

    Returns None — meaning "use defaults" — when the file is missing,
    unreadable, malformed, or holds the wrong kind of value.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("could not read %s (%s); starting from defaults", path, exc)
        _set_aside(path)
        return None
    if not isinstance(data, expected):
        log.warning(
            "%s holds a JSON %s, expected %s; starting from defaults",
            path,
            type(data).__name__,
            expected.__name__,
        )
        _set_aside(path)
        return None
    return data


def read_json_items(path: Path, parse: Any, kind: str) -> list:
    """Load a JSON list, dropping entries ``parse`` cannot make sense of.

    One malformed record (a hand-edited session, a field of the wrong type)
    costs only itself, not the rest of the file.
    """
    raw = read_json(path, list)
    if raw is None:
        return []
    items = []
    for entry in raw:
        try:
            items.append(parse(entry))
        except (AttributeError, TypeError, ValueError) as exc:
            log.warning("skipping unreadable %s entry in %s: %s", kind, path, exc)
    return items


def write_json(path: Path, payload: object) -> None:
    """Serialize ``payload`` to ``path``, creating parents, replacing atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
