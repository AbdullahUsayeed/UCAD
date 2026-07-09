import os
import subprocess
import tempfile
from pathlib import Path
_KICAD_CLI_CANDIDATES = ['C:\\Program Files\\KiCad\\9.0\\bin\\kicad-cli.exe', 'C:\\Program Files\\KiCad\\8.0\\bin\\kicad-cli.exe', 'C:\\Program Files\\KiCad\\7.0\\bin\\kicad-cli.exe', 'C:\\Program Files (x86)\\KiCad\\9.0\\bin\\kicad-cli.exe', 'C:\\Program Files (x86)\\KiCad\\8.0\\bin\\kicad-cli.exe', 'C:\\Program Files (x86)\\KiCad\\7.0\\bin\\kicad-cli.exe']
def _find_kicad_cli() -> str:
    env_path = os.environ.get('KICAD_CLI', '').strip()
    if env_path and Path(env_path).is_file():
        return env_path
    for candidate in _KICAD_CLI_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    try:
        result = subprocess.run(['where', 'kicad-cli'], capture_output=True, text=True, timeout=5)
        first_line = result.stdout.strip().splitlines()[0]
        if first_line and Path(first_line).is_file():
            return first_line
    except Exception:
        pass
    raise RuntimeError('kicad-cli.exe not found.\nEither:\n  • Install KiCad (https://www.kicad.org/download/) and re-run, or\n  • Set the KICAD_CLI environment variable to the full path of kicad-cli.exe')
def render_pcb_png(kicad_pcb_path: str, output_dir: str | None=None, width_px: int=1920, height_px: int=1080, background: str='opaque') -> str:
    pcb_path = Path(kicad_pcb_path).resolve()
    if not pcb_path.is_file():
        raise FileNotFoundError(f'PCB file not found: {pcb_path}')
    cli = _find_kicad_cli()
    if output_dir is None:
        output_dir = tempfile.gettempdir()
    out_png = Path(output_dir) / (pcb_path.stem + '_render.png')
    cmd = [cli, 'pcb', 'render', '--output', str(out_png), '--width', str(width_px), '--height', str(height_px), '--side', 'top', '--background', background, '--quality', 'high', '--preset', 'follow_plot_settings', '--use-board-stackup-colors']
    cmd.append(str(pcb_path))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError('kicad-cli render timed out after 60 s')
    if result.returncode != 0:
        err = (result.stderr or result.stdout or '').strip()
        raise RuntimeError(f'kicad-cli pcb render failed (exit {result.returncode}):\n{err}')
    if not out_png.is_file():
        raise RuntimeError(f'kicad-cli returned success but PNG not found at: {out_png}')
    return str(out_png)
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: python kicad_renderer.py <path_to.kicad_pcb>')
        sys.exit(1)
    try:
        cli_path = _find_kicad_cli()
        print(f'[kicad_renderer] Found kicad-cli: {cli_path}')
        png = render_pcb_png(sys.argv[1])
        print(f'[kicad_renderer] Rendered PNG: {png}')
    except Exception as exc:
        print(f'[kicad_renderer] ERROR: {exc}')
        sys.exit(1)
