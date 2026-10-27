# Changelog

All notable changes to this skill are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

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
