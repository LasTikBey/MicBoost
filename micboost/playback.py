"""Test kaydını kulaklık/hoparlörden dinletme (sanal kabloya GİTMEZ)."""
from __future__ import annotations

import numpy as np

from . import devices as dev


def play(data: np.ndarray, sr: int, device: dev.Device | None) -> None:
    import sounddevice as sd
    sd.stop()
    stereo = np.column_stack((data, data)).astype(np.float32)
    extra = None
    if device is not None and "wasapi" in device.hostapi.lower():
        try:
            extra = sd.WasapiSettings(exclusive=False, auto_convert=True)
        except TypeError:
            extra = sd.WasapiSettings(exclusive=False)
    sd.play(stereo, samplerate=sr, device=None if device is None else device.index,
            extra_settings=extra)


def stop() -> None:
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:  # noqa: BLE001
        pass
