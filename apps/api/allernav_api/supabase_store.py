from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from urllib import error, parse, request
from uuid import uuid4

from .models import MenuRefreshJob, MenuSource


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    service_role_key: str


_LAST_ERROR: str | None = None
_LAST_ERROR_DETAILS: dict[str, object] | None = None
_ERROR_LOCK = Lock()
LOGGER = logging.getLogger(__name__)


def get_supabase_config() -> SupabaseConfig | None:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return SupabaseConfig(url=url, service_role_key=key)


def configured() -> bool:
    return get_supabase_config() is not None


def last_error() -> str | None:
    with _ERROR_LOCK:
        return _LAST_ERROR


def last_error_details() -> dict[str, object] | None:
    with _ERROR_LOCK:
        return dict(_LAST_ERROR_DETAILS) if _LAST_ERROR_DETAILS else None


def _set_last_error(message: str | None, details: dict[str, object] | None = None) -> None:
    global _LAST_ERROR, _LAST_ERROR_DETAILS
    with _ERROR_LOCK:
        _LAST_ERROR = message
        _LAST_ERROR_DETAILS = dict(details) if details else None


def storage_diagnostics() -> dict[str, object]:
    _set_last_error(None)
    config = get_supabase_config()
    if not config:
        return {
            "supabase_env_configured": False,
            "menu_records_read_ok": False,
            "menu_refresh_jobs_insert_ok": False,
            "last_supabase_error": "Supabase environment variables are not configured.",
        }

    read_result = _request(
        config,
        "/rest/v1/menu_records",
        method="GET",
        query={"select": "restaurant_id", "limit": "1"},
    )
    read_ok = read_result is not None
    read_error = last_error_details() or last_error()

    now = datetime.now(UTC).isoformat()
    probe_id = str(uuid4())
    write_result = _request(
        config,
        "/rest/v1/menu_refresh_jobs",
        method="POST",
        body=[
            {
                "id": probe_id,
                "restaurant_id": "storage-diagnostic",
                "status": "complete",
                "message": "Storage diagnostic probe.",
                "processed_documents": 0,
                "total_documents": 0,
                "job_json": {},
                "created_at": now,
                "completed_at": now,
                "updated_at": now,
            }
        ],
        headers={"Prefer": "resolution=merge-duplicates", "Content-Type": "application/json"},
        query={"on_conflict": "id"},
    )
    write_ok = write_result is not None
    write_error = last_error_details() or last_error()
    if write_ok:
        _request(
            config,
            "/rest/v1/menu_refresh_jobs",
            method="DELETE",
            query={"id": f"eq.{probe_id}"},
        )

    diagnostic_error = write_error or read_error
    if isinstance(diagnostic_error, dict):
        _set_last_error(str(diagnostic_error.get("summary") or "Supabase storage diagnostic failed."), diagnostic_error)
    else:
        _set_last_error(diagnostic_error)
    return {
        "supabase_env_configured": True,
        "menu_records_read_ok": read_ok,
        "menu_refresh_jobs_insert_ok": write_ok,
        "last_supabase_error": diagnostic_error,
    }


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

    _set_last_error(None)
    try:
        with request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        summary, details = _sanitized_http_error(exc, response_text, config, path)
        _set_last_error(summary, details)
        LOGGER.warning("Supabase request failed: %s", json.dumps(details, ensure_ascii=True, sort_keys=True))
        return None
    except error.URLError as exc:
        _set_last_error(f"Supabase connection error: {_sanitize_text(str(exc.reason), config)}")
        return None
    except TimeoutError:
        _set_last_error("Supabase request timed out.")
        return None
    except ValueError as exc:
        _set_last_error(f"Supabase request configuration error: {_sanitize_text(str(exc), config)}")
        return None
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        _set_last_error("Supabase returned a response that was not valid JSON.")
        return None


def _sanitized_http_error(
    exc: error.HTTPError,
    response_text: str,
    config: SupabaseConfig,
    path: str,
) -> tuple[str, dict[str, object]]:
    details: list[str] = []
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        payload = None
    postgrest_code = payload.get("code") if isinstance(payload, dict) and isinstance(payload.get("code"), str) else None
    if isinstance(payload, dict):
        for key in ("code", "message", "details", "hint"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                details.append(value.strip())
    elif response_text.strip():
        details.append(response_text.strip())
    sanitized_body = _sanitize_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")) if payload is not None else response_text,
        config,
    )
    table_name = path.rstrip("/").split("/")[-1] or "unknown"
    suffix = f": {'; '.join(details)}" if details else ""
    summary = _sanitize_text(
        f"Supabase HTTP {exc.code} {exc.reason} | table={table_name} | path={path}"
        f" | code={postgrest_code or 'unknown'}{suffix}",
        config,
    )
    return summary, {
        "status_code": exc.code,
        "table_name": table_name,
        "request_path": path,
        "response_body": sanitized_body,
        "postgrest_code": postgrest_code,
        "summary": summary,
    }


def _sanitize_text(value: str, config: SupabaseConfig) -> str:
    sanitized = value.replace(config.service_role_key, "[redacted]")
    return " ".join(sanitized.split())[:500]
