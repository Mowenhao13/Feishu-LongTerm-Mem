from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_uvloop_available: bool = False
try:
    import uvloop

    _uvloop_available = True
except ImportError:
    pass


def is_uvloop_available() -> bool:
    return _uvloop_available


def setup_event_loop() -> None:
    """Configure an event loop, preferring uvloop for better performance."""
    if _uvloop_available:
        import uvloop

        uvloop.install()
        logger.info("uvloop installed as the event loop policy")


async def run_async(coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
    """Run an async coroutine with a timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Task timed out after {timeout}s")


class AsyncTaskRunner:
    """Simple async task runner with event loop management.

    Provides a synchronous interface for running async tasks,
    with support for concurrency limits and timeouts.
    """

    def __init__(self, max_concurrent: int = 10) -> None:
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
        async with self._semaphore:
            return await run_async(coro, timeout)

    async def run_many(
        self,
        coros: list[Coroutine[Any, Any, T]],
        timeout: float = 60.0,
    ) -> list[T]:
        sem = asyncio.Semaphore(self._max_concurrent)

        async def _limited(c: Coroutine[Any, Any, T]) -> T:
            async with sem:
                return await asyncio.wait_for(c, timeout=timeout / len(coros) if coros else timeout)

        return await asyncio.gather(*[_limited(c) for c in coros], return_exceptions=False)

    def run_sync(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run a coroutine synchronously from a sync context.

        Creates a new event loop if none exists.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        else:
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result()
            return loop.run_until_complete(coro)


_global_runner: Optional[AsyncTaskRunner] = None


def get_global_runner() -> AsyncTaskRunner:
    global _global_runner
    if _global_runner is None:
        setup_event_loop()
        _global_runner = AsyncTaskRunner()
    return _global_runner


class AsyncSignalProcessor:
    """Async wrapper for signal processing pipeline.

    Makes the signal detection and context assembly pipeline
    async-compatible.
    """

    def __init__(self, runner: Optional[AsyncTaskRunner] = None) -> None:
        from src.signal.detector import EnhancedDetector

        self._runner = runner or get_global_runner()
        self._detector = EnhancedDetector()

    async def process_text(
        self,
        content: str,
        source: str = "im",
    ) -> dict[str, Any]:
        """Async text processing: detect decision signals."""
        from src.signal.detector import async_detect

        return await self._runner.run(async_detect(content, source))

    async def process_batch(
        self,
        items: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Async batch processing."""
        from src.signal.detector import async_detect

        coros = [async_detect(item.get("content", ""), item.get("source", "im")) for item in items]
        return await self._runner.run_many(coros)


async def periodic_task(interval: float, coro_factory: Callable[[], Coroutine[Any, Any, None]]) -> None:
    """Run a periodic task with a fixed interval between completions."""
    while True:
        try:
            start = asyncio.get_event_loop().time()
            await coro_factory()
            elapsed = asyncio.get_event_loop().time() - start
            sleep = max(0.0, interval - elapsed)
            await asyncio.sleep(sleep)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Periodic task failed: %s", e)
            await asyncio.sleep(interval)