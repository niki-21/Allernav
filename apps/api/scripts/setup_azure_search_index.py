from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib import error, request


def search_api_version() -> str:
    return os.getenv("AZURE_SEARCH_API_VERSION", "2026-04-01")


def index_name() -> str:
    return os.getenv("AZURE_SEARCH_INDEX_NAME", "allernav-menu-evidence")


def index_definition_path() -> Path:
    return Path(__file__).resolve().parents[1] / "azure_search_index.json"


def load_index_definition(path: Path | None = None) -> dict[str, object]:
    definition_path = path or index_definition_path()
    payload = json.loads(definition_path.read_text(encoding="utf-8"))
    payload["name"] = index_name()
    return payload


def create_or_update_index(payload: dict[str, object]) -> dict[str, object]:
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").rstrip("/")
    api_key = os.getenv("AZURE_SEARCH_API_KEY", "")
    if not endpoint or not api_key:
        raise RuntimeError("Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY before creating the index.")

    url = f"{endpoint}/indexes/{index_name()}?api-version={search_api_version()}"
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), method="PUT")
    req.add_header("api-key", api_key)
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Azure AI Search index setup failed: {exc.code} {detail}") from exc
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Azure AI Search index setup failed.") from exc


def main() -> int:
    payload = load_index_definition()
    create_or_update_index(payload)
    print(f"Created or updated Azure AI Search index: {payload['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
