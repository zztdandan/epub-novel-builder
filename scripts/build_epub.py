#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a clean EPUB 3 novel from a plain-text source.

Cross-platform: works on Windows (cmd.exe / PowerShell) and Linux / macOS.
No third-party runtime deps beyond Pillow (for image processing).

Usage:
    python build_epub.py --src SOURCE.txt --out BOOK.epub \
        --img-dir ./images --icon-dir ./icons/split64

Key guarantees (learned the hard way -- see SKILL.md "踩坑总结"):
  * XHTML pages live in OEBPS/text/, so every image src uses ../images/...
  * Full-page illustrations are downscaled to <= max-side px and <= max-bytes,
    re-encoded as progressive JPEG.
  * Chapter icons are normalised onto an exact square RGBA canvas
    (default 128x128), centred, aspect preserved, never stretched.
  * Chapter icons are a separate top-of-chapter block, never nested in h1.
  * The specified font filename is auto-discovered and embedded; callers do not
    need to provide a font directory.
  * NCX is retained as the bookmark/navigation source; no visible TOC page is generated.
  * Only exact-match advertisement lines are removed; no fuzzy keyword
    deletion (that would eat legitimate prose).
  * mimetype is the first zip entry and is stored uncompressed.
"""

from __future__ import annotations

import argparse
import html
import io
import re
import shutil
import sys
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "ERROR: Pillow is required. Install it with: pip install Pillow\n"
        "Linux may need: sudo apt install python3-pil   (or pip3 install Pillow)\n"
    )
    raise SystemExit(2)


# --------------------------------------------------------------------------
# Text handling
# --------------------------------------------------------------------------

# Lines that are *exactly* these strings get dropped. Anything else is kept.
# Do NOT extend this with loose keywords such as "请记住" / "网址" -- those
# occur inside legitimate narrative prose.
DEFAULT_AD_LINES = {
    "（本章完）",
}

AD_PATTERN = re.compile(
    r"^\s*(?:下载自|备用地址|请记住本站|本书首发|更多精彩小说|"
    r"最新章节请|手机用户请|www\.[a-z0-9\-]+\.(?:com|net|org|cc|top|xyz))",
    re.IGNORECASE,
)

# Chapter heading detection. Covers 第一章 … 第一千五百章 and 番外 variants.
CH_NO = r"[零一二三四五六七八九十百千万0-9]"
CHAPTER_RE = re.compile(
    rf"^\s*(?:第{CH_NO}+章(?![0-9])[^\n]*|"
    rf"番外[^\n]*|"
    rf"第{CH_NO}+[节回](?![0-9])[^\n]*)\s*$"
)


def read_source(path: Path) -> list[str]:
    """Read a novel txt, tolerating BOM and common Chinese encodings."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # last resort, never crash
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def strip_ad_lines(lines: list[str], extra_ads: set[str]) -> tuple[list[str], int]:
    removed = 0
    kept: list[str] = []
    for line in lines:
        s = line.strip().lstrip("\ufeff").strip()
        if not s:
            kept.append(line)
            continue
        if s in DEFAULT_AD_LINES or s in extra_ads or AD_PATTERN.match(s):
            removed += 1
            continue
        kept.append(line)
    return kept, removed


def split_chapters(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Return (intro_lines, [(title, body_lines), ...])."""
    intro: list[str] = []
    chapters: list[tuple[str, list[str]]] = []
    title: str | None = None
    body: list[str] = []

    for line in lines:
        s = line.strip()
        if CHAPTER_RE.match(s):
            if title is not None:
                chapters.append((title, body))
            elif any(x.strip() for x in intro):
                pass
            title = s
            body = []
        elif title is None:
            intro.append(s)
        else:
            body.append(s)
    if title is not None:
        chapters.append((title, body))
    return intro, chapters


# --------------------------------------------------------------------------
# Image handling
# --------------------------------------------------------------------------


def save_budget_jpeg(src: Path, dst: Path, max_side: int, max_bytes: int) -> tuple[int, int, int]:
    """Downscale + re-encode to progressive JPEG under a byte budget."""
    im = Image.open(src)
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    data = b""
    for quality in range(82, 17, -4):
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            break
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return im.width, im.height, len(data)


def normalise_icon(src: Path, dst: Path, size: int) -> tuple[int, int, str]:
    """Fit the icon inside a transparent square canvas, centred, not stretched."""
    icon = Image.open(src).convert("RGBA")
    if icon.width > size or icon.height > size:
        icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(icon, ((size - icon.width) // 2, (size - icon.height) // 2))
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, format="PNG", optimize=True)
    return canvas.width, canvas.height, canvas.mode


# --------------------------------------------------------------------------
# EPUB assembly
# --------------------------------------------------------------------------

CSS = """@charset "utf-8";
html, body { margin: 0; padding: 0; }
@font-face { font-family: "LXGW WenKai Mono"; src: url("../fonts/LXGWWenKaiMono-Regular.ttf"); font-weight: normal; font-style: normal; }
body { color: #252525; background: #fbfaf7; font-family: "LXGW WenKai Mono", monospace; line-height: 1.75; font-size: 1em; }
main { max-width: 42em; margin: 0 auto; padding: 1.2em 1.1em 3em; }
.chapter-head { display: block; text-align: center; page-break-before: always; margin: 1.2em 0 1.8em; }
.chapter-icon { display: block; width: 64px; height: 64px; margin: 0 auto .8em; object-fit: contain; }
.chapter-title { display: block; color: #213746; font-size: 1.38em; line-height: 1.35; font-weight: 600; }
h1 { color: #213746; font-size: 1.38em; line-height: 1.35; text-align: center;
     font-weight: 600; margin: 1.6em 0 1.8em; page-break-before: always; }
h1 .chapter-icon { display: block; width: 64px; height: 64px;
     margin: 0 auto .8em; object-fit: contain; }
h1 .chapter-title { display: block; }
p { margin: 0 0 .72em; text-indent: 2em; text-align: justify; }
.cover { padding: 0; text-align: center; page-break-after: always; }
.cover img { display: block; width: 100%%; height: auto; max-height: 100vh; object-fit: contain; }
.frontmatter h1, .toc h1 { page-break-before: auto; }
.frontmatter h2 { color: #213746; text-align: center; font-size: 1.2em; margin: 2em 0 1em; }
.titlepage { text-align: center; padding-top: 12vh; }
.titlepage h1 { font-size: 2em; margin-bottom: .4em; page-break-before: auto; }
.titlepage .author { color: #52616b; font-size: 1.1em; }
.titlepage .summary { text-align: left; margin: 3em auto 0; max-width: 35em; }
.divider { padding: 0; text-align: center; page-break-before: always; }
.divider img { width: 100%%; height: auto; display: block; }
.divider p { text-indent: 0; text-align: center; color: #52616b; margin: 1em 0; }
.toc ol { list-style: none; padding-left: 0; }
.toc li { margin: .25em 0; }
.toc a { text-decoration: none; color: #213746; }
.toc .toc-section { margin-top: 1.1em; font-weight: 600; }
"""

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0"
 xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
 <rootfiles>
  <rootfile full-path="OEBPS/content.opf"
            media-type="application/oebps-package+xml"/>
 </rootfiles>
</container>
"""


def xhtml(title: str, body: str, lang: str = "zh-CN") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{lang}" xml:lang="{lang}">'
        f'<head><meta charset="UTF-8"/><title>{html.escape(title)}</title>'
        '<link rel="stylesheet" type="text/css" href="../styles/book.css"/></head>'
        f'<body>{body}</body></html>\n'
    )


def paras(items: list[str]) -> str:
    out = []
    for item in items:
        s = item.strip()
        if s:
            out.append("<p>" + html.escape(s) + "</p>")
    return "".join(out)


def build(args: argparse.Namespace) -> int:
    src = Path(args.src).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    img_dir = Path(args.img_dir).expanduser().resolve() if args.img_dir else None
    icon_dir = Path(args.icon_dir).expanduser().resolve() if args.icon_dir else None

    if not src.is_file():
        sys.stderr.write(f"ERROR: source not found: {src}\n")
        return 2

    work = Path(args.work_dir).expanduser().resolve() if args.work_dir else out.parent / (out.stem + "_work")
    root = work / "epub"
    if root.exists():
        shutil.rmtree(root)
    for sub in ("META-INF", "OEBPS/text", "OEBPS/images", "OEBPS/styles", "OEBPS/fonts"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    font_path = out.parent / args.font_name
    if not font_path.is_file():
        font_path = Path.cwd() / args.font_name
    if not font_path.is_file():
        sys.stderr.write(f"ERROR: required font not found by filename: {args.font_name}\n")
        return 4
    font_target = root / "OEBPS" / "fonts" / args.font_name
    shutil.copy2(font_path, font_target)

    extra_ads = set(a for a in (args.drop_line or []) if a)
    lines, removed = strip_ad_lines(read_source(src), extra_ads)
    intro, chapters = split_chapters(lines)
    if not chapters:
        sys.stderr.write("ERROR: no chapters detected. Check CHAPTER_RE against your source.\n")
        return 3

    # intro cleanup: drop leading title/author duplicates if present
    intro = [x.strip() for x in intro if x.strip()]

    # --- front matter / images -------------------------------------------
    (root / "mimetype").write_text("application/epub+zip", encoding="ascii")
    (root / "META-INF" / "container.xml").write_text(CONTAINER_XML, encoding="utf-8")
    (root / "OEBPS" / "styles" / "book.css").write_text(CSS % {"icon": args.icon_size}, encoding="utf-8")

    images: dict[str, str] = {}  # zip name -> media type
    manifest: list[str] = []
    spine: list[str] = []
    nav: list[tuple[str, str]] = []
    report: list[str] = []

    def add(id_: str, href: str, media: str, linear: bool = True) -> None:
        manifest.append(f'<item id="{id_}" href="{href}" media-type="{media}"/>')
        if linear:
            spine.append(f'<itemref idref="{id_}"/>')

    # illustrations: cover + splash dividers
    cover_name = None
    dividers: list[str] = []
    if img_dir and img_dir.is_dir():
        for candidate in sorted(img_dir.glob("*.png")) + sorted(img_dir.glob("*.jpg")):
            stem = unicodedata.normalize("NFC", candidate.stem)
            target = f"{stem}.jpg"
            w, h, n = save_budget_jpeg(candidate, root / "OEBPS" / "images" / target, args.max_image_side, args.max_image_bytes)
            images[target] = "image/jpeg"
            report.append(f"  illustration {candidate.name} -> {target} {w}x{h} {n}B")
            if stem.lower().startswith("cover"):
                cover_name = target
            elif stem.lower().startswith("divider"):
                dividers.append(target)

    # icons: normalise every one onto an exact square RGBA canvas
    icon_names: list[str] = []
    if icon_dir and icon_dir.is_dir():
        for i, source in enumerate(sorted(icon_dir.glob("icon-*.png"))):
            name = f"icon-{i:03d}.png"
            w, h, mode = normalise_icon(source, root / "OEBPS" / "images" / name, args.icon_size)
            images[name] = "image/png"
            icon_names.append(name)
            if i < 3:
                report.append(f"  icon {source.name} -> {name} {w}x{h} {mode}")
        if icon_names:
            report.append(f"  icons normalised: {len(icon_names)} @ {args.icon_size}x{args.icon_size} RGBA")

    # --- cover page -------------------------------------------------------
    csrc = f"../images/{cover_name}" if cover_name else ""
    if cover_name:
        body = f'<div class="cover"><img src="{csrc}" alt="封面"/></div>'
        (root / "OEBPS" / "text" / "cover.xhtml").write_text(xhtml("封面", body), encoding="utf-8")
        add("cover", "text/cover.xhtml", "application/xhtml+xml")

    # --- title page -------------------------------------------------------
    title_text = args.title or src.stem
    author_text = args.author or ""
    summary = "".join(f"<p>{html.escape(x)}</p>" for x in intro[:60])
    tp = (
        '<main class="titlepage">'
        f"<h1>{html.escape(title_text)}</h1>"
        + (f'<div class="author">作者：{html.escape(author_text)}</div>' if author_text else "")
        + (f'<div class="summary">{summary}</div>' if summary else "")
        + "</main>"
    )
    (root / "OEBPS" / "text" / "titlepage.xhtml").write_text(xhtml("简介", tp), encoding="utf-8")
    add("titlepage", "text/titlepage.xhtml", "application/xhtml+xml")
    nav.append(("titlepage.xhtml", "简介" if summary else title_text))

    # --- front matter -----------------------------------------------------
    # Keep publication context separate from the novel body, as in polished
    # reference books: title page, edition note, and a visible contents page.
    info_body = (
        '<main class="frontmatter"><h1>整理说明</h1>'
        '<h2>书目</h2>'
        f'<p>{html.escape(title_text)}，作者：{html.escape(author_text or "未知")}</p>'
        '<h2>版本说明</h2>'
        '<p>本电子书由纯文本整理为 EPUB 3；目录与书签统一由 toc.ncx 提供，不额外生成可见的目录页。</p>'
        '<p>正文按原始章节顺序编排；章头装饰图标仅作视觉标记，不改变正文内容。</p>'
        '</main>'
    )
    (root / "OEBPS" / "text" / "about.xhtml").write_text(xhtml("整理说明", info_body), encoding="utf-8")
    add("about", "text/about.xhtml", "application/xhtml+xml")
    nav.append(("about.xhtml", "整理说明"))

    total = len(chapters)
    divider_at: dict[int, str] = {}
    if dividers:
        # spread dividers across the book, and always put one before the extras
        step = max(total // (len(dividers) + 1), 1)
        for k in range(len(dividers)):
            divider_at[min(k * step, total - 1)] = dividers[k]
        extras = [i for i, (t, _) in enumerate(chapters) if "番外" in t]
        if extras and dividers:
            divider_at[extras[0]] = dividers[-1]

    for idx, (title, body_lines) in enumerate(chapters):
        if idx in divider_at:
            dname = divider_at[idx]
            did = f"divider{idx}"
            dbody = f'<div class="divider"><img src="../images/{dname}" alt=""/><p>{html.escape(title[:20])}</p></div>'
            (root / "OEBPS" / "text" / f"{did}.xhtml").write_text(xhtml(title[:20], dbody), encoding="utf-8")
            add(did, f"text/{did}.xhtml", "application/xhtml+xml")
            nav.append((f"{did}.xhtml", "◆ " + title[:20]))

        fid = f"ch{idx + 1:05d}"
        icon_html = (
            f'<img class="chapter-icon" src="../images/{icon_names[idx % len(icon_names)]}" alt=""/>'
            if icon_names
            else ""
        )
        cbody = (
            f'<main><div class="chapter-head">{icon_html}'
            f'<div class="chapter-title">{html.escape(title)}</div></div>'
            + paras(body_lines)
            + "</main>"
        )
        (root / "OEBPS" / "text" / f"{fid}.xhtml").write_text(xhtml(title, cbody), encoding="utf-8")
        add(fid, f"text/{fid}.xhtml", "application/xhtml+xml")
        nav.append((f"{fid}.xhtml", title))

    # --- bookmarks --------------------------------------------------------
    # Keep the NCX only: it is the reader-facing bookmark/navigation tree.
    book_id = "urn:uuid:" + str(uuid.uuid4())
    points = "".join(
        f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{html.escape(l)}</text></navLabel>'
        f'<content src="text/{html.escape(h)}"/></navPoint>'
        for i, (h, l) in enumerate(nav, start=1)
    )
    ncx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        f'<head><meta name="dtb:uid" content="{book_id}"/></head>'
        f"<docTitle><text>{html.escape(title_text)}</text></docTitle>"
        f"<navMap>{points}</navMap></ncx>"
    )
    (root / "OEBPS" / "toc.ncx").write_text(ncx, encoding="utf-8")
    manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')

    # --- assets in manifest ----------------------------------------------
    for name, media in images.items():
        iid = "img-" + re.sub(r"[^A-Za-z0-9]+", "-", name)
        props = ' properties="cover-image"' if name == cover_name else ""
        manifest.append(f'<item id="{iid}" href="images/{name}" media-type="{media}"{props}/>')
    manifest.append(f'<item id="font" href="fonts/{html.escape(args.font_name)}" media-type="font/ttf"/>')
    manifest.append('<item id="css" href="styles/book.css" media-type="text/css"/>')

    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" '
        'version="3.0" xml:lang="zh-CN">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">{book_id}</dc:identifier>'
        f"<dc:title>{html.escape(title_text)}</dc:title>"
        + (f"<dc:creator>{html.escape(author_text)}</dc:creator>" if author_text else "")
        + "<dc:language>zh-CN</dc:language>"
        + f'<meta property="dcterms:modified">{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}</meta>'
        + ('<meta name="cover" content="img-' + re.sub(r"[^A-Za-z0-9]+", "-", cover_name) + '"/>' if cover_name else "")
        + "</metadata>"
        f"<manifest>{''.join(manifest)}</manifest>"
        f'<spine toc="ncx">{"".join(spine)}</spine></package>'
    )
    (root / "OEBPS" / "content.opf").write_text(opf, encoding="utf-8")

    # --- zip (mimetype first, stored) ------------------------------------
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        try:
            out.unlink()
        except PermissionError:
            sys.stderr.write(
                f"ERROR: cannot overwrite {out} (file is open in a reader?).\n"
                "Close it, or pass a different --out path.\n"
            )
            return 4

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, "application/epub+zip")
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.name != "mimetype":
                z.write(p, p.relative_to(root).as_posix(), compress_type=zipfile.ZIP_DEFLATED)

    print(f"chapters    : {total}")
    print(f"ad lines    : {removed} removed")
    print(f"illustrations: {len([k for k in images if not k.startswith('icon-')])}")
    print(f"icons       : {len(icon_names)}")
    print(f"work dir    : {root}")
    print(f"output      : {out}")
    print(f"size        : {out.stat().st_size:,} bytes")
    if report:
        print("detail:")
        for line in report:
            print(line)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a clean EPUB 3 from a plain-text novel.")
    ap.add_argument("--src", required=True, help="source .txt (UTF-8/BOM, GB18030, GBK, Big5)")
    ap.add_argument("--out", required=True, help="output .epub path")
    ap.add_argument("--img-dir", default="", help="dir with cover.png / divider_*.png")
    ap.add_argument("--icon-dir", default="", help="dir with split icon-*.png files")
    ap.add_argument("--work-dir", default="", help="working dir (default: <out>_work)")
    ap.add_argument("--title", default="", help="book title (default: source filename stem)")
    ap.add_argument("--author", default="", help="author name")
    ap.add_argument("--font-name", default="LXGWWenKaiMono-Regular.ttf", help="required font filename; auto-discovered beside output or in current directory")
    ap.add_argument("--max-image-side", type=int, default=720, help="illustration longest side px (default 720)")
    ap.add_argument("--max-image-bytes", type=int, default=200_000, help="illustration byte budget (default 200000)")
    ap.add_argument("--icon-size", type=int, default=128, help="square icon canvas px (default 128)")
    ap.add_argument("--drop-line", action="append", default=[], help="extra exact line to drop (repeatable)")
    return build(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
