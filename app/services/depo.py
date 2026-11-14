"""JSON dosya yardimcilari: atomik yazim (yarim dosya kalmaz) ve guvenli okuma."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger


def json_yaz(yol: Path, veri: Any) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    fd, gecici = tempfile.mkstemp(dir=yol.parent, prefix=f".{yol.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=1)
        os.replace(gecici, yol)
    except BaseException:
        Path(gecici).unlink(missing_ok=True)
        raise


def json_oku(yol: Path, varsayilan: Any = None) -> Any:
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return varsayilan
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("Bozuk JSON atlandi: {} ({})", yol, e)
        return varsayilan


def klasor_sil(yol: Path) -> None:
    """Klasoru salt okunur dosyalariyla birlikte siler. Windows'ta git paket dosyalari salt
    okunurdur; duz rmtree(ignore_errors=True) onlari sessizce birakiyordu (karantina birikti)."""
    import shutil
    import stat

    def yazilabilir_yap(islev, p, _hata) -> None:
        os.chmod(p, stat.S_IWRITE)
        islev(p)

    if yol.exists():
        shutil.rmtree(yol, onexc=yazilabilir_yap)
