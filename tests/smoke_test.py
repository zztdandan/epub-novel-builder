#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end smoke test: build EPUBs from synthetic input, then verify them.

Two builds, because the skill has two font policies:
  * default  -- the reader keeps its own font (no @font-face, no font-family)
  * --font-name -- embed a font, declare it in the manifest, reference it in CSS

Everything else is generated at runtime, so the repo carries no binaries:
a plain-text novel with 6 chapters plus ad lines, a cover, a divider,
4 chapter icons of differing sizes, and a stand-in font file.

Run:
    python tests/smoke_test.py                 # scratch dir, cleaned up
    python tests/smoke_test.py --out-dir out   # keep the .epub files (CI)
Exit code 0 means every build + verify step succeeded.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "scripts" / "build_epub.py"
VERIFY = REPO / "scripts" / "verify_epub.py"
FONT_NAME = "sample-body-font.woff2"

SAMPLE = """《灯下长夜》
作者：示例作者

这是一段简介文字，用来验证简介页与 NCX 入口是否正确生成。
整理说明会放在简介页中，不单独生成可见目录页。

（本章完）
下载自 www.example.com

第一章 归途
雨从傍晚一直下到子夜。街口的路灯隔一会儿就闪一次，像在犹豫要不要亮。
他把伞收起来，靠在门框上，听见楼上有人在挪椅子。

第二章 旧信
抽屉最深处压着一封没有寄出的信，纸已经泛黄，折痕处起了毛。
信里只写了一句话：灯亮着，你就回来。

www.example.com
请记住本站

第三章 灯下
灯下的桌面干净得过分，连一枚灰都不肯留下。
他把信摊开，读了三遍，又把灯拧暗了一点。

第四章 长夜
夜比想象中长。他数过窗外的车声，数到四十七就停了。
风把窗帘掀起一角，又放下。

第五章 归零
天亮之前，他终于睡着了。
梦里有人在灯下站着，看不清脸，只看得见手里那封信。

番外 灯芯
后来有人问起那盏灯，他说：灯芯短了，火就低，但不会灭。
"""


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    im = Image.new("RGB", size)
    draw = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(h - 1, 1)
        draw.line(
            [(0, y), (w, y)],
            fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)),
        )
    return im


def make_fixture(root: Path) -> dict[str, Path]:
    images, icons = root / "images", root / "icons"
    images.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)

    source = root / "source.txt"
    source.write_text(SAMPLE, encoding="utf-8")

    # Illustrations: deliberately oversized so the budget pipeline runs.
    _gradient((1600, 2400), (18, 30, 46), (86, 112, 138)).save(images / "cover.png")
    _gradient((2000, 1400), (46, 38, 30), (120, 100, 78)).save(images / "divider_night.png")

    # Icons: different source sizes, must all come out 128x128 RGBA.
    for i, side in enumerate((96, 512, 130, 300)):
        im = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([2, 2, side - 3, side - 3], outline=(40, 55, 70, 255), width=max(side // 24, 2))
        d.line([(side // 4, side // 2), (side * 3 // 4, side // 2)],
               fill=(200, 120, 60, 255), width=max(side // 32, 2))
        im.save(icons / f"icon-{i:03d}.png")

    # Stand-in font: the builder never parses font binaries, only moves them.
    (root / FONT_NAME).write_bytes(b"wOF2\x00\x00\x00\x00" + b"\x00" * 60)

    return {"source": source, "images": images, "icons": icons, "root": root}


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
    return proc


def build_and_verify(fx: dict[str, Path], name: str, extra: list[str]) -> Path:
    out = fx["root"] / f"{name}.epub"
    proc = run([
        sys.executable, str(BUILD),
        "--src", str(fx["source"]),
        "--out", str(out),
        "--img-dir", str(fx["images"]),
        "--icon-dir", str(fx["icons"]),
        "--title", "灯下长夜",
        "--author", "示例作者",
        *extra,
    ])
    if proc.returncode != 0:
        raise SystemExit(f"BUILD FAILED for {name} (exit {proc.returncode})")

    proc = run([sys.executable, str(VERIFY), str(out)])
    if proc.returncode != 0 or "RESULT : OK" not in proc.stdout:
        raise SystemExit(f"VERIFY FAILED for {name} (exit {proc.returncode})")
    return out


def css_of(epub: Path) -> str:
    with zipfile.ZipFile(epub) as z:
        return "".join(
            z.read(n).decode("utf-8")
            for n in z.namelist()
            if n.endswith(".css")
        )


def opf_of(epub: Path) -> str:
    with zipfile.ZipFile(epub) as z:
        return "".join(
            z.read(n).decode("utf-8")
            for n in z.namelist()
            if n.endswith(".opf")
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build + verify synthetic EPUBs.")
    ap.add_argument("--out-dir", default="", help="keep build artifacts here (default: temp dir, removed)")
    args = ap.parse_args()

    keep = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
    root = keep or Path(tempfile.mkdtemp(prefix="epub-smoke-"))
    root.mkdir(parents=True, exist_ok=True)
    try:
        fx = make_fixture(root)

        # 1) default policy: the reader keeps its own font
        plain = build_and_verify(fx, "reader-default-font", [])
        css = css_of(plain)
        assert "@font-face" not in css, "default build must not declare @font-face"
        assert "font-family" not in css, "default build must not override the reader font"

        # 2) opt-in: embed a font, declare media-type, reference it from CSS
        embedded = build_and_verify(fx, "embedded-font", ["--font-name", FONT_NAME])
        opf = opf_of(embedded)
        assert 'media-type="font/woff2"' in opf, "woff2 must be declared as font/woff2"
        assert f"../fonts/{FONT_NAME}" in css_of(embedded), "CSS must reference the embedded font"
        with zipfile.ZipFile(embedded) as z:
            assert f"OEBPS/fonts/{FONT_NAME}" in z.namelist(), "font file missing from the archive"

        print("SMOKE TEST PASSED")
        print(f"artifacts: {plain}")
        print(f"artifacts: {embedded}")
        return 0
    finally:
        if keep is None:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
