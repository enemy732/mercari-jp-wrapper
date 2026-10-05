import argparse, base64, hashlib, json, os, sys, time, uuid
from functools import lru_cache
from urllib.parse import urlsplit

import jwt, requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

API = "https://api.mercari.jp"
WEB = "https://jp.mercari.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
KEY_PATH = os.environ.get("MERCARI_DPOP_KEY", "dpop.pem")
TIMEOUT = 30

SORTS = {"score": "SORT_SCORE", "newest": "SORT_CREATED_TIME", "price": "SORT_PRICE", "likes": "SORT_NUM_LIKES"}
ORDERS = {"desc": "ORDER_DESC", "asc": "ORDER_ASC"}
STATUSES = {"on_sale": ["STATUS_ON_SALE"], "sold_out": ["STATUS_SOLD_OUT", "STATUS_TRADING"]}

_sess = requests.Session()

@lru_cache(None)
def _load(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), None)
    k = ec.generate_private_key(ec.SECP256R1())
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
    return k

def _key(path=None): return _load(os.path.expanduser(path or KEY_PATH))

def _dev_id(k):
    pt = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return str(uuid.UUID(bytes=hashlib.sha256(pt).digest()[:16], version=4))

def _b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def _jwk(k):
    n = k.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256", "x": _b64u(n.x.to_bytes(32, "big")), "y": _b64u(n.y.to_bytes(32, "big"))}

def _htu(u):
    p = urlsplit(u)
    return f"{p.scheme}://{p.netloc}{p.path or '/'}"

def make_dpop(m, u, k=None):
    k = k or _key()
    h = {"typ": "dpop+jwt", "alg": "ES256", "jwk": _jwk(k)}
    c = {"iat": int(time.time()), "jti": str(uuid.uuid4()), "htu": _htu(u), "htm": m.upper(), "uuid": _dev_id(k)}
    return jwt.encode(c, k, algorithm="ES256", headers=h)

def build_web_headers(method, path):
    if not path.startswith("/"):
        path = "/" + path
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ja",
        "content-type": "application/json",
        "origin": WEB,
        "referer": WEB + "/",
        "user-agent": UA,
        "x-country-code": "JP",
        "x-platform": "web",
        "dpop": make_dpop(method, API + path),
    }

def call(method, path, params=None, body=None):
    if not path.startswith("/"):
        path = "/" + path
    r = _sess.request(method, API + path, params=params, json=body,
                      headers=build_web_headers(method, path), timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def search(keyword, sort="score", order="desc", status=None, price_min=0, price_max=0,
           page_size=120, page_token="", **extra):
    if isinstance(status, str):
        status = STATUSES.get(status, [status])
    body = {
        "userId": "",
        "config": {"responseToggles": ["QUERY_SUGGESTION_WEB_1"]},
        "pageSize": page_size,
        "pageToken": page_token,
        "searchSessionId": uuid.uuid4().hex,
        "source": "BaseSerp",
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "thumbnailTypes": [],
        "searchCondition": {
            "keyword": keyword,
            "excludeKeyword": "",
            "sort": SORTS.get(sort, sort),
            "order": ORDERS.get(order, order),
            "status": list(status or []),
            "sizeId": [],
            "categoryId": [],
            "brandId": [],
            "sellerId": [],
            "priceMin": price_min,
            "priceMax": price_max,
            "itemConditionId": [],
            "shippingPayerId": [],
            "shippingFromArea": [],
            "shippingMethod": [],
            "colorId": [],
            "hasCoupon": False,
            "attributes": [],
            "itemTypes": [],
            "skuIds": [],
            "shopIds": [],
            "excludeShippingMethodIds": [],
            **extra,
        },
        "serviceFrom": "suruga",
        "withItemBrand": True,
        "withItemSize": False,
        "withItemPromotions": True,
        "withItemSizes": True,
        "withShopname": False,
        "useDynamicAttribute": True,
        "withSuggestedItems": True,
        "withOfferPricePromotion": True,
        "withProductSuggest": True,
        "withParentProducts": False,
        "withProductArticles": True,
        "withSearchConditionId": False,
        "withAuction": True,
        "laplaceDeviceUuid": _dev_id(_key()),
    }
    return call("POST", "/v2/entities:search", body=body)

def get_item(item_id):
    if item_id[:1] == "m" and item_id[1:].isdigit():
        return call("GET", "/items/get", {
            "id": item_id,
            "include_item_attributes": "true",
            "include_product_page_component": "true",
            "include_non_ui_item_attributes": "true",
            "include_donation": "true",
            "include_item_attributes_sections": "true",
            "include_auction": "true",
        })["data"]
    return call("GET", f"/v1/marketplaces/shops/products/{item_id}", {"view": "FULL", "imageType": "JPEG"})

def _show(res):
    for it in res.get("items", []):
        st = it.get("status", "").removeprefix("ITEM_STATUS_").lower()
        print(f"{it['id']}  ¥{int(it.get('price') or 0):>9,}  {st:<8}  {it.get('name', '')}")
    tok = res.get("meta", {}).get("nextPageToken")
    if tok:
        sys.stdout.flush()
        print(f"next page: --page-token {tok}", file=sys.stderr)

def _dump(data, path=None):
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(out + "\n")
    else:
        print(out)

def main(argv=None):
    p = argparse.ArgumentParser(prog="mercari.py", description="unofficial jp.mercari.com api client")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("search", help="search listings")
    s.add_argument("keyword")
    s.add_argument("--sort", choices=SORTS, default="score")
    s.add_argument("--order", choices=ORDERS, default="desc")
    s.add_argument("--status", choices=STATUSES, help="default: both")
    s.add_argument("--min-price", type=int, default=0, metavar="YEN")
    s.add_argument("--max-price", type=int, default=0, metavar="YEN")
    s.add_argument("--page-size", type=int, default=120)
    s.add_argument("--page-token", default="")
    s.add_argument("--json", action="store_true", help="print the raw response")
    s.add_argument("-o", "--output", metavar="FILE", help="save the raw response to FILE (utf-8)")

    i = sub.add_parser("item", help="print one listing as json")
    i.add_argument("item_id", help="e.g. m12345678901")
    i.add_argument("-o", "--output", metavar="FILE", help="save to FILE (utf-8)")

    h = sub.add_parser("headers", help="print signed headers for an api path")
    h.add_argument("--method", default="POST")
    h.add_argument("--path", required=True, help="e.g. /v2/entities:search")

    d = sub.add_parser("dpop", help="print a dpop proof for a url")
    d.add_argument("--method", default="POST")
    d.add_argument("--url", required=True, help="e.g. https://api.mercari.jp/items/get")

    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        if args.cmd == "search":
            res = search(args.keyword, sort=args.sort, order=args.order, status=args.status,
                         price_min=args.min_price, price_max=args.max_price,
                         page_size=args.page_size, page_token=args.page_token)
            if args.json or args.output:
                _dump(res, args.output)
            else:
                _show(res)
        elif args.cmd == "item":
            _dump(get_item(args.item_id), args.output)
        elif args.cmd == "headers":
            print(json.dumps(build_web_headers(args.method, args.path), indent=2))
        elif args.cmd == "dpop":
            print(make_dpop(args.method, args.url))
    except requests.RequestException as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
