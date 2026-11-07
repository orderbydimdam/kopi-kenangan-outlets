#!/usr/bin/env python3
"""
Refresh stores.json from jasdorkopi.id API (1337+ stores).
Run as cron job or manually.

Usage:
  python3 refresh_stores.py           # Refresh from jasdorkopi.id
  python3 refresh_stores.py --dry-run # Preview without saving
"""
import argparse
import json
import os
import tempfile
import time
import urllib.request


class RefreshError(RuntimeError):
    """The source response cannot safely replace the current store list."""


def _page_payload(body, page):
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise RefreshError(f"page {page}: invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RefreshError(f"page {page}: response is not an object")

    outlets = payload.get("data")
    if not isinstance(outlets, list) or not outlets:
        raise RefreshError(f"page {page}: empty or invalid data")

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise RefreshError(f"page {page}: missing metadata")
    total = meta.get("total")
    last_page = meta.get("last_page")
    if type(total) is not int or total <= 0:
        raise RefreshError(f"page {page}: total must be a positive integer")
    if type(last_page) is not int or last_page <= 0:
        raise RefreshError(f"page {page}: last_page must be a positive integer")
    return outlets, total, last_page


def _read_page(opener, page):
    response = None
    try:
        response = opener(f"https://jasdorkopi.id/api/outlets?page={page}")
        return response.read()
    except Exception as exc:
        raise RefreshError(f"page {page}: source request failed") from exc
    finally:
        if response is not None:
            close = getattr(response, "close", None)
            if close is not None:
                close()


def _validate_codes(outlets):
    seen = set()
    for index, outlet in enumerate(outlets, 1):
        if not isinstance(outlet, dict):
            raise RefreshError(f"outlet {index}: row is not an object")
        code = outlet.get("code")
        if not isinstance(code, str) or not code.strip():
            raise RefreshError(f"outlet {index}: code must be a nonempty string")
        code = code.strip()
        if code in seen:
            raise RefreshError(f"outlet {index}: duplicate code")
        seen.add(code)
        outlet["code"] = code


def fetch_all_stores(opener=None, sleeper=None):
    opener = urllib.request.urlopen if opener is None else opener
    sleeper = time.sleep if sleeper is None else sleeper
    outlets = []
    total = last_page = None
    page = 1
    while True:
        page_outlets, page_total, page_last = _page_payload(
            _read_page(opener, page), page
        )
        if total is None:
            total, last_page = page_total, page_last
        elif (page_total, page_last) != (total, last_page):
            raise RefreshError(f"page {page}: metadata changed")

        if len(outlets) + len(page_outlets) > total:
            raise RefreshError(f"page {page}: more rows than total")
        outlets.extend(page_outlets)
        _validate_codes(outlets)
        print(
            f"\r  Page {page}/{last_page} ({len(outlets)}/{total})",
            end="",
            flush=True,
        )
        if page == last_page:
            break
        page += 1
        sleeper(0.3)

    if len(outlets) != total:
        raise RefreshError(f"fetched {len(outlets)} rows, expected {total}")
    print()
    return outlets


def _optional_text(outlet, field):
    value = outlet.get(field, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RefreshError(f"field {field} must be a string")
    return value


def _coordinate(outlet, field):
    value = outlet.get(field, "")
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise RefreshError(f"field {field} must be text or numeric")
    return str(value)


def convert(outlets):
    stores = []
    for index, outlet in enumerate(outlets, 1):
        if not isinstance(outlet, dict):
            raise RefreshError(f"outlet {index}: row is not an object")
        code = outlet.get("code")
        name = outlet.get("name")
        address = outlet.get("address")
        if not isinstance(code, str) or not code.strip():
            raise RefreshError(f"outlet {index}: invalid code")
        if not isinstance(name, str) or not name.strip():
            raise RefreshError(f"outlet {index}: invalid name")
        if not isinstance(address, str) or not address.strip():
            raise RefreshError(f"outlet {index}: invalid address")

        is_open = outlet.get("is_open", False)
        if not isinstance(is_open, bool):
            raise RefreshError(f"outlet {index}: is_open must be boolean")
        close = outlet.get("order_close_time")
        if close is None:
            close = outlet.get("real_close_time", "")
        if close is not None and not isinstance(close, str):
            raise RefreshError(f"outlet {index}: close must be a string")

        stores.append({
            "code": code.strip(),
            "name": name.strip(),
            "address": address,
            "latitude": _coordinate(outlet, "latitude"),
            "longitude": _coordinate(outlet, "longitude"),
            "is_open": is_open,
            "open": _optional_text(outlet, "open_time"),
            "close": close or "",
            "category": _optional_text(outlet, "category"),
            "image_url": _optional_text(outlet, "image_url"),
            "brand_and_image": [{"brand_name": "Kopi Kenangan"}],
        })
    _validate_codes(stores)
    return stores


def write_stores_atomic(stores, path):
    directory = os.path.dirname(os.path.abspath(path))
    prefix = "." + os.path.basename(path) + "."
    fd, temporary = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(stores, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def refresh(path, opener=None, sleeper=None):
    return write_stores_atomic(
        convert(fetch_all_stores(opener=opener, sleeper=sleeper)), path
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--output", default="stores.json")
    args = ap.parse_args()

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Refreshing stores from jasdorkopi.id...")
    outlets = fetch_all_stores()
    stores = convert(outlets)
    open_c = sum(1 for s in stores if s.get('is_open'))
    print(f"  {len(stores)} stores ({open_c} open)")

    if args.dry_run:
        return

    write_stores_atomic(stores, args.output)
    print(f"  Saved to {args.output}")

if __name__ == "__main__":
    main()
