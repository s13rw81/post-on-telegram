# src/post_on_telegram/__init__.py
"""
Post on Telegram - Send messages and documents to Telegram chats through a bot.

This is an unofficial library, not affiliated with Telegram.
"""

from __future__ import annotations

from ._version import __version__
from .errors import ConfigError, PostOnTelegramError
from .formatting import escape_html, escape_markdown_v2, format_pre
from .poster import Poster

__all__ = [
    "Poster",
    "PostOnTelegramError",
    "ConfigError",
    "escape_html",
    "escape_markdown_v2",
    "format_pre",
    "__version__",
]