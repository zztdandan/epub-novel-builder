# Windows 平台参考（cmd.exe / PowerShell）

本技能在 Windows 上的具体命令、路径与已知坑。

## Shell 选择

QwenPaw 在 Windows 上默认 shell 是 **cmd.exe**。部分命令必须改用 PowerShell
（`powershell -NoProfile -Command "..."`），下文逐条标注。

## 1. 定位源文件

用户给的路径经常不准（部分词是文件夹名）。先搜索实际位置：

```cmd
dir /s /b "C:\Users\<user>\Downloads\*关键词*.txt"
```

PowerShell 等价写法（更适合递归 + 通配）：

```powershell
Get-ChildItem -Path C:\Users\<user>\Downloads -Recurse -Filter *关键词*.txt |
  Select-Object -ExpandProperty FullName
```

> 坑：路径里的空格、中文、全角逗号都会让 cmd 的 `dir` 直接报「找不到文件」。
> 一定要用 `dir /s /b` 递归搜索确认，不要相信用户贴的那一串路径。

## 2. 调用 Python

Windows 上是 `python`（不是 `python3`）：

```cmd
python build_epub.py --src "...\book.txt" --out "...\book.epub" --img-dir "...\images" --icon-dir "...\icons\split64"
```

### 坑：`python -c` 里不能写 for 循环

cmd.exe 下，`python -c "a=1; for x in y: print(x)"` 会直接 SyntaxError，
因为复合语句不能跟在一行分号之后。三种可行做法：

1. 用 `exec()` + `\n`：
   ```cmd
   python -c "exec('import os\nfor f in os.listdir(\".\"):\n    print(f)')"
   ```
   cmd 里引号嵌套极其痛苦，能用下面两种就别用这个。

2. **推荐**：把逻辑写进 `.py` 文件再执行（本技能的 scripts/ 就是这个思路）。

3. PowerShell here-string 管道给 python：
   ```powershell
   @'
   import os
   for f in os.listdir('.'):
       print(f)
   '@ | python -
   ```

## 3. 生图与图标（img-gen / gpt-icon-generate）

路径用反斜杠 + 双引号包裹，含空格必须加引号：

```cmd
python "C:\Users\<user>\.qwenpaw\workspaces\default\skills\img-gen\scripts\img_gen.py" generate ^
  --preset apiyi_gpt_image_2 ^
  --prompt "..." ^
  --save "C:\path\build_dir\images\cover.png" ^
  --size 2K --ratio 2:3
```

> cmd 的续行符是 `^`（PowerShell 是反引号 `` ` ``，bash 是 `\`）。
> 单行写太长时注意这一点。

### ImageMagick

ImageMagick 7 在 Windows 上**只有 `magick.exe`**，没有独立的
`identify.exe` / `convert.exe`。切图脚本已用 `magick identify` /
`magick convert` 前缀，但需要 ImageMagick 在 PATH 中。

子代理/新会话可能不继承 PATH 变更，先显式刷新：

```powershell
$env:PATH = [Environment]::GetEnvironmentVariable('PATH','Machine') + ';' +
            [Environment]::GetEnvironmentVariable('PATH','User')
```

检查是否可用：

```cmd
magick identify --version
```

> 切图时 stderr 会刷 `WARNING: The convert command is deprecated...`，
> 这是 IM7 的正常噪音，不影响结果，不用管。

## 4. 文件被占用

重新打包时若 EPUB 正在阅读器/下载器里打开：

```
PermissionError: [WinError 32] 另一个程序正在使用此文件，进程无法访问。
```

处理方式：
- **首选**：换一个 `--out` 文件名（不要强行删被占用的文件）。
- 或者让用户先关闭阅读器再重跑。

`build_epub.py` 已经在 unlink 失败时返回明确错误并退出码 4，不会静默损坏。

## 5. 中文与编码

- 源 txt 常见 **UTF-8 with BOM**；`build_epub.py` 依次尝试
  `utf-8-sig → utf-8 → gb18030 → gbk → big5`，通常无需手动干预。
- cmd 控制台默认代码页可能是 936/GBK，脚本打印的中文可能显示为乱码，
  但**不影响文件写入**（Python 内部统一 UTF-8）。
  需要干净输出时：`chcp 65001` 或改用 PowerShell。

## 6. 路径分隔符

Python 的 `pathlib` 会自动处理 `\` 与 `/`。
在传给脚本的参数里反斜杠和正斜杠都能用，但 **cmd 下含空格必须加双引号**。
EPUB **内部**路径永远是正斜杠（`text/..`、`images/..`），脚本已处理好。

## 7. 快速命令清单

```cmd
:: 定位
dir /s /b "C:\Users\<user>\Downloads\*book*.txt"

:: 验证成品
python "C:\Users\<user>\.qwenpaw\workspaces\default\skills\epub-novel-builder\scripts\verify_epub.py" "C:\path\book.epub"
```
