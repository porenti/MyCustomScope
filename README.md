<div align="center">

# myCustomScope

**Бесплатный оверлей прицела для Windows · Free crosshair overlay for Windows**

[🇷🇺 Русский](#-русский) · [🇬🇧 English](#-english) · [🛠 Tech](#-technical)

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

---

## 🇷🇺 Русский

Бесплатный прицел-оверлей для Windows — отображает настраиваемый прицел поверх любого окна или игры без установки. Работает в оконном и безрамочном полноэкранном режиме, не перехватывает мышь. 6 типов прицела, настройка цвета и размера, горячая клавиша, поддержка нескольких мониторов.

### Запуск

1. Скачайте `myCustomScope.exe` из [Releases](../../releases/latest)
2. Запустите и подтвердите UAC-запрос
3. Иконка в трее — прицел включается клавишей **F6**

---

## 🇬🇧 English

Free crosshair overlay for Windows — renders a customizable crosshair on top of any window or game, no installation required. Works in windowed and borderless fullscreen, fully click-through. Six crosshair styles, color and size controls, rebindable hotkey, multi-monitor support.

### Quick start

1. Download `myCustomScope.exe` from [Releases](../../releases/latest)
2. Run it and confirm the UAC prompt
3. App icon appears in the tray — press **F6** to toggle the crosshair

---

## 🛠 Technical

| | |
|---|---|
| GUI & rendering | PyQt6 |
| Global hotkeys | keyboard |
| Packaging | PyInstaller `--onefile --uac-admin` |

**Key implementation details:**
- Click-through overlay via `WS_EX_LAYERED | WS_EX_TRANSPARENT` (ctypes)
- Single-instance enforcement via `QLocalSocket` / `QLocalServer` IPC
- Hotkey events bridged from background thread to Qt main loop via `pyqtSignal`
- Settings persisted to `%APPDATA%\myCustomScope\settings.ini` with 400 ms debounced writes

**Build from source:**
```bat
setup.bat   # create venv + install deps
build.bat   # produces dist\myCustomScope.exe
```

---

MIT License
