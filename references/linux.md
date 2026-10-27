# Linux 平台参考（bash / sh）

本技能在 Linux（及 macOS）上的具体命令、路径与已知坑。

## 1. 定位源文件

```bash
find ~/Downloads -type f -iname '*关键词*' -name '*.txt'
# 或
ls -1 ~/Downloads/**/*关键词*.txt 2>/dev/null
```

> 坑：路径里的空格、中文、全角标点同样会让 `ls` 报错。
> 用 `find -iname` 递归搜索确认，不要直接信任用户贴出的路径。

## 2. 调用 Python

Linux 上通常只有 `python3`：

```bash
python3 build_epub.py \
  --src "$HOME/Downloads/book.txt" \
  --out "$HOME/build/book.epub" \
  --img-dir "$HOME/build/images" \
  --icon-dir "$HOME/build/icons/split64"
```

### 依赖安装

```bash
# Pillow
sudo apt install python3-pil        # Debian / Ubuntu
sudo dnf install python3-pillow     # Fedora
python3 -m pip install --user Pillow  # 通用（无 root 时）
```

虚拟环境更干净：

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install Pillow
```

### `python -c` 多行

Linux 下 `python3 -c` 同样不能把 `for` 跟在分号后，但 bash 支持单引号多行：

```bash
python3 - <<'PY'
import os
for f in os.listdir('.'):
    print(f)
PY
```

here-doc 是本平台处理多行脚本最干净的方式。复杂逻辑请直接写 `.py` 文件
（见本技能 `scripts/`）。

## 3. 生图与图标（img-gen / gpt-icon-generate）

反斜杠在 bash 里是转义符，**路径用正斜杠**，含空格用引号：

```bash
python3 "$SKILLS/img-gen/scripts/img_gen.py" generate \
  --preset apiyi_gpt_image_2 \
  --prompt "..." \
  --save "$BUILD/images/cover.png" \
  --size 2K --ratio 2:3
```

其中可先设：

```bash
SKILLS="$HOME/.qwenpaw/workspaces/default/skills"
BUILD="$HOME/build/novel"
mkdir -p "$BUILD/images" "$BUILD/icons"
```

> 续行符是 `\`（Windows cmd 是 `^`）。

### ImageMagick

Linux 上 IM6 常以 `convert` / `identify` 单独存在，而 IM7 统一为 `magick`。
切图脚本使用 `magick identify` / `magick convert`，因此需要 IM7：

```bash
# 检查
magick identify --version || convert --version

# 安装 IM7（Debian/Ubuntu 通常直接从仓库拿到 7）
sudo apt install imagemagick

# 若仓库版本是 IM6 且没有 magick 命令，建个兼容软链
sudo ln -sf /usr/bin/convert /usr/local/bin/magick   # 仅在确认 IM6 时如此处理
```

> 注意：某些发行版的 IM 策略文件 `/etc/ImageMagick-6/policy.xml`
> 默认禁用 PDF/部分格式。**PNG 一般不受影响**，本技能只处理 PNG，无需改策略。
>
> 切图时 stderr 的 `WARNING: The convert command is deprecated...` 是
> IM7 的正常噪音，可忽略。

## 4. 文件被占用

Linux 上很少出现 Windows 那种强制锁定，但如果 EPUB 正被某个进程持有
（例如另一进程 mmap），`unlink` 依旧会失败。处理方式：

- 换 `--out` 文件名；或
- 找出持有点：

```bash
fuser -v book.epub 2>/dev/null || lsof book.epub 2>/dev/null
```

`build_epub.py` 在 unlink 失败时会返回退出码 4 并给出明确提示。

## 5. 中文与编码

- 源 txt 常见 UTF-8 with BOM，也可能 GB18030/GBK/Big5。
  `build_epub.py` 依次尝试 `utf-8-sig → utf-8 → gb18030 → gbk → big5`。
- 终端 locale 若是 `C`/`POSIX`，中文可能显示为方框或转义，
  但不影响写入文件：

  ```bash
  locale            # 查看
  export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8   # 需要干净输出时
  ```

- 若系统缺 `zh_CN.UTF-8` locale 且看不到中文，可临时用：

  ```bash
  export PYTHONIOENCODING=utf-8
  ```

## 6. 路径分隔符

`pathlib` 自动处理。EPUB **内部**路径永远是正斜杠，脚本已保证。
在 bash 中注意：未加引号的路径含空格会被拆成多个参数，务必引号包裹。

## 7. 权限

若把成品写到系统目录，注意普通用户无写权限。建议输出到用户目录：

```bash
mkdir -p "$HOME/build/novel"
```

## 8. 快速命令清单

```bash
# 定位
find ~/Downloads -type f -iname '*book*' -name '*.txt'

# 构建
SKILLS="$HOME/.qwenpaw/workspaces/default/skills"
python3 "$SKILLS/epub-novel-builder/scripts/build_epub.py" \
  --src "$HOME/Downloads/book.txt" \
  --out "$HOME/build/novel/book.epub" \
  --img-dir "$HOME/build/novel/images" \
  --icon-dir "$HOME/build/novel/icons/split64" \
  --title "书名" --author "作者"

# 验证
python3 "$SKILLS/epub-novel-builder/scripts/verify_epub.py" "$HOME/build/novel/book.epub"
```
