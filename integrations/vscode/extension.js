"use strict";

const vscode = require("vscode");

function ayarlar() {
  const cfg = vscode.workspace.getConfiguration("kairo");
  const url = String(cfg.get("url", "http://127.0.0.1:8765") || "").replace(/\/+$/, "");
  const anahtar = String(cfg.get("oturumAnahtari", "") || "").trim();
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
