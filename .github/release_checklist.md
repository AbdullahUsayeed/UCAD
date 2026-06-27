# Release Checklist

Before every release:

1. [ ] `python tools/update_deps.py` — regenerate .python-deps/ for Windows x64
2. [ ] `pytest --tb=short -q` — all tests pass
3. [ ] `python tools/build_release.py` — confirm .python-deps/ is included in output
4. [ ] Open FreeCAD, load the workbench, confirm no import errors in console
5. [ ] Test one prompt end-to-end with a real API key
6. [ ] Tag the release: `git tag v1.0.x && git push --tags`
7. [ ] Upload ZIP to distribution channel, update version number
8. [ ] Update package.xml version number to match
