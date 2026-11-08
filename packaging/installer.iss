; Inno Setup 6 betiği.  build.bat çalıştırınca (Inno Setup kuruluysa) otomatik derlenir.
; NOT: VB-CABLE sürücüsü bu pakete DAHİL DEĞİLDİR (VB-Audio lisansı); ayrıca kurulmalıdır.
#define AppName "MicBoost"
#define AppVersion "1.0.0"

[Setup]
AppId={{6F2B8C1E-4B7A-4E0D-9C55-3A1F0B7D2E91}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=MicBoost-Setup-{#AppVersion}
SetupIconFile=micboost.ico
UninstallDisplayIcon={app}\MicBoost.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked
Name: "autostart"; Description: "Windows ile birlikte arka planda başlat"; Flags: unchecked

[Files]
Source: "..\dist\MicBoost\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\KULLANIM_KILAVUZU.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\MicBoost"; Filename: "{app}\MicBoost.exe"
Name: "{group}\Kullanım kılavuzu"; Filename: "{app}\docs\KULLANIM_KILAVUZU.md"
Name: "{group}\MicBoost'u kaldır"; Filename: "{uninstallexe}"; Languages: turkish
Name: "{group}\Uninstall MicBoost"; Filename: "{uninstallexe}"; Languages: english
Name: "{autodesktop}\MicBoost"; Filename: "{app}\MicBoost.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "MicBoost"; ValueData: """{app}\MicBoost.exe"" --minimized"; Tasks: autostart; \
  Flags: uninsdeletevalue

[Run]
Filename: "https://vb-audio.com/Cable/"; Description: "Sanal mikrofon için gereken VB-CABLE sayfasını aç (ayrıca kurulmalı)"; \
  Flags: shellexec postinstall skipifsilent unchecked
Filename: "{app}\MicBoost.exe"; Description: "MicBoost'u başlat"; Flags: nowait postinstall skipifsilent
