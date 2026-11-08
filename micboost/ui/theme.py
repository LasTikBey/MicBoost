"""Tema paleti ve stil tanımları."""

THEMES = {
    "dark": {
        "BG": "#202226",
        "CARD": "#292b30",
        "CARD_BORDER": "#3d4047",
        "TRACK": "#34373d",
        "TEXT": "#e8e8f2",
        "MUTED": "#8a8aa3",
        "ACCENT": "#2563eb",
        "ACCENT_DK": "#1d4ed8",
        "BLUE": "#3b82f6",
        "CYAN": "#22d3ee",
        "GREEN": "#22c55e",
        "AMBER": "#f59e0b",
        "RED": "#ef4444",
        "METER_PEAK": "#ffffff",
        "CLIP_OFF": "#2a1a20",
        "SWITCH_OFF": "#2c2c3b",
        "SLIDER_HANDLE": "#f4f4ff",
    },
    "light": {
        "BG": "#eef1f5",
        "CARD": "#ffffff",
        "CARD_BORDER": "#d5dbe4",
        "TRACK": "#e4e9f0",
        "TEXT": "#202733",
        "MUTED": "#536174",
        "ACCENT": "#1d5bbf",
        "ACCENT_DK": "#174a9e",
        "BLUE": "#2c70c7",
        "CYAN": "#087f9b",
        "GREEN": "#087a50",
        "AMBER": "#a85c00",
        "RED": "#bd2833",
        "METER_PEAK": "#ffffff",
        "CLIP_OFF": "#eadfe0",
        "SWITCH_OFF": "#c7ccd7",
        "SLIDER_HANDLE": "#ffffff",
    },
}

globals().update(THEMES["dark"])


def build_qss(name: str = "dark") -> str:
    palette = THEMES.get(name, THEMES["dark"])
    bg = palette["BG"]
    card = palette["CARD"]
    card_border = palette["CARD_BORDER"]
    track = palette["TRACK"]
    text = palette["TEXT"]
    muted = palette["MUTED"]
    accent = palette["ACCENT"]
    accent_dk = palette["ACCENT_DK"]
    cyan = palette["CYAN"]
    amber = palette["AMBER"]
    red = palette["RED"]
    slider_handle = palette["SLIDER_HANDLE"]
    card_radius = "8px" if name == "light" else "0px"
    control_radius = "6px" if name == "light" else "0px"
    return f"""
* {{ font-family: "Montserrat", sans-serif; font-size: 13px; color: {text}; }}
QMainWindow, QDialog, QWidget#root {{ background: {bg}; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {muted}; }}
QLabel#h1 {{ font-size: 22px; font-weight: 700; }}
QLabel#cardTitle {{ font-size: 12px; font-weight: 700; color: {muted}; letter-spacing: 1px; }}
QLabel#bigValue {{ font-size: 46px; font-weight: 700; color: {text}; }}
QLabel#warn {{ color: {red}; font-weight: 600; }}
QLabel#info {{ color: {amber}; font-weight: 600; }}

QFrame#card {{ background: {card}; border: 1px solid {card_border}; border-radius: {card_radius}; }}

QGroupBox {{
    background: {card}; border: 1px solid {card_border}; border-radius: {control_radius};
    margin-top: 8px; padding: 12px 10px 10px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 6px; color: {muted};
}}

QPushButton {{
    background: {track}; border: 1px solid {card_border}; border-radius: {control_radius};
    padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {muted}; border-color: {card_border}; }}
QPushButton#primary, QPushButton#profileSave {{
    border: none; font-size: 16px; font-weight: 700; padding: 14px 28px; border-radius: {control_radius};
    background: {accent}; color: #ffffff;
}}
QPushButton#primary:hover {{ background: {accent_dk}; }}
QPushButton#stop {{
    border: none; font-size: 16px; font-weight: 700; padding: 14px 28px; border-radius: 0px;
    background: #3a1d28; color: #ffb4c0;
}}
QPushButton#stop:hover {{ background: #4b2230; }}

QLineEdit {{
    background: {track}; border: 1px solid {card_border}; border-radius: {control_radius};
    padding: 8px 10px; min-height: 22px; selection-background-color: {accent_dk};
}}
QLineEdit:hover {{ border-color: {accent}; }}
QLineEdit:focus {{ border: 1px solid {accent}; }}
QLineEdit:disabled {{ color: {muted}; background: {bg}; }}

QComboBox {{
    background: {track}; border: 1px solid {card_border}; border-radius: 2px;
    padding: 8px 34px 8px 12px; min-height: 22px;
}}
QComboBox:hover {{ border-color: {accent}; }}
QComboBox:focus {{ border: 1px solid {accent}; }}
QComboBox:disabled {{ color: {muted}; background: {bg}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: top right; width: 30px;
    border: none; background: transparent;
}}
QComboBox QAbstractItemView {{
    background: {card}; border: 1px solid {card_border};
    selection-background-color: {accent_dk}; selection-color: #ffffff;
    outline: 0; padding: 0; show-decoration-selected: 0;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 28px 8px 12px; border: none;
}}
QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected {{
    background: {accent_dk}; color: #ffffff;
}}

QMenu {{
    background: {card}; color: {text};
    border: 1px solid {card_border}; padding: 5px;
}}
QMenu::item {{
    background: transparent; color: {text}; padding: 8px 28px 8px 12px;
}}
QMenu::item:selected {{
    background: {accent_dk}; color: #ffffff;
}}
QMenu::item:disabled {{ color: {muted}; }}
QMenu::separator {{
    height: 1px; background: {card_border}; margin: 5px 7px;
}}

QSlider:horizontal {{ min-height: 40px; }}
QSlider::groove:horizontal {{ height: 12px; background: {card_border}; border-radius: 6px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {slider_handle}; width: 24px; height: 24px; margin: -6px 0;
    border-radius: 12px; border: 3px solid {accent};
}}
QSlider::handle:horizontal:hover {{ border-color: {cyan}; }}
QSlider::handle:horizontal:disabled {{ background: {muted}; border-color: {card_border}; }}

QSlider::groove:vertical {{ width: 12px; background: {card_border}; margin: 12px 6px; border-radius: 6px; }}
QSlider::sub-page:vertical {{ background: {card_border}; }}
QSlider::add-page:vertical {{ background: {accent}; }}
QSlider::handle:vertical {{
    height: 18px; margin: 0 -6px; background: {slider_handle};
    border: 3px solid {accent}; border-radius: 12px;
}}
QSlider::handle:vertical:hover {{ border-color: {cyan}; }}

QSlider#bigGain::groove:horizontal {{ height: 12px; background: {card_border}; border-radius: 6px; }}
QSlider#bigGain::sub-page:horizontal {{ background: {accent}; border-radius: 6px; }}
QSlider#bigGain::handle:horizontal {{
    width: 24px; height: 24px; margin: -6px 0; border-radius: 12px;
    background: {slider_handle}; border: 3px solid {accent};
}}
QSlider#bigGain::handle:horizontal:hover {{ border-color: {cyan}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {card_border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background: {card}; color: {text}; border: 1px solid {card_border}; padding: 4px; }}
"""


def apply(app=None, name: str = "dark") -> str:
    palette = THEMES.get(name, THEMES["dark"])
    globals().update(palette)
    global QSS
    QSS = build_qss(name)
    if app is not None:
        app.setStyleSheet(QSS)
    return QSS


QSS = build_qss()
