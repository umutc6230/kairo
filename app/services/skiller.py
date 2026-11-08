"""Skill'ler (Claude Code mantigi): her skill bir klasordeki SKILL.md (YAML frontmatter: name,
description) ya da tek .md dosyasi. Model sistem mesajinda uygun skill'lerin adini ve aciklamasini
gorur; gerekirse `skill_kullan` araciyla tam talimati yukler, `skill_dosyasi_oku` ile
klasordeki ek dosyalari (references/...) okur.
Skill'ler yalniz OKUNUR; icindeki betikler calistirilmaz.

Kaynaklar: ~/.claude/skills (Claude Code), ~/Documents/brain/skills (brain),
<veri>/skills (uygulama).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

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


@dataclass(frozen=True)
class Skill:
    ad: str
    aciklama: str
    kaynak: str  # claude | brain | uygulama
    dosya: Path  # SKILL.md ya da tek .md
    klasor: Path | None  # ek dosyalarin klasoru (tek dosyalik skill'de None)

    def ozet(self) -> dict:
        return {
            "ad": self.ad,
            "aciklama": self.aciklama,
            "kaynak": self.kaynak,
            "yol": str(self.dosya),
            "silinebilir": self.kaynak == "uygulama",
        }


def frontmatter(metin: str) -> tuple[dict, str]:
    """('---' arasi YAML, govde). YAML bozuksa bos sozluk."""
    if not metin.startswith("---"):
        return {}, metin
    son = metin.find("\n---", 3)
    if son < 0:
        return {}, metin
    try:
        veri = yaml.safe_load(metin[3:son]) or {}
    except yaml.YAMLError:
        veri = {}
    return (veri if isinstance(veri, dict) else {}), metin[son + 4 :].lstrip("\n")


def _skill_oku(dosya: Path, kaynak: str, klasor: Path | None) -> Skill | None:
    try:
        meta, govde = frontmatter(dosya.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    ad = str(meta.get("name") or (klasor.name if klasor else dosya.stem)).strip()
    aciklama = " ".join(str(meta.get("description") or "").split())
    if not aciklama:  # frontmatter yoksa ilk anlamli satir
        aciklama = next((s.strip("# ").strip() for s in govde.splitlines() if s.strip()), "")
    return Skill(ad=ad, aciklama=aciklama[:600], kaynak=kaynak, dosya=dosya, klasor=klasor)


def varsayilan_kaynaklar(veri_dizini: Path) -> list[tuple[str, Path]]:
    return [
        ("claude", Path.home() / ".claude" / "skills"),
        ("brain", Path.home() / "Documents" / "brain" / "skills"),
        ("uygulama", veri_dizini / "skills"),
    ]


class SkillDeposu:
    def __init__(self, veri_dizini: Path, kaynaklar: list[tuple[str, Path]] | None = None) -> None:
        self.uygulama_dizini = veri_dizini / "skills"
        self.kaynak_listesi = kaynaklar or varsayilan_kaynaklar(veri_dizini)

    def kesfet(self) -> list[Skill]:
        """Tum kaynaklari tarar. Ayni dosya (junction/kisayol) iki kaynakta varsa bir kez alinir;
        ayni ad iki kez varsa ilki (claude > brain > uygulama) kazanir."""
        gorulen_dosya: set[Path] = set()
        gorulen_ad: set[str] = set()
        sonuc: list[Skill] = []
        for kaynak, kok in self.kaynak_listesi:
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
    def olustur(self, ad: str, aciklama: str, icerik: str) -> Skill:
        ad = ad.strip().lower()
        if not AD_DESENI.fullmatch(ad):
            raise UygulamaHatasi("Skill adi kucuk harf, rakam, - _ . olmali (orn. fatura-okuma).")
        if not aciklama.strip():
            raise UygulamaHatasi("Aciklama zorunlu: model skill'i buna bakarak secer.")
        if any(s.ad == ad for s in self.kesfet()):
            raise UygulamaHatasi(f"Bu adda skill zaten var: {ad}")
        klasor = self.uygulama_dizini / ad
        klasor.mkdir(parents=True)
        on = yaml.safe_dump({"name": ad, "description": aciklama.strip()}, allow_unicode=True)
        (klasor / "SKILL.md").write_text(f"---\n{on}---\n\n{icerik.strip()}\n", encoding="utf-8")
        return self.getir(ad)

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
    p = puanla(skiller, sorgu)
    if p and p[0][0] >= OTOMATIK_ESIK and (len(p) == 1 or p[0][0] - p[1][0] >= 2):
        return p[0][1]
    return None


SINIR = (
    "Not: skill'lerdeki komut ve betikleri SEN CALISTIRAMAZSIN (komut calistirma aracin yok). "
    "Kullaniciya adim adim nasil calistiracagini anlat; gereken programlar (CLI, Python paketi) "
    "kullanicinin bilgisayarinda kurulu olmali. Yapamayacagin bir seyi yapabilirmis gibi soyleme."
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
def arac_isleyicileri(depo: SkillDeposu, kapali: set[str]) -> dict:
    def skill_kullan(ad: str) -> dict:
        try:
            s = depo.getir(ad.strip(), kapali)
        except Bulunamadi as e:
            return {"hata": e.mesaj}
        _, govde = frontmatter(s.dosya.read_text(encoding="utf-8", errors="replace"))
        sonuc = {"ad": s.ad, "talimat": govde[:MAX_SKILL_KARAKTER]}
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
