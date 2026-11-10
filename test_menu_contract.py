import json
import unittest
from unittest import mock

from api import menu


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload


class MenuContractTests(unittest.TestCase):
    def setUp(self):
        menu._menu_cache.clear()
        menu._token.update(val=None, t=0)
        menu._state["kk_down_until"] = 0

    def payload(self, products):
        group = {
            "background_color": 0,
            "group_code": "coffee",
            "group_name": "Coffee",
            "group_tab_url": "https://example.test/coffee",
            "has_combo": False,
            "layout_type": 1,
            "menu_products": products,
            "section_icon": "https://example.test/coffee.png",
            "show_promo_only": 0,
        }
        return {"error_code": 0, "data": {"menu_groups": [group]}, "msg": ""}

    def product(self, *, product_id=7, product_code="product-sku", **overrides):
        if product_code is None:
            product_code = None
        product = {
            "ActionUrl": "",
            "active_time": None,
            "available_end_timestamp": 0,
            "brand": "Brand",
            "bundle_code": "bundle",
            "delivery_restriction": 0,
            "description": "Description",
            "has_optional_group": False,
            "has_promotion": False,
            "id": product_id,
            "image": "https://example.test/product.jpg",
            "is_combo_v2": False,
            "is_mix_match": False,
            "is_restriction_customer": False,
            "is_sold_out": False,
            "labels": None,
            "limit_to_size": None,
            "limit_to_skus": None,
            "limit_to_temperature": None,
            "local_specific_days": None,
            "local_time_from": None,
            "local_time_to": None,
            "local_time_type": None,
            "name": "Product",
            "orig_price": 21000,
            "orig_price_dec": "21000.00",
            "price": 21000,
            "price_dec": "21000.00",
            "product_code": product_code,
            "product_type_id": 1,
            "skus": None,
            "type_code": 1,
            "veg_classification": 0,
        }
        product.update(overrides)
        return product

    def call_menu(self, products):
        menu._menu_cache.clear()
        menu._token.update(val=None, t=0)
        menu._state["kk_down_until"] = 0
        token = {"error_code": 0, "data": {"customer_name": "", "web_order_session_token": "synthetic-token"}, "msg": ""}
        with mock.patch.object(
            menu,
            "_request_json",
            side_effect=[token, self.payload(products), token, self.payload(products)],
        ):
            return menu.get_menu("STORE")

    def test_publishes_menu_product_sku(self):
        result = self.call_menu([self.product()])

        self.assertEqual(result["groups"][0]["products"][0]["sku"], "product-sku")

    def test_allows_identical_product_aliases(self):
        result = self.call_menu([self.product(), self.product()])

        self.assertEqual([p["sku"] for p in result["groups"][0]["products"]], ["product-sku"])

    def test_blank_or_missing_sku_keeps_product_with_null_sku(self):
        for overrides in [{"product_code": None}, {"product_code": ""}, {"product_code": "bad sku!"}]:
            with self.subTest(overrides=overrides):
                result = self.call_menu([self.product(**overrides)])
                self.assertIsNone(result["groups"][0]["products"][0]["sku"])

    def test_boundary_whitespace_sku_is_trimmed(self):
        result = self.call_menu([self.product(product_code=" product-sku ")])
        self.assertEqual(result["groups"][0]["products"][0]["sku"], "product-sku")

    def test_extra_upstream_fields_are_ignored(self):
        result = self.call_menu([self.product(brand_new_field={"x": 1})])
        self.assertEqual(result["total_items"], 1)

    def test_bad_product_is_skipped_not_fatal(self):
        bad = self.product(product_id=8, name="")
        result = self.call_menu([self.product(), bad])
        self.assertEqual(result["total_items"], 1)
        self.assertEqual(result["skipped_items"], 1)

    def test_empty_image_and_float_price_are_accepted(self):
        result = self.call_menu([self.product(image="", price=21000.0, orig_price="21000.00")])
        p = result["groups"][0]["products"][0]
        self.assertEqual((p["image"], p["price"], p["original_price"]), ("", 21000, 21000))

    def test_rejects_missing_product_id(self):
        product = self.product()
        del product["id"]

        self.assertIsNone(self.call_menu([product]))

    def test_rejects_boolean_menu_error_code(self):
        product = self.product()
        token = {"error_code": 0, "data": {"customer_name": "", "web_order_session_token": "synthetic-token"}, "msg": ""}
        payload = self.payload([product])
        payload["error_code"] = False
        with mock.patch.object(menu, "_request_json", side_effect=[token, payload, token, payload]):
            self.assertIsNone(menu.get_menu("STORE"))

    def test_rejects_invalid_product_id_types_and_forms(self):
        cases = [
            {"product_id": True},
            {"product_id": -1},
            {"product_id": ""},
            {"product_id": " 7"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertIsNone(self.call_menu([self.product(**overrides)]))

    def test_accepts_numeric_string_product_id(self):
        result = self.call_menu([self.product(product_id="7")])

        self.assertNotIn("error", result)
        self.assertEqual(result["groups"][0]["products"][0]["id"], "7")

    def test_conflicting_product_id_alias_keeps_first_only(self):
        products = [self.product(product_id=7, product_code="product-sku"), self.product(product_id=7, product_code="other-sku")]
        result = self.call_menu(products)
        self.assertEqual([p["sku"] for p in result["groups"][0]["products"]], ["product-sku"])

    def test_conflicting_sku_alias_keeps_first_only(self):
        products = [self.product(product_id=7, product_code="product-sku"), self.product(product_id=8, product_code="product-sku")]
        result = self.call_menu(products)
        self.assertEqual([p["id"] for p in result["groups"][0]["products"]], [7])


if __name__ == "__main__":
    unittest.main()
