from __future__ import annotations

from backend.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, type[Tool]] = {}

    def register(self, tool: type[Tool]) -> None:
        if tool.id in self._tools:
            raise ValueError(f"Duplicate tool id: {tool.id}")
        self._tools[tool.id] = tool

    def get(self, tool_id: str) -> type[Tool]:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {tool_id}") from exc

    def list(self) -> list[type[Tool]]:
        return sorted(self._tools.values(), key=lambda item: (item.category, item.name))


registry = ToolRegistry()


def register_builtin_tools() -> None:
    if registry.list():
        return
    from backend.tools.video_frames import VideoFramesTool

    registry.register(VideoFramesTool)


register_builtin_tools()
