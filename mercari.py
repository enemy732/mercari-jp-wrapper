import os, uuid, time, base64, jwt, requests, json, argparse, sys
from urllib.parse import urlsplit
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

KEY_PATH = "dpop.pem"

def _load_key():
    if os.path.exists(KEY_PATH):
        return serialization.load_pem_private_key(open(KEY_PATH,"rb").read(), None)
    k = ec.generate_private_key(ec.SECP256R1())
    open(KEY_PATH,"wb").write(k.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    return k

def _b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def _jwk(k):
    n = k.public_key().public_numbers()
    return {"kty":"EC","crv":"P-256","x":_b64u(n.x.to_bytes(32,"big")),"y":_b64u(n.y.to_bytes(32,"big"))}
def _htu(u):
    p = urlsplit(u)
    return f"{p.scheme}://{p.netloc}{p.path or '/'}"

def make_dpop(m,u):
    k = _load_key()
    h = {"typ":"dpop+jwt","alg":"ES256","jwk":_jwk(k)}
    c = {"htm":m.upper(),"htu":_htu(u),"iat":int(time.time()),"jti":str(uuid.uuid4())}
    return jwt.encode(c, k.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()), algorithm="ES256", headers=h)

def get_accounts_headers(method: str, path: str, *, origin: str = "https://jp.mercari.com") -> dict:
    if not path.startswith("/"):
        path = "/" + path
    accounts_url = f"https://accounts.mercari.com{path}"
    dpop = make_dpop(method, accounts_url)
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": origin,
        "referer": origin + "/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "dpop": dpop
    }
    try:
        res = requests.post(accounts_url, headers=headers, data="{}")
        try:
            data = res.json()
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
        except Exception:
            pass
    except Exception:
        pass
    return {}

def build_web_headers(method: str, path: str, *, use_preflight: bool = False) -> dict:
    if not path.startswith("/"):
        path = "/" + path
    api_url = f"https://api.mercari.jp{path}"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ja",
        "content-type": "application/json",
        "origin": "https://jp.mercari.com",
        "referer": "https://jp.mercari.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "x-country-code": "JP",
        "x-platform": "web",
    }
    if use_preflight:
        pre = get_accounts_headers(method, path)
        headers.update(pre)
        if "DPoP" not in {k.lower(): k for k in headers}.values() and "dpop" not in headers:
            headers["dpop"] = make_dpop(method, api_url)
    else:
        headers["dpop"] = make_dpop(method, api_url)
    return headers

def main():
    p = argparse.ArgumentParser(description="Mercari web auth helper (DPoP & headers)")
    sub = p.add_subparsers(dest="cmd")

    p_dpop = sub.add_parser("dpop", help="Generate a DPoP for a given URL")
    p_dpop.add_argument("--method", default="POST", help="HTTP method (default: POST)")
    p_dpop.add_argument("--url", required=True, help="Full URL (e.g., https://api.mercari.jp/v2/entities:search)")

    p_hdrs = sub.add_parser("headers", help="Generate web headers for an API path")
    p_hdrs.add_argument("--method", default="POST", help="HTTP method (default: POST)")
    p_hdrs.add_argument("--path", required=True, help="API path (e.g., /v2/entities:search)")
    p_hdrs.add_argument("--preflight", action="store_true", help="Use accounts.mercari.com preflight to fetch Authorization/DPoP")

    args = p.parse_args()
    if args.cmd == "dpop":
        token = make_dpop(args.method, args.url)
        print(token)
        return 0
    if args.cmd == "headers":
        hdrs = build_web_headers(args.method, args.path, use_preflight=args.preflight)
        print(json.dumps(hdrs, ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 1

if __name__ == "__main__":
    sys.exit(main())