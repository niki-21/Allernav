from __future__ import annotations

import io
import unittest
from urllib import error
from unittest.mock import patch

from allernav_api import supabase_store
from allernav_api.models import MenuItem, MenuSection, MenuSource, SourceType


class SupabaseStoreTests(unittest.TestCase):
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

    def test_storage_diagnostics_checks_read_and_write_without_exposing_config(self) -> None:
        config = supabase_store.SupabaseConfig(
            url="https://example.supabase.co",
            service_role_key="secret-service-key",
        )
        with patch("allernav_api.supabase_store.get_supabase_config", return_value=config), patch(
            "allernav_api.supabase_store._request", side_effect=[[], {}, {}]
        ):
            diagnostics = supabase_store.storage_diagnostics()

        self.assertEqual(
            diagnostics,
            {
                "supabase_env_configured": True,
                "supabase_menu_records_read_ok": True,
                "supabase_menu_refresh_jobs_write_ok": True,
                "last_supabase_error": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
