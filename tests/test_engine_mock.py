"""Ses motoru mantığı testi - SAHTE sounddevice ile (gerçek ses donanımı KULLANMAZ).

Doğruladıkları: yeniden bloklama (480'lik callback -> 256'lık DSP), halka tampon,
ön-tamponlama, seviye ölçümü, sanal kablo seçimi, aygıt çıkarılıp takılınca
yeniden bağlanma, test kaydı.  Gerçek PortAudio/WASAPI davranışını test ETMEZ.
"""
import os
import sys
import time
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SR = 48000


class FakeStream:
    def __init__(self, kind, cb, channels, **kw):
        self.kind, self.cb, self.channels = kind, cb, channels
        self.active = False
        self.closed = False

    def start(self):
        self.active = True

    def abort(self):
        self.active = False

    def close(self):
        self.closed = True
        self.active = False


class FakeSD(types.ModuleType):
    def __init__(self):
        super().__init__("sounddevice")
        self.devs = []
        self.streams = []
        self.refreshes = 0
        self.set_devices(mic=True)

    def set_devices(self, mic=True, cable=True):
        d = []
        if mic:
            d.append(dict(name="Test Mic (USB)", hostapi=0, max_input_channels=1,
                          max_output_channels=0, default_samplerate=48000.0))
        d.append(dict(name="Speakers", hostapi=0, max_input_channels=0,
                      max_output_channels=2, default_samplerate=48000.0))
        if cable:
            d.append(dict(name="CABLE Input (VB-Audio Virtual Cable)", hostapi=0,
                          max_input_channels=0, max_output_channels=2,
                          default_samplerate=48000.0))
            d.append(dict(name="CABLE Output (VB-Audio Virtual Cable)", hostapi=0,
                          max_input_channels=2, max_output_channels=0,
                          default_samplerate=48000.0))
        self.devs = d

    def query_devices(self, device=None, kind=None):
        if kind == "input":
            return next(x for x in self.devs if x["max_input_channels"] > 0)
        return self.devs

    def query_hostapis(self):
        return [dict(name="Windows WASAPI", default_input_device=0)]

    class WasapiSettings:
        def __init__(self, exclusive=False, auto_convert=False):
            pass

    def InputStream(self, **kw):
        s = FakeStream("in", kw["callback"], kw["channels"])
        self.streams.append(s)
        return s

    def OutputStream(self, **kw):
        s = FakeStream("out", kw["callback"], kw["channels"])
        self.streams.append(s)
        return s

    def _terminate(self):
        self.refreshes += 1

    def _initialize(self):
        pass


fake = FakeSD()
sys.modules["sounddevice"] = fake

from micboost import devices as dev  # noqa: E402
from micboost.dsp import Settings, db_to_lin, lin_to_db  # noqa: E402
from micboost.engine import AudioEngine, RingBuffer  # noqa: E402


def sine(db, n, start=0, f=440.0):
    t = (np.arange(n) + start) / SR
    return (db_to_lin(db) * np.sqrt(2) * np.sin(2 * np.pi * f * t)).astype(np.float32)


def drive(eng, seconds, in_db=-40.0, cb_frames=480):
    """Gerçek zamansız sürücü: her iterasyonda bir giriş ve bir çıkış callback'i."""
    in_s = next(s for s in fake.streams if s.kind == "in" and s.active)
    out_s = next(s for s in fake.streams if s.kind == "out" and s.active)
    total = int(seconds * SR)
    pos, outs = 0, []
    while pos < total:
        x = sine(in_db, cb_frames, pos)[:, None]
        in_s.cb(x, cb_frames, None, None)
        o = np.zeros((cb_frames, out_s.channels), np.float32)
        out_s.cb(o, cb_frames, None, None)
        outs.append(o)
        pos += cb_frames
    return np.concatenate(outs)


def test_ring_buffer_wraparound_and_overrun():
    r = RingBuffer(1000)
    r.write(np.arange(800, dtype=np.float32))
    d, short = r.read(500)
    assert not short and d[0] == 0 and d[-1] == 499
    r.write(np.arange(800, 1100, dtype=np.float32))      # sarma
    d, short = r.read(600)
    assert not short and d[0] == 500 and d[-1] == 1099
    d, short = r.read(10)
    assert short and np.all(d == 0)
    r.write(np.zeros(2000, np.float32))
    assert r.overruns >= 1 and r.size == 1000


def test_cable_detection():
    devs = dev.all_devices()
    assert dev.find_cable_render(devs).name.startswith("CABLE Input")
    assert dev.find_cable_capture(devs).name.startswith("CABLE Output")
    assert all("CABLE" not in d.name for d in dev.input_devices(devs))
    assert all("CABLE" not in d.name for d in dev.monitor_devices(devs))


def test_end_to_end_gain():
    fake.streams.clear()
    s = Settings(ns_on=False, gate_on=False, comp_on=False, mic_gain_db=20.0)
    eng = AudioEngine(s)
    devs = dev.all_devices()
    ok = eng.start(dev.input_devices(devs)[0].key, dev.find_cable_render(devs).key)
    assert ok and eng.state == "running", eng.message
    out = drive(eng, 2.0)
    assert out.shape[1] == 2
    seg = out[SR:, 0]
    lvl = lin_to_db(float(np.sqrt(np.mean(seg ** 2))))
    assert abs(lvl - (-20.0)) < 0.5, lvl
    assert np.allclose(out[:, 0], out[:, 1])
    m = eng.read_meters()
    assert abs(m["in_rms_db"] - (-40.0)) < 1.0 and m["out_peak_db"] > -20
    assert not m["clip_in"] and m["underruns"] == 0, m
    eng.shutdown()


def test_low_latency_mode_reduces_buffer_without_mock_underruns():
    fake.streams.clear()
    eng = AudioEngine(Settings(ns_on=False, gate_on=False, agc_on=False,
                               comp_on=False, limiter_on=False))
    eng.set_latency_mode("low")
    assert eng._target == 384
    assert eng.est_latency_ms < eng.proc.latency_ms + 1000.0 * 512 / SR + 20.0
    devs = dev.all_devices()
    assert eng.start(dev.input_devices(devs)[0].key, dev.find_cable_render(devs).key)
    drive(eng, 1.0, cb_frames=480)
    assert eng.out_underruns == 0
    eng.shutdown()


def test_input_clip_flag():
    fake.streams.clear()
    eng = AudioEngine(Settings())
    devs = dev.all_devices()
    eng.start(dev.input_devices(devs)[0].key, dev.find_cable_render(devs).key)
    drive(eng, 0.5, in_db=3.0)           # tam ölçek aşımı (clip)
    assert eng.read_meters()["clip_in"]
    eng.shutdown()


def test_unplug_replug_reconnects():
    fake.streams.clear()
    eng = AudioEngine(Settings())
    devs = dev.all_devices()
    key_in = dev.input_devices(devs)[0].key
    eng.start(key_in, dev.find_cable_render(devs).key)
    assert eng.state == "running"
    # mikrofonu çıkar: akışlar ölür
    fake.set_devices(mic=False)
    for s in fake.streams:
        s.active = False
    t0 = time.time()
    while eng.state == "running" and time.time() - t0 < 4:
        time.sleep(0.1)
    assert eng.state == "reconnecting", eng.state
    # mikrofonu tak
    fake.set_devices(mic=True)
    t0 = time.time()
    while eng.state != "running" and time.time() - t0 < 6:
        time.sleep(0.1)
    assert eng.state == "running", (eng.state, eng.message)
    assert eng.reconnects >= 1 and fake.refreshes >= 1
    eng.shutdown()


def test_capture_ab():
    fake.streams.clear()
    s = Settings(ns_on=False, gate_on=False, comp_on=False, mic_gain_db=20.0)
    eng = AudioEngine(s)
    devs = dev.all_devices()
    eng.start(dev.input_devices(devs)[0].key, dev.find_cable_render(devs).key)
    eng.begin_capture(1.0)
    assert eng.capture_result() is None
    drive(eng, 1.5, in_db=-40.0)
    raw, proc = eng.capture_result()
    r = lin_to_db(float(np.sqrt(np.mean(raw ** 2))))
    p = lin_to_db(float(np.sqrt(np.mean(proc[2000:] ** 2))))
    assert abs(r - (-40)) < 0.5 and abs(p - (-20)) < 0.7, (r, p)
    eng.shutdown()


def test_cable_as_input_rejected():
    fake.streams.clear()
    eng = AudioEngine(Settings())
    ok = eng.start("CABLE Output (VB-Audio Virtual Cable)|Windows WASAPI",
                   "CABLE Input (VB-Audio Virtual Cable)|Windows WASAPI")
    assert not ok and eng.state in ("reconnecting", "error")
    eng.shutdown()


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, "->", repr(e))
    sys.exit(1 if fails else 0)
