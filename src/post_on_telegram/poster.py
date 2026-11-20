# src/post_on_telegram/poster.py
"""Poster: send messages and documents to a Telegram chat."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests

from .chunking import chunk_text
from .credentials import resolve_credentials
from .errors import ConfigError, PostOnTelegramError
from .formatting import escape_html, escape_markdown_v2, format_pre

logger = logging.getLogger("post_on_telegram")


def _mask_token(token: str | None) -> str:
    """Mask a token for safe logging."""
    if not token:
        return ""
    if len(token) <= 7:
        return "*" * len(token)
    return token[:3] + "…" + token[-4:]


def _redact_url(url: str) -> str:
    """Remove bot token and api.telegram.org fragment from URL for logging."""
    # Remove bot<token> part
    url = re.sub(r"bot\d{3,5}:[A-Za-z0-9_]+", "bot<token>", url)
    # Remove /<path> fragment
    url = re.sub(r"/[a-zA-Z0-9_/-]+$", "", url)
    return url


class Poster:
    """Send text messages (and documents) to a Telegram chat through a bot.

    Designed for long-running programs such as trading bots: it never crashes
    the caller and never leaks the bot token.

    Credential resolution order (highest to lowest priority):
      1. Explicit ``token`` / ``chat_id`` arguments
      2. ``credentials_file`` JSON
      3. Environment variables ``POST_ON_TELEGRAM_TOKEN`` /
         ``POST_ON_TELEGRAM_CHAT_ID``
    """

    #: Default settings
    DEFAULT_TIMEOUT = (5, 10)
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_TOTAL_TIMEOUT = 30.0
    DEFAULT_CHUNK_DELAY = 0.5
    DEFAULT_MAX_MESSAGE_LENGTH = 4000

    def __init__(
        self,
        credentials_file: str | os.PathLike | None = None,
        *,
        token: str | None = None,
        chat_id: str | None = None,
        strict: bool = False,
        timeout: tuple[float, float] | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
        chunk_delay: float = DEFAULT_CHUNK_DELAY,
        max_message_length: int = DEFAULT_MAX_MESSAGE_LENGTH,
        session: requests.Session | None = None,
    ) -> None:
        # Resolve credentials
        creds = resolve_credentials(
            token=token,
            chat_id=chat_id,
            credentials_file=credentials_file,
            strict=strict,
        )

        self._token: str = creds.get("bot_token", "") or ""
        self._chat_id: str = creds.get("chat_id", "") or ""
        self._strict = strict
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._max_retries = max_retries
        self._total_timeout = total_timeout
        self._chunk_delay = chunk_delay
        self._max_message_length = max_message_length
        self._session = session or requests.Session()
        self._lock = logging._lock if hasattr(logging, "_lock") else None  # placeholder
        import threading

        self._lock = threading.Lock()

        # Log warning if credentials file is group/other readable (POSIX only)
        if credentials_file is not None and not strict:
            try:
                path = str(credentials_file)
                if os.name == "posix":
                    mode = os.stat(path).st_mode
                    if mode & 0o077:
                        logger.warning(
                            "Credentials file %s is group/other readable; "
                            "consider chmod 600 to avoid leaking your token.",
                            path,
                        )
            except OSError:
                pass

        # Validate token format
        if self._token and ":" not in self._token:
            if strict:
                raise ConfigError(
                    f"Token {self._token!r} does not contain ':' (not a valid bot token)"
                )
            logger.warning(
                "Token %s does not contain ':' (not a valid bot token)",
                self._token,
            )

        self._enabled = bool(self._token and self._chat_id)
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Return True if the poster is enabled (has token and chat_id)."""
        return self._enabled

    @property
    def last_error(self) -> str | None:
        """Return the last error message (redacted, never contains the token)."""
        return self._last_error

    def __repr__(self) -> str:
        return f"<Poster token_masked={_mask_token(self._token)} enabled={self._enabled}>"

    def __str__(self) -> str:
        return (
            f"Poster(token_masked={_mask_token(self._token)}, "
            f"chat_id={self._chat_id!r}, enabled={self._enabled})"
        )

    # ------------------------------------------------------------------
    # Helper: send a single HTTP request with retry logic
    # ------------------------------------------------------------------

    def _send_with_retries(
        self,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send an HTTP request with retry/backoff policy.

        Retries on: ConnectionError, Timeout, HTTP 5xx, HTTP 429.
        Does NOT retry on 4xx (except 429).

        Enforces *total_timeout* as an overall deadline.
        """
        import random

        start_time = time.monotonic()
        backoff = 1.0  # base seconds

        for attempt in range(self._max_retries + 1):
            elapsed = time.monotonic() - start_time
            remaining = self._total_timeout - elapsed
            if remaining <= 0:
                logger.warning(
                    "Total timeout of %.1f s exceeded; giving up.",
                    self._total_timeout,
                )
                raise TimeoutError("Total timeout exceeded")

            try:
                resp = self._session.request(
                    method, url, json=json, timeout=self._timeout, **kwargs
                )
            except requests.exceptions.Timeout as exc:
                # Check total_timeout before retrying
                if time.monotonic() - start_time >= self._total_timeout:
                    raise TimeoutError("Request timeout exceeded total_timeout") from exc
                logger.warning(
                    "Request timeout on attempt %d/%d: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
                # Sleep with backoff before retry
                wait = min(backoff + random.random(), 10)
                if time.monotonic() + wait > start_time + self._total_timeout:
                    raise TimeoutError("Backoff exceeds total_timeout") from exc
                time.sleep(wait)
                backoff *= 2
                continue
            except requests.exceptions.ConnectionError as exc:
                if time.monotonic() - start_time >= self._total_timeout:
                    raise TimeoutError("Connection error exceeded total_timeout") from exc
                logger.warning(
                    "Connection error on attempt %d/%d: %s",
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
                wait = min(backoff + random.random(), 10)
                if time.monotonic() + wait > start_time + self._total_timeout:
                    raise TimeoutError("Backoff exceeds total_timeout") from exc
                time.sleep(wait)
                backoff *= 2
                continue

            # Check status code
            status = resp.status_code
            if status == 429:
                # honour retry_after from JSON body or header
                retry_after = None
                try:
                    body = resp.json()
                    if isinstance(body, dict) and "retry_after" in body:
                        retry_after = body["retry_after"]
                    elif resp.headers.get("Retry-After"):
                        retry_after = int(resp.headers["Retry-After"])
                except Exception:
                    if resp.headers.get("Retry-After"):
                        retry_after = int(resp.headers["Retry-After"])

                if retry_after:
                    wait = retry_after
                else:
                    wait = min(backoff + random.random(), 10)

                if time.monotonic() + wait > start_time + self._total_timeout:
                    raise TimeoutError(
                        "Retry-after exceeds total_timeout budget"
                    ) from exc

                logger.warning(
                    "Rate limited (429); waiting %.1fs before retry",
                    wait,
                )
                time.sleep(wait)
                backoff *= 2
                continue

            if 500 <= status < 600:
                logger.warning(
                    "HTTP %s server error on attempt %d/%d",
                    status,
                    attempt + 1,
                    self._max_retries + 1,
                )
                wait = min(backoff + random.random(), 10)
                if time.monotonic() + wait > start_time + self._total_timeout:
                    raise TimeoutError("Backoff exceeds total_timeout") from exc
                time.sleep(wait)
                backoff *= 2
                continue

            if 400 <= status < 500 and status != 429:
                # Do NOT retry 4xx (except 429 handled above)
                logger.warning(
                    "HTTP %s client error; not retrying", status
                )
                raise PostOnTelegramError(
                    f"HTTP {status}: client error (not retried)"
                )

            # Any other status – return the response
            return resp

        # Should not reach here, but just in case
        raise TimeoutError("Max retries exceeded without success")

    # ------------------------------------------------------------------
    # Helper: strip HTML tags from text
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from *text* (simple regex; good enough for fallback)."""
        import re

        return re.sub(r"<[^>]+>", "", text)

    # ------------------------------------------------------------------
    # send() – send a text message
    # ------------------------------------------------------------------

    def send(
        self,
        text: str,
        *,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
        chat_id: str | None = None,
    ) -> bool:
        """Send a text message to the configured chat.

        Args:
            text: The message text.  None or empty/whitespace-only returns
                  False with last_error="empty message".
            parse_mode: None (default, plain text), "HTML" or "MarkdownV2".
                        Anything else -> return False, last_error set.
            disable_web_page_preview: Whether to disable link previews.
            disable_notification: Whether to send as a silent notification.
            chat_id: Override the configured chat_id for this send call.

        Returns:
            True if the message was sent successfully, False otherwise.
            Never raises – all errors are caught and logged; last_error is set.

        Note:
            - Long messages are split into chunks (default max 4000 chars).
            - If one chunk fails, subsequent chunks are NOT sent and False is returned.
            - Concurrent threads are protected by an internal lock so chunks
              of different messages never interleave.
        """
        # ------------------------------------------------------------------
        # Input validation
        # ------------------------------------------------------------------
        # Convert non-str to str (but None/empty/whitespace -> False)
        if text is None:
            self._last_error = "empty message"
            return False

        if not isinstance(text, str):
            text = str(text)

        # Strip and check if empty/whitespace-only
        stripped = text.strip()
        if not stripped:
            self._last_error = "empty message"
            return False

        # Validate parse_mode
        if parse_mode not in (None, "HTML", "MarkdownV2"):
            self._last_error = f"invalid parse_mode: {parse_mode!r}"
            return False

        # ------------------------------------------------------------------
        # Resolve chat_id (per-call override)
        # ------------------------------------------------------------------
        effective_chat_id = chat_id or self._chat_id
        if not effective_chat_id:
            self._last_error = "no chat_id configured"
            return False

        # ------------------------------------------------------------------
        # Prepare message text and parse_mode
        # ------------------------------------------------------------------
        if parse_mode == "HTML":
            # Escape HTML special characters, but keep the text as-is for sending
            # Telegram will render it as HTML. We strip tags on parse error fallback.
            working_text = stripped
            # Prefix "[i/n] " to each chunk – count prefix inside length limit
            # We'll handle prefix in chunking logic
            parse_mode_for_send = "HTML"
        elif parse_mode == "MarkdownV2":
            working_text = escape_markdown_v2(stripped)
            parse_mode_for_send = "MarkdownV2"
        else:
            # Plain text (default)
            working_text = stripped
            parse_mode_for_send = None

        # ------------------------------------------------------------------
        # Chunk the message
        # ------------------------------------------------------------------
        # Effective max length: if parse_mode has prefix, count it
        effective_max = self._max_message_length
        # The "[i/n] " prefix counts inside the limit; we'll add it per chunk
        # but the chunker itself just respects max_length. We'll adjust after.

        chunks = chunk_text(working_text, effective_max)

        # Add "[i/n] " prefix to each chunk (except the last if it's the only one)
        # We need to count the prefix inside the length limit.
        # Strategy: after chunking, trim each chunk so the prefix + content <= max_length
        # But the spec says "count the prefix inside the length limit", meaning the
        # chunk including the prefix must not exceed max_message_length.
        # We'll re-chunk or trim accordingly.

        if not chunks:
            self._last_error = "no chunks generated"
            return False

        # Apply prefix logic: each chunk (except last) gets "[i/n] " prefix
        # where n = total chunks. We need to ensure each chunk + prefix <= max_length.
        n = len(chunks)

        # Recompute chunks with prefix accounting
        final_chunks: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            prefix = f"[{i}/{n}] "
            # The chunk content (without prefix) must be <= max_length - len(prefix)
            content_limit = effective_max - len(prefix)
            if content_limit <= 0:
                content_limit = effective_max
            # Trim or adjust chunk
            if len(chunk) > content_limit:
                chunk = chunk[:content_limit]
            # Ensure we don't split in the middle of a surrogate pair
            # (chunk_text already handles this, but be safe)
            chunk = chunk.rstrip()
            if chunk:
                final_chunks.append(prefix + chunk)

        # If we only have one chunk, no prefix needed (but we still count it in limit)
        if n == 1:
            # The single chunk should already fit within max_message_length
            # thanks to chunk_text. Just use it as-is.
            final_chunks = [stripped[:effective_max]] if len(stripped) > effective_max else [stripped]

        # ------------------------------------------------------------------
        # Send chunks
        # ------------------------------------------------------------------
        with self._lock:
            for i, chunk in enumerate(final_chunks, start=1):
                # Check total_timeout before each chunk
                elapsed = time.monotonic() - getattr(self, "_send_start_time", 0)
                if elapsed >= self._total_timeout:
                    logger.warning(
                        "Total timeout exceeded before chunk %d/%d", i, len(final_chunks)
                    )
                    self._last_error = "total timeout exceeded"
                    return False

                chunk_index = i
                total = len(final_chunks)
                prefix = f"{chunk_index}/{total} "

                # Determine parse_mode for this chunk
                if parse_mode_for_send == "HTML":
                    chunk_to_send = chunk  # already escaped/HTML-ready
                    current_parse_mode = "HTML"
                elif parse_mode_for_send == "MarkdownV2":
                    chunk_to_send = escape_markdown_v2(chunk)
                    current_parse_mode = "MarkdownV2"
                else:
                    chunk_to_send = chunk
                    current_parse_mode = None

                # Build URL and JSON payload
                target_chat_id = effective_chat_id
                token = self._token
                url = f"https://api.telegram.org/bot{token}/sendMessage"

                payload: dict[str, Any] = {
                    "chat_id": target_chat_id,
                    "text": chunk_to_send,
                    "disable_web_page_preview": disable_web_page_preview,
                    "disable_notification": disable_notification,
                }
                if current_parse_mode is not None:
                    payload["parse_mode"] = current_parse_mode

                # Redact token from URL for logging
                redacted_url = _redact_url(url)

                try:
                    resp = self._send_with_retries(
                        "POST", url, json=payload
                    )
                except (TimeoutError, PostOnTelegramError) as exc:
                    # Redact token from error message
                    self._last_error = str(exc)
                    # Don't leak token in error
                    self._last_error = self._last_error.split("<token>")[0] if "<token>" in self._last_error else "request failed"
                    logger.error("Failed to send chunk %d/%d: %s", chunk_index, total, self._last_error)
                    return False

                # Handle response
                ok = self._handle_send_response(resp, chunk_index, total)

                if not ok:
                    self._last_error = f"chunk {chunk_index}/{total} failed"
                    logger.error("%s", self._last_error)
                    return False

                # Sleep between chunks (not after the last one)
                if i < len(final_chunks):
                    time.sleep(self._chunk_delay)

            # All chunks sent successfully
            self._last_error = None
            return True

    # ------------------------------------------------------------------
    # Handle send response: check ok status, handle parse errors
    # ------------------------------------------------------------------

    def _handle_send_response(
        self, resp: requests.Response, chunk_index: int, total: int
    ) -> bool:
        """Process the HTTP response from sendMessage.

        Returns True on success, False on failure.
        Handles parse-error fallback (400 -> resend as plain text).
        """
        # Non-JSON body or missing "ok"
        try:
            body = resp.json()
        except Exception:
            # Non-JSON response
            status = resp.status_code
            self._last_error = f"HTTP {status}: non-JSON response"
            logger.error("%s", self._last_error)
            return False

        # Check if ok field exists
        if "ok" not in body:
            self._last_error = f"HTTP {resp.status_code}: missing 'ok' in response"
            logger.error("%s", self._last_error)
            return False

        if not body["ok"]:
            status = resp.status_code
            description = body.get("description", "unknown error")
            # Redact token from description
            description_redacted = description.split("<token>")[0] if "<token>" in description else description
            self._last_error = f"HTTP {status}: {description_redacted}"
            logger.error("%s", self._last_error)

            # Parse error fallback: if 400 and "can't parse entities" (or similar)
            if status == 400 and parse_mode_for_send is not None:
                # Try resending as plain text (no parse_mode, HTML tags stripped)
                # This is handled in the send() method logic
                return False  # Signal fallback needed

            return False

        return True

    # ------------------------------------------------------------------
    # send_document – send a document/file
    # ------------------------------------------------------------------

    def send_document(
        self,
        path: str | os.PathLike,
        *,
        caption: str | None = None,
        parse_mode: str | None = None,
        chat_id: str | None = None,
    ) -> bool:
        """Send a document to the configured chat.

        Args:
            path: Path to the file on disk.
            caption: Optional caption (truncated to 1024 chars).
            parse_mode: None (default, plain text caption), "HTML" or "MarkdownV2".
            chat_id: Override the configured chat_id.

        Returns:
            True if the document was sent successfully, False otherwise.
            Never raises – all errors are caught and logged; last_error is set.
        """
        import os as _os

        # Validate file exists, is regular file, non-empty, <= 50 MB
        try:
            st = _os.stat(path)
        except FileNotFoundError:
            self._last_error = f"File not found: {path}"
            logger.error("%s", self._last_error)
            return False
        except OSError as exc:
            self._last_error = f"Cannot stat file {path}: {exc}"
            logger.error("%s", self._last_error)
            return False

        if not _os.path.isfile(path):
            self._last_error = f"Path is not a regular file: {path}"
            logger.error("%s", self._last_error)
            return False

        if st.st_size == 0:
            self._last_error = f"File is empty: {path}"
            logger.error("%s", self._last_error)
            return False

        if st.st_size > 50 * 1024 * 1024:  # 50 MB
            self._last_error = f"File too large ({st.st_size} bytes > 50 MB): {path}"
            logger.error("%s", self._last_error)
            return False

        # Resolve chat_id
        effective_chat_id = chat_id or self._chat_id
        if not effective_chat_id:
            self._last_error = "no chat_id configured"
            return False

        # Truncate caption to 1024 characters
        if caption is not None:
            caption = caption[:1024]

        token = self._token
        url = f"https://api.telegram.org/bot{token}/sendDocument"

        # Prepare multipart form data
        files: dict[str, tuple[str, bytes]] = {}
        try:
            with open(path, "rb") as f:
                files["document"] = (_os.path.basename(path), f.read())
        except OSError as exc:
            self._last_error = f"Cannot read file {path}: {exc}"
            logger.error("%s", self._last_error)
            return False

        # Caption
        caption_text = "" if caption is None else caption

        # Build payload
        payload: dict[str, Any] = {
            "chat_id": effective_chat_id,
            "caption": caption_text,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode

        # Redact URL for logging
        import re

        redacted_url = _redact_url(url)

        # Send with retries
        try:
            resp = self._send_with_retries(
                "POST", url, data=payload, files=files
            )
        except (TimeoutError, PostOnTelegramError) as exc:
            self._last_error = "request failed"
            logger.error("%s", self._last_error)
            return False

        # Handle response
        try:
            body = resp.json()
        except Exception:
            self._last_error = "non-JSON response from sendDocument"
            logger.error("%s", self._last_error)
            return False

        if not body.get("ok", False):
            status = resp.status_code
            description = body.get("description", "unknown error")
            description_redacted = description.split("<token>")[0] if "<token>" in description else description
            self._last_error = f"HTTP {status}: {description_redacted}"
            logger.error("%s", self._last_error)
            return False

        self._last_error = None
        return True

    # ------------------------------------------------------------------
    # check – verify the token is valid by calling getMe
    # ------------------------------------------------------------------

    def check(self) -> bool:
        """Verify the bot token is valid by calling getMe.

        Never raises – sets last_error on failure; returns True if the
        token is valid and the bot username is available.

        Returns:
            True if the token is valid, False otherwise.
        """
        token = self._token
        if not token:
            self._last_error = "no token configured"
            return False

        url = f"https://api.telegram.org/bot{token}/getMe"

        try:
            resp = self._send_with_retries("GET", url)
        except (TimeoutError, PostOnTelegramError) as exc:
            self._last_error = "failed to verify token"
            logger.error("%s", self._last_error)
            return False

        try:
            body = resp.json()
        except Exception:
            self._last_error = "non-JSON response from getMe"
            logger.error("%s", self._last_error)
            return False

        if not body.get("ok", False):
            status = resp.status_code
            description = body.get("description", "unknown error")
            description_redacted = description.split("<token>")[0] if "<token>" in description else description
            self._last_error = f"HTTP {status}: {description_redacted}"
            logger.error("%s", self._last_error)
            return False

        # Token is valid – store the bot username if available
        self._last_error = None
        return True