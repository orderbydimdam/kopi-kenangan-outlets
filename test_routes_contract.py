import io
import json
import unittest
from unittest import mock

from api import menu, options


class HandlerHarness:
    @staticmethod
    def call(handler_class, path, method="GET"):
        instance = handler_class.__new__(handler_class)
        instance.path = path
        instance.wfile = io.BytesIO()
        status = []
        headers = []
        instance.send_response = status.append
        instance.send_header = lambda key, value: headers.append((key, value))
        instance.end_headers = lambda: None
        getattr(instance, "do_" + method)()
        body = instance.wfile.getvalue()
        return status[0], headers, json.loads(body) if body else None


class RouteCompatibilityTests(unittest.TestCase):
    def test_menu_public_and_forwarded_paths_accept_only_path_parameters(self):
        result = {"store_code": "STORE", "total_items": 0}
        with mock.patch.object(menu, "get_menu", return_value=result) as get_menu:
            for path in ("/api/menu/STORE", "/api/menu.py/STORE"):
                with self.subTest(path=path):
                    status, headers, body = HandlerHarness.call(menu.handler, path)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, result)
            get_menu.assert_has_calls([mock.call("STORE"), mock.call("STORE")])

    def test_menu_rejects_query_and_malformed_forwarded_paths(self):
        with mock.patch.object(menu, "get_menu") as get_menu:
            for path in ("/api/menu/STORE?x=1", "/api/menu.py/STORE?x=1", "/api/menu/STORE/extra", "/api/menu.py?store=STORE"):
                with self.subTest(path=path):
                    status, _, body = HandlerHarness.call(menu.handler, path)
                    self.assertEqual(status, 400)
                    self.assertEqual(body, {"error": "invalid menu route"})
            get_menu.assert_not_called()

    def test_options_public_and_forwarded_paths_accept_only_path_parameters(self):
        result = {"store_code": "STORE", "product_id": "123", "variants": {}}
        with mock.patch.object(options, "get_options", return_value=result) as get_options:
            for path in ("/api/options/STORE/123", "/api/options.py/STORE/123"):
                with self.subTest(path=path):
                    status, _, body = HandlerHarness.call(options.handler, path)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, result)
            get_options.assert_has_calls([mock.call("STORE", "123"), mock.call("STORE", "123")])

    def test_options_rejects_query_and_backward_query_routes(self):
        with mock.patch.object(options, "get_options") as get_options:
            for path in (
                "/api/options/STORE/123?x=1",
                "/api/options.py/STORE/123?x=1",
                "/api/options?store=STORE&id=123",
                "/api/options.py?store=STORE&id=123",
                "/api/options/STORE/0123",
            ):
                with self.subTest(path=path):
                    status, _, body = HandlerHarness.call(options.handler, path)
                    self.assertEqual(status, 400)
                    self.assertEqual(body, {"error": "invalid options route"})
            get_options.assert_not_called()

    def test_menu_and_options_support_cors_options_requests(self):
        for handler_class in (menu.handler, options.handler):
            with self.subTest(handler=handler_class):
                status, headers, body = HandlerHarness.call(handler_class, "/api/placeholder", method="OPTIONS")
                self.assertEqual(status, 204)
                self.assertIsNone(body)
                self.assertIn(("Access-Control-Allow-Origin", "*"), headers)
                self.assertIn(("Access-Control-Allow-Methods", "GET,OPTIONS"), headers)

    def test_vercel_rewrites_public_paths_to_function_roots_without_suffix_forwarding(self):
        with open("vercel.json", encoding="utf-8") as handle:
            config = json.load(handle)
        rewrites = {item["source"]: item["destination"] for item in config["rewrites"]}
        self.assertEqual(rewrites["/api/menu/(.+)"], "/api/menu.py")
        self.assertEqual(rewrites["/api/options/(.+)"], "/api/options.py")


if __name__ == "__main__":
    unittest.main()
