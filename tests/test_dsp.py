"""DSP doğrulama testleri. Çalıştır:  python -m pytest -q   (veya python tests/test_dsp.py)"""
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from micboost.dsp import BLOCK, MicProcessor, Settings, db_to_lin, lin_to_db  # noqa: E402

SR = 48000
rng = np.random.default_rng(1)


def run(x, s, block=BLOCK, sr=SR):
    p = MicProcessor(sr)
    outs, infos = [], []
    for i in range(0, len(x) - block + 1, block):
        y, info = p.process(x[i:i + block], s)
        outs.append(y)
        infos.append(info)
    return np.concatenate(outs), infos, p


def rms_db(x):
    return lin_to_db(float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))))


def sine(db, f=440.0, dur=2.0):
    t = np.arange(int(SR * dur)) / SR
    return (db_to_lin(db) * np.sqrt(2) * np.sin(2 * np.pi * f * t))


def speechlike(dur=6.0, level_db=-35.0, seed=3):
    """Harmonikli, 3 Hz hece zarflı, aralarda duraklamalı konuşma benzeri sinyal."""
    r = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.arange(n) / SR
    f0 = 130 + 20 * np.sin(2 * np.pi * 0.7 * t)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    sig = sum(np.sin(k * ph) / k for k in range(1, 20))
    env = np.clip(np.sin(2 * np.pi * 1.5 * t), 0, None) ** 0.7  # konuşma/duraklama
    x = sig * env
    x *= db_to_lin(level_db) / max(1e-9, np.sqrt(np.mean(x[env > 0.3] ** 2)))
    return x, env


# ---------------------------------------------------------------- testler
def test_gain_accuracy():
    s = Settings(ns_on=False, gate_on=False, comp_on=False, agc_on=False,
                 limiter_on=True, mic_gain_db=20.0, output_gain_db=0.0)
    x = sine(-40.0, dur=2.0)
    y, _, _ = run(x, s)
    seg = y[SR:]
    assert abs(rms_db(seg) - (-20.0)) < 0.2, rms_db(seg)


def test_gain_range_zero_to_30():
    for g in (0.0, 15.0, 30.0):
        s = Settings(ns_on=False, gate_on=False, comp_on=False, mic_gain_db=g,
                     limiter_ceiling_db=-1.0)
        x = sine(-60.0, dur=1.5)
        y, _, _ = run(x, s)
        assert abs(rms_db(y[SR:]) - (-60.0 + g)) < 0.2


def test_equalizer_flat_setting_is_transparent():
    x = sine(-30.0, f=1000.0, dur=2.0)
    s = Settings(ns_on=False, gate_on=False, agc_on=False, comp_on=False,
                 mic_gain_db=0.0, eq_on=True)
    y, _, _ = run(x, s)
    assert abs(rms_db(y[SR:]) - rms_db(x[SR:])) < 0.1


def test_equalizer_boosts_selected_band():
    x = sine(-30.0, f=1000.0, dur=2.0)
    common = {"ns_on": False, "gate_on": False, "agc_on": False, "comp_on": False,
              "mic_gain_db": 0.0, "limiter_on": False}
    flat, _, _ = run(x, Settings(**common))
    boosted, _, _ = run(x, Settings(**common, eq_on=True, eq_1k_db=6.0))
    change_db = rms_db(boosted[SR:]) - rms_db(flat[SR:])
    assert 5.0 < change_db < 7.0, change_db


def test_equalizer_can_change_gain_without_nan():
    s = Settings(ns_on=False, gate_on=False, comp_on=False, eq_on=True,
                 eq_1k_db=6.0, limiter_on=False, mic_gain_db=0.0)
    processor = MicProcessor(SR)
    x = sine(-30.0, f=1000.0, dur=2.0)
    outputs = []
    for i in range(0, len(x), BLOCK):
        if i >= SR:
            s.eq_1k_db = -6.0
        y, _ = processor.process(x[i:i + BLOCK], s)
        outputs.append(y)
    output = np.concatenate(outputs)
    assert np.all(np.isfinite(output))
    assert rms_db(output[SR + BLOCK:]) < rms_db(output[SR // 2:SR - BLOCK])


def test_equalizer_clamps_band_gain():
    s = Settings(eq_100_db=30.0, eq_10k_db=-30.0).clamp()
    assert s.eq_100_db == 12.0 and s.eq_10k_db == -12.0


def test_input_volume_scales():
    s = Settings(ns_on=False, gate_on=False, comp_on=False, mic_gain_db=0.0,
                 input_volume=50.0)
    y, _, _ = run(sine(-30.0), s)
    assert abs(rms_db(y[SR:]) - (-36.02)) < 0.2


def test_limiter_never_exceeds_ceiling():
    s = Settings(ns_on=False, gate_on=False, comp_on=False, mic_gain_db=30.0,
                 limiter_ceiling_db=-1.0)
    x = np.concatenate([sine(-10, 300, 1.0), rng.normal(0, 0.5, SR),
                        np.where(np.arange(SR) % 4000 < 5, 1.0, 0.0)])
    y, _, _ = run(x, s)
    ceil = db_to_lin(-1.0)
    assert np.max(np.abs(y)) <= ceil + 1e-6, np.max(np.abs(y))
    assert np.max(np.abs(y)) > 0.5  # gerçekten çalışıyor, sadece susturmuyor


def test_limiter_transparent_below_ceiling():
    s = Settings(ns_on=False, gate_on=False, comp_on=False, mic_gain_db=0.0)
    x = sine(-20.0)
    y, _, _ = run(x, s)
    assert abs(rms_db(y[SR:]) - rms_db(x[SR:])) < 0.05


def test_compressor_reduces_dynamic_range():
    # yüksek ve alçak bölüm: kompresör farkı daraltmalı
    s_off = Settings(ns_on=False, gate_on=False, comp_on=False, mic_gain_db=0.0)
    s_on = Settings(ns_on=False, gate_on=False, comp_on=True, mic_gain_db=0.0,
                    comp_threshold_db=-30.0, comp_ratio=4.0)
    x = np.concatenate([sine(-12, dur=1.5), sine(-42, dur=1.5)])
    y0, _, _ = run(x, s_off)
    y1, _, _ = run(x, s_on)
    d0 = rms_db(y0[SR // 2:int(1.4 * SR)]) - rms_db(y0[int(2.0 * SR):int(2.9 * SR)])
    d1 = rms_db(y1[SR // 2:int(1.4 * SR)]) - rms_db(y1[int(2.0 * SR):int(2.9 * SR)])
    assert d0 > 29 and d1 < d0 - 10, (d0, d1)


def test_compressor_makeup_raises_quiet():
    s = Settings(ns_on=False, gate_on=False, comp_on=True, mic_gain_db=0.0,
                 comp_threshold_db=-30.0, comp_ratio=4.0, comp_makeup_db=9.0)
    y, _, _ = run(sine(-50, dur=2.0), s)
    assert abs(rms_db(y[SR:]) - (-41.0)) < 0.5


def test_gate_closes_on_noise_opens_on_speech():
    noise = rng.normal(0, db_to_lin(-62), SR * 2)
    speech, _ = speechlike(2.0, level_db=-30)
    x = np.concatenate([noise, speech + rng.normal(0, db_to_lin(-62), len(speech))])
    s = Settings(ns_on=False, gate_on=True, comp_on=False, mic_gain_db=0.0,
                 gate_threshold_db=-50.0, gate_range_db=40.0)
    y, infos, _ = run(x, s)
    quiet = rms_db(y[SR:2 * SR])
    assert quiet < rms_db(noise) - 25, (quiet, rms_db(noise))
    loud = y[2 * SR:]
    assert rms_db(loud) > rms_db(speech) - 3.0
    assert not infos[SR // BLOCK]["gate_open"]


def test_noise_suppression_snr_improves():
    speech, env = speechlike(8.0, level_db=-32)
    noise = rng.normal(0, db_to_lin(-52), len(speech))
    x = speech + noise
    s = Settings(ns_on=True, ns_strength=0.6, gate_on=False, comp_on=False,
                 mic_gain_db=0.0)
    y, _, p = run(x, s)
    lat = p.ns.latency
    ref_noise = noise[SR:]                     # ilk saniye: öğrenme
    pause = (env[:len(y)] < 0.02)
    pause[:SR] = False
    pause[-lat:] = False
    y_al = y[lat:]
    pause_al = pause[:len(y_al)]
    noise_in = rms_db(x[:len(y_al)][pause_al])
    noise_out = rms_db(y_al[pause_al])
    assert noise_in - noise_out > 10.0, (noise_in, noise_out)
    talk = (env[:len(y_al)] > 0.6)
    talk[:SR] = False
    loss = rms_db(x[:len(y_al)][talk]) - rms_db(y_al[talk])
    assert loss < 2.5, loss                    # konuşma fazla zayıflamamalı
    assert p.ns.underruns == 0


def test_noise_suppression_adapts_to_rising_broadband_noise():
    quiet = rng.normal(0.0, db_to_lin(-58.0), SR * 4)
    louder = rng.normal(0.0, db_to_lin(-42.0), SR * 5)
    x = np.concatenate((quiet, louder))
    s = Settings(ns_on=True, ns_strength=0.6, gate_on=False, comp_on=False,
                 agc_on=False, mic_gain_db=0.0, limiter_on=False)
    y, _, _ = run(x, s)
    start = SR * 8
    attenuation = rms_db(x[start:]) - rms_db(y[start:])
    assert attenuation > 8.0, attenuation


def test_agc_converges_to_target():
    speech, _ = speechlike(12.0, level_db=-38)
    s = Settings(ns_on=False, gate_on=True, gate_threshold_db=-55, comp_on=False,
                 agc_on=True, agc_target_db=-20.0, agc_max_gain_db=25.0,
                 mic_gain_db=0.0)
    y, _, _ = run(speech, s)
    seg = slice(8 * SR, 12 * SR)
    env = np.abs(y[seg]) > 0.01
    lvl = rms_db(y[seg][env])
    assert abs(lvl - (-20.0)) < 4.0, lvl


def test_bypass_is_passthrough_with_trim():
    s = Settings(bypass=True, input_volume=100.0)
    x = sine(-20.0)
    y, _, _ = run(x, s)
    assert np.allclose(y, np.clip(x, -1, 1), atol=1e-6)


def test_block_size_independence_ns_off():
    x, _ = speechlike(3.0, level_db=-30)
    s = Settings(ns_on=False, gate_on=True, comp_on=True, mic_gain_db=10.0)
    y1, _, _ = run(x, s, block=256)
    y2, _, _ = run(x, s, block=512)
    n = min(len(y1), len(y2))
    assert np.max(np.abs(y1[:n] - y2[:n])) < 0.02


def test_latency_reported():
    p = MicProcessor(SR)
    assert 5.0 < p.latency_ms < 10.0, p.latency_ms


def test_cpu_load():
    x, _ = speechlike(5.0, level_db=-30)
    s = Settings(ns_on=True, gate_on=True, comp_on=True, agc_on=True, eq_on=True,
                 eq_100_db=3.0, eq_300_db=-2.0, eq_1k_db=2.0,
                 eq_3k_db=3.0, eq_10k_db=1.0,
                 limiter_on=True, mic_gain_db=15.0)
    p = MicProcessor(SR)
    t0 = time.perf_counter()
    for i in range(0, len(x) - BLOCK, BLOCK):
        p.process(x[i:i + BLOCK], s)
    dt = time.perf_counter() - t0
    load = dt / (len(x) / SR)
    print(f"\nCPU yükü (tek çekirdek, tüm zincir): %{load * 100:.1f}")
    assert load < 0.25


def test_no_nan_on_silence_and_extremes():
    s = Settings(mic_gain_db=30.0, agc_on=True)
    for x in (np.zeros(SR), np.ones(SR) * 5.0, rng.normal(0, 1, SR)):
        y, _, _ = run(x, s)
        assert np.all(np.isfinite(y)) and np.max(np.abs(y)) <= 1.0


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, "->", repr(e))
    sys.exit(1 if fails else 0)
