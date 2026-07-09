import os
import subprocess
import sys
from pathlib import Path
ADDON_DIR = Path(__file__).resolve().parent
DEPS_DIR = ADDON_DIR / '.python-deps'
REQ_FILE = ADDON_DIR / 'requirements.txt'
def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog(f'[AICompanion] {msg}\n')
    except ImportError:
        print(msg)
def _find_python():
    candidates = ['C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe', 'C:\\Program Files\\FreeCAD 1.0\\bin\\python.exe', 'C:\\Program Files\\FreeCAD 0.21\\bin\\python.exe', '/snap/freecad/current/usr/bin/python3', '/app/bin/python3', '/usr/lib/freecad/bin/python3', '/Applications/FreeCAD.app/Contents/Resources/bin/python3']
    for p in candidates:
        if os.path.exists(p):
            return p
    return sys.executable
def main():
    _log('Post-install: installing pip dependencies...')
    if not REQ_FILE.exists():
        _log('requirements.txt not found — skipping pip install')
        return
    python_exe = _find_python()
    _log(f'Using Python: {python_exe}')
    try:
        result = subprocess.run([python_exe, '-m', 'pip', 'install', '--target', str(DEPS_DIR), '--upgrade', '-r', str(REQ_FILE)], capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            _log('Dependencies installed successfully')
        else:
            _log(f'pip install failed:\n{result.stderr.strip()}')
    except Exception as e:
        _log(f'Post-install failed: {e}')
if __name__ == '__main__':
    main()
