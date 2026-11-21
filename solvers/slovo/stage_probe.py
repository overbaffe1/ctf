#!/usr/bin/env python3
"""Передатчик К-5: проверка гипотезы о содержимом station.img.

Факты, установленные на стенде (см. writeups/tasks/slovo-v-efire.md):
  * emit(station, frame) -> 18497 тактов x 3 байта;
  * byte0/byte1 (номера рабочих/опорных головок) зависят ТОЛЬКО от station.img,
    байты station[32..75]; байты station[0..31] управляют только byte2 (модулятор);
    frame.bin в byte0/byte1 не входит вообще;
  * byte1 = (byte0 + 5) mod 13;
  * поэтому восстановить кадр из журнала можно только зная station.img
    ("начальная настройка и калибровка передатчика берутся из предыдущего задания").

Скрипт берёт кандидат (строку-ответ предыдущего задания), строит из неё
128-байтовую кассету несколькими распространёнными способами и меряет,
насколько b0/b1 согласуются с журналом (таблица соответствий «головка -> набор
поддиапазонов» в каждом такте).
"""
import hashlib, subprocess, sys, collections, csv, os, tempfile

TX = "/tmp/uro/mm/transmitter"       # или путь к ./transmitter
STATION_LEN, NBEATS_POSSIBLE = 128, 18497

def station_candidates(s: str):
    b = s.encode()
    yield "raw-pad0", b[:128].ljust(128, b"\0")
    h = hashlib.sha256(b).digest(); yield "sha256x4", (h * 4)[:128]
    yield "sha256+sha256b", (h + hashlib.sha256(h).digest())[:128]
    md5 = hashlib.md5(b).digest(); yield "md5x8", (md5 * 8)[:128]
    yield "ascii+zeros", b[:32].ljust(128, b"\0")
    yield "flag-body", b.split(b"{")[-1].rstrip(b"}")[:128].ljust(128, b"\0")

def emit(station: bytes, frame: bytes = bytes(1536), tmp="/tmp/slovo_probe"):
    os.makedirs(tmp, exist_ok=True)
    open(f"{tmp}/st.img", "wb").write(station)
    open(f"{tmp}/fr.bin", "wb").write(frame)
    r = subprocess.run([TX, "emit", f"{tmp}/st.img", f"{tmp}/fr.bin", f"{tmp}/sy.bin"],
                       cwd=os.path.dirname(TX), capture_output=True)
    if r.returncode:
        return None
    d = open(f"{tmp}/sy.bin", "rb").read()
    return [(d[i], d[i + 1], d[i + 2]) for i in range(0, len(d), 3)]

def journal_signature(path="/tmp/z.csv"):
    bands = None
    beats = collections.OrderedDict()
    for row in list(csv.reader(open(path, encoding="utf-8"), delimiter=";"))[1:]:
        s, t, band, lvl, typ, cel = row
        beats.setdefault((int(s), float(t)), []).append((band, float(lvl), typ))
    return list(beats.values())          # порядок тактов = порядок в журнале

def score(sym, jbeats):
    """Для каждого такта: совпадает ли b0 с поддиапазоном головки А/Б/В (любой)."""
    hits = collections.Counter(); n = 0
    per_head = collections.Counter()
    for (b0, b1, mod), rows in zip(sym, jbeats):
        bands_of = collections.defaultdict(set)
        for band, lvl, typ in rows:
            bands_of[typ].add(band)
        idx_of = {b: i for i, b in enumerate(sorted({r[0] for r in rows},
                                                   key=lambda x: int(x.split("-")[0])))}
        i0 = None
        for band, lvl, typ in rows:
            pass
        n += 1
        for typ, bs in bands_of.items():
            if len(bs) == b0 or len(bs) == b1:
                hits[typ] += 1
    return hits, n

if __name__ == "__main__":
    cands = sys.argv[1:] or ["flag{test}"]
    jb = journal_signature()
    for c in cands:
        for name, st in station_candidates(c):
            sym = emit(st)
            if sym is None:
                print(f"{c!r:40} {name:16} emit-failed"); continue
            h, n = score(sym, jb)
            print(f"{c!r:40} {name:16} b0-dist={collections.Counter(x[0] for x in sym).most_common(3)} head-band-size hits={dict(h)}")
