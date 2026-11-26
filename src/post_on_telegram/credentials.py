# src/post_on_telegram/credentials.py
"""Credential resolution for the Poster class.

Handles reading bot tokens and chat IDs from:
1. Explicit arguments to Poster
2. A JSON credentials file
3. Environment variables POST_ON_TELEGRAM_TOKEN / POST_ON_TELEGRAM_CHAT_ID

Never logs or returns the unmasked token.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .errors import ConfigError

logger = logging.getLogger("post_on_telegram")


def _expand_user(path: str | os.PathLike[str]) -> Path:
    """Expand ~ in *path* (environment variables are intentionally NOT expanded)."""
    return Path(os.path.expanduser(str(path)))


def _check_file_permissions(path: str | Path) -> None:
    """On POSIX, warn if credentials file is group/other readable (mode & 0o077).

    Never raises; only logs a warning on non-Windows.
    """
    if os.name == "posix":
        try:
            mode = os.stat(str(path)).st_mode
            if mode & 0o077:
                logger.warning(
                    "Credentials file %s is group/other readable (mode %o); consider chmod 600",
                    path,
                    mode & 0o777,
                )
        except OSError:
            pass


def _extract_token_from_dict(data: dict[str, Any], strict: bool) -> str:
    """Extract bot_token from dict, supporting legacy alias 'telegram_token'."""
    val = data.get("bot_token")
    if val is None:
        val = data.get("telegram_token")
    if val is None:
        return ""
    token_str = str(val).strip()
    return token_str


def _extract_chat_id_from_dict(data: dict[str, Any], strict: bool) -> str:
    """Extract chat_id from dict, supporting legacy alias 'telegram_id'."""
    val = data.get("chat_id")
    if val is None:
        val = data.get("telegram_id")
    if val is None:
        return ""
    chat_str = str(val).strip()
    return chat_str


def _decode_credentials_bytes(raw_bytes: bytes) -> str:
    """Decode credentials file bytes, handling UTF-8 (with/without BOM) and UTF-16.

    Detects UTF-16 BOMs (FF FE for little-endian, FE FF for big-endian) and
    decodes accordingly. Falls back to UTF-8 with BOM handling (utf-8-sig).
    """
    if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
        return raw_bytes.decode("utf-16")
    return raw_bytes.decode("utf-8-sig")


def resolve_credentials(
    token: str | None = None,
    chat_id: str | int | None = None,
    *,
    credentials_file: str | os.PathLike[str] | None = None,
    strict: bool = False,
) -> dict[str, str]:
    """Resolve bot token and chat ID following the priority order.

    Priority: explicit args > credentials file > env vars.

    Args:
        token: Explicit bot token.
        chat_id: Explicit chat ID (str or int).
        credentials_file: Path to JSON credentials file.
        strict: If True, raise ConfigError on configuration errors.

    Returns:
        dict with "bot_token" and "chat_id" keys.

    Raises:
        ConfigError: If strict=True and resolution fails or format is invalid.
    """
    resolved_token: str | None = None
    resolved_chat_id: str | None = None

    # 1. Explicit arguments
    if token is not None:
        token_str = str(token).strip()
        if token_str:
            resolved_token = token_str

    if chat_id is not None:
        chat_str = str(chat_id).strip()
        if chat_str:
            resolved_chat_id = chat_str

    # 2. Credentials file
    if credentials_file is not None:
        target_path = _expand_user(credentials_file)
        try:
            path_exists = target_path.exists()
        except OSError as exc:
            path_exists = False
            msg = f"Could not access credentials file {target_path}: {exc}"
            if strict:
                raise ConfigError(msg) from exc
            logger.warning(msg)

        if not path_exists:
            msg = f"Credentials file not found: {target_path}"
            if strict:
                raise ConfigError(msg)
            logger.warning(msg)
        else:
            try:
                is_file = target_path.is_file()
            except OSError as exc:
                is_file = False
                msg = f"Could not stat credentials file {target_path}: {exc}"
                if strict:
                    raise ConfigError(msg) from exc
                logger.warning(msg)

            if not is_file:
                msg = f"Credentials path is not a file: {target_path}"
                if strict:
                    raise ConfigError(msg)
                logger.warning(msg)
            else:
                _check_file_permissions(target_path)
                data: Any = {}
                try:
                    raw_bytes = target_path.read_bytes()
                    raw_text = _decode_credentials_bytes(raw_bytes)
                    if not raw_text.strip():
                        msg = f"Credentials file is empty: {target_path}"
                        if strict:
                            raise ConfigError(msg)
                        logger.warning(msg)
                        data = {}
                    else:
                        data = json.loads(raw_text)
                except ValueError as exc:
                    # Covers UnicodeDecodeError and json.JSONDecodeError
                    msg = f"Invalid JSON in credentials file {target_path}: {exc}"
                    if strict:
                        raise ConfigError(msg) from exc
                    logger.warning(msg)
                    data = {}
                except OSError as exc:
                    msg = f"Could not read credentials file {target_path}: {exc}"
                    if strict:
                        raise ConfigError(msg) from exc
                    logger.warning(msg)
                    data = {}

                if not isinstance(data, dict):
                    msg = (
                        f"Credentials file {target_path} must contain a JSON object, "
                        f"got {type(data).__name__}"
                    )
                    if strict:
                        raise ConfigError(msg)
                    logger.warning(msg)
                else:
                    file_token = _extract_token_from_dict(data, strict)
                    file_chat = _extract_chat_id_from_dict(data, strict)

                    if resolved_token is None and file_token:
                        resolved_token = file_token
                    if resolved_chat_id is None and file_chat:
                        resolved_chat_id = file_chat

    # 3. Environment variables fallback
    if resolved_token is None:
        env_token = os.environ.get("POST_ON_TELEGRAM_TOKEN", "").strip()
        if env_token:
            resolved_token = env_token

    if resolved_chat_id is None:
        env_chat = os.environ.get("POST_ON_TELEGRAM_CHAT_ID", "").strip()
        if env_chat:
            resolved_chat_id = env_chat

    # Validate results
    if strict:
        if not resolved_token:
            raise ConfigError("No bot_token provided or found in environment/file")
        if not resolved_chat_id:
            raise ConfigError("No chat_id provided or found in environment/file")
        if ":" not in resolved_token:
            raise ConfigError("Invalid token format: token does not contain ':'")

    if resolved_token and ":" not in resolved_token:
        logger.warning("Token does not contain ':' (not a valid Telegram bot token)")

    return {
        "bot_token": resolved_token or "",
        "chat_id": resolved_chat_id or "",
    }
