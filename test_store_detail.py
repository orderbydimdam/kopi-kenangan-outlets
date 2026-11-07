import json
import unittest
from unittest import mock

from api import store_detail


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload


class CanonicalizeStoreTests(unittest.TestCase):
    def test_trims_name_without_mutating_input_or_dropping_fields(self):
        store = {"code": "A", "name": "  Outlet A  ", "is_open": True}
        original = store.copy()

        result = store_detail.canonicalize_store(store)

        self.assertEqual(result, {"code": "A", "name": "Outlet A", "is_open": True})
        self.assertIsNot(result, store)
        self.assertEqual(store, original)

    def test_rejects_missing_non_string_or_whitespace_only_name(self):
        for store in (
            {"code": "A"},
            {"code": "A", "name": None},
            {"code": "A", "name": 123},
            {"code": "A", "name": " \t\n"},
        ):
            with self.subTest(store=store):
                self.assertIsNone(store_detail.canonicalize_store(store))


class GetStoreLiveTests(unittest.TestCase):
    def test_live_response_is_canonicalized_and_cached(self):
        payload = {"error_code": 0, "data": {"code": "LIVE", "name": "  Live  "}}
        with mock.patch.object(
            store_detail.urllib.request,
            "urlopen",
            return_value=Response(json.dumps(payload).encode()),
        ):
            result = store_detail.get_store_live("LIVE")

        self.assertEqual(result, {"code": "LIVE", "name": "Live"})
        self.assertEqual(payload["data"]["name"], "  Live  ")
        self.assertEqual(store_detail._cache["LIVE"]["data"], result)

    def test_invalid_live_name_is_rejected(self):
        payload = {"error_code": 0, "data": {"code": "INVALID", "name": " \t"}}
        with mock.patch.object(
            store_detail.urllib.request,
            "urlopen",
            return_value=Response(json.dumps(payload).encode()),
        ):
            result = store_detail.get_store_live("INVALID")

        self.assertIsNone(result)

    def test_fallback_store_is_canonicalized(self):
        stores = [{"code": "FALLBACK", "name": "  Cached  ", "category": "Mall"}]
        with mock.patch.object(
            store_detail.urllib.request,
            "urlopen",
            side_effect=OSError("unavailable"),
        ), mock.patch.object(store_detail.os.path, "exists", return_value=True), mock.patch(
            "builtins.open", mock.mock_open(read_data=json.dumps(stores))
        ):
            result = store_detail.get_store_live("FALLBACK")

        self.assertEqual(result, {"code": "FALLBACK", "name": "Cached", "category": "Mall"})


if __name__ == "__main__":
    unittest.main()
