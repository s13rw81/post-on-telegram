# src/post_on_telegram/chunking.py
"""Message chunking logic for Telegram's character limits."""

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
    if 0xD800 <= ord(left) <= 0xDBFF and 0xDC00 <= ord(right) <= 0xDFFF:
        return False
    # Never split a base character from its combining marks.
    if unicodedata.category(right).startswith("M"):
        return False
    return True


def _find_split_point(text: str, limit: int) -> int:
    """Find the best split point within *limit* characters.

    Prefers a blank line, then a newline, then a space, finally a hard cut.
    Never returns 0 unless limit <= 0 or text is empty.
    """
    if len(text) <= limit:
        return len(text)
    if limit <= 0:
        return 0

    search_end = min(limit, len(text))
    # 1. Search backwards for a blank line (two consecutive newlines).
    blank_line = text.rfind("\n\n", 0, search_end)
    if blank_line != -1:
        candidate = blank_line + 2
        if candidate <= limit and _is_safe_split_point(text, candidate):
            return candidate

    # 2. Search backwards for a single newline.
    newline = text.rfind("\n", 0, search_end)
    if newline != -1:
        candidate = newline + 1
        if candidate <= limit and _is_safe_split_point(text, candidate):
            return candidate

    # 3. Search backwards for a space.
    space = text.rfind(" ", 0, search_end)
    if space != -1:
        candidate = space + 1
        if candidate <= limit and _is_safe_split_point(text, candidate):
            return candidate

    # 4. Hard cut: move backwards until we find a safe split point.
    candidate = limit
    while candidate > 0 and not _is_safe_split_point(text, candidate):
        candidate -= 1
    if candidate == 0:
        # Last resort: split at limit
        candidate = limit
    return candidate


def _split_into_raw_slices(text: str, max_slice_len: int) -> list[str]:
    """Split *text* into raw slices each at most *max_slice_len* characters.

    Splits at natural boundaries (blank line, newline, space, or hard cut)
    without dropping any non-whitespace content.
    """
    if max_slice_len <= 0:
        raise ValueError("max_slice_len must be > 0")

    slices: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_slice_len:
            # Only add if it has non-whitespace content or it's the final remaining text
            if remaining.strip() or True:
                slices.append(remaining)
            break
        split_at = _find_split_point(remaining, max_slice_len)
        if split_at <= 0:
            split_at = max_slice_len
        piece = remaining[:split_at]
        # Drop whitespace-only intermediate slices
        if piece.strip():
            slices.append(piece)
        remaining = remaining[split_at:]
    return slices


def _calculate_prefix_len(n: int) -> int:
    """Calculate the length of the prefix "[i/n] " for a given chunk count n."""
    return len(f"[{n}/{n}] ")


def chunk_text(text: str, max_length: int) -> list[str]:
    """Split *text* into chunks of at most *max_length* characters.

    When more than one chunk is needed, each chunk is prefixed with "[i/n] "
    where the prefix is counted inside the *max_length* limit.

    Splitting prefers blank lines, then newlines, then spaces, and finally
    hard cuts. No empty chunks are produced and no text is lost.

    Args:
        text: The text to split.
        max_length: Maximum characters per chunk (must be > 0).

    Returns:
        A list of non-empty chunks.
    """
    if max_length <= 0:
        raise ValueError("max_length must be > 0")

    if not text:
        return []

    # If the text fits in one chunk without prefix, return it directly.
    if len(text) <= max_length:
        return [text]

    # Iteratively determine total chunk count n such that:
    # len(f"[{i}/{n}] " + slice_i) <= max_length for all i in 1..n
    n_guess = 2
    while True:
        # Calculate maximum prefix length across all 1..n_guess
        # e.g. for n_guess=10, prefixes range from "[1/10] " (len 7) to "[10/10] " (len 8)
        max_prefix_len = _calculate_prefix_len(n_guess)
        payload_limit = max_length - max_prefix_len
        if payload_limit <= 0:
            # max_length is too small for prefix + payload
            payload_limit = 1

        raw_slices = _split_into_raw_slices(text, payload_limit)
        actual_n = len(raw_slices)

        if actual_n <= n_guess:
            # We found a stable n!
            n = actual_n
            if n == 1:
                return [text]
            chunks: list[str] = []
            for i, piece in enumerate(raw_slices, start=1):
                # Use escaped prefix for MarkdownV2: \[i/n\]
                # The prefix length is counted inside the max_length limit
                prefix = f"[{i}/{n}] "
                chunks.append(prefix + piece)
            return chunks
        # Otherwise, need more chunks than guessed
        n_guess = max(actual_n, n_guess + 1)
