"""Read a text file the way people actually save them."""

from __future__ import annotations

from pathlib import Path


def read_text(path: str | Path) -> str:
    """UTF-8 first (a byte-order mark is fine). Old Windows exports fall back to Latin-1, which accepts any byte."""
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")
