# UCAD Assistant Release Checklist

## Pre-Release

- [ ] Bump version in `package.xml`
- [ ] Bump version in `launcher/version.py` (launcher + plugin)
- [ ] Bump version in `installer/setup.iss` (`MyAppVersion`)
- [ ] Update CHANGELOG / release notes
- [ ] Run full test suite: `python -m pytest tests/ -v`
- [ ] Test Mod in FreeCAD (manual launch via Addon Manager)

## Build Package (GitHub Actions)

Pushing a `v*` tag runs `.github/workflows/release.yml`, which:
- Runs the full test suite
- Vendors deps with `python tools/update_deps.py`
- Builds `UCAD-{version}.zip` (plain open-source source)
- Creates a draft GitHub Release

## Build Installer (Windows, optional)

- [ ] Install Inno Setup 6+ from https://jrsoftware.org/isdl.php
- [ ] Build: `installer\build_installer.bat`
- [ ] Verify: `dist\UCAD_Assistant_<version>_Setup.exe` exists

## Test Installer

- [ ] Test on clean Windows VM (no FreeCAD)
  - [ ] Installer detects missing FreeCAD
  - [ ] FreeCAD downloads successfully
  - [ ] Launcher starts after install
  - [ ] Launch button works
- [ ] Test on Windows with FreeCAD installed
  - [ ] Installer detects existing FreeCAD
  - [ ] Settings persist
  - [ ] Launch → FreeCAD opens with UCAD workbench

## Release

- [ ] Tag release in git: `git tag v<version> && git push --tags`
- [ ] Publish the draft GitHub Release created by CI
- [ ] Attach `UCAD_Assistant_<version>_Setup.exe` if the installer was built

## Post-Release

- [ ] Update README with new version
- [ ] Submit to FreeCAD Addon Manager (if applicable)
- [ ] Announce on FreeCAD forum

## Notes

- Project is **LGPL-2.0-or-later open source** — no source obfuscation.
- The installer ships plain source staged via `python tools/stage_mod.py`.
