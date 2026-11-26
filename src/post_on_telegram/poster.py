# src/post_on_telegram/poster.py
"""Poster: send messages and documents to a Telegram chat."""

from __future__ import annotations

import html
import logging
import os
import re
import threading
import time
from typing import Any

import requests

from .chunking import chunk_text
from .credentials import resolve_credentials
from .errors import ConfigError

logger = logging.getLogger("post_on_telegram")
logger.addHandler(logging.NullHandler())


def _mask_token(token: str | None) -> str:
    """Mask a token for safe display: 1234…wxyz, or asterisks if too short."""
    if not token:
        return ""
    if len(token) <= 8:
        return "*" * len(token)
    return token[:4] + "…" + token[-4:]


def redact(text: str, token: str | None = None) -> str:
    """Central redact function removing token and bot URL segments from text.

    Removes the token, "bot<token>", and "api.telegram.org/bot..." fragments.
    """
    if not text:
        return ""

    result = str(text)

    # 1. Redact specific known token if provided
    if token:
        result = result.replace(token, "<token>")

    # 2. Redact bot token pattern (e.g. 123456789:AAFakeToken...) in URLs or text
    result = re.sub(r"api\.telegram\.org/bot[^/\s]+", "api.telegram.org/bot<token>", result)
    result = re.sub(r"bot\d{5,}:[A-Za-z0-9_-]+", "bot<token>", result)
    result = re.sub(r"\d{5,}:[A-Za-z0-9_-]{20,}", "<token>", result)

    return result


class _Urllib3TokenRedactionFilter(logging.Filter):
    """Logging filter that redacts bot tokens from urllib3 connection log records."""

    def __init__(self, token: str | None = None) -> None:
        super().__init__()
        self._token = token

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the message of the log record in place."""
        try:
            original_msg = record.getMessage()
            redacted = redact(original_msg, self._token)
            if redacted != original_msg:
                record.msg = redacted
                record.args = ()
                record.message = redacted
                record.asctime = record.asctime
            return True
        except Exception:
            return True


def _install_urllib3_redaction(token: str | None = None) -> None:
    """Attach a redaction filter to the "urllib3.connectionpool" logger."""
    logger_name = "urllib3.connectionpool"
    urllib3_logger = logging.getLogger(logger_name)
    if not any(isinstance(f, _Urllib3TokenRedactionFilter) for f in urllib3_logger.filters):
        urllib3_logger.addFilter(_Urllib3TokenRedactionFilter(token))


class Poster:
    """Send text messages (and documents) to a Telegram chat through a bot.

    Designed for long-running programs such as trading bots: it never crashes
    the caller and never leaks the bot token.
    """

    def __init__(
        self,
        credentials_file: str | os.PathLike[str] | None = None,
        *,
        token: str | None = None,
        chat_id: str | int | None = None,
        strict: bool = False,
        timeout: tuple[float, float] = (5, 10),
        max_retries: int = 3,
        total_timeout: float = 30.0,
        chunk_delay: float = 0.5,
        max_message_length: int = 4000,
        session: requests.Session | None = None,
    ) -> None:
        if max_message_length < 1 or max_message_length > 4096:
            msg = f"max_message_length must be in 1..4096, got {max_message_length}"
            if strict:
                raise ConfigError(msg)
            logger.warning(msg)

        if max_retries < 0:
            msg = f"max_retries must be >= 0, got {max_retries}"
            if strict:
                raise ConfigError(msg)
            logger.warning(msg)

        self._strict = strict
        self._timeout = timeout
        self._max_retries = max_retries
        self._total_timeout = total_timeout
        self._chunk_delay = chunk_delay
        self._max_message_length = max_message_length
        self._session = session if session is not None else requests.Session()
        self._lock = threading.Lock()
        self._last_error: str | None = None

        try:
            creds = resolve_credentials(
                token=token,
                chat_id=chat_id,
                credentials_file=credentials_file,
                strict=strict,
            )
            self._token = creds.get("bot_token", "")
            self._chat_id = creds.get("chat_id", "")
        except ConfigError as exc:
            redacted_msg = redact(str(exc), token)
            self._last_error = redacted_msg
            if strict:
                raise ConfigError(redacted_msg) from exc
            logger.warning("Configuration error: %s", redacted_msg)
            self._token = ""
            self._chat_id = ""
        except Exception as exc:
            redacted_msg = redact(str(exc), token)
            self._last_error = redacted_msg
            if strict:
                raise ConfigError(redacted_msg) from exc
            logger.warning("Configuration error: %s", redacted_msg)
            self._token = ""
            self._chat_id = ""

        self._enabled = bool(self._token and self._chat_id)

        _install_urllib3_redaction(self._token)

    @property
    def enabled(self) -> bool:
        """Return True if both token and chat_id are present."""
        return self._enabled

    @property
    def last_error(self) -> str | None:
        """Return the last error message (always redacted)."""
        return self._last_error

    def __repr__(self) -> str:
        return f"<Poster token={_mask_token(self._token)} enabled={self._enabled}>"

    def __str__(self) -> str:
        masked = _mask_token(self._token)
        return f"Poster(token={masked}, chat_id={self._chat_id!r}, enabled={self._enabled})"

    def _set_error(self, message: str) -> None:
        """Store error message in last_error after redacting tokens."""
        self._last_error = redact(message, self._token)

    def _strip_html(self, text: str) -> str:
        """Strip HTML tags for plain-text fallback."""
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text)

    @staticmethod
    def _parse_retry_after(value: Any) -> float | None:
        """Parse a retry_after value from Telegram.

        Returns:
            float >= 0 (math.inf allowed) if valid, None if invalid.
        """
        if value is None:
            return None
        # bool is a subclass of int, check it first
        if isinstance(value, bool):
            return None
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        # NaN check
        if f != f:  # math.isnan(f) but without function call
            return None
        # Negative check
        if f < 0:
            return None
        return f

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        deadline: float,
        **kwargs: Any,
    ) -> requests.Response:
        """Execute request with retries according to SPEC policy.

        Retries on requests.ConnectionError, requests.Timeout, HTTP 5xx, and HTTP 429.
        Never retries other 4xx (400, 401, 403, 404).
        """
        import random

        backoff = 1.0

        for attempt in range(self._max_retries + 1):
            now = time.monotonic()
            if now >= deadline:
                raise TimeoutError("Total timeout deadline exceeded")

            # Adjust per-request timeout so it does not exceed remaining total budget
            remaining_total = deadline - now
            req_timeout = self._timeout
            if isinstance(req_timeout, tuple):
                connect_t, read_t = req_timeout
                req_timeout = (min(connect_t, remaining_total), min(read_t, remaining_total))

            try:
                resp = self._session.request(method, url, timeout=req_timeout, **kwargs)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if attempt == self._max_retries:
                    raise
                now = time.monotonic()
                jitter = random.uniform(0.0, 0.5)
                wait = min(backoff + jitter, 10.0)
                if now + wait >= deadline:
                    raise TimeoutError("Total timeout exceeded during backoff") from exc
                time.sleep(wait)
                backoff = min(backoff * 2, 10.0)
                continue

            # Check status code
            status = resp.status_code

            if status == 429:
                if attempt == self._max_retries:
                    return resp
                # Honour parameters.retry_after from JSON body or Retry-After header
                retry_wait: float | None = None
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        params = data.get("parameters")
                        if isinstance(params, dict) and "retry_after" in params:
                            retry_wait = self._parse_retry_after(params["retry_after"])
                        elif "retry_after" in data:
                            retry_wait = self._parse_retry_after(data["retry_after"])
                except Exception:
                    pass

                if retry_wait is None:
                    hdr = resp.headers.get("Retry-After")
                    if hdr:
                        retry_wait = self._parse_retry_after(hdr)

                if retry_wait is None:
                    # Invalid or missing: fall back to exponential backoff with jitter
                    jitter = random.uniform(0.0, 0.5)
                    retry_wait = min(backoff + jitter, 10.0)

                now = time.monotonic()
                if now + retry_wait >= deadline:
                    # Required wait exceeds remaining total_timeout budget: give up immediately
                    return resp

                time.sleep(retry_wait)
                backoff = min(backoff * 2, 10.0)
                continue

            if 500 <= status < 600:
                if attempt == self._max_retries:
                    return resp
                now = time.monotonic()
                jitter = random.uniform(0.0, 0.5)
                wait = min(backoff + jitter, 10.0)
                if now + wait >= deadline:
                    raise TimeoutError("Total timeout exceeded during backoff")
                time.sleep(wait)
                backoff = min(backoff * 2, 10.0)
                continue

            # 2xx, 3xx, 4xx (non-429): do not retry
            return resp

        raise TimeoutError("Exhausted retries")

    def send(
        self,
        text: Any,
        *,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
        chat_id: str | int | None = None,
    ) -> bool:
        """Send a text message to the chat. Never raises."""
        try:
            if not self._enabled:
                self._set_error("Poster is not configured or disabled")
                return False

            if text is None:
                self._set_error("empty message")
                return False

            text_str = str(text)
            if not text_str.strip():
                self._set_error("empty message")
                return False

            if parse_mode not in (None, "HTML", "MarkdownV2"):
                self._set_error(f"Unsupported parse_mode: {parse_mode!r}")
                return False

            target_chat_id = str(chat_id).strip() if chat_id is not None else self._chat_id
            if not target_chat_id:
                self._set_error("No chat_id specified")
                return False

            # Lock to prevent concurrent threads from interleaving chunks
            with self._lock:
                deadline = time.monotonic() + self._total_timeout
                chunks = chunk_text(text_str, self._max_message_length)
                if not chunks:
                    self._set_error("empty message")
                    return False

                total_chunks = len(chunks)
                url = f"https://api.telegram.org/bot{self._token}/sendMessage"

                for i, chunk in enumerate(chunks):
                    if time.monotonic() >= deadline:
                        self._set_error("Total timeout deadline exceeded")
                        return False

                    payload: dict[str, Any] = {
                        "chat_id": target_chat_id,
                        "text": chunk,
                        "disable_web_page_preview": disable_web_page_preview,
                        "disable_notification": disable_notification,
                    }
                    if parse_mode:
                        payload["parse_mode"] = parse_mode

                    try:
                        resp = self._request_with_retries(
                            "POST", url, deadline=deadline, json=payload
                        )
                    except Exception as exc:
                        self._set_error(f"Network error sending chunk: {exc}")
                        logger.warning("Network error sending chunk: %s", self._last_error)
                        return False

                    # Check response
                    ok, desc, retry_fallback = self._check_response(resp)
                    if not ok:
                        if retry_fallback and parse_mode:
                            logger.warning("Telegram parse error; falling back to plain text")
                            fallback_text = chunk
                            if parse_mode == "HTML":
                                fallback_text = self._strip_html(chunk)

                            fallback_payload = {
                                "chat_id": target_chat_id,
                                "text": fallback_text,
                                "disable_web_page_preview": disable_web_page_preview,
                                "disable_notification": disable_notification,
                            }
                            try:
                                fb_resp = self._request_with_retries(
                                    "POST", url, deadline=deadline, json=fallback_payload
                                )
                                fb_ok, fb_desc, _ = self._check_response(fb_resp)
                                if not fb_ok:
                                    self._set_error(f"HTTP {fb_resp.status_code}: {fb_desc}")
                                    return False
                            except Exception as fb_exc:
                                self._set_error(f"Fallback request failed: {fb_exc}")
                                return False
                        else:
                            self._set_error(f"HTTP {resp.status_code}: {desc}")
                            return False

                    # Delay between chunks
                    if i < total_chunks - 1:
                        if time.monotonic() + self._chunk_delay >= deadline:
                            self._set_error("Total timeout exceeded between chunks")
                            return False
                        time.sleep(self._chunk_delay)

                self._last_error = None
                return True

        except Exception as exc:
            self._set_error(f"Unexpected error: {exc}")
            logger.warning("Unexpected error in send(): %s", self._last_error)
            return False

    def _check_response(self, resp: requests.Response) -> tuple[bool, str, bool]:
        """Check response JSON body. Returns (ok, description, is_parse_error)."""
        try:
            data = resp.json()
        except Exception:
            return False, "Non-JSON response body", False

        if not isinstance(data, dict):
            return False, "Response is not a JSON object", False

        if "ok" not in data:
            return False, "Response missing 'ok' field", False

        if not data["ok"] or resp.status_code != 200:
            desc = str(data.get("description", ""))
            is_parse_error = resp.status_code == 400 and "can't parse entities" in desc.lower()
            return False, desc, is_parse_error

        return True, "", False

    def send_document(
        self,
        path: str | os.PathLike[str],
        caption: str | None = None,
        *,
        parse_mode: str | None = None,
        chat_id: str | int | None = None,
    ) -> bool:
        """Send a file as a document. Never raises."""
        try:
            if not self._enabled:
                self._set_error("Poster is not configured or disabled")
                return False

            file_path = os.path.expanduser(str(path))
            if not os.path.exists(file_path):
                self._set_error(f"File not found: {path}")
                return False

            if not os.path.isfile(file_path):
                self._set_error(f"Not a regular file: {path}")
                return False

            try:
                size = os.path.getsize(file_path)
            except OSError as exc:
                self._set_error(f"Could not stat file: {exc}")
                return False

            if size == 0:
                self._set_error("File is empty")
                return False

            if size > 50 * 1024 * 1024:
                self._set_error("File exceeds 50 MB limit")
                return False

            target_chat_id = str(chat_id).strip() if chat_id is not None else self._chat_id
            if not target_chat_id:
                self._set_error("No chat_id specified")
                return False

            if parse_mode not in (None, "HTML", "MarkdownV2"):
                self._set_error(f"Unsupported parse_mode: {parse_mode!r}")
                return False

            data: dict[str, Any] = {"chat_id": target_chat_id}
            if caption:
                truncated_caption = caption[:1024]
                data["caption"] = truncated_caption
                if parse_mode:
                    data["parse_mode"] = parse_mode

            url = f"https://api.telegram.org/bot{self._token}/sendDocument"
            deadline = time.monotonic() + self._total_timeout

            with open(file_path, "rb") as f:
                files = {"document": (os.path.basename(file_path), f)}
                resp = self._request_with_retries(
                    "POST", url, deadline=deadline, data=data, files=files
                )

            ok, desc, _ = self._check_response(resp)
            if not ok:
                self._set_error(f"HTTP {resp.status_code}: {desc}")
                return False

            self._last_error = None
            return True

        except Exception as exc:
            self._set_error(f"Unexpected error in send_document: {exc}")
            logger.warning("Unexpected error in send_document(): %s", self._last_error)
            return False

    def check(self) -> bool:
        """Call getMe to verify bot token. Never raises."""
        try:
            if not self._token:
                self._set_error("No bot token configured")
                return False

            url = f"https://api.telegram.org/bot{self._token}/getMe"
            deadline = time.monotonic() + self._total_timeout

            resp = self._request_with_retries("GET", url, deadline=deadline)
            ok, desc, _ = self._check_response(resp)
            if not ok:
                self._set_error(f"HTTP {resp.status_code}: {desc}")
                return False

            self._last_error = None
            return True

        except Exception as exc:
            self._set_error(f"Unexpected error in check(): {exc}")
            logger.warning("Unexpected error in check(): %s", self._last_error)
            return False
