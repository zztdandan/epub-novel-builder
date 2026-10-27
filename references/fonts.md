# 可选分支：字体（默认不覆写）

本技能**默认不碰字体**。`book.css` 里不写 `font-family`，也不生成 `@font-face`，
正文一律使用阅读器自己的正文字体 —— 用户在阅读器里设置的字体、字号、行距才是最终结果。

只有在下面这些情况，才走本文的可选分支：

| 触发条件 | 例子 |
|---|---|
| 需要固定排版风格 | 出版物要求统一衬线、统一字重 |
| 正文含生僻字 / 异体字 | 系统字体缺字，出现豆腐块 |
| 有明确的书名/风格要求 | 客户指定用某款字体 |
| 需要保证跨设备一致 | 图表混排、注音、特殊符号对齐 |

**代价先看清**：一款完整中文字体动辄 10–30 MB，会把一本 500 KB 的小说撑到 13 MB。
除非必要，不加。加了就必须做子集化（见下文）。

---

## 1. 嵌入字体（一步）

把字体文件放到**输出目录**或**当前执行目录**，然后只传文件名，不传路径：

```bash
python3 "<本技能目录>/scripts/build_epub.py" \
  --src "$BUILD/source.txt" \
  --out "$BUILD/<书名>.epub" \
  --img-dir "$BUILD/images" --icon-dir "$BUILD/icons/split64" \
  --font-name BookBody.woff2 \
  --title "<书名>" --author "<作者>"
```

构建器会：

1. 按文件名在 `--out` 所在目录、再在当前目录查找该文件；找不到直接退出码 4 并说明
2. 复制到 EPUB 的 `OEBPS/fonts/` 下
3. 在 OPF manifest 里按扩展名写**正确的 media-type**
4. 在 CSS 里生成 `@font-face`，并把 `body` 切到该字体

| 扩展名 | manifest media-type |
|---|---|
| `.ttf` | `font/ttf` |
| `.otf` | `font/otf` |
| `.woff` | `font/woff` |
| `.woff2` | `font/woff2` |

这四个都是 EPUB 3 的 core media type（EPUB 3.3 表 3.2），不需要 fallback。
**优先 `.woff2`**：同样的字形，体积通常只有 TTF 的一半左右。

要退回默认策略，删掉 `--font-name` 即可 —— 不生成 `@font-face`，不改 `font-family`。

---

## 2. 先子集化，再嵌入（重要）

完整字体直接塞进 EPUB 是本节优先级最高的问题。实测（LXGW WenKai Mono，25.96 MB 原始 TTF）：

| 方案 | 字体 | 成品 EPUB（一本 6 章短篇） |
|---|---|---|
| 完整 TTF | 25.96 MB | 13 MB |
| 子集化到本书 306 个字符（TTF） | 124 KB | 107 KB |
| 同上转 WOFF2 | 57 KB | 94 KB |
| 3500 常用汉字范围（≈普通长篇）TTF | 1.8 MB | ~2 MB |
| 同上转 WOFF2 | 848 KB | ~1 MB |
| 整个 CJK 统一汉字区（20992 字）TTF | 13 MB | 13 MB |

做法（需要 `fonttools`，`pip install "fonttools[woff]" brotli`）：

```bash
# 1) 收集本书真正用到的字符（正文 + 标题 + 标点 + 必要 ASCII）
cat "$BUILD/source.txt" > /tmp/chars.txt
printf '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ .,:;!?()[]-—_…“”‘’《》（）、；：？！\n' >> /tmp/chars.txt

# 2) 转成码位列表
python3 - <<'PY'
uniq = sorted({ord(c) for c in open('/tmp/chars.txt', encoding='utf-8').read()})
open('/tmp/uni.txt', 'w').write(','.join('U+%04X' % c for c in uniq))
print('codepoints:', len(uniq))
PY

# 3) 子集化 + 转 WOFF2（--flavor=woff2 一步到位）
pyftsubset LXGWWenKaiMono-Regular.ttf \
  --unicodes-file=/tmp/uni.txt \
  --flavor=woff2 \
  --layout-features='*' \
  --output-file=BookBody.woff2

ls -lh BookBody.woff2
```

注意：

- 子集里**必须**包含书名、作者、章节标题、番外标题、标点、数字、拉丁字母 —— 否则那些位置会缺字。
- 用户以后可能搜索生僻字；EPUB 里没有的字形，阅读器会回退到系统字体（只要 CSS 留了回退族）。
- 加了 `--layout-features='*'` 才能保住连字；中文一般用不到，可以去掉再省一点体积。
- 纯英文书用 `--unicodes=U+0020-007E` 就够，字体通常只有几十 KB。

---

## 3. 字体许可

- 商用字体**不要**随书分发，除非许可证明确允许嵌入。
- 常见开源中文字体：LXGW WenKai（OFL）、Source Han Serif/Sans 思源（OFL）、
  Noto Sans CJK（OFL）。
- OFL 1.1 要点：可以嵌入、可以随书分发，但必须**随附版权声明与许可文本**
  （建议把 `OFL.txt` 一起放进 `OEBPS/fonts/`，并在 OPF 加 `<dc:rights>`）。
- 严格按 OFL，**子集化属于"修改"**，带 Reserved Font Name 的字体在修改后不应继续使用原名；
  实务上多数项目保留原名并在书中注明"已子集化"，风险由发布方评估。

---

## 4. 常见反例

| 反例 | 后果 |
|---|---|
| `body { font-family: "X", monospace; }` | CJK 的 `monospace` 往往映射到难看的等宽字体，缺字时直接豆腐块 |
| 只写 `@font-face` 不写 `font-family` | 字体嵌进去了但没人用，`verify_epub.py` 会报"字体未被引用" |
| `font-family` 用 `!important` | 阅读器的"用户字体覆盖"失效，读者改不了字体 —— 不要这样做 |
| 只嵌 `.ttf` 却写 `media-type="application/x-font-ttf"` | 非 core media type，epubcheck 报错，部分阅读器忽略 |
| 用完整字体但没做子集 | 一本书 13 MB，移动端首开慢、商店体积超限 |

---

## 5. 验证

```bash
# 技能自带验证器：字体相关的断言
python3 "<本技能目录>/scripts/verify_epub.py" "$BUILD/<书名>.epub"
```

- 有字体时：`@font-face` 必须存在；每个嵌入字体必须在 CSS 里被 `../fonts/<文件名>` 引用；
  manifest 的 `media-type` 必须与扩展名匹配。
- **没有**字体时（默认策略）：CSS 里**不允许**出现 `@font-face`，
  也不允许出现 `font-family` —— 这条断言用来防止"顺手加了一行字体声明"污染默认策略。

需要更严格的规范校验时，用 npm 版 EPUBCheck 复核（自带 Java 的机器也可以用 jar）：

```bash
npx -y epubcheck-standalone-cli@5.4.0-build3 "$BUILD/<书名>.epub"
```

EPUBCheck **不检查字体二进制是否有效**（空的占位文件也能通过），
所以字体是否真的能渲染，仍要靠上面的 CSS/manifest 断言 + 实际打开阅读器确认。
