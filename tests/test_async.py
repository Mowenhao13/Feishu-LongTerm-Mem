from __future__ import annotations

import asyncio

import pytest

from src.detect.async_runner import (
    AsyncSignalProcessor,
    AsyncTaskRunner,
    get_global_runner,
    is_uvloop_available,
    periodic_task,
    run_async,
    setup_event_loop,
)
from src.detect.detector import async_detect


class TestEventLoopSetup:
    def test_setup_event_loop_does_not_raise(self):
        setup_event_loop()

    def test_is_uvloop_available_bool(self):
        assert isinstance(is_uvloop_available(), bool)


class TestRunAsync:
    @pytest.mark.asyncio
    async def test_run_async_simple(self):
        async def hello() -> str:
            return "hello"

        result = await run_async(hello())
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_run_async_timeout(self):
        async def slow() -> str:
            await asyncio.sleep(100)
            return "slow"

        with pytest.raises(TimeoutError):
            await run_async(slow(), timeout=0.1)


class TestAsyncTaskRunner:
    @pytest.mark.asyncio
    async def test_run_single_task(self):
        runner = AsyncTaskRunner(max_concurrent=5)

        async def task() -> int:
            return 42

        result = await runner.run(task(), timeout=5.0)
        assert result == 42

    @pytest.mark.asyncio
    async def test_run_many_tasks(self):
        runner = AsyncTaskRunner(max_concurrent=5)

        async def task(i: int) -> int:
            return i * 2

        coros = [task(i) for i in range(5)]
        results = await runner.run_many(coros, timeout=10.0)
        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_run_many_empty(self):
        runner = AsyncTaskRunner()
        results = await runner.run_many([], timeout=10.0)
        assert results == []

    def test_run_sync(self):
        runner = AsyncTaskRunner()

        async def task() -> str:
            return "sync_result"

        result = runner.run_sync(task())
        assert result == "sync_result"

    def test_global_runner_singleton(self):
        r1 = get_global_runner()
        r2 = get_global_runner()
        assert r1 is r2


class TestAsyncDetect:
    @pytest.mark.asyncio
    async def test_async_detect_im(self):
        result = await async_detect("决定使用PostgreSQL", source="im")
        assert isinstance(result, dict)
        assert "score" in result
        assert "level" in result
        assert "is_decision" in result
        assert "anti_signals" in result
        assert "signal_count" in result

    @pytest.mark.asyncio
    async def test_async_detect_decision(self):
        result = await async_detect("决定使用Python开发后端服务")
        assert result["is_decision"] is True
        assert result["score"] > 0

    @pytest.mark.asyncio
    async def test_async_detect_non_decision(self):
        result = await async_detect("早上好，今天天气真好")
        assert result["is_decision"] is False

    @pytest.mark.asyncio
    async def test_async_detect_doc_source(self):
        result = await async_detect("采用微服务架构方案", source="doc")
        assert isinstance(result, dict)
        assert "score" in result

    @pytest.mark.asyncio
    async def test_async_detect_empty(self):
        result = await async_detect("")
        assert result["is_decision"] is False
        assert result["score"] == 0.0


class TestAsyncSignalProcessor:
    @pytest.mark.asyncio
    async def test_process_text(self):
        processor = AsyncSignalProcessor()
        result = await processor.process_text("决定使用MySQL", source="im")
        assert isinstance(result, dict)
        assert "score" in result

    @pytest.mark.asyncio
    async def test_process_batch(self):
        processor = AsyncSignalProcessor()
        items = [
            {"content": "决定使用PostgreSQL", "source": "im"},
            {"content": "早上好", "source": "im"},
            {"content": "采用微服务架构方案", "source": "doc"},
        ]
        results = await processor.process_batch(items)
        assert len(results) == 3
        assert results[0]["is_decision"] is True
        assert results[1]["is_decision"] is False

    @pytest.mark.asyncio
    async def test_process_batch_empty(self):
        processor = AsyncSignalProcessor()
        results = await processor.process_batch([])
        assert results == []


class TestPeriodicTask:
    @pytest.mark.asyncio
    async def test_periodic_task_cancellation(self):
        call_count = 0

        async def task():
            nonlocal call_count
            call_count += 1

        runner = asyncio.create_task(periodic_task(0.05, task))
        await asyncio.sleep(0.12)
        runner.cancel()
        await runner
        assert call_count >= 1


class TestAsyncSignalProcessorConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_limit(self):
        runner = AsyncTaskRunner(max_concurrent=2)

        async def slow_task(i: int) -> int:
            await asyncio.sleep(0.1)
            return i

        coros = [slow_task(i) for i in range(4)]
        results = await runner.run_many(coros, timeout=5.0)
        assert results == [0, 1, 2, 3]