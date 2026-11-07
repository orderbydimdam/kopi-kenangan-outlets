from http.server import BaseHTTPRequestHandler
import json, os, time, urllib.request, urllib.parse, concurrent.futures

STORES = None
_rt_cache = {}
_jd_cache = {}

def load_stores():
    global STORES
    if STORES is None:
        path = os.path.join(os.path.dirname(__file__), '..', 'stores.json')
        with open(path) as f:
            STORES = json.load(f)
    return STORES

def get_kk_api(code):
    """Primary: get_store from order.kopikenangan.com"""
    now = time.time()
    if code in _rt_cache and now - _rt_cache[code]['t'] < 120:
        return _rt_cache[code]['v']
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            'https://order.kopikenangan.com/web_order/api/store/get_store',
            data=json.dumps({"store_code": code}).encode(),
            headers={"Content-Type": "application/json", "language": "id", "time_zone": "7"}
        ), timeout=5)
        d = json.loads(r.read())
        if d.get("error_code") == 0:
            v = d["data"].get("is_open")
            _rt_cache[code] = {"v": v, "t": now}
            return v
    except: pass
    return None

def get_jasdor_status(code):
    """Secondary: jasdorkopi.id verification (1-5 min cache)"""
    now = time.time()
    if code in _jd_cache and now - _jd_cache[code]['t'] < 300:
        return _jd_cache[code]['v']
    try:
        # jasdorkopi.id doesn't have per-store endpoint, but we can check
        # by fetching from their API and finding the store
        r = urllib.request.urlopen(f'https://jasdorkopi.id/api/outlets?page=1&search={code}', timeout=5)
        d = json.loads(r.read())
        for o in d.get('data', []):
            if o.get('code') == code:
                v = o.get('is_open')
                _jd_cache[code] = {"v": v, "t": now}
                return v
    except: pass
    return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        stores = load_stores()
        parsed = self.path.split('?', 1)
        qs = urllib.parse.parse_qs(parsed[1] if len(parsed) > 1 else "")

        codes_param = qs.get('codes', [''])[0]
        codes = [c.strip() for c in codes_param.split(',') if c.strip()][:20]

        result = []
        for s in stores:
            # If codes specified, only include those stores
            if codes and s["code"] not in codes:
                continue

            entry = {
                "code": s["code"],
                "name": s.get("name"),
                "address": s.get("address"),
                "open": s.get("open"),
                "close": s.get("close"),
                "latitude": s.get("latitude"),
                "longitude": s.get("longitude"),
                "category": s.get("category"),
                "image_url": s.get("image_url"),
                "is_open": s.get("is_open"),
                "_source": "cached",
            }

            if codes:
                kk_status = get_kk_api(s["code"])
                jd_status = get_jasdor_status(s["code"])

                if kk_status is not None and jd_status is not None:
                    if kk_status == jd_status:
                        entry["is_open"] = kk_status
                        entry["_source"] = "verified"  # Both agree
                    else:
                        # Disagree — trust KK API (primary) but mark
                        entry["is_open"] = kk_status
                        entry["_source"] = "disputed"
                        entry["_kk"] = kk_status
                        entry["_jd"] = jd_status
                elif kk_status is not None:
                    entry["is_open"] = kk_status
                    entry["_source"] = "kk_api"
                elif jd_status is not None:
                    entry["is_open"] = jd_status
                    entry["_source"] = "jd_api"

            result.append(entry)

        # Filters
        if 'open' in qs:
            want = qs['open'][0] == '1'
            result = [s for s in result if s.get('is_open') == want]
        if 'q' in qs:
            q = qs['q'][0].lower()
            result = [s for s in result if q in (s.get('name','') + s.get('code','') + s.get('address','')).lower()]

        # Distance sort
        if 'lat' in qs and 'lon' in qs:
            import math
            ulat, ulon = float(qs['lat'][0]), float(qs['lon'][0])
            for s in result:
                try:
                    slat, slon = float(s.get('latitude',0)), float(s.get('longitude',0))
                    dlat = math.radians(slat - ulat)
                    dlon = math.radians(slon - ulon)
                    a = math.sin(dlat/2)**2 + math.cos(math.radians(ulat))*math.cos(math.radians(slat))*math.sin(dlon/2)**2
                    s['_dist'] = 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                except: s['_dist'] = 9999
            result.sort(key=lambda s: s.get('_dist', 9999))
            for s in result:
                d = s.pop('_dist', None)
                if d is not None and d < 9999:
                    s['distance_km'] = round(d, 1)

        body = json.dumps({
            "total": len(stores),
            "open": sum(1 for s in result if s.get('is_open')),
            "results": len(result),
            "stores": result
        }, ensure_ascii=False).encode()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass
