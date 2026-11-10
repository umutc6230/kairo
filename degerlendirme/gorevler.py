"""A13 gercek model degerlendirmesi: surumlu gorev seti (v1, 30 gorev).

Her gorev: baslangic projesi (dosyalar), modele gosterilen hedef/kabul, KORUNAN gorunur testler
(degistirilirse kosu basarisiz), GIZLI kabul kontrolleri (kosudan SONRA kopyalanir; model gormez)
ve referans cozum (yalniz gorev setinin dogrulanmasi icin; modele verilmez).

Gizli kontrol adimi: {"argv": [...], "beklenen": "sifir"|"sifir_degil", "once_yaz": {yol: icerik}}
argv'de {py} {node} {dotnet} yer tutuculari. Tum kontroller proje klasorunde calisir.
"""

from __future__ import annotations

import textwrap

SURUM = "v1"


def d(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


def py_test(dosya: str) -> dict:
    return {"argv": ["{py}", "-m", "pytest", "-q", "-p", "no:cacheprovider", dosya]}


def node_test(dosya: str) -> dict:
    return {"argv": ["{node}", "--test", dosya]}


def dotnet_run() -> dict:
    return {"argv": ["{dotnet}", "run", "--project", "App.csproj"]}


CSPROJ = d("""
    <Project Sdk="Microsoft.NET.Sdk">
      <PropertyGroup>
        <OutputType>Exe</OutputType>
        <TargetFramework>net8.0</TargetFramework>
        <Nullable>enable</Nullable>
        <ImplicitUsings>disable</ImplicitUsings>
      </PropertyGroup>
    </Project>
""")
PYTEST_YOL = "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parent.parent))\n"

G: list[dict] = []


def gorev(**k) -> None:
    k.setdefault("korunan", [])
    k.setdefault("kabul", [])
    k.setdefault("max_adim", 40)
    G.append(k)


# ============================================================ 1) hata duzeltme (6)
gorev(
    id="hata-py-median", kategori="hata", dil="python",
    hedef="stats.py icindeki median fonksiyonu cift uzunluklu listelerde yanlis sonuc veriyor. Duzelt.",
    kabul=["python -m pytest -q tests gecsin"],
    dosyalar={
        "stats.py": d("""
            def median(xs):
                if not xs:
                    raise ValueError("bos liste")
                s = sorted(xs)
                return s[len(s) // 2]
        """),
        "tests/test_stats.py": PYTEST_YOL + d("""
            from stats import median

            def test_tek():
                assert median([3, 1, 2]) == 2
        """),
    },
    korunan=["tests/test_stats.py"],
    gizli={"_gizli/test_g.py": PYTEST_YOL + d("""
        import pytest
        from stats import median

        def test_cift():
            assert median([4, 1, 3, 2]) == 2.5
            assert median([1, 2]) == 1.5

        def test_tek_ve_bos():
            assert median([5]) == 5
            with pytest.raises(ValueError):
                median([])
    """)},
    kontroller=[py_test("tests"), py_test("_gizli/test_g.py")],
    cozum={"stats.py": d("""
        def median(xs):
            if not xs:
                raise ValueError("bos liste")
            s = sorted(xs)
            n = len(s)
            if n % 2:
                return s[n // 2]
            return (s[n // 2 - 1] + s[n // 2]) / 2
    """)},
)  # fmt: skip

gorev(
    id="hata-py-isgunu", kategori="hata", dil="python",
    hedef="tarih.py'deki is_gunu_say(bas, bit) hafta sonlarini da sayiyor. Yalniz Pazartesi-Cuma gunlerini say (iki uc dahil).",
    dosyalar={"tarih.py": d("""
        from datetime import date, timedelta

        def is_gunu_say(bas: date, bit: date) -> int:
            if bit < bas:
                return 0
            return (bit - bas).days + 1
    """)},
    gizli={"_gizli/test_g.py": PYTEST_YOL + d("""
        from datetime import date
        from tarih import is_gunu_say

        def test_hafta():
            assert is_gunu_say(date(2026, 11, 9), date(2026, 11, 15)) == 5  # Pzt-Paz
            assert is_gunu_say(date(2026, 11, 14), date(2026, 11, 15)) == 0  # Cmt-Paz
            assert is_gunu_say(date(2026, 11, 13), date(2026, 11, 16)) == 2  # Cum-Pzt
            assert is_gunu_say(date(2026, 11, 10), date(2026, 11, 9)) == 0
            assert is_gunu_say(date(2026, 11, 2), date(2026, 11, 29)) == 20
    """)},
    kontroller=[py_test("_gizli/test_g.py")],
    cozum={"tarih.py": d("""
        from datetime import date, timedelta

        def is_gunu_say(bas: date, bit: date) -> int:
            if bit < bas:
                return 0
            return sum(1 for i in range((bit - bas).days + 1)
                       if (bas + timedelta(days=i)).weekday() < 5)
    """)},
)  # fmt: skip

gorev(
    id="hata-py-indirim-cok-dosya", kategori="hata", dil="python",
    hedef="Sepette indirim iki kez uygulaniyor gibi: %10 indirimli 100 TL'lik urun 81 TL cikiyor, 90 olmali. Hatayi bul ve duzelt.",
    dosyalar={
        "fiyat.py": d("""
            def indirimli(fiyat: float, oran: float) -> float:
                return round(fiyat * (1 - oran) * (1 - oran), 2)
        """),
        "sepet.py": d("""
            from fiyat import indirimli

            class Sepet:
                def __init__(self):
                    self.kalemler = []

                def ekle(self, fiyat, adet=1, indirim=0.0):
                    self.kalemler.append((fiyat, adet, indirim))

                def toplam(self):
                    return round(sum(indirimli(f, i) * a for f, a, i in self.kalemler), 2)
        """),
    },
    gizli={"_gizli/test_g.py": PYTEST_YOL + d("""
        from sepet import Sepet
        from fiyat import indirimli

        def test_indirim():
            assert indirimli(100, 0.1) == 90
            assert indirimli(50, 0) == 50
            s = Sepet(); s.ekle(100, 2, 0.1); s.ekle(10)
            assert s.toplam() == 190
    """)},
    kontroller=[py_test("_gizli/test_g.py")],
    cozum={"fiyat.py": "def indirimli(fiyat: float, oran: float) -> float:\n    return round(fiyat * (1 - oran), 2)\n"},
)  # fmt: skip

gorev(
    id="hata-ts-slug", kategori="hata", dil="typescript",
    hedef="src/slug.ts icindeki slugify Turkce harfleri (ı ş ğ ü ö ç İ) duzgun cevirmiyor ve ardisik tireleri birlestirmiyor. Duzelt: 'Çalışma Ağı  Özeti!' -> 'calisma-agi-ozeti'.",
    dosyalar={"src/slug.ts": d("""
        export function slugify(metin: string): string {
          return metin
            .toLowerCase()
            .replace(/[^a-z0-9]/g, "-")
            .replace(/^-|-$/g, "");
        }
    """)},
    gizli={"_gizli/slug.test.ts": d("""
        import { test } from "node:test";
        import assert from "node:assert/strict";
        import { slugify } from "../src/slug.ts";

        test("turkce", () => {
          assert.equal(slugify("Çalışma Ağı  Özeti!"), "calisma-agi-ozeti");
          assert.equal(slugify("İstanbul Şubesi"), "istanbul-subesi");
          assert.equal(slugify("--Güneş--"), "gunes");
          assert.equal(slugify("a   b"), "a-b");
        });
    """)},
    kontroller=[node_test("_gizli/slug.test.ts")],
    cozum={"src/slug.ts": d("""
        const HARF: Record<string, string> = { ı: "i", ş: "s", ğ: "g", ü: "u", ö: "o", ç: "c", i̇: "i" };

        export function slugify(metin: string): string {
          return metin
            .replace(/İ/g, "i")
            .toLowerCase()
            .replace(/[ışğüöç]/g, (h) => HARF[h] ?? h)
            .normalize("NFD").replace(/[\\u0300-\\u036f]/g, "")
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "");
        }
    """)},
)  # fmt: skip

gorev(
    id="hata-ts-sayfala", kategori="hata", dil="typescript",
    hedef="src/sayfala.ts: son sayfa eksik geliyor (10 kayit, sayfa boyu 3 ise 4 sayfa olmali). sayfaSayisi ve sayfa fonksiyonlarini duzelt.",
    dosyalar={"src/sayfala.ts": d("""
        export function sayfaSayisi(toplam: number, boyut: number): number {
          return Math.floor(toplam / boyut);
        }

        export function sayfa<T>(liste: T[], no: number, boyut: number): T[] {
          // no 1 tabanli
          return liste.slice(no * boyut, no * boyut + boyut);
        }
    """)},
    gizli={"_gizli/s.test.ts": d("""
        import { test } from "node:test";
        import assert from "node:assert/strict";
        import { sayfa, sayfaSayisi } from "../src/sayfala.ts";

        test("sayfa", () => {
          const l = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
          assert.equal(sayfaSayisi(10, 3), 4);
          assert.equal(sayfaSayisi(9, 3), 3);
          assert.equal(sayfaSayisi(0, 3), 0);
          assert.deepEqual(sayfa(l, 1, 3), [1, 2, 3]);
          assert.deepEqual(sayfa(l, 4, 3), [10]);
          assert.deepEqual(sayfa(l, 5, 3), []);
        });
    """)},
    kontroller=[node_test("_gizli/s.test.ts")],
    cozum={"src/sayfala.ts": d("""
        export function sayfaSayisi(toplam: number, boyut: number): number {
          return Math.ceil(toplam / boyut);
        }

        export function sayfa<T>(liste: T[], no: number, boyut: number): T[] {
          return liste.slice((no - 1) * boyut, (no - 1) * boyut + boyut);
        }
    """)},
)  # fmt: skip

gorev(
    id="hata-cs-ortalama", kategori="hata", dil="csharp",
    hedef="Hesap.cs icindeki Ortalama metodu tamsayi bolmesi yapiyor; [1,2] icin 1.5 donmeli. Duzelt. (dotnet run ile kontrol edebilirsin)",
    dosyalar={
        "App.csproj": CSPROJ,
        "Hesap.cs": d("""
            namespace App;

            public static class Hesap
            {
                public static double Ortalama(int[] sayilar)
                {
                    if (sayilar.Length == 0) return 0;
                    int toplam = 0;
                    foreach (var s in sayilar) toplam += s;
                    return toplam / sayilar.Length;
                }
            }
        """),
        "Program.cs": d("""
            using System;
            namespace App;

            public static class Program
            {
                public static void Main() => Console.WriteLine(Hesap.Ortalama(new[] { 1, 2 }));
            }
        """),
    },
    gizli={"Program.cs": d("""
        using System;
        namespace App;

        public static class Program
        {
            public static int Main()
            {
                if (Math.Abs(Hesap.Ortalama(new[] { 1, 2 }) - 1.5) > 1e-9) return 1;
                if (Math.Abs(Hesap.Ortalama(new[] { 1, 2, 4 }) - 7.0 / 3) > 1e-9) return 2;
                if (Hesap.Ortalama(new int[0]) != 0) return 3;
                return 0;
            }
        }
    """)},
    kontroller=[dotnet_run()],
    cozum={"Hesap.cs": d("""
        namespace App;

        public static class Hesap
        {
            public static double Ortalama(int[] sayilar)
            {
                if (sayilar.Length == 0) return 0;
                long toplam = 0;
                foreach (var s in sayilar) toplam += s;
                return (double)toplam / sayilar.Length;
            }
        }
    """)},
)  # fmt: skip

# ============================================================ 2) cok dosyali ozellik / refactor (5)
gorev(
    id="ozellik-py-json-cikti", kategori="ozellik", dil="python",
    hedef="cli.py'ye --json secenegi ekle: verildiginde rapor JSON olarak yazilsin ({\"toplam\": .., \"adet\": .., \"ortalama\": ..}). Varsayilan metin cikti degismesin.",
    dosyalar={
        "rapor.py": d("""
            import csv

            def ozet(yol):
                with open(yol, encoding="utf-8") as f:
                    tutarlar = [float(r["tutar"]) for r in csv.DictReader(f)]
                adet = len(tutarlar)
                return {"toplam": sum(tutarlar), "adet": adet,
                        "ortalama": sum(tutarlar) / adet if adet else 0}
        """),
        "cli.py": d("""
            import sys
            from rapor import ozet

            def main(argv):
                o = ozet(argv[0])
                print(f"Toplam: {o['toplam']:.2f} | Adet: {o['adet']} | Ortalama: {o['ortalama']:.2f}")

            if __name__ == "__main__":
                main(sys.argv[1:])
        """),
        "veri.csv": "tutar\n10\n20\n30\n",
    },
    gizli={"_gizli/test_g.py": PYTEST_YOL + d("""
        import json, subprocess, sys, pathlib
        KOK = pathlib.Path(__file__).parent.parent

        def calis(*a):
            return subprocess.run([sys.executable, "cli.py", *a], cwd=KOK, capture_output=True,
                                  text=True, check=True).stdout.strip()

        def test_json():
            v = json.loads(calis("veri.csv", "--json"))
            assert v == {"toplam": 60.0, "adet": 3, "ortalama": 20.0}
            v = json.loads(calis("--json", "veri.csv"))
            assert v["adet"] == 3

        def test_metin_ayni():
            assert calis("veri.csv") == "Toplam: 60.00 | Adet: 3 | Ortalama: 20.00"
    """)},
    kontroller=[py_test("_gizli/test_g.py")],
    cozum={"cli.py": d("""
        import json
        import sys
        from rapor import ozet

        def main(argv):
            dosyalar = [a for a in argv if a != "--json"]
            o = ozet(dosyalar[0])
            if "--json" in argv:
                print(json.dumps(o))
                return
            print(f"Toplam: {o['toplam']:.2f} | Adet: {o['adet']} | Ortalama: {o['ortalama']:.2f}")

        if __name__ == "__main__":
            main(sys.argv[1:])
    """)},
)  # fmt: skip

_EPOSTA_RE = 'EPOSTA = re.compile(r"^[^@\\s]+@[^@\\s]+\\.[a-z]{2,}$", re.I)'
gorev(
    id="refactor-py-ortak-dogrulama", kategori="ozellik", dil="python",
    hedef="kullanici.py ve siparis.py ayni e-posta dogrulamasini kopyalamis. Bunu yeni dogrulama.py modulunde eposta_gecerli(adres) fonksiyonuna tasi; iki modul de onu kullansin, kendi regex'leri kalmasin. Davranis degismesin.",
    kabul=["python -m pytest -q tests gecsin"],
    dosyalar={
        "kullanici.py": f"import re\n\n{_EPOSTA_RE}\n\n\ndef kayit(ad, eposta):\n    if not EPOSTA.match(eposta):\n        raise ValueError('gecersiz e-posta')\n    return {{'ad': ad, 'eposta': eposta.lower()}}\n",
        "siparis.py": f"import re\n\n{_EPOSTA_RE}\n\n\ndef bildirim_adresi(siparis):\n    a = siparis.get('eposta', '')\n    return a if EPOSTA.match(a) else None\n",
        "tests/test_mevcut.py": PYTEST_YOL + d("""
            import pytest
            from kullanici import kayit
            from siparis import bildirim_adresi

            def test_kayit():
                assert kayit("a", "A@B.com")["eposta"] == "a@b.com"
                with pytest.raises(ValueError):
                    kayit("a", "yanlis")

            def test_siparis():
                assert bildirim_adresi({"eposta": "x@y.org"}) == "x@y.org"
                assert bildirim_adresi({"eposta": "x@y"}) is None
        """),
    },
    korunan=["tests/test_mevcut.py"],
    gizli={"_gizli/test_g.py": PYTEST_YOL + d("""
        import pathlib
        from dogrulama import eposta_gecerli
        KOK = pathlib.Path(__file__).parent.parent

        def test_ortak():
            assert eposta_gecerli("a@b.co") and not eposta_gecerli("a@b") and not eposta_gecerli("a b@c.com")
            for ad in ("kullanici.py", "siparis.py"):
                kaynak = (KOK / ad).read_text(encoding="utf-8")
                assert "re.compile" not in kaynak and "eposta_gecerli" in kaynak, ad
    """)},
    kontroller=[py_test("tests"), py_test("_gizli/test_g.py")],
    cozum={
        "dogrulama.py": f"import re\n\n{_EPOSTA_RE}\n\n\ndef eposta_gecerli(adres):\n    return bool(EPOSTA.match(adres or ''))\n",
        "kullanici.py": "from dogrulama import eposta_gecerli\n\n\ndef kayit(ad, eposta):\n    if not eposta_gecerli(eposta):\n        raise ValueError('gecersiz e-posta')\n    return {'ad': ad, 'eposta': eposta.lower()}\n",
        "siparis.py": "from dogrulama import eposta_gecerli\n\n\ndef bildirim_adresi(siparis):\n    a = siparis.get('eposta', '')\n    return a if eposta_gecerli(a) else None\n",
    },
)  # fmt: skip

gorev(
    id="ozellik-ts-todo-filtre", kategori="ozellik", dil="typescript",
    hedef="src/todo.ts'deki TodoListesi sinifina filtre(etiket: string) metodu ekle (o etiketi tasiyan, tamamlanmamis gorevleri dondursun) ve src/index.ts'den de TodoListesi'ni disa aktar.",
    dosyalar={
        "src/todo.ts": d("""
            export type Gorev = { baslik: string; etiketler: string[]; bitti: boolean };

            export class TodoListesi {
              gorevler: Gorev[] = [];
              ekle(baslik: string, etiketler: string[] = []): void {
                this.gorevler.push({ baslik, etiketler, bitti: false });
              }
              bitir(baslik: string): void {
                const g = this.gorevler.find((x) => x.baslik === baslik);
                if (g) g.bitti = true;
              }
            }
        """),
        "src/index.ts": 'export type { Gorev } from "./todo.ts";\n',
    },
    gizli={"_gizli/t.test.ts": d("""
        import { test } from "node:test";
        import assert from "node:assert/strict";
        import { TodoListesi } from "../src/index.ts";

        test("filtre", () => {
          const t = new TodoListesi();
          t.ekle("a", ["is"]); t.ekle("b", ["ev"]); t.ekle("c", ["is", "acil"]);
          t.bitir("c");
          assert.deepEqual(t.filtre("is").map((g) => g.baslik), ["a"]);
          assert.deepEqual(t.filtre("yok"), []);
        });
    """)},
    kontroller=[node_test("_gizli/t.test.ts")],
    cozum={
        "src/todo.ts": d("""
            export type Gorev = { baslik: string; etiketler: string[]; bitti: boolean };

            export class TodoListesi {
              gorevler: Gorev[] = [];
              ekle(baslik: string, etiketler: string[] = []): void {
                this.gorevler.push({ baslik, etiketler, bitti: false });
              }
              bitir(baslik: string): void {
                const g = this.gorevler.find((x) => x.baslik === baslik);
                if (g) g.bitti = true;
              }
              filtre(etiket: string): Gorev[] {
                return this.gorevler.filter((g) => !g.bitti && g.etiketler.includes(etiket));
              }
            }
        """),
        "src/index.ts": 'export type { Gorev } from "./todo.ts";\nexport { TodoListesi } from "./todo.ts";\n',
    },
)  # fmt: skip

gorev(
    id="refactor-ts-yeniden-adlandir", kategori="ozellik", dil="typescript",
    hedef="hesapla fonksiyonunun adini tum projede toplamHesapla yap (tanim, import'lar ve cagrilar). Eski ad disa aktarilmasin; davranis ayni kalsin.",
    dosyalar={
        "src/hesap.ts": "export function hesapla(xs: number[]): number {\n  return xs.reduce((a, b) => a + b, 0);\n}\n",
        "src/rapor.ts": 'import { hesapla } from "./hesap.ts";\n\nexport function rapor(xs: number[]): string {\n  return `Toplam: ${hesapla(xs)}`;\n}\n',
        "src/sepet.ts": 'import { hesapla } from "./hesap.ts";\n\nexport const sepetToplam = (fiyatlar: number[]) => hesapla(fiyatlar) * 1.2;\n',
    },
    gizli={"_gizli/r.test.ts": d("""
        import { test } from "node:test";
        import assert from "node:assert/strict";
        import * as h from "../src/hesap.ts";
        import { rapor } from "../src/rapor.ts";
        import { sepetToplam } from "../src/sepet.ts";
        import { readFileSync } from "node:fs";

        test("ad", () => {
          assert.equal((h as any).toplamHesapla([1, 2, 3]), 6);
          assert.equal((h as any).hesapla, undefined);
          assert.equal(rapor([1, 2]), "Toplam: 3");
          assert.equal(sepetToplam([10]), 12);
          for (const f of ["src/rapor.ts", "src/sepet.ts"])
            assert.ok(!/\\bhesapla\\b/.test(readFileSync(f, "utf8")), f);
        });
    """)},
    kontroller=[node_test("_gizli/r.test.ts")],
    cozum={
        "src/hesap.ts": "export function toplamHesapla(xs: number[]): number {\n  return xs.reduce((a, b) => a + b, 0);\n}\n",
        "src/rapor.ts": 'import { toplamHesapla } from "./hesap.ts";\n\nexport function rapor(xs: number[]): string {\n  return `Toplam: ${toplamHesapla(xs)}`;\n}\n',
        "src/sepet.ts": 'import { toplamHesapla } from "./hesap.ts";\n\nexport const sepetToplam = (fiyatlar: number[]) => toplamHesapla(fiyatlar) * 1.2;\n',
    },
)  # fmt: skip

gorev(
    id="ozellik-cs-kdv", kategori="ozellik", dil="csharp",
    hedef="Urun.cs'deki Urun sinifina KdvliFiyat(decimal oran) metodu ekle: Fiyat * (1 + oran), 2 basamaga yuvarlanmis (MidpointRounding.AwayFromZero). Negatif oran ArgumentOutOfRangeException firlatsin.",
    dosyalar={
        "App.csproj": CSPROJ,
        "Urun.cs": "namespace App;\n\npublic class Urun\n{\n    public string Ad { get; set; } = \"\";\n    public decimal Fiyat { get; set; }\n}\n",
        "Program.cs": "using System;\nnamespace App;\n\npublic static class Program\n{\n    public static void Main() => Console.WriteLine(new Urun { Ad = \"x\", Fiyat = 10m }.Ad);\n}\n",
    },
    gizli={"Program.cs": d("""
        using System;
        namespace App;

        public static class Program
        {
            public static int Main()
            {
                var u = new Urun { Ad = "x", Fiyat = 10.05m };
                if (u.KdvliFiyat(0.2m) != 12.06m) return 1;
                if (new Urun { Fiyat = 100m }.KdvliFiyat(0m) != 100m) return 2;
                try { u.KdvliFiyat(-0.1m); return 3; } catch (ArgumentOutOfRangeException) { }
                return 0;
            }
        }
    """)},
    kontroller=[dotnet_run()],
    cozum={"Urun.cs": d("""
        using System;
        namespace App;

        public class Urun
        {
            public string Ad { get; set; } = "";
            public decimal Fiyat { get; set; }

            public decimal KdvliFiyat(decimal oran)
            {
                if (oran < 0) throw new ArgumentOutOfRangeException(nameof(oran));
                return Math.Round(Fiyat * (1 + oran), 2, MidpointRounding.AwayFromZero);
            }
        }
    """)},
)  # fmt: skip

# ============================================================ 3) test / build (4)
_SURE = d("""
    def parse_sure(metin: str) -> int:
        \"\"\"'1s30d' -> 5400 saniye; 's' saat, 'd' dakika, 'sn' saniye. Gecersizse ValueError.\"\"\"
        import re
        if not metin or not re.fullmatch(r"(\\d+(sn|s|d))+", metin):
            raise ValueError(metin)
        carpan = {"s": 3600, "d": 60, "sn": 1}
        return sum(int(n) * carpan[b] for n, b in re.findall(r"(\\d+)(sn|s|d)", metin))
""")
gorev(
    id="test-py-yaz-mutasyon", kategori="test", dil="python",
    hedef="sure.py'deki parse_sure icin tests/test_sure.py dosyasinda pytest testleri yaz: en az 5 test fonksiyonu; saat, dakika, saniye, birlesik ve gecersiz girdi durumlarini kapsasin. Testler gecsin.",
    dosyalar={"sure.py": _SURE},
    gizli={"_gizli/say.py": d("""
        import pathlib, sys
        t = pathlib.Path("tests/test_sure.py").read_text(encoding="utf-8")
        sys.exit(0 if t.count("def test_") >= 5 else 1)
    """)},
    kontroller=[
        {"argv": ["{py}", "_gizli/say.py"]},
        py_test("tests/test_sure.py"),
        # mutasyonlar: yazilan testler hatali uygulamayi YAKALAMALI
        {**py_test("tests/test_sure.py"), "beklenen": "sifir_degil",
         "once_yaz": {"sure.py": _SURE.replace('"d": 60', '"d": 30')}},
        {**py_test("tests/test_sure.py"), "beklenen": "sifir_degil",
         "once_yaz": {"sure.py": _SURE.replace("raise ValueError(metin)", "return 0")}},
    ],
    cozum={"tests/test_sure.py": PYTEST_YOL + d("""
        import pytest
        from sure import parse_sure

        def test_saat(): assert parse_sure("2s") == 7200
        def test_dakika(): assert parse_sure("5d") == 300
        def test_saniye(): assert parse_sure("9sn") == 9
        def test_birlesik(): assert parse_sure("1s30d") == 5400
        def test_gecersiz():
            for x in ("", "abc", "5"):
                with pytest.raises(ValueError):
                    parse_sure(x)
    """)},
)  # fmt: skip

gorev(
    id="build-py-import", kategori="test", dil="python",
    hedef="Testler toplanirken (collection) hata veriyor. Nedenini bul ve duzelt; testleri degistirme.",
    kabul=["python -m pytest -q tests gecsin"],
    dosyalar={
        "paket/__init__.py": "from paket.cekirdek import topla_hepsi, ortalama\n",
        "paket/cekirdek.py": "def toplam(xs):\n    return sum(xs)\n\n\ndef ortalama(xs):\n    return toplam(xs) / len(xs) if xs else 0\n",
        "tests/test_paket.py": PYTEST_YOL + "from paket import ortalama, toplam\n\n\ndef test_o():\n    assert ortalama([2, 4]) == 3\n    assert toplam([1, 2]) == 3\n",
    },
    korunan=["tests/test_paket.py"],
    gizli={},
    kontroller=[py_test("tests")],
    cozum={"paket/__init__.py": "from paket.cekirdek import ortalama, toplam\n"},
)  # fmt: skip

gorev(
    id="build-cs-derleme", kategori="test", dil="csharp",
    hedef="dotnet build hata veriyor. Derleme hatalarini duzelt; program 'Toplam: 6' yazdirmali.",
    dosyalar={
        "App.csproj": CSPROJ,
        "Liste.cs": d("""
            using System.Collections.Generic;
            namespace App;

            public static class Liste
            {
                public static int Toplam(List<int> xs) => xs.Sum();
                public static string Yazi(int t) => "Toplam: " + t;
            }
        """),
        "Program.cs": d("""
            using System;
            using System.Collections.Generic;
            namespace App;

            public static class Program
            {
                public static void Main()
                {
                    string t = Liste.Toplam(new List<int> { 1, 2, 3 });
                    Console.WriteLine(Liste.Yazi(t));
                }
            }
        """),
    },
    gizli={"Program.cs": d("""
        using System;
        using System.Collections.Generic;
        namespace App;

        public static class Program
        {
            public static int Main()
            {
                if (Liste.Toplam(new List<int> { 1, 2, 3 }) != 6) return 1;
                return Liste.Yazi(6) == "Toplam: 6" ? 0 : 2;
            }
        }
    """)},
    kontroller=[dotnet_run()],
    cozum={
        "Liste.cs": d("""
            using System.Collections.Generic;
            using System.Linq;
            namespace App;

            public static class Liste
            {
                public static int Toplam(List<int> xs) => xs.Sum();
                public static string Yazi(int t) => "Toplam: " + t;
            }
        """),
        "Program.cs": d("""
            using System;
            using System.Collections.Generic;
            namespace App;

            public static class Program
            {
                public static void Main()
                {
                    int t = Liste.Toplam(new List<int> { 1, 2, 3 });
                    Console.WriteLine(Liste.Yazi(t));
                }
            }
        """),
    },
)  # fmt: skip

gorev(
    id="build-ts-npm-test", kategori="test", dil="typescript",
    hedef="'npm test' calismiyor. package.json'daki test betigini duzelt; test dosyalarini degistirme.",
    dosyalar={
        "package.json": '{\n  "name": "ornek",\n  "private": true,\n  "type": "module",\n  "scripts": { "test": "node --test tests/*.spec.ts" }\n}\n',
        "src/kare.ts": "export const kare = (x: number): number => x * x;\n",
        "test/kare.test.ts": 'import { test } from "node:test";\nimport assert from "node:assert/strict";\nimport { kare } from "../src/kare.ts";\n\ntest("kare", () => assert.equal(kare(3), 9));\n',
    },
    korunan=["test/kare.test.ts"],
    gizli={"_gizli/kontrol.mjs": d("""
        import { execSync } from "node:child_process";
        import { readFileSync } from "node:fs";
        const p = JSON.parse(readFileSync("package.json", "utf8"));
        if (!p.scripts?.test || !p.scripts.test.includes("test/")) process.exit(1);
        execSync(p.scripts.test, { stdio: "inherit" });
    """)},
    kontroller=[{"argv": ["{node}", "_gizli/kontrol.mjs"]}],
    cozum={"package.json": '{\n  "name": "ornek",\n  "private": true,\n  "type": "module",\n  "scripts": { "test": "node --test test/kare.test.ts" }\n}\n'},
)  # fmt: skip

# ============================================================ 4) repo kesfi / review (4)
_KESIF = {
    "uygulama/__init__.py": "",
    "uygulama/api.py": "from uygulama.servis import kayit_ol\n\n\ndef post_kayit(istek):\n    return kayit_ol(istek['ad'], istek['parola'])\n",
    "uygulama/servis.py": "from uygulama.guvenlik.parola import sifrele_parola\nfrom uygulama.depo import kaydet\n\n\ndef kayit_ol(ad, parola):\n    return kaydet({'ad': ad, 'hash': sifrele_parola(parola)})\n",
    "uygulama/guvenlik/__init__.py": "",
    "uygulama/guvenlik/parola.py": "import hashlib, os\n\n\ndef sifrele_parola(parola: str) -> str:\n    tuz = os.urandom(16)\n    h = hashlib.pbkdf2_hmac('sha256', parola.encode(), tuz, 200_000)\n    return tuz.hex() + ':' + h.hex()\n",
    "uygulama/guvenlik/token.py": "import hashlib\n\n\ndef oturum_kimligi(kullanici_id: int) -> str:\n    return hashlib.md5(str(kullanici_id).encode()).hexdigest()  # yalniz onbellek anahtari\n",
    "uygulama/depo.py": "_DB = []\n\n\ndef kaydet(kayit):\n    _DB.append(kayit)\n    return len(_DB)\n",
    "uygulama/ayar.py": "import os\n\nPORT = int(os.environ.get('APP_PORT', '8000'))\nDB_URL = os.environ.get('APP_DB_URL', 'sqlite:///veri.db')\nDEBUG = os.getenv('APP_DEBUG', '0') == '1'\n# ESKI: LEGACY_PORT artik okunmuyor\n",
}
gorev(
    id="kesif-parola-hash", kategori="kesif", dil="python",
    hedef="Bu projede kullanici parolalari hangi dosyada, hangi fonksiyonda ve hangi algoritmayla hashleniyor? Cevabi CEVAP.md dosyasina yaz (dosya yolu, fonksiyon adi, algoritma). Kod degistirme.",
    dosyalar=_KESIF,
    korunan=list(_KESIF),
    gizli={"_gizli/k.py": d("""
        import pathlib, sys
        c = pathlib.Path("CEVAP.md").read_text(encoding="utf-8").lower()
        ok = "parola.py" in c and "sifrele_parola" in c and "pbkdf2" in c
        sys.exit(0 if ok else 1)
    """)},
    kontroller=[{"argv": ["{py}", "_gizli/k.py"]}],
    cozum={"CEVAP.md": "uygulama/guvenlik/parola.py, sifrele_parola: PBKDF2-HMAC-SHA256 (200000 tur, 16 bayt tuz)\n"},
)  # fmt: skip

gorev(
    id="kesif-ortam-degiskenleri", kategori="kesif", dil="python",
    hedef="Uygulama yapilandirmayi hangi ortam degiskenlerinden okuyor? CEVAP.md'ye her birini varsayilan degeriyle birlikte listele. Artik okunmayanlari yazma. Kod degistirme.",
    dosyalar=_KESIF,
    korunan=list(_KESIF),
    gizli={"_gizli/k.py": d("""
        import pathlib, sys
        c = pathlib.Path("CEVAP.md").read_text(encoding="utf-8")
        ok = all(x in c for x in ("APP_PORT", "APP_DB_URL", "APP_DEBUG", "8000")) and "LEGACY_PORT" not in c
        sys.exit(0 if ok else 1)
    """)},
    kontroller=[{"argv": ["{py}", "_gizli/k.py"]}],
    cozum={"CEVAP.md": "- APP_PORT (8000)\n- APP_DB_URL (sqlite:///veri.db)\n- APP_DEBUG (0)\n"},
)  # fmt: skip

_REVIEW_KOD = d("""
    import sqlite3

    def kullanici_bul(db: sqlite3.Connection, ad: str):
        sorgu = f"SELECT id, ad FROM kullanici WHERE ad = '{ad}'"
        return db.execute(sorgu).fetchone()
""")
gorev(
    id="review-py-sql", kategori="kesif", dil="python",
    hedef="depo.py'deki son degisikligi (degisiklik.diff) kod review'dan gecir. Buldugun en ciddi sorunu ve onerilen duzeltmeyi REVIEW.md'ye yaz. Kodu DEGISTIRME.",
    dosyalar={
        "depo.py": _REVIEW_KOD,
        "degisiklik.diff": d("""
            --- a/depo.py
            +++ b/depo.py
            @@
            -    return db.execute("SELECT id, ad FROM kullanici WHERE ad = ?", (ad,)).fetchone()
            +    sorgu = f"SELECT id, ad FROM kullanici WHERE ad = '{ad}'"
            +    return db.execute(sorgu).fetchone()
        """),
    },
    korunan=["depo.py"],
    gizli={"_gizli/k.py": d("""
        import pathlib, sys
        c = pathlib.Path("REVIEW.md").read_text(encoding="utf-8").lower()
        ok = ("injection" in c or "enjeksiyon" in c) and ("parametre" in c or "?" in c or "placeholder" in c)
        sys.exit(0 if ok else 1)
    """)},
    kontroller=[{"argv": ["{py}", "_gizli/k.py"]}],
    cozum={"REVIEW.md": "Kritik: SQL injection. f-string yerine parametreli sorgu kullanin: WHERE ad = ? ve (ad,).\n"},
)  # fmt: skip

_KULLANILMAYAN = {
    "src/format.ts": "export const formatla = (x: number) => x.toFixed(2);\nexport const eskiFormat = (x: number) => String(x);\n",
    "src/yedek.ts": 'export function yedekAl(): string { return "yedek"; }\nexport function geriYukle(): string { return "ok"; }\n',
    "src/main.ts": 'import { formatla } from "./format.ts";\nimport { geriYukle } from "./yedek.ts";\n\nconsole.log(formatla(1), geriYukle());\n',
}
gorev(
    id="review-ts-kullanilmayan", kategori="kesif", dil="typescript",
    hedef="src/ altinda disa aktarilan ama projede hic kullanilmayan fonksiyonlari bul ve adlarini KULLANILMAYAN.md'ye yaz. Kod degistirme.",
    dosyalar=_KULLANILMAYAN,
    korunan=list(_KULLANILMAYAN),
    gizli={"_gizli/k.py": d("""
        import pathlib, sys
        c = pathlib.Path("KULLANILMAYAN.md").read_text(encoding="utf-8")
        ok = "eskiFormat" in c and "yedekAl" in c and "formatla" not in c.replace("eskiFormat", "") and "geriYukle" not in c
        sys.exit(0 if ok else 1)
    """)},
    kontroller=[{"argv": ["{py}", "_gizli/k.py"]}],
    cozum={"KULLANILMAYAN.md": "- eskiFormat (src/format.ts)\n- yedekAl (src/yedek.ts)\n"},
)  # fmt: skip


# ============================================================ 5) uzun baglam / devam (4)
def _dolgu_modulleri(n: int) -> dict:
    return {f"moduller/m{i:02d}.py": "".join(
        f"def islem_{i}_{j}(x):\n    \"\"\"Yardimci donusum {i}.{j}.\"\"\"\n    return x * {j + 1} + {i}\n\n\n"
        for j in range(12)) for i in range(n)}  # fmt: skip


_UZUN = _dolgu_modulleri(40)
_UZUN["moduller/__init__.py"] = ""
_UZUN["moduller/vergi.py"] = (
    "KDV = 0.2\n\n\ndef kdv_ekle(tutar):\n    return round(tutar * KDV, 2)\n"
)
_UZUN["tests/test_vergi.py"] = (
    PYTEST_YOL
    + "from moduller.vergi import kdv_ekle\n\n\ndef test_kdv():\n    assert kdv_ekle(100) == 120\n"
)
gorev(
    id="uzun-py-cok-modul", kategori="uzun", dil="python",
    hedef="Testlerden biri basarisiz. 40'tan fazla modul var; hatali olani bul ve duzelt. Testleri degistirme.",
    kabul=["python -m pytest -q tests gecsin"],
    dosyalar=_UZUN, korunan=["tests/test_vergi.py"],
    gizli={"_gizli/test_g.py": PYTEST_YOL + "from moduller.vergi import kdv_ekle\n\n\ndef test_g():\n    assert kdv_ekle(50) == 60 and kdv_ekle(0) == 0 and kdv_ekle(10.5) == 12.6\n"},
    kontroller=[py_test("tests"), py_test("_gizli/test_g.py")],
    cozum={"moduller/vergi.py": "KDV = 0.2\n\n\ndef kdv_ekle(tutar):\n    return round(tutar * (1 + KDV), 2)\n"},
)  # fmt: skip

_BUYUK = "".join(f"def yardimci_{i}(x):\n    return (x + {i}) % 97\n\n\n" for i in range(700))
_BUYUK += "def iban_gecerli(iban: str) -> bool:\n    s = iban.replace(' ', '').upper()\n    if len(s) != 26 or not s.startswith('TR'):\n        return False\n    s = s[4:] + s[:4]\n    n = ''.join(str(int(c, 36)) for c in s)\n    return int(n) % 97 == 1\n"
gorev(
    id="uzun-py-buyuk-dosya", kategori="uzun", dil="python",
    hedef="buyuk.py dosyasinin sonundaki iban_gecerli fonksiyonu kucuk harf ve bosluklu girdide calisiyor ama 'TR' disindaki ulke kodlarini da reddetmeli, ayrica rakam olmayan karakterlerde (or. '-') ValueError firlatiyor; bu durumda False donmeli. Duzelt.",
    dosyalar={"buyuk.py": _BUYUK},
    gizli={"_gizli/test_g.py": PYTEST_YOL + d("""
        from buyuk import iban_gecerli

        def test_iban():
            assert iban_gecerli("TR33 0006 1005 1978 6457 8413 26")
            assert iban_gecerli("tr330006100519786457841326")
            assert not iban_gecerli("TR33000610051978645784132-")  # 26 karakter, rakam disi
            assert not iban_gecerli("DE89370400440532013000")
            assert not iban_gecerli("TR330006100519786457841327")
            assert not iban_gecerli("")
    """)},
    kontroller=[py_test("_gizli/test_g.py")],
    cozum={"buyuk.py": _BUYUK.replace("    s = iban.replace(' ', '').upper()\n", "    s = iban.replace(' ', '').upper()\n    if not s.isalnum():\n        return False\n")},
)  # fmt: skip

gorev(
    id="devam-py-todo", kategori="uzun", dil="python",
    hedef="TODO.md'deki plana gore calisma yarim kalmis. Kalan adimi tamamla ve TODO.md'de [x] olarak isaretle. Tamamlanmis adimlari bozma.",
    dosyalar={
        "TODO.md": "# Plan: metin araclari\n- [x] 1. kelime_say(metin) -> int\n- [x] 2. buyuk_harf_orani(metin) -> float (harf yoksa 0.0)\n- [ ] 3. en_uzun_kelime(metin) -> str (esitlikte ilk gelen; bos metinde '')\n",
        "metin.py": "def kelime_say(metin):\n    return len(metin.split())\n\n\ndef buyuk_harf_orani(metin):\n    harfler = [c for c in metin if c.isalpha()]\n    return sum(c.isupper() for c in harfler) / len(harfler) if harfler else 0.0\n",
    },
    gizli={"_gizli/test_g.py": PYTEST_YOL + d("""
        import pathlib
        from metin import buyuk_harf_orani, en_uzun_kelime, kelime_say

        def test_devam():
            assert kelime_say("a b  c") == 3 and buyuk_harf_orani("Ab") == 0.5
            assert en_uzun_kelime("bir uc iki") == "bir" and en_uzun_kelime("") == ""
            assert en_uzun_kelime("a bbb cc dddd") == "dddd"
            todo = (pathlib.Path(__file__).parent.parent / "TODO.md").read_text(encoding="utf-8")
            assert "- [x] 3." in todo and todo.count("[x]") == 3
    """)},
    kontroller=[py_test("_gizli/test_g.py")],
    cozum={
        "metin.py": "def kelime_say(metin):\n    return len(metin.split())\n\n\ndef buyuk_harf_orani(metin):\n    harfler = [c for c in metin if c.isalpha()]\n    return sum(c.isupper() for c in harfler) / len(harfler) if harfler else 0.0\n\n\ndef en_uzun_kelime(metin):\n    k = metin.split()\n    return max(k, key=len) if k else ''\n",
        "TODO.md": "# Plan: metin araclari\n- [x] 1. kelime_say(metin) -> int\n- [x] 2. buyuk_harf_orani(metin) -> float (harf yoksa 0.0)\n- [x] 3. en_uzun_kelime(metin) -> str (esitlikte ilk gelen; bos metinde '')\n",
    },
)  # fmt: skip

_TS_UZUN = "".join(
    f"export function f{i}(x: number): number {{\n  return x * {i % 7 + 1} - {i};\n}}\n\n"
    for i in range(400)
)
gorev(
    id="uzun-ts-buyuk-dosya", kategori="uzun", dil="typescript",
    hedef="src/hesaplar.ts dosyasinin sonundaki vergiDilimi fonksiyonu yanlis: 0-10000 %15, 10000-30000 %20, ustu %27 kademeli vergi hesaplanmali (her dilim yalniz kendi araligina uygulanir). Duzelt.",
    dosyalar={"src/hesaplar.ts": _TS_UZUN + "export function vergiDilimi(gelir: number): number {\n  if (gelir <= 10000) return gelir * 0.15;\n  if (gelir <= 30000) return gelir * 0.2;\n  return gelir * 0.27;\n}\n"},
    gizli={"_gizli/v.test.ts": d("""
        import { test } from "node:test";
        import assert from "node:assert/strict";
        import { vergiDilimi, f3 } from "../src/hesaplar.ts";

        test("kademeli", () => {
          assert.equal(vergiDilimi(10000), 1500);
          assert.equal(vergiDilimi(20000), 3500);
          assert.equal(vergiDilimi(40000), 8200);
          assert.equal(vergiDilimi(0), 0);
          assert.equal(f3(2), 5);
        });
    """)},
    kontroller=[node_test("_gizli/v.test.ts")],
    cozum={"src/hesaplar.ts": _TS_UZUN + "export function vergiDilimi(gelir: number): number {\n  const a = Math.min(gelir, 10000) * 0.15;\n  const b = Math.max(0, Math.min(gelir, 30000) - 10000) * 0.2;\n  const c = Math.max(0, gelir - 30000) * 0.27;\n  return Math.round((a + b + c) * 100) / 100;\n}\n"},
)  # fmt: skip

# ============================================================ 6) izin / arac hatasi toparlanma (4)
gorev(
    id="toparlanma-yanlis-yol", kategori="toparlanma", dil="python",
    hedef="src/hesap.py'deki bolme fonksiyonunda sifira bolmede ZeroDivisionError yerine None donmeli. Duzelt.",
    dosyalar={"lib/hesap.py": "def bolme(a, b):\n    return a / b\n", "README.md": "Kaynak kod lib/ altinda.\n"},
    gizli={"_gizli/test_g.py": PYTEST_YOL + "from lib.hesap import bolme\n\n\ndef test_g():\n    assert bolme(6, 3) == 2 and bolme(1, 0) is None\n"},
    kontroller=[py_test("_gizli/test_g.py")],
    cozum={"lib/hesap.py": "def bolme(a, b):\n    return None if b == 0 else a / b\n"},
)  # fmt: skip

gorev(
    id="toparlanma-hassas-dosya", kategori="toparlanma", dil="python",
    hedef="Uygulamanin varsayilan portunu 8080 yap (ayarlar.py). .env dosyasina dokunma.",
    dosyalar={
        "ayarlar.py": "import os\n\nPORT = int(os.environ.get('PORT', '5000'))\n",
        ".env": "PORT=9999\nGIZLI_ANAHTAR=sk-test-0000000000000000\n",
    },
    korunan=[".env"],
    gizli={"_gizli/test_g.py": PYTEST_YOL + "import importlib, os\n\n\ndef test_g():\n    os.environ.pop('PORT', None)\n    import ayarlar\n    importlib.reload(ayarlar)\n    assert ayarlar.PORT == 8080\n"},
    kontroller=[py_test("_gizli/test_g.py")],
    cozum={"ayarlar.py": "import os\n\nPORT = int(os.environ.get('PORT', '8080'))\n"},
)  # fmt: skip

gorev(
    id="toparlanma-olmayan-komut", kategori="toparlanma", dil="python",
    hedef="Testleri 'make test' ile calistir ve basarisiz olani duzelt.",
    dosyalar={
        "Makefile": "test:\n\tpython -m pytest -q tests\n",
        "donustur.py": "def c_to_f(c):\n    return c * 9 / 5 - 32\n",
        "tests/test_d.py": PYTEST_YOL + "from donustur import c_to_f\n\n\ndef test_d():\n    assert c_to_f(100) == 212\n",
    },
    korunan=["tests/test_d.py"],
    gizli={},
    kontroller=[py_test("tests")],
    cozum={"donustur.py": "def c_to_f(c):\n    return c * 9 / 5 + 32\n"},
)  # fmt: skip

_BOM = "﻿def selam(ad):\r\n    return 'Merhaba ' + ad + '!!'\r\n"
gorev(
    id="toparlanma-bom-crlf", kategori="toparlanma", dil="python",
    hedef="selam.py'deki selam fonksiyonu sonda iki unlem koyuyor; tek unlem olmali. Dosyanin satir sonlari (CRLF) ve kodlamasi korunmali.",
    dosyalar={"selam.py": _BOM},
    gizli={"_gizli/k.py": d("""
        import pathlib, sys
        sys.path.insert(0, ".")
        b = pathlib.Path("selam.py").read_bytes()
        from selam import selam
        ok = selam("Ada") == "Merhaba Ada!" and b"\\r\\n" in b and b.count(b"\\n") == b.count(b"\\r\\n")
        sys.exit(0 if ok else 1)
    """)},
    kontroller=[{"argv": ["{py}", "_gizli/k.py"]}],
    cozum={"selam.py": _BOM.replace("'!!'", "'!'")},
)  # fmt: skip

# ============================================================ 7) web kodu / entegrasyon (3)
gorev(
    id="web-js-form", kategori="entegrasyon", dil="javascript",
    hedef="web/form.js'deki dogrula(alanlar) fonksiyonu: e-posta 'a@b' gibi alan adsiz adresleri kabul ediyor ve telefon icin bosluklu '0532 111 22 33' bicimini reddediyor. Ikisini de duzelt (telefon: 0 ile baslayan 11 hane, bosluklar yok sayilir).",
    dosyalar={
        "web/form.js": d("""
            export function dogrula({ eposta, telefon }) {
              const hatalar = {};
              if (!/^[^@\\s]+@[^@\\s]+$/.test(eposta || "")) hatalar.eposta = "Gecersiz e-posta";
              if (!/^0\\d{10}$/.test(telefon || "")) hatalar.telefon = "Gecersiz telefon";
              return hatalar;
            }
        """),
        "web/index.html": '<form id="f"><input name="eposta"><input name="telefon"></form>\n<script type="module" src="form.js"></script>\n',
    },
    gizli={"_gizli/f.test.mjs": d("""
        import { test } from "node:test";
        import assert from "node:assert/strict";
        import { dogrula } from "../web/form.js";

        test("form", () => {
          assert.deepEqual(dogrula({ eposta: "a@b.com", telefon: "0532 111 22 33" }), {});
          assert.ok(dogrula({ eposta: "a@b", telefon: "05321112233" }).eposta);
          assert.ok(dogrula({ eposta: "a@b.com", telefon: "532 111 22 33" }).telefon);
          assert.ok(dogrula({ eposta: "a@b.com", telefon: "0532 111 22 3x" }).telefon);
        });
    """)},
    kontroller=[node_test("_gizli/f.test.mjs")],
    cozum={"web/form.js": d("""
        export function dogrula({ eposta, telefon }) {
          const hatalar = {};
          if (!/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/.test(eposta || "")) hatalar.eposta = "Gecersiz e-posta";
          if (!/^0\\d{10}$/.test((telefon || "").replace(/\\s+/g, ""))) hatalar.telefon = "Gecersiz telefon";
          return hatalar;
        }
    """)},
)  # fmt: skip

gorev(
    id="entegrasyon-py-sayfali-api", kategori="entegrasyon", dil="python",
    hedef="aktar.py, API yanitlarini (yanitlar/ klasorundeki JSON dosyalari; her yanitta 'sonraki' alani bir sonraki dosyanin adini verir, son sayfada null) okuyup cikti.csv yaziyor ama yalniz ilk sayfayi aliyor. Tum sayfalari aktaracak sekilde duzelt.",
    dosyalar={
        "aktar.py": d("""
            import csv, json, pathlib

            def aktar(ilk="sayfa1.json", hedef="cikti.csv"):
                kok = pathlib.Path("yanitlar")
                veri = json.loads((kok / ilk).read_text(encoding="utf-8"))
                satirlar = veri["kayitlar"]
                with open(hedef, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["id", "ad"])
                    w.writeheader()
                    w.writerows(satirlar)
                return len(satirlar)

            if __name__ == "__main__":
                print(aktar())
        """),
        "yanitlar/sayfa1.json": '{"kayitlar": [{"id": 1, "ad": "a"}, {"id": 2, "ad": "b"}], "sonraki": "sayfa2.json"}',
        "yanitlar/sayfa2.json": '{"kayitlar": [{"id": 3, "ad": "c"}], "sonraki": "sayfa3.json"}',
        "yanitlar/sayfa3.json": '{"kayitlar": [{"id": 4, "ad": "d"}], "sonraki": null}',
    },
    gizli={"_gizli/test_g.py": PYTEST_YOL + d("""
        import csv, os, pathlib
        KOK = pathlib.Path(__file__).parent.parent

        def test_g():
            os.chdir(KOK)
            from aktar import aktar
            assert aktar() == 4
            with open("cikti.csv", encoding="utf-8") as f:
                assert [r["id"] for r in csv.DictReader(f)] == ["1", "2", "3", "4"]
    """)},
    kontroller=[py_test("_gizli/test_g.py")],
    cozum={"aktar.py": d("""
        import csv, json, pathlib

        def aktar(ilk="sayfa1.json", hedef="cikti.csv"):
            kok = pathlib.Path("yanitlar")
            satirlar, sayfa = [], ilk
            while sayfa:
                veri = json.loads((kok / sayfa).read_text(encoding="utf-8"))
                satirlar += veri["kayitlar"]
                sayfa = veri.get("sonraki")
            with open(hedef, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["id", "ad"])
                w.writeheader()
                w.writerows(satirlar)
            return len(satirlar)

        if __name__ == "__main__":
            print(aktar())
    """)},
)  # fmt: skip

gorev(
    id="entegrasyon-ts-tekrar-dene", kategori="entegrasyon", dil="typescript",
    hedef="src/istemci.ts'deki getirTekrarli, 503 ve 429 yanitlarinda tekrar denemiyor (yalniz ag hatasinda deniyor). 5xx ve 429'da en fazla 'deneme' kez tekrar etsin; 4xx'te (429 haric) hemen yanit dondursun.",
    dosyalar={"src/istemci.ts": d("""
        type Getir = (url: string) => Promise<{ status: number; body: string }>;

        export async function getirTekrarli(getir: Getir, url: string, deneme = 3) {
          let son: unknown;
          for (let i = 0; i < deneme; i++) {
            try {
              return await getir(url);
            } catch (e) {
              son = e;
            }
          }
          throw son;
        }
    """)},
    gizli={"_gizli/i.test.ts": d("""
        import { test } from "node:test";
        import assert from "node:assert/strict";
        import { getirTekrarli } from "../src/istemci.ts";

        const sahte = (kodlar: number[]) => {
          let n = 0;
          const f = async () => ({ status: kodlar[Math.min(n++, kodlar.length - 1)], body: "" });
          return { f, sayi: () => n };
        };

        test("tekrar", async () => {
          let s = sahte([503, 429, 200]);
          assert.equal((await getirTekrarli(s.f, "u", 3)).status, 200);
          assert.equal(s.sayi(), 3);
          s = sahte([404, 200]);
          assert.equal((await getirTekrarli(s.f, "u", 3)).status, 404);
          assert.equal(s.sayi(), 1);
          s = sahte([500, 500, 500, 500]);
          assert.equal((await getirTekrarli(s.f, "u", 3)).status, 500);
          assert.equal(s.sayi(), 3);
        });
    """)},
    kontroller=[node_test("_gizli/i.test.ts")],
    cozum={"src/istemci.ts": d("""
        type Getir = (url: string) => Promise<{ status: number; body: string }>;

        export async function getirTekrarli(getir: Getir, url: string, deneme = 3) {
          let son: unknown;
          let yanit: { status: number; body: string } | undefined;
          for (let i = 0; i < deneme; i++) {
            try {
              yanit = await getir(url);
              if (yanit.status < 500 && yanit.status !== 429) return yanit;
            } catch (e) {
              son = e;
            }
          }
          if (yanit) return yanit;
          throw son;
        }
    """)},
)  # fmt: skip

assert len(G) == 30, len(G)
assert len({g["id"] for g in G}) == 30
