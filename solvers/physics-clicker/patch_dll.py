#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Physics Clicker — снятие проверки лицензии Steam с оригинальной steam_api64.dll.

Ничего не эмулирует и не требует запущенного Steam: патчим только те экспорты,
через которые игра спрашивает «куплено ли».

    python3 patch_dll.py steam_api64.dll steam_api64_patched.dll

Что патчится (по ИМЕНАМ ЭКСПОРТОВ, а не по смещениям — работает на любой версии):
    SteamAPI_RestartAppIfNecessary          -> return 0  (не перезапускать через Steam)
    SteamAPI_ISteamApps_BIsSubscribedApp    -> return 1
    SteamAPI_ISteamApps_BIsSubscribed       -> return 1
    SteamAPI_ISteamApps_BIsAppInstalled     -> return 1
    SteamAPI_ISteamApps_BIsDlcInstalled     -> return 1
    SteamAPI_ISteamApps_BIsSubscribedFromFreeWeekend -> return 0
    SteamAPI_ISteamApps_BIsTimedTrial       -> return 0
    SteamAPI_ISteamApps_BIsVACBanned        -> return 0
    SteamAPI_ISteamApps_GetEarliestPurchaseUnixTime -> 1577836800 (2020-01-01)

Оригинал не трогается, результат пишется в отдельный файл.
"""

import sys
import struct

try:
    import pefile
except ImportError:
    sys.exit("нужен pefile: pip install pefile")


# имя экспорта -> байты-заглушка (x64)
PATCHES = {
    # return 0
    "SteamAPI_RestartAppIfNecessary":                        b"\x31\xc0\xc3",              # xor eax,eax; ret
    "SteamAPI_ISteamApps_BIsSubscribedFromFreeWeekend":      b"\x31\xc0\xc3",
    "SteamAPI_ISteamApps_BIsTimedTrial":                     b"\x31\xc0\xc3",
    "SteamAPI_ISteamApps_BIsVACBanned":                      b"\x31\xc0\xc3",
    "SteamAPI_ISteamApps_BIsCybercafe":                      b"\x31\xc0\xc3",
    "SteamAPI_ISteamApps_BIsLowViolence":                    b"\x31\xc0\xc3",
    # return 1
    "SteamAPI_ISteamApps_BIsSubscribedApp":                  b"\xb8\x01\x00\x00\x00\xc3",  # mov eax,1; ret
    "SteamAPI_ISteamApps_BIsSubscribed":                     b"\xb8\x01\x00\x00\x00\xc3",
    "SteamAPI_ISteamApps_BIsAppInstalled":                   b"\xb8\x01\x00\x00\x00\xc3",
    "SteamAPI_ISteamApps_BIsDlcInstalled":                   b"\xb8\x01\x00\x00\x00\xc3",
    "SteamAPI_ISteamApps_BIsSubscribedFromFamilySharing":    b"\xb8\x01\x00\x00\x00\xc3",
    # дата покупки: 1577836800 = 2020-01-01 00:00:00 UTC
    "SteamAPI_ISteamApps_GetEarliestPurchaseUnixTime":
        b"\xb8" + struct.pack("<I", 1577836800) + b"\xc3",                                   # mov eax,imm32; ret
}


def rva_to_off(pe, rva):
    """pefile отдаёт адреса экспортов уже как RVA — вычитать ImageBase не нужно."""
    return pe.get_offset_from_rva(rva)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + "_patched.dll"

    pe = pefile.PE(src, fast_load=True)
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]]
    )
    if not hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        sys.exit("в файле нет таблицы экспортов — это не steam_api64.dll")

    exports = {}
    for s in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if s.name:
            exports[s.name.decode()] = s.address

    data = bytearray(open(src, "rb").read())
    print("файл: %s (%d байт)" % (src, len(data)))
    print("архитектура: %s" % {0x8664: "x64", 0x14c: "x86"}.get(pe.FILE_HEADER.Machine, "?"))
    print("экспортов: %d" % len(exports))
    print()

    done, missed = 0, []
    for name, patch in PATCHES.items():
        if name not in exports:
            missed.append(name)
            continue
        off = rva_to_off(pe, exports[name])
        old = bytes(data[off:off + len(patch)])
        # длину хвоста тоже обнуляем, чтобы не осталось «мусорных» инструкций
        tail = 0
        if len(patch) <= 8 and old[:len(patch)] != patch:
            # стираем до 8 байт (заглушка короче исходного трамплина)
            span = max(len(patch), 6)
            data[off:off + span] = patch + b"\xcc" * (span - len(patch))
            tail = span
        else:
            data[off:off + len(patch)] = patch
            tail = len(patch)
        print("  %-48s RVA=0x%06X off=0x%06X  было: %-20s -> %s"
              % (name, exports[name], off, old.hex(" ") or "(пусто!)", patch.hex(" ")))
        done += 1

    open(dst, "wb").write(bytes(data))
    print()
    print("пропатчено: %d" % done)
    if missed:
        print("не найдено в экспортах (пропущено): %s" % ", ".join(missed))
    print("результат: %s" % dst)
    print()
    print("Дальше:")
    print("  1. закрой игру;")
    print("  2. рядом с exe переименуй оригинал: steam_api64.dll -> steam_api64.dll.orig")
    print("  3. положи этот файл как steam_api64.dll;")
    print("  4. запускай exe напрямую, Steam можно не запускать.")


if __name__ == "__main__":
    main()
