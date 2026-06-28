from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib import error, parse, request

from .models import MenuRefreshJob, MenuSource


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    service_role_key: str


def get_supabase_config() -> SupabaseConfig | None:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    return SupabaseConfig(url=url, service_role_key=key)


def configured() -> bool:
    return get_supabase_config() is not None


def save_menu_source(
    *,
    restaurant_id: str,
    restaurant_name: str | None,
    source: MenuSource,
    status: str,
    error_message: str | None = None,
) -> bool:
    config = get_supabase_config()
    if not config:
        return False

    payload = {
        "restaurant_id": restaurant_id,
        "restaurant_name": restaurant_name,
        "source_url": source.source_url,
        "source_type": source.source_type.value,
        "fetched_at": source.source_timestamp,
        "status": status,
        "error": error_message,
        "raw_text": source.raw_text,
        "menu_json": source.model_dump(mode="json"),
    }
    response = _request(
        config,
        "/rest/v1/menu_records",
        method="POST",
        body=[payload],
        headers={
            "Prefer": "resolution=merge-duplicates",
            "Content-Type": "application/json",
        },
        query={"on_conflict": "restaurant_id"},
    )
    if response is None:
        return False
    if source.document_url:
        save_menu_document(config=config, restaurant_id=restaurant_id, source=source)
    return True


def save_menu_document(*, config: SupabaseConfig, restaurant_id: str, source: MenuSource) -> bool:
    if not source.document_url:
        return False
    payload = {
        "restaurant_id": restaurant_id,
        "document_url": source.document_url,
        "content_type": source.content_type,
        "extraction_method": source.extraction_method,
        "page_count": source.page_count,
        "extraction_confidence": source.extraction_confidence,
        "raw_text": source.raw_text,
    }
    response = _request(
        config,
        "/rest/v1/menu_documents",
        method="POST",
        body=[payload],
        headers={
            "Prefer": "resolution=merge-duplicates",
            "Content-Type": "application/json",
        },
        query={"on_conflict": "restaurant_id,document_url"},
    )
    return response is not None


def load_menu_source(restaurant_id: str) -> tuple[str | None, MenuSource] | None:
    config = get_supabase_config()
    if not config:
        return None

    payload = _request(
        config,
        "/rest/v1/menu_records",
        method="GET",
        query={
            "restaurant_id": f"eq.{restaurant_id}",
            "status": "eq.complete",
            "select": "restaurant_name,menu_json",
            "limit": "1",
        },
    )
    if not isinstance(payload, list) or not payload:
        return None

    row = payload[0]
    if not isinstance(row, dict) or not isinstance(row.get("menu_json"), dict):
        return None
    return row.get("restaurant_name"), MenuSource.model_validate(row["menu_json"])


def save_menu_refresh_job(job: MenuRefreshJob) -> bool:
    config = get_supabase_config()
    if not config:
        return False
    payload = {
        "id": job.id,
        "restaurant_id": job.place_id,
        "status": job.status,
        "message": job.message,
        "processed_documents": job.processed_documents,
        "total_documents": job.total_documents,
        "job_json": job.model_dump(mode="json"),
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    response = _request(
        config,
        "/rest/v1/menu_refresh_jobs",
        method="POST",
        body=[payload],
        headers={"Prefer": "resolution=merge-duplicates", "Content-Type": "application/json"},
        query={"on_conflict": "id"},
    )
    return response is not None


def load_menu_refresh_job(job_id: str) -> MenuRefreshJob | None:
    config = get_supabase_config()
    if not config:
        return None
    payload = _request(
        config,
        "/rest/v1/menu_refresh_jobs",
        method="GET",
        query={"id": f"eq.{job_id}", "select": "job_json", "limit": "1"},
    )
    if not isinstance(payload, list) or not payload:
        return None
    value = payload[0].get("job_json") if isinstance(payload[0], dict) else None
    return MenuRefreshJob.model_validate(value) if isinstance(value, dict) else None


def save_menu_document_page(
    *,
    job_id: str,
    restaurant_id: str,
    document_url: str,
    page_number: int,
    status: str,
    raw_text: str | None = None,
    extraction_confidence: float | None = None,
    error_message: str | None = None,
) -> bool:
    config = get_supabase_config()
    if not config:
        return False
    payload = {
        "job_id": job_id,
        "restaurant_id": restaurant_id,
        "document_url": document_url,
        "page_number": page_number,
        "status": status,
        "raw_text": raw_text,
        "extraction_confidence": extraction_confidence,
        "error": error_message,
    }
    response = _request(
        config,
        "/rest/v1/menu_document_pages",
        method="POST",
        body=[payload],
        headers={"Prefer": "resolution=merge-duplicates", "Content-Type": "application/json"},
        query={"on_conflict": "job_id,document_url"},
    )
    return response is not None


def load_menu_document_pages(job_id: str) -> dict[str, dict[str, object]]:
    config = get_supabase_config()
    if not config:
        return {}
    payload = _request(
        config,
        "/rest/v1/menu_document_pages",
        method="GET",
        query={
            "job_id": f"eq.{job_id}",
            "select": "document_url,page_number,status,raw_text,extraction_confidence,error",
        },
    )
    if not isinstance(payload, list):
        return {}
    return {
        str(row["document_url"]): row
        for row in payload
        if isinstance(row, dict) and isinstance(row.get("document_url"), str)
    }


def _request(
    config: SupabaseConfig,
    path: str,
    *,
    method: str,
    body: object | None = None,
    headers: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
) -> object | None:
    query_string = f"?{parse.urlencode(query)}" if query else ""
    url = f"{config.url}{path}{query_string}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = request.Request(url, data=data, method=method)
    req.add_header("apikey", config.service_role_key)
    req.add_header("Authorization", f"Bearer {config.service_role_key}")
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)

    try:
        with request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except (error.HTTPError, error.URLError, TimeoutError, ValueError):
        return None
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
