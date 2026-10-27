#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify a built EPUB against every failure mode hit in practice.

Checks (each one corresponds to a real bug that shipped at least once):
  1. mimetype is the first zip entry and is stored uncompressed.
  2. OEBPS paths in container.xml / OPF actually exist.
  3. Every <img src> in OEBPS/text/*.xhtml resolves relative to that file.
     (The classic bug: `images/x.jpg` instead of `../images/x.jpg`,
      which makes cover art silently fail to load while icons still work.)
  4. Illustrations are within the pixel/size budget.
  5. Chapter icons are exactly square, RGBA, and consistent.
  6. The required LXGW WenKai Mono font is embedded and referenced.
  7. No leftover advertisement strings.
  8. Chapter markup keeps icon and title in separate top-level blocks.

Usage:
    python verify_epub.py BOOK.epub
    python verify_epub.py BOOK.epub --max-image-side 720 --icon-size 128
Exit code 0 = all checks passed, 1 = at least one failure.
"""

from __future__ import annotations

import argparse
import io
import posixpath
import re
import sys
import zipfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.stderr.write("ERROR: Pillow is required. Install with: pip install Pillow\n")
    raise SystemExit(2)

AD_NEEDLES = ["soushu2024", "soushu2025", "（本章完）"]
IMG_SRC_RE = re.compile(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.notes: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        if ok:
            self.notes.append(f"  PASS  {label}")
        else:
            self.failures.append(f"  FAIL  {label}" + (f"  -- {detail}" if detail else ""))
        return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a built EPUB.")
    ap.add_argument("epub")
    ap.add_argument("--max-image-side", type=int, default=720)
    ap.add_argument("--max-image-bytes", type=int, default=200_000)
    ap.add_argument("--icon-size", type=int, default=128)
    args = ap.parse_args()

    path = Path(args.epub).expanduser().resolve()
    if not path.is_file():
        sys.stderr.write(f"ERROR: not found: {path}\n")
        return 2

    r = Result()
    z = zipfile.ZipFile(path)
    names = z.namelist()
    nameset = set(names)

    # 1. mimetype first + stored ------------------------------------------
    first = names[0] if names else ""
    info = z.getinfo(first) if first else None
    r.check(first == "mimetype", "mimetype is first zip entry", f"first={first!r}")
    if info:
        r.check(info.compress_type == zipfile.ZIP_STORED, "mimetype is stored (uncompressed)",
                f"compress_type={info.compress_type}")
    if "mimetype" in nameset:
        r.check(z.read("mimetype") == b"application/epub+zip", "mimetype content correct")

    # 2. container.xml + OPF ----------------------------------------------
    r.check("META-INF/container.xml" in nameset, "META-INF/container.xml present")
    opfs = [n for n in names if n.endswith(".opf")]
    r.check(len(opfs) == 1, "exactly one OPF", f"found={opfs}")
    opf_dir = posixpath.dirname(opfs[0]) if opfs else ""
    if opfs:
        opf_text = z.read(opfs[0]).decode("utf-8", "ignore")
        manifest = dict(re.findall(r'<item\b[^>]*id="([^"]+)"[^>]*href="([^"]+)"', opf_text))
        missing = [h for h in manifest.values() if posixpath.normpath(posixpath.join(opf_dir, h)) not in nameset]
        r.check(not missing, "all manifest items exist in zip", f"missing={missing[:5]}")
        r.check('properties="cover-image"' in opf_text, "OPF declares cover-image")
        r.check('properties="nav"' not in opf_text and not any(n.endswith("nav.xhtml") for n in names),
                "no visible EPUB 3 navigation document")
        r.check('toc="ncx"' in opf_text and any(n.endswith("toc.ncx") for n in names), "EPUB 2 NCX is linked from spine")
        r.check("<dc:title>" in opf_text and "<dc:language>" in opf_text,
                "title and language metadata are present")

    # 3. relative image paths resolve -------------------------------------
    bad_src: list[str] = []
    xhtml_files = [n for n in names if n.endswith((".xhtml", ".html"))]
    abs_src = 0
    for n in xhtml_files:
        text = z.read(n).decode("utf-8", "ignore")
        base = posixpath.dirname(n)
        for src in IMG_SRC_RE.findall(text):
            if src.startswith(("http://", "https://", "data:")):
                continue
            if src.startswith("/"):
                abs_src += 1
                bad_src.append(f"{n}: absolute {src}")
                continue
            resolved = posixpath.normpath(posixpath.join(base, src))
            if resolved not in nameset:
                bad_src.append(f"{n}: {src} -> {resolved} MISSING")
    r.check(not bad_src, "every <img src> resolves inside the EPUB", "; ".join(bad_src[:6]))
    r.check(abs_src == 0, "no root-absolute image src")

    text_pages = [n for n in xhtml_files if "/text/" in n]
    r.check(bool(text_pages), "chapter/text pages exist", f"count={len(text_pages)}")

    # 4. illustration budget ----------------------------------------------
    heavy: list[str] = []
    big: list[str] = []
    for n in names:
        low = n.lower()
        if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
            data = z.read(n)
            if "icon-" in posixpath.basename(low):
                continue
            if len(data) > args.max_image_bytes:
                heavy.append(f"{n} {len(data)}B")
            try:
                im = Image.open(io.BytesIO(data))
                if max(im.size) > args.max_image_side:
                    big.append(f"{n} {im.size}")
            except Exception as e:  # noqa: BLE001
                r.failures.append(f"  FAIL  unreadable image {n}: {e}")
    r.check(not heavy, f"illustrations <= {args.max_image_bytes} bytes", "; ".join(heavy[:5]))
    r.check(not big, f"illustrations longest side <= {args.max_image_side}px", "; ".join(big[:5]))

    # 5. icon normalisation ------------------------------------------------
    icons = [n for n in names if posixpath.basename(n).startswith("icon-") and n.lower().endswith(".png")]
    if icons:
        wrong: list[str] = []
        modes: set[str] = set()
        for n in icons:
            im = Image.open(io.BytesIO(z.read(n)))
            modes.add(im.mode)
            if im.size != (args.icon_size, args.icon_size):
                wrong.append(f"{n} {im.size}")
        r.check(not wrong, f"all icons are exactly {args.icon_size}x{args.icon_size}", "; ".join(wrong[:5]))
        r.check(modes == {"RGBA"}, "all icons carry an alpha channel (RGBA)", f"modes={sorted(modes)}")
        r.notes.append(f"  INFO  icon count = {len(icons)}")
    else:
        r.notes.append("  INFO  no chapter icons present (skipped)")

    # 6. no embedded fonts -------------------------------------------------
    fonts = [n for n in names if n.lower().endswith((".ttf", ".otf", ".woff", ".woff2", ".ttc"))]
    r.check(any(posixpath.basename(n) == "LXGWWenKaiMono-Regular.ttf" for n in fonts),
            "LXGW WenKai Mono font is embedded", "; ".join(fonts[:5]))
    css_files = [n for n in names if n.endswith(".css")]
    css_text = "".join(z.read(n).decode("utf-8", "ignore") for n in css_files)
    r.check("LXGW WenKai Mono" in css_text and "../fonts/LXGWWenKaiMono-Regular.ttf" in css_text,
            "CSS references the required font")

    # 7. advertisement residue --------------------------------------------
    residue: list[str] = []
    for n in text_pages:
        text = z.read(n).decode("utf-8", "ignore")
        for needle in AD_NEEDLES:
            if needle in text:
                residue.append(f"{n}: {needle}")
    r.check(not residue, "no advertisement residue", "; ".join(residue[:5]))

    # 8. chapter heading markup -------------------------------------------
    chapters = [n for n in text_pages if posixpath.basename(n).startswith("ch")]
    if chapters and icons:
        broken: list[str] = []
        for n in chapters:
            text = z.read(n).decode("utf-8", "ignore")
            if "chapter-icon" not in text or "chapter-title" not in text or "<h1><img" in text:
                broken.append(n)
        r.check(not broken, "chapter icon + title use separate block elements",
                f"{len(broken)} pages missing, e.g. {broken[:3]}")
        r.notes.append(f"  INFO  chapter count = {len(chapters)}")

    # report -----------------------------------------------------------------
    print(f"EPUB   : {path}")
    print(f"size   : {path.stat().st_size:,} bytes")
    print(f"entries: {len(names)}")
    for line in r.notes:
        print(line)
    if r.failures:
        print()
        for line in r.failures:
            print(line)
        print(f"\nRESULT : FAILED ({len(r.failures)} check(s))")
        return 1
    print(f"\nRESULT : OK ({len(r.notes)} check(s) passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
