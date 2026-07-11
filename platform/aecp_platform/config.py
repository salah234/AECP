"""Environment-based configuration loading.

Services must fail closed at startup: any missing required setting is a
startup error, never a silently-applied default. This module should
collect every missing/invalid key and raise once, so an operator sees the
full list of problems instead of fixing them one restart at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ConfigError(Exception):
    """Raised when one or more required settings are missing or invalid."""


@dataclass
class Loader:
    """Collects configuration values from the environment.

    Usage pattern (once implemented): construct a Loader, call the typed
    getters for every setting a service needs, then call `.validate()`
    once at the end of startup and let it raise ConfigError with every
    problem found, rather than raising on the first missing var.
    """

    prefix: str = ""
    _errors: list[str] = field(default_factory=list)

    def require_str(self, key: str) -> str:
        """Return the string value of an env var, recording an error if unset/blank."""
        raise NotImplementedError

    def optional_str(self, key: str, default: str) -> str:
        """Return the string value of an env var, or `default` if unset."""
        raise NotImplementedError

    def require_int(self, key: str) -> int:
        """Return the int value of an env var, recording an error if unset/invalid."""
        raise NotImplementedError

    def optional_bool(self, key: str, default: bool) -> bool:
        """Return the bool value of an env var, or `default` if unset."""
        raise NotImplementedError

    def validate(self) -> None:
        """Raise ConfigError listing every problem recorded so far, or
        return None if configuration is complete and valid.
        """
        raise NotImplementedError
