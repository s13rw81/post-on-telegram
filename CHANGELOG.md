# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-20

### Added

- Initial release of Post on Telegram.
- `Poster` class with `send`, `send_document`, and `check` methods.
- Credential resolution from explicit args, credentials file, and environment variables.
- Support for plain text, HTML, and MarkdownV2 parse modes.
- Automatic long-message chunking (default max 4000 chars).
- Retry logic with exponential backoff and jitter.
- Thread-safe sending via internal lock.
- CLI (`post-on-telegram`) with `--check`, `--stdin`, `--file`, etc.
- Formatting helpers: `escape_html`, `escape_markdown_v2`, `format_pre`.
- Strict and non-strict configuration modes.
- Secure credential handling with token redaction in logs and error messages.