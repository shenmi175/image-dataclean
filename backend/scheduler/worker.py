from __future__ import annotations

import traceback
from typing import Any

from backend.scheduler.context import WorkerTaskContext
from backend.tools.base import TaskCancelled
from backend.tools.registry import registry


def run_task_worker(
    task_id: str,
    tool_id: str,
    params: dict[str, Any],
    output_path: str,
    pause_event: Any,
    cancel_event: Any,
    message_queue: Any,
    resolution_queue: Any,
) -> None:
    context = WorkerTaskContext(
        task_id,
        output_path,
        pause_event,
        cancel_event,
        message_queue,
        resolution_queue,
    )
    try:
        tool_type = registry.get(tool_id)
        validated = tool_type.params_model.model_validate(params)
        result = tool_type().run(validated, context)
        message_queue.put({"kind": "completed", "result": result})
    except TaskCancelled:
        message_queue.put({"kind": "cancelled", "message": "任务已取消，部分输出已保留"})
    except Exception as exc:  # worker boundary must report every tool failure
        message_queue.put(
            {
                "kind": "failed",
                "error": str(exc) or exc.__class__.__name__,
                "traceback": traceback.format_exc(),
            }
        )
