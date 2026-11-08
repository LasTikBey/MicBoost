# MicBoost

Windows 10/11 için mikrofon ses yükseltici: fiziksel mikrofon → gerçek zamanlı DSP
(gain, compressor, limiter, gürültü bastırma, noise gate, AGC) → **sanal kablo (VB-CABLE)** →
Discord / oyunlar / Zoom'da "mikrofon" olarak kullanılır.

- Kullanım ve kurulum: [`docs/KULLANIM_KILAVUZU.md`](docs/KULLANIM_KILAVUZU.md)
- Hızlı deneme: `run.bat` · EXE + kurulum dosyası: `build.bat` (`dist\MicBoost.exe` ve `dist\MicBoost\`)
- Otomatik EXE derleme: `watch-build.bat` ilk açılışta derler, sonra kaynak dosyalar kaydedildikçe yeniden derler. Durdurmak için `Ctrl+C`; derleme sırasında MicBoost EXE kapalı olmalıdır.
- Geliştirme bağımlılıklarını kaldırma: `uninstall-dev.bat` (yalnızca `.venv` ve `.venv-build` klasörlerini siler)
- Testler: `python tests/test_dsp.py` ve `python tests/test_engine_mock.py`

```
main.py                    başlatıcı
micboost/dsp.py            DSP zinciri (numpy/scipy) — test edildi
micboost/engine.py         mikrofon → DSP → sanal kablo, yeniden bağlanma
micboost/devices.py        aygıt keşfi, VB-CABLE eşleştirme
micboost/ui/               PySide6 koyu tema arayüzü
packaging/                 PyInstaller spec, Inno Setup, ikon
tests/                     DSP testleri + sahte-ses-kartı motor testi
```

**Önemli:** Sanal mikrofon için kendi çekirdek sürücüm yok; imzalı VB-CABLE gerekir.
Gerçek ses donanımı ve arayüz bu geliştirme ortamında denenemedi — ayrıntı:
kılavuzun "Bilinen sınırlar" bölümü.
