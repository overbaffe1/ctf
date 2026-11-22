# Physics Clicker — запуск без лицензии Steam

## Быстрый ответ

**Удали `steam_api64.dll` из папки игры.** Мотор (GacUI/KlayGE-подобный, `config.json` с `uuid`, `core.src`/`main.src`)
грузит Steam **опционально**: `PC.exe` импортирует `SteamInternal_SteamAPI_Init`, но сам решает, звать ли его.
`SteamAPI_RestartAppIfNecessary` тоже вызывается только если Steam вообще поднялся.

Без dll игра идёт по «пиратской» ветке: лицензия считается отсутствующей, и именно там она просит
активацию. Мой патченный `steam_api64.dll` держит инициализацию успешной, и игра уходит в ветку
«лицензия есть», где ждёт настоящий Steam-клиент — отсюда мгновенное закрытие.

## Готовая папка

`game/` — распакованная игра **без** `steam_api64.dll`:

```
PC.exe  config.json  core.src  main.src  d3dcompiler_47.dll  xaudio2_9redist.dll
```

Скачай `game/` и запусти `PC.exe`. Если всё равно закрывается — верни dll из `game_with_dll/`
(там лежит оригинальная валвовская, не патченная).

## Что было проверено на файлах (без запуска)

- `PC.exe` — x64, подсистема GUI, импортирует из `steam_api64.dll` только:
  `SteamAPI_Init`, `SteamInternal_SteamAPI_Init`, `SteamAPI_RestartAppIfNecessary`,
  `SteamAPI_GetHSteamUser`, `SteamAPI_RunCallbacks`, `Register/UnregisterCallback`,
  `Register/UnregisterCallResult`, `FindOrCreateUserInterface`, `ContextInit`, `Shutdown`.
  **Ни одного `ISteamApps_*`** — прямых вызовов проверки подписки из exe нет.
- `engine.log` содержит только строку про старт логгера → процесс успел инициализироваться и упал позже.
- `steam_api64.dll` (317 080 байт, 1054 экспорта) — оригинальная валвовская.

## Если понадобится патчить dll

`patch_dll.py` заменяет 12 экспортов (`BIsSubscribedApp` → 1, `RestartAppIfNecessary` → 0 и т.д.).
Готовый файл: `steam_api64_patched.dll`. Но, судя по импортам exe, игра его не спрашивает —
поэтому основной путь это **удалить dll**, а не патчить.
