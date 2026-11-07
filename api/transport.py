import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://order.kopikenangan.com/web_order/api"
REQUEST_TIMEOUT = 10
MAX_BODY_BYTES = 2 * 1024 * 1024


class IntegrationError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IntegrationError("redirect rejected")



def _open(url, payload, headers):
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect())
    return opener.open(request, timeout=REQUEST_TIMEOUT)



def _json_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise IntegrationError("duplicate JSON key")
        value[key] = item
    return value



def request_json(path, payload, headers):
    if type(path) is not str or not path.startswith("/") or "://" in path:
        raise IntegrationError("invalid upstream path")
    url = BASE + path
    parts = urllib.parse.urlsplit(url)
    base = urllib.parse.urlsplit(BASE)
    if (parts.scheme, parts.netloc) != (base.scheme, base.netloc) or not parts.path.startswith(base.path + "/"):
        raise IntegrationError("upstream host rejected")
    if type(payload) is not bytes:
        raise IntegrationError("invalid request body")
    response = None
    try:
        response = _open(url, payload, headers)
        status = getattr(response, "status", None)
        if status != 200:
            raise IntegrationError("upstream status rejected")
        response_headers = getattr(response, "headers", {})
        content_type = response_headers.get("Content-Type")
        if type(content_type) is not str or content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise IntegrationError("upstream MIME rejected")
        raw_length = response_headers.get("Content-Length")
        length = None
        if raw_length is not None:
            if type(raw_length) is not str or not raw_length.isdigit():
                raise IntegrationError("invalid upstream length")
            length = int(raw_length)
            if length > MAX_BODY_BYTES:
                raise IntegrationError("upstream body too large")
        body = response.read(MAX_BODY_BYTES + 1)
        if type(body) is not bytes or len(body) > MAX_BODY_BYTES or (length is not None and len(body) != length):
            raise IntegrationError("upstream body size rejected")
        try:
            return json.loads(body, object_pairs_hook=_json_pairs)
        except (TypeError, ValueError) as exc:
            raise IntegrationError("invalid upstream JSON") from exc
    except IntegrationError:
        raise
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise IntegrationError("upstream request failed") from exc
    finally:
        if response is not None:
            close = getattr(response, "close", None)
            if close is not None:
                close()
