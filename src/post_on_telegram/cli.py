# src/post_on_telegram/cli.py
"""Command-line interface for post-on-telegram.

Usage:
    post-on-telegram [--credentials FILE] [--parse-mode {plain,html,markdownv2}] [--no-preview] [--silent] [--chat-id ID] [--file PATH [--caption TEXT]] [--check] [--version] [MESSAGE | -]

    MESSAGE  - Message to send (positional argument)
    -        - Read message from standard input (stdin-style)
    --check  - Verify the token via getMe and print the bot username if available
    --version - Print the version and exit
    --parse-mode {plain,html,markdownv2} - Set message parsing mode (default: plain)
    --no-preview - Disable link previews (default: enabled)
    --silent - Suppress error messages (only exit codes)
    --chat-id ID - Override chat_id (numeric or @channelname)
    --file PATH [--caption TEXT] - Send a file (document) instead of a message
    --credentials FILE - Path to JSON credentials file

Exit codes:
    0 - Success
    1 - Send failed (error message printed to stderr)
    2 - Usage/configuration error (error message printed to stderr)
"""

import argparse
import sys
import os
import json
import logging
import subprocess

from .poster import Poster
from .errors import ConfigError, PostOnTelegramError

logger = logging.getLogger("post_on_telegram")


def _read_stdin() -> str:
    """Read message from stdin (utf-8)."""
    try:
        return sys.stdin.read()
    except Exception as exc:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send messages and documents to a Telegram chat via a bot",
        add_help=False,
    )
    parser.add_argument("message", nargs="?", default="-", help="Message to send (use '-' to read from stdin)")
    parser.add_argument("--credentials", type=str, help="Path to JSON credentials file")
    parser.add_argument("--parse-mode", choices=["plain", "html", "markdownv2"], default="plain", help="Message parsing mode")
    parser.add_argument("--no-preview", action="store_true", help="Disable link previews")
    parser.add_argument("--silent", action="store_true", help="Suppress error messages")
    parser.add_argument("--chat-id", type=str, help="Override chat_id (numeric or @channelname)")
    parser.add_argument("--file", type=str, help="Path to file to send as document")
    parser.add_argument("--caption", type=str, help="Caption for file (truncated to 1024 chars)")
    parser.add_argument("--check", action="store_true", help="Verify token via getMe")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------
    if args.version:
        from ._version import __version__
        print(f"post-on-telegram {__version__}")
        return 0

    # ------------------------------------------------------------------
    # Check mode
    # ------------------------------------------------------------------
    if args.check:
        try:
            poster = Poster(credentials_file=args.credentials)
            if poster.check():
                # Try to get bot username (not part of public API, but we can try)
                token = poster._token
                if token:
                    # Use getMe to get username
                    import requests

                    url = f"https://api.telegram.org/bot{token}/getMe"
                    try:
                        resp = requests.get(url, timeout=(5, 10))
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("ok", False):
                                username = data.get("username", "unknown")
                                print(f"Bot username: {username}")
                                return 0
            except Exception as exc:
                if not args.silent:
                    print(f"Error checking token: {exc}", file=sys.stderr)
                return 2
        return 0

    # ------------------------------------------------------------------
    # Prepare message
    # ------------------------------------------------------------------
    if args.message == "-":
        message = _read_stdin()
    else:
        message = args.message

    # ------------------------------------------------------------------
    # Prepare file (document)
    # ------------------------------------------------------------------
    if args.file:
        # Send document instead of message
        try:
            poster = Poster(credentials_file=args.credentials)
            if not poster.send_document(
                args.file,
                caption=args.caption,
                parse_mode=args.parse_mode,
                chat_id=args.chat_id,
            ):
                if not args.silent:
                    print("Failed to send document", file=sys.stderr)
                return 1
            return 0
        except Exception as exc:
            if not args.silent:
                print(f"Error sending document: {exc}", file=sys.stderr)
            return 1

    # ------------------------------------------------------------------
    # Send message
    # ------------------------------------------------------------------
    try:
        poster = Poster(credentials_file=args.credentials)
        if poster.send(
            message,
            parse_mode=args.parse_mode,
            disable_web_page_preview=not args.no_preview,
            chat_id=args.chat_id,
        ):
            return 0
        else:
            if not args.silent:
                print("Failed to send message", file=sys.stderr)
            return 1
    except ConfigError as exc:
        if not args.silent:
            print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except PostOnTelegramError as exc:
        if not args.silent:
            print(f"Telegram error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if not args.silent:
            print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())