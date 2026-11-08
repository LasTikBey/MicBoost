"""MicBoost ana penceresi."""
from __future__ import annotations

import logging
import math

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__, playback
from .. import devices as dev
from ..config import AppConfig
from ..engine import AudioEngine
from . import theme
from .localization import tr
from .widgets import Card, LevelMeter, ParamSlider, StatusPill, ToggleSwitch

log = logging.getLogger("micboost.ui")
VBCABLE_URL = "https://vb-audio.com/Cable/"


def _fmt_db(v: float) -> str:
    return "−∞" if v <= -100 else f"{v:+.1f}".replace("-", "−")


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig, engine: AudioEngine, tray_icon=None):
        super().__init__()
        self.cfg, self.engine, self.s = cfg, engine, cfg.dsp
        if self.cfg.language not in ("tr", "en", "fr"):
            self.cfg.language = "en"
        self._really_quit = False
        self._capture = None
        self._recording = False
        self._last_dev_scan = 0.0
        self._devices_loaded = False
        self._cable_available = False
        self._param_controls = {}
        self._toggle_controls = {}
        # Arayüz kurulurken (Gain çubuğu vb.) _set() çağrıldığı için en başta oluşturulmalı
        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self._save)

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1180, 860)
        self.setMinimumSize(900, 560)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(16)

        outer.addLayout(self._build_header())

        self._body_scroll = QScrollArea()
        self._body_scroll.setWidgetResizable(True)
        self._body_scroll.setFrameShape(QFrame.NoFrame)
        self._body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        panel = QWidget()
        panel.setObjectName("root")
        self._columns_layout = QBoxLayout(QBoxLayout.LeftToRight, panel)
        self._columns_layout.setContentsMargins(0, 0, 8, 0)
        self._columns_layout.setSpacing(18)
        self._columns_layout.addWidget(self._column(
            [self._build_devices_card(), self._build_gain_card(),
             self._build_meter_card(), self._build_test_card()]), 5)
        self._columns_layout.addWidget(self._column(
            [self._build_level_card(), self._build_eq_card(), self._build_ns_card(),
             self._build_gate_card(), self._build_agc_card(), self._build_comp_card(),
             self._build_limiter_card()]), 4)
        self._body_scroll.setWidget(panel)
        outer.addWidget(self._body_scroll, 1)

        outer.addLayout(self._build_footer())

        self._tick_timer = QTimer(self, interval=33)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()
        self._status_timer = QTimer(self, interval=500)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        self.tray = tray_icon
        if self.tray is not None:
            self._build_tray()

        self.engine.set_latency_mode(self.cfg.latency_mode)
        if self.cfg.autostart_engine:
            QTimer.singleShot(400, self._start)

    # ================================================================ kurulum
    def _t(self, text: str) -> str:
        return tr(self.cfg.language, text)

    @staticmethod
    def _new_combo() -> QComboBox:
        combo = QComboBox()
        combo.setMaxVisibleItems(8)
        view = QListView(combo)
        view.setFrameShape(QFrame.NoFrame)
        view.setUniformItemSizes(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        combo.setView(view)
        popup = view.window()
        popup.setFrameShape(QFrame.NoFrame)
        popup.setContentsMargins(0, 0, 0, 0)
        return combo

    @staticmethod
    def _column(cards) -> QWidget:
        column = QWidget()
        lay = QVBoxLayout(column)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        for c in cards:
            c.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)  # kart asla küçülmez
            lay.addWidget(c)
        lay.addStretch(1)
        return column

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "_columns_layout"):
            return
        direction = QBoxLayout.TopToBottom if self.width() < 1120 else QBoxLayout.LeftToRight
        if self._columns_layout.direction() != direction:
            self._columns_layout.setDirection(direction)

    def _build_header(self):
        h = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(APP_NAME)
        t.setObjectName("h1")
        sub = QLabel(self._t("Mikrofon yükseltici · sanal mikrofon aktarımı"))
        sub.setObjectName("muted")
        col.addWidget(t)
        col.addWidget(sub)
        h.addLayout(col)
        h.addStretch(1)
        self.btn_settings = QPushButton("⚙ " + self._t("Ayarlar"))
        self.btn_settings.clicked.connect(self._open_settings)
        h.addWidget(self.btn_settings)
        self.pill = StatusPill()
        h.addWidget(self.pill)
        return h

    def _open_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("Ayarlar"))
        dialog.setMinimumWidth(500)
        form = QFormLayout(dialog)
        form.setContentsMargins(24, 22, 24, 20)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)

        language = self._new_combo()
        language.addItem("Türkçe", "tr")
        language.addItem("English", "en")
        language.addItem("Français", "fr")
        language.setCurrentIndex(max(0, language.findData(self.cfg.language)))
        form.addRow(self._t("Dil"), language)

        theme_choice = self._new_combo()
        theme_choice.addItem(self._t("Koyu"), "dark")
        theme_choice.addItem(self._t("Açık"), "light")
        theme_choice.setCurrentIndex(max(0, theme_choice.findData(self.cfg.theme)))
        form.addRow(self._t("Tema"), theme_choice)

        close_behavior = self._new_combo()
        if ((self.tray is not None and self.tray.isVisible())
                or self.cfg.close_behavior == "tray"):
            close_behavior.addItem(self._t("Tepsiye küçült, arka planda çalışsın"), "tray")
        close_behavior.addItem(self._t("Tamamen çık, ses motorunu durdur"), "quit")
        selected = close_behavior.findData(self.cfg.close_behavior)
        close_behavior.setCurrentIndex(max(selected, 0))
        form.addRow(self._t("Pencere kapatıldığında"), close_behavior)

        profiles_group = QGroupBox(self._t("Ses profilleri"))
        profiles_layout = QVBoxLayout(profiles_group)
        profiles_layout.setContentsMargins(14, 18, 14, 14)
        profiles_layout.setSpacing(10)
        profile_choice = self._new_combo()
        profile_choice.setObjectName("profileChoice")
        for slot in range(1, 6):
            key = str(slot)
            default_name = self._default_profile_name(key)
            profile_choice.addItem(self.cfg.profile_names.get(key, default_name), key)
        profiles_layout.addWidget(profile_choice)
        name_row = QHBoxLayout()
        name_edit = QLineEdit()
        name_edit.setObjectName("profileName")
        name_edit.setMaxLength(32)
        name_edit.setPlaceholderText(self._t("Profil adı (en fazla 32 karakter)"))
        name_row.addWidget(name_edit, 1)
        profile_rename = QPushButton(self._t("Adı kaydet"))
        profile_rename.setObjectName("profileRename")
        name_row.addWidget(profile_rename)
        profiles_layout.addLayout(name_row)
        profile_action_row = QHBoxLayout()
        profile_action_row.setSpacing(8)
        profile_save = QPushButton(self._t("Profili kaydet"))
        profile_save.setObjectName("profileSave")
        profile_load = QPushButton(self._t("Profili uygula"))
        profile_load.setObjectName("profileLoad")
        profile_delete = QPushButton(self._t("Profili sil"))
        profile_delete.setObjectName("profileDelete")
        for button in (profile_save, profile_load, profile_delete):
            profile_action_row.addWidget(button, 1)
        profiles_layout.addLayout(profile_action_row)
        form.addRow(profiles_group)

        name_edit.setText(profile_choice.currentText())
        profile_choice.currentIndexChanged.connect(
            lambda _: name_edit.setText(profile_choice.currentText()))
        profile_load.setEnabled(bool(self.cfg.profiles.get(profile_choice.currentData())))
        profile_delete.setEnabled(profile_load.isEnabled())
        profile_choice.currentIndexChanged.connect(
            lambda _: self._update_profile_buttons(profile_choice, profile_load, profile_delete))
        profile_save.clicked.connect(
            lambda: self._save_profile(
                profile_choice.currentData(), name_edit, profile_choice, profile_load, profile_delete))
        profile_rename.clicked.connect(
            lambda: self._rename_profile(
                profile_choice.currentData(), name_edit, profile_choice))
        name_edit.returnPressed.connect(profile_rename.click)
        profile_load.clicked.connect(
            lambda: self._load_profile(profile_choice.currentData()))
        profile_delete.clicked.connect(
            lambda: self._delete_profile(
                profile_choice.currentData(), profile_choice, name_edit, profile_load, profile_delete))

        reset_all = QPushButton(self._t("Tüm ayarları varsayılana döndür"))
        reset_all.clicked.connect(lambda: self._reset_all_settings(dialog))
        form.addRow(reset_all)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(self._t("Kaydet"))
        buttons.button(QDialogButtonBox.Cancel).setText(self._t("İptal"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.Accepted:
            return
        old_language = self.cfg.language
        old_theme = self.cfg.theme
        self.cfg.language = language.currentData()
        self.cfg.theme = theme_choice.currentData()
        self.cfg.close_behavior = close_behavior.currentData()
        self._save()
        if old_theme != self.cfg.theme:
            theme.apply(QApplication.instance(), self.cfg.theme)
            self._refresh_status()
        if old_language != self.cfg.language:
            QMessageBox.information(
                self, APP_NAME, self._t("Dil değişikliği yeniden başlatınca uygulanır."))

    def _build_devices_card(self):
        c = Card(self._t("Aygıtlar"))
        self.cb_mic = self._new_combo()
        self.cb_out = self._new_combo()
        self.cb_mic.currentIndexChanged.connect(self._dev_changed)
        self.cb_out.currentIndexChanged.connect(self._dev_changed)
        for label, cb in (("Mikrofon (fiziksel)", self.cb_mic),
                          ("Çıkış → sanal kablo girişi (CABLE Input)", self.cb_out)):
            l = QLabel(self._t(label))
            l.setObjectName("muted")
            c.add(l)
            c.add(cb)
        row = QHBoxLayout()
        b_ref = QPushButton(self._t("⟳ Aygıtları yenile"))
        b_ref.clicked.connect(self._refresh_devices_clicked)
        b_win = QPushButton(self._t("Windows kayıt aygıtları"))
        b_win.setToolTip(self._t("Windows Ses ayarlarını açar (mikrofon seviyesi / mikrofon güçlendirme burada)"))
        b_win.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("ms-settings:sound")))
        row.addWidget(b_ref)
        row.addWidget(b_win)
        c.add(row)
        return c

    def _build_gain_card(self):
        c = Card(self._t("Mikrofon kazancı (Gain)"))
        self.lbl_gain = QLabel()
        self.lbl_gain.setObjectName("bigValue")
        self.lbl_gain.setAlignment(Qt.AlignCenter)
        c.add(self.lbl_gain)
        self.sl_gain = QSlider(Qt.Horizontal)
        self.sl_gain.setObjectName("bigGain")
        self.sl_gain.setRange(0, 300)          # 0.1 dB adım -> 0..+30 dB
        self.sl_gain.setValue(round(self.s.mic_gain_db * 10))
        self.sl_gain.valueChanged.connect(self._gain_changed)
        c.add(self.sl_gain)
        row = QHBoxLayout()
        for db in (0, 6, 12, 18, 24, 30):
            b = QPushButton(f"+{db}")
            b.clicked.connect(lambda _=False, d=db: self.sl_gain.setValue(d * 10))
            row.addWidget(b)
        c.add(row)
        hint = QLabel(self._t("Kazanç sessizliği/gürültüyü de aynı oranda yükseltir. "
                      "Gürültü artarsa Gürültü Bastırma ve Noise Gate kullanın."))
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        c.add(hint)
        self._gain_changed(self.sl_gain.value())
        return c

    def _build_meter_card(self):
        c = Card(self._t("Ses seviyesi  (dBFS)"))
        top = QHBoxLayout()
        self.lbl_in = QLabel(self._t("GİRİŞ (öncesi)"))
        self.val_in = QLabel("−∞")
        self.val_in.setObjectName("muted")
        top.addWidget(self.lbl_in)
        top.addStretch(1)
        top.addWidget(self.val_in)
        c.add(top)
        self.m_in = LevelMeter()
        c.add(self.m_in)
        top2 = QHBoxLayout()
        self.lbl_out = QLabel(self._t("ÇIKIŞ (sonrası → sanal mikrofon)"))
        self.val_out = QLabel("−∞")
        self.val_out.setObjectName("muted")
        top2.addWidget(self.lbl_out)
        top2.addStretch(1)
        top2.addWidget(self.val_out)
        c.add(top2)
        self.m_out = LevelMeter()
        c.add(self.m_out)

        row = QHBoxLayout()
        self.lbl_gate = QLabel(self._t("Kapı: —"))
        self.lbl_comp = QLabel("Comp: 0.0 dB")
        self.lbl_lim = QLabel("Limiter: 0.0 dB")
        for l in (self.lbl_gate, self.lbl_comp, self.lbl_lim):
            l.setObjectName("muted")
            row.addWidget(l)
            row.addStretch(1)
        c.add(row)

        ab = QHBoxLayout()
        ab_l = QLabel(self._t("A/B karşılaştırma: yalnızca ORİJİNAL sesi gönder (işleme kapalı)"))
        ab_l.setWordWrap(True)
        self.sw_bypass = ToggleSwitch()
        self.sw_bypass.setChecked(self.s.bypass)
        self.sw_bypass.toggled.connect(lambda on: self._set("bypass", on))
        ab.addWidget(ab_l, 1)
        ab.addWidget(self.sw_bypass)
        c.add(ab)

        self.warn_clip = QLabel("")
        self.warn_clip.setObjectName("warn")
        self.warn_clip.setWordWrap(True)
        self.warn_clip.hide()
        self.warn_lim = QLabel("")
        self.warn_lim.setObjectName("info")
        self.warn_lim.hide()
        c.add(self.warn_clip)
        c.add(self.warn_lim)
        return c

    def _build_test_card(self):
        c = Card(self._t("Mikrofon testi (5 sn kayıt → dinle)"))
        row = QHBoxLayout()
        self.btn_rec = QPushButton(self._t("● 5 sn kaydet"))
        self.btn_rec.clicked.connect(self._record_clicked)
        self.btn_raw = QPushButton(self._t("▶ Orijinal"))
        self.btn_proc = QPushButton(self._t("▶ İşlenmiş"))
        self.btn_stopplay = QPushButton("■")
        self.btn_raw.clicked.connect(lambda: self._play(0))
        self.btn_proc.clicked.connect(lambda: self._play(1))
        self.btn_stopplay.clicked.connect(playback.stop)
        for b in (self.btn_raw, self.btn_proc, self.btn_stopplay):
            b.setEnabled(False)
        for b in (self.btn_rec, self.btn_raw, self.btn_proc, self.btn_stopplay):
            row.addWidget(b)
        c.add(row)
        mrow = QHBoxLayout()
        ml = QLabel(self._t("Dinleme aygıtı (kulaklık önerilir):"))
        ml.setObjectName("muted")
        self.cb_mon = self._new_combo()
        self.cb_mon.currentIndexChanged.connect(self._dev_changed)
        mrow.addWidget(ml)
        mrow.addWidget(self.cb_mon, 1)
        c.add(mrow)
        self.lbl_test = QLabel(self._t("Motor çalışırken kayıt alınır; sonuç burada karşılaştırılır."))
        self.lbl_test.setObjectName("muted")
        self.lbl_test.setWordWrap(True)
        c.add(self.lbl_test)
        return c

    # ---- sağ panel kartları -------------------------------------------------
    def _slider(self, card, label, attr, lo, hi, step, unit="", dec=0, scale=1.0, tip=""):
        ps = ParamSlider(self._t(label), lo, hi, step, unit, dec, self._t(tip))
        ps.set_value(getattr(self.s, attr) * scale)
        ps.valueChanged.connect(lambda v, a=attr, k=scale: self._set(a, v / k))
        self._param_controls[attr] = (ps, scale)
        card.add(ps)
        return ps

    def _toggle(self, card, attr):
        card.switch.setChecked(bool(getattr(self.s, attr)))
        card.toggled.connect(lambda on, a=attr: self._set(a, on))
        self._toggle_controls[attr] = card.switch

    def _build_level_card(self):
        c = Card(self._t("Seviye"))
        self._slider(c, "Input Volume (yazılımsal giriş seviyesi)", "input_volume",
                     0, 200, 1, "%", 0,
                     tip="Mikrofondan gelen sesi DSP'den önce ölçekler. Windows'taki fiziksel "
                         "mikrofon seviyesi değildir; onu 'Windows kayıt aygıtları' düğmesinden ayarlayın.")
        self._slider(c, "Output Gain (sanal mikrofona giden)", "output_gain_db",
                     -20, 12, 0.5, "dB", 1)
        return c

    def _build_ns_card(self):
        c = Card(self._t("Gürültü bastırma"), toggle=True)
        self._toggle(c, "ns_on")
        self._slider(c, "Güç", "ns_strength", 0, 100, 1, "%", 0, scale=100.0,
                     tip="Sabit fan/hışırtı gürültüsünü öğrenip azaltır. Konuşurken gürültü "
                         "öğrenimini yavaşlatır; ani klavye tıkırtılarını tamamen silemez. "
                         "Ses metalikleşirse gücü azaltın.")
        return c

    def _build_eq_card(self):
        c = Card(self._t("Ekolayzer"), toggle=True)
        self._toggle(c, "eq_on")
        self.sw_eq = c.switch
        self._applying_eq_preset = False
        self.cb_eq_preset = self._new_combo()
        for label, key in (
            ("Özel", "custom"),
            ("Düz", "flat"),
            ("Konuşma netliği", "clarity"),
            ("Sıcak ton", "warm"),
        ):
            self.cb_eq_preset.addItem(self._t(label), key)
        self.cb_eq_preset.setCurrentIndex(0)
        self.cb_eq_preset.currentIndexChanged.connect(self._eq_preset_changed)
        c.add(self.cb_eq_preset)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.eq_value_labels = {}
        self.eq_sliders = {}
        bands = (
            ("100 Hz", "eq_100_db"),
            ("300 Hz", "eq_300_db"),
            ("1 kHz", "eq_1k_db"),
            ("3 kHz", "eq_3k_db"),
            ("10 kHz", "eq_10k_db"),
        )
        for frequency, attr in bands:
            column = QVBoxLayout()
            column.setSpacing(4)
            value = QLabel(f"{getattr(self.s, attr):+.0f} dB")
            value.setObjectName("muted")
            value.setAlignment(Qt.AlignCenter)
            slider = QSlider(Qt.Vertical)
            slider.setRange(-12, 12)
            slider.setValue(round(getattr(self.s, attr)))
            slider.setFixedHeight(128)
            slider.setToolTip(self._t("Kazanç: -12 ile +12 dB"))
            slider.valueChanged.connect(
                lambda v, a=attr, label=value: self._eq_changed(a, label, v))
            label = QLabel(frequency)
            label.setAlignment(Qt.AlignCenter)
            label.setObjectName("muted")
            column.addWidget(value)
            column.addWidget(slider, 1, Qt.AlignHCenter)
            column.addWidget(label)
            row.addLayout(column, 1)
            self.eq_value_labels[attr] = value
            self.eq_sliders[attr] = slider
        c.add(row)
        reset = QPushButton(self._t("Düz ayara sıfırla"))
        reset.clicked.connect(self._reset_eq)
        c.add(reset)
        return c

    def _eq_changed(self, attr, label, value):
        label.setText(f"{value:+d} dB")
        self._set(attr, float(value))
        custom_index = self.cb_eq_preset.findData("custom")
        if not self._applying_eq_preset and self.cb_eq_preset.currentIndex() != custom_index:
            self.cb_eq_preset.setCurrentIndex(custom_index)

    def _eq_preset_changed(self, _):
        preset = self.cb_eq_preset.currentData()
        presets = {
            "flat": (False, (0, 0, 0, 0, 0)),
            "clarity": (True, (-2, -1, 1, 3, 1)),
            "warm": (True, (2, 1, 0, -1, -2)),
        }
        selected = presets.get(preset)
        if selected is None:
            return
        enabled, values = selected
        self._applying_eq_preset = True
        try:
            self.sw_eq.setChecked(enabled)
            for slider, value in zip(self.eq_sliders.values(), values):
                slider.setValue(value)
        finally:
            self._applying_eq_preset = False

    def _reset_eq(self):
        self.cb_eq_preset.setCurrentIndex(self.cb_eq_preset.findData("flat"))

    def _build_gate_card(self):
        c = Card(self._t("Noise gate"), toggle=True)
        self._toggle(c, "gate_on")
        self._slider(c, "Eşik (ham mikrofon seviyesi)", "gate_threshold_db", -90, -10, 1, "dB", 0,
                     tip="Konuşmadığınız sırada ölçer bu değerin altında kalmalı, konuşurken üstüne çıkmalı.")
        return c

    def _build_agc_card(self):
        c = Card(self._t("Otomatik kazanç (AGC)"), toggle=True)
        self._toggle(c, "agc_on")
        self._slider(c, "Hedef seviye (RMS)", "agc_target_db", -40, -6, 1, "dB", 0)
        self._slider(c, "En fazla ek kazanç", "agc_max_gain_db", 0, 30, 1, "dB", 0)
        return c

    def _build_comp_card(self):
        c = Card(self._t("Compressor"), toggle=True)
        self._toggle(c, "comp_on")
        self._slider(c, "Eşik", "comp_threshold_db", -60, 0, 1, "dB", 0)
        self._slider(c, "Oran", "comp_ratio", 1, 20, 0.5, ": 1", 1)
        self._slider(c, "Attack", "comp_attack_ms", 1, 100, 1, "ms", 0)
        self._slider(c, "Release", "comp_release_ms", 10, 500, 5, "ms", 0)
        self._slider(c, "Makeup kazancı", "comp_makeup_db", 0, 24, 0.5, "dB", 1,
                     tip="Sıkıştırmadan sonra genel seviyeyi yükseltir (düşük sesler daha duyulur olur).")
        return c

    def _build_limiter_card(self):
        c = Card(self._t("Limiter"), toggle=True)
        self._toggle(c, "limiter_on")
        self._slider(c, "Tavan (ceiling)", "limiter_ceiling_db", -12, -0.1, 0.1, "dBFS", 1)
        self._slider(c, "Release", "limiter_release_ms", 5, 500, 5, "ms", 0)
        return c

    def _build_footer(self):
        h = QHBoxLayout()
        h.setSpacing(16)
        self.btn_start = QPushButton(self._t("▶  BAŞLAT"))
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumWidth(220)
        self.btn_start.clicked.connect(self._toggle_engine)
        h.addWidget(self.btn_start)

        self.cb_lat = self._new_combo()
        for key, label in (("low", "Düşük gecikme"), ("normal", "Dengeli"), ("safe", "Kesintisiz (güvenli)")):
            self.cb_lat.addItem(self._t(label), key)
        self.cb_lat.setCurrentIndex(max(0, self.cb_lat.findData(self.cfg.latency_mode)))
        self.cb_lat.currentIndexChanged.connect(self._latency_changed)
        h.addWidget(self.cb_lat)
        h.addStretch(1)
        self.lbl_stats = QLabel("")
        self.lbl_stats.setObjectName("muted")
        h.addWidget(self.lbl_stats)
        return h

    def _build_tray(self):
        menu = QMenu(self)
        act_show = QAction(self._t("MicBoost'u aç"), self)
        act_show.triggered.connect(self._show_from_tray)
        self._act_toggle = QAction(self._t("Başlat"), self)
        self._act_toggle.triggered.connect(self._toggle_engine)
        act_quit = QAction(self._t("Çıkış (tamamen kapat)"), self)
        act_quit.triggered.connect(self._quit)
        for a in (act_show, self._act_toggle):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_quit)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.setToolTip(APP_NAME)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_from_tray()

    # ================================================================ ayarlar
    def _set(self, attr, value):
        setattr(self.s, attr, value)
        self.s.clamp()
        self._save_timer.start()

    def _update_profile_buttons(self, choice, load_button, delete_button):
        exists = bool(self.cfg.profiles.get(choice.currentData()))
        load_button.setEnabled(exists)
        delete_button.setEnabled(exists)

    def _default_profile_name(self, slot):
        return self._t("Ses profili {slot}").format(slot=slot)

    def _profile_name(self, slot, name_edit):
        name = name_edit.text().strip()
        return name or self._default_profile_name(slot)

    def _rename_profile(self, slot, name_edit, choice):
        index = choice.findData(slot)
        if index < 0:
            return
        name = self._profile_name(slot, name_edit)
        previous = self.cfg.profile_names.get(slot)
        default_name = self._default_profile_name(slot)
        if name == default_name:
            self.cfg.profile_names.pop(slot, None)
        else:
            self.cfg.profile_names[slot] = name
        choice.setItemText(index, name)
        if not self._save():
            if previous is None:
                self.cfg.profile_names.pop(slot, None)
            else:
                self.cfg.profile_names[slot] = previous
            choice.setItemText(index, previous or default_name)
            QMessageBox.warning(self, APP_NAME, self._t("Ayarlar kaydedilemedi. Günlük dosyasını kontrol edin."))

    def _save_profile(self, slot, name_edit, choice, load_button, delete_button):
        if slot in self.cfg.profiles:
            answer = QMessageBox.question(
                self, APP_NAME, self._t("Bu ses profilinin üzerine yazılsın mı?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        previous = self.cfg.profiles.get(slot)
        previous_name = self.cfg.profile_names.get(slot)
        self.cfg.profiles[slot] = self.s.to_dict()
        name = self._profile_name(slot, name_edit)
        default_name = self._default_profile_name(slot)
        if name == default_name:
            self.cfg.profile_names.pop(slot, None)
        else:
            self.cfg.profile_names[slot] = name
        if not self._save():
            if previous is None:
                del self.cfg.profiles[slot]
            else:
                self.cfg.profiles[slot] = previous
            if previous_name is None:
                self.cfg.profile_names.pop(slot, None)
            else:
                self.cfg.profile_names[slot] = previous_name
            QMessageBox.warning(self, APP_NAME, self._t("Ayarlar kaydedilemedi. Günlük dosyasını kontrol edin."))
            return
        choice.setItemText(choice.findData(slot), name)
        load_button.setEnabled(True)
        delete_button.setEnabled(True)

    def _load_profile(self, slot):
        profile = self.cfg.profiles.get(slot)
        if profile is None:
            return
        from ..dsp import Settings

        self._apply_dsp_settings(Settings.from_dict(profile))
        if not self._save():
            QMessageBox.warning(self, APP_NAME, self._t("Ayarlar kaydedilemedi. Günlük dosyasını kontrol edin."))

    def _delete_profile(self, slot, choice, name_edit, load_button, delete_button):
        if slot not in self.cfg.profiles:
            return
        answer = QMessageBox.question(
            self, APP_NAME, self._t("Bu ses profili silinsin?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        previous = self.cfg.profiles.pop(slot)
        previous_name = self.cfg.profile_names.pop(slot, None)
        if not self._save():
            self.cfg.profiles[slot] = previous
            if previous_name is not None:
                self.cfg.profile_names[slot] = previous_name
            QMessageBox.warning(self, APP_NAME, self._t("Ayarlar kaydedilemedi. Günlük dosyasını kontrol edin."))
            return
        index = choice.findData(slot)
        if index >= 0:
            default_name = self._default_profile_name(slot)
            choice.setItemText(index, default_name)
            if choice.currentData() == slot:
                name_edit.setText(default_name)
        load_button.setEnabled(False)
        delete_button.setEnabled(False)

    def _apply_dsp_settings(self, settings):
        for name, value in settings.to_dict().items():
            setattr(self.s, name, value)
        self.s.clamp()
        self._sync_dsp_controls()

    def _sync_dsp_controls(self):
        for attr, (control, scale) in self._param_controls.items():
            control.set_value(getattr(self.s, attr) * scale)
        for attr, control in self._toggle_controls.items():
            control.blockSignals(True)
            control.setChecked(bool(getattr(self.s, attr)))
            control.blockSignals(False)
        self.sl_gain.blockSignals(True)
        self.sl_gain.setValue(round(self.s.mic_gain_db * 10))
        self.sl_gain.blockSignals(False)
        self.lbl_gain.setText(f"+{self.s.mic_gain_db:.1f} dB")
        self.sw_bypass.blockSignals(True)
        self.sw_bypass.setChecked(self.s.bypass)
        self.sw_bypass.blockSignals(False)
        for attr, slider in self.eq_sliders.items():
            slider.blockSignals(True)
            slider.setValue(round(getattr(self.s, attr)))
            slider.blockSignals(False)
            self.eq_value_labels[attr].setText(f"{round(getattr(self.s, attr)):+d} dB")
        self.cb_eq_preset.blockSignals(True)
        self.cb_eq_preset.setCurrentIndex(self.cb_eq_preset.findData("custom"))
        self.cb_eq_preset.blockSignals(False)

    def _reset_all_settings(self, dialog):
        answer = QMessageBox.question(
            self, APP_NAME, self._t(
                "Ses ayarları varsayılana döndürülecek ve ses motoru durdurulacak. "
                "Dil, tema, diğer uygulama tercihleri ve kayıtlı profiller korunacak. Devam edilsin mi?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return

        from ..dsp import Settings

        defaults = AppConfig()
        if self.engine.state in ("running", "reconnecting"):
            self.engine.stop()
        self._apply_dsp_settings(Settings())
        self.cfg.mic_key = defaults.mic_key
        self.cfg.out_key = defaults.out_key
        self.cfg.monitor_key = defaults.monitor_key
        self.cfg.latency_mode = defaults.latency_mode
        self.engine.set_latency_mode(defaults.latency_mode)
        self.cb_lat.setCurrentIndex(self.cb_lat.findData(defaults.latency_mode))
        self.populate_devices()
        if not self._save():
            QMessageBox.warning(self, APP_NAME, self._t("Ayarlar kaydedilemedi. Günlük dosyasını kontrol edin."))
        self._refresh_status()
        dialog.reject()
        QMessageBox.information(self, APP_NAME, self._t("Ses ayarları varsayılana döndürüldü."))

    def _save(self):
        self._save_timer.stop()
        try:
            self.cfg.save()
        except OSError:
            log.exception("Ayarlar kaydedilemedi")
            return False
        return True

    def _gain_changed(self, v: int):
        db = v / 10.0
        self.lbl_gain.setText(f"+{db:.1f} dB")
        self._set("mic_gain_db", db)

    def _latency_changed(self, _):
        mode = self.cb_lat.currentData()
        self.cfg.latency_mode = mode
        self.engine.set_latency_mode(mode)
        self._save_timer.start()

    # ================================================================ aygıtlar
    def populate_devices(self):
        self._devices_loaded = False
        for cb in (self.cb_mic, self.cb_out, self.cb_mon):
            cb.blockSignals(True)
            cb.clear()
        try:
            devs = dev.all_devices()
        except Exception as e:
            log.exception("Aygıtlar listelenemedi")
            self.lbl_test.setText(self._t("Ses aygıtları okunamadı (PortAudio): {e}").format(e=e))
            self._devices_loaded = True
            self._cable_available = False
            for cb in (self.cb_mic, self.cb_out, self.cb_mon):
                cb.blockSignals(False)
            self._refresh_status()
            return
        for d in dev.input_devices(devs):
            self.cb_mic.addItem(d.name, d.key)
        for d in dev.output_devices(devs):
            self.cb_out.addItem(d.name, d.key)
        for d in dev.monitor_devices(devs):
            self.cb_mon.addItem(d.name, d.key)

        def select(cb, key, fallback=None):
            i = cb.findData(key) if key else -1
            if i < 0 and key:
                device_name = key.split("|", 1)[0]
                i = next((index for index in range(cb.count())
                          if cb.itemText(index) == device_name), -1)
            if i < 0 and key:
                cb.insertItem(0, self._t("Kaydedilmiş aygıt (şu an kullanılamıyor)"), key)
                i = 0
            elif i < 0 and fallback is not None:
                i = cb.findData(fallback.key)
            cb.setCurrentIndex(max(0, i) if cb.count() else -1)

        select(self.cb_mic, self.cfg.mic_key, dev.default_input(devs))
        cable = dev.find_cable_render(devs)
        self._cable_available = cable is not None
        # Sanal kablo varsa her zaman onu öner (kayıtlı seçim farklıysa kayıtlıyı koru)
        select(self.cb_out, self.cfg.out_key, cable)
        select(self.cb_mon, self.cfg.monitor_key)
        for cb in (self.cb_mic, self.cb_out, self.cb_mon):
            cb.blockSignals(False)
        self._devices_loaded = True
        self._dev_changed()
        self._refresh_status()

    def _dev_changed(self, *_):
        mic_key = self.cb_mic.currentData()
        out_key = self.cb_out.currentData()
        monitor_key = self.cb_mon.currentData()
        if mic_key:
            self.cfg.mic_key = mic_key
        if out_key:
            self.cfg.out_key = out_key
        if monitor_key:
            self.cfg.monitor_key = monitor_key
        self._save_timer.start()

    def _refresh_devices_clicked(self):
        was_running = self.engine.state in ("running", "reconnecting")
        if was_running:
            self.engine.stop()
        try:
            dev.refresh_portaudio()
        except Exception:
            log.exception("PortAudio yenilenemedi")
        self.populate_devices()
        if was_running:
            self._start()

    # ================================================================ motor
    def _toggle_engine(self):
        if self.engine.state in ("running", "reconnecting"):
            self.engine.stop()
            playback.stop()
        else:
            self._start()
        self._refresh_status()

    def _start(self):
        mic_key, out_key = self.cb_mic.currentData(), self.cb_out.currentData()
        if not mic_key:
            QMessageBox.warning(self, APP_NAME, self._t("Bir mikrofon seçin."))
            return
        out_name = self.cb_out.currentText()
        if not out_key or not dev.is_cable_render(out_name):
            box = QMessageBox(self)
            box.setWindowTitle(APP_NAME)
            box.setIcon(QMessageBox.Warning)
            has_cable = dev.find_cable_render() is not None
            if has_cable:
                box.setText(self._t("Çıkış olarak sanal kablo (CABLE Input) seçili değil."))
                box.setInformativeText(self._t(
                    "Discord/oyunlar sesinizi ancak 'CABLE Input' çıkışına yazarsanız duyar. "
                    "Yine de bu çıkışa başlatılsın mı? (yalnızca test için)"))
            else:
                box.setText(self._t("Sanal kablo bulunamadı."))
                box.setInformativeText(self._t(
                    "Discord/oyunların işlenmiş sesi mikrofon olarak görmesi için ücretsiz VB-CABLE "
                    "sanal ses sürücüsünü kurmanız gerekir (docs/KULLANIM_KILAVUZU.md). Kurulumdan "
                    "sonra bilgisayarı yeniden başlatın, sonra 'Aygıtları yenile'ye basın."))
            b_open = box.addButton(self._t("VB-CABLE sayfasını aç"), QMessageBox.ActionRole)
            b_go = box.addButton(self._t("Yine de başlat (test)"), QMessageBox.AcceptRole)
            box.addButton(self._t("İptal"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is b_open:
                QDesktopServices.openUrl(QUrl(VBCABLE_URL))
                return
            if box.clickedButton() is not b_go:
                return
        ok = self.engine.start(mic_key, out_key)
        if not ok and self.engine.state == "error":
            QMessageBox.critical(self, APP_NAME, self.engine.message)
        self._refresh_status()

    def _refresh_status(self):
        if not self._devices_loaded:
            return
        st = self.engine.state
        out_is_cable = dev.is_cable_render(self.cb_out.currentText())
        if st == "running":
            if out_is_cable:
                self.pill.set_state("ok", self._t("Sanal mikrofon bağlı — uygulamalarda “CABLE Output” seçin"))
            else:
                self.pill.set_state("warn", self._t("Çalışıyor, ancak çıkış sanal kablo DEĞİL"))
        elif st == "reconnecting":
            self.pill.set_state("warn", self.engine.message or self._t("Yeniden bağlanıyor…"))
        elif st == "error":
            self.pill.set_state("bad", self.engine.message or self._t("Hata"))
        else:
            if self._cable_available:
                self.pill.set_state("idle", self._t("Durdu — sanal kablo bulundu"))
            else:
                self.pill.set_state("bad", self._t("Sanal kablo (VB-CABLE) bulunamadı"))
        running = st in ("running", "reconnecting")
        self.btn_start.setText(self._t("■  DURDUR" if running else "▶  BAŞLAT"))
        self.btn_start.setObjectName("stop" if running else "primary")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        if st == "running":
            self.lbl_stats.setText(
                f"~{self.engine.est_latency_ms:.0f} ms gecikme · "
                f"kesinti {self.engine.out_underruns} · yeniden bağlanma {self.engine.reconnects}")
        else:
            self.lbl_stats.setText("")
        if self.tray is not None:
            self._act_toggle.setText(self._t("Durdur" if running else "Başlat"))
            self.tray.setToolTip(f"{APP_NAME} — " + {
                "running": self._t("çalışıyor"), "reconnecting": self._t("yeniden bağlanıyor"),
                "error": self._t("hata")}.get(st, self._t("durdu")))

    # ================================================================ ölçüm döngüsü
    def _tick(self):
        if self.engine.state == "running":
            m = self.engine.read_meters()
            self.m_in.feed(m["in_peak_db"], m["in_rms_db"], m["clip_in"])
            self.m_out.feed(m["out_peak_db"], m["out_rms_db"], m["clip_out"])
            self.val_in.setText(self._t("tepe {peak} dB · RMS {rms} dB").format(
                peak=_fmt_db(self.m_in.peak_db), rms=_fmt_db(m["in_rms_db"])))
            self.val_out.setText(self._t("tepe {peak} dB · RMS {rms} dB").format(
                peak=_fmt_db(self.m_out.peak_db), rms=_fmt_db(m["out_rms_db"])))
            self.lbl_gate.setText(self._t("Kapı: ") + self._t("AÇIK" if m["gate_open"] else "kapalı"))
            self.lbl_comp.setText(f"Comp: {m['comp_gr_db']:.1f} dB")
            self.lbl_lim.setText(f"Limiter: {m['lim_gr_db']:.1f} dB")
            if m["clip_in"]:
                self.warn_clip.setText(self._t(
                    "⚠ GİRİŞ KIRPILIYOR (clipping). Mikrofon donanımı tam ölçeğe ulaşıyor; yazılım bunu "
                    "geri düzeltemez. Windows'taki mikrofon seviyesini/güçlendirmesini veya mikrofona "
                    "yakınlığı azaltın."))
                self.warn_clip.show()
            elif m["clip_out"]:
                self.warn_clip.setText(self._t("⚠ ÇIKIŞ KIRPILIYOR. Output Gain'i düşürün."))
                self.warn_clip.show()
            else:
                self.warn_clip.hide()
            if m["limiting"]:
                self.warn_lim.setText(self._t("Limiter devrede ({db:.1f} dB). Çok yüksek kazanç: "
                                              "ses bozulabilir, kazancı azaltmayı düşünün.").format(
                                                  db=m["lim_gr_db"]))
                self.warn_lim.show()
            else:
                self.warn_lim.hide()
        else:
            self.m_in.feed(-120, -120, False)
            self.m_out.feed(-120, -120, False)
            self.val_in.setText("—")
            self.val_out.setText("—")
            self.warn_clip.hide()
            self.warn_lim.hide()
        self._poll_capture()

    # ================================================================ test kaydı
    def _record_clicked(self):
        if self.engine.state != "running":
            QMessageBox.information(self, APP_NAME, self._t("Test kaydı için önce BAŞLAT'a basın."))
            return
        playback.stop()
        self._capture = None
        self.engine.begin_capture(5.0)
        self._recording = True
        self.btn_rec.setEnabled(False)
        for b in (self.btn_raw, self.btn_proc, self.btn_stopplay):
            b.setEnabled(False)
        self.lbl_test.setText(self._t("Kaydediliyor… 5 saniye normal sesinizle konuşun."))

    def _poll_capture(self):
        if not self._recording or self.engine.capture_active:
            return
        self._recording = False
        self.btn_rec.setEnabled(True)
        res = self.engine.capture_result()
        if res is None:
            self.lbl_test.setText(self._t("Kayıt alınamadı."))
            return
        import numpy as np
        raw, proc = res
        self._capture = res

        def stats(x):
            pk = float(np.max(np.abs(x))) if len(x) else 0.0
            act = x[np.abs(x) > 10 ** (-60 / 20)]
            rms = float(np.sqrt(np.mean(act ** 2))) if len(act) else 0.0
            f = lambda v: 20 * math.log10(max(v, 1e-6))
            return f(pk), f(rms)

        rp, rr = stats(raw)
        pp, pr = stats(proc)
        self.lbl_test.setText(self._t(
            "Orijinal:  tepe {rp:.1f} dB · konuşma RMS {rr:.1f} dB\n"
            "İşlenmiş: tepe {pp:.1f} dB · konuşma RMS {pr:.1f} dB   →  fark {diff:+.1f} dB").format(
                rp=rp, rr=rr, pp=pp, pr=pr, diff=pr - rr))
        for b in (self.btn_raw, self.btn_proc, self.btn_stopplay):
            b.setEnabled(True)

    def _play(self, which: int):
        if not self._capture:
            return
        d = dev.find_by_key(self.cb_mon.currentData() or "", "mon")
        try:
            playback.play(self._capture[which], self.engine.sr, d)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, self._t("Oynatılamadı: {error}").format(error=e))

    # ================================================================ kapanış / tepsi
    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        self._really_quit = True
        self.close()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.isMinimized():
            self._set_ui_timers_active(True)

    def hideEvent(self, event):
        self._set_ui_timers_active(False)
        super().hideEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._set_ui_timers_active(not self.isMinimized() and self.isVisible())

    def _set_ui_timers_active(self, active: bool):
        for timer in (self._tick_timer, self._status_timer):
            if active and not timer.isActive():
                timer.start()
            elif not active and timer.isActive():
                timer.stop()
        if active:
            self._refresh_status()

    def closeEvent(self, e):
        self._save()
        # X'e basınca kapanmak yerine tepsiye iner; motor çalışmaya devam eder.
        # Tamamen kapatmak için: tepsi simgesine sağ tık → Çıkış.
        if (not self._really_quit and self.cfg.close_behavior == "tray"
            and self.tray is not None and self.tray.isVisible()):
            e.ignore()
            self.hide()
            if not getattr(self, "_tray_hint_shown", False):
                self._tray_hint_shown = True
                self.tray.showMessage(APP_NAME, self._t("Arka planda çalışmaya devam ediyor. "
                                      "Kapatmak için simgeye sağ tıklayıp Çıkış'ı seçin."),
                                      QSystemTrayIcon.Information, 4000)
            return
        playback.stop()
        self.engine.shutdown()
        if self.tray is not None:
            self.tray.hide()
        e.accept()
        QApplication.quit()
