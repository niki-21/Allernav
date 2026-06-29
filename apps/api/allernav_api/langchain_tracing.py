from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


def langchain_run_config(
    *,
    name: str,
    metadata: dict[str, Any],
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "run_name": name,
        "tags": tags or ["allernav", "rag"],
        "metadata": metadata,
    }


def invoke_traced_runnable(
    *,
    name: str,
    value: InputT,
    func: Callable[[InputT], OutputT],
    metadata: dict[str, Any],
) -> OutputT:
    try:
        from langchain_core.runnables import RunnableLambda
    except ImportError:
        return func(value)
    runnable = RunnableLambda(func)
    return runnable.invoke(value, config=langchain_run_config(name=name, metadata=metadata))


async def ainvoke_traced_runnable(
    *,
    name: str,
    value: InputT,
    func: Callable[[InputT], Awaitable[OutputT]],
    metadata: dict[str, Any],
) -> OutputT:
    try:
        from langchain_core.runnables import RunnableLambda
    except ImportError:
        return await func(value)
    runnable = RunnableLambda(func)
    return await runnable.ainvoke(value, config=langchain_run_config(name=name, metadata=metadata))


def update_current_trace_metadata(**metadata: Any) -> None:
    try:
        from langsmith import get_current_run_tree

        run = get_current_run_tree()
    except (ImportError, RuntimeError):
        return
    if run is not None:
        run.metadata.update({key: value for key, value in metadata.items() if value is not None})
