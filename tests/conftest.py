"""Pytest compatibility helpers for asyncio-marked tests.

This keeps async tests runnable in environments where pytest-asyncio
is not installed, while preserving existing @pytest.mark.asyncio usage.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    """
    Execute coroutine tests marked with ``@pytest.mark.asyncio`` without
    requiring an external plugin.
    """
    if "asyncio" not in pyfuncitem.keywords:
        return None

    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None

    kwargs = {
        arg_name: pyfuncitem.funcargs[arg_name]
        for arg_name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_func(**kwargs))
    return True
