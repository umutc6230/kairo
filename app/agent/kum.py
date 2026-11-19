"""Docker'siz Windows kum havuzu: komut bir AppContainer icinde calisir (yonetici gerekmez).

- Hicbir capability verilmez: internet, yerel ag ve loopback KAPALI.
- Yazma izni yalniz proje kokune verilir (icacls, AppContainer SID'ine Modify, devralinir).
  Kullanici profili (Belgeler, .ssh, AppData) AppContainer'a kapali; okunamaz/yazilamaz.
- Alt surec KILL_ON_JOB_CLOSE Job Object'inde: yardimci olunce o da olur.
- Sinir: kullanici klasorune kurulu araclar (or. AppData'daki Python/Node) okunamadigindan
  calismayabilir; Windows ve Program Files altindakiler calisir.

Kullanim (yardimci surec): `Kairo.exe --kum <kok> <cwd> <komut>` -> cikis kodu = komutun kodu.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import sys
from ctypes import wintypes as w
from pathlib import Path

KAP_ADI = "Kairo.Kum"
_ERROR_ALREADY_EXISTS_HR = 0x800700B7
_PTA_SECURITY_CAPABILITIES = 0x00020009
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_CREATE_SUSPENDED = 0x00000004
_STARTF_USESTDHANDLES = 0x00000100
_JOB_KILL_ON_CLOSE = 0x00002000
_JOB_EXTENDED_LIMIT = 9
_INFINITE = 0xFFFFFFFF


class _SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", w.DWORD),
        ("Reserved", w.DWORD),
    ]


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR),
        ("lpTitle", w.LPWSTR), ("dwX", w.DWORD), ("dwY", w.DWORD), ("dwXSize", w.DWORD),
        ("dwYSize", w.DWORD), ("dwXCountChars", w.DWORD), ("dwYCountChars", w.DWORD),
        ("dwFillAttribute", w.DWORD), ("dwFlags", w.DWORD), ("wShowWindow", w.WORD),
        ("cbReserved2", w.WORD), ("lpReserved2", ctypes.c_void_p), ("hStdInput", w.HANDLE),
        ("hStdOutput", w.HANDLE), ("hStdError", w.HANDLE),
    ]  # fmt: skip


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", w.HANDLE), ("hThread", w.HANDLE),
        ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD),
    ]  # fmt: skip


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]


class _BASIC_LIMIT(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
        ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD),
    ]  # fmt: skip


class _EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_LIMIT), ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]  # fmt: skip


def destekli() -> bool:
    return sys.platform == "win32" and sys.getwindowsversion().build >= 9200  # Windows 8+


def _k32() -> ctypes.WinDLL:
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = w.HANDLE
    k.GetStdHandle.restype = w.HANDLE
    k.CreateJobObjectW.restype = w.HANDLE
    k.DuplicateHandle.argtypes = [
        w.HANDLE, w.HANDLE, w.HANDLE, ctypes.POINTER(w.HANDLE), w.DWORD, w.BOOL, w.DWORD,
    ]  # fmt: skip
    return k


def kap_adi(kok: Path) -> str:
    """Her proje kokune AYRI AppContainer: A projesine verilen yazma izni B'nin kabinde gecmez."""
    oz = hashlib.sha256(str(kok.resolve()).lower().encode()).hexdigest()[:24]
    return f"{KAP_ADI}.{oz}"


def kok_dogrula(kok: Path) -> Path:
    """Ev klasoru, onun ustleri, surucu koku ve Windows/Program Files kok olarak reddedilir."""
    k = kok.resolve()
    ev = Path.home().resolve()
    sistem = [Path(os.environ.get(d, "")).resolve() for d in ("WINDIR", "PROGRAMFILES",
              "PROGRAMFILES(X86)", "PROGRAMDATA") if os.environ.get(d)]  # fmt: skip
    if not k.is_dir():
        raise OSError(f"Proje klasoru yok: {k}")
    genis = k == ev or k in ev.parents or k.parent == k
    if genis or any(k == s or s in k.parents for s in sistem):
        raise OSError(f"Kum havuzu bu klasore yazma izni vermez (cok genis): {k}. Proje acin.")
    return k


def kap_sid(ad: str = KAP_ADI) -> str:
    """AppContainer profilini (yoksa) olusturur, SID metnini dondurur."""
    userenv = ctypes.WinDLL("userenv")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    sid = ctypes.c_void_p()
    hr = userenv.CreateAppContainerProfile(
        ad, ad, "Kairo komut kum havuzu", None, 0, ctypes.byref(sid)
    )
    if hr & 0xFFFFFFFF == _ERROR_ALREADY_EXISTS_HR:
        hr = userenv.DeriveAppContainerSidFromAppContainerName(ad, ctypes.byref(sid))
    if hr != 0:
        raise OSError(f"AppContainer olusturulamadi (HRESULT {hr & 0xFFFFFFFF:#x})")
    metin = w.LPWSTR()
    try:
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(metin)):
            raise ctypes.WinError(ctypes.get_last_error())
        return metin.value or ""
    finally:
        ctypes.windll.kernel32.LocalFree(metin)
        advapi.FreeSid(sid)


_DACL = 4  # DACL_SECURITY_INFORMATION
_LISTELE = 0x1000A1  # LIST_DIRECTORY | TRAVERSE | READ_ATTRIBUTES | SYNCHRONIZE


def _sddl(yol: Path) -> str:
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    gerek = w.DWORD()
    advapi.GetFileSecurityW(str(yol), _DACL, None, 0, ctypes.byref(gerek))
    sd = ctypes.create_string_buffer(gerek.value)
    if not advapi.GetFileSecurityW(str(yol), _DACL, sd, gerek, ctypes.byref(gerek)):
        raise ctypes.WinError(ctypes.get_last_error())
    metin = w.LPWSTR()
    if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
        sd, 1, _DACL, ctypes.byref(metin), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return metin.value or ""
    finally:
        ctypes.windll.kernel32.LocalFree(metin)


def _ace_ekle(yol: Path, ace: str) -> None:
    """ACE'yi DACL basina ekler. SetFileSecurityW alt agaca YAYILMAZ (icacls tum agaci dolasir)."""
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    eski = _sddl(yol)
    bas, _, aceler = eski.partition("(")  # "D:PAI" + ilk ACE'den sonrasi
    yeni_sddl = f"{bas}{ace}" + (f"({aceler}" if aceler else "")
    sd = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        yeni_sddl, 1, ctypes.byref(sd), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not advapi.SetFileSecurityW(str(yol), _DACL, sd):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        ctypes.windll.kernel32.LocalFree(sd)


GIT_SERT = {"core.hooksPath": "NUL", "core.fsmonitor": "false"}
SERT_AKTIF = False  # KumAdaptoru olusunca True: ortam_allowlist sertlestirmeyi ekler


def git_sertlestir(ortam: dict) -> None:
    """Kairo'nun KUM DISI git komutlari kum kabinin yazabildigi hook/fsmonitor'u calistirmasin.
    GIT_CONFIG_* komut satiri onceligindedir: repo .git/config'i (ic ice depolar dahil) ezer."""
    n = int(ortam.get("GIT_CONFIG_COUNT", "0") or 0)
    if any(ortam.get(f"GIT_CONFIG_KEY_{i}") == "core.hooksPath" for i in range(n)):
        return  # zaten sertlestirildi
    for i, (a, d) in enumerate(GIT_SERT.items(), start=n):
        ortam[f"GIT_CONFIG_KEY_{i}"], ortam[f"GIT_CONFIG_VALUE_{i}"] = a, d
    ortam["GIT_CONFIG_COUNT"] = str(n + len(GIT_SERT))


def git_kilitle(kok: Path, sid: str) -> None:
    """.git kum kabina SALT OKUNUR: kabin yazdigi hook ya da core.fsmonitor, Kairo'nun kum DISINDA
    calisan git komutlarinda calisip kacis olurdu. Deny ACE paket SID'inde islemedigi (denendi)
    icin .git koktan devralmayi keser, kabin iznini kaldirir ve yalniz okuma verir. .git dosyasi
    (worktree) da kilitlenir: yonlendirilirse git baska klasoru kullanir.
    shortcut: kum icinde YENI olusturulan ya da ic ice .git kilitlenmez; onlara karsi git_sertlestir
    (hook/fsmonitor kapali) korur, filter/diff surucusu gibi diger repo ayarlarina karsi korumaz.
    """
    g = kok / ".git"
    if not os.path.lexists(g):
        return
    if os.lstat(g).st_file_attributes & 0x400 or kok not in g.resolve().parents:
        raise OSError(
            ".git bir baglanti (reparse point) ya da proje disini gosteriyor; kum reddedildi."
        )
    oku = f"(A;{'OICI' if g.is_dir() else ''};0x1200a9;;;{sid})"
    sddl = _sddl(g)
    if sddl.startswith("D:P") and sddl.count(f";{sid})") == 1 and oku in sddl:
        return  # zaten kilitli
    miras = "(OI)(CI)" if g.is_dir() else ""
    for a in (["/inheritance:d"], ["/remove:g", f"*{sid}"], ["/remove:d", f"*{sid}"],
              ["/grant", f"*{sid}:{miras}RX"]):  # fmt: skip
        r = subprocess.run(  # noqa: S603 - sabit arac, kabuk yok
            ["icacls", str(g), *a, "/Q"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if r.returncode != 0:
            raise OSError(f".git kum havuzuna kilitlenemedi: {r.stderr or r.stdout}")


def koke_izin_ver(kok: Path, sid: str) -> None:
    """Proje kokune Modify (alt klasorlere devralinir); izin zaten varsa dokunulmaz."""
    if sid not in _sddl(kok):
        r = subprocess.run(  # noqa: S603 - sabit arac, kabuk yok
            ["icacls", str(kok), "/grant", f"*{sid}:(OI)(CI)M", "/Q"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )  # fmt: skip
        if r.returncode != 0:
            raise OSError(f"Proje klasorune kum havuzu izni verilemedi: {r.stderr or r.stdout}")
    git_kilitle(kok, sid)
    # dir/PowerShell ust klasorleri listeler: yalniz O KLASOR icin (devralinmayan) listele.
    # Bedel: ust klasorlerdeki ADLAR gorunur, icerik degil. Yetki yoksa (or. C:\\) atlanir.
    for ust in kok.parents:
        try:
            if sid not in _sddl(ust):
                _ace_ekle(ust, f"(A;;{_LISTELE:#x};;;{sid})")
        except OSError:
            continue


def _miras(k: ctypes.WinDLL, h: int) -> int:
    """Std tutamacin kalitilabilir kopyasi (AppContainer surecine gecer)."""
    yeni = w.HANDLE()
    cur = k.GetCurrentProcess()
    if not k.DuplicateHandle(cur, h, cur, ctypes.byref(yeni), 0, True, 2):  # SAME_ACCESS
        raise ctypes.WinError(ctypes.get_last_error())
    return yeni.value or 0


def calistir(kok: Path, cwd: Path, komut: str) -> int:
    k = _k32()
    kok = kok_dogrula(kok)
    sid_metin = kap_sid(kap_adi(kok))
    koke_izin_ver(kok, sid_metin)
    sid = ctypes.c_void_p()
    if not ctypes.windll.advapi32.ConvertStringSidToSidW(sid_metin, ctypes.byref(sid)):
        raise ctypes.WinError()
    yetenek = _SECURITY_CAPABILITIES(sid, None, 0, 0)  # capability yok: ag kapali

    boyut = ctypes.c_size_t()
    k.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(boyut))
    liste = ctypes.create_string_buffer(boyut.value)
    if not k.InitializeProcThreadAttributeList(liste, 1, 0, ctypes.byref(boyut)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not k.UpdateProcThreadAttribute(
        liste, 0, ctypes.c_size_t(_PTA_SECURITY_CAPABILITIES), ctypes.byref(yetenek),
        ctypes.c_size_t(ctypes.sizeof(yetenek)), None, None,
    ):  # fmt: skip
        raise ctypes.WinError(ctypes.get_last_error())

    si = _STARTUPINFOEXW()
    si.StartupInfo.cb = ctypes.sizeof(si)
    si.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
    si.StartupInfo.hStdInput = _miras(k, k.GetStdHandle(-10))
    si.StartupInfo.hStdOutput = _miras(k, k.GetStdHandle(-11))
    si.StartupInfo.hStdError = _miras(k, k.GetStdHandle(-12))
    si.lpAttributeList = ctypes.cast(liste, ctypes.c_void_p)

    gecici = kok / ".kairo-kum-tmp"  # AppContainer kullanici TEMP'ine yazamaz
    gecici.mkdir(exist_ok=True)
    ortam = {**os.environ, "TEMP": str(gecici), "TMP": str(gecici)}
    blok = ctypes.create_unicode_buffer("\0".join(f"{a}={d}" for a, d in ortam.items()) + "\0\0")
    satir = ctypes.create_unicode_buffer(f'cmd.exe /d /s /c "{komut}"')
    pi = _PROCESS_INFORMATION()
    if not k.CreateProcessW(
        None, satir, None, None, True,
        _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT | _CREATE_SUSPENDED,
        blok, str(cwd), ctypes.byref(si), ctypes.byref(pi),
    ):  # fmt: skip
        raise ctypes.WinError(ctypes.get_last_error())

    is_ = k.CreateJobObjectW(None, None)
    bilgi = _EXTENDED_LIMIT()
    bilgi.BasicLimitInformation.LimitFlags = _JOB_KILL_ON_CLOSE
    k.SetInformationJobObject(is_, _JOB_EXTENDED_LIMIT, ctypes.byref(bilgi), ctypes.sizeof(bilgi))
    k.AssignProcessToJobObject(is_, pi.hProcess)
    k.ResumeThread(pi.hThread)
    k.WaitForSingleObject(pi.hProcess, _INFINITE)
    kod = w.DWORD()
    k.GetExitCodeProcess(pi.hProcess, ctypes.byref(kod))
    for h in (pi.hThread, pi.hProcess, is_):
        k.CloseHandle(h)
    return kod.value


def argv(kok: Path, cwd: Path, komut: str) -> list[str]:
    """Yardimci surecin argv'si: derlenmiste exe'nin kendisi, gelistirmede python -m."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--kum", str(kok), str(cwd), komut]
    # -P: calisma klasoru (proje) sys.path'e girmez; kod yalniz bu deponun mutlak kokunden
    # yuklenir, projeye konmus sahte "app" paketi yardimciyi (kum disi) ele geciremez.
    depo = str(Path(__file__).resolve().parents[2])
    kod = (
        f"import sys; sys.path.insert(0, {depo!r}); "
        "from app.agent.kum import main; sys.exit(main(sys.argv[1:]))"
    )
    return [sys.executable, "-P", "-c", kod, str(kok), str(cwd), komut]


def kok_kur(proje: str) -> int:
    """Bir kerelik, YONETICI olarak: surucu kokune o projenin kabi icin listele izni."""
    proje_kok = kok_dogrula(Path(proje))
    sid = kap_sid(kap_adi(proje_kok))
    for kok in {Path(proje_kok.anchor)}:
        if sid not in _sddl(kok):
            _ace_ekle(kok, f"(A;;{_LISTELE:#x};;;{sid})")
        print(f"{kok} hazir")
    return 0


def main(a: list[str]) -> int:
    try:
        return calistir(Path(a[0]), Path(a[1]), a[2])
    except OSError as e:
        print(f"Kum havuzu baslatilamadi: {e}", file=sys.stderr)
        return 125


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
