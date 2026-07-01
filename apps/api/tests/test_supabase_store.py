from __future__ import annotations

import io
import unittest
from urllib import error
from unittest.mock import patch
from uuid import UUID

from allernav_api import supabase_store
from allernav_api.models import MenuItem, MenuRefreshJob, MenuSection, MenuSource, SourceType


class SupabaseStoreTests(unittest.TestCase):
    def test_config_normalizes_supabase_rest_endpoint_to_project_url(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co/rest/v1/",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
            },
        ):
            config = supabase_store.get_supabase_config()

        self.assertIsNotNone(config)
        self.assertEqual(config.url, "https://example.supabase.co")

    def test_save_menu_source_persists_document_metadata(self) -> None:
        source = MenuSource(
            source_type=SourceType.OFFICIAL_MENU,
            source_url="https://example.com/menu.pdf",
            document_url="https://example.com/menu.pdf",
            content_type="application/pdf",
            extraction_method="azure_document_intelligence_read",
            page_count=3,
            extraction_confidence=0.88,
            raw_text="Normandie Crepe: apples and cream",
            sections=[
                MenuSection(
                    title="Crepes",
                    items=[MenuItem(name="Normandie Crepe", description="Apples and cream")],
                )
            ],
        )
        calls: list[dict] = []

        def fake_request(*args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            return {}

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
            },
        ), patch.object(supabase_store, "_request", side_effect=fake_request):
            saved = supabase_store.save_menu_source(
                restaurant_id="place-1",
                restaurant_name="Crepe House",
                source=source,
                status="complete",
            )

        self.assertTrue(saved)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["args"][1], "/rest/v1/menu_records")
        self.assertEqual(calls[1]["args"][1], "/rest/v1/menu_documents")
        self.assertEqual(calls[1]["kwargs"]["query"], {"on_conflict": "restaurant_id,document_url"})
        document_payload = calls[1]["kwargs"]["body"][0]
        self.assertEqual(document_payload["restaurant_id"], "place-1")
        self.assertEqual(document_payload["document_url"], "https://example.com/menu.pdf")
        self.assertEqual(document_payload["extraction_method"], "azure_document_intelligence_read")
        self.assertEqual(document_payload["page_count"], 3)
        self.assertEqual(document_payload["extraction_confidence"], 0.88)

    def test_request_captures_sanitized_http_error_details(self) -> None:
        config = supabase_store.SupabaseConfig(
            url="https://example.supabase.co",
            service_role_key="secret-service-key",
        )
        http_error = error.HTTPError(
            "https://example.supabase.co/rest/v1/menu_refresh_jobs",
            400,
            "Bad Request",
            {},
            io.BytesIO(
                b'{"code":"PGRST204","message":"Missing column job_json",'
                b'"details":"secret-service-key is not accepted"}'
            ),
        )
        with patch("allernav_api.supabase_store.request.urlopen", side_effect=http_error):
            result = supabase_store._request(config, "/rest/v1/menu_refresh_jobs", method="POST", body=[])

        self.assertIsNone(result)
        self.assertIn("Supabase HTTP 400", supabase_store.last_error() or "")
        self.assertIn("PGRST204", supabase_store.last_error() or "")
        self.assertNotIn("secret-service-key", supabase_store.last_error() or "")
        details = supabase_store.last_error_details()
        self.assertEqual(details["status_code"], 400)
        self.assertEqual(details["table_name"], "menu_refresh_jobs")
        self.assertEqual(details["request_path"], "/rest/v1/menu_refresh_jobs")
        self.assertEqual(details["postgrest_code"], "PGRST204")
        self.assertIn("Missing column job_json", str(details["response_body"]))
        self.assertNotIn("secret-service-key", str(details))

    def test_storage_diagnostics_checks_read_and_write_without_exposing_config(self) -> None:
        config = supabase_store.SupabaseConfig(
            url="https://example.supabase.co",
            service_role_key="secret-service-key",
        )
        calls: list[tuple[tuple, dict]] = []

        def fake_request(*args, **kwargs):
            calls.append((args, kwargs))
            return [] if kwargs["method"] == "GET" else {}

        with patch("allernav_api.supabase_store.get_supabase_config", return_value=config), patch(
            "allernav_api.supabase_store._request", side_effect=fake_request
        ):
            diagnostics = supabase_store.storage_diagnostics()

        self.assertEqual(
            diagnostics,
            {
                "supabase_env_configured": True,
                "menu_records_read_ok": True,
                "menu_refresh_jobs_insert_ok": True,
                "last_supabase_error": None,
            },
        )
        insert_payload = next(kwargs["body"][0] for _args, kwargs in calls if kwargs["method"] == "POST")
        self.assertEqual(str(UUID(insert_payload["id"])), insert_payload["id"])

    def test_menu_refresh_job_404_exposes_useful_postgrest_diagnostics(self) -> None:
        job = MenuRefreshJob(
            id="job-404",
            place_id="place-404",
            status="queued",
            message="Queued",
            created_at="2026-06-30T12:00:00+00:00",
        )
        http_error = error.HTTPError(
            "https://example.supabase.co/rest/v1/menu_refresh_jobs?on_conflict=id",
            404,
            "Not Found",
            {},
            io.BytesIO(b'{"code":"PGRST125","message":"Could not find the table menu_refresh_jobs"}'),
        )

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "secret-service-key",
            },
        ), patch("allernav_api.supabase_store.request.urlopen", side_effect=http_error):
            saved = supabase_store.save_menu_refresh_job(job)

        self.assertFalse(saved)
        details = supabase_store.last_error_details()
        self.assertEqual(details["status_code"], 404)
        self.assertEqual(details["table_name"], "menu_refresh_jobs")
        self.assertEqual(details["postgrest_code"], "PGRST125")
        self.assertIn("Could not find the table", str(details["response_body"]))
        self.assertNotIn("secret-service-key", str(details))


if __name__ == "__main__":
    unittest.main()
