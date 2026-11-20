# src/post_on_telegram/errors.py
"""Exceptions raised by the library.

Only raised when strict=True is passed to Poster. In the default
non-strict mode, configuration problems are logged as warnings and
the poster is disabled instead.
"""


class PostOnTelegramError(Exception):
    """Base class for all errors raised by post_on_telegram."""


class ConfigError(PostOnTelegramError):
    """Raised when configuration is invalid and strict=True is set.

    Attributes:
        message: Human-readable description of the problem.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message