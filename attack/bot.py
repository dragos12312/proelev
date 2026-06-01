"""
Suspicious-user bot. Drives a real browser via Playwright through the
3-factor login and then fires patterns the AI detector should catch:

  - rapid hits across many different paths (high n_requests + high n_paths)
  - repeated 403s by probing admin endpoints as a normal user
  - 422 fuzzing by sending malformed bodies

After ~30 seconds the AI detector's next cycle will flag this user, and
the admin panel will render an observation row with reason "ai: ...".

Usage:
    pip install playwright
    python -m playwright install chromium

    # log in as the seeded normal user, then attack
    python attack/bot.py
    python attack/bot.py --base http://192.168.56.1:8000 --email user@proelev.ro
"""
import argparse
import asyncio
import json
import os
import random
import sys
import time

# playwright is an optional dep, import lazily so the script can give a
# clean install hint if it's missing
try:
    from playwright.async_api import async_playwright
except ImportError:
    print("playwright not installed. run:")
    print("    pip install playwright")
    print("    python -m playwright install chromium")
    sys.exit(1)

import urllib.request
import urllib.error
import ssl


DEFAULT_BASE = os.environ.get("BOT_BASE", "http://localhost:8000")


def _http_post(base: str, path: str, body: dict, token: str | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method="POST")
    ctx = ssl._create_unverified_context() if base.startswith("https") else None
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def _http_get(base: str, path: str, token: str | None = None) -> tuple[int, dict]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base}{path}", headers=headers, method="GET")
    ctx = ssl._create_unverified_context() if base.startswith("https") else None
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def three_factor_login(base: str, email: str, password: str, answer: str = "proelev") -> str:
    """Walk the 3 factor wizard via plain HTTP and return the access token."""
    code, body = _http_post(base, "/auth/login", {"email": email, "password": password})
    if code != 200:
        raise SystemExit(f"factor 1 failed: {code} {body}")
    challenge = body["challenge_id"]

    # grab the email code from the public mock inbox endpoint
    code2, msg = _http_get(base, f"/auth/inbox/last?to={email}")
    if code2 != 200:
        raise SystemExit(f"inbox fetch failed: {code2} {msg}")
    email_code = msg["code"]

    code3, _ = _http_post(base, "/auth/login/verify-email",
                           {"challenge_id": challenge, "code": email_code})
    if code3 != 200:
        raise SystemExit(f"factor 2 failed: {code3}")

    code4, body4 = _http_post(base, "/auth/login/verify-question",
                              {"challenge_id": challenge, "answer": answer})
    if code4 != 200:
        raise SystemExit(f"factor 3 failed: {code4}")
    return body4["access_token"]


async def run_browser_phase(base: str, token: str) -> None:
    """Drive a real Chromium window so the lab teacher SEES the bot work."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()

        # stash the token in sessionStorage before any frontend JS loads
        # so the homeworks page accepts us as a logged-in user
        await page.add_init_script(
            "sessionStorage.setItem('authToken', %s);" % json.dumps(token)
        )
        # also a minimal user object so utils/auth.js doesn't crash
        await page.add_init_script(
            "sessionStorage.setItem('currentUser', %s);" % json.dumps(json.dumps({
                "id": 2, "email": "user@proelev.ro", "name": "User Demo",
                "role": "user", "permissions": ["homework_read", "comment_create"],
            }))
        )

        # 1. visit the homeworks page so the lab teacher sees the bot present
        ui_base = base.replace(":8000", ":5173") if ":8000" in base else base
        try:
            await page.goto(f"{ui_base}/homeworks", wait_until="domcontentloaded", timeout=8000)
        except Exception:
            pass  # if the frontend isn't running we just keep attacking the api
        await asyncio.sleep(2)
        await browser.close()


def attack_phase(base: str, token: str, total: int = 80) -> None:
    """Fire a noisy mix of requests so the AI detector picks us up.

    - half are GETs to admin endpoints we are NOT allowed on (403 spam)
    - quarter are malformed POSTs (422 fuzz)
    - quarter are DELETEs to homeworks we don't own (404/403 mix)
    """
    print(f"\nfiring {total} requests to {base} as bot...")
    fired = {"sum": 0, "403": 0, "404": 0, "422": 0, "other": 0}
    paths = [
        ("GET",  "/admin/observations"),
        ("GET",  "/admin/logs"),
        ("GET",  "/admin/observations?include_dismissed=true"),
    ]
    bad_bodies = [
        {"email": 12345},                       # type error
        {"password": ["a", "b"]},               # type error
        {},                                     # missing fields
        {"x": "y" * 200},                       # unknown fields
    ]
    for i in range(total):
        kind = i % 4
        if kind < 2:
            method, path = random.choice(paths)
            code, _ = _http_get(base, path, token=token)
        elif kind == 2:
            code, _ = _http_post(base, "/auth/login", random.choice(bad_bodies))
        else:
            # delete a random homework id, the user doesnt have the perm
            code, _ = _http_post(base, f"/homeworks/{random.randint(1, 999)}", {}, token=token)
        fired["sum"] += 1
        fired[str(code)] = fired.get(str(code), 0) + 1
        if (i + 1) % 20 == 0:
            print(f"  fired {i+1}/{total}, status counts: {fired}")
        time.sleep(0.05)  # ~20 RPS, well under rate limit so we can pile up logs
    print(f"\ndone. final tally: {fired}")
    print("now open the admin panel and click 'Rulează detector AI'.")
    print("within ~30s, the background AI cycle will also flag this user.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Suspicious-user bot")
    ap.add_argument("--base",     default=DEFAULT_BASE, help="API base URL (default %(default)s)")
    ap.add_argument("--email",    default="user@proelev.ro")
    ap.add_argument("--password", default="Parola123")
    ap.add_argument("--answer",   default="proelev")
    ap.add_argument("--count",    type=int, default=80, help="how many noisy requests to fire")
    ap.add_argument("--no-browser", action="store_true",
                    help="skip the playwright browser phase, only fire the API attack")
    args = ap.parse_args()

    token = three_factor_login(args.base, args.email, args.password, args.answer)
    print(f"logged in as {args.email}, token len={len(token)}")

    if not args.no_browser:
        asyncio.run(run_browser_phase(args.base, token))

    attack_phase(args.base, token, total=args.count)


if __name__ == "__main__":
    main()
