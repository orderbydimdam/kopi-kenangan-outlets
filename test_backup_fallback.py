import os
import unittest
from unittest import mock

from api import menu
from api.transport import IntegrationError

KOPKEN_FORMAT = {
    "error_code": 0,
    "data": {"menu_groups": [{"group_code": "C", "group_name": "Coffee", "menu_products": [
        {"id": 1, "name": "Americano", "product_code": "A1", "price": 17000, "orig_price": 17000,
         "is_sold_out": False, "has_promotion": False, "image": ""},
        {"id": 2, "name": "Latte", "product_code": "L1", "price": 22000, "orig_price": 22000,
         "is_sold_out": True, "has_promotion": False, "image": ""}]}]},
}


class BackupFallbackTest(unittest.TestCase):
    def setUp(self):
        menu._menu_cache.clear()
        menu._last_error.clear()
        menu._token.update(val=None, t=0)
        menu._state["kk_down_until"] = 0

    def tearDown(self):
        menu._state["kk_down_until"] = 0
        menu._menu_cache.clear()
        menu._last_error.clear()

    def kopken_down(self):
        return mock.patch.object(menu, "_fetch_menu", side_effect=IntegrationError("upstream request failed: HTTP 404"))

    def test_backup_used_when_kopken_fails(self):
        with self.kopken_down(), mock.patch.dict(os.environ, {"JK_STORE_TOKEN": "tok"}), \
             mock.patch.object(menu, "request_json", return_value=KOPKEN_FORMAT) as rj:
            result = menu.get_menu("KK.X.Y")
        self.assertEqual(result["source"], "backup")
        self.assertEqual(result["total_items"], 2)
        self.assertEqual(result["available_items"], 1)
        args, kwargs = rj.call_args
        self.assertEqual(args[0], "/menu")
        self.assertEqual(kwargs["base_url"], menu.BACKUP_BASE)
        self.assertEqual(args[2]["x-store-token"], "tok")

    def test_backup_accepts_unwrapped_menu_groups(self):
        with self.kopken_down(), mock.patch.dict(os.environ, {"JK_STORE_TOKEN": "tok"}), \
             mock.patch.object(menu, "request_json", return_value=KOPKEN_FORMAT["data"]):
            self.assertEqual(menu.get_menu("KK.X.Y")["total_items"], 2)

    def test_no_token_reports_reason(self):
        with self.kopken_down(), mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(menu.get_menu("KK.X.Y"))
        self.assertIn("JK_STORE_TOKEN", menu.last_error("KK.X.Y"))
        self.assertIn("HTTP 404", menu.last_error("KK.X.Y"))

    def test_unknown_backup_format_lists_keys(self):
        with self.kopken_down(), mock.patch.dict(os.environ, {"JK_STORE_TOKEN": "tok"}), \
             mock.patch.object(menu, "request_json", return_value={"ok": True, "items": []}):
            self.assertIsNone(menu.get_menu("KK.X.Y"))
        self.assertIn("items", menu.last_error("KK.X.Y"))

    def test_kopken_skipped_for_5_minutes_after_failure(self):
        with self.kopken_down() as k, mock.patch.dict(os.environ, {"JK_STORE_TOKEN": "tok"}), \
             mock.patch.object(menu, "request_json", return_value=KOPKEN_FORMAT):
            menu.get_menu("KK.A.B")
            menu.get_menu("KK.C.D")
        self.assertEqual(k.call_count, 2)  # hanya outlet pertama mencoba Kopken (2 percobaan)


if __name__ == "__main__":
    unittest.main()
