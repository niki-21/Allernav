from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib import error, parse, request

from .models import MenuSource


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
