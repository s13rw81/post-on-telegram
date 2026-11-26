# Post on Telegram

[![CI](https://github.com/s13rw81/post-on-telegram/actions/workflows/ci.yml/badge.svg)](https://github.com/s13rw81/post-on-telegram/actions/workflows/ci.yml)
[![Python Versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Typing](https://img.shields.io/badge/typing-%3CTyped%3E-blue)](https://peps.python.org/pep-0487/)

**Post on Telegram** is a Python library that sends text messages (and documents) to a Telegram chat through a bot. It is designed to be called from long-running programs such as trading bots: it never crashes the caller and never leaks the bot token.

> **Disclaimer:** This is an unofficial project and is not affiliated with Telegram.

## Table of Contents

- [What is this?](#what-is-this)
- [Features](#features)
- [Installation](#installation)
- [Two-minute setup](#two-minute-setup)
- [Quick start](#quick-start)
- [Formatting](#formatting)
- [Long messages and rate limits](#long-messages-and-rate-limits)
- [Sending files](#sending-files)
- [CLI usage](#cli-usage)
- [Logging](#logging)
- [Using it inside long-running apps](#using-it-inside-long-running-apps)
- [Troubleshooting / FAQ](#troubleshooting--faq)
- [Security notes](#security-notes)
- [API reference](#api-reference)
- [Development](#development)
- [Contributing](#contributing)
- [Security policy](#security-policy)
- [License](#license)

## What is this?

Post on Telegram sends messages to Telegram chats via a bot. It is built for
people who run bots or notification services from Python — for example, a
trading bot that sends alerts, a scraper that posts updates, or a server that
sends system notifications.

It is designed to be safe to call from long-running programs:

- It **never raises** (unless `strict=True` is used for configuration errors).
- It **never crashes** the caller – all errors are caught, logged, and stored in
  `last_error`.
- It **never leaks** the bot token – all logs, error messages, and representations
  are redacted.

## Features

- ✅ Send text messages to any Telegram chat (private, group, channel).
- ✅ Send documents/files (up to 50 MB) with captions.
- ✅ Automatic long-message chunking (default max 4000 chars, safely below
  Telegram's 4096 limit).
- ✅ Multiple parse modes: plain text, HTML, MarkdownV2 (with automatic fallback
  to plain text on parse errors).
- ✅ Retry logic with exponential backoff and jitter; honours `retry_after` on
  rate limits; enforces an overall timeout.
- ✅ Thread-safe sending (lock prevents interleaved chunks).
- ✅ CLI (`post-on-telegram`) with `--check`, `--stdin`, `--file`, etc.
- ✅ Strict and non-strict configuration modes.
- ✅ Secure credential handling (file, env vars, explicit args).

## Installation

From PyPI (once published):

```bash
pip install post-on-telegram
```

From a Git tag:

```bash
pip install "git+https://github.com/s13rw81/post-on-telegram.git@v0.1.0"
```

From a wheel/sdist file:

```bash
pip install dist/post_on_telegram-0.1.0-py3-none-any.whl
```

For development:

```bash
git clone https://github.com/s13rw81/post-on-telegram.git
cd post-on-telegram
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Two-minute setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Start a chat with the bot (or add it to a group; for channels add it as an
   administrator).
3. Find the chat ID (use the `getUpdates` method via @BotFather or a small script).
4. Create a credentials JSON file (e.g. `~/.post-on-telegram-credentials.json`):

```json
{
  "bot_token": "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq",
  "chat_id": "-1001234567890"
}
```

5. Lock down file permissions (chmod 600 on Linux/macOS, icacls on Windows).
6. Verify with:

```bash
post-on-telegram --check
```

## Quick start

Basic send:

```python
from post_on_telegram import Poster

poster = Poster()
poster.send("Hello, world!")
```

Using env vars:

```python
import os

os.environ["POST_ON_TELEGRAM_TOKEN"] = "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq"
os.environ["POST_ON_TELEGRAM_CHAT_ID"] = "-1001234567890"

poster = Poster()
poster.send("Hello from env vars!")
```

Explicit token/chat_id:

```python
poster = Poster(
    token="123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq", chat_id="-1001234567890"
)
poster.send("Hello with explicit credentials!")
```

Check boolean result and last error:

```python
if poster.send("Hello!"):
    print("Sent!")
else:
    print(f"Failed: {poster.last_error}")
```

## Formatting

- Plain text (default): `poster.send("Hello!")`
- HTML: `poster.send("Hello <b>world</b>!", parse_mode="HTML")`
- MarkdownV2: `poster.send("**Hello** world!", parse_mode="MarkdownV2")`

Use `format_pre` for monospace blocks:

```python
from post_on_telegram import format_pre, escape_html

poster.send(format_pre("a | b\n--- | ---\n1 | 2"), parse_mode="HTML")
```

Automatic fallback: if Telegram returns a 400 parse error, the library retries
the chunk as plain text (HTML tags stripped for HTML mode).

## Long messages and rate limits

Messages longer than `max_message_length` (default 4000) are split into chunks.
Retries use exponential backoff with jitter; honour `retry_after` on 429. If the
required wait exceeds the remaining `total_timeout` budget, the request gives up
immediately without sleeping. Invalid `retry_after` values (NaN, negative,
non-numeric, or HTTP-date headers) are ignored and fall back to exponential
backoff.

## Sending files

```python
poster.send_document("/path/to/file.pdf", caption="Report")
```

## CLI usage

```bash
post-on-telegram "Hello from CLI!"
cat report.txt | post-on-telegram -
post-on-telegram --check
post-on-telegram --file report.pdf --caption "Report"
```

## Logging

```python
import logging

logging.basicConfig(level=logging.INFO)
```

## Using it inside long-running apps

```python
from post_on_telegram import Poster

poster = Poster()


def send_alert(message: str) -> None:
    if not poster.send(message):
        # log poster.last_error
        pass
```

## Troubleshooting / FAQ

- 401 Unauthorized: token invalid or revoked.
- 400 chat not found: chat_id wrong or bot not in chat.
- 403 bot was blocked/kicked: unblock the bot.
- "can't parse entities": automatic fallback to plain text handles this.

## Security notes

- Token is never logged or exposed in error messages.
- Credentials file should have chmod 600.

## API reference

See the docstrings in `post_on_telegram`.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest --cov=post_on_telegram
python -m build
python -m twine check dist/*
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security policy

See [SECURITY.md](SECURITY.md).

## License

MIT – see [LICENSE](LICENSE).