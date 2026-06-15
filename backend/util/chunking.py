"""Markdown-aware text chunking for the shared vector memory.

Splits on Markdown headings first (so a `##` section stays together), then
falls back to paragraph and fixed-size windowing for very long blocks.
"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")


def chunk_text(text: str, max_chars: int = 700, overlap: int = 120) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    chunks: list[str] = []
    for block in _split_blocks(text):
        if len(block) <= max_chars:
            chunks.append(block)
        else:
            chunks.extend(_window(block, max_chars, overlap))
    return [c.strip() for c in chunks if c.strip()]


def _split_blocks(text: str) -> list[str]:
    """Group lines into heading-delimited blocks, then split long ones by paragraph."""
    lines = text.split("\n")
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if _HEADING_RE.match(line) and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))

    out: list[str] = []
    for block in blocks:
        if len(block) <= 1600:
            out.append(block)
        else:
            out.extend(p for p in re.split(r"\n\s*\n", block) if p.strip())
    return out


def _window(text: str, max_chars: int, overlap: int) -> list[str]:
    out: list[str] = []
    start = 0
    step = max(1, max_chars - overlap)
    while start < len(text):
        out.append(text[start:start + max_chars])
        if start + max_chars >= len(text):
            break
        start += step
    return out
