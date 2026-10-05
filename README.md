## mercari-jp-wrapper (unofficial)

[![tests](https://github.com/enemy732/mercari-jp-wrapper/actions/workflows/tests.yml/badge.svg)](https://github.com/enemy732/mercari-jp-wrapper/actions/workflows/tests.yml)

small python client for the api behind [jp.mercari.com](https://jp.mercari.com). it signs requests the same way the web app does, so you can search listings and pull item details from a script. no account, no cookies, no browser.

### install

needs python 3.10+.

```bash
git clone https://github.com/enemy732/mercari-jp-wrapper
cd mercari-jp-wrapper
pip install -r requirements.txt
```

### command line

```bash
python mercari.py search "rick owens"
python mercari.py search "rick owens" --status on_sale --sort price --order asc --max-price 30000
python mercari.py search "rick owens" -o results.json
python mercari.py item m12345678901
```

`search` prints one listing per line, then the token for the next page if there is one:

```
m10000000001  ¥    5,000  on_sale   rick owens drkshdw tee
m10000000002  ¥    5,500  on_sale   リックオウエンス パンツ
next page: --page-token v1:1
```

search options:

- `--sort score|newest|price|likes` and `--order desc|asc`
- `--status on_sale|sold_out` (default is both)
- `--min-price` / `--max-price` in yen
- `--page-size` (default 120, same as the site) and `--page-token`
- `--json` prints the raw response, `-o FILE` saves it

`item` prints the full json for one listing. mercari shops ids work too (anything that isn't `m` + digits), they just come back in a different shape. it takes `-o FILE` as well.

on windows powershell 5.1, use `-o` instead of `>`. powershell re-encodes redirected output and mangles the japanese text, while `-o` always writes utf-8.

if you'd rather send requests yourself:

```bash
python mercari.py headers --method POST --path /v2/entities:search
python mercari.py dpop --method GET --url https://api.mercari.jp/items/get
```

### python

```python
from mercari import search, get_item

res = search("rick owens", status="on_sale", sort="newest")
for item in res["items"]:
    print(item["id"], item["price"], item["name"])

page2 = search("rick owens", status="on_sale", sort="newest",
               page_token=res["meta"]["nextPageToken"])

item = get_item(res["items"][0]["id"])
print(item["description"])
```

`search` returns the raw response. any extra keyword goes into `searchCondition` as-is, using the site's field names: `excludeKeyword="kids"`, `categoryId=[...]`, `brandId=[...]` and so on. easiest way to find the ids is to set the filter on the site and copy them out of the request in devtools.

for anything else there's `call`. it signs the request and returns the json:

```python
from mercari import call

seller = call("GET", "/users/get_profile",
              params={"user_id": "123456789", "_user_format": "profile"})
listings = call("GET", "/items/get_items",
                params={"seller_id": "123456789", "status": "on_sale", "limit": 30})
```

### how it works

every request to `api.mercari.jp` carries a `dpop` header ([RFC 9449](https://www.rfc-editor.org/rfc/rfc9449)). it's a small jwt signed with an ec p-256 key, holding the http method, the url without the query string, a timestamp, a random id and a device uuid. the public key rides along in the jwt header, so the server can check the signature without knowing who you are.

what the api actually enforces (checked oct 2026):

- missing `dpop`, bad signature, or a proof made for a different method or url: 401
- missing `x-platform: web`: 400
- old or reused proofs still go through, but every request gets a fresh one anyway

the key is made on first run and saved as `dpop.pem` in the current directory. set `MERCARI_DPOP_KEY` to keep it somewhere else. it isn't tied to any account, delete it and a new one gets made. the device uuid is derived from the key, so one key file is one "device", same as one browser.

the rest of the headers (`accept-language: ja`, `x-country-code: JP`, origin, referer, user agent) copy what chrome sends.

### finding more endpoints

open jp.mercari.com with devtools on the network tab, filter by `api.mercari.jp`, and do whatever you're after on the site. copy the method, path, query params and json body into `call(...)`.

### tests

```bash
pip install pytest
pytest
```

that runs offline. set `MERCARI_LIVE=1` to also hit the real api (a handful of requests). in powershell: `$env:MERCARI_LIVE=1; pytest`

### note

not affiliated with mercari. this is an undocumented api and can change or break at any time. keep request rates low and respect mercari's terms.
