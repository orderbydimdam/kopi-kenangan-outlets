from http.server import BaseHTTPRequestHandler
import json, os, time, urllib.request

BASE = "https://order.kopikenangan.com/web_order/api"
HEADERS = {"Content-Type": "application/json", "language": "id", "time_zone": "7"}
_cache = {}

def canonicalize_store(store):
    if not isinstance(store, dict) or not isinstance(store.get("name"), str):
        return None
    name = store["name"].strip()
    if not name:
        return None
    canonical = dict(store)
    canonical["name"] = name
    return canonical

def get_store_live(code):
    now = time.time()
    if code in _cache and now - _cache[code]['time'] < 300:
        return canonicalize_store(_cache[code]['data'])
    try:
        req = urllib.request.Request(f"{BASE}/store/get_store",
            data=json.dumps({"store_code": code}).encode(), headers=HEADERS)
        r = urllib.request.urlopen(req, timeout=10)
        d = json.loads(r.read())
        if d.get("error_code") == 0:
            store = canonicalize_store(d['data'])
            if store is not None:
                _cache[code] = {'data': store, 'time': now}
                return store
    except Exception:
        pass
    # Fallback to cached stores.json
    path = os.path.join(os.path.dirname(__file__), '..', 'stores.json')
    if os.path.exists(path):
        with open(path) as f:
            stores = json.load(f)
        store = next((s for s in stores if isinstance(s, dict) and s.get('code') == code), None)
        if store:
            return canonicalize_store(store)
    return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        code = self.path.split('/api/stores/')[-1].split('?')[0]
        if not code:
            self.send_response(400); self.end_headers(); return

        store = get_store_live(code)
        if not store:
            body = json.dumps({"error": "Store not found"}).encode()
            self.send_response(404)
        else:
            body = json.dumps(store, ensure_ascii=False).encode()
            self.send_response(200)

        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, s-maxage=60, max-age=30')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass
