# src/post_on_telegram/credentials.py
"""Credential resolution for the Poster class.

Handles reading bot tokens and chat IDs from:
1. Explicit arguments to Poster
2. A JSON credentials file
3. Environment variables POST_ON_TELEGRAM_TOKEN / POST_ON_TELEGRAM_CHAT_ID

Never logs or returns the full token; always masks it.
"""

import json
import os
import re
import warnings
from pathlib import Path
from typing import Optional

from .errors import ConfigError
from .logging_utils import get_logger

logger = get_logger(__name__)

#: Fake token used in tests; never leak this in logs or error messages.
_CANARY_TOKEN = "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq"

#: Regex matching a Telegram bot token: digits, colon, letters/digits/underscore.
_TOKEN_RE = re.compile(r"^\d{3,5}:[A-Za-z0-9_]+$")


def _mask_token(token: Optional[str]) -> str:
    """Return a masked version of *token* for safe logging/display.

    Format: first 3 chars + "…" + last 4 chars, or all stars if too short.
    """
    if not token:
        return ""
    if len(token) <= 7:
        return "*" * len(token)
    return token[:3] + "…" + token[-4:]


def _expand_user(path: str) -> str:
    """Expand ~ and environment variables in *path*."""
    return os.path.expanduser(os.path.expandvars(path))


def _check_file_permissions(path: str) -> None:
    """On POSIX, warn if credentials file is group/other readable.

    Never raises; only logs a warning on non-Windows.
    """
    if os.name == "posix":
        try:
            mode = os.stat(path).st_mode
            if mode & 0o077:
                logger.warning(
                    "Credentials file %s is group/other readable; "
                    "consider chmod 600 to avoid leaking your token.",
                    path,
                )
        except OSError:
            pass


def resolve_credentials(
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
    *,
    credentials_file: Optional[str | os.PathLike] = None,
    strict: bool = False,
) -> dict[str, str]:
    """Resolve bot token and chat ID following the priority order.

    Priority (explicit args > credentials file > env vars).

    Args:
        token: Explicit bot token (overrides all other sources).
        chat_id: Explicit chat ID (overrides all other sources).
        credentials_file: Path to JSON file with keys "bot_token" and "chat_id".
        strict: If True, raise ConfigError on any problem; if False, log
                warning and return empty dict (poster will be disabled).

    Returns:
        dict with keys "bot_token" and "chat_id" (both str), or empty dict
        if strict=False and problems are found.

    Raises:
        ConfigError: If strict=True and a problem is found.
    """
    # ------------------------------------------------------------------
    # 1. Explicit arguments (highest priority)
    # ------------------------------------------------------------------
    resolved_token: Optional[str] = token
    resolved_chat_id: Optional[str] = chat_id

    # ------------------------------------------------------------------
    # 2. Credentials file
    # ------------------------------------------------------------------
    if resolved_token is None or resolved_chat_id is None:
        cf: Optional[Path] = None
        if credentials_file is not None:
            cf = Path(_expand_user(str(credentials_file)))
        else:
            # Check common locations
            for candidate in (
                Path("~/.post-on-telegram-credentials.json"),
                Path("~/.config/post-on-telegram/credentials.json"),
            ):
                if candidate.exists():
                    cf = candidate
                    break

        if cf is not None and cf.is_file():
            try:
                data = json.loads(cf.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                msg = f"Invalid JSON in credentials file {cf}: {exc}"
                if strict:
                    raise ConfigError(msg) from exc
                logger.warning(msg)
                data = {}
            else:
                _check_file_permissions(str(cf))
                if not isinstance(data, dict):
                    msg = f"Credentials file {cf} must contain a JSON object"
                    if strict:
                        raise ConfigError(msg) from exc
                    logger.warning(msg)
                    data = {}
                else:
                    # Extract token and chat_id, supporting legacy aliases
                    resolved_token = _extract_token_from_dict(data, strict)
                    resolved_chat_id = _extract_chat_id_from_dict(data, strict)

                    if resolved_token and resolved_chat_id:
                        # Both found – good, skip env vars
                        pass
                    elif resolved_token and not resolved_chat_id:
                        msg = f"Credentials file {cf} missing chat_id"
                        if strict:
                            raise ConfigError(msg) from exc
                        logger.warning(msg)
                    elif not resolved_token and resolved_chat_id:
                        msg = f"Credentials file {cf} missing bot_token"
                        if strict:
                            raise ConfigError(msg) from exc
                        logger.warning(msg)

    # ------------------------------------------------------------------
    # 3. Environment variables (lowest priority)
    # ------------------------------------------------------------------
    if resolved_token is None:
        env_token = os.environ.get("POST_ON_TELEGRAM_TOKEN", "")
        if env_token:
            if _TOKEN_RE.match(env_token):
                resolved_token = env_token
            else:
                msg = (
                    f"Environment variable POST_ON_TELEGRAM_TOKEN "
                    f"does not look like a Telegram token: {env_token!r}"
                )
                if strict:
                    raise ConfigError(msg) from exc
                logger.warning(msg)

    if resolved_chat_id is None:
        resolved_chat_id = os.environ.get("POST_ON_TELEGRAM_CHAT_ID", "")
        if resolved_chat_id:
            # Store as string, strip whitespace/newlines
            resolved_chat_id = resolved_chat_id.strip()
        else:
            resolved_chat_id = ""

    # ------------------------------------------------------------------
    # 4. Final validation
    # ------------------------------------------------------------------
    if not resolved_token:
        msg = "No bot token found (explicit, file, or env var)."
        if strict:
            raise ConfigError(msg)
        logger.warning(msg)
        resolved_token = ""

    if not resolved_chat_id:
        msg = "No chat_id found (explicit, file, or env var)."
        if strict:
            raise ConfigError(msg)
        logger.warning(msg)
        resolved_chat_id = ""

    # Ensure token has a colon (Telegram bot token format)
    if resolved_token and ":" not in resolved_token:
        msg = f"Token {resolved_token!r} does not contain ':' (not a valid bot token)"
        if strict:
            raise ConfigError(msg)
        logger.warning(msg)

    result = {"bot_token": resolved_token, "chat_id": str(resolved_chat_id)}
    return result


def _extract_token_from_dict(data: dict, strict: bool) -> str:
    """Extract bot_token from dict, supporting legacy alias 'telegram_token'.

    Returns empty string if not found and strict=False (logs warning).
    Raises ConfigError if strict=True.
    """
    token = data.get("bot_token") or data.get("telegram_token")
    if not token:
        if strict:
            raise ConfigError("No bot_token found in credentials file")
        logger.warning("No bot_token found in credentials file")
        return ""
    # Validate format
    if not _TOKEN_RE.match(token):
        if strict:
            raise ConfigError(f"Token {token!r} does not look like a Telegram bot token")
        logger.warning("Token %s does not look like a Telegram bot token", token)
        return ""
    # Strip whitespace/newlines
    token = token.strip()
    if not token:
        if strict:
            raise ConfigError("bot_token is empty after stripping")
        logger.warning("bot_token is empty after stripping")
        return ""
    return token


def _extract_chat_id_from_dict(data: dict, strict: bool) -> str:
    """Extract chat_id from dict, supporting legacy alias 'telegram_id'.

    Returns empty string if not found and strict=False (logs warning).
    Raises ConfigError if strict=True.
    """
    chat_id = data.get("chat_id") or data.get("telegram_id")
    if chat_id is None:
        if strict:
            raise ConfigError("No chat_id found in credentials file")
        logger.warning("No chat_id found in credentials file")
        return ""
    # Strip whitespace/newlines
    chat_id = str(chat_id).strip()
    if not chat_id:
        if strict:
            raise ConfigError("chat_id is empty after stripping")
        logger.warning("chat_id is empty after stripping")
        return ""
    return chat_id