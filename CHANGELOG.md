# Changelog

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
