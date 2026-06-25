from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.setup_azure_search_index import create_or_update_index, load_index_definition


class AzureSearchSetupTests(unittest.TestCase):
    def test_load_index_definition_uses_configured_index_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "index.json"
            path.write_text(json.dumps({"name": "placeholder", "fields": []}), encoding="utf-8")
            os.environ["AZURE_SEARCH_INDEX_NAME"] = "custom-index"

            payload = load_index_definition(path)

        os.environ.pop("AZURE_SEARCH_INDEX_NAME", None)
        self.assertEqual(payload["name"], "custom-index")

    def test_create_or_update_index_uses_put_without_network(self) -> None:
        os.environ["AZURE_SEARCH_ENDPOINT"] = "https://example.search.windows.net"
        os.environ["AZURE_SEARCH_API_KEY"] = "test-key"
        os.environ["AZURE_SEARCH_INDEX_NAME"] = "allernav-test"

        class FakeResponse:
            def __enter__(self):  # noqa: ANN204
                return self

            def __exit__(self, *_args):  # noqa: ANN204
                return False

            def read(self) -> bytes:
                return b'{"name":"allernav-test"}'

        captured = {}

        def fake_urlopen(req, timeout):  # noqa: ANN001, ANN202
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("scripts.setup_azure_search_index.request.urlopen", side_effect=fake_urlopen):
            response = create_or_update_index({"name": "allernav-test", "fields": []})

        os.environ.pop("AZURE_SEARCH_ENDPOINT", None)
        os.environ.pop("AZURE_SEARCH_API_KEY", None)
        os.environ.pop("AZURE_SEARCH_INDEX_NAME", None)

        self.assertEqual(response["name"], "allernav-test")
        self.assertEqual(captured["method"], "PUT")
        self.assertIn("/indexes/allernav-test", captured["url"])


if __name__ == "__main__":
    unittest.main()
