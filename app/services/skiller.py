"""Skill'ler (Claude Code mantigi): her skill bir klasordeki SKILL.md (YAML frontmatter: name,
description) ya da tek .md dosyasi. Model sistem mesajinda uygun skill'lerin adini ve aciklamasini
gorur; gerekirse `skill_kullan` araciyla tam talimati yukler, `skill_dosyasi_oku` ile
klasordeki ek dosyalari (references/...) okur.
Skill'ler yalniz OKUNUR; icindeki betikler calistirilmaz.

Kaynaklar: ~/.claude/skills (Claude Code), ~/Documents/brain/skills (brain),
<veri>/skills (uygulama), ve YALNIZ guvenilir projede <proje>/.claude/skills (proje).

A6: surum, gereken araclar (allowed-tools/required-tools), icerik hash'i, guven ve bozuk frontmatter
hatasi tutulur. Manifestte arac/izin istemek IZIN VERMEK DEGILDIR: her arac PolitikaMotoru'ndan
gecer.
"""

from __future__ import annotations

import functools
import hashlib
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import yerlesik_skill_dizini
from app.exceptions import Bulunamadi, UygulamaHatasi

MAX_SKILL_KARAKTER = 8000
MAX_LISTE = 6  # sistem mesajinda gosterilen en uygun skill sayisi (kucuk baglam)
AD_DESENI = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
KELIME = re.compile(r"[a-z0-9çğıöşü]{3,}")
DURAK = {
    "bir",
    "ile",
    "icin",
    "için",
    "gibi",
    "olan",
    "olarak",
    "veya",
    "daha",
    "cok",
    "çok",
    "use",
    "when",
    "this",
    "that",
    "with",
    "from",
    "and",
    "the",
}


GUVEN = {
    "claude": "kullanici",
    "brain": "kullanici",
    "uygulama": "kullanici",
    "yerlesik": "kullanici",
    "proje": "proje",
}


@dataclass(frozen=True)
class Skill:
    ad: str
    aciklama: str
    kaynak: str  # claude | brain | uygulama | proje
    dosya: Path  # SKILL.md ya da tek .md
    klasor: Path | None  # ek dosyalarin klasoru (tek dosyalik skill'de None)
    surum: str = ""
    gereken_araclar: tuple[str, ...] = ()
    hash: str = ""  # SKILL.md icerik hash'i (degisiklik/kaynak takibi)
    hata: str = ""  # bozuk frontmatter vb.: skill listelenir ama YUKLENMEZ
    scriptler: tuple[str, ...] = ()  # manifestte ILAN edilen calistirilabilir dosyalar (A6.2)

    def ozet(self) -> dict:
        return {
            "ad": self.ad,
            "aciklama": self.aciklama,
            "kaynak": self.kaynak,
            "yol": str(self.dosya),
            "silinebilir": self.kaynak == "uygulama",
            "duzenlenebilir": self.kaynak == "uygulama",
            "surum": self.surum,
            "gereken_araclar": list(self.gereken_araclar),
            "hash": self.hash,
            "guven": GUVEN.get(self.kaynak, "bilinmiyor"),
            "hata": self.hata,
            "scriptler": list(self.scriptler),
        }


def frontmatter_ayrintili(metin: str) -> tuple[dict, str, str]:
    """(meta, govde, hata). Bozuk YAML sessizce yutulmaz: hata metni doner."""
    if not metin.startswith("---"):
        return {}, metin, ""
    son = metin.find("\n---", 3)
    if son < 0:
        return {}, metin, "Frontmatter kapanmamis: ikinci '---' satiri yok."
    govde = metin[son + 4 :].lstrip("\n")
    try:
        veri = yaml.safe_load(metin[3:son]) or {}
    except yaml.YAMLError as e:
        yer = getattr(e, "problem_mark", None)
        konum = f" (satir {yer.line + 2})" if yer is not None else ""
        return {}, govde, f"Frontmatter YAML hatasi{konum}: {getattr(e, 'problem', e)}"
    if not isinstance(veri, dict):
        return {}, govde, "Frontmatter anahtar: deger biciminde olmali."
    return veri, govde, ""


def frontmatter(metin: str) -> tuple[dict, str]:
    """('---' arasi YAML, govde). YAML bozuksa bos sozluk (geriye uyumlu)."""
    meta, govde, _ = frontmatter_ayrintili(metin)
    return meta, govde


def _araclar(deger: object) -> tuple[str, ...]:
    if isinstance(deger, str):
        parcalar = re.split(r"[,\s]+", deger)
    elif isinstance(deger, list):
        parcalar = [str(x) for x in deger]
    else:
        return ()
    return tuple(sorted({p.strip() for p in parcalar if p.strip()}))[:30]


def _scriptler(deger: object) -> tuple[str, ...]:
    if isinstance(deger, str):
        deger = [deger]
    if not isinstance(deger, list):
        return ()
    yollar = {str(x).strip().replace("\\", "/").lstrip("./") for x in deger if str(x).strip()}
    return tuple(sorted(yollar))[:20]


# ---- A6.2: skill scriptleri ----
# Uzanti -> yorumlayici. Listede olmayan tur (exe, bat, cmd, vbs...) CALISTIRILMAZ.
YORUMLAYICILAR: dict[str, list[str]] = {
    ".py": ["python", "-I"],
    ".ps1": ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"],
    ".sh": ["bash"],
    ".js": ["node"],
    ".mjs": ["node"],
}
# cmd.exe metakarakterleri: arguman komut zincirine donusemesin
YASAK_ARG = re.compile(r'[&|<>^%!`"\r\n\x00]')
MAX_ARG = 20


@dataclass(frozen=True)
class ScriptPlani:
    komut: str
    yol: Path
    sha256: str
    ozet: str


def script_plani(s: Skill, yol: str, argumanlar: list[str] | None = None) -> ScriptPlani:
    """Calistirmadan once dogrular. Calistirma kararini VERMEZ; yalniz neyin calisacagini
    kesinlestirir (izin motoru bu planin hash'iyle karar verir)."""
    if s.hata:
        raise UygulamaHatasi(f"Skill '{s.ad}' bozuk; scripti calistirilmaz: {s.hata}")
    if s.klasor is None:
        raise UygulamaHatasi("Tek dosyalik skill'in scripti olmaz.")
    temiz = yol.strip().replace("\\", "/").lstrip("./")
    if temiz not in s.scriptler:
        ilan = ", ".join(s.scriptler) or "yok"
        raise UygulamaHatasi(
            f"'{yol}' skill manifestinde (scripts:) ilan edilmemis; calistirilmaz. Ilan edilenler: "
            f"{ilan}"
        )
    hedef = (s.klasor / temiz).resolve()
    if not hedef.is_relative_to(s.klasor.resolve()) or not hedef.is_file():
        raise UygulamaHatasi(f"Script skill klasorunde yok: {temiz}")
    on = YORUMLAYICILAR.get(hedef.suffix.lower())
    if on is None:
        raise UygulamaHatasi(
            f"'{hedef.suffix}' turu calistirilmaz; izinli: {', '.join(sorted(YORUMLAYICILAR))}"
        )
    yorumlayici = sys.executable if on[0] == "python" and _python_mu() else shutil.which(on[0])
    if not yorumlayici:
        raise UygulamaHatasi(f"'{on[0]}' bu bilgisayarda bulunamadi; script calistirilamaz.")
    argumanlar = [str(a) for a in (argumanlar or [])]
    if len(argumanlar) > MAX_ARG:
        raise UygulamaHatasi(f"En fazla {MAX_ARG} arguman verilebilir.")
    for a in argumanlar:
        if len(a) > 500 or YASAK_ARG.search(a):
            raise UygulamaHatasi(f"Arguman izinli degil (ozel karakter ya da cok uzun): {a[:60]}")
    ozet_hash = hashlib.sha256(hedef.read_bytes()).hexdigest()
    komut = subprocess.list2cmdline([yorumlayici, *on[1:], str(hedef), *argumanlar])
    return ScriptPlani(
        komut=komut,
        yol=hedef,
        sha256=ozet_hash,
        ozet=f"Skill scripti: {s.ad}/{temiz} {' '.join(argumanlar)} (sha256 {ozet_hash[:12]}, "
        f"kaynak {s.kaynak})".strip(),
    )


def _python_mu() -> bool:
    """Paketli uygulamada sys.executable uygulamanin kendisidir; python degil."""
    return Path(sys.executable).stem.lower().startswith("python")


def _skill_oku(dosya: Path, kaynak: str, klasor: Path | None) -> Skill | None:
    try:
        ham = dosya.read_bytes()
    except OSError:
        return None
    metin = ham.decode("utf-8", errors="replace")
    meta, govde, hata = frontmatter_ayrintili(metin)
    ad = str(meta.get("name") or (klasor.name if klasor else dosya.stem)).strip()
    aciklama = " ".join(str(meta.get("description") or "").split())
    if not aciklama:  # frontmatter yoksa ilk anlamli satir
        aciklama = next((s.strip("# ").strip() for s in govde.splitlines() if s.strip()), "")
    return Skill(
        ad=ad,
        aciklama=aciklama[:600],
        kaynak=kaynak,
        dosya=dosya,
        klasor=klasor,
        surum=str(meta.get("version") or meta.get("surum") or "")[:40],
        gereken_araclar=_araclar(
            meta.get("required-tools") or meta.get("allowed-tools") or meta.get("tools")
        ),
        hash=hashlib.sha256(ham).hexdigest()[:16],
        hata=hata,
        scriptler=_scriptler(meta.get("scripts")) if klasor else (),
    )


def varsayilan_kaynaklar(veri_dizini: Path) -> list[tuple[str, Path]]:
    return [
        ("claude", Path.home() / ".claude" / "skills"),
        ("brain", Path.home() / "Documents" / "brain" / "skills"),
        ("uygulama", veri_dizini / "skills"),
        # Uygulamayla gelen (docx, pdf; app/skills/NOTICE.txt).
        # En sonda: ayni adli kullanici skill'i onde gelir.
        ("yerlesik", yerlesik_skill_dizini()),
    ]


def _imza(kaynaklar: tuple) -> tuple:
    """Skill dosyalarinin ucuz imzasi (yalniz stat; icerik okunmaz)."""
    parcalar: list = []
    for kaynak, kok in kaynaklar:
        parcalar.append((kaynak, str(kok)))
        try:
            ogeler = list(kok.iterdir())
        except OSError:
            continue
        for oge in ogeler:
            f = oge / "SKILL.md" if oge.is_dir() else oge
            try:
                st = f.stat()
            except OSError:
                continue
            parcalar.append((str(f), st.st_mtime_ns, st.st_size))
    return tuple(parcalar)


def _bosaltir(f):
    """Skill yazan metodlar: once ve sonra onbellegi bosaltir (yeni/silinen skill hemen gorunur)."""

    @functools.wraps(f)
    def w(self, *a, **k):
        self._onbellek = None
        try:
            return f(self, *a, **k)
        finally:
            self._onbellek = None

    return w


class SkillDeposu:
    def __init__(self, veri_dizini: Path, kaynaklar: list[tuple[str, Path]] | None = None) -> None:
        self.uygulama_dizini = veri_dizini / "skills"
        self.kaynak_listesi = kaynaklar or varsayilan_kaynaklar(veri_dizini)
        # aktif GUVENILIR projenin skill klasorleri (api baglar); guvenilmeyen repo skill ekleyemez
        self.proje_kaynaklari: Callable[[], list[tuple[str, Path]]] = lambda: []

    def kesfet(self) -> list[Skill]:
        """Onbellekli tarama: her mesajda iki kez taranip ~0.6 sn yiyordu. Dosyalarin imzasi
        (yol, degisme zamani, boyut) ayniysa YAML yeniden okunmaz; disaridan yapilan her
        ekleme/silme/duzenleme imzayi degistirir."""
        kaynaklar = (*self.kaynak_listesi, *self.proje_kaynaklari())
        imza = _imza(kaynaklar)
        onb = getattr(self, "_onbellek", None)
        if onb and onb[0] == imza:
            return list(onb[1])
        sonuc = self._tara(kaynaklar)
        self._onbellek = (imza, sonuc)
        return list(sonuc)

    def onbellegi_bosalt(self) -> None:
        self._onbellek = None

    def _tara(self, kaynaklar: tuple) -> list[Skill]:
        """Tum kaynaklari tarar. Ayni dosya (junction/kisayol) iki kaynakta varsa bir kez alinir;
        ayni ad iki kez varsa ilki (claude > brain > uygulama) kazanir."""
        gorulen_dosya: set[Path] = set()
        gorulen_ad: set[str] = set()
        sonuc: list[Skill] = []
        for kaynak, kok in kaynaklar:
            if not kok.is_dir():
                continue
            for oge in sorted(kok.iterdir(), key=lambda p: p.name.lower()):
                if oge.is_dir() and (oge / "SKILL.md").is_file():
                    s = _skill_oku(oge / "SKILL.md", kaynak, oge)
                elif oge.is_file() and oge.suffix.lower() == ".md":
                    s = _skill_oku(oge, kaynak, None)
                else:
                    continue
                if s is None:
                    continue
                try:
                    gercek = s.dosya.resolve()
                except OSError:
                    gercek = s.dosya
                if gercek in gorulen_dosya or s.ad in gorulen_ad:
                    continue
                gorulen_dosya.add(gercek)
                gorulen_ad.add(s.ad)
                sonuc.append(s)
        return sonuc

    def getir(self, ad: str, kapali: set[str] | None = None) -> Skill:
        for s in self.kesfet():
            if s.ad == ad and ad not in (kapali or set()):
                return s
        raise Bulunamadi(f"Skill bulunamadi: {ad}")

    # ---- uygulama skill'leri (eklenebilir/silinebilir) ----
    @_bosaltir
    def guncelle(self, ad: str, aciklama: str, icerik: str, surum: str = "",
                 gereken_araclar: list[str] | None = None) -> Skill:  # fmt: skip
        """Yalniz uygulama skill'i duzenlenir; Claude/brain/proje kaynaklari salt okunur."""
        s = self.getir(ad)
        if s.kaynak != "uygulama" or s.klasor is None:
            raise UygulamaHatasi("Yalniz uygulamada eklenen skill'ler duzenlenebilir.")
        if not aciklama.strip():
            raise UygulamaHatasi("Aciklama zorunlu: model skill'i buna bakarak secer.")
        self._surum_sakla(s.klasor)
        self._yaz(s.klasor, s.ad, aciklama, icerik, surum, gereken_araclar)
        return self.getir(ad)

    # ---- revizyonlar (openbot'un yerel skill surumlemesinden): her guncellemede eski hal saklanir
    @staticmethod
    def _surum_klasoru(klasor: Path) -> Path:
        return klasor / ".surumler"

    def revizyon(self, ad: str) -> int:
        """Su anki revizyon numarasi (1 = ilk hal). Ajan guncellerken bunu gondermeli."""
        s = self.getir(ad)
        if s.klasor is None:
            return 1
        return len(list(self._surum_klasoru(s.klasor).glob("SKILL.r*.md"))) + 1

    def _surum_sakla(self, klasor: Path) -> None:
        hedef = self._surum_klasoru(klasor)
        hedef.mkdir(exist_ok=True)
        n = len(list(hedef.glob("SKILL.r*.md"))) + 1
        shutil.copy2(klasor / "SKILL.md", hedef / f"SKILL.r{n}.md")

    def revizyonlar(self, ad: str) -> list[dict]:
        s = self.getir(ad)
        if s.klasor is None:
            return []
        eski = sorted(self._surum_klasoru(s.klasor).glob("SKILL.r*.md"),
                      key=lambda p: int(p.stem.split(".r")[-1]))  # fmt: skip
        return [{"revizyon": int(p.stem.split(".r")[-1]), "boyut": p.stat().st_size} for p in eski]

    @_bosaltir
    def geri_al(self, ad: str, revizyon: int) -> Skill:
        s = self.getir(ad)
        if s.kaynak != "uygulama" or s.klasor is None:
            raise UygulamaHatasi("Yalniz uygulamada eklenen skill'ler geri alinabilir.")
        kaynak = self._surum_klasoru(s.klasor) / f"SKILL.r{int(revizyon)}.md"
        if not kaynak.is_file():
            raise UygulamaHatasi(f"Revizyon yok: {revizyon}")
        self._surum_sakla(s.klasor)  # geri alma da geri alinabilsin
        shutil.copy2(kaynak, s.klasor / "SKILL.md")
        return self.getir(ad)

    @_bosaltir
    def ajan_kaydet(self, ad: str, aciklama: str, icerik: str, okunan_revizyon: int = 0) -> dict:
        """Ajanin skill_kaydet araci: yoksa olusturur, varsa (okunan revizyon guncelse) gunceller.
        Claude/brain/proje skill'leri DEGISTIRILMEZ; ajan yalniz uygulama skill'i yazar."""
        ad = ad.strip().lower()
        mevcut = next((x for x in self.kesfet() if x.ad == ad), None)
        if mevcut is None:
            self.olustur(ad, aciklama, icerik)
            return {"olusturuldu": ad, "revizyon": 1}
        if mevcut.kaynak != "uygulama":
            raise UygulamaHatasi(
                f"'{ad}' {mevcut.kaynak} kaynakli bir skill; ajan degistiremez. Baska ad sec."
            )
        simdiki = self.revizyon(ad)
        if int(okunan_revizyon or 0) != simdiki:
            raise UygulamaHatasi(
                f"Skill degismis (su an revizyon {simdiki}). Once skill_kullan ile oku, sonra "
                f"okunan_revizyon={simdiki} ile tekrar kaydet."
            )
        self.guncelle(ad, aciklama, icerik)
        return {"guncellendi": ad, "revizyon": simdiki + 1, "onceki_saklandi": simdiki}

    @staticmethod
    def _yaz(klasor: Path, ad: str, aciklama: str, icerik: str, surum: str = "",
             gereken_araclar: list[str] | None = None) -> None:  # fmt: skip
        meta: dict = {"name": ad, "description": aciklama.strip()}
        if surum.strip():
            meta["version"] = surum.strip()[:40]
        if gereken_araclar:
            meta["required-tools"] = sorted({a.strip() for a in gereken_araclar if a.strip()})
        on = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
        hedef = klasor / "SKILL.md"
        gecici = hedef.with_suffix(".tmp")
        gecici.write_text(f"---\n{on}---\n\n{icerik.strip()}\n", encoding="utf-8")
        gecici.replace(hedef)

    @_bosaltir
    def olustur(self, ad: str, aciklama: str, icerik: str, surum: str = "",
                gereken_araclar: list[str] | None = None) -> Skill:  # fmt: skip
        ad = ad.strip().lower()
        if not AD_DESENI.fullmatch(ad):
            raise UygulamaHatasi("Skill adi kucuk harf, rakam, - _ . olmali (orn. fatura-okuma).")
        if not aciklama.strip():
            raise UygulamaHatasi("Aciklama zorunlu: model skill'i buna bakarak secer.")
        if any(s.ad == ad for s in self.kesfet()):
            raise UygulamaHatasi(f"Bu adda skill zaten var: {ad}")
        klasor = self.uygulama_dizini / ad
        klasor.mkdir(parents=True)
        self._yaz(klasor, ad, aciklama, icerik, surum, gereken_araclar)
        return self.getir(ad)

    @_bosaltir
    def sil(self, ad: str) -> None:
        s = self.getir(ad)
        if s.kaynak != "uygulama" or s.klasor is None:
            raise UygulamaHatasi("Yalniz uygulamada eklenen skill'ler silinebilir.")
        shutil.rmtree(s.klasor)


# ---- secim (kucuk baglam: yalniz en uygunlar listelenir) ----
def _kelimeler(metin: str) -> set[str]:
    return {k for k in KELIME.findall(metin.lower()) if k not in DURAK}


OTOMATIK_ESIK = 5  # bu puan ve ustundeki en iyi skill talimati dogrudan sisteme yuklenir


def puanla(skiller: list[Skill], sorgu: str) -> list[tuple[int, Skill]]:
    """[(puan, skill)] buyukten kucuge; esigin (2) altindakiler yok."""
    sorgu_k = _kelimeler(sorgu)
    if not sorgu_k:
        return []
    puanli = []
    for s in skiller:
        aday = _kelimeler(f"{s.ad.replace('-', ' ')} {s.aciklama}")
        puan = 0
        for k in sorgu_k:
            if k in aday:  # tam kelime
                puan += 3
            elif len(k) >= 4 and any(  # Turkce ek: biri digerinin koku (markdown ~ markdowna)
                len(a) >= 4 and (a.startswith(k) or k.startswith(a)) for a in aday
            ):
                puan += 2
            elif len(k) >= 5 and any(a[:5] == k[:5] for a in aday if len(a) >= 5):
                puan += 1  # ortak 5 harflik on ek (cevirip ~ cevirir)
            if len(k) >= 4 and k in s.ad:
                puan += 2  # skill adinda geciyor
        if puan >= 2:  # tek on ek eslesmesi gurultu sayilir
            puanli.append((puan, s.ad, s))
    puanli.sort(key=lambda x: (-x[0], x[1]))
    return [(p, s) for p, _, s in puanli]


def uygun_skiller(skiller: list[Skill], sorgu: str, n: int = MAX_LISTE) -> list[Skill]:
    """Mesajla ad/aciklama kelime ortusmesine gore siralar; hic ortusmeyen secilmez.
    Turkce ekler icin 5 harflik on ek eslesmesi de sayilir (fatura ~ faturayi)."""
    return [s for _, s in puanla(skiller, sorgu)[:n]]


def otomatik_skill(skiller: list[Skill], sorgu: str) -> Skill | None:
    """Kucuk modeller araci 'cagiracagim' deyip cagirmayabiliyor: mesajla guclu eslesen tek
    skill varsa talimati dogrudan yuklenir (ikinciyle arasi acik olmali)."""
    p = puanla([s for s in skiller if not s.hata], sorgu)  # bozuk skill otomatik yuklenmez
    if p and p[0][0] >= OTOMATIK_ESIK and (len(p) == 1 or p[0][0] - p[1][0] >= 2):
        return p[0][1]
    return None


MODEL_ADAY = 8  # modele sorulan en fazla aday


def secim_istemi(adaylar: list[Skill], mesaj: str) -> str:
    satirlar = "\n".join(f"{i}. {s.ad}: {s.aciklama[:220]}" for i, s in enumerate(adaylar, 1))
    return (
        "Kullanicinin mesaji icin asagidaki skill'lerden biri ACIKCA gerekli mi?\n"
        f"Mesaj: {mesaj[:1500]}\n\nSkill'ler:\n{satirlar}\n\n"
        "Yalniz tek bir sayi yaz: uygun skill'in numarasi, hicbiri acikca uymuyorsa 0."
    )


def secim_coz(cevap: str, adaylar: list[Skill]) -> Skill | None:
    """Modelin cevabindaki ilk sayi; 0 ya da gecersizse None."""
    m = re.search(r"\d+", cevap or "")
    i = int(m.group()) if m else 0
    return adaylar[i - 1] if 1 <= i <= len(adaylar) else None


async def model_ile_sec(llm, skiller: list[Skill], mesaj: str, sorgu: str) -> Skill | None:
    """Kelime eslesmesi yalniz aday listesini daraltir; karari model verir (anlamdan).
    Aday yoksa model cagrilmaz. Hata olursa cagiran kelime yontemine duser."""
    adaylar = [s for _, s in puanla([s for s in skiller if not s.hata], sorgu)][:MODEL_ADAY]
    if not adaylar:
        return None
    cevap = await llm.metin(secim_istemi(adaylar, mesaj), max_tokens=8, dusunme="kapali")
    if not re.search(r"\d", cevap or ""):  # model sayi vermedi: karar yok, kelime yontemi
        raise ValueError(f"Model skill secimine sayi vermedi: {cevap[:60]!r}")
    return secim_coz(cevap, adaylar)


SINIR = (
    "Not: skill'lerdeki komut ve betikleri SEN CALISTIRAMAZSIN (komut calistirma aracin yok). "
    "Kullaniciya adim adim nasil calistiracagini anlat; gereken programlar (CLI, Python paketi) "
    "kullanicinin bilgisayarinda kurulu olmali. Yapamayacagin bir seyi yapabilirmis gibi soyleme."
)


SINIR_AJAN = (
    "Not: skill'lerdeki komut ve betikleri komut_calistir ile KENDIN calistir; gereken program "
    "kurulu degilse kurulum komutunu da sen calistir. Onay gerekiyorsa sistem kullaniciya sorar."
)


SCRIPT_NOTU = (
    "Guncelleme: bu projede skill'in manifestinde (scripts:) ILAN EDILEN scriptleri "
    "skill_scripti_calistir ile calistirabilirsin; kullanici onayi gerekebilir. Ilan edilmemis "
    "komutlari yine kullaniciya anlat."
)


def otomatik_metin(s: Skill, sinir: int = 4000) -> str:
    _, govde = frontmatter(s.dosya.read_text(encoding="utf-8", errors="replace"))
    not_ = "\n[... kisaltildi; tamami icin skill_kullan]" if len(govde) > sinir else ""
    return (
        f"Bu mesaj icin '{s.ad}' skill'i otomatik yuklendi; talimatina uy. {SINIR}\n"
        f'<skill ad="{s.ad}">\n{govde[:sinir]}{not_}\n</skill>'
    )


def tam_liste_metni(skiller: list[Skill], aciklama_siniri: int = 110) -> str:
    """Claude Code gibi tum etkin skill'lerin adi + kisa aciklamasi (sabit; onbellege girer)."""
    if not skiller:
        return ""
    satirlar = "\n".join(
        f"- {s.ad}: {s.aciklama[:aciklama_siniri]}" for s in sorted(skiller, key=lambda s: s.ad)
    )
    return (
        "Kullanilabilir skill'ler (uzman talimatlari). Kullanicinin istegi bunlardan birine "
        "uyuyorsa ONCE skill_kullan(ad) aracini CAGIR, talimati okuyup ona gore calis. Emin "
        f"degilsen skill_ara(sorgu) kullan. {SINIR}\n{satirlar}"
    )


def sistem_metni(secilenler: list[Skill]) -> str:
    if not secilenler:
        return ""
    satirlar = "\n".join(f"- {s.ad}: {s.aciklama[:220]}" for s in secilenler)
    return (
        "Bu konuyla ilgili olabilecek skill'ler (uzman talimatlari) var. Gorev bunlardan birine "
        "uyuyorsa ONCE skill_kullan(ad) ile talimatini yukle ve ona gore calis; baska skill aramak "
        f"icin skill_ara(sorgu) kullan.\n{satirlar}"
    )


# ---- model araclari ----
def arac_isleyicileri(
    depo: SkillDeposu, kapali: set[str], mevcut_araclar: Callable[[], set[str]] | None = None
) -> dict:
    def skill_kullan(ad: str) -> dict:
        try:
            s = depo.getir(ad.strip(), kapali)
        except Bulunamadi as e:
            return {"hata": e.mesaj}
        if s.hata:  # bozuk skill yarim talimatla calistirilmaz
            return {"hata": f"Skill '{s.ad}' bozuk, yuklenmedi: {s.hata}"}
        _, govde = frontmatter(s.dosya.read_text(encoding="utf-8", errors="replace"))
        sonuc = {"ad": s.ad, "talimat": govde[:MAX_SKILL_KARAKTER]}
        if s.kaynak == "uygulama":  # ajan guncellerken bu revizyonu gondermeli
            sonuc["revizyon"] = depo.revizyon(s.ad)
        if s.surum:
            sonuc["surum"] = s.surum
        if s.gereken_araclar:
            sonuc["gereken_araclar"] = list(s.gereken_araclar)
            sonuc["izin_notu"] = (
                "Skill'in arac listesi IZIN VERMEZ; her arac yine izin motorundan gecer."
            )
            if mevcut_araclar is not None:
                eksik = sorted(set(s.gereken_araclar) - mevcut_araclar())
                if eksik:
                    sonuc["eksik_araclar"] = eksik
        if len(govde) > MAX_SKILL_KARAKTER:
            sonuc["not"] = "Talimat kisaltildi."
        if s.klasor:
            ekler = [
                str(p.relative_to(s.klasor)).replace("\\", "/")
                for p in sorted(s.klasor.rglob("*"))
                if p.is_file() and p.name != "SKILL.md" and "__pycache__" not in p.parts
            ]
            if ekler:
                sonuc["dosyalar"] = ekler[:40]
                sonuc["dosya_okuma"] = "Gerekirse skill_dosyasi_oku(ad, yol) ile oku."
        return sonuc

    def skill_dosyasi_oku(ad: str, yol: str) -> dict:
        try:
            s = depo.getir(ad.strip(), kapali)
        except Bulunamadi as e:
            return {"hata": e.mesaj}
        if s.klasor is None:
            return {"hata": "Bu skill tek dosyadan olusuyor; ek dosyasi yok."}
        hedef = (s.klasor / yol).resolve()
        if not hedef.is_relative_to(s.klasor.resolve()) or not hedef.is_file():
            return {"hata": f"Skill klasorunde boyle bir dosya yok: {yol}"}
        veri = hedef.read_bytes()[:200_000]
        if b"\x00" in veri[:4096]:
            return {"hata": "Ikili dosya; okunamaz."}
        metin = veri.decode("utf-8", errors="replace")
        return {"dosya": yol, "icerik": metin[:MAX_SKILL_KARAKTER], "karakter": len(metin)}

    def skill_ara(sorgu: str) -> dict:
        etkin = [s for s in depo.kesfet() if s.ad not in kapali]
        bulunan = uygun_skiller(etkin, sorgu, n=10)
        return {"sonuc": [{"ad": s.ad, "aciklama": s.aciklama[:200]} for s in bulunan]}

    return {
        "skill_kullan": skill_kullan,
        "skill_dosyasi_oku": skill_dosyasi_oku,
        "skill_ara": skill_ara,
    }


ARACLAR: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "skill_kullan",
            "description": "Bir skill'in tam talimatini yukler. Gorev listedeki bir "
            "skill'e uyuyorsa "
            "once bunu cagir.",
            "parameters": {
                "type": "object",
                "properties": {"ad": {"type": "string", "description": "Skill adi"}},
                "required": ["ad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_dosyasi_oku",
            "description": "Yuklenen skill'in klasorundeki bir dosyayi (references/... gibi) okur.",
            "parameters": {
                "type": "object",
                "properties": {"ad": {"type": "string"}, "yol": {"type": "string"}},
                "required": ["ad", "yol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_ara",
            "description": "Tum skill'ler arasinda konuya gore arama yapar "
            "(listede olmayanlar icin).",
            "parameters": {
                "type": "object",
                "properties": {"sorgu": {"type": "string"}},
                "required": ["sorgu"],
            },
        },
    },
]


SKILL_KAYDET_ARACI: dict = {
    "type": "function",
    "function": {
        "name": "skill_kaydet",
        "description": "Tekrar kullanilacak is akisini skill olarak kaydet/guncelle "
        "(guncellemede okunan_revizyon ver).",
        "parameters": {
            "type": "object",
            "properties": {
                "ad": {"type": "string"},
                "aciklama": {"type": "string"},
                "icerik": {"type": "string"},
                "okunan_revizyon": {"type": "integer"},
            },
            "required": ["ad", "aciklama", "icerik"],
        },
    },
}


# ---- A6.2: script araci (yalniz ajan komut araci acikken sunulur) ----
SCRIPT_ARACI: dict = {
    "type": "function",
    "function": {
        "name": "skill_scripti_calistir",
        "description": "Yuklenen skill'in manifestinde (scripts:) ILAN EDILMIS bir scriptini proje "
        "klasorunde calistirir. Kullanici onayi isteyebilir; ilan edilmemis dosya calismaz.",
        "parameters": {
            "type": "object",
            "properties": {
                "ad": {"type": "string", "description": "Skill adi"},
                "script": {"type": "string", "description": "Ornek: scripts/donustur.py"},
                "argumanlar": {"type": "array", "items": {"type": "string"}},
                "arka_plan": {"type": "boolean"},
            },
            "required": ["ad", "script"],
        },
    },
}


def script_isleyicisi(depo: SkillDeposu, kapali: set[str], ajan_kaydi) -> dict:
    """`ajan_kaydi.skill_scripti` izin motorundan gecirir; burada yalniz plan kurulur."""

    def skill_scripti_calistir(
        ad: str, script: str, argumanlar: list[str] | None = None, arka_plan: bool = False
    ) -> dict:
        try:
            s = depo.getir(ad.strip(), kapali)
        except Bulunamadi as e:
            return {"hata": e.mesaj, "karar": "hata"}
        return ajan_kaydi.skill_scripti(
            lambda: script_plani(s, script, argumanlar), arka_plan=arka_plan
        )

    return {"skill_scripti_calistir": skill_scripti_calistir}
