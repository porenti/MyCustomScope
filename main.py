#!/usr/bin/env python3
"""Crosshair Overlay — gaming crosshair overlay with system tray."""

import os
import sys
import ctypes
from contextlib import contextmanager
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSlider, QComboBox, QPushButton, QSystemTrayIcon, QMenu,
    QRadioButton, QButtonGroup, QGroupBox, QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, QObject, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import (
    QIcon, QColor, QPainter, QPen, QBrush, QPixmap,
)
import keyboard


# ── Configuration ─────────────────────────────────────────────────────────────

CROSSHAIR_KEYS: list[str] = ["dot", "plus", "plus_dot", "cross", "square", "plus_spaced"]

DEFAULT_SIZE  = 20
TOGGLE_HOTKEY = "F6"
DEFAULT_LANG  = "ru"

_APPDATA = os.path.join(os.environ.get("APPDATA", "."), "CrosshairOverlay")
os.makedirs(_APPDATA, exist_ok=True)
SETTINGS_PATH = os.path.join(_APPDATA, "settings.ini")

STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "window_title":   "Crosshair Overlay",
        "lang_group":     "Язык",
        "lang_ru":        "Русский",
        "lang_en":        "English",
        "type_group":     "Тип прицела",
        "ct_dot":         "Точка",
        "ct_plus":        "Плюс (+)",
        "ct_plus_dot":    "Плюс с точкой",
        "ct_cross":       "Крест (×)",
        "ct_square":      "Квадрат",
        "ct_plus_spaced": "Плюс с отступами",
        "monitor_group":  "Монитор",
        "monitor_item":   "Монитор {n}  ({w}×{h})",
        "size_group":     "Размер прицела",
        "color_group":    "Цвет",
        "hotkey_group":   "Горячая клавиша",
        "hotkey_label":   "Вкл / Выкл:",
        "hotkey_change":  "Изменить",
        "hotkey_capture": "Нажмите…",
        "toggle_on":      "Включить прицел",
        "toggle_off":     "Выключить прицел",
        "close_text":     "Что сделать?",
        "close_tray":     "Свернуть в трей",
        "close_exit":     "Завершить",
        "tray_settings":  "Настройки",
        "tray_toggle":    "Вкл / Выкл  ({hk})",
        "tray_exit":      "Выход",
    },
    "en": {
        "window_title":   "Crosshair Overlay",
        "lang_group":     "Language",
        "lang_ru":        "Русский",
        "lang_en":        "English",
        "type_group":     "Crosshair Type",
        "ct_dot":         "Dot",
        "ct_plus":        "Plus (+)",
        "ct_plus_dot":    "Plus with Dot",
        "ct_cross":       "Cross (×)",
        "ct_square":      "Square",
        "ct_plus_spaced": "Plus with Gap",
        "monitor_group":  "Monitor",
        "monitor_item":   "Monitor {n}  ({w}×{h})",
        "size_group":     "Crosshair Size",
        "color_group":    "Color",
        "hotkey_group":   "Hotkey",
        "hotkey_label":   "Toggle:",
        "hotkey_change":  "Change",
        "hotkey_capture": "Press…",
        "toggle_on":      "Enable Crosshair",
        "toggle_off":     "Disable Crosshair",
        "close_text":     "What would you like to do?",
        "close_tray":     "Minimize to Tray",
        "close_exit":     "Exit",
        "tray_settings":  "Settings",
        "tray_toggle":    "Toggle  ({hk})",
        "tray_exit":      "Exit",
    },
}


@contextmanager
def _blocked(widgets):
    """Temporarily block Qt signals on a sequence of QObjects."""
    ws = list(widgets)
    for w in ws:
        w.blockSignals(True)
    try:
        yield
    finally:
        for w in ws:
            w.blockSignals(False)


def make_app_icon() -> QIcon:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "icon.ico")
    if os.path.exists(path):
        return QIcon(path)

    # Fallback for dev runs without bundled assets.
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(0, 255, 0), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(16, 3,  16, 13)
    p.drawLine(16, 19, 16, 29)
    p.drawLine(3,  16, 13, 16)
    p.drawLine(19, 16, 29, 16)
    p.setBrush(QBrush(QColor(0, 255, 0)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(13, 13, 6, 6)
    p.end()
    return QIcon(px)


# ── Persistent settings ───────────────────────────────────────────────────────

class AppSettings:
    def __init__(self) -> None:
        self._qs = QSettings(SETTINGS_PATH, QSettings.Format.IniFormat)

    def save(self, window: "SettingsWindow", active: bool, hotkey: str) -> None:
        self._qs.setValue("crosshair/type",  window.get_crosshair_type())
        self._qs.setValue("crosshair/size",  window.get_size())
        color = window.get_color()
        self._qs.setValue("crosshair/r",     color.red())
        self._qs.setValue("crosshair/g",     color.green())
        self._qs.setValue("crosshair/b",     color.blue())
        self._qs.setValue("display/monitor", window.get_monitor_index())
        self._qs.setValue("state/active",    active)
        self._qs.setValue("hotkey/toggle",   hotkey)
        self._qs.setValue("ui/lang",         window._lang)
        self._qs.sync()

    def load(self, window: "SettingsWindow") -> tuple[bool, str, str]:
        def _int(key: str, default: int) -> int:
            try:
                return int(self._qs.value(key, default))
            except (TypeError, ValueError):
                return default

        ct = self._qs.value("crosshair/type", "dot")
        for btn in window.type_group.buttons():
            if btn.property("ct_key") == ct:
                btn.setChecked(True)
                break

        window.size_slider.setValue(_int("crosshair/size", DEFAULT_SIZE))
        window._sliders["R"].setValue(_int("crosshair/r", 0))
        window._sliders["G"].setValue(_int("crosshair/g", 255))
        window._sliders["B"].setValue(_int("crosshair/b", 0))

        monitor_idx = _int("display/monitor", 0)
        if monitor_idx < window.monitor_combo.count():
            window.monitor_combo.setCurrentIndex(monitor_idx)

        active = str(self._qs.value("state/active",  "false")).lower() == "true"
        hotkey = str(self._qs.value("hotkey/toggle", TOGGLE_HOTKEY))
        lang   = str(self._qs.value("ui/lang",       DEFAULT_LANG))
        if lang not in STRINGS:
            lang = DEFAULT_LANG
        return active, hotkey, lang


# ── Thread-safe hotkey forwarder ──────────────────────────────────────────────

class _HotkeySignaler(QObject):
    toggled = pyqtSignal()


class _HotkeyCapture(QThread):
    captured = pyqtSignal(str)

    def run(self) -> None:
        try:
            key = keyboard.read_hotkey(suppress=False)
            self.captured.emit(key)
        except Exception as exc:
            print(f"[warn] hotkey capture failed: {exc}")


# ── Crosshair overlay window ──────────────────────────────────────────────────

class CrosshairOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.crosshair_type = "dot"
        self.color          = QColor(0, 255, 0)
        self.size           = DEFAULT_SIZE
        self._stroke_w      = max(1, DEFAULT_SIZE // 8)
        self._pen           = QPen(self.color, self._stroke_w, Qt.PenStyle.SolidLine,
                                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        self._brush         = QBrush(self.color)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def show_on_screen(self, screen) -> None:
        self.setGeometry(screen.geometry())
        self.show()
        self._make_click_through()

    def apply_settings(self, crosshair_type: str, color: QColor, size: int) -> None:
        self.crosshair_type = crosshair_type
        self.color          = color
        self.size           = size
        self._stroke_w      = max(1, size // 8)
        self._pen           = QPen(color, self._stroke_w, Qt.PenStyle.SolidLine,
                                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        self._brush         = QBrush(color)
        self.update()

    def _make_click_through(self) -> None:
        try:
            hwnd  = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020)
        except Exception:
            pass

    @staticmethod
    def _draw_plus_lines(p: QPainter, cx: int, cy: int, half: int, gap: int) -> None:
        p.drawLine(cx - half, cy, cx - gap, cy)
        p.drawLine(cx + gap,  cy, cx + half, cy)
        p.drawLine(cx, cy - half, cx, cy - gap)
        p.drawLine(cx, cy + gap,  cx, cy + half)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p  = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width()  // 2
        cy = self.height() // 2
        s  = self.size
        p.setPen(self._pen)

        if self.crosshair_type == "dot":
            r = max(2, s // 3)
            p.setBrush(self._brush)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        elif self.crosshair_type == "plus":
            self._draw_plus_lines(p, cx, cy, s // 2, max(2, s // 6))

        elif self.crosshair_type == "plus_dot":
            w   = self._stroke_w
            r   = w // 2
            gap = r + w + 2
            self._draw_plus_lines(p, cx, cy, s // 2, gap)
            p.setBrush(self._brush)
            p.setPen(Qt.PenStyle.NoPen)
            if r > 0:
                p.drawRect(cx - r, cy - r, r * 2, r * 2)
            else:
                p.fillRect(cx, cy, 1, 1, self.color)

        elif self.crosshair_type == "cross":
            half = s // 2
            gap  = max(2, s // 6)
            d    = int(half * 0.707)
            dg   = int(gap  * 0.707)
            p.drawLine(cx - d,  cy - d,  cx - dg, cy - dg)
            p.drawLine(cx + dg, cy + dg, cx + d,  cy + d)
            p.drawLine(cx + d,  cy - d,  cx + dg, cy - dg)
            p.drawLine(cx - dg, cy + dg, cx - d,  cy + d)

        elif self.crosshair_type == "square":
            half = s // 2
            p.setBrush(self._brush)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(cx - half, cy - half, s, s)

        elif self.crosshair_type == "plus_spaced":
            self._draw_plus_lines(p, cx, cy, s // 2, max(2, s // 5))

        p.end()


# ── Settings window ───────────────────────────────────────────────────────────

class SettingsWindow(QMainWindow):
    lang_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang           = DEFAULT_LANG
        self._overlay_active = False
        self._capturing      = False
        self.setFixedSize(380, 630)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self._build_ui()
        self._apply_theme()

    def _tr(self, key: str, **kwargs) -> str:
        s = STRINGS[self._lang].get(key, key)
        return s.format(**kwargs) if kwargs else s

    def closeEvent(self, event) -> None:  # noqa: N802
        box = QMessageBox(self)
        box.setWindowTitle(self._tr("window_title"))
        box.setText(self._tr("close_text"))
        btn_tray = box.addButton(self._tr("close_tray"), QMessageBox.ButtonRole.ResetRole)
        btn_exit = box.addButton(self._tr("close_exit"), QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(btn_tray)
        box.exec()
        if box.clickedButton() is btn_exit:
            QApplication.instance().quit()
        else:
            event.ignore()
            self.hide()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(self._make_lang_group())
        layout.addWidget(self._make_type_group())
        layout.addWidget(self._make_monitor_group())
        layout.addWidget(self._make_size_group())
        layout.addWidget(self._make_color_group())
        layout.addWidget(self._make_hotkey_group())
        layout.addWidget(self._make_toggle_btn())

    def _make_lang_group(self) -> QGroupBox:
        g = QGroupBox(self._tr("lang_group"))
        self._lang_grp = g
        lay = QHBoxLayout(g)
        self._lang_btn_group = QButtonGroup()
        for code in ("ru", "en"):
            rb = QRadioButton(self._tr(f"lang_{code}"))
            rb.setProperty("lang_code", code)
            if code == self._lang:
                rb.setChecked(True)
            self._lang_btn_group.addButton(rb)
            lay.addWidget(rb)
        self._lang_btn_group.buttonToggled.connect(self._on_lang_btn_toggled)
        return g

    def _make_type_group(self) -> QGroupBox:
        g = QGroupBox(self._tr("type_group"))
        self._type_grp = g
        lay = QGridLayout(g)
        lay.setSpacing(6)
        self.type_group = QButtonGroup()
        for idx, key in enumerate(CROSSHAIR_KEYS):
            rb = QRadioButton(self._tr(f"ct_{key}"))
            rb.setProperty("ct_key", key)
            if key == "dot":
                rb.setChecked(True)
            self.type_group.addButton(rb)
            lay.addWidget(rb, idx // 2, idx % 2)
        return g

    def _make_monitor_group(self) -> QGroupBox:
        g = QGroupBox(self._tr("monitor_group"))
        self._monitor_grp = g
        lay = QHBoxLayout(g)
        self.monitor_combo = QComboBox()
        self._screen_geos: list[tuple[int, int]] = []
        for i, s in enumerate(QApplication.screens()):
            geo = s.geometry()
            self._screen_geos.append((geo.width(), geo.height()))
            self.monitor_combo.addItem(
                self._tr("monitor_item", n=i + 1, w=geo.width(), h=geo.height()), i
            )
        lay.addWidget(self.monitor_combo)
        return g

    def _make_size_group(self) -> QGroupBox:
        g = QGroupBox(self._tr("size_group"))
        self._size_grp = g
        lay = QHBoxLayout(g)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(4, 80)
        self.size_slider.setValue(DEFAULT_SIZE)
        self._size_lbl = QLabel(str(DEFAULT_SIZE))
        self._size_lbl.setFixedWidth(28)
        self.size_slider.valueChanged.connect(lambda v: self._size_lbl.setText(str(v)))
        lay.addWidget(self.size_slider)
        lay.addWidget(self._size_lbl)
        return g

    def _make_color_group(self) -> QGroupBox:
        g = QGroupBox(self._tr("color_group"))
        self._color_grp = g
        lay = QGridLayout(g)
        lay.setSpacing(6)
        lay.setColumnStretch(1, 1)

        self._sliders: dict[str, QSlider] = {}
        self._ch_labels: dict[str, QLabel] = {}
        defaults = {"R": 0, "G": 255, "B": 0}

        for row_idx, ch in enumerate(("R", "G", "B")):
            ch_lbl = QLabel(ch)
            ch_lbl.setFixedWidth(14)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 255)
            sl.setValue(defaults[ch])
            val_lbl = QLabel(str(defaults[ch]))
            val_lbl.setFixedWidth(28)
            sl.valueChanged.connect(self._on_color_changed)
            self._sliders[ch]   = sl
            self._ch_labels[ch] = val_lbl
            lay.addWidget(ch_lbl,  row_idx, 0)
            lay.addWidget(sl,      row_idx, 1)
            lay.addWidget(val_lbl, row_idx, 2)

        self.color_preview = QFrame()
        self.color_preview.setObjectName("colorPreview")
        self.color_preview.setFixedWidth(40)
        self.color_preview.setStyleSheet("background: rgb(0,255,0); border-radius: 4px;")
        lay.addWidget(self.color_preview, 0, 3, 3, 1)
        return g

    def _make_hotkey_group(self) -> QGroupBox:
        g = QGroupBox(self._tr("hotkey_group"))
        self._hotkey_grp = g
        lay = QHBoxLayout(g)
        self._hotkey_prefix_lbl = QLabel(self._tr("hotkey_label"))
        lay.addWidget(self._hotkey_prefix_lbl)
        self.hotkey_lbl = QLabel(f"<b>{TOGGLE_HOTKEY}</b>")
        self.hotkey_lbl.setStyleSheet("color: #7aa2f7; font-size: 13px; min-width: 46px;")
        lay.addWidget(self.hotkey_lbl)
        lay.addStretch()
        self.hotkey_change_btn = QPushButton(self._tr("hotkey_change"))
        self.hotkey_change_btn.setObjectName("changeBtn")
        self.hotkey_change_btn.setFixedWidth(90)
        lay.addWidget(self.hotkey_change_btn)
        return g

    def _make_toggle_btn(self) -> QPushButton:
        self.toggle_btn = QPushButton(self._tr("toggle_on"))
        self.toggle_btn.setObjectName("toggleBtn")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setFixedHeight(42)
        return self.toggle_btn

    def _on_lang_btn_toggled(self, btn: QRadioButton, checked: bool) -> None:
        if not checked:
            return
        self._lang = btn.property("lang_code")
        self._retranslate()
        self.lang_changed.emit(self._lang)

    def _retranslate(self) -> None:
        self.setWindowTitle(self._tr("window_title"))
        self._lang_grp.setTitle(self._tr("lang_group"))
        for btn in self._lang_btn_group.buttons():
            btn.setText(self._tr(f"lang_{btn.property('lang_code')}"))
        self._type_grp.setTitle(self._tr("type_group"))
        for btn in self.type_group.buttons():
            btn.setText(self._tr(f"ct_{btn.property('ct_key')}"))
        self._monitor_grp.setTitle(self._tr("monitor_group"))
        for i, (w, h) in enumerate(self._screen_geos):
            self.monitor_combo.setItemText(i, self._tr("monitor_item", n=i + 1, w=w, h=h))
        self._size_grp.setTitle(self._tr("size_group"))
        self._color_grp.setTitle(self._tr("color_group"))
        self._hotkey_grp.setTitle(self._tr("hotkey_group"))
        self._hotkey_prefix_lbl.setText(self._tr("hotkey_label"))
        self.hotkey_change_btn.setText(
            self._tr("hotkey_capture") if self._capturing else self._tr("hotkey_change")
        )
        self.toggle_btn.setText(
            self._tr("toggle_off") if self._overlay_active else self._tr("toggle_on")
        )

    def _on_color_changed(self) -> None:
        r = self._sliders["R"].value()
        g = self._sliders["G"].value()
        b = self._sliders["B"].value()
        self._ch_labels["R"].setText(str(r))
        self._ch_labels["G"].setText(str(g))
        self._ch_labels["B"].setText(str(b))
        self.color_preview.setStyleSheet(f"background: rgb({r},{g},{b}); border-radius: 4px;")

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
            * { font-family: 'Segoe UI', sans-serif; font-size: 12px; }
            QMainWindow, QWidget#root { background: #1a1b26; }
            QGroupBox {
                color: #7aa2f7; font-weight: 600;
                border: 1px solid #2d3149; border-radius: 8px;
                margin-top: 10px; padding-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                left: 10px; padding: 0 4px; background: #1a1b26;
            }
            QLabel { color: #c0caf5; }
            QRadioButton { color: #c0caf5; spacing: 6px; }
            QRadioButton::indicator { width: 14px; height: 14px; border-radius: 7px; }
            QRadioButton::indicator:checked  { background: #7aa2f7; border: 2px solid #7aa2f7; }
            QRadioButton::indicator:unchecked { background: #24253a; border: 2px solid #565f89; }
            QSlider::groove:horizontal { height: 4px; background: #2d3149; border-radius: 2px; }
            QSlider::handle:horizontal {
                width: 16px; height: 16px; margin: -6px 0;
                background: #7aa2f7; border-radius: 8px;
            }
            QSlider::sub-page:horizontal { background: #7aa2f7; border-radius: 2px; }
            QComboBox {
                background: #24253a; color: #c0caf5;
                border: 1px solid #2d3149; border-radius: 6px; padding: 5px 10px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: #24253a; color: #c0caf5;
                border: 1px solid #2d3149; selection-background-color: #2d3149;
            }
            QPushButton {
                background: #24253a; color: #c0caf5;
                border: 1px solid #2d3149; border-radius: 6px; padding: 8px;
                font-size: 13px;
            }
            QPushButton:hover  { background: #2d3149; border-color: #7aa2f7; }
            QPushButton:disabled { color: #565f89; border-color: #2d3149; }
            QPushButton#toggleBtn:checked {
                background: #9ece6a; color: #1a1b26;
                border-color: #9ece6a; font-weight: 600;
            }
            QPushButton#changeBtn:disabled { color: #f38ba8; border-color: #f38ba8; }
            QMessageBox { background: #1a1b26; color: #c0caf5; }
            QMessageBox QLabel { color: #c0caf5; font-size: 13px; }
            QMessageBox QPushButton { min-width: 110px; padding: 7px; }
        """)

    def get_crosshair_type(self) -> str:
        btn = self.type_group.checkedButton()
        return btn.property("ct_key") if btn else "dot"

    def get_color(self) -> QColor:
        return QColor(
            self._sliders["R"].value(),
            self._sliders["G"].value(),
            self._sliders["B"].value(),
        )

    def get_size(self) -> int:
        return self.size_slider.value()

    def get_monitor_index(self) -> int:
        return self.monitor_combo.currentIndex()

    def set_overlay_active(self, active: bool) -> None:
        self._overlay_active = active
        self.toggle_btn.setChecked(active)
        self.toggle_btn.setText(self._tr("toggle_off") if active else self._tr("toggle_on"))

    def set_hotkey_label(self, hotkey: str) -> None:
        self.hotkey_lbl.setText(f"<b>{hotkey}</b>")

    def set_capturing(self, capturing: bool) -> None:
        self._capturing = capturing
        self.hotkey_change_btn.setEnabled(not capturing)
        self.hotkey_change_btn.setText(
            self._tr("hotkey_capture") if capturing else self._tr("hotkey_change")
        )


# ── Application controller ────────────────────────────────────────────────────

class App:
    _SERVER_NAME = "CrosshairOverlay_IPC"

    def __init__(self) -> None:
        self.qapp = QApplication(sys.argv)
        self._local_server: QLocalServer | None = None

        if not self._try_become_primary():
            sys.exit(0)

        self.qapp.setQuitOnLastWindowClosed(False)
        self.qapp.setApplicationName("Crosshair Overlay")

        _icon = make_app_icon()
        self.qapp.setWindowIcon(_icon)

        self.overlay  = CrosshairOverlay()
        self.window   = SettingsWindow()
        self.window.setWindowIcon(_icon)

        self.settings            = AppSettings()
        self.active              = False
        self._current_hotkey     = TOGGLE_HOTKEY
        self._capture_thread: _HotkeyCapture | None = None

        self._save_timer = QTimer(self.qapp)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._do_save)

        self._connect_signals()
        self._setup_tray(_icon)
        self._register_hotkey(self._current_hotkey)
        self._load_settings()

    def _try_become_primary(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self._SERVER_NAME)
        if sock.waitForConnected(500):
            sock.write(b"show")
            sock.waitForBytesWritten(500)
            sock.disconnectFromServer()
            return False

        QLocalServer.removeServer(self._SERVER_NAME)
        self._local_server = QLocalServer()
        self._local_server.newConnection.connect(self._on_secondary_instance)
        self._local_server.listen(self._SERVER_NAME)
        return True

    def _on_secondary_instance(self) -> None:
        if self._local_server is None:
            return
        conn = self._local_server.nextPendingConnection()
        if conn:
            conn.disconnectFromServer()
        self._show_settings()

    def _connect_signals(self) -> None:
        self.window.toggle_btn.clicked.connect(self._on_toggle_btn)
        self.window.monitor_combo.currentIndexChanged.connect(self._on_monitor_change)
        self.window.hotkey_change_btn.clicked.connect(self._start_hotkey_capture)
        self.window.lang_changed.connect(self._on_lang_changed)

        for btn in self.window.type_group.buttons():
            btn.toggled.connect(self._on_setting_changed)
        self.window.size_slider.valueChanged.connect(self._on_setting_changed)
        for sl in self.window._sliders.values():
            sl.valueChanged.connect(self._on_setting_changed)

        self.qapp.aboutToQuit.connect(self._on_quit)

    def _on_toggle_btn(self, checked: bool) -> None:
        self._set_active(checked)
        self._save()

    def _on_monitor_change(self, index: int) -> None:
        if self.active:
            screens = QApplication.screens()
            if 0 <= index < len(screens):
                self.overlay.show_on_screen(screens[index])
        self._save()

    def _on_setting_changed(self) -> None:
        self._sync_overlay()
        self._save()

    def _on_lang_changed(self, _lang: str) -> None:
        self._update_tray_labels()
        self._save()

    def _update_tray_labels(self) -> None:
        self._tray_settings_action.setText(self.window._tr("tray_settings"))
        self._tray_toggle_action.setText(
            self.window._tr("tray_toggle", hk=self._current_hotkey)
        )
        self._tray_exit_action.setText(self.window._tr("tray_exit"))

    def _sync_overlay(self) -> None:
        self.overlay.apply_settings(
            self.window.get_crosshair_type(),
            self.window.get_color(),
            self.window.get_size(),
        )

    def _save(self) -> None:
        self._save_timer.start()

    def _do_save(self) -> None:
        self.settings.save(self.window, self.active, self._current_hotkey)

    def _load_settings(self) -> None:
        all_widgets = [
            self.window.size_slider,
            self.window.monitor_combo,
            *self.window.type_group.buttons(),
            *self.window._sliders.values(),
            *self.window._lang_btn_group.buttons(),
        ]
        with _blocked(all_widgets):
            saved_active, saved_hotkey, saved_lang = self.settings.load(self.window)

        if saved_lang != self.window._lang:
            self.window._lang = saved_lang
            with _blocked(self.window._lang_btn_group.buttons()):
                for btn in self.window._lang_btn_group.buttons():
                    btn.setChecked(btn.property("lang_code") == saved_lang)
            self.window._retranslate()
            self._update_tray_labels()

        self.window._size_lbl.setText(str(self.window.size_slider.value()))
        self.window._on_color_changed()

        if saved_hotkey and saved_hotkey != self._current_hotkey:
            self._reassign_hotkey(saved_hotkey)

        self._sync_overlay()
        if saved_active:
            self._set_active(True)

    def _setup_tray(self, icon: QIcon) -> None:
        self.tray = QSystemTrayIcon(icon, self.qapp)
        self.tray.setToolTip("Crosshair Overlay")

        menu = QMenu()
        self._tray_settings_action = menu.addAction(
            self.window._tr("tray_settings"), self._show_settings
        )
        self._tray_toggle_action = menu.addAction(
            self.window._tr("tray_toggle", hk=self._current_hotkey), self._toggle
        )
        menu.addSeparator()
        self._tray_exit_action = menu.addAction(
            self.window._tr("tray_exit"), self.qapp.quit
        )

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_settings()

    def _show_settings(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _register_hotkey(self, hotkey: str) -> None:
        self._hk_signaler = _HotkeySignaler()
        self._hk_signaler.toggled.connect(self._toggle)
        try:
            keyboard.add_hotkey(hotkey, self._hk_signaler.toggled.emit)
        except Exception as exc:
            print(f"[warn] hotkey {hotkey!r} not registered: {exc}")

    def _reassign_hotkey(self, new_hotkey: str) -> None:
        try:
            keyboard.remove_hotkey(self._current_hotkey)
        except Exception:
            pass
        self._current_hotkey = new_hotkey
        try:
            keyboard.add_hotkey(new_hotkey, self._hk_signaler.toggled.emit)
        except Exception as exc:
            print(f"[warn] hotkey {new_hotkey!r} not registered: {exc}")
        self.window.set_hotkey_label(new_hotkey)
        self._update_tray_labels()

    def _start_hotkey_capture(self) -> None:
        self.window.set_capturing(True)
        self._capture_thread = _HotkeyCapture()
        self._capture_thread.captured.connect(self._on_hotkey_captured)
        self._capture_thread.start()

    def _on_hotkey_captured(self, key: str) -> None:
        self.window.set_capturing(False)
        self._reassign_hotkey(key)
        self._save()

    def _set_active(self, active: bool) -> None:
        self.active = active
        self.window.set_overlay_active(active)
        if active:
            self._sync_overlay()
            idx     = self.window.get_monitor_index()
            screens = QApplication.screens()
            if 0 <= idx < len(screens):
                self.overlay.show_on_screen(screens[idx])
        else:
            self.overlay.hide()

    def _toggle(self) -> None:
        self._set_active(not self.active)
        self._save()

    def _on_quit(self) -> None:
        self._save_timer.stop()
        self._do_save()
        if self._capture_thread is not None:
            self._capture_thread.wait(1000)
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def run(self) -> None:
        self.window.show()
        sys.exit(self.qapp.exec())


if __name__ == "__main__":
    App().run()
