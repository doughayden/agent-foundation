"""Eval-lane hook that lets a test choose the session's exit code.

A gate that finds its verdict rests on unscored runs fails its test normally, so
pytest reports the traceback, captured logs, and stdout as usual, then records
``EVAL_ERROR_EXIT_CODE`` here so ``judge-eval.yml`` can tell that failure apart
from a sub-threshold score (exit 1). This conftest holds no credential mocking:
the eval lane runs against real credentials.
"""

from collections.abc import Callable

import pytest

EXIT_STATUS_KEY = pytest.StashKey[int]()


@pytest.fixture
def set_exit_status(request: pytest.FixtureRequest) -> Callable[[int], None]:
    """Return a function that sets the exit code the session ends with."""

    def _set(code: int) -> None:
        request.config.stash[EXIT_STATUS_KEY] = code

    return _set


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Replace the session's exit code with one a test recorded, if any."""
    code = session.config.stash.get(EXIT_STATUS_KEY, None)
    if code is not None:
        session.exitstatus = code
