# Release Checklist

Before every release:

1. [ ] `python tools/update_deps.py` — regenerate .python-deps/ for Windows x64
2. [ ] `pytest --tb=short -q` — all tests pass
3. [ ] `python tools/package_release.py` — builds obfuscated UCAD-{version}.zip
4. [ ] Open FreeCAD, load the workbench, confirm no import errors in console
5. [ ] Test one prompt end-to-end with a real API key
6. [ ] Update package.xml version number
7. [ ] Tag the release: `git tag v1.0.x && git push --tags`
   - GitHub Actions auto-builds release.zip and creates a draft Release
8. [ ] Publish the draft Release on GitHub
