import json
import unittest
from unittest import mock

from api import options


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload


class OptionsContractTests(unittest.TestCase):
    def setUp(self):
        options._opts_cache.clear()
        options._token.update(val=None, t=0)

    def option_payload(self, *, addon_group=None, variants=None, notes=None, dimension_groups=None):
        addon_group = addon_group or {
            "dimension_code": 42,
            "dimension_description": "Syrup choices",
            "dimension_text": "Syrup",
            "display_type": 1,
            "mandatory": False,
            "only_one": False,
            "dimension_value_wordings": [
                {
                    "addon_price": 7000,
                    "addon_price_dec": "7000.00",
                    "discount_amount_dec": None,
                    "icon": "",
                    "label": None,
                    "value": 1,
                    "value_description": "Choice A description",
                    "value_icon": "",
                    "value_text": "Choice A",
                    "addon_sku": "addon-sku-a",
                },
                {
                    "addon_price": 9000,
                    "addon_price_dec": "9000.00",
                    "discount_amount_dec": None,
                    "icon": "",
                    "label": None,
                    "value": 2,
                    "value_description": "Choice B description",
                    "value_icon": "",
                    "value_text": "Choice B",
                    "addon_sku": "addon-sku-b",
                },
            ],
        }
        variants = variants or {"combo": self.variant()}
        dimension_groups = [] if dimension_groups is None else dimension_groups
        data = {
            "attribution_flag": 0,
            "base_product": self.base_product(),
            "bottom_labels": None,
            "cover_images": None,
            "custom_title": "",
            "default_selection_addons": None,
            "default_selection_impact_sku": None,
            "default_selection_notes": None,
            "heart_point_aov": None,
            "inactive_reason": None,
            "is_sold_out": False,
            "labels": None,
            "middle_banners": None,
            "notes": notes,
            "option_product_map": variants,
            "product_addon_wording": {"addon_wordings": [addon_group]},
            "product_dimension_wording": {"bundle_id": 123, "dimension_wordings": dimension_groups},
            "spu_veg_classification": 0,
            "toast": "",
            "veg_classifications": None,
        }
        return {"error_code": 0, "data": data, "msg": ""}

    def base_product(self):
        return {
            "additional_price": "0.00",
            "base_sku": None,
            "bundle_code": "bundle",
            "category": None,
            "category_id": None,
            "combo_item_default_notes_map": None,
            "combo_item_id": None,
            "default_sku": None,
            "description": "Description",
            "discount_percentage": None,
            "group_id": None,
            "icon": "",
            "id": 123,
            "image": "https://example.test/product.jpg",
            "is_combo_item": None,
            "is_favorite": None,
            "is_soldout": None,
            "knowledge_image": None,
            "knowledge_title": None,
            "mix_match_item_discount": None,
            "mix_match_item_discount_dec": None,
            "name": "Product",
            "price": 21000,
            "price_dec": "21000.00",
            "type": "product",
            "type_code": 1,
            "veg_classification": 0,
        }

    def variant(self, **overrides):
        variant = {
            "addon_skus": ["addon-sku-b", "addon-sku-a"],
            "cover_image": None,
            "default_skus": None,
            "discount_amount": None,
            "discount_amount_dec": None,
            "discount_cashback": None,
            "discount_cashback_dec": None,
            "discount_item_number_limit": None,
            "display_description": "",
            "flash_sale_info": None,
            "label_info": None,
            "minimum_purchase": None,
            "name": "Variant",
            "price": 21000,
            "price_dec": "21000.00",
            "product_code": "variant-sku",
            "recommend_addons": None,
        }
        variant.update(overrides)
        return variant

    def call_options(self, payload):
        options._token.update(val=None, t=0)
        token = {"error_code": 0, "data": {"customer_name": "", "web_order_session_token": "synthetic-token"}, "msg": ""}
        with mock.patch("api.menu._request_json", return_value=token), mock.patch.object(options, "_request_json", return_value=payload):
            return options.get_options("STORE", "123")

    def test_accepts_nullable_live_base_skus_and_missing_option_lists(self):
        result = self.call_options(self.option_payload())
        self.assertNotIn("error", result)

    def test_rejects_unknown_option_data_field(self):
        payload = self.option_payload()
        payload["data"]["unexpected"] = False
        self.assertIn("error", self.call_options(payload))

    def test_returns_none_for_valid_empty_no_options_contract(self):
        payload = self.option_payload()
        payload["data"]["product_dimension_wording"]["dimension_wordings"] = None
        payload["data"]["product_addon_wording"]["addon_wordings"] = None
        payload["data"]["option_product_map"] = {}
        self.assertIsNone(self.call_options(payload))

    def test_returns_none_for_valid_single_variant_no_options_contract(self):
        payload = self.option_payload()
        payload["data"]["product_dimension_wording"]["dimension_wordings"] = None
        payload["data"]["product_addon_wording"]["addon_wordings"] = None
        payload["data"]["option_product_map"] = {"": self.variant(addon_skus=[])}
        self.assertIsNone(self.call_options(payload))

    def test_rejects_malformed_no_options_variant_map_before_returning_none(self):
        malformed_variant = self.variant(addon_skus=[])
        malformed_variant["price"] = "21000"
        extra_field_variant = self.variant(addon_skus=[])
        extra_field_variant["unexpected"] = False
        for variants in ({"": {}}, {"": self.variant(addon_skus=["unpublished"])}, {"unexpected": self.variant(addon_skus=[])}, {"": malformed_variant}, {"": extra_field_variant}):
            payload = self.option_payload()
            payload["data"]["product_dimension_wording"]["dimension_wordings"] = None
            payload["data"]["product_addon_wording"]["addon_wordings"] = None
            payload["data"]["option_product_map"] = variants
            with self.subTest(variants=variants):
                self.assertIn("error", self.call_options(payload))

    def test_rejects_boolean_options_error_code(self):
        payload = self.option_payload()
        payload["error_code"] = False
        self.assertIn("error", self.call_options(payload))

    def test_rejects_empty_variant_map_for_selectable_contract(self):
        payload = self.option_payload()
        payload["data"]["option_product_map"] = {}
        self.assertIn("error", self.call_options(payload))

    def test_rejects_conflicting_default_selection(self):
        payload = self.option_payload()
        payload["data"]["default_selection_impact_sku"] = {"wrong": "value"}
        self.assertIn("error", self.call_options(payload))

    def test_accepts_nullable_live_note_labels(self):
        note = {"check_type": "radio", "title": "Notes", "groups": [{
            "description": "Description", "display_type_code": 1, "display_value_texts": [], "invisible_when": {},
            "labels": None, "new_menu_option_url": "", "option_name": "Notes", "option_type": 1, "option_url": "",
            "select_value": 1, "value_descriptions": ["Description"], "value_images": ["https://example.test/note.jpg"],
            "value_texts": ["Value"], "values": [1],
        }]}
        result = self.call_options(self.option_payload(notes=[note]))
        self.assertEqual(result["notes"], [{"type": "radio", "name": "Notes", "values": {"1": "Value"}}])

    def test_accepts_empty_optional_note_display_metadata(self):
        note = {"check_type": "radio", "title": "Notes", "groups": [{
            "description": "", "display_type_code": 1, "display_value_texts": [], "invisible_when": {},
            "labels": None, "new_menu_option_url": "", "option_name": "Notes", "option_type": 1, "option_url": "",
            "select_value": 1, "value_descriptions": [""], "value_images": [""],
            "value_texts": ["Value"], "values": [1],
        }]}

        result = self.call_options(self.option_payload(notes=[note]))

        self.assertEqual(result["notes"], [{"type": "radio", "name": "Notes", "values": {"1": "Value"}}])

    def test_rejects_blank_required_note_name_or_value_text(self):
        for field, replacement in (("option_name", ""), ("value_texts", [""])):
            note = {"check_type": "radio", "title": "Notes", "groups": [{
                "description": "", "display_type_code": 1, "display_value_texts": [], "invisible_when": {},
                "labels": None, "new_menu_option_url": "", "option_name": "Notes", "option_type": 1, "option_url": "",
                "select_value": 1, "value_descriptions": [""], "value_images": [""],
                "value_texts": ["Value"], "values": [1],
            }]}
            note["groups"][0][field] = replacement

            with self.subTest(field=field):
                self.assertIn("error", self.call_options(self.option_payload(notes=[note])))

    def test_rejects_null_optional_note_display_metadata(self):
        for field in ("description", "value_descriptions", "value_images"):
            note = {"check_type": "radio", "title": "Notes", "groups": [{
                "description": "", "display_type_code": 1, "display_value_texts": [], "invisible_when": {},
                "labels": None, "new_menu_option_url": "", "option_name": "Notes", "option_type": 1, "option_url": "",
                "select_value": 1, "value_descriptions": [""], "value_images": [""],
                "value_texts": ["Value"], "values": [1],
            }]}
            note["groups"][0][field] = None if field == "description" else [None]

            with self.subTest(field=field):
                self.assertIn("error", self.call_options(self.option_payload(notes=[note])))


    def dimension_group(self, code, values):
        template = self.option_payload()["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0]
        return {
            "dimension_code": code,
            "dimension_description": "Dimension description",
            "dimension_text": code,
            "display_type": 1,
            "dimension_value_wordings": [
                {**template, "addon_price": None, "addon_price_dec": None, "discount_amount_dec": None,
                 "addon_sku": "", "value": value, "value_text": f"{code} {value}"}
                for value in values
            ],
        }

    def test_accepts_complete_multi_dimension_variant_matrix(self):
        dimensions = [self.dimension_group("size", ["s", "l"]), self.dimension_group("ice", ["n", "f"])]
        variants = {
            f"size-{size}:ice-{ice}:": self.variant(product_code=f"fixture-{size}-{ice}")
            for size in ("s", "l") for ice in ("n", "f")
        }
        payload = self.option_payload(dimension_groups=dimensions, variants=variants)
        payload["data"]["default_selection_impact_sku"] = {"size": "s", "ice": "n"}

        result = self.call_options(payload)

        self.assertEqual(set(result["variants"]), set(variants))
        self.assertEqual(len(result["variants"]), 4)

    def test_accepts_strict_nonempty_variant_subset_with_complete_dimension_coverage(self):
        dimensions = [self.dimension_group("size", ["s", "l"]), self.dimension_group("ice", ["n", "f"])]
        variants = {
            "size-s:ice-n:": self.variant(product_code="variant-s-n"),
            "size-l:ice-f:": self.variant(product_code="variant-l-f"),
        }
        payload = self.option_payload(dimension_groups=dimensions, variants=variants)
        payload["data"]["default_selection_impact_sku"] = {"size": "s", "ice": "n"}

        result = self.call_options(payload)

        self.assertNotIn("error", result)
        self.assertEqual(set(result["variants"]), set(variants))

    def test_rejects_uncovered_or_extra_multi_dimension_variant_combo(self):
        dimensions = [self.dimension_group("size", ["s", "l"]), self.dimension_group("ice", ["n", "f"])]
        complete = {
            f"size-{size}:ice-{ice}:": self.variant(product_code=f"fixture-{size}-{ice}")
            for size in ("s", "l") for ice in ("n", "f")
        }
        uncovered = {key: value for key, value in complete.items() if not key.startswith("size-l:")}
        cases = [uncovered, {**complete, "size-s:ice-x:": self.variant(product_code="fixture-extra")}]

        for variants in cases:
            with self.subTest(variant_keys=tuple(variants)):
                self.assertIn("error", self.call_options(self.option_payload(dimension_groups=dimensions, variants=variants)))

    def test_rejects_missing_default_published_combo(self):
        dimensions = [self.dimension_group("size", ["s", "l"]), self.dimension_group("ice", ["n", "f"])]
        variants = {
            "size-s:ice-n:": self.variant(product_code="fixture-s-n"),
            "size-l:ice-f:": self.variant(product_code="fixture-l-f"),
        }
        payload = self.option_payload(dimension_groups=dimensions, variants=variants)
        payload["data"]["default_selection_impact_sku"] = {"size": "s", "ice": "f"}

        self.assertIn("error", self.call_options(payload))

    def test_publishes_variant_sku_sorted_compatibility_and_addon_sku(self):
        result = self.call_options(self.option_payload())

        variant = result["variants"]["combo"]
        self.assertEqual(variant["sku"], "variant-sku")
        self.assertEqual(variant["addon_skus"], ["addon-sku-a", "addon-sku-b"])
        self.assertEqual(variant["addons"], 2)
        self.assertEqual(result["addons"][0]["values"][0]["sku"], "addon-sku-a")

    def test_publishes_addon_group_selection_booleans(self):
        result = self.call_options(self.option_payload())

        addon = result["addons"][0]
        self.assertIs(addon["mandatory"], False)
        self.assertIs(addon["only_one"], False)

    def test_rejects_missing_blank_boundary_whitespace_and_duplicate_variant_sku(self):
        cases = [
            {"combo": {"product_code": None, "addon_skus": []}},
            {"combo": {"product_code": "", "addon_skus": []}},
            {"combo": {"product_code": " variant-sku", "addon_skus": []}},
            {
                "a": {"product_code": "same-sku", "addon_skus": []},
                "b": {"product_code": "same-sku", "addon_skus": []},
            },
        ]
        for variants in cases:
            with self.subTest(variants=variants):
                result = self.call_options(self.option_payload(variants=variants))
                self.assertIn("error", result)

    def test_rejects_malformed_duplicate_and_unknown_addon_compatibility_sku(self):
        cases = [
            {"combo": {"product_code": "variant-sku", "addon_skus": [None]}},
            {"combo": {"product_code": "variant-sku", "addon_skus": [" addon-sku-a"]}},
            {"combo": {"product_code": "variant-sku", "addon_skus": ["addon-sku-a", "addon-sku-a"]}},
            {"combo": {"product_code": "variant-sku", "addon_skus": ["not-published"]}},
        ]
        for variants in cases:
            with self.subTest(variants=variants):
                result = self.call_options(self.option_payload(variants=variants))
                self.assertIn("error", result)

    def test_rejects_duplicate_or_malformed_published_addon_sku(self):
        duplicate = self.option_payload()
        duplicate["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][1]["addon_sku"] = "addon-sku-a"
        malformed = self.option_payload()
        malformed["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0]["addon_sku"] = " addon-sku-a"

        for payload in (duplicate, malformed):
            with self.subTest(payload=payload):
                self.assertIn("error", self.call_options(payload))

    def test_hides_upstream_exception_details(self):
        options._token.update(val=None, t=0)
        with mock.patch.object(options, "_request_json", side_effect=OSError("internal upstream detail")), mock.patch.object(options, "get_token", return_value="synthetic-token"):
            result = options.get_options("STORE", "123")

        self.assertEqual(result, {"error": "options unavailable"})

    def test_rejects_malformed_addon_wrapper(self):
        unknown = self.option_payload()
        unknown["data"]["product_addon_wording"]["unexpected"] = False
        missing = self.option_payload()
        del missing["data"]["product_addon_wording"]["addon_wordings"]

        for payload in (unknown, missing):
            with self.subTest(payload=payload):
                self.assertIn("error", self.call_options(payload))

    def test_rejects_addon_value_unknown_key(self):
        payload = self.option_payload()
        payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0]["unexpected"] = False

        self.assertIn("error", self.call_options(payload))

    def test_rejects_addon_group_unknown_key_and_non_boolean_or_missing_flags(self):
        unknown = self.option_payload()
        unknown["data"]["product_addon_wording"]["addon_wordings"][0]["unexpected"] = False
        wrong_type = self.option_payload()
        wrong_type["data"]["product_addon_wording"]["addon_wordings"][0]["mandatory"] = 0
        missing_flag = self.option_payload()
        del missing_flag["data"]["product_addon_wording"]["addon_wordings"][0]["only_one"]

        for payload in (unknown, wrong_type, missing_flag):
            with self.subTest(payload=payload):
                self.assertIn("error", self.call_options(payload))

    def test_rejects_missing_variant_compatibility_list_or_addon_sku(self):
        missing_list = self.option_payload()
        del missing_list["data"]["option_product_map"]["combo"]["addon_skus"]
        missing_sku = self.option_payload()
        del missing_sku["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0]["addon_sku"]

        for payload in (missing_list, missing_sku):
            with self.subTest(payload=payload):
                self.assertIn("error", self.call_options(payload))

    def test_rejects_variant_map_above_contract_bound(self):
        variants = {
            f"combo-{i}": {"product_code": f"variant-{i}", "addon_skus": []}
            for i in range(101)
        }

        self.assertIn("error", self.call_options(self.option_payload(variants=variants)))

    def test_rejects_duplicate_published_addon_sku_across_groups(self):
        payload = self.option_payload()
        second_group = json.loads(json.dumps(payload["data"]["product_addon_wording"]["addon_wordings"][0]))
        second_group["dimension_code"] = "second"
        payload["data"]["product_addon_wording"]["addon_wordings"].append(second_group)

        self.assertIn("error", self.call_options(payload))

    def test_rejects_addon_price_string(self):
        payload = self.option_payload()
        payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0]["addon_price"] = "7000"

        self.assertIn("error", self.call_options(payload))

    def test_rejects_addon_price_bool(self):
        payload = self.option_payload()
        payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0]["addon_price"] = True

        self.assertIn("error", self.call_options(payload))

    def test_rejects_blank_addon_value_text(self):
        payload = self.option_payload()
        payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0]["value_text"] = ""

        self.assertIn("error", self.call_options(payload))

    def test_rejects_duplicate_addon_value_id_within_group(self):
        payload = self.option_payload()
        values = payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"]
        values[1]["value"] = values[0]["value"]

        self.assertIn("error", self.call_options(payload))

    def test_rejects_blank_addon_group_code(self):
        payload = self.option_payload()
        payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_code"] = ""

        self.assertIn("error", self.call_options(payload))

    def test_rejects_variant_price_string(self):
        payload = self.option_payload()
        payload["data"]["option_product_map"]["combo"]["price"] = "21000"

        self.assertIn("error", self.call_options(payload))

    def test_rejects_variant_sold_out_string(self):
        payload = self.option_payload()
        payload["data"]["option_product_map"]["combo"]["is_sold_out"] = "false"

        self.assertIn("error", self.call_options(payload))

    def test_rejects_unknown_variant_field(self):
        payload = self.option_payload()
        payload["data"]["option_product_map"]["combo"]["unexpected"] = False

        self.assertIn("error", self.call_options(payload))

    def test_rejects_empty_addon_values(self):
        payload = self.option_payload()
        payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"] = []

        self.assertIn("error", self.call_options(payload))

    def test_rejects_addon_values_above_global_bound(self):
        payload = self.option_payload()
        groups = []
        for group_index in range(options._MAX_ADDON_GROUPS):
            group = json.loads(json.dumps(payload["data"]["product_addon_wording"]["addon_wordings"][0]))
            group["dimension_code"] = "group-" + str(group_index)
            group["dimension_value_wordings"] = group["dimension_value_wordings"][:1]
            group["dimension_value_wordings"][0]["addon_sku"] = "addon-" + str(group_index)
            groups.append(group)
        groups.append(json.loads(json.dumps(groups[0])))
        groups[-1]["dimension_code"] = "overflow"
        groups[-1]["dimension_value_wordings"][0]["addon_sku"] = "addon-overflow"
        payload["data"]["product_addon_wording"]["addon_wordings"] = groups

        self.assertIn("error", self.call_options(payload))

    def test_rejects_duplicate_group_code(self):
        payload = self.option_payload()
        second_group = json.loads(json.dumps(payload["data"]["product_addon_wording"]["addon_wordings"][0]))
        second_group["dimension_value_wordings"][0]["addon_sku"] = "addon-sku-c"
        payload["data"]["product_addon_wording"]["addon_wordings"].append(second_group)

        self.assertIn("error", self.call_options(payload))

    def test_rejects_noncanonical_addon_identifiers_and_sku(self):
        cases = []
        for field, value in (("value", ""), ("value", "choice a"), ("addon_sku", "addon/special"), ("addon_sku", "x" * 101)):
            payload = self.option_payload()
            payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0][field] = value
            cases.append(payload)

        for payload in cases:
            with self.subTest(payload=payload):
                self.assertIn("error", self.call_options(payload))

    def test_rejects_blank_group_name(self):
        payload = self.option_payload()
        payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_text"] = " \t"

        self.assertIn("error", self.call_options(payload))

    def test_rejects_negative_addon_price(self):
        payload = self.option_payload()
        payload["data"]["product_addon_wording"]["addon_wordings"][0]["dimension_value_wordings"][0]["addon_price"] = -1

        self.assertIn("error", self.call_options(payload))

    def test_rejects_blank_variant_map_key(self):
        payload = self.option_payload(variants={"": payload_variant()})

        self.assertIn("error", self.call_options(payload))

    def test_rejects_noncanonical_variant_sku(self):
        payload = self.option_payload()
        payload["data"]["option_product_map"]["combo"]["product_code"] = "variant sku"

        self.assertIn("error", self.call_options(payload))

    def test_rejects_blank_variant_name(self):
        payload = self.option_payload()
        payload["data"]["option_product_map"]["combo"]["name"] = ""

        self.assertIn("error", self.call_options(payload))

    def test_normalizes_null_variant_sold_out_to_false(self):
        payload = self.option_payload()
        payload["data"]["option_product_map"]["combo"]["is_sold_out"] = None

        result = self.call_options(payload)

        self.assertIs(result["variants"]["combo"]["sold_out"], False)

    def test_rejects_unknown_top_level_options_field(self):
        payload = self.option_payload()
        payload["data"]["unexpected"] = False

        self.assertIn("error", self.call_options(payload))

    def test_rejects_malformed_options_without_caching(self):
        payload = self.option_payload()
        payload["data"]["option_product_map"]["combo"]["price"] = "21000"

        self.assertIn("error", self.call_options(payload))
        self.assertEqual(options._opts_cache, {})

    def test_accepts_live_shaped_variant_allowlist(self):
        live_variant = {
            "addon_skus": [], "cover_image": None, "default_skus": [],
            "discount_amount": 0, "discount_amount_dec": "0.00",
            "discount_cashback": 0, "discount_cashback_dec": "0.00",
            "discount_item_number_limit": 0, "display_description": "",
            "flash_sale_info": None, "label_info": [], "minimum_purchase": 1,
            "name": "Variant", "price": 21000, "price_dec": "21000.00",
            "product_code": "variant-live", "recommend_addons": [],
        }
        result = self.call_options(self.option_payload(variants={"combo-live": live_variant}))

        self.assertNotIn("error", result)
        self.assertEqual(result["variants"]["combo-live"]["addons"], 0)


def payload_variant():
    return {
        "price": 21000,
        "name": "Variant",
        "is_sold_out": False,
        "product_code": "variant-sku",
        "addon_skus": [],
    }


if __name__ == "__main__":
    unittest.main()
