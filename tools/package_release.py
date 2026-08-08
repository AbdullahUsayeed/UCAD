"""package_release.py — Build a deployable .zip for UCAD Assistant.

Usage:
    python tools/package_release.py

Output: UCAD-{version}.zip at repo root, ready for GitHub Releases.

The project is LGPL-2.1-or-later open source, so the package ships the
plain source (no obfuscation).

Zip structure:
    UCAD-{version}/
    ├── AICompanion/          # the addon directory
    │   ├── Init.py
    │   ├── InitGui.py
    │   ├── ... (all modules)
    │   └── .python-deps/     # vendored dependencies
    ├── install.bat           # Windows double-click installer
    └── install.sh            # Linux/macOS installer
"""

import os
import shutil
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent


def get_version() -> str:
    import xml.etree.ElementTree as ET
    pkg_xml = SOURCE / "package.xml"
    if not pkg_xml.exists():
        return "0.0.0"
    tree = ET.parse(pkg_xml)
    root = tree.getroot()
    # package.xml has a default namespace — resolve it so findtext works.
    ns = ""
    if root.tag.startswith("{"):
        ns = "{" + root.tag.split("}")[0].strip("{") + "}"
    ver = root.findtext(f"{ns}version", "0.0.0")
    return ver.strip()


def copy_plain_source(out_dir: Path):
    print("Copying plain open-source source (LGPL-2.1-or-later).")

    exclude_patterns = {
        # build/install/dev artifacts never ship with the addon
        "__pycache__", ".git", ".github", ".pytest_cache",
        ".coverage", ".gitignore",
        "config.json", "test_obf", ".release_staging",
        "build", "dist", "tests", "examples", "launcher", "installer",
        "tools", "deploy", "server", "worker", "scripts", "Resources",
        ".python-deps",
        "install.bat", "install.sh",
    }
    # server-side / infra files that belong in the repo, not the addon package
    exclude_files = {
        "server.py", "database.py", "Dockerfile", "docker-compose.yml",
        "pytest.ini", "requirements-dev.txt",
    }
    exclude_extensions = {".pyc", ".cover", ".tmp", ".zip"}

    for dirpath, dirnames, filenames in os.walk(SOURCE):
        dirpath_p = Path(dirpath)
        # Prune excluded directories so we never traverse huge trees
        dirnames[:] = [
            d for d in dirnames
            if d not in exclude_patterns and (dirpath_p / d).name not in exclude_patterns
        ]
        for fname in filenames:
            item = dirpath_p / fname
            rel = item.relative_to(SOURCE)
            parts = rel.parts
            if any(p in exclude_patterns for p in parts):
                continue
            if item.name in exclude_files:
                continue
            if item.suffix in exclude_extensions:
                continue
            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)

    deps_src = SOURCE / ".python-deps"
    if deps_src.exists():
        deps_dst = out_dir / ".python-deps"
        deps_dst.mkdir(parents=True, exist_ok=True)
        # Strip caches, compiled artifacts, tests, and package metadata so the
        # vendored deps are runtime-only and as small as possible.
        for item in deps_src.rglob("*"):
            rel = item.relative_to(deps_src)
            parts = rel.parts
            if any(
                p in ("__pycache__", "tests", "test", "testing")
                or p.endswith(".dist-info")
                or p.endswith(".egg-info")
                for p in parts
            ):
                continue
            if item.suffix in (".pyc", ".pyo", ".pyi", ".egg-info", ".tmp"):
                continue
            dst = deps_dst / rel
            if item.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            else:
                shutil.copy2(item, dst)
        size_mb = sum(f.stat().st_size for f in deps_dst.rglob("*") if f.is_file()) / 1e6
        print(f"  Copied .python-deps/: {size_mb:.1f} MB")


def build_package():
    version = get_version()
    zip_name = f"UCAD-{version}.zip"
    zip_path = SOURCE / zip_name

    staging = SOURCE / ".release_staging"
    if staging.exists():
        shutil.rmtree(staging)

    addon_dir = staging / "AICompanion"
    copy_plain_source(addon_dir)

    for installer in ["install.bat", "install.sh"]:
        src = SOURCE / installer
        if src.exists():
            shutil.copy2(src, staging / installer)
            print(f"  Copied {installer}")

    print(f"\n{'=' * 60}")
    print(f"Creating {zip_name} ...")
    print("=" * 60)

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(staging.rglob("*")):
            if file_path.is_file():
                arcname = f"{zip_name[:-4]}/{file_path.relative_to(staging)}"
                zf.write(file_path, arcname)

    print(f"\nZip contents ({zip_name}):")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            print(f"  {info.file_size:>10,} B  {info.filename}")

    size_mb = zip_path.stat().st_size / 1e6
    print(f"\n{'=' * 60}")
    print(f"Package created: {zip_path}")
    print(f"Size:           {size_mb:.2f} MB")
    print(f"Version:        {version}")
    print("=" * 60)

    shutil.rmtree(staging, ignore_errors=True)
    return zip_path


if __name__ == "__main__":
    build_package()
