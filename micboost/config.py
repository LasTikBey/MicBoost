"""Kalıcı ayarlar (%APPDATA%\\MicBoost\\config.json) ve günlükleme."""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
from dataclasses import dataclass, field
from pathlib import Path

from .dsp import Settings


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / "MicBoost"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class AppConfig:
    dsp: Settings = field(default_factory=Settings)
    mic_key: str = ""
    out_key: str = ""
    monitor_key: str = ""
    latency_mode: str = "low"         # low | normal | safe
    autostart_engine: bool = False    # uygulama açılınca otomatik başlat
    language: str = "en"
    theme: str = "dark"              # dark | light
    close_behavior: str = "tray"     # tray | quit
    profiles: dict[str, dict] = field(default_factory=dict)
    profile_names: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return app_dir() / "config.json"

    def save(self) -> None:
        data = {
            "dsp": self.dsp.to_dict(),
            "profiles": self.profiles,
            "profile_names": self.profile_names,
            "mic_key": self.mic_key, "out_key": self.out_key,
            "monitor_key": self.monitor_key,
            "latency_mode": self.latency_mode,
            "autostart_engine": self.autostart_engine,
            "language": self.language,
            "theme": self.theme,
            "close_behavior": self.close_behavior,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    @classmethod
    def load(cls) -> AppConfig:
        cfg = cls()
        try:
            d = json.loads(cfg.path.read_text(encoding="utf-8"))
            cfg.dsp = Settings.from_dict(d.get("dsp", {}))
            profiles = d.get("profiles", {})
            if isinstance(profiles, dict):
                cfg.profiles = {
                    str(slot): Settings.from_dict(values).to_dict()
                    for slot, values in profiles.items()
                    if str(slot) in {"1", "2", "3", "4", "5"} and isinstance(values, dict)
                }
            names = d.get("profile_names", {})
            if isinstance(names, dict):
                cfg.profile_names = {
                    str(slot): name.strip()[:32]
                    for slot, name in names.items()
                    if str(slot) in {"1", "2", "3", "4", "5"}
                    and isinstance(name, str) and name.strip()
                }
            cfg.mic_key = str(d.get("mic_key", ""))
            cfg.out_key = str(d.get("out_key", ""))
            cfg.monitor_key = str(d.get("monitor_key", ""))
            cfg.latency_mode = str(d.get("latency_mode", "low"))
            cfg.autostart_engine = bool(d.get("autostart_engine", False))
            cfg.language = str(d.get("language", "en"))
            if cfg.language not in ("tr", "en", "fr"):
                cfg.language = "en"
            cfg.theme = str(d.get("theme", "dark"))
            if cfg.theme not in ("dark", "light"):
                cfg.theme = "dark"
            cfg.close_behavior = str(d.get("close_behavior", "tray"))
            if cfg.close_behavior not in ("tray", "quit"):
                cfg.close_behavior = "tray"
        except (OSError, ValueError):
            pass
        return cfg


def setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        app_dir() / "micboost.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
