#!/usr/bin/env python3
"""Guard the design system: every runtime tokens.css must match the canonical
copy byte-for-byte, and the v3 layer must not introduce hard-coded hex colors.

运行时副本清单（2026-10-24 起）：
- web/library/tokens.css        页声
- web/private-radio/tokens.css  私台
- web/tokens.css                选题台（workbench.html 引用）
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANON = ROOT / "design-system" / "tokens.css"
RUNTIMES = [
    ROOT / "web" / "library" / "tokens.css",
    ROOT / "web" / "private-radio" / "tokens.css",
    ROOT / "web" / "tokens.css",
]
V3 = ROOT / "web" / "library" / "workspace-v3.css"
V4 = ROOT / "web" / "library" / "studio-next.css"
V5 = ROOT / "web" / "library" / "experience.css"
V6 = ROOT / "web" / "library" / "neon.css"
ALLOW = {"#fff", "#ffffff"}  # only inside SVG data URIs, never text colors


def main() -> int:
    errors = []
    if not CANON.is_file():
        errors.append("canonical design-system/tokens.css missing")
    else:
        canon_bytes = CANON.read_bytes()
        for rt in RUNTIMES:
            rel = rt.relative_to(ROOT)
            if not rt.is_file():
                errors.append(f"{rel} missing (runtime copy of canonical tokens)")
            elif rt.read_bytes() != canon_bytes:
                errors.append(
                    f"{rel} drifted from design-system/tokens.css; "
                    f"run: cp design-system/tokens.css {rel}"
                )

    neon_canon = ROOT / 'design-system' / 'neon-tokens.css'
    neon_runtime = ROOT / 'web' / 'library' / 'neon-tokens.css'
    if neon_canon.read_bytes() != neon_runtime.read_bytes():
        errors.append('neon-tokens.css drifted from its project canonical copy')
    for sheet in (V3, V4, V5, V6, *(ROOT / "web" / "library" / name for name in ("griffin.css", "shell.css", "knowledge-refinement.css", "player-refinement.css"))):
        if not sheet.is_file():
            continue
        text = sheet.read_text(encoding="utf-8")
        hexes = [h for h in re.findall(r"(?<![\w-])#[0-9a-fA-F]{3,8}(?![\w-])", text) if h.lower() not in ALLOW]
        if hexes:
            errors.append(f"{sheet.name} contains hard-coded colors: {sorted(set(hexes))}")

    if errors:
        for e in errors:
            print(f"[x] {e}")
        return 1
    print(f"[ok] tokens in sync ({len(RUNTIMES)} runtime copies); no hard-coded colors in active sheets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
