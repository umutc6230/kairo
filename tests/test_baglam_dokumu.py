async def test_baglam_dokumu_parcalari_toplar(istemci):
    """Sag panel baglam dokumu: mesajlar disinda sistem, talimat ve araclar da sayilir."""
    oid = (await istemci.post("/api/oturumlar")).json()["id"]
    await istemci.put("/api/talimatlar", json={"metin": "Her zaman kisa cevap ver. " * 20})
    b = (await istemci.get(f"/api/oturumlar/{oid}/baglam")).json()
    kalem = {k["tur"]: k for k in b["kalemler"]}
    assert kalem["mesaj"]["token"] == 0
    assert kalem["talimat"]["token"] > 0  # KAIRO.md sayildi
    assert b["kullanilan"] == sum(k["token"] for k in b["kalemler"])
    assert b["bos"] == max(0, b["boyut"] - b["kullanilan"])
    assert all(k["token"] > 0 for k in b["kalemler"] if k["tur"] != "mesaj")  # bos kalem yok
