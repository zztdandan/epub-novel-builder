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
  6. Navigation: exactly one manifest item with properties="nav", the document
     exists, and it is NOT in the spine (so no reader renders it as a page),
     plus a linked toc.ncx with a non-empty navMap for EPUB 2 reading systems.
  7. Font policy: either no font at all and no font-family override in the CSS,
     or every embedded font is declared in the manifest with a correct media
     type and referenced from the stylesheet.
  8. No leftover advertisement strings.
  9. Chapter markup keeps icon and title in separate top-level blocks.

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
FONT_MEDIA_TYPES = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


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

    opf_text = ""
    items: list[str] = []

    def attr(tag: str, name: str) -> str:
        m = re.search(rf'\b{name}="([^"]*)"', tag)
        return m.group(1) if m else ""

    if opfs:
        opf_text = z.read(opfs[0]).decode("utf-8", "ignore")
        items = re.findall(r"<item\b[^>]*/>", opf_text)
        manifest = dict(re.findall(r'<item\b[^>]*id="([^"]+)"[^>]*href="([^"]+)"', opf_text))
        missing = [h for h in manifest.values() if posixpath.normpath(posixpath.join(opf_dir, h)) not in nameset]
        r.check(not missing, "all manifest items exist in zip", f"missing={missing[:5]}")
        r.check('properties="cover-image"' in opf_text, "OPF declares cover-image")

        # navigation: EPUB 3 nav document (required) + legacy NCX (both kept)
        nav_items = [t for t in items if "nav" in attr(t, "properties").split()]
        r.check(len(nav_items) == 1, 'exactly one manifest item declares properties="nav"',
                f"found={len(nav_items)}")
        nav_path = ""
        if len(nav_items) == 1:
            nav_path = posixpath.normpath(posixpath.join(opf_dir, attr(nav_items[0], "href")))
            r.check(nav_path in nameset, "navigation document exists in the archive", nav_path)
            spine_ids = re.findall(r'<itemref\b[^>]*idref="([^"]+)"', opf_text)
            r.check(attr(nav_items[0], "id") not in spine_ids,
                    "navigation document stays out of the spine (no visible TOC page)")

        r.check('toc="ncx"' in opf_text and any(n.endswith("toc.ncx") for n in names),
                "legacy NCX is linked from the spine", "kept for EPUB 2 reading systems")
        if any(n.endswith("toc.ncx") for n in names):
            ncx_path = [n for n in names if n.endswith("toc.ncx")][0]
            ncx_text = z.read(ncx_path).decode("utf-8", "ignore")
            r.check("<navPoint" in ncx_text, "NCX contains navigation points")

        if nav_path and nav_path in nameset:
            nav_text = z.read(nav_path).decode("utf-8", "ignore")
            r.check('epub:type="toc"' in nav_text, "nav document exposes a toc nav")
            r.check('xmlns:epub="http://www.idpf.org/2007/ops"' in nav_text,
                    "nav document declares the epub: namespace")
            nav_base = posixpath.dirname(nav_path)
            dead = [
                h for h in re.findall(r'<a\b[^>]*href="([^"]+)"', nav_text)
                if not h.startswith(("http://", "https://", "mailto:"))
                and posixpath.normpath(posixpath.join(nav_base, h)) not in nameset
            ]
            r.check(not dead, "every nav link resolves inside the EPUB", "; ".join(dead[:5]))
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

    # 7. font policy ---------------------------------------------------------
    fonts = [n for n in names if n.lower().endswith((".ttf", ".otf", ".woff", ".woff2"))]
    css_files = [n for n in names if n.endswith(".css")]
    css_text = "".join(z.read(n).decode("utf-8", "ignore") for n in css_files)
    if fonts:
        r.check("@font-face" in css_text, "CSS declares @font-face for the embedded font")
        unreferenced = [
            n for n in fonts
            if f"../fonts/{posixpath.basename(n)}" not in css_text
        ]
        r.check(not unreferenced, "every embedded font is referenced from CSS",
                "; ".join(posixpath.basename(n) for n in unreferenced[:5]))
        wrong_media = []
        for n in fonts:
            expected = FONT_MEDIA_TYPES.get(posixpath.splitext(n)[1].lower())
            declared = [
                attr(t, "media-type") for t in items
                if posixpath.basename(attr(t, "href")) == posixpath.basename(n)
            ]
            if expected and declared and declared[0] != expected:
                wrong_media.append(f"{n}: {declared[0]} != {expected}")
        r.check(not wrong_media, "embedded font has the right EPUB media-type",
                "; ".join(wrong_media[:5]))
        r.notes.append(f"  INFO  embedded font = {[posixpath.basename(n) for n in fonts]}")
    else:
        r.check("@font-face" not in css_text, "no @font-face without an embedded font")
        r.check("font-family" not in css_text,
                "stylesheet does not override the reader's font",
                "default policy: reader typography wins")
        r.notes.append("  INFO  no embedded font (reader default typography)")

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
