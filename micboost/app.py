"""Uygulama giriş noktası."""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import APP_NAME
from .config import AppConfig, setup_logging
from .engine import AudioEngine
from .ui import theme
from .ui.main_window import MainWindow


def make_icon() -> QIcon:
    """Create the original in-memory icon for the taskbar and tray."""
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, 256, 256)
    gradient.setColorAt(0, QColor(theme.ACCENT))
    gradient.setColorAt(1, QColor(theme.BLUE))
    p.setPen(Qt.NoPen)
    p.setBrush(gradient)
    p.drawRoundedRect(8, 8, 240, 240, 52, 52)
    p.setBrush(QColor("white"))
    p.drawRoundedRect(98, 50, 60, 100, 30, 30)
    pen = QPen(QColor("white"), 14)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(70, 80, 116, 100, 180 * 16, 180 * 16)
    p.drawLine(128, 180, 128, 208)
    p.drawLine(100, 208, 156, 208)
    p.end()
    return QIcon(pm)


def load_app_font() -> None:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    font_path = base_dir / "assets" / "fonts" / "Montserrat[wght].ttf"
    if not font_path.is_file():
        logging.getLogger("micboost").error("Montserrat font file not found: %s", font_path)
        return
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        logging.getLogger("micboost").error("Could not load Montserrat font: %s", font_path)


def main() -> int:
    setup_logging()
    log = logging.getLogger("micboost")

    def excepthook(t, v, tb):
        log.error("Yakalanmamış hata", exc_info=(t, v, tb))
        sys.__excepthook__(t, v, tb)
    sys.excepthook = excepthook

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    load_app_font()
    icon = make_icon()
    app.setWindowIcon(icon)
    app.setQuitOnLastWindowClosed(False)  # pencere gizlenince (tepsi) uygulama kapanmasın

    lock = QLockFile(str(Path(tempfile.gettempdir()) / "micboost.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "MicBoost zaten çalışıyor (sistem tepsisine bakın).")
        return 0

    cfg = AppConfig.load()
    theme.apply(app, cfg.theme)
    engine = AudioEngine(cfg.dsp)
    tray = QSystemTrayIcon(icon) if QSystemTrayIcon.isSystemTrayAvailable() else None
    if tray is not None:
        tray.setToolTip(APP_NAME)
    win = MainWindow(cfg, engine, tray)
    if "--minimized" in sys.argv and tray is not None:
        # Windows ile açılış: pencere gösterilmez, motor arka planda başlar. Aygıtlar henüz
        # hazır değilse izleme iş parçacığı hazır olana dek yeniden dener.
        if not engine.start(cfg.mic_key, cfg.out_key) and engine.state == "error":
            win.show()
    else:
        win.showMaximized()
    QTimer.singleShot(0, win.populate_devices)
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
