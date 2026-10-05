import json, os, sys, time, uuid

import jwt, pytest, requests

import mercari

live = pytest.mark.skipif(os.environ.get("MERCARI_LIVE") != "1", reason="set MERCARI_LIVE=1 to hit the real api")

@pytest.fixture(autouse=True)
def tmp_key(tmp_path, monkeypatch):
    monkeypatch.setattr(mercari, "KEY_PATH", str(tmp_path / "dpop.pem"))

def decode(tok):
    h = jwt.get_unverified_header(tok)
    return h, jwt.decode(tok, jwt.PyJWK(h["jwk"]).key, algorithms=["ES256"])

class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

@pytest.fixture
def api(monkeypatch):
    class Sess:
        def __init__(self):
            self.calls, self.resp = [], Resp({})

        def request(self, method, url, **kw):
            self.calls.append(dict(method=method, url=url, **kw))
            return self.resp

    s = Sess()
    monkeypatch.setattr(mercari, "_sess", s)
    return s

def test_dpop():
    h, c = decode(mercari.make_dpop("post", "https://api.mercari.jp/v2/entities:search"))
    assert h["typ"] == "dpop+jwt"
    assert h["alg"] == "ES256"
    assert set(h["jwk"]) == {"kty", "crv", "x", "y"}
    assert c["htm"] == "POST"
    assert c["htu"] == "https://api.mercari.jp/v2/entities:search"
    assert abs(c["iat"] - time.time()) < 5
    assert c["uuid"] == mercari._dev_id(mercari._key())
    uuid.UUID(c["jti"])

@pytest.mark.parametrize("url, htu", [
    ("https://api.mercari.jp/items/get?id=m1#top", "https://api.mercari.jp/items/get"),
    ("https://api.mercari.jp", "https://api.mercari.jp/"),
])
def test_htu(url, htu):
    assert decode(mercari.make_dpop("GET", url))[1]["htu"] == htu

def test_jti_unique():
    u = "https://api.mercari.jp/items/get"
    assert decode(mercari.make_dpop("GET", u))[1]["jti"] != decode(mercari.make_dpop("GET", u))[1]["jti"]

def test_key_reused():
    a = mercari._key()
    assert os.path.exists(mercari.KEY_PATH)
    mercari._load.cache_clear()
    b = mercari._key()
    assert a.public_key().public_numbers() == b.public_key().public_numbers()

def test_key_dir(tmp_path):
    p = tmp_path / "a" / "b" / "dpop.pem"
    mercari._key(str(p))
    assert p.exists()

@pytest.mark.skipif(sys.platform == "win32", reason="unix only")
def test_key_perms():
    mercari._key()
    assert os.stat(mercari.KEY_PATH).st_mode & 0o777 == 0o600

def test_dev_id(tmp_path):
    a, b = mercari._key(str(tmp_path / "a.pem")), mercari._key(str(tmp_path / "b.pem"))
    assert mercari._dev_id(a) == mercari._dev_id(a) != mercari._dev_id(b)
    assert uuid.UUID(mercari._dev_id(a)).version == 4

def test_headers():
    h = mercari.build_web_headers("GET", "items/get")
    assert h["x-platform"] == "web"
    assert h["origin"] == "https://jp.mercari.com"
    c = decode(h["dpop"])[1]
    assert (c["htm"], c["htu"]) == ("GET", "https://api.mercari.jp/items/get")

def test_search(api):
    mercari.search("rick owens", sort="price", order="asc", status="sold_out",
                   price_min=1000, price_max=5000, page_token="v1:1", brandId=[1234])
    r = api.calls[0]
    assert r["method"] == "POST"
    assert r["url"] == "https://api.mercari.jp/v2/entities:search"
    assert r["timeout"] == mercari.TIMEOUT

    body = r["json"]
    cond = body["searchCondition"]
    assert cond["keyword"] == "rick owens"
    assert (cond["sort"], cond["order"]) == ("SORT_PRICE", "ORDER_ASC")
    assert cond["status"] == ["STATUS_SOLD_OUT", "STATUS_TRADING"]
    assert (cond["priceMin"], cond["priceMax"]) == (1000, 5000)
    assert cond["brandId"] == [1234]
    assert body["pageToken"] == "v1:1"
    assert body["laplaceDeviceUuid"] == mercari._dev_id(mercari._key())

    c = decode(r["headers"]["dpop"])[1]
    assert (c["htm"], c["htu"]) == ("POST", r["url"])

def test_search_defaults(api):
    mercari.search("socks")
    body = api.calls[0]["json"]
    cond = body["searchCondition"]
    assert body["pageSize"] == 120
    assert (cond["sort"], cond["order"], cond["status"]) == ("SORT_SCORE", "ORDER_DESC", [])

def test_item(api):
    api.resp = Resp({"result": "OK", "data": {"id": "m123"}})
    assert mercari.get_item("m123") == {"id": "m123"}
    r = api.calls[0]
    assert (r["method"], r["url"]) == ("GET", "https://api.mercari.jp/items/get")
    assert r["params"]["id"] == "m123"

@pytest.mark.parametrize("item_id", ["2JQ74ZxG6WakPN98uJ2Kqs", "mQ74ZxG6WakPN98uJ2Kqs"])
def test_shops_item(api, item_id):
    api.resp = Resp({"name": item_id})
    assert mercari.get_item(item_id) == {"name": item_id}
    url = api.calls[0]["url"]
    assert url == f"https://api.mercari.jp/v1/marketplaces/shops/products/{item_id}"
    assert decode(api.calls[0]["headers"]["dpop"])[1]["htu"] == url

def test_http_error(api):
    api.resp = Resp({}, 401)
    with pytest.raises(requests.HTTPError):
        mercari.call("GET", "/items/get")

SAMPLE = {
    "items": [
        {"id": "m111", "name": "Rick Owens ramones", "price": "45000", "status": "ITEM_STATUS_ON_SALE"},
        {"id": "m222", "name": "ソックス", "price": "800", "status": "ITEM_STATUS_SOLD_OUT"},
    ],
    "meta": {"nextPageToken": "v1:1", "numFound": "2"},
}

def test_cli_help(capsys):
    assert mercari.main([]) == 1
    assert "search" in capsys.readouterr().out

def test_cli_search(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(mercari, "search", lambda kw, **a: seen.update(a, kw=kw) or SAMPLE)
    assert mercari.main(["search", "rick owens", "--sort", "newest", "--status", "on_sale", "--max-price", "50000"]) == 0

    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "m111  ¥   45,000  on_sale   Rick Owens ramones",
        "m222  ¥      800  sold_out  ソックス",
    ]
    assert "--page-token v1:1" in err
    assert seen == {"kw": "rick owens", "sort": "newest", "order": "desc", "status": "on_sale",
                    "price_min": 0, "price_max": 50000, "page_size": 120, "page_token": ""}

def test_cli_json(monkeypatch, capsys):
    monkeypatch.setattr(mercari, "search", lambda kw, **a: SAMPLE)
    assert mercari.main(["search", "socks", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == SAMPLE

def test_cli_search_out(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mercari, "search", lambda kw, **a: SAMPLE)
    f = tmp_path / "res.json"
    assert mercari.main(["search", "socks", "-o", str(f)]) == 0
    assert json.loads(f.read_text(encoding="utf-8")) == SAMPLE
    assert capsys.readouterr().out == ""

def test_cli_item_out(monkeypatch, tmp_path):
    item = {"id": "m1", "name": "ソックス"}
    monkeypatch.setattr(mercari, "get_item", lambda i: item)
    f = tmp_path / "item.json"
    assert mercari.main(["item", "m1", "-o", str(f)]) == 0
    assert json.loads(f.read_text(encoding="utf-8")) == item

def test_cli_dpop(capsys):
    assert mercari.main(["dpop", "--method", "get", "--url", "https://api.mercari.jp/items/get?id=m1"]) == 0
    c = decode(capsys.readouterr().out.strip())[1]
    assert (c["htm"], c["htu"]) == ("GET", "https://api.mercari.jp/items/get")

def test_cli_headers(capsys):
    assert mercari.main(["headers", "--path", "/v2/entities:search"]) == 0
    h = json.loads(capsys.readouterr().out)
    assert h["x-platform"] == "web"
    assert decode(h["dpop"])[1]["htm"] == "POST"

def test_cli_error(monkeypatch, capsys):
    def boom(i):
        raise requests.HTTPError("404 Client Error: Not Found")
    monkeypatch.setattr(mercari, "get_item", boom)
    assert mercari.main(["item", "m0"]) == 1
    assert "404" in capsys.readouterr().err

@live
def test_live_search():
    res = mercari.search("rick owens", status="on_sale", sort="price", order="asc", price_min=5000, page_size=30)
    items = res["items"]
    prices = [int(i["price"]) for i in items]
    assert items
    assert prices == sorted(prices)
    assert min(prices) >= 5000
    assert {i["status"] for i in items} == {"ITEM_STATUS_ON_SALE"}
    assert res["meta"]["nextPageToken"]
    assert mercari.get_item(items[0]["id"])["id"] == items[0]["id"]

@live
def test_live_pages():
    a = mercari.search("socks", page_size=30)
    b = mercari.search("socks", page_size=30, page_token=a["meta"]["nextPageToken"])
    assert {i["id"] for i in a["items"]}.isdisjoint(i["id"] for i in b["items"])

@live
def test_live_sold_out():
    items = mercari.search("socks", status="sold_out", page_size=30)["items"]
    assert items
    assert {i["status"] for i in items} <= {"ITEM_STATUS_SOLD_OUT", "ITEM_STATUS_TRADING"}

@live
def test_live_shops():
    items = mercari.search("ソックス")["items"]
    shop = next((i for i in items if i.get("itemType") == "ITEM_TYPE_BEYOND"), None)
    if not shop:
        pytest.skip("no shops items in results")
    assert mercari.get_item(shop["id"])["name"] == shop["id"]

@live
def test_live_bad_proof():
    h = mercari.build_web_headers("GET", "/items/get")
    r = requests.post(mercari.API + "/v2/entities:search", headers=h, json={}, timeout=30)
    assert r.status_code == 401
