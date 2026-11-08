"""Ses aygıtı keşfi (PortAudio / sounddevice üzerinden).

Windows aynı fiziksel aygıtı MME, DirectSound, WASAPI ve WDM-KS altında ayrı ayrı
listeler. MicBoost varsayılan olarak WASAPI (paylaşımlı mod) aygıtlarını gösterir;
WASAPI yoksa MME'ye düşer.
"""
from __future__ import annotations

from dataclasses import dataclass

# Sanal ses kablosu eşleştirme (VB-Audio Virtual Cable ve türevleri).
# "Cable Input"  = oynatma (render) ucu  -> MicBoost buraya YAZAR
# "Cable Output" = kayıt (capture) ucu   -> Discord/oyun bunu MİKROFON olarak seçer
CABLE_RENDER_HINTS = ("cable input", "hi-fi cable input", "vb-audio virtual cable")
CABLE_CAPTURE_HINTS = ("cable output", "hi-fi cable output")


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    hostapi: str
    max_in: int
    max_out: int
    default_sr: float

    @property
    def key(self) -> str:
        return f"{self.name}|{self.hostapi}"


def _sd():
    import sounddevice as sd  # gecikmeli import: PortAudio yoksa testler yine çalışır
    return sd


def refresh_portaudio() -> None:
    """PortAudio'yu yeniden başlatıp aygıt listesini tazeler.

    DİKKAT: açık akış varken çağrılmamalıdır.
    """
    sd = _sd()
    sd._terminate()
    sd._initialize()


def all_devices() -> list[Device]:
    sd = _sd()
    apis = sd.query_hostapis()
    out = []
    for i, d in enumerate(sd.query_devices()):
        out.append(Device(i, d["name"], apis[d["hostapi"]]["name"],
                          int(d["max_input_channels"]), int(d["max_output_channels"]),
                          float(d["default_samplerate"])))
    return out


def _preferred(devs: list[Device]) -> list[Device]:
    wasapi = [d for d in devs if "wasapi" in d.hostapi.lower()]
    if wasapi:
        return wasapi
    mme = [d for d in devs if "mme" in d.hostapi.lower()]
    return mme or devs


def is_cable_capture(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in CABLE_CAPTURE_HINTS)


def is_cable_render(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in CABLE_RENDER_HINTS)


def input_devices(devs: list[Device] | None = None) -> list[Device]:
    """Fiziksel mikrofon adayları (sanal kablonun kayıt ucu geri besleme olmasın diye hariç)."""
    devs = devs if devs is not None else all_devices()
    return [d for d in _preferred([d for d in devs if d.max_in > 0])
            if not is_cable_capture(d.name)]


def output_devices(devs: list[Device] | None = None) -> list[Device]:
    devs = devs if devs is not None else all_devices()
    return _preferred([d for d in devs if d.max_out > 0])


def monitor_devices(devs: list[Device] | None = None) -> list[Device]:
    """Test kaydını dinlemek için kulaklık/hoparlör adayları (sanal kablo hariç)."""
    return [d for d in output_devices(devs) if not is_cable_render(d.name)]


def find_cable_render(devs: list[Device] | None = None) -> Device | None:
    for d in output_devices(devs):
        if is_cable_render(d.name):
            return d
    return None


def find_cable_capture(devs: list[Device] | None = None) -> Device | None:
    devs = devs if devs is not None else all_devices()
    for d in _preferred([d for d in devs if d.max_in > 0]):
        if is_cable_capture(d.name):
            return d
    return None


def default_input(devs: list[Device] | None = None) -> Device | None:
    sd = _sd()
    devs = devs if devs is not None else all_devices()
    cands = input_devices(devs)
    try:
        di = sd.query_devices(kind="input")
        for d in cands:
            if d.name == di["name"]:
                return d
        # WASAPI varsayılanı hostapi'ye göre farklı index döndürebilir
        apis = sd.query_hostapis()
        for a in apis:
            if "wasapi" in a["name"].lower() and a.get("default_input_device", -1) >= 0:
                idx = a["default_input_device"]
                for d in cands:
                    if d.index == idx:
                        return d
    except Exception:  # noqa: BLE001
        pass
    return cands[0] if cands else None


def find_by_key(key: str, kind: str, devs: list[Device] | None = None) -> Device | None:
    """Kaydedilmiş 'ad|hostapi' anahtarından aygıtı (indeks değişmiş olsa da) bul."""
    if not key:
        return None
    devs = devs if devs is not None else all_devices()
    pool = {"in": input_devices(devs), "out": output_devices(devs),
            "mon": monitor_devices(devs)}[kind]
    for d in pool:
        if d.key == key:
            return d
    name = key.split("|")[0]
    for d in pool:
        if d.name == name:
            return d
    return None
