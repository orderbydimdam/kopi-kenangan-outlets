from http.server import BaseHTTPRequestHandler
import json
import os
import re
import time
import urllib.parse

from .transport import BASE, IntegrationError, MAX_BODY_BYTES, REQUEST_TIMEOUT, _open, request_json

HEADERS = {"Content-Type": "application/json", "language": "id", "time_zone": "7"}
_token = {"val": None, "t": 0}
_menu_cache = {}
_MAX_GROUPS = 100
_MAX_PRODUCTS = 200
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]+$")
_URL = re.compile(r"^https://[^/?#]+(?:/[^?#]*)?(?:\?[^#]*)?$")
_STORE = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
_MAX_TOTAL = 1000  # batas pengaman; lewat dari ini dipotong, BUKAN menggagalkan seluruh menu


def _request_json(path, payload, headers):
    return request_json(path, payload, headers)


def _invalid(message="invalid menu contract"):
    raise ValueError(message)


def _loose_text(value, max_length=300):
    if type(value) is not str:
        _invalid()
    value = value.strip()
    if not value or len(value) > max_length:
        _invalid()
    return value


def _identifier(value):
    if type(value) is int:
        if value < 0:
            _invalid()
        return value
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        _invalid()
    return value


def _sku(value):
    """SKU opsional: kalau kosong/aneh produk tetap dipakai (sku=None), tidak dibuang."""
    if type(value) is not str:
        return None
    value = value.strip()
    if not value or len(value) > 100 or not _IDENTIFIER.fullmatch(value):
        return None
    return value


def _loose_price(value):
    # Kopken kadang kirim 21000, 21000.0, atau "21000.00".
    if type(value) is bool or value is None:
        _invalid()
    try:
        number = float(value)
    except (TypeError, ValueError):
        _invalid()
    if number != number or number < 0 or number > 10_000_000:
        _invalid()
    return int(round(number))


def _loose_image(value):
    if type(value) is not str:
        return ""
    value = value.strip()
    if not value or not _URL.fullmatch(value):
        return ""
    return value.split("?", 1)[0]



# Helper ketat di bawah ini dipakai api/options.py (kontrak opsi produk). Jangan dipakai parser menu.
def _text(value, max_length=300):
    if type(value) is not str or not value or len(value) > max_length or value != value.strip():
        _invalid()
    return value


def _price(value):
    if type(value) is not int or value < 0:
        _invalid()
    return value


def _image(value, optional=False):
    if value is None and optional:
        return ""
    if type(value) is not str or not value or value != value.strip() or not _URL.fullmatch(value):
        _invalid()
    return value.split("?", 1)[0]


def _flag(value):
    return value is True or value == 1


def _product(raw):
    if type(raw) is not dict:
        _invalid()
    product_id = _identifier(raw["id"])
    name = _loose_text(raw["name"])
    price = _loose_price(raw["price"])
    original_price = _loose_price(raw["orig_price"]) if raw.get("orig_price") is not None else price
    sold_out = _flag(raw.get("is_sold_out"))
    return {
        "id": product_id,
        "sku": _sku(raw.get("product_code")),
        "name": name,
        "price": price,
        "original_price": original_price,
        "available": not sold_out,
        "has_promo": _flag(raw.get("has_promotion")),
        "image": _loose_image(raw.get("image")),
    }


def _fields(p):
    return (str(p["id"]), p["sku"], p["name"], p["price"], p["original_price"], p["available"], p["has_promo"], p["image"])


def _parse_menu(payload, code):
    """Toleran: field tambahan diabaikan, produk rusak dilewati satu per satu.
    Hanya gagal kalau amplop respons salah atau tidak ada satu pun produk valid."""
    if type(payload) is not dict:
        _invalid("payload bukan object")
    err = payload.get("error_code")
    if type(err) is not int or err != 0:
        _invalid("error_code upstream: %r" % (err,))
    data = payload.get("data")
    if type(data) is not dict:
        _invalid("data kosong")
    groups_raw = data.get("menu_groups")
    if type(groups_raw) is not list or not groups_raw:
        _invalid("menu_groups kosong")

    groups, seen_id, seen_sku = [], {}, {}
    total = skipped = 0
    for group_raw in groups_raw[:_MAX_GROUPS]:
        if type(group_raw) is not dict or type(group_raw.get("menu_products")) is not list:
            continue
        try:
            group_name = _loose_text(group_raw.get("group_name"))
        except ValueError:
            group_name = "Menu"
        group_code = group_raw.get("group_code")
        group_code = group_code.strip() if type(group_code) is str and group_code.strip() else group_name
        products = []
        for product_raw in group_raw["menu_products"]:
            if total >= _MAX_TOTAL:
                break
            try:
                product = _product(product_raw)
            except (ValueError, KeyError, TypeError):
                skipped += 1
                continue
            identity, fields = str(product["id"]), _fields(product)
            if identity in seen_id:
                if seen_id[identity] != fields:
                    skipped += 1
                continue
            if product["sku"] is not None and product["sku"] in seen_sku and seen_sku[product["sku"]] != identity:
                skipped += 1
                continue
            seen_id[identity] = fields
            if product["sku"] is not None:
                seen_sku[product["sku"]] = identity
            products.append(product)
            total += 1
        if products:
            groups.append({"group_code": group_code, "group_name": group_name, "products": products})
    if total == 0:
        _invalid("tidak ada produk valid")
    return {
        "store_code": code,
        "total_items": total,
        "available_items": sum(1 for g in groups for p in g["products"] if p["available"]),
        "skipped_items": skipped,
        "groups": groups,
    }


def get_token():
    if _token["val"] is not None and time.time() - _token["t"] < 600:
        return _token["val"]
    payload = _request_json("/create_web_token", json.dumps({"phone": "6281200000000"}).encode(), HEADERS)
    try:
        if type(payload) is not dict or type(payload.get("error_code")) is not int or payload["error_code"] != 0:
            raise IntegrationError("invalid token response")
        token = payload["data"]["web_order_session_token"]
    except (KeyError, TypeError):
        raise IntegrationError("invalid token response")
    if type(token) is not str or not token.strip() or len(token) > 2000:
        raise IntegrationError("invalid token response")
    token = token.strip()
    _token.update(val=token, t=time.time())
    return token


_last_error = {}


def last_error(code):
    return _last_error.get(code, "unknown")


def _fetch_menu(code):
    return _parse_menu(
        _request_json("/product/query_web_order_product_menu", json.dumps({"store_code": code, "sales_type": 10401}).encode(), {**HEADERS, "Authorization": get_token()}),
        code,
    )


# ---- Cadangan: juragankopi (POST /api/kk/menu, header x-store-token) ----
# Token disimpan di environment variable Vercel JK_STORE_TOKEN. JANGAN ditulis di kode / frontend.
BACKUP_BASE = os.environ.get("JK_BASE", "https://juragankopi.my.id/api/kk")
_state = {"kk_down_until": 0}


def _unwrap(payload):
    """Backup bisa mengirim format Kopken apa adanya, atau dibungkus satu level lagi."""
    if type(payload) is dict and "menu_groups" in payload:
        return {"error_code": 0, "data": payload}
    if type(payload) is dict and type(payload.get("data")) is dict and "menu_groups" in payload["data"] and "error_code" not in payload:
        return {"error_code": 0, "data": payload["data"]}
    if type(payload) is dict and type(payload.get("result")) is dict:
        return _unwrap(payload["result"])
    return payload


def _fetch_backup(code):
    token = os.environ.get("JK_STORE_TOKEN", "").strip()
    if not token:
        raise IntegrationError("backup tidak aktif: JK_STORE_TOKEN belum diisi")
    payload = request_json(
        "/menu",
        json.dumps({"store_code": code}).encode(),
        {"Content-Type": "application/json", "x-store-token": token},
        base_url=BACKUP_BASE,
    )
    try:
        menu = _parse_menu(_unwrap(payload), code)
    except ValueError as exc:
        keys = sorted(payload.keys())[:8] if type(payload) is dict else type(payload).__name__
        raise IntegrationError("backup format tak dikenal (%s): %s" % (keys, exc))
    menu["source"] = "backup"
    return menu


def _try_kopken(code):
    last = None
    for attempt in range(2):
        try:
            return _fetch_menu(code)
        except (IntegrationError, ValueError, TypeError, KeyError) as exc:
            last = "%s: %s" % (type(exc).__name__, exc)
            _token.update(val=None, t=0)  # token mungkin kedaluwarsa: ambil baru lalu coba lagi
    raise IntegrationError(last)


def get_menu(code):
    if type(code) is not str or not _STORE.fullmatch(code):
        return None
    now = time.time()
    cached = _menu_cache.get(code)
    if cached and now - cached["t"] < cached.get("ttl", 300):
        return cached["data"]

    result, errors = None, []
    # 1) Kopken langsung (gratis). Kalau baru saja gagal, lewati 5 menit supaya tidak lambat.
    if now >= _state["kk_down_until"]:
        try:
            result = _try_kopken(code)
            result["source"] = "kopken"
        except IntegrationError as exc:
            errors.append("kopken: %s" % exc)
            _state["kk_down_until"] = now + 300
    else:
        errors.append("kopken: dilewati (gagal <5 menit lalu)")

    # 2) Cadangan juragankopi. Hasil di-cache 30 menit supaya hemat panggilan/saldo.
    ttl = 300
    if result is None:
        try:
            result = _fetch_backup(code)
            ttl = 1800
        except IntegrationError as exc:
            errors.append("backup: %s" % exc)

    if result is None:
        _last_error[code] = " | ".join(errors)
        # Semua sumber gagal: pakai salinan lama (maks 6 jam) daripada gagal total.
        if cached and now - cached["t"] < 6 * 3600:
            return cached["data"]
        return None
    _menu_cache[code] = {"data": result, "t": now, "ttl": ttl}
    return result


def _route(path):
    prefix = "/api/menu/" if path.startswith("/api/menu/") else "/api/menu.py/"
    if not path.startswith(prefix) or path.endswith("/") or path.count("/") != 3:
        return None
    code = path[len(prefix):]
    return code if _STORE.fullmatch(code) else None


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        code = _route(parsed.path) if not parsed.query else None
        if code is None:
            body = json.dumps({"error": "invalid menu route"}).encode()
            status = 400
        else:
            menu = get_menu(code)
            if not menu:
                body = json.dumps({"error": "Menu not available", "reason": last_error(code)}).encode()
                status = 502
            else:
                body = json.dumps(menu, ensure_ascii=False).encode()
                status = 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, s-maxage=60, max-age=30" if status == 200 else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
