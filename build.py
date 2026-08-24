"""Build the self-contained frontend with a read-only fallback snapshot."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app_data import static_snapshot

ROOT = Path(__file__).resolve().parent
TOKEN = "/*__STATIC_SNAPSHOT__*/"
CSS_TOKEN = "/*__PREMIUM_CSS__*/"


def main() -> int:
    template = (ROOT / "page" / "template.html").read_text(encoding="utf-8")
    if template.count(TOKEN) != 1:
        print(f"template must contain {TOKEN} exactly once, found {template.count(TOKEN)}")
        return 1
    if template.count(CSS_TOKEN) != 1:
        print(f"template must contain {CSS_TOKEN} exactly once, found {template.count(CSS_TOKEN)}")
        return 1
    premium_css = (ROOT / "page" / "premium.css").read_text(encoding="utf-8")
    snapshot = static_snapshot()

    missing = [d["id"] for d in snapshot["knowledge"] if not d.get("provenance")]
    if missing:
        print(f"refusing to build: documents without a provenance stamp: {missing}")
        return 1

    payload = json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/")
    rendered = template.replace(CSS_TOKEN, premium_css).replace(TOKEN, payload)
    (ROOT / "index.html").write_text(rendered, encoding="utf-8")
    print(f"wrote index.html ({(ROOT / 'index.html').stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
