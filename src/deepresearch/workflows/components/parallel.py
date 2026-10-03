"""Bounded parallel work with ordered results and settled sibling cancellation."""
from __future__ import annotations

import asyncio


async def bounded_map(items, worker, *, concurrency=4):
    if type(concurrency) is not int or not 1 <= concurrency <= 8:
        raise ValueError("Parallel admission requires between one and eight slots")
    semaphore = asyncio.Semaphore(concurrency)

    async def execute(item):
        async with semaphore:
            return await worker(item)

    tasks = [asyncio.create_task(execute(item)) for item in items]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
