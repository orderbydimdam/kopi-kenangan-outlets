from http.server import BaseHTTPRequestHandler
import json, os, math, urllib.parse

STORES = None

def load_stores():
    global STORES
    if STORES is None:
        path = os.path.join(os.path.dirname(__file__), '..', 'stores.json')
        with open(path) as f:
            STORES = json.load(f)
    return STORES

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        stores = load_stores()
        parsed = self.path.split('?', 1)
        qs = urllib.parse.parse_qs(parsed[1]) if len(parsed) > 1 else {}

        result = list(stores)

        # Filter: specific codes (comma-separated)
        if 'codes' in qs:
            wanted = set(c.strip() for c in qs['codes'][0].split(',') if c.strip())
            result = [s for s in result if s.get('code') in wanted]

        # Filter: open/closed
        if 'open' in qs:
            want = qs['open'][0] == '1'
            result = [s for s in result if bool(s.get('is_open')) == want]

        # Filter: city/address search
        if 'city' in qs:
            c = qs['city'][0].lower()
            result = [s for s in result if c in (s.get('address','') + s.get('name','')).lower()]

        # Search: name/code/address
        if 'q' in qs:
            q = qs['q'][0].lower()
            result = [s for s in result if q in (s.get('name','') + s.get('code','') + s.get('address','') + s.get('alias','')).lower()]

        # Distance sort
        user_lat = float(qs['lat'][0]) if 'lat' in qs else None
        user_lon = float(qs['lon'][0]) if 'lon' in qs else None
        if user_lat is not None and user_lon is not None:
            for s in result:
                try:
                    s['_dist'] = haversine(user_lat, user_lon, float(s.get('latitude',0)), float(s.get('longitude',0)))
                except:
                    s['_dist'] = 9999
            result.sort(key=lambda s: s.get('_dist', 9999))
            for s in result:
                d = s.pop('_dist', None)
                if d is not None and d < 9999:
                    s['distance_km'] = round(d, 1)

        body = json.dumps({
            "total": len(stores),
            "open": sum(1 for s in stores if s.get('is_open')),
            "closed": sum(1 for s in stores if not s.get('is_open')),
            "results": len(result),
            "stores": result
        }, ensure_ascii=False).encode()

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'public, s-maxage=300, max-age=60')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass
