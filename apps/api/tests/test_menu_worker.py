from __future__ import annotations

import unittest
from unittest.mock import patch

from allernav_api.document_intelligence import DocumentExtraction
from allernav_api.menu_job_queue import MenuRefreshMessage
from allernav_api.menu_indexing import finish_menu_index
from allernav_api.menu_worker import process_menu_refresh_message
from allernav_api.models import MenuItem, MenuRefreshJob, MenuSection, MenuSource, SearchIndexResponse, SourceType


MESSAGE = MenuRefreshMessage(
    version=1,
    job_id="00000000-0000-0000-0000-000000000001",
    place_id="forever-thai",
    restaurant_name="Forever Thai",
    website_url="https://www.foreverthaibushwick.com/menu",
    document_urls=["https://images.example/page-1.jpg", "https://images.example/page-2.jpg"],
    menu_version="May 2026",
)


class MenuWorkerTests(unittest.TestCase):
    def test_processes_all_pages_before_storage_and_indexing(self) -> None:
        saved_jobs = []
        saved_sources = []

        def extractor(url: str) -> DocumentExtraction:
            return DocumentExtraction(
                content=f"CHICKEN SATAY - chicken with peanut sauce {url}",
                content_type="image/jpeg",
                extraction_method="azure_document_intelligence",
                page_count=1,
                confidence=0.9,
            )

        def normalizer(**kwargs):  # noqa: ANN003, ANN202
            return [
                MenuSection(
                    title=f"Page {kwargs['source_page']}",
                    items=[
                        MenuItem(
                            name=f"Chicken Satay {kwargs['source_page']}",
                            description="Chicken with peanut sauce",
                            source_page=kwargs["source_page"],
                            source_url=kwargs["source_url"],
                            ocr_confidence=kwargs["ocr_confidence"],
                        )
                    ],
                )
            ]

        with patch("allernav_api.menu_worker.supabase_store.load_menu_refresh_job", return_value=None), patch(
            "allernav_api.menu_worker.supabase_store.load_menu_document_pages", return_value={}
        ), patch(
            "allernav_api.menu_worker.supabase_store.save_menu_document_page", return_value=True
        ), patch(
            "allernav_api.menu_worker.supabase_store.save_menu_refresh_job",
            side_effect=lambda job: saved_jobs.append(job) or True,
        ), patch(
            "allernav_api.menu_worker.save_menu_source",
            side_effect=lambda **kwargs: saved_sources.append(kwargs["source"]) or True,
        ), patch(
            "allernav_api.menu_indexing.index_restaurant_menu",
            return_value=SearchIndexResponse(
                restaurant_id="forever-thai", indexed_documents=2, status="indexed"
            ),
        ):
            job = process_menu_refresh_message(MESSAGE, extractor=extractor, normalizer=normalizer)

        self.assertEqual(job.status, "complete")
        self.assertEqual(job.processed_documents, 2)
        self.assertEqual(job.item_count, 2)
        self.assertEqual(saved_sources[0].menu_version, "May 2026")
        self.assertEqual(saved_sources[0].document_urls, MESSAGE.document_urls)
        self.assertEqual(saved_jobs[-1].status, "complete")
        self.assertEqual(saved_jobs[-1].indexing_status, "complete")
        pending_jobs = [job for job in saved_jobs if job.indexing_status == "pending"]
        self.assertEqual(len(pending_jobs), 1)
        self.assertEqual(pending_jobs[0].status, "complete")
        self.assertEqual(pending_jobs[0].trace[-1].status, "pending")

    def test_partial_ocr_failure_is_retried_and_not_published(self) -> None:
        saved_jobs = []

        with patch("allernav_api.menu_worker.supabase_store.load_menu_refresh_job", return_value=None), patch(
            "allernav_api.menu_worker.supabase_store.load_menu_document_pages", return_value={}
        ), patch(
            "allernav_api.menu_worker.supabase_store.save_menu_document_page", return_value=True
        ), patch(
            "allernav_api.menu_worker.supabase_store.save_menu_refresh_job",
            side_effect=lambda job: saved_jobs.append(job) or True,
        ):
            with self.assertRaises(RuntimeError):
                process_menu_refresh_message(MESSAGE, attempt=3, extractor=lambda _url: None)

        self.assertEqual(saved_jobs[-1].status, "failed")
        self.assertIn("after 3 attempts", saved_jobs[-1].message)

    def test_index_failure_keeps_published_menu_complete(self) -> None:
        job = MenuRefreshJob(
            id=MESSAGE.job_id,
            place_id=MESSAGE.place_id,
            status="complete",
            message="Menu extracted.",
            item_count=2,
            indexing_status="pending",
            created_at="2026-06-29T00:00:00+00:00",
            completed_at="2026-06-29T00:00:01+00:00",
        )

        saved_jobs = []
        result = finish_menu_index(
            job,
            persist=saved_jobs.append,
            indexer=lambda _place_id: (_ for _ in ()).throw(RuntimeError("Azure unavailable")),
        )

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.indexing_status, "failed")
        self.assertIn("menu remains available", result.message)
        self.assertEqual(result.trace[-1].status, "failed")

    def test_discovery_worker_runs_deep_scan_after_fast_menu_publish(self) -> None:
        message = MenuRefreshMessage(
            version=MESSAGE.version,
            job_id=MESSAGE.job_id,
            place_id=MESSAGE.place_id,
            restaurant_name=MESSAGE.restaurant_name,
            website_url=MESSAGE.website_url,
            document_urls=[],
            menu_version=MESSAGE.menu_version,
        )
        existing = MenuRefreshJob(
            id=message.job_id,
            place_id=message.place_id,
            status="deep_scanning",
            message="Menu found; deeper scan is running.",
            item_count=1,
            indexing_status="pending",
            created_at="2026-06-29T00:00:00+00:00",
        )
        source = MenuSource(
            source_type=SourceType.RESTAURANT_WEBSITE,
            source_url=message.website_url,
            reliability=0.9,
            sections=[MenuSection(title="Dinner", items=[MenuItem(name="Rice Bowl")])],
        )

        with patch("allernav_api.menu_worker.supabase_store.load_menu_refresh_job", return_value=existing), patch(
            "allernav_api.menu_worker.supabase_store.save_menu_refresh_job", return_value=True
        ), patch(
            "allernav_api.menu_worker.ingest_menu_from_website", return_value=source
        ) as ingest, patch(
            "allernav_api.menu_worker.finish_menu_index", side_effect=lambda job, persist: job
        ):
            result = process_menu_refresh_message(message)

        self.assertEqual(result.status, "complete")
        self.assertTrue(ingest.call_args.kwargs["deep_scan"])
        self.assertEqual(next(step for step in result.trace if step.id == "deep_scan").status, "complete")


if __name__ == "__main__":
    unittest.main()
