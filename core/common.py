"""Shared, stateless helpers used across platform services.

These are pure mechanics with no business rules. Each exists once here so that
individual services do not re-implement the same small utility in several files.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Set


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def get_attr(obj: Any, *names: str, default: Any = None) -> Any:
    """Return the first present attribute among ``names``, else ``default``."""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def as_set(value: Any) -> Set[Any]:
    """Coerce a value into a set, tolerating None and common iterables."""
    if value is None:
        return set()
    if isinstance(value, (set, frozenset)):
        return set(value)
    if isinstance(value, (list, tuple)):
        return set(value)
    return {value}


class ConfigurationError(ValueError):
    """Raised when a required service dependency is missing or invalid."""