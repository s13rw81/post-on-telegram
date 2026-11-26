# src/post_on_telegram/formatting.py
"""Text formatting helpers for Telegram messages."""

from __future__ import annotations


def escape_html(text: str) -> str:
    """Escape HTML special characters: &, <, >.

    Args:
        text: The text to escape.

    Returns:
        The text with &, <, > escaped as HTML entities.
    """
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def escape_markdown_v2(text: str) -> str:
    """Escape all MarkdownV2 special characters.

    Characters escaped: _ * [ ] ( ) ~ ` > # + - = | { } . ! and backslash.

    Args:
        text: The text to escape.

    Returns:
        The text with MarkdownV2 special characters escaped.
    """
    chars_to_escape = r"_*[]()~`>#+-=|{}.!\\"
    escape_table = str.maketrans({c: f"\\{c}" for c in chars_to_escape})
    return text.translate(escape_table)


def format_pre(text: str) -> str:
    """Format text as a monospace code block (HTML <pre> tag).

    Intended for use with parse_mode="HTML".

    Args:
        text: The text to format.

    Returns:
        The text wrapped in <pre> tags with HTML-escaped content.
    """
    escaped = escape_html(text)
    return f"<pre>{escaped}</pre>"
