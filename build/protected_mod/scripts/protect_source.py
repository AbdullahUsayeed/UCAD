import ast
import re
import shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'build' / 'protected_mod'
EXCLUDE_FOLDERS = {'build', 'dist', '__pycache__', '.git', '.pytest_cache', '.python-deps', 'launcher', 'installer', 'tests', 'examples', 'server', 'tools', 'Resources'}
EXCLUDE_FILES = {'config.json'}
def _strip_comments(text):
    lines = []
    for line in text.splitlines():
        in_single = in_double = False
        i = 0
        while i < len(line):
            if line[i] == '#' and (not in_single) and (not in_double):
                line = line[:i].rstrip()
                break
            if line[i] == '\\':
                i += 2
                continue
            if line[i] == "'" and (not in_double):
                in_single = not in_single
            elif line[i] == '"' and (not in_single):
                in_double = not in_double
            i += 1
        lines.append(line)
    return '\n'.join(lines)
def _strip_docstrings(text):
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if not node.body:
                continue
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body.pop(0)
        return ast.unparse(tree)
    except SyntaxError:
        return text
def _minify(text):
    text = _strip_comments(text)
    text = _strip_docstrings(text)
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    text = '\n'.join(lines) + '\n'
    text = re.sub('\\n{3,}', '\n\n', text)
    return text
def _process_file(src, dst):
    if src.suffix not in ('.py',):
        return False
    if src.name in EXCLUDE_FILES:
        return False
    try:
        orig = src.read_text(encoding='utf-8')
        minified = _minify(orig)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(minified, encoding='utf-8')
        return True
    except Exception as e:
        print(f'  SKIP {src.relative_to(ROOT)}: {e}')
        return False
def _copy_static(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    count = 0
    SKIP_EXTS = {'.pyc', '.pyo', '.cover'}
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if any((p in EXCLUDE_FOLDERS for p in rel.parts)):
            continue
        if not path.is_file() or path.suffix in SKIP_EXTS:
            continue
        dst = OUT / rel
        if path.suffix == '.py':
            if _process_file(path, dst):
                count += 1
        else:
            _copy_static(path, dst)
            count += 1
    for init in OUT.rglob('__init__.py'):
        if init.stat().st_size < 80:
            orig = ROOT / init.relative_to(OUT)
            if orig.exists():
                init.write_bytes(orig.read_bytes())
    print(f'Protected {count} files to {OUT}')
if __name__ == '__main__':
    main()
