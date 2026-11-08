"""MicBoost ses motoru: fiziksel mikrofon -> DSP -> sanal kablo (render ucu).

Mimari
------
    [Fiziksel mikrofon] --InputStream--> input callback
            (yeniden bloklama: 256 örnek) -> MicProcessor.process -> RingBuffer
    RingBuffer --OutputStream--> output callback -> [CABLE Input]  (sanal kablo)
    [CABLE Output] = Discord / oyun / Zoom'da seçilen "mikrofon"

İki aygıtın saat kristali farklı olduğundan (drift) tek bir duplex akış yerine iki
ayrı akış + sürüklenme toleranslı halka tampon kullanılır.
Bir izleme (watchdog) iş parçacığı callback'lerin durmasını / aygıtın çıkarılmasını
algılar ve aygıt geri geldiğinde akışları kendiliğinden yeniden açar.
"""
from __future__ import annotations

import logging
import threading
import time

import numpy as np

from . import devices as dev
from .dsp import BLOCK, MicProcessor, Settings, lin_to_db

log = logging.getLogger("micboost.engine")

SAMPLE_RATE = 48000

# Tampon önayarları: (hedef doluluk, üst sınır) örnek cinsinden
LATENCY_PRESETS = {
    "low": (384, 1024),
    "normal": (1024, 2560),
    "safe": (2048, 4608),
}


class RingBuffer:
    """Tek üretici/tek tüketici, kilitli, mono float32 halka tampon."""

    def __init__(self, capacity: int):
        self.cap = capacity
        self.buf = np.zeros(capacity, np.float32)
        self.r = 0
        self.size = 0
        self.lock = threading.Lock()
        self.overruns = 0

    def clear(self):
        with self.lock:
            self.r = 0
            self.size = 0

    def write(self, x: np.ndarray):
        n = len(x)
        with self.lock:
            if n > self.cap:
                x, n = x[-self.cap:], self.cap
                self.overruns += 1
            free = self.cap - self.size
            if n > free:                       # taşma: en eski örnekleri at
                drop = n - free
                self.r = (self.r + drop) % self.cap
                self.size -= drop
                self.overruns += 1
            w = (self.r + self.size) % self.cap
            first = min(n, self.cap - w)
            self.buf[w:w + first] = x[:first]
            if first < n:
                self.buf[:n - first] = x[first:]
            self.size += n

    def drop_to(self, keep: int):
        with self.lock:
            if self.size > keep:
                d = self.size - keep
                self.r = (self.r + d) % self.cap
                self.size = keep

    def read(self, n: int):
        """Döner: (veri[n], yetersiz_mi)."""
        out = np.zeros(n, np.float32)
        with self.lock:
            m = min(n, self.size)
            first = min(m, self.cap - self.r)
            out[:first] = self.buf[self.r:self.r + first]
            if first < m:
                out[first:m] = self.buf[:m - first]
            self.r = (self.r + m) % self.cap
            self.size -= m
        return out, m < n


class AudioEngine:
    def __init__(self, settings: Settings, sr: int = SAMPLE_RATE):
        self.settings = settings
        self.sr = sr
        self.proc = MicProcessor(sr)
        self.latency_mode = "normal"
        self.ring = RingBuffer(16384)
        self._lock = threading.RLock()
        self._in_stream = None
        self._out_stream = None
        self._stage = np.zeros(0, np.float32)
        self._prebuf = True
        self._target, self._high = LATENCY_PRESETS["normal"]

        self.state = "stopped"        # stopped | running | reconnecting | error
        self.message = ""
        self._in_key = ""
        self._out_key = ""
        self._want_running = False
        self._last_cb = 0.0
        self._watchdog = None
        self._stop_evt = threading.Event()

        # sayaçlar
        self.in_status_errors = 0
        self.out_underruns = 0
        self.cb_exceptions = 0
        self.reconnects = 0
        # ölçümler (son okumadan beri tepe değerler)
        self._mlock = threading.Lock()
        self._acc = self._new_acc()
        self._clip_in_until = 0.0
        self._clip_out_until = 0.0
        # test kaydı
        self._cap_n = 0
        self._cap_raw: list[np.ndarray] = []
        self._cap_proc: list[np.ndarray] = []

    # ------------------------------------------------------------------ yardımcılar
    @staticmethod
    def _new_acc():
        return dict(raw_peak=0.0, in_peak=0.0, in_rms=0.0, out_peak=0.0, out_rms=0.0,
                    comp_gr=0.0, lim_gr=0.0, agc_gain=0.0, gate_open=False)

    def _sd(self):
        import sounddevice as sd
        return sd

    def set_latency_mode(self, mode: str):
        self.latency_mode = mode if mode in LATENCY_PRESETS else "normal"
        self._target, self._high = LATENCY_PRESETS[self.latency_mode]

    @property
    def est_latency_ms(self) -> float:
        """Kabaca: DSP + halka tampon + (varsayılan ~10 ms) giriş ve çıkış tamponları."""
        return self.proc.latency_ms + 1000.0 * self._target / self.sr + 20.0

    # ------------------------------------------------------------------ açma / kapama
    def start(self, in_key: str, out_key: str) -> bool:
        """Akışları başlatır. Aygıt şu an yoksa izleme iş parçacığı beklemeye geçer."""
        with self._lock:
            self.stop()
            self._in_key, self._out_key = in_key, out_key
            self._want_running = True
            self._stop_evt.clear()
            ok = self._try_open()
            self._ensure_watchdog()
            return ok

    def stop(self):
        with self._lock:
            self._want_running = False
            self._close_streams()
            self.state = "stopped"
            self.message = ""

    def shutdown(self):
        self.stop()
        self._stop_evt.set()

    def _close_streams(self):
        for name in ("_in_stream", "_out_stream"):
            st = getattr(self, name)
            setattr(self, name, None)
            if st is not None:
                try:
                    st.abort()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    st.close()
                except Exception:  # noqa: BLE001
                    pass

    def _try_open(self) -> bool:
        with self._lock:
            try:
                d_in = dev.find_by_key(self._in_key, "in")
                d_out = dev.find_by_key(self._out_key, "out")
                if d_in is None:
                    self.state, self.message = "reconnecting", "Mikrofon bulunamadı, bekleniyor…"
                    return False
                if d_out is None:
                    self.state, self.message = "reconnecting", "Sanal kablo (CABLE Input) bulunamadı."
                    return False
                if dev.is_cable_capture(d_in.name):
                    self.state, self.message = "error", "Giriş olarak sanal kablo seçilemez (geri besleme)."
                    return False
                self._open_streams(d_in, d_out)
                self.state, self.message = "running", ""
                self._last_cb = time.monotonic()
                return True
            except Exception as e:  # noqa: BLE001
                log.exception("Akış açılamadı")
                self._close_streams()
                self.state = "reconnecting" if self._want_running else "error"
                self.message = f"Akış açılamadı: {e}"
                return False

    def _open_streams(self, d_in: dev.Device, d_out: dev.Device):
        sd = self._sd()
        in_ch = 1
        out_ch = max(1, min(2, d_out.max_out))
        attempts = [(self.sr, True), (self.sr, False)]
        if abs(d_in.default_sr - self.sr) > 1 and abs(d_in.default_sr - d_out.default_sr) < 1:
            attempts.append((int(d_in.default_sr), True))
        last_err = None
        for sr, auto in attempts:
            self._reset_pipeline(sr)
            try:
                in_extra = out_extra = None
                if "wasapi" in d_in.hostapi.lower():
                    in_extra = self._wasapi(sd, auto)
                if "wasapi" in d_out.hostapi.lower():
                    out_extra = self._wasapi(sd, auto)
                self._out_stream = sd.OutputStream(
                    device=d_out.index, samplerate=sr, channels=out_ch, dtype="float32",
                    latency="low", callback=self._out_cb, extra_settings=out_extra)
                self._in_stream = sd.InputStream(
                    device=d_in.index, samplerate=sr, channels=in_ch, dtype="float32",
                    latency="low", callback=self._in_cb, extra_settings=in_extra)
                self._out_stream.start()
                self._in_stream.start()
                return
            except Exception as e:  # noqa: BLE001
                last_err = e
                self._close_streams()
        raise RuntimeError(str(last_err))

    @staticmethod
    def _wasapi(sd, auto: bool):
        try:
            return sd.WasapiSettings(exclusive=False, auto_convert=auto)
        except TypeError:   # eski sounddevice sürümü
            return sd.WasapiSettings(exclusive=False)

    def _reset_pipeline(self, sr: int):
        self.sr = sr
        self.proc = MicProcessor(sr)
        self.ring.clear()
        self._stage = np.zeros(0, np.float32)
        self._prebuf = True

    # ------------------------------------------------------------------ callback'ler
    def _in_cb(self, indata, frames, time_info, status):
        try:
            self._last_cb = time.monotonic()
            if status:
                self.in_status_errors += 1
            mono = indata[:, 0] if indata.shape[1] == 1 else indata.mean(axis=1)
            self._stage = np.concatenate((self._stage, mono))
            s = self.settings
            while len(self._stage) >= BLOCK:
                blk, self._stage = self._stage[:BLOCK], self._stage[BLOCK:]
                y, info = self.proc.process(blk, s)
                self.ring.write(y)
                self._record(blk, y, info, s)
        except Exception:  # noqa: BLE001
            self.cb_exceptions += 1
            log.exception("input callback hatası")

    def _out_cb(self, outdata, frames, time_info, status):
        try:
            if status:
                self.out_underruns += 1
            if self._prebuf:
                if self.ring.size >= max(self._target, frames):
                    self._prebuf = False
                else:
                    outdata.fill(0)
                    return
            if self.ring.size > self._high:           # saat kayması: gecikmeyi geri çek
                self.ring.drop_to(self._target)
            data, short = self.ring.read(frames)
            if short:
                self.out_underruns += 1
                self._prebuf = True
            outdata[:] = data[:, None]
        except Exception:  # noqa: BLE001
            self.cb_exceptions += 1
            outdata.fill(0)

    def _record(self, raw_trimmed_src, y, info, s):
        now = time.monotonic()
        if info["raw_peak"] >= 0.99:
            self._clip_in_until = now + 1.5
        if info["out_peak"] >= 0.999:
            self._clip_out_until = now + 1.5
        with self._mlock:
            a = self._acc
            for k in ("raw_peak", "in_peak", "in_rms", "out_peak", "out_rms"):
                a[k] = max(a[k], info.get(k, 0.0))
            a["comp_gr"] = min(a["comp_gr"], info.get("comp_gr", 0.0))
            a["lim_gr"] = min(a["lim_gr"], info.get("lim_gr", 0.0))
            a["agc_gain"] = info.get("agc_gain", 0.0)
            a["gate_open"] = info.get("gate_open", False)
        if self._cap_n > 0:
            self._cap_raw.append((raw_trimmed_src * (s.input_volume / 100.0)).astype(np.float32))
            self._cap_proc.append(y.copy())
            self._cap_n -= len(y)

    # ------------------------------------------------------------------ ölçümler
    def read_meters(self) -> dict:
        """Son çağrıdan beri biriken tepe değerleri dB olarak döndürür ve sıfırlar."""
        with self._mlock:
            a, self._acc = self._acc, self._new_acc()
        now = time.monotonic()
        return {
            "in_peak_db": lin_to_db(a["in_peak"]),
            "in_rms_db": lin_to_db(a["in_rms"]),
            "out_peak_db": lin_to_db(a["out_peak"]),
            "out_rms_db": lin_to_db(a["out_rms"]),
            "comp_gr_db": a["comp_gr"],
            "lim_gr_db": a["lim_gr"],
            "agc_gain_db": a["agc_gain"],
            "gate_open": a["gate_open"],
            "clip_in": now < self._clip_in_until,
            "clip_out": now < self._clip_out_until,
            "limiting": a["lim_gr"] < -0.5,
            "underruns": self.out_underruns,
            "overruns": self.ring.overruns,
            "reconnects": self.reconnects,
            "buffer_ms": 1000.0 * self.ring.size / self.sr,
        }

    # ------------------------------------------------------------------ test kaydı
    def begin_capture(self, seconds: float = 5.0):
        self._cap_raw, self._cap_proc = [], []
        self._cap_n = int(seconds * self.sr)

    @property
    def capture_active(self) -> bool:
        return self._cap_n > 0

    def capture_result(self):
        if self._cap_n > 0 or not self._cap_raw:
            return None
        raw = np.concatenate(self._cap_raw)
        proc = np.concatenate(self._cap_proc)
        return raw, proc

    # ------------------------------------------------------------------ izleme
    def _ensure_watchdog(self):
        if self._watchdog is None or not self._watchdog.is_alive():
            self._watchdog = threading.Thread(target=self._watch, daemon=True,
                                              name="micboost-watchdog")
            self._watchdog.start()

    def _watch(self):
        while not self._stop_evt.wait(1.0):
            with self._lock:
                if not self._want_running:
                    continue
                stalled = (self.state == "running" and
                           time.monotonic() - self._last_cb > 2.0)
                dead = (self.state == "running" and
                        (self._in_stream is None or self._out_stream is None or
                         not self._in_stream.active or not self._out_stream.active))
                if stalled or dead:
                    log.warning("Akış durdu (stalled=%s dead=%s); yeniden bağlanılıyor", stalled, dead)
                    self._close_streams()
                    self.state, self.message = "reconnecting", "Aygıt bağlantısı koptu, yeniden deneniyor…"
                    self.reconnects += 1
                if self.state == "reconnecting":
                    try:
                        dev.refresh_portaudio()   # akış yokken güvenli
                    except Exception:  # noqa: BLE001
                        log.exception("PortAudio yenilenemedi")
                    self._try_open()
