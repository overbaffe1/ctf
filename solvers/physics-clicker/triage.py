#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Physics Clicker — быстрый триаж папки игры.

    python3 triage.py "C:\\CTF\\Physics Clicker"

Что делает (только чтение, ничего не запускает):
  1. дерево файлов с размерами и типами;
  2. поиск flag{...} по всем файлам (ASCII, UTF-8, UTF-16LE);
  3. поиск признаков Steam: steam_appid.txt, SteamDRMP.dll, вызовы SteamAPI_*,
     BIsSubscribedApp, SteamAPI_RestartAppIfNecessary;
  4. для .exe/.dll: PE-заголовок, секции, таблица импортов (если есть pefile);
  5. поиск строк, похожих на лицензионные проверки и на текст задания.

Ничего не меняет и не требует прав администратора.
"""

import os
import re
import sys
import struct

FLAG_RE = re.compile(rb"flag\{[^}\r\n]{1,160}\}")

STEAM_KEYS = [
    b"steam_appid", b"SteamAPI_Init", b"SteamAPI_RestartAppIfNecessary",
    b"SteamAPI_Shutdown", b"SteamUser", b"BIsSubscribedApp", b"BIsSubscribed",
    b"SteamDRMP", b"SteamClient", b"steam_api64", b"steam_api.dll",
    b"CheckAppOwnership", b"GetEarliestPurchaseUnixTime",
    b"SteamApps", b"workshop", b"appid",
]

TEXT_KEYS = [
    b"license", b"licence", b"activation", b"activat", b"trial",
    b"not purchased", b"no license", b"Steam is not running",
    b"key", b"serial", b"purchase",
]

SKIP_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".dds", ".wav", ".ogg",
            ".mp3", ".mp4", ".webm", ".ttf", ".otf", ".pak", ".bundle",
            ".zip", ".7z", ".rar"}

MAX_SCAN = 300 * 1024 * 1024      # не лезем в файлы больше 300 МБ


def human(n):
    for u in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or u == "ГБ":
            return ("%d %s" % (n, u)) if u == "Б" else ("%.1f %s" % (n, u))
        n /= 1024.0


def utf16_alts(patterns):
    out = []
    for p in patterns:
        out.append(p)
        out.append(p.decode("latin-1").encode("utf-16-le"))
    return out


def pe_info(path, data):
    """Мини-разбор PE без внешних библиотек."""
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    try:
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
            return None
        machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
        nsec = struct.unpack_from("<H", data, e_lfanew + 6)[0]
        tds = struct.unpack_from("<I", data, e_lfanew + 8)[0]
        opt_size = struct.unpack_from("<H", data, e_lfanew + 20)[0]
        magic = struct.unpack_from("<H", data, e_lfanew + 24)[0]
        sec_off = e_lfanew + 24 + opt_size
        secs = []
        for i in range(nsec):
            o = sec_off + i * 40
            name = data[o:o + 8].rstrip(b"\0").decode("latin-1", "replace")
            vsize, vaddr, rsize = struct.unpack_from("<III", data, o + 8)
            secs.append((name, vaddr, vsize, rsize))
        return {
            "arch": {0x8664: "x64", 0x14c: "x86"}.get(machine, hex(machine)),
            "pe32plus": magic == 0x20b,
            "timestamp": tds,
            "sections": secs,
        }
    except Exception:
        return None


def imports_of(path, data):
    try:
        import pefile  # noqa
    except ImportError:
        return None
    try:
        pe = pefile.PE(data=data, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        out = []
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) or []:
            dll = entry.dll.decode("latin-1", "replace")
            funcs = [imp.name.decode("latin-1", "replace")
                     for imp in entry.imports if imp.name]
            out.append((dll, funcs))
        return out
    except Exception:
        return None


def main():
    if len(sys.argv) < 2:
        print("нужно указать папку: python3 triage.py \"C:\\CTF\\Physics Clicker\"")
        return
    root = sys.argv[1]
    if not os.path.isdir(root):
        print("нет такой папки: %s" % root)
        return

    print("=" * 74)
    print("ДЕРЕВО ФАЙЛОВ: %s" % root)
    print("=" * 74)
    files = []
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            files.append((p, sz))
    files.sort(key=lambda x: -x[1])
    for p, sz in files[:60]:
        rel = os.path.relpath(p, root)
        print("  %10s  %s" % (human(sz), rel))
    print("  всего файлов: %d, суммарно %s" % (len(files), human(sum(s for _, s in files))))

    # ключевые файлы
    print()
    print("=" * 74)
    print("КЛЮЧЕВЫЕ ФАЙЛЫ")
    print("=" * 74)
    names = {os.path.basename(p).lower(): p for p, _ in files}
    for k in ("steam_appid.txt", "steam_api64.dll", "steam_api.dll", "steamdrmp.dll",
              "steamclient64.dll", "steamclient.dll", "steam_emu.ini", "coldclientloader.ini"):
        p = names.get(k)
        print("  %-22s %s" % (k, os.path.relpath(p, root) if p else "—"))
    exes = [p for p, _ in files if p.lower().endswith(".exe")]
    print("  exe: %s" % ", ".join(os.path.relpath(p, root) for p in exes[:10]))
    if names.get("steam_appid.txt"):
        try:
            print("  steam_appid.txt -> %r" % open(names["steam_appid.txt"]).read().strip()[:40])
        except Exception as e:
            print("  steam_appid.txt прочитать не удалось: %s" % e)

    # сканирование
    print()
    print("=" * 74)
    print("ПОИСК: флаги, Steam, лицензии")
    print("=" * 74)
    flags, steam_hits, text_hits = set(), {}, {}

    for p, sz in files:
        if sz > MAX_SCAN:
            continue
        ext = os.path.splitext(p)[1].lower()
        if ext in SKIP_EXT:
            continue
        try:
            with open(p, "rb") as f:
                data = f.read()
        except Exception:
            continue
        rel = os.path.relpath(p, root)

        for m in FLAG_RE.findall(data):
            flags.add(m.decode("latin-1", "replace"))
        # UTF-16 вариант флага
        u16 = data.decode("utf-16-le", "ignore")
        for m in re.findall(r"flag\{[^}\r\n]{1,160}\}", u16):
            flags.add(m + "  (utf-16)")

        for key in utf16_alts(STEAM_KEYS):
            if key in data:
                label = key.decode("latin-1", "replace").replace("\x00", "")
                steam_hits.setdefault(label, set()).add(rel)

        if ext in (".exe", ".dll", ".txt", ".cfg", ".ini", ".json", ".py", ".cs", ".gd"):
            for key in utf16_alts(TEXT_KEYS):
                if key in data.lower():
                    label = key.decode("latin-1", "replace").replace("\x00", "")
                    text_hits.setdefault(label, set()).add(rel)

    print("\n  ФЛАГИ:")
    if flags:
        for f in sorted(flags):
            print("    %s" % f)
    else:
        print("    не найдено (вероятно, флаг появляется только в запущенной игре)")

    print("\n  STEAM-ПРИЗНАКИ:")
    for k in sorted(steam_hits, key=lambda x: -len(steam_hits[x])):
        where = sorted(steam_hits[k])[:3]
        print("    %-32s %s" % (k, ", ".join(where)))

    print("\n  ЛИЦЕНЗИОННЫЕ СЛОВА:")
    for k in sorted(text_hits, key=lambda x: -len(text_hits[x]))[:12]:
        where = sorted(text_hits[k])[:3]
        print("    %-20s %s" % (k, ", ".join(where)))

    # PE
    print()
    print("=" * 74)
    print("PE-ФАЙЛЫ")
    print("=" * 74)
    for p, sz in files:
        if not p.lower().endswith((".exe", ".dll")):
            continue
        try:
            data = open(p, "rb").read() if sz <= 80 * 1024 * 1024 else b""
        except Exception:
            continue
        info = pe_info(p, data) if data else None
        if not info:
            continue
        rel = os.path.relpath(p, root)
        print("  %s  [%s%s, секций %d]"
              % (rel, info["arch"], "+" if info["pe32plus"] else "",
                 len(info["sections"])))
        imps = imports_of(p, data)
        if imps:
            for dll, funcs in imps:
                if "steam" in dll.lower():
                    print("      импорт: %s" % dll)
                    for fn in funcs:
                        if "steam" in fn.lower() or "App" in fn or "Sub" in fn:
                            print("        - %s" % fn)
        else:
            print("      (pefile не установлен: pip install pefile — покажет импорты)")

    print()
    print("Готово. Если в STEAM-ПРИЗНАКАХ есть BIsSubscribedApp/SteamAPI_RestartAppIfNecessary,")
    print("а флагов нет — игру надо запускать через эмулятор Steam.")


if __name__ == "__main__":
    main()
