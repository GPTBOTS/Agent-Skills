from __future__ import annotations

import zipfile
from pathlib import Path

_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def write_zip(entries: list[tuple[str, bytes]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(entries, key=lambda e: e[0])
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in items:
            zi = zipfile.ZipInfo(arcname, date_time=_FIXED_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, data)
