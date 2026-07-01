from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from . import supabase_store
from .document_intelligence import DocumentExtraction, extract_document_from_url
from .menu_indexing import finish_menu_index
from .menu_ingestion import (
    ingest_menu_from_website,
    sanitize_ingestion_exception,
    sanitize_sections,
    save_menu_source,
    summarize_menu_text,
)
from .menu_job_queue import MenuRefreshMessage
from .menu_normalization import extract_english_menu_page
from .models import IngestionTraceStep, MenuRefreshJob, MenuSection, MenuSource, SourceType


DocumentExtractor = Callable[[str], DocumentExtraction | None]
PageNormalizer = Callable[..., list[MenuSection]]


def process_menu_refresh_message(
    message: MenuRefreshMessage,
    *,
    attempt: int = 1,
    extractor: DocumentExtractor = extract_document_from_url,
    normalizer: PageNormalizer = extract_english_menu_page,
) -> MenuRefreshJob:
    existing = supabase_store.load_menu_refresh_job(message.job_id)
    if existing and existing.status == "complete":
        if existing.indexing_status in {"pending", "failed"}:
            return finish_menu_index(existing, persist=_save_job)
        return existing
    job = existing or _new_job(message)
    try:
        if message.document_urls:
            job = _process_image_menu(job, message, extractor=extractor, normalizer=normalizer)
        else:
            job = _process_discovery_fallback(job, message)
        return job
    except Exception as exc:
        terminal = attempt >= 3
        detail = sanitize_ingestion_exception(exc)
        no_items_extracted = str(exc) == "No reliable dish-level menu items were extracted."
        failed = job.model_copy(
            update={
                "status": "failed" if terminal else "queued",
                "message": (
                    "No reliable dish-level menu items were extracted."
                    if terminal and no_items_extracted
                    else f"Menu processing failed after {attempt} attempts: {detail}"
                    if terminal
                    else f"Menu processing attempt {attempt} failed and will be retried."
                ),
                "completed_at": datetime.now(UTC).isoformat() if terminal else None,
                "trace": _upsert_trace(
                    job.trace,
                    IngestionTraceStep(
                        id="menu_ingestion_error",
                        label="Run menu discovery",
                        status="failed",
                        detail=detail,
                        provider="fastapi",
                    ),
                ),
            }
        )
        _save_job(failed)
        raise


def _process_image_menu(
    job: MenuRefreshJob,
    message: MenuRefreshMessage,
    *,
    extractor: DocumentExtractor,
    normalizer: PageNormalizer,
) -> MenuRefreshJob:
    job = _transition(
        job,
        status="ocr_processing",
        message=f"Reading 0 of {len(message.document_urls)} menu pages with Azure Document Intelligence.",
        trace=IngestionTraceStep(
            id="document_ocr",
            label="Read menu images",
            status="running",
            detail=f"Processing {len(message.document_urls)} official menu images.",
            provider="azure_document_intelligence",
        ),
    )
    stored_pages = supabase_store.load_menu_document_pages(job.id)
    extractions: dict[int, tuple[str, DocumentExtraction]] = {}
    pending: list[tuple[int, str]] = []
    for page_number, url in enumerate(message.document_urls, start=1):
        stored = stored_pages.get(url)
        if stored and stored.get("status") == "complete" and isinstance(stored.get("raw_text"), str):
            extractions[page_number] = (
                url,
                DocumentExtraction(
                    content=str(stored["raw_text"]),
                    content_type="image/jpeg",
                    extraction_method="azure_document_intelligence",
                    page_count=1,
                    confidence=(
                        float(stored["extraction_confidence"])
                        if isinstance(stored.get("extraction_confidence"), (int, float))
                        else None
                    ),
                ),
            )
        else:
            pending.append((page_number, url))

    failures: list[str] = []
    if pending:
        with ThreadPoolExecutor(max_workers=min(3, len(pending))) as executor:
            futures = {executor.submit(extractor, url): (page_number, url) for page_number, url in pending}
            for future in as_completed(futures):
                page_number, url = futures[future]
                extraction = future.result()
                if extraction:
                    extractions[page_number] = (url, extraction)
                    supabase_store.save_menu_document_page(
                        job_id=job.id,
                        restaurant_id=message.place_id,
                        document_url=url,
                        page_number=page_number,
                        status="complete",
                        raw_text=extraction.content,
                        extraction_confidence=extraction.confidence,
                    )
                else:
                    failures.append(url)
                    supabase_store.save_menu_document_page(
                        job_id=job.id,
                        restaurant_id=message.place_id,
                        document_url=url,
                        page_number=page_number,
                        status="failed",
                        error_message="Azure Document Intelligence returned no content.",
                    )
                job = job.model_copy(
                    update={
                        "processed_documents": len(extractions),
                        "message": f"Read {len(extractions)} of {len(message.document_urls)} menu pages.",
                    }
                )
                _save_job(job)
    if failures or len(extractions) != len(message.document_urls):
        job = _transition(
            job,
            status="ocr_processing",
            message="Azure Document Intelligence could not read every menu page.",
            trace=IngestionTraceStep(
                id="document_ocr",
                label="Read menu images",
                status="failed",
                detail=f"OCR failed for {len(failures) or len(message.document_urls) - len(extractions)} menu page(s).",
                provider="azure_document_intelligence",
                item_count=len(extractions),
            ),
        )
        raise RuntimeError(f"OCR failed for {len(failures) or len(message.document_urls) - len(extractions)} menu page(s).")

    job = _transition(
        job,
        status="normalizing",
        message="Converting OCR evidence into structured English menu items.",
        trace=IngestionTraceStep(
            id="document_ocr",
            label="Read menu images",
            status="complete",
            detail=f"Azure OCR returned content for all {len(extractions)} menu pages.",
            provider="azure_document_intelligence",
            item_count=len(extractions),
        ),
    )
    sections: list[MenuSection] = []
    for page_number in sorted(extractions):
        url, extraction = extractions[page_number]
        sections.extend(
            normalizer(
                ocr_text=extraction.content,
                source_url=url,
                source_page=page_number,
                ocr_confidence=extraction.confidence,
                restaurant_id=message.place_id,
            )
        )
    sections = sanitize_sections(sections, max_sections=24, max_items_per_section=60)
    if not sections:
        raise RuntimeError("OCR completed, but English menu normalization produced no grounded dishes.")

    confidences = [
        extraction.confidence
        for _url, extraction in extractions.values()
        if extraction.confidence is not None
    ]
    confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
    source = MenuSource(
        source_type=SourceType.OFFICIAL_MENU,
        source_url=message.website_url,
        source_timestamp=datetime.now(UTC).isoformat(),
        reliability=round(min(0.82, max(0.35, confidence or 0.55)), 2),
        raw_text=summarize_menu_text(sections),
        sections=sections,
        content_type="image/jpeg",
        document_url=message.document_urls[0],
        document_urls=message.document_urls,
        menu_version=message.menu_version,
        extraction_method="azure_document_intelligence_langchain",
        page_count=len(extractions),
        extraction_confidence=confidence,
    )
    stored = save_menu_source(
        restaurant_id=message.place_id,
        restaurant_name=message.restaurant_name,
        source=source,
        save_local=False,
    )
    if not stored:
        raise RuntimeError("Could not persist the completed menu in Supabase.")
    item_count = sum(len(section.items) for section in sections)
    completed = job.model_copy(
        update={
            "status": "complete",
            "message": f"Captured {item_count} menu items; RAG indexing is continuing in the background.",
            "item_count": item_count,
            "source_url": source.source_url,
            "content_type": source.content_type,
            "extraction_method": source.extraction_method,
            "page_count": source.page_count,
            "extraction_confidence": source.extraction_confidence,
            "processed_documents": len(extractions),
            "indexing_status": "pending",
            "completed_at": datetime.now(UTC).isoformat(),
            "trace": _upsert_trace(
                _upsert_trace(
                    _upsert_trace(
                        job.trace,
                        IngestionTraceStep(
                            id="normalization",
                            label="Structure OCR evidence",
                            status="complete",
                            detail=f"LangChain structured extraction produced {item_count} grounded English dishes.",
                            provider="langchain_azure_openai",
                            item_count=item_count,
                        ),
                    ),
                    IngestionTraceStep(
                        id="menu_extracted",
                        label="Menu extracted",
                        status="complete",
                        detail=f"Published {item_count} dish-level menu items for immediate review.",
                        provider=source.extraction_method,
                        item_count=item_count,
                    ),
                ),
                IngestionTraceStep(
                    id="search_index",
                    label="Index menu evidence",
                    status="pending",
                    detail="Menu extracted and published; the RAG index is updating.",
                    provider="azure_ai_search",
                    item_count=item_count,
                ),
            ),
        }
    )
    _save_job(completed)
    return finish_menu_index(completed, persist=_save_job)


def _process_discovery_fallback(job: MenuRefreshJob, message: MenuRefreshMessage) -> MenuRefreshJob:
    source = ingest_menu_from_website(
        restaurant_id=message.place_id,
        restaurant_name=message.restaurant_name,
        website_url=message.website_url,
        db_path=Path("/tmp/allernav-menu-worker.sqlite"),
        trace=job.trace,
        deep_scan=True,
    )
    item_count = sum(len(section.items) for section in source.sections)
    if not item_count:
        raise RuntimeError("No reliable dish-level menu items were extracted.")
    completed = job.model_copy(
        update={
            "status": "complete",
            "message": f"Captured {item_count} menu items; RAG indexing is continuing in the background.",
            "item_count": item_count,
            "source_url": source.source_url,
            "content_type": source.content_type,
            "extraction_method": source.extraction_method,
            "page_count": source.page_count,
            "extraction_confidence": source.extraction_confidence,
            "indexing_status": "pending",
            "completed_at": datetime.now(UTC).isoformat(),
            "trace": _upsert_trace(
                _upsert_trace(
                    _upsert_trace(
                        job.trace,
                        IngestionTraceStep(
                            id="deep_scan",
                            label="Run deeper menu scan",
                            status="complete",
                            detail="Background OCR and rendered extraction finished.",
                            provider="azure_functions",
                            item_count=item_count,
                        ),
                    ),
                    IngestionTraceStep(
                        id="menu_extracted",
                        label="Menu extracted",
                        status="complete",
                        detail=f"Published {item_count} dish-level menu items for immediate review.",
                        provider=source.extraction_method or "menu_ingestion",
                        item_count=item_count,
                    ),
                ),
                IngestionTraceStep(
                    id="search_index",
                    label="Index menu evidence",
                    status="pending",
                    detail="Menu extracted and published; the RAG index is updating.",
                    provider="azure_ai_search",
                    item_count=item_count,
                ),
            ),
        }
    )
    _save_job(completed)
    return finish_menu_index(completed, persist=_save_job)


def _new_job(message: MenuRefreshMessage) -> MenuRefreshJob:
    now = datetime.now(UTC).isoformat()
    return MenuRefreshJob(
        id=message.job_id,
        place_id=message.place_id,
        status="queued",
        message="Menu refresh is queued.",
        document_urls=message.document_urls,
        total_documents=len(message.document_urls),
        menu_version=message.menu_version,
        trace=[],
        created_at=now,
    )


def _transition(
    job: MenuRefreshJob,
    *,
    status: str,
    message: str,
    trace: IngestionTraceStep,
) -> MenuRefreshJob:
    updated = job.model_copy(
        update={"status": status, "message": message, "trace": _upsert_trace(job.trace, trace)}
    )
    _save_job(updated)
    return updated


def _save_job(job: MenuRefreshJob) -> None:
    supabase_store.save_menu_refresh_job(job)


def _upsert_trace(trace: list[IngestionTraceStep], step: IngestionTraceStep) -> list[IngestionTraceStep]:
    return [existing for existing in trace if existing.id != step.id] + [step]
