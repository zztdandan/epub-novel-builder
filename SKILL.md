---
name: epub-novel-builder
description: "Use this skill to convert a plain-text novel (.txt) into a finished EPUB ebook: chapter splitting, advertisement removal, illustrations, per-chapter icons, image size budgeting, cover/title pages, NCX bookmarks, and validating that images actually load. Covers Windows and Linux. 触发词：制作epub、转epub、整理小说、电子书排版、小说做成电子书、epub生成。"
version: 1.0.0
license: MIT
metadata:
  qwenpaw:
    emoji: "📖"
    requires: {}
---

# EPUB 小说制作技能

本技能的固定规划约束：所有 EPUB 默认使用唯一指定字体文件名 `LXGWWenKaiMono-Regular.ttf`。调用方只指定文件名，不指定字体目录；构建器从输出目录或当前执行目录自动寻找该文件，并嵌入 EPUB 的 `fonts/` 资源目录，再由 CSS 的 `@font-face` 和正文字体声明统一使用。

目录策略：不生成可见的目录 XHTML，也不生成 EPUB 3 `nav.xhtml` 页面。目录/书签只通过 `toc.ncx` 提供，并将每章、分隔页、简介等有效入口写入 NCX，确保阅读器目录栏和书签功能正常，同时避免正文前出现冗长目录。

章节装饰策略：图标不得嵌套在 `h1` 或标题文本内。图标使用独立的顶端块级容器，标题使用后续独立块级元素，保证图标置顶、标题换行，并避免阅读器重排成同一行。本技能保留了真实制作中发现的图片路径、压缩、广告清理、图标归一化和 Windows 文件占用等防线；同时吸收参考书的出版结构经验：先组织书籍层级，再组织资源；OPF 提供规范元数据和封面属性，NCX 提供阅读器目录/书签；正文章节保持独立 XHTML，简介、分隔页和正文入口写入 NCX；图标是辅助识别，不是填充素材的理由，默认使用克制的章头标记。技能验证器现在检查：字体文件已嵌入且 CSS 正确引用；不存在可见 `nav.xhtml`；`toc.ncx` 存在并关联到 spine；章节图标和标题是独立顶层块；图片路径、封面属性、元数据和资源预算均正确。

## 目录

- [平台分流：先确定你在哪个系统](#平台分流)
- [踩坑总结（必读）](#踩坑总结必读)
- [完整工作流程](#完整工作流程)
- [验证](#验证)
- [推荐目录结构](#推荐目录结构)
- [平台参考文档](#平台参考文档)

---

## 平台分流

本技能**同时支持 Windows 与 Linux / macOS**。动手前先确认落在哪一支，然后加载对应参考文档：

| 系统 | Python | 续行符 | 路径 | 参考文档 |
|------|--------|--------|------|----------|
| Windows（cmd.exe / PowerShell） | `python` | cmd `^` / PS `` ` `` | 反斜杠可用，含空格要引号 | [`references/windows.md`](references/windows.md) |
| Linux / macOS（bash） | `python3` | `\` | 正斜杠，含空格要引号 | [`references/linux.md`](references/linux.md) |

两平台共通的差异点：

- **Pillow 必须装**。Linux 常缺：`sudo apt install python3-pil` 或
  `python3 -m pip install --user Pillow`。
- **ImageMagick 7 需要 `magick` 命令**（切图脚本用 `magick identify` /
  `magick convert`）。Windows 装 IM7 并加 PATH；Linux 装 `imagemagick`。
- **多行 Python 不要用 `-c` 加 `for`**（两平台都报 SyntaxError）。
  用 `.py` 文件，或 Windows PowerShell here-string / Linux here-doc。
- **EPUB 内部路径永远是正斜杠**，由脚本保证，与宿主系统无关。

判断当前平台的快捷方式：

```bash
# Linux / macOS
uname -s
# Windows (cmd)
ver
```

---

## 踩坑总结（必读）

按危害排序。前三条会导致"能打开但显示不全"，且**不会报错**。

### 坑 1 —— 图片相对路径写错（最隐蔽，封面全部加载不出）

**现象**：封面 / 分隔页图片完全加载不出来，但章节内图标显示正常。

**根因**：XHTML 在 `OEBPS/text/` 下，图片却在 `OEBPS/images/`。
若写成 `src="images/cover.jpg"`，会被解析为
`OEBPS/text/images/cover.jpg` —— 不存在。而图标恰好写了 `../images/`
所以正常，于是呈现"有的图能看、有的图不能看"的假象。

**正确写法**：`OEBPS/text/` 下所有图片引用必须是 `../images/xxx`。

**预防**：`build_epub.py` 统一使用 `../images/`；交付前跑
`verify_epub.py`，它会逐页解析每个 `<img src>` 并确认目标存在于 zip 内。

### 坑 2 —— 图片过大，整书或部分章节加载失败

**现象**：阅读器里整本书或部分章节打不开 / 长时间白屏。

**根因**：生图默认 2K，单张约 4MB。移动端阅读器无法处理。

**正确做法**：
- 整页插图：最长边 ≤ **720 px**，单张 ≤ **200 KB**
- 用 **progressive JPEG** + `optimize=True`
- quality 从 82 起每步 −4 递减，直到满足字节预算
- 图标用 PNG（要透明），体积天然很小

`build_epub.py` 的 `save_budget_jpeg()` 已实现该循环。

### 坑 3 —— 广告清理误删正文

**现象**：正文里正常的角色台词被删掉。

**根因**："请记住"、"网址"等词出现在小说对白中，模糊关键词匹配会误伤。

**正确做法**：只做**精确匹配**删除，绝不做模糊关键词删除。
`build_epub.py` 默认只删固定尾注（如 `（本章完）`），另外仅对
`下载自 / 备用地址 / 请记住本站 / www.xxx.com` 这类**行首强特征**做正则匹配；
需要补充时用 `--drop-line` 显式加精确整行。

### 坑 4 —— 图标尺寸不统一

**现象**：切出的图标大小各异，章头显示参差不齐。

**根因**：连通域切图按真实 bbox 裁切，每个图标像素尺寸不同。

**正确做法**：切图后归一化 —— 等比缩放进透明正方形画布并居中，
**不拉伸**：

```python
icon = Image.open(src).convert("RGBA")
icon.thumbnail((size, size), Image.Resampling.LANCZOS)
canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
canvas.alpha_composite(icon, ((size - icon.width) // 2, (size - icon.height) // 2))
canvas.save(dst, "PNG", optimize=True)
```

`normalise_icon()` 已实现。若用户说"8×8 / 128"，通常指
**8×8 网格共 64 个图标，每个 128×128 像素** —— 有歧义时先确认。

### 坑 5 —— 章头图标位置漂移

**现象**：图标有时在标题左边，有时在上方，随阅读器宽度变化。

**根因**：图标嵌套在 `h1` 或与标题共享行内排版时，阅读器会按标题宽度重新布局。

**正确做法**：图标和标题都放在独立的顶层块中，图标容器位于章节正文最顶部；不要把图片放进 `h1`。

```css
.chapter-head { display: block; text-align: center; page-break-before: always; }
.chapter-icon { display: block; width: 64px; height: 64px; margin: 0 auto .8em; }
.chapter-title { display: block; }
```

```html
<div class="chapter-head">
  <img class="chapter-icon" src="../images/icon-000.png" alt=""/>
  <div class="chapter-title">第一章 …</div>
</div>
```

### 坑 6 —— 密集图标板切图数量不对

**现象**：8×8 图标板切出的数量少于 64（相邻图标被合并）。

**根因**：默认 `--close-disk 5` 的形态学闭运算把相邻图标连成一个连通域。

**正确做法**：密集网格降低这些参数：

```bash
--close-disk 1 --threshold 2% --min-area 5000
```

### 坑 7 —— 不验证用户给的路径

**现象**：按用户贴的完整路径读文件，报"找不到文件"。

**根因**：路径中某些片段其实是**文件夹名**（例如 `Vidogram`），
不是文件名的一部分。

**正确做法**：先递归搜索确认真实路径（Windows `dir /s /b`，
Linux `find -type f -iname`），再处理。见对应平台参考文档。

### 坑 8 —— EPUB 被占用导致覆盖失败

**现象**：重打包时报 `PermissionError: [WinError 32]`（Windows）。

**根因**：成品正被阅读器 / 下载句柄打开。

**正确做法**：换一个 `--out` 文件名，**不要**强删被占用文件。
`build_epub.py` 在此情形返回退出码 4 并给出明确提示，不会静默损坏。

### 坑 9 —— `python -c` 里写 for 循环

Windows cmd 与 Linux bash 都会 SyntaxError（复合语句不能跟在分号后）。

**正确做法**：写 `.py` 文件执行；或 Windows 用 PowerShell here-string
`@'...'@ | python -`，Linux 用 here-doc `python3 - <<'PY' ... PY`。

---

## 完整工作流程

### Step 1 — 定位源文件

**不要信任用户给的路径**（坑 7）。按平台参考文档的搜索命令确认真实路径。

### Step 2 — 建立工作目录

统一结构，便于清理和复用（见下文"推荐目录结构"）：

```bash
# Linux
BUILD="$HOME/build/<书名>"; mkdir -p "$BUILD/images" "$BUILD/icons"
```
```cmd
:: Windows
set BUILD=C:\path\build_<书名>
mkdir "%BUILD%\images" "%BUILD%\icons"
```

### Step 3 — 生成插图（封面 + 分隔页）

用 `img-gen` 技能。提示词要点：

- 必写 `no text, no letters, no watermark`（图内不要出现文字）
- 写明画布尺寸与比例；封面用 `2:3`
- 封面在上三分之一留出干净负空间给标题排版

```bash
python3 "<skills>/img-gen/scripts/img_gen.py" generate \
  --preset apiyi_gpt_image_2 \
  --prompt "… no text, no letters, no watermark …" \
  --save "$BUILD/images/cover.png" --size 2K --ratio 2:3
```

保存到 `$BUILD/images/`，文件名以 `cover` / `divider` 开头即可被构建脚本识别。

### Step 4 — 生成图标板并切图

用 `gpt-icon-generate` 技能，默认 **8×8 = 64 个**图标：

```bash
# 1) 生成图标板（1K = 1280×1280）
python3 "<skills>/img-gen/scripts/img_gen.py" generate \
  --preset apiyi_gpt_image_2 \
  --prompt "Create a premium icon sheet with exactly 64 distinct symbolic icons arranged in a clean 8x8 regular grid. Canvas size 1024x1024. Pure white page background. Each icon visually centered in its own cell with generous empty padding, no text, no letters, no numbers. Unified ink-and-watercolor style. Each icon has a thin contour-hugging soft shadow. Do not create square cards, panels, tiles, borders, or frames." \
  --save "$BUILD/icons/icon-sheet-64.png" --size 1K --ratio 1:1

# 2) 校验尺寸
python3 "<skills>/gpt-icon-generate/scripts/verify_image_output.py" \
  "$BUILD/icons/icon-sheet-64.png" --requested-width 1280 --requested-height 1280

# 3) 计算切图参数
python3 "<skills>/gpt-icon-generate/scripts/plan_icon_sheet_params.py" \
  --width 1280 --height 1280 --rows 8 --cols 8

# 4) 切图（密集网格必须降参，见坑 6）
python3 "<skills>/gpt-icon-generate/scripts/split_icon_sheet_connected_bbox.py" \
  "$BUILD/icons/icon-sheet-64.png" "$BUILD/icons/split64" \
  --rows 8 --cols 8 --pad 18 --border 10 --fuzz 1.5% \
  --postprocess baseline --min-area 5000 --close-disk 1 --threshold 2%
```

### Step 5 — 构建 EPUB

一条命令完成清理、分章、压图、图标归一化、XHTML 生成、NCX 书签、字体嵌入与打包：

```bash
python3 "<本技能目录>/scripts/build_epub.py" \
  --src "$BUILD/source.txt" \
  --out "$BUILD/<书名>.epub" \
  --img-dir "$BUILD/images" \
  --icon-dir "$BUILD/icons/split64" \
  --title "<书名>" --author "<作者>"
```

常用参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--font-name` | `LXGWWenKaiMono-Regular.ttf` | 唯一指定字体文件名；自动从输出目录或当前执行目录查找并嵌入 |
| `--max-image-side` | `720` | 整页插图最长边像素上限 |
| `--max-image-bytes` | `200000` | 整页插图单张字节上限 |
| `--icon-size` | `128` | 图标统一正方形边长 |
| `--drop-line` | 无 | 额外要精确删除的整行，可重复 |
| `--work-dir` | `<out>_work` | 解包工作目录 |
| `--title` / `--author` | 源文件名 / 空 | 元数据 |

脚本行为要点：

- 只在**精确整行匹配**下删广告（坑 3）
- 自动识别章节（`第X章` / `番外` / `第X节|回`）
- 插图统一转 progressive JPEG 并压到预算内（坑 2）
- 图标统一归一化到 `icon-size` 的 RGBA 画布（坑 4）
- 章头图标与标题使用独立顶层块，图标置顶且标题换行（坑 5）
- 自动寻找并嵌入 `LXGWWenKaiMono-Regular.ttf`，CSS 使用该字体
- 不生成可见目录页和 `nav.xhtml`；只生成 `toc.ncx` 书签
- 所有图片引用写 `../images/`（坑 1）
- `mimetype` 为 zip 首项且不压缩

### Step 6 — 验证

**必须**跑验证脚本，它会逐项检查上述每个坑：

```bash
python3 "<本技能目录>/scripts/verify_epub.py" "$BUILD/<书名>.epub"
```

通过输出 `RESULT : OK`；失败会列出具体文件名与原因，退出码 1。

---

## 验证

`scripts/verify_epub.py` 检查项：

1. `mimetype` 是首个 zip 条目且为 STORED，内容正确
2. `META-INF/container.xml` 存在；OPF 中每个 manifest 项在 zip 内真实存在
3. **每个 `<img src>` 相对所在 XHTML 可解析且目标存在**（坑 1 的自动防线）
4. 插图在 `--max-image-side` / `--max-image-bytes` 预算内（坑 2）
5. 所有图标为**精确正方形 + RGBA**且尺寸一致（坑 4）
6. 指定字体 `LXGWWenKaiMono-Regular.ttf` 已嵌入，且 CSS 正确引用
7. 不存在可见 `nav.xhtml` 或目录 XHTML；`toc.ncx` 存在并关联到 spine
8. 无广告残留（`soushu2024` / `soushu2025` / `（本章完）`）
9. 章节页含 `chapter-icon` 与 `chapter-title`，且图标不嵌套在 `h1` 内

---

## 推荐目录结构

```
build_<书名>/
├── source.txt                 # 源小说
├── <书名>.epub                 # 成品
├── <书名>_work/                # 构建中间产物（可随时删除）
│   └── epub/
│       ├── mimetype
│       ├── META-INF/container.xml
│       └── OEBPS/
│           ├── content.opf
│           ├── toc.ncx             # 阅读器目录/书签
│           ├── fonts/               # LXGWWenKaiMono-Regular.ttf
│           ├── styles/book.css
│           ├── text/*.xhtml
│           └── images/        # cover.jpg / divider_*.jpg / icon-*.png
├── images/                    # 生成的整页插图原图
│   ├── cover.png
│   ├── divider_ruin.png
│   └── divider_frontier.png
└── icons/
    ├── icon-sheet-64.png      # 图标板
    └── split64/               # 切图输出 icon-000.png … icon-063.png
```

若用户在意体积，构建完成后可整体删除 `<书名>_work/`；保留 `images/`、
`icons/` 便于换风格重新打包。

---

## 平台参考文档

- [`references/windows.md`](references/windows.md) —— cmd/PowerShell 命令、
  续行符、ImageMagick PATH 刷新、`WinError 32` 处理、中文代码页
- [`references/linux.md`](references/linux.md) —— bash 命令、
  Pillow/ImageMagick 安装、here-doc、locale 与 `PYTHONIOENCODING`、权限

---

## 失败模式速查

| 症状 | 原因 | 解决 |
|------|------|------|
| 封面加载不出、图标正常 | 图片 src 写成 `images/` 而非 `../images/` | 坑 1；跑 `verify_epub.py` |
| 整书/部分章节白屏 | 插图 >200KB 或 >720px | 坑 2；降低 `--max-image-*` |
| 正文被删 | 模糊关键词删广告 | 坑 3；只用精确匹配 / `--drop-line` |
| 图标大小不一 | 未归一化 | 坑 4；透明画布居中缩放 |
| 图标位置漂移 | 图标与标题同行或嵌套在 h1 | 坑 5；使用独立 `.chapter-head` 顶端块和独立 `.chapter-title` |
| EPUB 前出现冗长目录 | 生成可见目录页或 nav.xhtml | 删除目录 XHTML/nav，仅保留 toc.ncx 书签 |
| 字体未生效 | 没有嵌入或 CSS 未引用指定字体 | 自动查找并嵌入 `LXGWWenKaiMono-Regular.ttf`，验证 CSS 路径 |
| 切图数量不足 | 密集网格参数过大 | 坑 6；`--close-disk 1 --threshold 2%` |
| 找不到源文件 | 路径里有文件夹名 | 坑 7；递归搜索确认 |
| `WinError 32` | 成品被阅读器占用 | 坑 8；换 `--out` 文件名 |
| `python -c` SyntaxError | for 循环跟分号 | 坑 9；写 `.py` 或用 here-doc |
