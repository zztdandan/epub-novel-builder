# EPUB Novel Builder

把一部纯文本小说（`.txt`）一键变成**排版体面、插图可靠、目录完整**的 EPUB 电子书。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](#平台支持)
[![Agent Skill](https://img.shields.io/badge/agent%20skill-SKILL.md-6f42c1.svg)](SKILL.md)

> 这是一个 [Agent Skill](https://agentskills.io)：一个 `SKILL.md` + 若干脚本的文件夹。
> Agent 读完它会知道该按什么顺序做事、哪些坑不能踩；脚本负责把确定性的部分做对。

**TL;DR** — An agent skill that turns a plain-text novel into a clean EPUB 3 with chapter splitting,
ad removal, illustrations, normalised chapter icons, dual navigation (EPUB 3 nav + EPUB 2 NCX),
no font override (optional embedding), plus a verifier
that catches the bugs that actually break e-readers. Windows / Linux / macOS. MIT.

---

## 为什么需要它

用 Calibre 或 `pandoc` 转 EPUB，能打开，但经常出现这些**不报错**的问题：

- 封面加载不出来，章节里的图却正常 → 相对路径写错（`images/x.jpg` vs `../images/x.jpg`）
- 整本书或部分章节白屏 → 单张插图 4 MB、2000 px，移动端阅读器直接放弃
- 正文里正常台词被删 → 广告清理用了模糊关键词匹配
- 章头图标大小不一、位置随屏幕宽度漂移 → 图标没归一化、被塞进 `h1`
- 阅读器目录栏空白 → 只生成了 EPUB 3 `nav.xhtml` 或只生成了 `toc.ncx`，两种阅读器各认一种
- 读者改不了字体/字号 → 作者 CSS 用 `font-family` 把正文字体钉死了

`epub-novel-builder` 把这些都写成流程约束，并配一个**逐条对应的验证器**：`verify_epub.py`
会把上面每一条都检查一遍，一条不过就退出码 1。构建完不跑验证，等于没做完。

## 特性

| | |
|---|---|
| 📚 **章节切分** | 识别 `第X章` / `第X节` / `第X回` / `番外`，中文数字与阿拉伯数字都支持 |
| 🧹 **广告清理** | 只做**精确整行**匹配 + 行首强特征正则，绝不误删正文 |
| 🖼 **整页插图** | 自动缩到 ≤720 px、≤200 KB，转 progressive JPEG 并按质量递减试探 |
| 🎯 **章头图标** | 统一归一化到透明正方形画布，等比缩放居中，永不拉伸 |
| 🧭 **双轨目录** | 同时给 `nav.xhtml`（EPUB 3 必需，只进 manifest、**不进 spine**，书前不会出现目录页）和 `toc.ncx`（章 / 番外 / 分隔页 / 简介全入表） |
| 🔤 **不覆写字体** | 默认 CSS 不含 `font-family`，读者在阅读器里设的字体/字号说了算；需要时 `--font-name` 才嵌入并切换 |
| ⚖️ **体积可控** | 可选字体子集化 + WOFF2：中文完整字体 26 MB → 单本书 100 KB–1 MB（[见方法](references/fonts.md)） |
| 🧾 **规范打包** | `mimetype` 为首项且不压缩；OPF 元数据 / `cover-image` 属性完整 |
| ✅ **验证器** | 30 项断言覆盖上述每条失败模式，CI 友好 |
| 🔍 **EPUBCheck 配套** | 提供 npm 版（免 Java）校验流程，CI 双绿灯才发版 |
| 🪟 **跨平台** | Windows cmd/PowerShell 与 Linux/macOS bash 都有对应操作手册 |

## 安装

### 方式 1：用 skills CLI（推荐）

```bash
# 全局安装，任何项目里都能用
npx skills add zztdandan/epub-novel-builder -g

# 或只装到当前项目
npx skills add zztdandan/epub-novel-builder
```

### 方式 2：手动放到 Agent 的技能目录

```bash
git clone https://github.com/zztdandan/epub-novel-builder.git
```

| 你的 Agent | 放到哪里 |
|---|---|
| Claude Code / 通用 | `<project>/.claude/skills/epub-novel-builder/` 或 `~/.claude/skills/` |
| GitHub Copilot | `<project>/.github/skills/epub-novel-builder/` |
| 其他兼容 Agent Skills 的宿主 | `~/.agents/skills/epub-novel-builder/`（或该宿主文档指定的 skills 目录） |

`SKILL.md` 必须位于该目录根部，`scripts/`、`references/` 与它同级。

### 依赖

```bash
pip install Pillow           # 唯一必需依赖
# Debian/Ubuntu 也可： sudo apt install python3-pil
```

Python 3.9+。图标板切图另需 ImageMagick 7（`magick` 命令），可选。

字体：**不需要**。默认策略是不碰字体（见 [references/fonts.md](references/fonts.md)）。
只有在你确实要固定字体时，才自备字体文件（推荐子集化后的 `.woff2`）并用 `--font-name` 指定。

## 快速开始

```bash
# 目录准备
mkdir -p build/书名/images build/书名/icons
cp 你的小说.txt build/书名/source.txt

# 构建（插图与图标可省略，但封面/图标缺失时验证器会提示）
python3 scripts/build_epub.py \
  --src build/书名/source.txt \
  --out build/书名/书名.epub \
  --img-dir build/书名/images \
  --icon-dir build/书名/icons \
  --title "书名" --author "作者"

# 验证 —— 必做
python3 scripts/verify_epub.py build/书名/书名.epub
```

看到 `RESULT : OK` 才算完成。

### 直接当 CLI 用（不经过 Agent）

这个技能也是个能独立运行的命令行工具：

```bash
python3 scripts/build_epub.py --help
python3 scripts/verify_epub.py --help
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--src` | 必填 | 源 txt（UTF-8 / BOM / GB18030 / GBK / Big5 自动识别） |
| `--out` | 必填 | 输出 epub 路径 |
| `--img-dir` | 空 | 插图目录，`cover*` 作封面，`divider*` 作分隔页 |
| `--icon-dir` | 空 | 章节图标目录（`icon-*.png`，按序循环使用） |
| `--title` / `--author` | 文件名 / 空 | OPF 元数据；无作者时不写 `dc:creator` |
| `--font-name` | 空（不嵌入） | **可选**。传了才嵌入字体并把 `body` 切到该字体；扩展名决定 media-type（ttf/otf/woff/woff2） |
| `--max-image-side` | `720` | 整页插图最长边像素上限 |
| `--max-image-bytes` | `200000` | 整页插图单张字节上限 |
| `--icon-size` | `128` | 图标正方形画布边长 |
| `--drop-line` | 无 | 额外要精确删除的整行，可重复 |
| `--work-dir` | `<out>_work` | 中间产物目录，可随时删除 |

退出码：`0` 成功 · `2` 源文件不存在 · `3` 未识别到章节 · `4` 字体缺失或目标被占用。

## 验证器检查什么

`scripts/verify_epub.py` 共 30 项断言，按失败模式分组，每一组都对应一个真实踩过的坑：

| # | 检查项 | 对应的失败现象 |
|---|---|---|
| 1 | `mimetype` 是首个 zip 条目且 STORED、内容正确 | 阅读器拒读、Calibre 报警 |
| 2 | `container.xml` 存在；OPF 每个 manifest 项在 zip 内真实存在 | 打开后空白 / 缺页 |
| 3 | OPF 声明 `cover-image` | 书架无缩略图 |
| 4 | nav 文档恰好一个、**不在 spine**，含 `toc` 且链接全部可解析；`toc.ncx` 关联到 spine 且有导航点 | 目录栏空白 / 书前冗长目录 / epubcheck `RSC-005` |
| 5 | **每个 `<img src>` 相对其所在 XHTML 可解析且存在** | 封面黑块、图标正常（最隐蔽） |
| 6 | 无根绝对路径图片引用 | 桌面阅读器正常、手机全白 |
| 7 | 插图在像素 / 字节预算内 | 整书或章节白屏 |
| 8 | 所有图标精确正方形 + RGBA + 尺寸一致 | 章头参差不齐 |
| 9 | 字体策略：无字体时 CSS 无 `@font-face`/`font-family`；有字体时被引用且 media-type 正确 | 字体不生效 / 读者改不了字体 |
| 10 | 无广告残留（`soushu20xx`、`（本章完）` 等） | 正文夹带推广行 |
| 11 | 章节页含 `chapter-icon` 与 `chapter-title`，图标未嵌套进 `h1` | 图标漂移、标题被挤成一行 |

## 工作流程

完整版见 [SKILL.md](SKILL.md)，摘要：

1. **定位源文件** — 别信用户贴的路径，先递归搜一遍（路径里常混着文件夹名）
2. **建工作目录** — `images/` 放插图原图，`icons/` 放图标板与切图
3. **生成插图** — 封面 2:3，提示词必写 `no text, no letters, no watermark`
4. **生成并切图标板** — 8×8 = 64 个；密集网格切图必须降参（`--close-disk 1 --threshold 2%`）
5. **构建** — 一条命令完成清理、分章、压图、归一化、XHTML、nav + NCX 双轨目录、打包
6. **验证** — `verify_epub.py`，必须 `RESULT : OK`

生成插图 / 图标板那两步用的是另外的技能（如 `img-gen`、`gpt-icon-generate`），
也可以换成你自己喜欢的任何出图方式——本技能的边界从"手里有图"开始。

## 产物结构

```
书名.epub
├── mimetype                     # 首项、STORED
├── META-INF/container.xml
└── OEBPS/
    ├── content.opf              # 元数据 + manifest + spine(toc="ncx")
    ├── nav.xhtml                # EPUB 3 导航（必需；不在 spine，读者看不到）
    ├── toc.ncx                  # EPUB 2 目录 / 书签
    ├── fonts/                   # 可选：仅在传了 --font-name 时存在
    ├── styles/book.css
    ├── text/
    │   ├── cover.xhtml  titlepage.xhtml  about.xhtml
    │   ├── ch00001.xhtml …      # 章节图标与标题为独立顶层块
    │   └── divider<N>.xhtml
    └── images/                  # cover.jpg / divider_*.jpg / icon-*.png
```

## EPUBCheck（不在技能内，单独跑）

技能自带验证器只覆盖它自己踩过的坑（图片路径、字节预算、图标形状、nav/spine 关系……），
**不等于** EPUB 规范合规。发版前再跑一遍官方 EPUBCheck，两条流水线互补：

```bash
# 推荐：npm 版，不需要装 Java（TeaVM 编译版，输出与官方 jar 一致）
npx -y epubcheck-standalone-cli@5.4.0-build3 书名.epub

echo $?          # 0 = 无 error/warning，非 0 = 有问题
```

- 有 Java 的机器也可以用官方 jar：`java -jar epubcheck.jar 书名.epub`
- 只关心结论时不看输出细节，直接看退出码即可（CI 里就是这么用的）
- EPUBCheck **不校验字体二进制、不测阅读器兼容、不测可访问性**（可访问性用 [Ace](https://github.com/daisy/ace)）；
  它管“是否合规”，`verify_epub.py` 管“是否真的能看”

本仓库的 CI 已经这么跑（`.github/workflows/ci.yml` 的 `epubcheck` job，Node 24 + `epubcheck-standalone-cli`）。

## 已知取舍

- **nav 不进 spine**：符合规范（「Although EPUB Publications have to include an EPUB Navigation Document,
  it is not mandatory to include it in the spine」），也因此永远不会被渲染成书前目录页。
  代价是：如果你的目标阅读器只能靠 spine 里的目录页导航（极端少见的旧设备），它看不到 nav。
- **默认不覆写字体**：正文用阅读器默认字体。想固定排版就传 `--font-name`，
  但请先子集化，否则一本书的字体就能顶到 26 MB（[实测数字](references/fonts.md)）。
- **不内建 EPUBCheck**：技能保持“零 Java 依赖”，规范校验交给上面的 npm 流程 / CI。

## 平台支持

| 系统 | Python | 续行符 | 参考文档 |
|---|---|---|---|
| Windows（cmd / PowerShell） | `python` | cmd `^` / PS `` ` `` | [references/windows.md](references/windows.md) |
| Linux / macOS（bash） | `python3` | `\` | [references/linux.md](references/linux.md) |

两份参考文档覆盖：Pillow / ImageMagick 安装、here-doc、locale 与 `PYTHONIOENCODING`、
中文代码页、`WinError 32`（文件被阅读器占用）处理。
字体相关的可选分支另见 [references/fonts.md](references/fonts.md)（嵌入、子集化、WOFF2、OFL 许可）。

## 开发与测试

```bash
pip install Pillow
python tests/smoke_test.py                  # 两种字体策略各构一本 + 验证（CI 跑的就是它）
python tests/smoke_test.py --out-dir out    # 保留产物，供 EPUBCheck 复核
```

冒烟测试全部在运行时生成夹具（小说文本、封面、分隔页、4 个不同尺寸图标、占位字体），
仓库里没有二进制资源。两本产物分别覆盖：**默认不覆写字体**、**`--font-name` 嵌入字体**。

## 目录

```
epub-novel-builder/
├── SKILL.md                 # Agent 指令（流程、10 个坑、参数表）
├── scripts/
│   ├── build_epub.py        # 构建器
│   └── verify_epub.py       # 验证器（30 项断言）
├── references/
│   ├── windows.md
│   ├── linux.md
│   └── fonts.md             # 可选分支：字体嵌入与子集化
├── tests/smoke_test.py
├── .github/workflows/ci.yml
├── requirements.txt
└── LICENSE
```

## 许可

代码与文档：[MIT](LICENSE)。
生成的插图与可选嵌入的字体不在本仓库内，请遵循各自许可（字体常见为 OFL，须随书附许可文本）。
本技能不提供、不内置任何小说文本。
