# Changelog

## Unreleased

- Bilingual interface: a switch in the header flips the whole UI between Persian (RTL) and English (LTR). In English mode every label, flash message, status and confirm dialog is English only; dates use the Gregorian calendar and digits switch to Latin. The choice lives in the session, so nothing changes until you pick a language.
- Native desktop window (pywebview + WebView2) instead of opening a browser tab; PDF downloads use the Windows save dialog.
- "Show the file after generating" checkbox on the job page opens the new PDF inline, with download and send shortcuts.
- PDF layout fixes for English and mixed-direction CVs: per-paragraph direction, RTL bullets, and non-overlapping date/title rows.
- CV upload no longer reads a "Page N" or "صفحه N" footer as the candidate name.
- "Save and test connection" for AI and SMTP now stores settings only when the test succeeds, and says so in the message.
- Desktop launcher: single-instance guard with a Persian notice, a load watchdog with an error message instead of a blank window, and a title bar without the zero-width non-joiner glyph problem.

## v0.3 - 2026-11-08

First public snapshot. The application runs end to end for a single user:

- Profile storage and CV upload with PDF, DOCX and TXT parsing.
- Job import by URL or pasted text, with language detection and match scoring.
- Tailored CV PDF, cover letter and ZIP package per application.
- Application tracker with stages, notes and generated files.
- Optional SMTP sending and OpenAI-compatible rewriting, both disabled by default.
- CSRF protection on forms and a local session secret.
- Added README, roadmap, changelog and license for the public release.

### Known gaps at this version

- No automated tests and no CI.
- Untyped service functions and no structured logging.
- No packaging or installer.
