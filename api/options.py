from http.server import BaseHTTPRequestHandler
import itertools
import json
import re
import time
import urllib.parse

from .menu import HEADERS, _STORE, _image, _price, _text, get_token
from .transport import IntegrationError, request_json

_token = __import__('api.menu', fromlist=['_token'])._token
_opts_cache = {}
_MAX_DIMENSIONS = 8
_MAX_DIMENSION_VALUES = 20
_MAX_NOTES = 20
_MAX_NOTE_VALUES = 50
_MAX_ADDON_GROUPS = 20
_MAX_ADDON_VALUES = 100
_MAX_VARIANTS = 100
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]+$")
_DATA_KEYS = {"attribution_flag", "base_product", "bottom_labels", "cover_images", "custom_title", "default_selection_addons", "default_selection_impact_sku", "default_selection_notes", "heart_point_aov", "inactive_reason", "is_sold_out", "labels", "middle_banners", "notes", "option_product_map", "product_addon_wording", "product_dimension_wording", "spu_veg_classification", "toast", "veg_classifications"}
_BASE_PRODUCT_KEYS = {"additional_price", "base_sku", "bundle_code", "category", "category_id", "combo_item_default_notes_map", "combo_item_id", "default_sku", "description", "discount_percentage", "group_id", "icon", "id", "image", "is_combo_item", "is_favorite", "is_soldout", "knowledge_image", "knowledge_title", "mix_match_item_discount", "mix_match_item_discount_dec", "name", "price", "price_dec", "type", "type_code", "veg_classification"}
_DIMENSION_WRAPPER_KEYS = {"bundle_id", "dimension_wordings"}
_DIMENSION_GROUP_KEYS = {"dimension_code", "dimension_description", "dimension_text", "dimension_value_wordings", "display_type"}
_ADDON_WRAPPER_KEYS = {"addon_wordings"}
_ADDON_GROUP_KEYS = {"dimension_code", "dimension_description", "dimension_text", "dimension_value_wordings", "display_type", "mandatory", "only_one"}
_ADDON_VALUE_KEYS = {"addon_price", "addon_price_dec", "addon_sku", "discount_amount_dec", "icon", "label", "value", "value_description", "value_icon", "value_text"}
_NOTE_KEYS = {"check_type", "groups", "title"}
_NOTE_GROUP_KEYS = {"description", "display_type_code", "display_value_texts", "invisible_when", "labels", "new_menu_option_url", "option_name", "option_type", "option_url", "select_value", "value_descriptions", "value_images", "value_texts", "values"}
_VARIANT_KEYS = {"addon_skus", "cover_image", "default_skus", "discount_amount", "discount_amount_dec", "discount_cashback", "discount_cashback_dec", "discount_item_number_limit", "display_description", "flash_sale_info", "is_sold_out", "label_info", "minimum_purchase", "name", "price", "price_dec", "product_code", "recommend_addons"}
_VARIANT_REQUIRED_KEYS = _VARIANT_KEYS - {"is_sold_out"}

def _request_json(path, payload, headers):
    return request_json(path, payload, headers)

def _invalid(message="invalid options contract"):
    raise ValueError(message)

def _exact_dict(value, keys):
    if type(value) is not dict or set(value) != keys: _invalid()
    return value

def _subset_dict(value, keys):
    if type(value) is not dict or not set(value).issubset(keys): _invalid()
    return value

def _identifier(value):
    if type(value) is int:
        if value < 0: _invalid()
        return value
    if type(value) is not str or not value or len(value) > 100 or not _IDENTIFIER.fullmatch(value): _invalid()
    return value

def _sku(value):
    if type(value) is not str or not value or len(value) > 100 or value != value.strip() or not _IDENTIFIER.fullmatch(value): _invalid()
    return value

def _dimension_sku(value):
    if value == "": return value
    return _sku(value)

def _nullable(value, checker):
    if value is not None: checker(value)
    return value

def _optional_text(value):
    if type(value) is str and value == "": return value
    return _text(value)

def _optional_image(value):
    if type(value) is str and value == "": return value
    return _image(value)

def _list(value, maximum, nonempty=False):
    if type(value) is not list or len(value) > maximum or (nonempty and not value): _invalid()
    return value

def _parse_base_product(raw, product_id):
    base = _exact_dict(raw, _BASE_PRODUCT_KEYS)
    if str(_identifier(base["id"])) != str(_identifier(product_id)): _invalid("options product binding mismatch")
    result = {"name": _text(base["name"]), "image": _image(base["image"], optional=True), "price": _price(base["price"])}
    _nullable(base["base_sku"], _sku); _nullable(base["default_sku"], _sku)
    return result

def _parse_dimension_values(values):
    _list(values, _MAX_DIMENSION_VALUES, nonempty=True); seen = set(); result = []
    for value in values:
        _exact_dict(value, _ADDON_VALUE_KEYS)
        if value["addon_price"] is not None or value["addon_price_dec"] is not None or value["discount_amount_dec"] is not None: _invalid()
        value_id = _identifier(value["value"]); key = str(value_id)
        if key in seen: _invalid()
        seen.add(key); _dimension_sku(value["addon_sku"])
        result.append({"id": value_id, "label": _text(value["value_text"])})
    return result

def _parse_dimensions(data):
    wrapper = data.get("product_dimension_wording")
    if wrapper is None: return []
    _exact_dict(wrapper, _DIMENSION_WRAPPER_KEYS)
    groups = wrapper["dimension_wordings"]
    if groups is None: return []
    _list(groups, _MAX_DIMENSIONS); result = []; codes = set()
    for group in groups:
        _exact_dict(group, _DIMENSION_GROUP_KEYS); code = _identifier(group["dimension_code"]); key = str(code)
        if key in codes: _invalid()
        codes.add(key); result.append({"code": code, "name": _text(group["dimension_text"]), "values": _parse_dimension_values(group["dimension_value_wordings"])})
    return result

def _parse_addons(data):
    wrapper = data.get("product_addon_wording")
    if wrapper is None: return [], set()
    _exact_dict(wrapper, _ADDON_WRAPPER_KEYS); groups_raw = wrapper["addon_wordings"]
    if groups_raw is None: return [], set()
    groups = _list(groups_raw, _MAX_ADDON_GROUPS); addons = []; published = set(); codes = set(); total = 0
    for group in groups:
        _subset_dict(group, _ADDON_GROUP_KEYS); required = {"dimension_code", "dimension_text", "mandatory", "only_one", "dimension_value_wordings"}
        if not required.issubset(group) or type(group["mandatory"]) is not bool or type(group["only_one"]) is not bool: _invalid()
        code = _identifier(group["dimension_code"]); key = str(code)
        if key in codes: _invalid()
        codes.add(key); values = _list(group["dimension_value_wordings"], _MAX_ADDON_VALUES, nonempty=True); total += len(values)
        if total > _MAX_ADDON_VALUES: _invalid()
        output = []; value_ids = set()
        for value in values:
            _exact_dict(value, _ADDON_VALUE_KEYS); _nullable(value["addon_price_dec"], _text); _nullable(value["discount_amount_dec"], _text)
            value_id = _identifier(value["value"]); value_key = str(value_id)
            if value_key in value_ids: _invalid()
            value_ids.add(value_key); label = _text(value["value_text"]); sku = _sku(value["addon_sku"]); price = _price(value["addon_price"])
            if sku in published: _invalid()
            published.add(sku); output.append({"id": value_id, "label": label, "price": price, "sku": sku})
        addons.append({"code": code, "name": _text(group["dimension_text"]), "mandatory": group["mandatory"], "only_one": group["only_one"], "values": output})
    return addons, published

def _parse_notes(data):
    raw = data.get("notes")
    if raw is None: return []
    result = []
    for note in _list(raw, _MAX_NOTES):
        _exact_dict(note, _NOTE_KEYS)
        if note["check_type"] != "radio" or type(note["title"]) is not str: _invalid()
        if note["groups"] is None: continue
        for group in _list(note["groups"], _MAX_NOTES):
            _exact_dict(group, _NOTE_GROUP_KEYS); _optional_text(group["description"]); values = _list(group["values"], _MAX_NOTE_VALUES); texts = _list(group["value_texts"], _MAX_NOTE_VALUES); descriptions = _list(group["value_descriptions"], _MAX_NOTE_VALUES); images = _list(group["value_images"], _MAX_NOTE_VALUES); labels = group["labels"]
            if labels is None: labels = [None] * len(values)
            else: _list(labels, _MAX_NOTE_VALUES)
            if not len(values) == len(texts) == len(descriptions) == len(images) == len(labels): _invalid()
            pairs = []; seen = set()
            for value, text, description, image, label in zip(values, texts, descriptions, images, labels):
                value_id = _identifier(value); key = str(value_id)
                if key in seen: _invalid()
                seen.add(key); _text(text); _optional_text(description); _optional_image(image); _nullable(label, _text); pairs.append((key, text))
            result.append({"type": "radio", "name": _text(group["option_name"]), "values": dict(pairs)})
    return result

def _combo_parts(key):
    if type(key) is not str or not key or not key.endswith(":"): _invalid("invalid variant key")
    parts = key[:-1].split(":")
    if any(not part or "-" not in part for part in parts): _invalid("invalid variant key")
    parsed = [(_identifier(part.split("-", 1)[0]), _identifier(part.split("-", 1)[1])) for part in parts]
    if len({str(code) for code, _ in parsed}) != len(parsed): _invalid("duplicate variant dimension")
    return parsed

def _parse_variants(data, dimensions, published, no_options=False):
    opm = data.get("option_product_map")
    if type(opm) is not dict or len(opm) > _MAX_VARIANTS: _invalid()
    if not opm:
        if dimensions: _invalid("incomplete variant matrix")
        return {}
    dimension_values = {str(dim["code"]): {str(v["id"]) for v in dim["values"]} for dim in dimensions}
    choices = []
    expected_count = 1
    for code, values in dimension_values.items():
        expected_count *= len(values)
        if expected_count > _MAX_VARIANTS: _invalid("variant matrix limit exceeded")
        choices.append([(code, value) for value in sorted(values)])
    expected = {":".join(f"{code}-{value}" for code, value in combination) + ":" for combination in itertools.product(*choices)} if dimensions else set()
    if dimensions and not set(opm).issubset(expected): _invalid("invalid variant matrix")
    if no_options and set(opm) != {""}: _invalid("invalid no-options variant map")
    if not no_options and not dimensions and len(opm) != 1: _invalid("invalid no-options variant map")
    result = {}; skus = set(); represented = {code: set() for code in dimension_values}
    for combo, value in opm.items():
        parsed = _combo_parts(combo) if dimensions else []
        if dimensions and (set(str(code) for code, _ in parsed) != set(dimension_values) or any(str(item) not in dimension_values[str(code)] for code, item in parsed)): _invalid()
        for code, item in parsed: represented[str(code)].add(str(item))
        if type(value) is not dict or set(value) not in (_VARIANT_REQUIRED_KEYS, _VARIANT_KEYS): _invalid()
        sku = _sku(value["product_code"])
        if sku in skus: _invalid()
        skus.add(sku); addon_skus = [_sku(item) for item in _list(value["addon_skus"], _MAX_ADDON_VALUES)]
        if len(set(addon_skus)) != len(addon_skus) or any(item not in published for item in addon_skus): _invalid()
        if value["default_skus"] is not None: [_sku(item) for item in _list(value["default_skus"], _MAX_DIMENSION_VALUES)]
        sold_out = value.get("is_sold_out")
        if sold_out is not None and type(sold_out) is not bool: _invalid()
        result[combo] = {"price": _price(value["price"]), "name": _text(value["name"]), "sold_out": bool(sold_out), "addons": len(addon_skus), "sku": sku, "addon_skus": sorted(addon_skus)}
    if dimensions and any(represented[code] != values for code, values in dimension_values.items()): _invalid("uncovered dimension value")
    selection = _default_selection(data, dimensions)
    if dimensions and selection is not None:
        default_combo = ":".join(f"{dim['code']}-{selection[str(dim['code'])]}" for dim in dimensions) + ":"
        if default_combo not in result: _invalid("default selection is not published")
    return result

def _default_selection(data, dimensions):
    selection = data.get("default_selection_impact_sku")
    if selection is None: return None
    if type(selection) is not dict or len(selection) > _MAX_DIMENSIONS: _invalid("invalid default selection")
    allowed = {str(dim["code"]): {str(item["id"]) for item in dim["values"]} for dim in dimensions}
    if set(selection) != set(allowed) or any(str(value) not in allowed[code] for code, value in selection.items()): _invalid("invalid default selection")
    return dict(selection)

def _parse_options(payload, store_code, product_id):
    if type(payload) is not dict or set(payload) != {"data", "error_code", "msg"} or type(payload["error_code"]) is not int or payload["error_code"] != 0 or type(payload["msg"]) is not str: _invalid()
    data = _exact_dict(payload["data"], _DATA_KEYS); sold_out = data["is_sold_out"]
    if type(sold_out) is not bool: _invalid()
    base = _parse_base_product(data["base_product"], product_id); dimensions = _parse_dimensions(data); addons, published = _parse_addons(data); _default_selection(data, dimensions); notes = _parse_notes(data); opm = data["option_product_map"]
    if type(opm) is not dict or len(opm) > _MAX_VARIANTS: _invalid()
    if not dimensions and not addons:
        _parse_variants(data, dimensions, published, no_options=True)
        return None
    if not opm: _invalid("incomplete variant matrix")
    variants = _parse_variants(data, dimensions, published)
    return {"store_code": store_code, "product_id": product_id, "name": base["name"], "image": base["image"], "base_price": base["price"], "prices": sorted({x["price"] for x in variants.values()}), "dimensions": dimensions, "addons": addons, "notes": notes, "default_selection": _default_selection(data, dimensions), "variants": variants, "is_sold_out": sold_out}

def get_options(store_code, product_id):
    if type(store_code) is not str or not _STORE.fullmatch(store_code) or type(product_id) is not str or not product_id.isdigit() or product_id != str(int(product_id)): return None
    now = time.time(); key = f"{store_code}:{product_id}"
    if key in _opts_cache and now - _opts_cache[key]["t"] < 600: return _opts_cache[key]["data"]
    try:
        result = _parse_options(_request_json("/product/get_web_order_product_options", json.dumps({"store_code": store_code, "product_id": int(product_id), "sales_type": 10401}).encode(), {**HEADERS, "Authorization": get_token()}), store_code, product_id)
    except (IntegrationError, OSError, ValueError, TypeError, KeyError): return {"error": "options unavailable"}
    if result is not None: _opts_cache[key] = {"data": result, "t": now}
    return result

def _route(path):
    prefix = "/api/options/"
    if path.startswith(prefix) and path.count("/") == 4: parts = path[len(prefix):].split("/")
    elif path.startswith("/api/options.py/") and path.count("/") == 4: parts = path[len("/api/options.py/"):].split("/")
    else: return None
    store_code, product_id = parts
    return (store_code, product_id) if _STORE.fullmatch(store_code) and product_id.isdigit() and product_id == str(int(product_id)) else None

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path); route = _route(parsed.path) if not parsed.query else None
        if route is None: body = json.dumps({"error": "invalid options route"}).encode(); self.send_response(400)
        else:
            opts = get_options(*route)
            if opts is None or "error" in opts: body = json.dumps({"error": "Options not available"}).encode(); self.send_response(404)
            else: body = json.dumps(opts, ensure_ascii=False).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json"); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Cache-Control", "public, s-maxage=600"); self.end_headers(); self.wfile.write(body)
    def log_message(self, format, *args): pass
