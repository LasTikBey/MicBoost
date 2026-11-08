"""MicBoost - gerçek zamanlı ses işleme zinciri (saf numpy/scipy).

Zincir sırası:
    Input Volume -> HPF(80 Hz) -> Noise Suppression -> Noise Gate -> Equalizer
    -> Mic Gain -> AGC -> Compressor -> Output Gain -> Limiter

Tüm ayarlar `Settings` nesnesinden her blokta okunur; arayüz iş parçacığı bu
nesneyi istediği an değiştirebilir (ayar değişimleri blok içinde rampalanır,
tıkırtı oluşmaz).

Tasarım notları
---------------
* Kontrol hızı: dinamik işlemciler (gate/AGC/compressor) her SUB=32 örnekte
  (48 kHz'de ~0.67 ms) bir kazanç hesaplar ve örnek seviyesinde lineer
  enterpolasyon yapar. Böylece Python döngüsü ses hızından ~32 kat yavaş çalışır.
* Limiter lookahead'li (1.5 ms) ve tepe değeri garanti eder: çıkış hiçbir zaman
  tavan seviyesini aşmaz.
* Gürültü bastırma: STFT tabanlı spektral çıkarma (RNNoise gibi bir sinir ağı
  DEĞİL). Sabit gürültüde (fan, hışırtı) iyi; klavye tıkırtısı gibi ani
  seslerde sınırlı etkilidir. Bkz. docs/KULLANIM_KILAVUZU.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, fields

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import butter, lfilter, sosfilt

SUB = 32          # kontrol alt-bloğu (örnek)
BLOCK = 256       # önerilen işleme bloğu (gürültü bastırıcının hop'u ile aynı)


def db_to_lin(db: float) -> float:
    return 10.0 ** (db / 20.0)


def lin_to_db(x: float) -> float:
    return 20.0 * math.log10(max(x, 1e-12))


def _coef(tau_ms: float, rate_hz: float) -> float:
    """Tek kutuplu filtre katsayısı (state = c*state + (1-c)*input)."""
    if tau_ms <= 0:
        return 0.0
    return math.exp(-1.0 / (tau_ms * 1e-3 * rate_hz))


# --------------------------------------------------------------------------
# Ayarlar
# --------------------------------------------------------------------------
@dataclass
class Settings:
    # Seviye
    input_volume: float = 100.0      # % (0..200) yazılımsal giriş seviyesi
    mic_gain_db: float = 12.0        # 0..+30 dB
    output_gain_db: float = 0.0      # -20..+12 dB
    bypass: bool = False             # True: yalnızca input_volume uygulanır (A/B testi)
    # Gürültü bastırma
    ns_on: bool = True
    ns_strength: float = 0.5         # 0..1
    # Ekolayzer: 5 sabit merkez frekansta tepe filtresi kazançları (dB)
    eq_on: bool = False
    eq_100_db: float = 0.0
    eq_300_db: float = 0.0
    eq_1k_db: float = 0.0
    eq_3k_db: float = 0.0
    eq_10k_db: float = 0.0
    # Noise gate
    gate_on: bool = True
    gate_threshold_db: float = -50.0  # dBFS (mikrofon ham seviyesine göre)
    gate_range_db: float = 40.0      # kapalıyken kaç dB bastırılsın
    # AGC
    agc_on: bool = False
    agc_target_db: float = -20.0     # dBFS RMS
    agc_max_gain_db: float = 20.0
    # Compressor
    comp_on: bool = True
    comp_threshold_db: float = -24.0
    comp_ratio: float = 3.0
    comp_attack_ms: float = 8.0
    comp_release_ms: float = 120.0
    comp_makeup_db: float = 0.0
    # Limiter
    limiter_on: bool = True
    limiter_ceiling_db: float = -1.0
    limiter_release_ms: float = 80.0

    def clamp(self) -> "Settings":
        def c(v, lo, hi):
            return max(lo, min(hi, v))
        self.input_volume = c(self.input_volume, 0.0, 200.0)
        self.mic_gain_db = c(self.mic_gain_db, 0.0, 30.0)
        self.output_gain_db = c(self.output_gain_db, -20.0, 12.0)
        self.ns_strength = c(self.ns_strength, 0.0, 1.0)
        for name in ("eq_100_db", "eq_300_db", "eq_1k_db", "eq_3k_db", "eq_10k_db"):
            setattr(self, name, c(getattr(self, name), -12.0, 12.0))
        self.gate_threshold_db = c(self.gate_threshold_db, -90.0, -10.0)
        self.gate_range_db = c(self.gate_range_db, 6.0, 80.0)
        self.agc_target_db = c(self.agc_target_db, -40.0, -6.0)
        self.agc_max_gain_db = c(self.agc_max_gain_db, 0.0, 30.0)
        self.comp_threshold_db = c(self.comp_threshold_db, -60.0, 0.0)
        self.comp_ratio = c(self.comp_ratio, 1.0, 20.0)
        self.comp_attack_ms = c(self.comp_attack_ms, 0.5, 100.0)
        self.comp_release_ms = c(self.comp_release_ms, 10.0, 1000.0)
        self.comp_makeup_db = c(self.comp_makeup_db, 0.0, 24.0)
        self.limiter_ceiling_db = c(self.limiter_ceiling_db, -12.0, -0.1)
        self.limiter_release_ms = c(self.limiter_release_ms, 5.0, 500.0)
        return self

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        s = cls()
        for f in fields(cls):
            if f.name in d:
                try:
                    setattr(s, f.name, type(getattr(s, f.name))(d[f.name]))
                except (TypeError, ValueError):
                    pass
        return s.clamp()


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------
def _sub_idx(n: int) -> np.ndarray:
    return np.arange(0, n, SUB)


def _sub_power(x: np.ndarray, idx: np.ndarray) -> np.ndarray:
    sums = np.add.reduceat(x * x, idx)
    counts = np.diff(np.append(idx, len(x)))
    return sums / counts


def _ramp(x: np.ndarray, g_prev: float, g_list, idx: np.ndarray) -> np.ndarray:
    """Alt-blok kazançlarını örnek seviyesine lineer enterpolasyonla uygula."""
    n = len(x)
    ends = np.minimum(idx + SUB, n)
    xp = np.concatenate(([0], ends))
    fp = np.concatenate(([g_prev], g_list))
    gains = np.interp(np.arange(1, n + 1), xp, fp)
    return x * gains


# --------------------------------------------------------------------------
# Gürültü bastırma (spektral çıkarma, streaming)
# --------------------------------------------------------------------------
class SpectralNoiseSuppressor:
    """50% örtüşmeli sqrt-Hann STFT, gecikme = N - H = 256 örnek.

    Blok boyutu H'nin (256) katı olmalıdır; değilse çıkış sonuna sıfır eklenir.
    """

    NOISE_BIAS = 1.65  # minimum-takibi gürültüyü olduğundan düşük tahmin eder
    NOISE_RISE_CONFIRM_FRAMES = 24
    NOISE_RISE_ALPHA = 0.015

    def __init__(self, n_fft: int = 512, hop: int = 256):
        self.N, self.H = n_fft, hop
        self.win = np.sqrt(np.hanning(n_fft + 1)[:-1])
        self.reset()

    @property
    def latency(self) -> int:
        return self.N - self.H

    def reset(self):
        n_bins = self.N // 2 + 1
        self.in_buf = np.zeros(0)
        self.ola = np.zeros(self.N)
        self.fifo = np.zeros(self.N - self.H)
        self.noise = None
        self.noise_rise_frames = 0
        self.mag_s = np.zeros(n_bins)
        self.pw_slow = np.zeros(n_bins)
        self.g = np.ones(n_bins)
        self.underruns = 0

    def process(self, x: np.ndarray, strength: float) -> np.ndarray:
        N, H = self.N, self.H
        self.in_buf = np.concatenate((self.in_buf, x))
        outs = []
        over = 1.0 + 2.5 * strength                 # aşırı çıkarma 1..3.5
        gmin = db_to_lin(-(8.0 + 22.0 * strength))  # taban kazanç -8..-30 dB
        gmin2 = gmin * gmin
        while len(self.in_buf) >= N:
            frame = self.in_buf[:N] * self.win
            spec = np.fft.rfft(frame)
            mag = np.abs(spec)
            self.mag_s = 0.5 * self.mag_s + 0.5 * mag
            pw_s = self.mag_s ** 2                      # hızlı yumuşatma (kazanç için)
            self.pw_slow = 0.85 * self.pw_slow + 0.15 * (mag * mag)  # yavaş (gürültü takibi)
            if self.noise is None:
                self.noise = (mag * mag).copy()
                self.pw_slow = self.noise.copy()
                self.noise_rise_frames = 0
            else:
                speech_activity = np.mean(self.pw_slow > self.noise * 2.5)
                spectrum = np.maximum(self.pw_slow[1:-1], 1e-14)
                flatness = np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum)
                noise_rising = np.mean(self.pw_slow) > 2.5 * np.mean(self.noise)
                if flatness > 0.35 and noise_rising:
                    self.noise_rise_frames += 1
                else:
                    self.noise_rise_frames = 0
                if self.noise_rise_frames >= self.NOISE_RISE_CONFIRM_FRAMES:
                    rising = np.where(
                        self.pw_slow > self.noise,
                        (1.0 - self.NOISE_RISE_ALPHA) * self.noise
                        + self.NOISE_RISE_ALPHA * self.pw_slow,
                        self.noise)
                    self.noise = np.where(
                        self.pw_slow < self.noise,
                        0.9 * self.noise + 0.1 * self.pw_slow,
                        rising)
                else:
                    self.noise = np.where(
                        self.pw_slow < self.noise,
                        0.9 * self.noise + 0.1 * self.pw_slow,
                        self.noise * (1.001 if speech_activity < 0.2 else 1.0))
            g2 = 1.0 - over * self.NOISE_BIAS * self.noise / np.maximum(pw_s, 1e-14)
            g = np.sqrt(np.maximum(g2, gmin2))
            # frekansta hafif yumuşatma (müzikal gürültüyü azaltır)
            gp = np.pad(g, 1, mode="edge")
            g = 0.25 * gp[:-2] + 0.5 * gp[1:-1] + 0.25 * gp[2:]
            # zamanda: hızlı açılma, yavaş kapanma
            self.g = np.where(g > self.g, 0.4 * self.g + 0.6 * g,
                              0.85 * self.g + 0.15 * g)
            y = np.fft.irfft(spec * self.g, N) * self.win
            self.ola += y
            outs.append(self.ola[:H].copy())
            self.ola = np.concatenate((self.ola[H:], np.zeros(H)))
            self.in_buf = self.in_buf[H:]
        if outs:
            self.fifo = np.concatenate([self.fifo] + outs)
        n = len(x)
        if len(self.fifo) >= n:
            out, self.fifo = self.fifo[:n], self.fifo[n:]
        else:
            self.underruns += 1
            out = np.concatenate((self.fifo, np.zeros(n - len(self.fifo))))
            self.fifo = np.zeros(0)
        return out


# --------------------------------------------------------------------------
# Noise gate
# --------------------------------------------------------------------------
class NoiseGate:
    def __init__(self, sr: int):
        self.rate = sr / SUB
        self.sp = 0.0
        self.open = False
        self.hold = 0
        self.g = 1.0

    def process(self, x: np.ndarray, s: Settings):
        """Döner: (çıkış, alt-blok başına 'açık' bayrakları)."""
        idx = _sub_idx(len(x))
        pows = _sub_power(x, idx).tolist()
        a_det = _coef(5.0, self.rate)
        a_att = _coef(1.5, self.rate)
        a_rel = _coef(150.0, self.rate)
        hold_n = int(0.22 * self.rate)
        thr = s.gate_threshold_db
        hyst = 5.0
        floor = db_to_lin(-s.gate_range_db)
        flags, gains = [], []
        sp, op, hold, g = self.sp, self.open, self.hold, self.g
        for p in pows:
            sp = a_det * sp + (1.0 - a_det) * p
            lvl = 10.0 * math.log10(sp + 1e-20)
            if lvl > thr or (op and lvl > thr - hyst):
                op, hold = True, hold_n
            elif hold > 0:
                hold -= 1
            else:
                op = False
            target = 1.0 if (op or not s.gate_on) else floor
            c = a_att if target > g else a_rel
            g = c * g + (1.0 - c) * target
            flags.append(op)
            gains.append(g)
        g_prev = self.g
        self.sp, self.open, self.hold, self.g = sp, op, hold, g
        return _ramp(x, g_prev, gains, idx), flags


# --------------------------------------------------------------------------
# Five-band parametric EQ
# --------------------------------------------------------------------------
class Equalizer:
    FREQUENCIES = (100.0, 300.0, 1000.0, 3000.0, 10000.0)
    ATTRS = ("eq_100_db", "eq_300_db", "eq_1k_db", "eq_3k_db", "eq_10k_db")
    Q = 1.0

    def __init__(self, sr: int):
        self.sr = sr
        self.x_hist = np.zeros((len(self.FREQUENCIES), 2))
        self.y_hist = np.zeros_like(self.x_hist)
        self._gain_cache = [None] * len(self.FREQUENCIES)
        self._b_cache = np.zeros((len(self.FREQUENCIES), 3))
        self._a_cache = np.zeros_like(self._b_cache)
        self._zi = np.zeros((len(self.FREQUENCIES), 2))

    @staticmethod
    def _last_two(x: np.ndarray) -> np.ndarray:
        if len(x) >= 2:
            return x[-2:]
        if len(x) == 1:
            return np.array([x[0], x[0]])
        return np.zeros(2)

    def process(self, x: np.ndarray, s: Settings) -> np.ndarray:
        gains = [getattr(s, name) if s.eq_on else 0.0 for name in self.ATTRS]
        if not any(gains):
            tail = self._last_two(x)
            self.x_hist[:] = tail
            self.y_hist[:] = tail
            return x

        y = x
        for index, (frequency, gain_db) in enumerate(zip(self.FREQUENCIES, gains)):
            if not gain_db:
                tail = self._last_two(y)
                self.x_hist[index] = tail
                self.y_hist[index] = tail
                continue

            frequency = min(frequency, self.sr * 0.45)
            if self._gain_cache[index] != gain_db:
                amplitude = 10.0 ** (gain_db / 40.0)
                omega = 2.0 * math.pi * frequency / self.sr
                alpha = math.sin(omega) / (2.0 * self.Q)
                cosine = math.cos(omega)
                a0 = 1.0 + alpha / amplitude
                self._b_cache[index] = (
                    (1.0 + alpha * amplitude) / a0,
                    (-2.0 * cosine) / a0,
                    (1.0 - alpha * amplitude) / a0,
                )
                self._a_cache[index] = (
                    1.0,
                    (-2.0 * cosine) / a0,
                    (1.0 - alpha / amplitude) / a0,
                )
                self._gain_cache[index] = gain_db
            _, b1, b2 = self._b_cache[index]
            _, a1, a2 = self._a_cache[index]
            x1, x2 = self.x_hist[index]
            y1, y2 = self.y_hist[index]
            self._zi[index] = (
                b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2,
                b2 * x1 - a2 * y1,
            )
            stage_input = y
            y, _ = lfilter(self._b_cache[index], self._a_cache[index],
                           stage_input, zi=self._zi[index])
            self.x_hist[index] = self._last_two(stage_input)
            self.y_hist[index] = self._last_two(y)
        return y


# --------------------------------------------------------------------------
# AGC
# --------------------------------------------------------------------------
class AGC:
    def __init__(self, sr: int):
        self.rate = sr / SUB
        self.sp = 1e-6
        self.gain_db = 0.0

    def process(self, x: np.ndarray, open_flags, s: Settings):
        idx = _sub_idx(len(x))
        pows = _sub_power(x, idx).tolist()
        a_lvl = _coef(120.0, self.rate)
        a_dn = _coef(60.0, self.rate)     # kazancı düşürme (hızlı)
        a_up = _coef(700.0, self.rate)    # kazancı artırma (yavaş)
        sp, gdb = self.sp, self.gain_db
        gains = []
        for p, op in zip(pows, open_flags):
            if op:                         # yalnızca konuşma varken seviye ölç/ayarla
                sp = a_lvl * sp + (1.0 - a_lvl) * p
                lvl = 10.0 * math.log10(sp + 1e-20)
                want = max(-12.0, min(s.agc_max_gain_db, s.agc_target_db - lvl))
                c = a_dn if want < gdb else a_up
                gdb = c * gdb + (1.0 - c) * want
            gains.append(10.0 ** (gdb / 20.0))
        g_prev = 10.0 ** (self.gain_db / 20.0)
        self.sp, self.gain_db = sp, gdb
        return _ramp(x, g_prev, gains, idx)


# --------------------------------------------------------------------------
# Compressor
# --------------------------------------------------------------------------
class Compressor:
    KNEE = 6.0

    def __init__(self, sr: int):
        self.rate = sr / SUB
        self.gr_db = 0.0   # mevcut kazanç azaltma (<= 0)

    def process(self, x: np.ndarray, s: Settings):
        idx = _sub_idx(len(x))
        peaks = np.maximum.reduceat(np.abs(x), idx).tolist()
        a_att = _coef(s.comp_attack_ms, self.rate)
        a_rel = _coef(s.comp_release_ms, self.rate)
        T, R, W = s.comp_threshold_db, s.comp_ratio, self.KNEE
        slope = 1.0 / R - 1.0
        gr = self.gr_db
        gains = []
        for pk in peaks:
            L = 20.0 * math.log10(pk + 1e-9)
            over = L - T
            if 2.0 * over < -W:
                tgt = 0.0
            elif 2.0 * abs(over) <= W:
                tgt = slope * (over + W / 2.0) ** 2 / (2.0 * W)
            else:
                tgt = slope * over
            c = a_att if tgt < gr else a_rel
            gr = c * gr + (1.0 - c) * tgt
            gains.append(10.0 ** ((gr + s.comp_makeup_db) / 20.0))
        g_prev = 10.0 ** ((self.gr_db + s.comp_makeup_db) / 20.0)
        self.gr_db = gr
        return _ramp(x, g_prev, gains, idx), gr


# --------------------------------------------------------------------------
# Limiter (lookahead, tepe garantili)
# --------------------------------------------------------------------------
class Limiter:
    def __init__(self, sr: int):
        self.sr = sr
        self.L = max(8, int(sr * 0.0015))
        self.dbuf = np.zeros(self.L)
        self.t_hist = np.ones(2 * self.L)
        self.r = 1.0

    @property
    def latency(self) -> int:
        return self.L

    def process(self, x: np.ndarray, s: Settings):
        L, n = self.L, len(x)
        ceiling = db_to_lin(s.limiter_ceiling_db) * 0.9999
        t = np.minimum(1.0, ceiling / np.maximum(np.abs(x), 1e-9))
        t_ext = np.concatenate((self.t_hist, t))
        m_ext = sliding_window_view(t_ext, L + 1).min(axis=1)       # L+n
        cs = np.concatenate(([0.0], np.cumsum(m_ext)))
        g = (cs[L + 1:] - cs[:n]) / (L + 1)                          # n
        self.t_hist = t_ext[-2 * L:]
        x_ext = np.concatenate((self.dbuf, x))
        y_d, self.dbuf = x_ext[:n], x_ext[n:]
        # release (kazanç yumuşak geri döner; tavan garantisi bozulmaz)
        r = self.r
        if r >= 0.99999 and g.min() >= 0.99999:
            gains = np.ones(n)
        else:
            alpha = 1.0 - math.exp(-1.0 / (s.limiter_release_ms * 1e-3 * self.sr))
            out = []
            for v in g.tolist():
                r = r + (1.0 - r) * alpha
                if v < r:
                    r = v
                out.append(r)
            gains = np.asarray(out)
            self.r = r
        return y_d * gains, float(gains.min())


# --------------------------------------------------------------------------
# Ana zincir
# --------------------------------------------------------------------------
class MicProcessor:
    """Tek kanallı (mono) float32/float64 blokları işler."""

    def __init__(self, sr: int = 48000):
        self.sr = sr
        self.hpf = butter(2, 80.0, btype="highpass", fs=sr, output="sos")
        self.hpf_zi = np.zeros((self.hpf.shape[0], 2))
        self.ns = SpectralNoiseSuppressor()
        self.gate = NoiseGate(sr)
        self.eq = Equalizer(sr)
        self.agc = AGC(sr)
        self.comp = Compressor(sr)
        self.lim = Limiter(sr)
        self._trim = 1.0
        self._mic = 1.0
        self._out = 1.0

    @property
    def latency_samples(self) -> int:
        return self.ns.latency + self.lim.latency

    @property
    def latency_ms(self) -> float:
        return 1000.0 * self.latency_samples / self.sr

    @staticmethod
    def _lin_ramp(x, g0, g1):
        if g0 == g1:
            return x * g1
        return x * np.linspace(g0, g1, len(x), endpoint=True)

    def process(self, block: np.ndarray, s: Settings):
        """Döner: (çıkış float32, info dict)."""
        raw = np.asarray(block, dtype=np.float64)
        info = {"raw_peak": float(np.max(np.abs(raw))) if len(raw) else 0.0}

        trim = s.input_volume / 100.0
        x = self._lin_ramp(raw, self._trim, trim)
        self._trim = trim
        info["in_peak"] = float(np.max(np.abs(x)))
        info["in_rms"] = float(math.sqrt(np.mean(x * x)))

        if s.bypass:
            y = np.clip(x, -1.0, 1.0)
            info.update(gate_open=True, comp_gr=0.0, agc_gain=0.0, lim_gr=0.0,
                        pre_lim_peak=info["in_peak"])
        else:
            y, zi = sosfilt(self.hpf, x, zi=self.hpf_zi)
            self.hpf_zi = zi
            if s.ns_on:
                y = self.ns.process(y, s.ns_strength)
            else:
                # NS kapalıyken gecikmeyi sabit tut (açıp kapatınca atlama olmasın)
                y = self._passthrough_delay(y)
            y, flags = self.gate.process(y, s)
            y = self.eq.process(y, s)

            mic = db_to_lin(s.mic_gain_db)
            y = self._lin_ramp(y, self._mic, mic)
            self._mic = mic

            if s.agc_on:
                y = self.agc.process(y, flags, s)
            info["agc_gain"] = self.agc.gain_db if s.agc_on else 0.0

            if s.comp_on:
                y, gr = self.comp.process(y, s)
            else:
                gr = 0.0
            info["comp_gr"] = gr

            out = db_to_lin(s.output_gain_db)
            y = self._lin_ramp(y, self._out, out)
            self._out = out
            info["pre_lim_peak"] = float(np.max(np.abs(y)))
            info["gate_open"] = bool(flags[-1]) if flags else False

            if s.limiter_on:
                y, g = self.lim.process(y, s)
                info["lim_gr"] = lin_to_db(g)
            else:
                y = self.lim_delay_only(y)
                info["lim_gr"] = 0.0
            y = np.clip(y, -1.0, 1.0)

        info["out_peak"] = float(np.max(np.abs(y)))
        info["out_rms"] = float(math.sqrt(np.mean(y * y)))
        return y.astype(np.float32), info

    # -- gecikme eşitleme yardımcıları -------------------------------------
    def _passthrough_delay(self, y):
        buf = getattr(self, "_nsd", None)
        d = self.ns.latency
        if buf is None:
            buf = np.zeros(d)
        ext = np.concatenate((buf, y))
        self._nsd = ext[len(y):]
        return ext[:len(y)]

    def lim_delay_only(self, y):
        buf = getattr(self, "_limd", None)
        d = self.lim.latency
        if buf is None:
            buf = np.zeros(d)
        ext = np.concatenate((buf, y))
        self._limd = ext[len(y):]
        return ext[:len(y)]
