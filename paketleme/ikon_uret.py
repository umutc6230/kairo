"""Kairo baykus ikonunu (app/web/kairo.svg ile ayni piksel izgarasi) .ico ve .png olarak uretir.

Calistir: python paketleme/ikon_uret.py  -> paketleme/ikon.ico, ikon.png, app/web/kairo.ico
"""

from pathlib import Path

from PIL import Image, ImageDraw

KOK = Path(__file__).resolve().parent.parent
TURKUAZ, KREM, KOYU, SARI = "#2bb6a8", "#f4f1e8", "#1f1f1e", "#f2b134"
# (x, y, g, y, renk) - kairo.svg ile ayni 13x10 izgara
PIKSELLER = [
    (2, 0, 1, 1, TURKUAZ), (10, 0, 1, 1, TURKUAZ), (2, 1, 9, 8, TURKUAZ),
    (1, 4, 1, 3, TURKUAZ), (11, 4, 1, 3, TURKUAZ),
    (3, 2, 3, 3, KREM), (7, 2, 3, 3, KREM), (4, 3, 1, 1, KOYU), (8, 3, 1, 1, KOYU),
    (6, 5, 1, 1, SARI), (4, 9, 2, 1, SARI), (7, 9, 2, 1, SARI),
]  # fmt: skip


def ciz(boyut: int) -> Image.Image:
    img = Image.new("RGBA", (boyut, boyut), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    birim = boyut // 14  # 13 genislik + kenar payi; kare tuval
    ox = (boyut - 13 * birim) // 2
    oy = (boyut - 10 * birim) // 2
    for x, y, g, h, renk in PIKSELLER:
        d.rectangle([ox + x * birim, oy + y * birim, ox + (x + g) * birim - 1,
                     oy + (y + h) * birim - 1], fill=renk)  # fmt: skip
    return img


if __name__ == "__main__":
    buyuk = ciz(256)
    buyuk.save(KOK / "paketleme" / "ikon.png")
    boyutlar = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    for hedef in (KOK / "paketleme" / "ikon.ico", KOK / "app" / "web" / "kairo.ico"):
        buyuk.save(hedef, sizes=boyutlar)
    print("ikon uretildi")
