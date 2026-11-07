from http.server import BaseHTTPRequestHandler
import json, time, urllib.request, urllib.parse

BASE = "https://order.kopikenangan.com/web_order/api"
HEADERS = {"Content-Type": "application/json", "language": "id", "time_zone": "7"}
_token = {"val": None, "t": 0}
_menu_cache = {}
_stores = None

def load_stores():
    global _stores
    if _stores is None:
        path = os.path.join(os.path.dirname(__file__), '..', 'stores.json')
        with open(path) as f:
            _stores = json.load(f)
    return _stores

import os

def get_token():
    if _token["val"] and time.time() - _token["t"] < 600:
        return _token["val"]
    r = urllib.request.urlopen(urllib.request.Request(f"{BASE}/create_web_token",
        data=json.dumps({"phone": "6281200000000"}).encode(), headers=HEADERS))
    _token["val"] = json.loads(r.read())["data"]["web_order_session_token"]
    _token["t"] = time.time()
    return _token["val"]

def get_menu(code):
    now = time.time()
    if code in _menu_cache and now - _menu_cache[code]['t'] < 300:
        return _menu_cache[code]['data']
    try:
        token = get_token()
        h = {**HEADERS, "Authorization": token}
        r = urllib.request.urlopen(urllib.request.Request(f"{BASE}/product/query_web_order_product_menu",
            data=json.dumps({"store_code": code, "sales_type": 10401}).encode(), headers=h), timeout=10)
        d = json.loads(r.read())
        if d.get("error_code") != 0:
            return None
        groups = d.get("data", {}).get("menu_groups", [])
        _menu_cache[code] = {'data': groups, 't': now}
        return groups
    except Exception:
        return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        stores = load_stores()
        parsed = self.path.split('?', 1)
        qs = urllib.parse.parse_qs(parsed[1]) if len(parsed) > 1 else {}
        query = qs.get('q', [''])[0].lower().strip()
        limit = int(qs.get('limit', ['20'])[0])

        if not query:
            body = json.dumps({"error": "Missing ?q= parameter"}).encode()
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)
            return

        # Phase 1: match stores by name/address/code (fast, from cache)
        store_matches = []
        for s in stores:
            searchable = (s.get('name','') + s.get('code','') + s.get('address','')).lower()
            if query in searchable:
                store_matches.append({
                    "store_code": s['code'],
                    "store_name": s.get('name'),
                    "is_open": s.get('is_open'),
                    "address": s.get('address'),
                    "match_type": "store",
                    "matching_items": []
                })

        # Phase 2: search menu items — check already-cached menus first (instant)
        results = []
        seen = set()
        for sm in store_matches:
            results.append(sm)
            seen.add(sm['store_code'])

        cached_codes = list(_menu_cache.keys())
        for code in cached_codes:
            if code in seen or len(results) >= limit:
                continue
            groups = _menu_cache[code]['data']
            matches = self.find_items(groups, query)
            if matches:
                store_name = next((s.get('name') for s in stores if s['code'] == code), code)
                results.append({
                    "store_code": code,
                    "store_name": store_name,
                    "is_open": next((s.get('is_open') for s in stores if s['code'] == code), None),
                    "match_type": "menu_cached",
                    "matching_items": matches
                })
                seen.add(code)

        body = json.dumps({
            "query": query,
            "results": len(results),
            "note": "store matches are instant; menu search covers recently viewed stores",
            "stores": results[:limit]
        }, ensure_ascii=False).encode()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, s-maxage=300')
        self.end_headers()
        self.wfile.write(body)

    def find_items(self, groups, query):
        matches = []
        for g in groups:
            for p in g.get('menu_products', []):
                if query in p.get('name', '').lower():
                    matches.append({
                        "name": p.get("name"),
                        "price": p.get("price"),
                        "available": not p.get("is_sold_out", False)
                    })
        return matches

    def log_message(self, *a): pass
