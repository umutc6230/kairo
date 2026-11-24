"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const vscode = require("vscode");

function baglantiOku(cfg) {
  const kok = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || "";
  const adaylar = [
    String(cfg.get("baglantiDosyasi", "") || "").trim(),
    process.env.KAIRO_VERI_DIZINI ? path.join(process.env.KAIRO_VERI_DIZINI, "baglanti.json") : "",
    path.join(os.homedir(), "Desktop", "Portable Programlar", "Kairo", "data", "baglanti.json"),
    kok ? path.join(kok, "data", "baglanti.json") : "",
  ].filter(Boolean);
  for (const yol of adaylar) {
    try {
      if (fs.existsSync(yol)) {
        const d = JSON.parse(fs.readFileSync(yol, "utf8"));
        if (d && d.url) return d;
      }
    } catch {
      // okunamayan/yarim dosyayi atla
    }
  }
  return null;
}

function ayarlar() {
  const cfg = vscode.workspace.getConfiguration("kairo");
  const bag = baglantiOku(cfg);
  const urlInsp = cfg.inspect ? cfg.inspect("url") : null;
  const ozelUrl = urlInsp && (urlInsp.globalValue || urlInsp.workspaceValue);
  const hamUrl = ozelUrl || (bag && bag.url) || cfg.get("url", "http://127.0.0.1:8765");
  const url = String(hamUrl || "").replace(/\/+$/, "");
  const anahtar = String(cfg.get("oturumAnahtari", "") || (bag && bag.oturum_anahtari) || "").trim();
  return { url, anahtar };
}

async function baglamGonder() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("Kairo: Acik bir dosya yok.");
    return;
  }
  const { url, anahtar } = ayarlar();
  const doc = editor.document;
  const sel = editor.selection;
  const secim = sel && !sel.isEmpty ? doc.getText(sel).slice(0, 20000) : "";
  const satirBas = (sel ? sel.start.line : 0) + 1;
  const satirBit = (sel ? sel.end.line : 0) + 1;
  const kok = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || "";

  const headers = { "Content-Type": "application/json" };
  if (anahtar) headers["X-YAS-Oturum"] = anahtar;

  try {
    const r = await fetch(`${url}/api/editor/baglam`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        dosya: doc.uri.fsPath,
        satir_baslangic: satirBas,
        satir_bitis: satirBit,
        secim,
        proje_kok: kok,
        kaynak: "vscode",
      }),
    });
    if (!r.ok) {
      const hata = await r.text().catch(() => `HTTP ${r.status}`);
      vscode.window.showErrorMessage(`Kairo baglam gonderilemedi: ${hata.slice(0, 200)}`);
      return;
    }
    vscode.window.setStatusBarMessage(
      `Kairo: ${doc.fileName} (L${satirBas}-L${satirBit}) gonderildi.`,
      3000
    );
  } catch (err) {
    vscode.window.showErrorMessage(`Kairo sunucusuna baglanilamadi: ${err.message}`);
  }
}

async function kairoAc() {
  const { url } = ayarlar();
  await vscode.env.openExternal(vscode.Uri.parse(url));
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("kairo.baglamGonder", baglamGonder),
    vscode.commands.registerCommand("kairo.ac", kairoAc)
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
