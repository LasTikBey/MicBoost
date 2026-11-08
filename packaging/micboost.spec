# PyInstaller spec -  build.bat tarafından çağrılır:  pyinstaller packaging\micboost.spec
# onedir + windowed: onefile'a göre daha hızlı açılır ve antivirüs yanlış alarmı daha azdır.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent

datas = collect_data_files("_sounddevice_data", excludes=["**/.github/**"])
datas += [
    (str(root / "assets" / "fonts" / "Montserrat[wght].ttf"), "assets/fonts"),
    (str(root / "assets" / "fonts" / "OFL-Montserrat.txt"), "assets/fonts"),
    (str(root / "packaging" / "micboost.ico"), "packaging"),
]
binaries = collect_dynamic_libs("_sounddevice_data")

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["scipy.signal", "scipy.special._ufuncs_cxx"],
    excludes=["tkinter", "matplotlib", "PIL", "pytest",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtNetwork"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MicBoost",
    console=False,
    icon=str(root / "packaging" / "micboost.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MicBoost", upx=False)
