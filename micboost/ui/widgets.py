"""Özel arayüz bileşenleri: seviye ölçer, toggle anahtar, parametre kaydırıcısı, kart."""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import theme


class LevelMeter(QWidget):
    """Animasyonlu dBFS ölçer (RMS dolgusu + tepe tutma çizgisi + clip LED'i)."""

    FALL_DB_PER_S = 40.0
    PEAK_HOLD_S = 1.2

    def __init__(self, min_db: float = -60.0, max_db: float = 0.0, parent=None):
        super().__init__(parent)
        self.min_db, self.max_db = min_db, max_db
        self._rms = min_db
        self._peak = min_db
        self._hold_peak = min_db
        self._hold_t = 0.0
        self._last = time.monotonic()
        self.clip = False
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(46)

    def feed(self, peak_db: float, rms_db: float, clip: bool = False):
        now = time.monotonic()
        dt = max(0.0, min(0.25, now - self._last))
        self._last = now
        fall = self.FALL_DB_PER_S * dt
        peak_db = max(self.min_db, min(self.max_db, peak_db))
        rms_db = max(self.min_db, min(self.max_db, rms_db))
        self._rms = max(rms_db, self._rms - fall)
        self._peak = max(peak_db, self._peak - fall)
        if peak_db >= self._hold_peak:
            self._hold_peak, self._hold_t = peak_db, now
        elif now - self._hold_t > self.PEAK_HOLD_S:
            self._hold_peak = max(self.min_db, self._hold_peak - fall)
        self.clip = clip
        self.update()

    @property
    def peak_db(self) -> float:
        return self._hold_peak

    def _x(self, db: float, w: float) -> float:
        span = self.max_db - self.min_db
        return w * (db - self.min_db) / span

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), 22.0
        track = QRectF(0, 0, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.TRACK))
        p.drawRoundedRect(track, 8, 8)

        p.save()
        p.setClipRect(QRectF(0, 0, max(0.0, self._x(self._rms, w)), h))
        p.setBrush(QColor(theme.ACCENT))
        p.drawRoundedRect(track, 8, 8)
        p.restore()

        # tepe tutma çizgisi
        px = self._x(self._hold_peak, w)
        pen = QPen(QColor(theme.METER_PEAK), 2)
        p.setPen(pen)
        p.drawLine(int(px), 3, int(px), int(h) - 3)

        # clip LED
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.RED if self.clip else theme.CLIP_OFF))
        p.drawEllipse(QRectF(w - 16, 5, 12, 12))

        # ölçek
        p.setPen(QColor(theme.MUTED))
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        for db in (-60, -48, -36, -24, -12, -6, 0):
            if db < self.min_db or db > self.max_db:
                continue
            x = self._x(db, w)
            txt = str(db)
            tw = p.fontMetrics().horizontalAdvance(txt)
            p.drawText(int(min(max(0, x - tw / 2), w - tw)), int(h) + 14, txt)
        p.end()


class ToggleSwitch(QCheckBox):
    """iOS tarzı açma/kapama anahtarı."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pos = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(120)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)

    def _on_anim(self, v):
        self._pos = float(v)
        self.update()

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool):
        super().setChecked(on)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        off, on = QColor(theme.SWITCH_OFF), QColor(theme.ACCENT)
        c = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = 3 + (r.width() - d - 6) * self._pos
        p.setBrush(QColor(theme.SLIDER_HANDLE))
        p.drawEllipse(QRectF(x, 3, d, d))
        p.end()


class Card(QFrame):
    """Başlıklı, isteğe bağlı aç/kapa anahtarlı kart."""

    toggled = Signal(bool)

    def __init__(self, title: str, toggle: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 18)
        self.body.setSpacing(12)
        head = QHBoxLayout()
        self.title = QLabel(title.upper())
        self.title.setObjectName("cardTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.switch = None
        if toggle:
            self.switch = ToggleSwitch()
            self.switch.toggled.connect(self.toggled)
            head.addWidget(self.switch)
        self.body.addLayout(head)

    def add(self, w):
        if isinstance(w, QWidget):
            self.body.addWidget(w)
        else:
            self.body.addLayout(w)


class ParamSlider(QWidget):
    """Etiket + değer + kaydırıcı. Değerler float; iç ölçek `steps` ile."""

    valueChanged = Signal(float)

    def __init__(self, label: str, lo: float, hi: float, step: float = 1.0,
                 unit: str = "", decimals: int = 0, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.lo, self.step, self.unit, self.decimals = lo, step, unit, decimals
        n = round((hi - lo) / step)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QHBoxLayout()
        self.name = QLabel(label)
        self.val = QLabel()
        self.val.setObjectName("muted")
        row.addWidget(self.name)
        row.addStretch(1)
        row.addWidget(self.val)
        lay.addLayout(row)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, n)
        self.slider.valueChanged.connect(self._changed)
        lay.addWidget(self.slider)
        if tooltip:
            self.setToolTip(tooltip)
        self._show(self.value())

    def value(self) -> float:
        return self.lo + self.slider.value() * self.step

    def set_value(self, v: float):
        self.slider.blockSignals(True)
        self.slider.setValue(round((v - self.lo) / self.step))
        self.slider.blockSignals(False)
        self._show(self.value())

    def _show(self, v: float):
        sign = "+" if (self.lo < 0 < v) else ""
        self.val.setText(f"{sign}{v:.{self.decimals}f} {self.unit}".strip())

    def _changed(self, _):
        v = self.value()
        self._show(v)
        self.valueChanged.emit(v)


class StatusPill(QLabel):
    """Renkli durum rozeti (yeşil/amber/kırmızı)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_state("idle", "—")

    def set_state(self, kind: str, text: str):
        color = {"ok": theme.GREEN, "warn": theme.AMBER,
                 "bad": theme.RED, "idle": theme.MUTED}
        c = color.get(kind, theme.MUTED)
        self.setText(f"●  {text}")
        self.setStyleSheet(
            f"color:{c}; background:{theme.CARD}; border:1px solid {c}; "
            "border-radius:0px; padding:5px 14px; font-weight:600;")
