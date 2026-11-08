# Roadmap

Living document. Items move to "Done" only when they are merged and verified.

## Now (v0.4)

- [ ] pytest suite for `services/`: CV parsing, match scoring, tailoring, PDF output
- [ ] GitHub Actions workflow: install, compile, run the tests on every push
- [ ] Type hints and a logger on the service layer
- [ ] Fix the CV parser on two-column layouts

## Next (v0.5)

- [ ] Windows packaging with PyInstaller and an Inno Setup installer
- [ ] Better Persian PDF typography (line breaking, mixed-direction runs)
- [ ] Import presets for the three job boards used most often
- [ ] Backup and restore from the settings page

## Later

- [ ] Optional multi-user mode behind a login
- [ ] Job-board API integrations instead of HTML scraping
- [ ] English UI strings for the interface itself
- [ ] Docker image for self-hosting

## Known trade-offs

- Local-first storage is a deliberate choice; sync is out of scope.
- The AI features stay optional and bring-your-own-key; the app must work fully without them.
