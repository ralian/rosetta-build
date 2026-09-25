"""Async subprocess helpers for compiler/linker drivers."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

__all__ = ["run_driver"]


async def run_driver(argv: Sequence[str]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    returncode = process.returncode
    if returncode is None:
        returncode = -1
    return (
        returncode,
        stdout_bytes.decode(errors="replace"),
        stderr_bytes.decode(errors="replace"),
    )
