import json
import os
import tempfile
import unittest
from unittest import mock

import refresh_stores


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def close(self):
        pass


class SequenceOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return Response(response)


def page(rows, total, last_page):
    return json.dumps({
        "data": rows,
        "meta": {"total": total, "last_page": last_page},
    }).encode()


def outlet(code, **overrides):
    value = {
        "code": code,
        "name": "Outlet " + str(code),
        "address": "Address " + str(code),
        "latitude": "-6.2",
        "longitude": "106.8",
        "is_open": True,
        "open_time": "08:00",
        "order_close_time": "22:00",
        "category": "Mall",
        "image_url": "https://example.test/image.jpg",
    }
    value.update(overrides)
    return value


class FetchValidationTests(unittest.TestCase):
    def assert_rejected_without_write(self, responses):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stores.json")
            original = b'{"keep": true}'
            with open(path, "wb") as handle:
                handle.write(original)
            opener = SequenceOpener(*responses)

            with self.assertRaises(refresh_stores.RefreshError):
                refresh_stores.refresh(path, opener=opener, sleeper=lambda _: None)

            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), original)

    def test_empty_first_page_is_rejected(self):
        self.assert_rejected_without_write([page([], 1, 1)])

    def test_source_exception_is_rejected_without_write(self):
        self.assert_rejected_without_write([OSError("source unavailable")])

    def test_non_json_page_is_rejected_without_write(self):
        self.assert_rejected_without_write([b"not json"])

    def test_malformed_metadata_is_rejected_without_write(self):
        payload = json.dumps({"data": [outlet("A")], "meta": {"total": "1", "last_page": 1}}).encode()
        self.assert_rejected_without_write([payload])

    def test_early_empty_page_is_rejected_without_write(self):
        self.assert_rejected_without_write([
            page([outlet("A")], 2, 3),
            page([], 2, 3),
        ])

    def test_changed_total_between_pages_is_rejected(self):
        self.assert_rejected_without_write([
            page([outlet("A")], 2, 2),
            page([outlet("B")], 3, 2),
        ])

    def test_changed_last_page_between_pages_is_rejected(self):
        self.assert_rejected_without_write([
            page([outlet("A")], 2, 2),
            page([outlet("B")], 2, 3),
        ])

    def test_duplicate_missing_and_blank_codes_are_rejected(self):
        cases = [
            [outlet("A"), outlet(" A ")],
            [outlet("A"), outlet(None)],
            [outlet("A"), outlet("   ")],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                with self.assertRaises(refresh_stores.RefreshError):
                    refresh_stores.fetch_all_stores(
                        SequenceOpener(page(rows, len(rows), 1)),
                        sleeper=lambda _: None,
                    )

    def test_complete_pages_succeed_with_exact_count(self):
        opener = SequenceOpener(
            page([outlet("A"), outlet("B")], 3, 2),
            page([outlet("C")], 3, 2),
        )
        rows = refresh_stores.fetch_all_stores(opener, sleeper=lambda _: None)
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["code"] for row in rows], ["A", "B", "C"])
        self.assertEqual(len(opener.urls), 2)


class ConvertTests(unittest.TestCase):
    def test_convert_trims_boundary_whitespace_from_name(self):
        rows = refresh_stores.convert([outlet("A", name="  Outlet A  ")])
        self.assertEqual(rows[0]["name"], "Outlet A")
        self.assertTrue(rows[0]["name"])

    def test_convert_rejects_whitespace_only_name(self):
        with self.assertRaises(refresh_stores.RefreshError):
            refresh_stores.convert([outlet("A", name=" \t\n")])

    def test_convert_retains_one_canonical_output_per_input(self):
        rows = refresh_stores.convert([outlet(" A "), outlet("B")])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["code"], "A")
        self.assertEqual(set(rows[0]), {
            "code", "name", "address", "latitude", "longitude", "is_open",
            "open", "close", "category", "image_url", "brand_and_image",
        })
        self.assertIsInstance(rows[0]["code"], str)
        self.assertIsInstance(rows[0]["name"], str)
        self.assertIsInstance(rows[0]["address"], str)
        self.assertIsInstance(rows[0]["latitude"], str)
        self.assertIsInstance(rows[0]["longitude"], str)
        self.assertIsInstance(rows[0]["is_open"], bool)
        self.assertIsInstance(rows[0]["open"], str)
        self.assertIsInstance(rows[0]["close"], str)
        self.assertIsInstance(rows[0]["category"], str)
        self.assertIsInstance(rows[0]["image_url"], str)
        self.assertIsInstance(rows[0]["brand_and_image"], list)

    def test_convert_rejects_bad_rows_instead_of_returning_partial_data(self):
        with self.assertRaises(refresh_stores.RefreshError):
            refresh_stores.convert([outlet("A"), {"code": "B"}])


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_write_preserves_existing_file_on_serialization_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stores.json")
            original = b'{"keep": true}'
            with open(path, "wb") as handle:
                handle.write(original)

            with self.assertRaises(TypeError):
                refresh_stores.write_stores_atomic([{"bad": object()}], path)

            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), original)
            self.assertEqual(os.listdir(directory), ["stores.json"])

    def test_atomic_write_preserves_existing_file_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stores.json")
            original = b'{"keep": true}'
            with open(path, "wb") as handle:
                handle.write(original)

            with mock.patch.object(refresh_stores.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    refresh_stores.write_stores_atomic([], path)

            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), original)
            self.assertEqual(os.listdir(directory), ["stores.json"])

    def test_atomic_write_replaces_file_only_after_complete_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "stores.json")
            refresh_stores.write_stores_atomic([{"code": "A"}], path)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), [{"code": "A"}])


if __name__ == "__main__":
    unittest.main()
