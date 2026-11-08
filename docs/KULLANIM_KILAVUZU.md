# MicBoost — Kullanım Kılavuzu

MicBoost, mikrofonunuzun sesini **yazılımla yükseltir, temizler ve sanal bir mikrofon
üzerinden** Discord, oyunlar, Zoom, Skype, WhatsApp gibi uygulamalara iletir.

> **Önce dürüst özet** — neyin gerçek, neyin sınırlı olduğu en altta "Bilinen sınırlar"
> bölümünde. En önemlisi: sanal mikrofon için **kendi sürücümü yazmadım**; Microsoft imzalı,
> hazır bir sanal ses kablosu olan **VB-CABLE** ile çalışır ve ayrıca kurulması gerekir.

---

## 1. Nasıl çalışır

```
 Fiziksel mikrofon
        │  (WASAPI, 48 kHz, mono)
        ▼
 ┌─────────────────────── MicBoost ───────────────────────┐
 │ Input Volume → 80 Hz HPF → Gürültü Bastırma → Noise Gate │
 │ → Mic Gain (0…+30 dB) → AGC → Compressor → Output Gain   │
 │ → Limiter (tepe garantili)                              │
 └──────────────────────────┬──────────────────────────────┘
                            ▼
              "CABLE Input"  (sanal kablonun oynatma ucu)
                            │  ← Windows içinde dijital olarak bağlı
                            ▼
              "CABLE Output" (sanal kablonun KAYIT ucu = sanal mikrofon)
                            ▼
              Discord / Valorant / CS2 / Zoom / Skype / WhatsApp
```

Discord ve oyunlarda mikrofon olarak **CABLE Output** seçersiniz. MicBoost'un yazdığı işlenmiş
ses, onlara normal bir mikrofon gibi görünür.

## 2. Kurulum

### 2.1 Sanal ses sürücüsü: VB-CABLE (zorunlu)

1. <https://vb-audio.com/Cable/> adresinden **VB-CABLE Driver Pack**'i indirin.
2. Zip'i çıkarın, `VBCABLE_Setup_x64.exe` dosyasına sağ tık → **Yönetici olarak çalıştır** →
   *Install Driver*.
3. **Bilgisayarı yeniden başlatın.**
4. Windows **Ayarlar → Sistem → Ses → Daha fazla ses ayarı** (veya `Win+R`, `mmsys.cpl`):
   - **Oynatma** sekmesinde *CABLE Input*, **Kayıt** sekmesinde *CABLE Output* görünmelidir.
   - Her ikisine çift tıklayın → **Gelişmiş** → biçimi **24 bit, 48000 Hz** yapın
     (MicBoost 48 kHz çalışır; eşleşme cızırtıyı önler).
   - *CABLE Output*'ta **Dinle** sekmesindeki "Bu aygıtı dinle" kutusunu **işaretlemeyin**.

> **Lisans uyarısı:** VB-CABLE bağış tabanlı (donationware) bir üründür ve kendi lisans
> koşulları vardır. Sürücüyü MicBoost kurulum paketine **dahil etmedim**; kendiniz indirip
> lisansını okuyun (ticari kullanım için ek koşullar olabilir).

### 2.2 MicBoost'u kurma — iki yol

**A) Kurulum dosyası / EXE ile:** `build.bat` çalıştırdığınızda güncel EXE
`dist\MicBoost.exe` konumuna ve bağımlılıklarıyla birlikte `dist\MicBoost\MicBoost.exe`
konumuna üretilir. (EXE'yi tek başına taşımayın; yanındaki `_internal` klasörü gerekir.)
Inno Setup 6 kuruluysa `dist\MicBoost-Setup-1.0.0.exe` de üretilir. Kurulum sihirbazını
çalıştırın. (Bu dosyalar bu pakette hazır gelmez; Windows'ta `build.bat` ile derlenir.)

**B) Python ile (en hızlı deneme):**
1. 64-bit **Python 3.10 – 3.13** kurun (python.org; "Add to PATH" işaretli).
2. Proje klasöründe `run.bat` dosyasına çift tıklayın. İlk çalışmada sanal ortamı kurar ve
   bağımlılıkları (`requirements.txt`) yükler, sonra uygulamayı açar.

### 2.3 EXE / kurulum dosyasını kendiniz derleme

```
build.bat
```
Adımlar: sanal ortam → `requirements-dev.txt` → testler → PyInstaller
(`packaging\micboost.spec`) → kök `dist\MicBoost.exe` ve `_internal` dosyalarını güncelleme
→ Inno Setup (`packaging\installer.iss`, kuruluysa). Her başarılı derlemede iki EXE konumu
aynı güncel programı içerir.
Kod imzalama yapılmadığı için Windows SmartScreen "bilinmeyen yayıncı" uyarısı verebilir.

## 3. İlk kullanım (5 adım)

1. MicBoost'u açın. Sağ üstteki rozet **"Durdu — sanal kablo bulundu"** demeli.
2. **Mikrofon** listesinden fiziksel mikrofonunuzu seçin. **Çıkış**'ta
   *CABLE Input* otomatik seçilir.
3. **BAŞLAT**'a basın. Rozet **"Sanal mikrofon bağlı"** olur, ölçerler hareket eder.
4. Discord/oyun/Zoom ayarlarında **giriş (mikrofon) aygıtını "CABLE Output"** yapın
   (aşağıdaki tabloya bakın).
5. Gain'i ayarlayın; Discord'un mikrofon testinde ("Let's Check") ve karşı tarafa duyurarak deneyin.

| Uygulama | Nerede seçilir |
|---|---|
| Discord | Kullanıcı Ayarları → Ses ve Video → **Giriş Aygıtı: CABLE Output**. *Otomatik giriş duyarlılığını* kapatıp eşiği elle ayarlayın; Discord'un kendi **Gürültü Bastırma / Otomatik Kazanç**'ını kapatın (çift işleme sesi bozar). |
| Valorant | Ayarlar → Ses → Sesli Sohbet → **Giriş Aygıtı: CABLE Output** |
| CS2 | Oyun, mikrofon için Windows'un **varsayılan kayıt aygıtını** kullanır: `mmsys.cpl` → Kayıt → *CABLE Output* → **Varsayılan olarak ayarla** |
| Zoom / Skype / Teams | Ses ayarları → Mikrofon: **CABLE Output** |
| WhatsApp (masaüstü) | Windows varsayılan kayıt aygıtını kullanır → yukarıdaki CS2 yöntemi |

> Bazı oyunların anti-hile yazılımları sanal ses sürücülerine kısıt getirebilir. VB-CABLE
> yaygın kullanılır, ancak **bunu Valorant/CS2 ile bu ortamda test edemedim**; sorun yaşarsanız
> oyunun destek sayfasına bakın.

## 4. Kontroller

| Kontrol | Ne yapar | Başlangıç önerisi |
|---|---|---|
| **Gain (büyük kaydırıcı)** | Gürültü bastırma ve gate'ten **sonra**, 0 … +30 dB sabit yükseltme | +12 dB |
| Input Volume | DSP'den önce yazılımsal giriş ölçeği (0–200 %). **Windows'taki fiziksel mikrofon seviyesini değiştirmez** (onu "Windows kayıt aygıtları" düğmesiyle ayarlayın) | 100 % |
| Output Gain | Sanal mikrofona giden son seviye (−20…+12 dB) | 0 dB |
| Ekolayzer | 100 Hz, 300 Hz, 1 kHz, 3 kHz ve 10 kHz bantlarında ±12 dB ayar. **Düz ayara sıfırla** tüm bantları nötrler. Düşük frekansları fazla artırmak uğultu/patlama seslerini de büyütebilir. | Kapalı / düz |
| Gürültü bastırma | Sabit gürültüyü (fan, hışırtı) azaltır | Güç %50 |
| Noise gate | Eşik altındaki sesi (siz susarken) kısar. Eşiği, susarken ölçer altında, konuşurken üstünde kalacak şekilde ayarlayın | −50 dB |
| AGC | Konuşma seviyesini hedefe doğru otomatik dengeler (yalnızca konuşma varken) | Kapalı; sesiniz bazen çok kısık/yüksekse açın |
| Compressor | Yüksek sesleri sıkıştırır; Makeup ile genel seviyeyi yükselterek kısık kısımları duyulur yapar | Eşik −24 dB, oran 3:1 |
| Limiter | Tepe değerleri tavanın üstüne **çıkarmaz** (clipping'i önler) | Tavan −1 dBFS |
| A/B anahtarı | İşlemeyi kapatır, yalnızca ham (Input Volume'lü) sesi gönderir | Karşılaştırma için |

**Ölçerler:** üst çubuk = mikrofondan gelen ham ses (öncesi), alt çubuk = sanal mikrofona giden
(sonrası). Dolgu RMS, beyaz çizgi tepe tutmadır; sağdaki LED kırpmayı gösterir.

**Mikrofon testi:** BAŞLAT'tan sonra *5 sn kaydet*'e basıp konuşun; *Orijinal* ve *İşlenmiş*
düğmeleriyle kulaklığınızdan karşılaştırın (dinleme hoparlörden olursa geri besleme yapabilir).

**Gecikme seçeneği:** Yeni kurulumlarda *Düşük gecikme* varsayılan olarak seçilir (tahmini ≈ 35 ms; Dengeli ≈ 48 ms, Kesintisiz ≈ 70 ms). Cızırtı ya da kesinti olursa *Dengeli* veya *Kesintisiz* moduna geçin.

**Ses profilleri ve sıfırlama:** Başlıktaki **Ayarlar** penceresinde beş slottan birini seçip
profil adını değiştirebilir, **Adı kaydet** ile yeniden adlandırabilir ve **Profili kaydet**
ile mevcut DSP ayarlarını o slota kaydedebilirsiniz. Bir profili seçip **Profili uygula**
ayarları hemen yükler; **Profili sil** slotu ve adını kaldırır. **Tüm ayarları varsayılana
döndür** yalnızca ses/DSP, aygıt ve gecikme ayarlarını sıfırlar; dil, tema, diğer uygulama
tercihleri ve kayıtlı profiller korunur. Sıfırlama sırasında ses motoru durdurulur.

### Uyarılar
- **GİRİŞ KIRPILIYOR:** mikrofonun kendisi tam ölçeğe vuruyor. Yazılım bunu düzeltemez;
  Windows'ta mikrofon seviyesini/"Mikrofon Güçlendirme"yi düşürün veya mikrofondan uzaklaşın.
- **Limiter devrede:** kazanç çok yüksek; ses bozulmaya başlar, Gain'i düşürün.

## 5. Mikrofon çıkarılıp takılırsa
MicBoost akışın durduğunu (≈ 2 sn içinde) algılar, rozeti "yeniden bağlanıyor" yapar ve
aygıt geri geldiğinde kendiliğinden devam eder. Windows ile açılışta cihazlar geç hazır olsa
bile aynı mekanizma bekler. (Bu davranış sahte bir ses sistemiyle test edildi; gerçek USB
çıkarıp-takma davranışı sürücüye göre değişebilir.)

## 6. Arka planda çalışma
Başlığın sağındaki **Ayarlar** düğmesinden pencere kapatıldığında ne olacağını seçebilirsiniz:

- **Tepsiye küçült, arka planda çalışsın:** Pencere gizlenir; ses motoru çalışmaya devam eder.
- **Tamamen çık, ses motorunu durdur:** Uygulama ve ses motoru kapatılır, arka planda çalışmaz.

Sistem tepsisi kullanılamıyorsa pencere kapatıldığında uygulama tamamen çıkar. Tepsi menüsündeki
**Çıkış** komutu her durumda uygulamayı tamamen kapatır. Dil seçimi Ayarlar'dan yapılır ve
uygulama yeniden başlatıldığında uygulanır. Kurulumda "Windows ile başlat" seçilirse `--minimized`
ile pencere açmadan başlar ve motoru kendisi çalıştırır.

Ayarlar: `%APPDATA%\MicBoost\config.json` · Günlük: `%APPDATA%\MicBoost\micboost.log`

## 7. Sorun giderme

| Belirti | Çözüm |
|---|---|
| Rozet "Sanal kablo bulunamadı" | VB-CABLE'ı kurup **yeniden başlatın**; sonra **⟳ Aygıtları yenile** |
| Karşı taraf hiçbir şey duymuyor | Uygulamada giriş aygıtı **CABLE Output** mu? MicBoost **BAŞLAT** durumda mı? Rozet yeşil mi? |
| Çok kısık | Gain'i artırın, Compressor Makeup ekleyin, AGC açın. Windows mikrofon seviyesini de yükseltin |
| Cızırtı / kesinti | Gecikme kutusunu "Kesintisiz"e alın; CABLE Input/Output biçimlerini 48 kHz yapın; ağır programları kapatın |
| Yankı / kendi sesimi duyuyorum | CABLE Output'ta "Bu aygıtı dinle"yi kapatın; Discord'da başka bir uygulamanın sesini geri çevirmeyin |
| Arka plan gürültüsü de yükseldi | Gürültü bastırma gücünü artırın, Noise gate eşiğini ayarlayın; fiziksel olarak mikrofonu yaklaştırıp Gain'i düşürmek en iyisidir |
| Ses "sulu / robotik" | Gürültü bastırma gücünü düşürün |
| Discord'da çift işleme gibi | Discord'da Krisp/Gürültü Bastırma ve Otomatik Kazancı kapatın |

## 8. Kendi sanal mikrofon sürücü (ör. "MicBoost Virtual Microphone") — neden yapılmadı, ne gerekir

İstenen aygıt adı **"MicBoost Virtual Microphone"** idi. Bu adı taşıyan *gerçek* bir giriş
aygıtı, kernel modunda bir **sanal ses sürücüsü** demektir. Bunu bu çalışmada üretmedim
ve üretmiş gibi davranmıyorum. Gerekli olanlar:

- **Kod:** Microsoft'un *Windows-driver-samples → audio → SysVAD* örneği (WDM/PortCls sanal ses
  miniport) temel alınır; kayıt (capture) uç noktası, MicBoost'tan paylaşımlı bellek/IOCTL ile ses
  alacak şekilde değiştirilir. Yazım dili C/C++, **WDK + Visual Studio** gerekir.
- **İmzalama (zorunlu):** 64-bit Windows 10/11'de kernel sürücüleri imzasız yüklenmez.
  Yaygın dağıtım için **Microsoft Hardware Dev Center** hesabı, **EV kod imzalama sertifikası**
  ve sürücü paketinin Microsoft'a **attestation (veya WHQL) imzalatılması** gerekir.
  Yalnızca geliştirme/test için *test imzalama modu* (`bcdedit /set testsigning on`,
  Secure Boot kapalı) kullanılır; bu mod masaüstünde "Test Modu" filigranı çıkarır ve günlük
  kullanıcıya önerilmez.
- **Güvenlik/uyumluluk:** Sürücü hataları mavi ekrana (BSOD) yol açar; **HVCI / Bellek
  Bütünlüğü** ile uyumlu olmalı, Driver Verifier ile sınanmalıdır.
- **Kolaylaştırıcı seçenek:** VB-CABLE kullanıp Windows **Ses → Kayıt → CABLE Output →
  Özellikler → Genel** bölümünden aygıtı "MicBoost Virtual Microphone" diye **yeniden
  adlandırabilirsiniz**. Bu yalnızca görünen addır (sürücü yine VB-CABLE'dır) ve bazı
  uygulamalar eski adı önbelleğe alabilir. Bu adımı burada denemedim.

Bu yüzden mimari: *imzalı hazır sürücü (VB-CABLE) + kendi DSP/aktarım yazılımı*. İleride kendi
sürücünüz hazır olursa, `micboost/devices.py` içindeki `CABLE_*_HINTS` listesine yeni aygıt
adını eklemek yeterlidir; DSP/motor değişmez.

## 9. Bilinen sınırlar (hiçbirini gizlemiyorum)

1. **Sanal mikrofon = VB-CABLE.** Aygıt adı varsayılan olarak "CABLE Output"tur; "MicBoost
   Virtual Microphone" adlı ayrı bir sürücü **yok** (bkz. bölüm 8).
2. **Gerçek ses donanımıyla test edilmedi.** Bu çalışma ortamında Windows, PortAudio ve ses
   kartı yoktu. DSP zinciri sentetik sinyallerle (kazanç doğruluğu, limiter tavanı,
   compressor, gate, AGC, gürültü bastırma, CPU yükü) ölçülerek; motor mantığı (yeniden
   bloklama, tampon, seviye ölçümü, aygıt çıkarma/takma) **sahte `sounddevice`** ile test
   edildi. WASAPI davranışı (örnekleme hızı dönüşümü, gerçek gecikme, sürücü tuhaflıkları)
   sizin makinenizde doğrulanmalıdır.
3. **Arayüz bu ortamda çalıştırılmadı** (PySide6 kurulu değildi); yalnızca sözdizimi ve ad
   denetimi yapıldı. Küçük görsel/Qt uyumsuzlukları çıkabilir.
4. **EXE ve kurulum dosyası derlenmedi** (Windows gerekir); betikler (`build.bat`,
   `micboost.spec`, `installer.iss`) hazırdır fakat çalıştırılmadı.
5. **Gürültü bastırma spektral çıkarma ile yapılır; RNNoise/Krisp gibi yapay zekâ modeli
   değildir.** Ölçüm: sabit beyaz gürültüde ≈ 11–19 dB azalma, konuşma seviyesi ≈ 0,4 dB
   değişti. **Klavye tıkırtısı gibi ani sesleri tam silmez**; Noise gate yardımcı olur.
6. **Gain gürültüyü de yükseltir.** Düşük seviyeli bir mikrofonda +30 dB, taban gürültüsünü de
   +30 dB yapar. Mikrofonu ağza yaklaştırmak ve Windows tarafındaki seviyeyi artırmak daha temizdir.
7. **Input Volume yazılımsaldır;** donanım/Windows seviyesini değiştirmez.
8. **Kırpılmış (clipping) girişi kurtaramaz.**
9. **Gecikme ölçülmedi, tahmindir** (arayüzde "~xx ms"): DSP ≈ 6,8 ms + tampon + WASAPI
   arabellekleri. Sanal kablo ve Discord kendi gecikmelerini ekler.
10. Stereo mikrofonlar mono'ya karıştırılır. Gelişmiş seçenek olarak WASAPI *exclusive* mod
    yoktur (paylaşımlı mod kullanılır).
11. Bazı oyun/anti-hile yazılımlarının sanal ses aygıtına tepkisi test edilmedi.
