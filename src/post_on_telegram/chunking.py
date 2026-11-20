# src/post_on_telegram/chunking.py
"""Message chunking logic for Telegram's 4096-character limit."""

from __future__ import annotations

import unicodedata


def _is_safe_split_point(text: str, index: int) -> bool:
    """Return True if splitting at *index* won't break a surrogate pair or
    separate a base character from its combining marks.

    *index* is the position where the left chunk ends (i.e. text[index-1]
    is the last character of the left chunk and text[index] is the first
    character of the right chunk).
    """
    if index <= 0 or index >= len(text):
        return True
    left = text[index - 1]
    right = text[index]
    # Never split inside a surrogate pair (high surrogate followed by low).
    if (
        0xD800 <= ord(left) <= 0xDBFF
        and 0xDC00 <= ord(right) <= 0xDFFF
    ):
        return False
    # Never split a base character from its combining marks.
    if unicodedata.category(right).startswith("M"):
        return False
    return True


def _find_split_point(text: str, limit: int) -> int:
    """Find the best split point within *limit* characters.

    Prefers a blank line, then a newline, then a space, finally a hard cut.
    Never returns 0 unless the text itself is empty.
    """
    if len(text) <= limit:
        return len(text)

    # Search backwards from limit for a blank line (two newlines).
    search_end = min(limit, len(text))
    blank_line = text.rfind("\n\n", 0, search_end)
    if blank_line != -1:
        # Split after the blank line (include both newlines in left chunk).
        candidate = blank_line + 2
        if candidate <= limit and _is_safe_split_point(text, candidate):
            return candidate

    # Search backwards for a single newline.
    newline = text.rfind("\n", 0, search_end)
    if newline != -1:
        candidate = newline + 1
        if candidate <= limit and _is_safe_split_point(text, candidate):
            return candidate

    # Search backwards for a space.
    space = text.rfind(" ", 0, search_end)
    if space != -1:
        candidate = space + 1
        if candidate <= limit and _is_safe_split_point(text, candidate):
            return candidate

    # Hard cut: move backwards until we find a safe split point.
    candidate = limit
    while candidate > 0 and not _is_safe_split_point(text, candidate):
        candidate -= 1
    if candidate == 0:
        # Force a split at limit even if it breaks a surrogate pair (last resort).
        candidate = limit
    return candidate


def chunk_text(text: str, max_length: int) -> list[str]:
    """Split *text* into chunks of at most *max_length* characters.

    Splitting prefers blank lines, then newlines, then spaces, and finally
    hard cuts. No empty chunks are produced and no text is lost (re-joining
    the chunks reproduces the original apart from whitespace trimmed at split
    points).

    Args:
        text: The text to split.
        max_length: Maximum characters per chunk (must be > 0).

    Returns:
        A list of non-empty chunks.
    """
    if max_length <= 0:
        raise ValueError("max_length must be > 0")

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        split_at = _find_split_point(remaining, max_length)
        if split_at <= 0:
            split_at = max_length

        chunk = remaining[:split_at]
        # Trim trailing whitespace at the split point so re-joining with a
        # single space reproduces the original (modulo whitespace).
        chunk = chunk.rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:]

    return chunks