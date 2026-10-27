# Changelog

All notable changes to this skill are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-10-27

### Changed
- **Navigation is now dual-track.** The builder emits an EPUB 3 navigation document
  (`nav.xhtml`, declared with `properties="nav"`, deliberately kept **out of the spine**
  so no reader renders it as a TOC page) *and* the legacy `toc.ncx`. EPUB 3 requires a
  navigation document, so NCX-only output was non-conformant; NCX is still there for
  EPUB 2 reading systems. Spec: "not mandatory to include it in the spine".
- **The skill no longer overrides typography.** `book.css` contains no `font-family` and
  no `@font-face` by default; the reader's own font/size wins. `--font-name` is now an
  opt-in flag that embeds a font *and* switches the body to it.
- `--font-name` accepts `.ttf` / `.otf` / `.woff` / `.woff2` and writes the matching
  EPUB media-type instead of always `font/ttf`.

### Added
- `references/fonts.md`: optional font branch — when embedding is justified, `pyftsubset`
  subsetting (26 MB → ~1 MB measured), WOFF2, OFL obligations, and anti-patterns.
- Pit #10 in `SKILL.md`: NCX-only output and the `RSC-005` epubcheck error it causes.
- EPUBCheck flow documented in the README and enforced in CI via npm
  (`epubcheck-standalone-cli@5.4.0-build3`, no Java needed). It is intentionally **not**
  part of the skill's own scripts.
- `tests/smoke_test.py --out-dir` so CI can keep artifacts for EPUBCheck.

### Changed (verifier)
- New assertions: exactly one `properties="nav"` item, nav not in the spine, nav has
  `epub:type="toc"` and the `epub:` namespace, every nav link resolves, NCX has navPoints.
- Font policy assertions: with no font, CSS must contain neither `@font-face` nor
  `font-family`; with a font, it must be referenced from CSS and have the right media-type.
- 23 → 30 assertions.

## [1.0.0] - 2026-10-27

### Added
- First public release as an agent skill.
- `scripts/build_epub.py`: txt → EPUB 3 (chapter splitting, exact-match ad removal,
  illustration downscaling to pixel/byte budget, icon normalisation to square RGBA,
  cover/title page, `toc.ncx` bookmarks only, font embedding, mimetype-first zip).
- `scripts/verify_epub.py`: 23 checks that each map to a real shipped bug.
- `references/windows.md`, `references/linux.md`: per-platform command sheets.
- `tests/smoke_test.py`: runtime-generated fixture → build → verify, used by CI.
- GitHub Actions CI on Ubuntu / Windows / macOS, Python 3.9–3.12.

### Fixed
- `.chapter-head` CSS selector was missing its leading dot, so the chapter header block
  never received `page-break-before` and centring.
- 整理说明 page claimed EPUB 3 `nav.xhtml` is generated; it is not (NCX only).
