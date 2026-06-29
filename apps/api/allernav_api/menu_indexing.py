from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from .azure_search import index_restaurant_menu
from .models import IngestionTraceStep, MenuRefreshJob, SearchIndexResponse


JobPersister = Callable[[MenuRefreshJob], None]
MenuIndexer = Callable[[str], SearchIndexResponse]


def finish_menu_index(
    job: MenuRefreshJob,
    *,
    persist: JobPersister,
    indexer: MenuIndexer | None = None,
) -> MenuRefreshJob:
    started_at = datetime.now(UTC)
    running = job.model_copy(
        update={
            "indexing_status": "running",
            "trace": _upsert_trace(
                job.trace,
                IngestionTraceStep(
                    id="search_index",
                    label="Index menu evidence",
                    status="running",
                    detail="Menu evidence is available while the RAG index updates.",
                    provider="azure_ai_search",
                    item_count=job.item_count,
                ),
            ),
        }
    )
    persist(running)

    try:
        result = (indexer or index_restaurant_menu)(job.place_id)
        index_status = "complete" if result.status == "indexed" else "skipped"
        detail = (
            f"Indexed {result.indexed_documents} dish document{'s' if result.indexed_documents != 1 else ''} in Azure AI Search."
            if result.status == "indexed"
            else f"Azure AI Search returned {result.status.replace('_', ' ')}."
        )
        item_count = result.indexed_documents
    except Exception as exc:  # noqa: BLE001 - a published menu remains available after index failure
        index_status = "failed"
        detail = str(exc) or "Azure AI Search indexing failed."
        item_count = 0

    updated = running.model_copy(
        update={
            "indexing_status": index_status,
            "message": _completion_message(job.item_count, index_status),
            "trace": _upsert_trace(
                running.trace,
                IngestionTraceStep(
                    id="search_index",
                    label="Index menu evidence",
                    status=index_status,
                    detail=detail,
                    provider="azure_ai_search",
                    item_count=item_count,
                    duration_ms=round((datetime.now(UTC) - started_at).total_seconds() * 1000),
                ),
            ),
        }
    )
    persist(updated)
    return updated


def _completion_message(item_count: int, index_status: str) -> str:
    if index_status == "complete":
        return f"Captured {item_count} menu items; RAG index is ready."
    if index_status == "failed":
        return f"Captured {item_count} menu items; RAG indexing failed but the menu remains available."
    return f"Captured {item_count} menu items; RAG indexing was skipped."


def _upsert_trace(trace: list[IngestionTraceStep], step: IngestionTraceStep) -> list[IngestionTraceStep]:
    return [existing for existing in trace if existing.id != step.id] + [step]
