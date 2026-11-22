# Physics Clicker — снять проверку лицензии Steam

## Что в папке
- `steam_api64_patched.dll` — оригинальная валвовская `steam_api64.dll` (x64, 1054 экспорта, 317 080 байт)
  с вырезанными проверками лицензии. Остальные 72 байта файла идентичны оригиналу.
- `patch_dll.py` — тот же патч в виде скрипта (позволяет пересобрать на любой версии dll).
- `triage.py` — осмотр папки игры: флаги, Steam-признаки, PE-заголовки.

## Что именно пропатчено (по именам экспортов, RVA → файловое смещение)
| экспорт | было | стало |
|---|---|---|
| `SteamAPI_RestartAppIfNecessary` | `push rbp; push rbx; ...` | `xor eax,eax; ret` (0) |
| `SteamAPI_ISteamApps_BIsSubscribedApp` | `mov rax,[rcx]; jmp [rax+0x30]` | `mov eax,1; ret` |
| `SteamAPI_ISteamApps_BIsSubscribed` | трамплин | `mov eax,1; ret` |
| `SteamAPI_ISteamApps_BIsAppInstalled` | трамплин | `mov eax,1; ret` |
| `SteamAPI_ISteamApps_BIsDlcInstalled` | трамплин | `mov eax,1; ret` |
| `SteamAPI_ISteamApps_BIsSubscribedFromFamilySharing` | трамплин | `mov eax,1; ret` |
| `SteamAPI_ISteamApps_BIsTimedTrial` | трамплин | `xor eax,eax; ret` (0) |
| `SteamAPI_ISteamApps_BIsVACBanned` | трамплин | `xor eax,eax; ret` (0) |
| `SteamAPI_ISteamApps_BIsCybercafe` | трамплин | `xor eax,eax; ret` (0) |
| `SteamAPI_ISteamApps_BIsLowViolence` | трамплин | `xor eax,eax; ret` (0) |
| `SteamAPI_ISteamApps_BIsSubscribedFromFreeWeekend` | трамплин | `xor eax,eax; ret` (0) |
| `SteamAPI_ISteamApps_GetEarliestPurchaseUnixTime` | трамплин | `mov eax,1577836800; ret` (2020-01-01) |

Проверено: 72 изменённых байта, все внутри `.text`, PE валиден, таблица экспортов цела.

## Установка
1. Закрыть игру.
2. В папке с exe: `steam_api64.dll` → `steam_api64.dll.orig` (на случай отката).
3. Положить `steam_api64_patched.dll` рядом и переименовать в `steam_api64.dll`.
4. Запускать exe **напрямую**, Steam запускать не нужно.

## Важно
Если игра всё равно просит лицензию — значит проверка идёт не через `steam_api64.dll`,
а внутри монетизации Unity (`UnityEngine.Purchasing` / `Steamworks.NET` в `Assembly-CSharp.dll`),
либо через Steam DRM-обёртку (`SteamDRMP.dll`). Тогда:
- для DRM — снять обёртку Steamless (`atom0s/Steamless`);
- для проверки внутри управляемого кода — смотреть `*_Data/Managed/Assembly-CSharp.dll`
  через dnSpy/ILSpy и искать `BIsSubscribedApp` / `SteamApps`.
