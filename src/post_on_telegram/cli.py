# src/post_on_telegram/cli.py
"""Command-line interface for post-on-telegram."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ._version import __version__
from .poster import Poster, redact


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="post-on-telegram",
        description="Send messages and documents to Telegram chats via a bot.",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default=None,
        help="Message text to send, or '-' for stdin",
    )
    parser.add_argument("--credentials", metavar="FILE", help="Path to credentials JSON file")
    parser.add_argument(
        "--parse-mode",
        choices=["plain", "html", "markdownv2"],
        default="plain",
        help="Message parse mode (plain, html, or markdownv2)",
    )
    parser.add_argument("--no-preview", action="store_true", help="Disable web page preview")
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Send silently (disable notification)",
    )
    parser.add_argument("--chat-id", metavar="ID", help="Override chat ID")
    parser.add_argument("--file", metavar="PATH", help="Path of document to send")
    parser.add_argument("--caption", metavar="TEXT", help="Caption for document")
    parser.add_argument("--check", action="store_true", help="Verify credentials and bot identity")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI main function.

    Exit codes:
        0 - Success
        1 - Send or Telegram failure
        2 - Usage or configuration error
    """
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # Reject --token explicitly (security rule: tokens must not appear in process lists/argv)
    for arg in raw_args:
        if arg == "--token" or arg.startswith("--token="):
            sys.stderr.write(
                "Error: --token is not supported for security reasons. "
                "Use a credentials file or POST_ON_TELEGRAM_TOKEN env var.\n"
            )
            return 2

    try:
        args = _parse_args(raw_args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    # Map CLI parse-mode string to library parse_mode
    mode_map = {
        "plain": None,
        "html": "HTML",
        "markdownv2": "MarkdownV2",
    }
    lib_parse_mode = mode_map.get(args.parse_mode.lower()) if args.parse_mode else None

    poster = Poster(credentials_file=args.credentials, chat_id=args.chat_id)

    # Handle --check
    if args.check:
        if not poster.enabled:
            err = poster.last_error or "Missing credentials (token or chat_id)"
            sys.stderr.write(f"Check failed: {redact(err)}\n")
            return 2

        # Check bot validity via getMe
        if not poster.check():
            err = poster.last_error or "Check failed"
            sys.stderr.write(f"Check failed: {redact(err)}\n")
            return 1

        # Fetch username if possible
        username = "valid bot"
        try:
            url = f"https://api.telegram.org/bot{poster._token}/getMe"
            resp = poster._session.get(url, timeout=(5, 10))
            data = resp.json()
            if isinstance(data, dict) and data.get("ok"):
                res = data.get("result", {})
                if isinstance(res, dict) and "username" in res:
                    username = f"@{res['username']}"
        except Exception:
            pass

        sys.stdout.write(f"Bot verified successfully: {username}\n")
        return 0

    # Ensure poster is configured
    if not poster.enabled:
        err = poster.last_error or "No bot token or chat ID configured"
        sys.stderr.write(f"Configuration error: {redact(err)}\n")
        return 2

    # Handle --file document upload
    if args.file:
        ok = poster.send_document(
            args.file,
            caption=args.caption,
            parse_mode=lib_parse_mode,
            chat_id=args.chat_id,
        )
        if not ok:
            err = poster.last_error or "Failed to send document"
            sys.stderr.write(f"Error: {redact(err)}\n")
            return 1
        return 0

    # Read message
    message_text = args.message
    if message_text == "-":
        try:
            message_text = sys.stdin.read()
        except Exception as exc:
            sys.stderr.write(f"Error reading stdin: {exc}\n")
            return 2

    if message_text is None:
        sys.stderr.write("Error: MESSAGE or --file or --check required\n")
        return 2

    ok = poster.send(
        message_text,
        parse_mode=lib_parse_mode,
        disable_web_page_preview=args.no_preview,
        disable_notification=args.silent,
        chat_id=args.chat_id,
    )
    if not ok:
        err = poster.last_error or "Failed to send message"
        sys.stderr.write(f"Error: {redact(err)}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
