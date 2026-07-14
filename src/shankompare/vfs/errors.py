"""VFS exception hierarchy.

Backends translate their native errors (OSError, paramiko exceptions, ...)
into these types so upper layers never depend on a specific backend.
"""


class VfsError(Exception):
    """Base class for all VFS errors."""


class VfsAuthError(VfsError):
    """Authentication with the remote system failed."""


class VfsConnectionError(VfsError):
    """The connection could not be established or was lost."""


class VfsNotFound(VfsError):
    """The path does not exist."""


class VfsPermissionError(VfsError):
    """The operation is not permitted on this path."""
