class PostOnTelegramError(Exception):
    """Base exception for post-on-telegram."""


class ConfigError(PostOnTelegramError):
    """Raised when configuration is invalid (strict mode)."""
