"""User-facing errors. Each one is rendered as a short message, never a traceback."""

from __future__ import annotations

# Exit codes (see the CLI surface ticket).
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_ENV = 3


class ShepherdError(Exception):
    """Base class for errors shown to the user in Shepherd terms."""

    exit_code = EXIT_FAIL

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigError(ShepherdError):
    exit_code = EXIT_USAGE


class UnknownBoard(ShepherdError):
    exit_code = EXIT_USAGE


class EnvironmentProblem(ShepherdError):
    """Missing toolchain, missing backend, unusable machine setup."""

    exit_code = EXIT_ENV


class NetworkRequired(EnvironmentProblem):
    """A step needs internet and the network failed or is offline."""

    def __init__(self, what: str, *, failed: str | None = None, hint: str | None = None):
        self.what = what
        self.failed = failed
        message = f"internet required for {what}"
        if hint is None:
            if what == "AI explanation":
                hint = "connect to the network and re-run, or use `--no-ai`"
            else:
                hint = (
                    "connect to the network and re-run `shepherd init` "
                    "(or `shepherd doctor --fix` to repair)"
                )
        super().__init__(message, hint=hint)


class RunLocked(ShepherdError):
    exit_code = EXIT_ENV
