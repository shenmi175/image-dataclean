from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Generic, TypeVar

from backend.tools.base import TaskCancelled, TaskContext
from backend.tools.common.batch import checkpoint

ItemT = TypeVar("ItemT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class ParallelResult(Generic[ItemT, ResultT]):  # noqa: UP046 - Python 3.10 launcher
    index: int
    item: ItemT
    value: ResultT | None = None
    error: BaseException | None = None


def parallel_map(  # noqa: UP047 - Python 3.10 launcher
    items: Iterable[ItemT],
    worker: Callable[[ItemT], ResultT],
    context: TaskContext,
    *,
    workers: int | None = None,
    max_in_flight: int | None = None,
) -> Iterator[ParallelResult[ItemT, ResultT]]:
    """Run bounded file-level work and yield results as they complete.

    Task state, counters and reports remain owned by the caller thread. The
    iterable is consumed lazily so video frames and large datasets stay bounded.
    """
    worker_count = max(1, workers or context.parallel_workers)
    if worker_count == 1:
        for index, item in enumerate(items):
            checkpoint(context)
            try:
                yield ParallelResult(index, item, value=worker(item))
            except TaskCancelled:
                raise
            except BaseException as exc:
                yield ParallelResult(index, item, error=exc)
        return

    limit = max(worker_count, max_in_flight or worker_count * 2)
    iterator = enumerate(items)
    executor = ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix=f"tool-{context.task_id[:8]}",
    )
    pending: dict[Future[ResultT], tuple[int, ItemT]] = {}

    def fill() -> None:
        while len(pending) < limit:
            checkpoint(context)
            try:
                index, item = next(iterator)
            except StopIteration:
                return
            pending[executor.submit(worker, item)] = (index, item)

    context.log("info", f"启用并行处理：{worker_count} 个线程")
    aborted = False
    try:
        fill()
        while pending:
            checkpoint(context)
            completed, _ = wait(tuple(pending), timeout=0.1, return_when=FIRST_COMPLETED)
            if not completed:
                continue
            for future in completed:
                index, item = pending.pop(future)
                try:
                    yield ParallelResult(index, item, value=future.result())
                except TaskCancelled:
                    raise
                except BaseException as exc:
                    yield ParallelResult(index, item, error=exc)
            fill()
    except BaseException:
        aborted = True
        for future in pending:
            future.cancel()
        raise
    finally:
        executor.shutdown(wait=not aborted, cancel_futures=True)
