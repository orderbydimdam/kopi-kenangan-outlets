# ☕ Kopi Kenangan — Outlet & Menu API

Unofficial real-time API + web app untuk melihat status **buka/tutup** dan **menu** semua outlet Kopi Kenangan.

> ⚠️ **Disclaimer**: Proyek riset pribadi. Tidak berafiliasi dengan Kopi Kenangan.

## Live App

🔗 **[kopi-kenangan-outlets.vercel.app](https://kopi-kenangan-outlets.vercel.app)**

- 🏪 **1,337 outlets** seluruh Indonesia
- 🟢 **Status real-time** — auto-check saat outlet visible di layar
- 🍵 **Menu + gambar** — harga, promo, ketersediaan
- 📍 **Sort by jarak** — pakai lokasi user

## API

Base: `https://kopi-kenangan-outlets.vercel.app`

### `GET /api/stores`

| Parameter | Contoh | Fungsi |
|-----------|--------|--------|
| (none) | — | Semua 1337 stores |
| `codes` | `KK.KDS.RKDRSLSQJSDM,GI` | Filter specific codes |
| `open` | `1` / `0` | Filter buka/tutup |
| `q` | `kudus` | Search nama/kode/alamat |
| `city` | `jakarta` | Filter alamat |
| `lat`, `lon` | `-6.2`, `106.8` | Sort by distance + tambah `distance_km` |

```bash
curl "https://kopi-kenangan-outlets.vercel.app/api/stores?codes=KK.KDS.RKDRSLSQJSDM"
curl "https://kopi-kenangan-outlets.vercel.app/api/stores?open=1&city=jakarta"
curl "https://kopi-kenangan-outlets.vercel.app/api/stores?lat=-6.2&lon=106.8"
```

### `GET /api/stores/:code`

Detail 1 outlet + **real-time `is_open`** (live check ke server KK, cache 5 menit).

```bash
curl https://kopi-kenangan-outlets.vercel.app/api/stores/KK.KDS.RKDRSLSQJSDM
```

### `GET /api/stores_realtime?codes=C1,C2,...`

Real-time status untuk multiple stores (max 20). Verifikasi ganda:

| `_source` | Arti |
|-----------|------|
| `verified` | KK API + jasdorkopi.id agree |
| `disputed` | Sumber beda (trust KK API, include `_kk`/`_jd`) |
| `kk_api` | Hanya KK API respond |
| `jd_api` | Hanya jasdorkopi respond |
| `cached` | Fallback ke stores.json |

```bash
curl "https://kopi-kenangan-outlets.vercel.app/api/stores_realtime?codes=KK.KDS.RKDRSLSQJSDM,GI"
```

### `GET /api/menu/:code`

Menu outlet — nama, harga, promo, ketersediaan, **gambar produk**, dan `sku` kanonik. Cache 5 menit.

```bash
curl https://kopi-kenangan-outlets.vercel.app/api/menu/DPK.APTKROXY
```

### `GET /api/options/:code/:product_id`

Kontrak opsi produk read-only. Setiap produk menu memiliki `sku`; setiap varian memiliki `sku` dan sorted unique `addon_skus`; setiap nilai add-on memiliki `sku`. Grup add-on juga mengembalikan boolean `mandatory` dan `only_one`. Respons ditolak jika identitas SKU kosong, ambigu, duplikat, atau kompatibilitas mengarah ke add-on yang tidak dipublikasikan.

```bash
curl https://kopi-kenangan-outlets.vercel.app/api/options/DPK.APTKROXY/9645
```

### `GET /api/menu/search?q=...`

Search: store name/address (instant) + menu items dari store yang sudah pernah dibuka.

```bash
curl "https://kopi-kenangan-outlets.vercel.app/api/menu/search?q=kopi+kenangan+mantan"
```

## Deploy

1. Fork → import ke [vercel.com/new](https://vercel.com/new) → Deploy
2. GitHub Actions auto-refresh `stores.json` tiap 10 menit (dari jasdorkopi.id)

## Struktur

```
├── api/
│   ├── stores.py           # GET /api/stores — list + filters
│   ├── store_detail.py     # GET /api/stores/:code — real-time
│   ├── stores_realtime.py  # GET /api/stores_realtime — dual-verify
│   ├── menu.py             # GET /api/menu/:code — menu + images
│   ├── options.py          # GET /api/options/:code/:product_id — option contract
│   └── menu_search.py      # GET /api/menu/search
├── stores.json             # 1337 stores (auto-refresh 10 menit)
├── refresh_stores.py       # Fetcher dari jasdorkopi.id
├── index.html              # Frontend
├── .github/workflows/refresh.yml
└── vercel.json
```

## Data Sources

| Sumber | Endpoint | Fungsi |
|--------|----------|--------|
| `order.kopikenangan.com` | `/store/get_store` | Real-time `is_open` (primary) |
| `order.kopikenangan.com` | `/product/query_web_order_product_menu` | Menu (web token gratis) |
| `jasdorkopi.id` | `/api/outlets` | 1337 store list + verifikasi status |

## License

MIT
