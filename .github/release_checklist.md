# Release Checklist

Before every release:

1. [ ] `pytest --tb=short -q` — all tests pass
2. [ ] Update `package.xml` version number (and `launcher/version.py` if launcher changed)
3. [ ] Tag the release: `git tag v1.0.x && git push --tags`
   - GitHub Actions auto-builds `UCAD-{version}.zip` (plain open-source source + vendored deps)
   - It runs the test suite first and creates a draft Release
4. [ ] Publish the draft Release on GitHub
5. [ ] (Optional) Build the Windows installer locally:
   - `installer\build_installer.bat` (requires Inno Setup 6)
   - Verify `dist\UCAD_Assistant_<version>_Setup.exe` exists
6. [ ] Submit to FreeCAD Addon Manager (if applicable)

## Notes

- The project is **LGPL-2.0-or-later open source** — no source obfuscation.
- The installer ships plain source staged via `python tools/stage_mod.py`.
