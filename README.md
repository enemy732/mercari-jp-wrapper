## mercari web auth helper (unofficial)

generate dpop tokens and build the headers the web app expects.

### install

```bash
pip install -r requirements.txt
```

### usage

```bash
python mercari.py dpop --method POST --url https://api.mercari.jp/v2/entities:search
python mercari.py headers --method POST --path /v2/entities:search
python mercari.py headers --method POST --path /v2/entities:search --preflight
```

### auth

- base: `https://api.mercari.jp`
- preflight: `POST https://accounts.mercari.com{path}`
- headers: `x-country-code: jp`, `x-platform: web`, `accept-language: ja`

### api

- post `/v2/entities:search`
  - minimal payload:
  ```json
  {
    "pageSize": 60,
    "pageToken": "",
    "searchSessionId": "<uuid-hex>",
    "source": "BaseSerp",
    "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
    "searchCondition": { "keyword": "rick owens", "order": "ORDER_DESC", "sort": "SORT_SCORE" },
    "withAuction": true,
    "laplaceDeviceUuid": "<uuid-hex>"
  }
  ```

- more endpoints live under `/v2/`. confirm via devtools + `--preflight`.

### discover

1. do the action on jp.mercari.com and watch the network tab.
2. reuse the `path` with `mercari.py headers --preflight`.
3. send your request with those headers.

### note

not affiliated with mercari. use responsibly.