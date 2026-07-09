from __future__ import annotations
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional
TIMEOUT_S: int = 30
MEMORY_LIMIT_MB: int = 512
FREECAD_BIN_ENV_VAR = 'FREECAD_BIN'
_BANNED_MODULES = {'subprocess', 'socket', 'http', 'urllib', 'requests', 'ftplib', 'smtplib', 'telnetlib', 'xmlrpc', 'multiprocessing', 'ctypes', 'cffi', 'winreg', 'nt'}
_BANNED_BUILTINS = {'eval', 'exec', 'compile', '__import__', 'open', 'breakpoint'}
_FAST_REJECT_RE = re.compile('\\b(subprocess|socket\\.connect|os\\.system|os\\.popen|shutil\\.rmtree|shutil\\.move|open\\s*\\(.*[\'\\"]w[\'\\"]|eval\\s*\\(|exec\\s*\\()\\b', re.IGNORECASE)
def _windows_registry_paths() -> list[str]:
    paths: list[str] = []
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in ('SOFTWARE\\FreeCAD', 'SOFTWARE\\WOW6432Node\\FreeCAD'):
                try:
                    key = winreg.OpenKey(root, sub)
                    install_dir, _ = winreg.QueryValueEx(key, 'InstallPath')
                    candidate = str(Path(install_dir) / 'bin' / 'FreeCADCmd.exe')
                    paths.append(candidate)
                    winreg.CloseKey(key)
                except OSError:
                    pass
    except ImportError:
        pass
    return paths
def _candidate_paths() -> list[str]:
    candidates: list[str] = []
    env_bin = os.environ.get(FREECAD_BIN_ENV_VAR, '').strip()
    if env_bin:
        candidates.append(env_bin)
    if sys.platform == 'win32':
        candidates.extend(_windows_registry_paths())
        prog_files = [os.environ.get('PROGRAMFILES', 'C:\\Program Files'), os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), os.path.expanduser('~\\AppData\\Local\\Programs')]
        versions = ['', ' 1.0', ' 1.1', ' 0.21', ' 0.20', ' 0.19']
        for base in prog_files:
            for ver in versions:
                candidates.append(str(Path(base) / f'FreeCAD{ver}' / 'bin' / 'FreeCADCmd.exe'))
        candidates += [os.path.expanduser('~\\AppData\\Local\\FreeCAD\\bin\\FreeCADCmd.exe'), os.path.expanduser('~\\FreeCAD\\bin\\FreeCADCmd.exe')]
    elif sys.platform == 'darwin':
        candidates += ['/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd', os.path.expanduser('~/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd')]
    else:
        candidates += ['/usr/bin/freecadcmd', '/usr/local/bin/freecadcmd', '/snap/bin/freecad', '/usr/lib/freecad/bin/freecad', '/opt/freecad/bin/freecadcmd', os.path.expanduser('~/.local/bin/freecadcmd')]
    for name in ('freecadcmd', 'FreeCADCmd', 'freecad', 'FreeCAD'):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    return candidates
def detect_freecad(raise_on_missing: bool=True) -> Optional[str]:
    seen: set[str] = set()
    for candidate in _candidate_paths():
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        p = Path(candidate)
        if p.is_file() and os.access(candidate, os.X_OK):
            return candidate
    if raise_on_missing:
        raise FileNotFoundError(f'FreeCAD executable not found.\nSet the {FREECAD_BIN_ENV_VAR} environment variable to the full path of FreeCADCmd.exe (Windows) or freecadcmd (Linux/macOS).\nExample (Windows): set FREECAD_BIN=C:\\Program Files\\FreeCAD 1.0\\bin\\FreeCADCmd.exe')
    return None
class _SecurityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split('.')[0]
            if top in _BANNED_MODULES:
                self.violations.append(f"Line {node.lineno}: banned import '{alias.name}'")
        self.generic_visit(node)
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ''
        top = module.split('.')[0]
        if top in _BANNED_MODULES:
            self.violations.append(f"Line {node.lineno}: banned import from '{module}'")
        self.generic_visit(node)
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name and name in _BANNED_BUILTINS:
            self.violations.append(f"Line {node.lineno}: banned call '{name}()'")
        self.generic_visit(node)
def validate_ast(script: str) -> dict:
    match = _FAST_REJECT_RE.search(script)
    if match:
        return _err(f"Static analysis: suspicious pattern detected: '{match.group()}'")
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        return _err(f'Syntax error on line {e.lineno}: {e.msg}')
    visitor = _SecurityVisitor()
    visitor.visit(tree)
    if visitor.violations:
        return _err('Static analysis violations:\n' + '\n'.join(visitor.violations))
    return _ok('AST validation passed.')
def _build_env() -> dict[str, str]:
    return {k: os.environ.get(k, '') for k in ('PATH', 'PYTHONPATH', 'PYTHONHOME', 'FREECAD_USER_HOME', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'TEMP', 'TMP')}
def _resource_limit_header() -> str:
    if sys.platform == 'linux':
        return f'import resource\nresource.setrlimit(resource.RLIMIT_CPU, ({TIMEOUT_S}, {TIMEOUT_S + 5}))\nresource.setrlimit(resource.RLIMIT_AS, ({MEMORY_LIMIT_MB * 1024 * 1024}, {MEMORY_LIMIT_MB * 1024 * 1024}))\n'
    return ''
def run_sandboxed(script: str, freecad_bin: Optional[str]=None, timeout: int=TIMEOUT_S, capture_output: bool=True) -> dict:
    ast_result = validate_ast(script)
    if not ast_result['ok']:
        ast_result['validation_mode'] = 'ast_only'
        return ast_result
    if freecad_bin is None:
        freecad_bin = detect_freecad(raise_on_missing=False)
    if freecad_bin is None:
        return {**_ok(f'AST validation passed. WARNING: FreeCAD executable not found — set {FREECAD_BIN_ENV_VAR} for full subprocess validation.'), 'validation_mode': 'ast_only'}
    script_exit = script.rstrip() + '\nimport sys; sys.exit(0)\n'
    full_script = _resource_limit_header() + script_exit
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
            tmp.write(full_script)
            tmp_path = Path(tmp.name)
        result = subprocess.run([freecad_bin, '--console', '--run-script', str(tmp_path)], capture_output=capture_output, timeout=timeout, env=_build_env())
        return {'ok': result.returncode == 0, 'stdout': result.stdout.decode('utf-8', errors='replace') if capture_output else '', 'stderr': result.stderr.decode('utf-8', errors='replace') if capture_output else '', 'exit_code': result.returncode, 'timed_out': False, 'validation_mode': 'subprocess'}
    except subprocess.TimeoutExpired:
        return {**_err(f'Sandbox timed out after {timeout}s.'), 'timed_out': True, 'validation_mode': 'subprocess'}
    except FileNotFoundError:
        return {**_ok('AST validation passed (subprocess unavailable at execution time).'), 'validation_mode': 'ast_only'}
    except Exception as e:
        return {**_err(f'Sandbox process error: {e}'), 'validation_mode': 'subprocess'}
    finally:
        if tmp_path:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
_MUTATION_RE = re.compile('\\b(addObject|removeObject|deleteObject|cut|fuse|makeCompound|export|saveAs|write|recompute|setattr|__import__)\\s*\\(', re.IGNORECASE)
def validate_in_sandbox(script: str) -> dict:
    ast_result = validate_ast(script)
    if not ast_result['ok']:
        ast_result['validation_mode'] = 'ast_only'
        return ast_result
    safe_lines = []
    for line in script.splitlines():
        if _MUTATION_RE.search(line):
            safe_lines.append(f'# stripped: {line.strip()}')
        else:
            safe_lines.append(line)
    return run_sandboxed('\n'.join(safe_lines))
def health_check() -> dict:
    probe = "import FreeCAD\nprint('sandbox_ok')\n"
    freecad_bin = detect_freecad(raise_on_missing=False)
    result = run_sandboxed(probe, freecad_bin=freecad_bin)
    return {'ok': result['ok'], 'freecad_bin': freecad_bin or 'not found', 'validation_mode': result.get('validation_mode', 'unknown'), 'message': result['stdout'].strip() or result['stderr'].strip() or 'no output'}
def _ok(message: str) -> dict:
    return {'ok': True, 'stdout': message, 'stderr': '', 'exit_code': 0, 'timed_out': False}
def _err(message: str) -> dict:
    return {'ok': False, 'stdout': '', 'stderr': message, 'exit_code': 1, 'timed_out': False}
