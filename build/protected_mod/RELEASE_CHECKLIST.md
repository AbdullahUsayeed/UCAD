# UCAD Assistant Release Checklist

## Pre-Release

- [ ] Bump version in `package.xml`
- [ ] Bump version in `launcher/version.py` (launcher + plugin)
- [ ] Bump version in `installer/setup.iss` (`MyAppVersion`)
- [ ] Update CHANGELOG / release notes
- [ ] Run full test suite: `python -m pytest tests/ -v`
- [ ] Test Mod in FreeCAD (manual launch via Addon Manager)

## Build Launcher

- [ ] Install PyInstaller: `pip install pyinstaller`
- [ ] Build: `python launcher/build_launcher.py`
- [ ] Verify: `dist/UCAD Launcher/UCAD Launcher.exe` exists
- [ ] Test launcher: `dist/UCAD Launcher/UCAD Launcher.exe`

## Build Installer

- [ ] Install Inno Setup 6+ from https://jrsoftware.org/isdl.php
- [ ] Build: `installer\build_installer.bat`
- [ ] Verify: `dist/UCAD_Assistant_<version>_Setup.exe` exists

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
- [ ] Create GitHub Release with:
  - [ ] `UCAD_Assistant_<version>_Setup.exe` (installer)
  - [ ] Source code archive
  - [ ] Release notes

## Post-Release

- [ ] Update README with new version
- [ ] Submit to FreeCAD Addon Manager (if applicable)
- [ ] Announce on FreeCAD forum
