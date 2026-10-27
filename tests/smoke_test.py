#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end smoke test: build a tiny EPUB from synthetic input, then verify it.

Everything is generated at runtime -- no binary fixtures in the repo:
  * a plain-text novel with 6 chapters, front matter and ad lines
  * a cover + one divider illustration (Pillow)
  * 4 chapter icons of differing sizes (to exercise normalisation)
  * a stand-in font file with the required filename

Run:
    python tests/smoke_test.py
Exit code 0 means build + verify both succeeded.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
FONT_NAME = "LXGWWenKaiMono-Regular.ttf"

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


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="epub-smoke-"))
    try:
        images = tmp / "images"
        icons = tmp / "icons"
        images.mkdir()
        icons.mkdir()

        source = tmp / "source.txt"
        source.write_text(SAMPLE, encoding="utf-8")

        # Illustrations: deliberately oversized so the budget pipeline runs.
        _gradient((1600, 2400), (18, 30, 46), (86, 112, 138)).save(images / "cover.png")
        _gradient((2000, 1400), (46, 38, 30), (120, 100, 78)).save(images / "divider_night.png")

        # Icons: different source sizes, must all come out 128x128 RGBA.
        for i, side in enumerate((96, 512, 130, 300)):
            im = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.ellipse([2, 2, side - 3, side - 3], outline=(40, 55, 70, 255), width=max(side // 24, 2))
            d.line([(side // 4, side // 2), (side * 3 // 4, side // 2)], fill=(200, 120, 60, 255), width=max(side // 32, 2))
            im.save(icons / f"icon-{i:03d}.png")

        # The builder resolves the font by filename next to the output file.
        (tmp / FONT_NAME).write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 64)

        out = tmp / "sample.epub"
        build = subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "build_epub.py"),
                "--src", str(source),
                "--out", str(out),
                "--img-dir", str(images),
                "--icon-dir", str(icons),
                "--title", "灯下长夜",
                "--author", "示例作者",
            ],
            capture_output=True, text=True,
        )
        sys.stdout.write(build.stdout)
        if build.returncode != 0:
            sys.stderr.write(build.stderr)
            print(f"BUILD FAILED (exit {build.returncode})")
            return 1

        verify = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "verify_epub.py"), str(out)],
            capture_output=True, text=True,
        )
        sys.stdout.write(verify.stdout)
        if verify.returncode != 0:
            sys.stderr.write(verify.stderr)
            print(f"VERIFY FAILED (exit {verify.returncode})")
            return 1

        if "RESULT : OK" not in verify.stdout:
            print("VERIFY did not report RESULT : OK")
            return 1

        print("SMOKE TEST PASSED")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
