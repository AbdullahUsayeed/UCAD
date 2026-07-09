import base64
import json
import os
from pathlib import Path
try:
    from cutout_knowledge_base import generate_vision_prompt_appendix
    _RECOGNITION_GUIDE = generate_vision_prompt_appendix()
except Exception:
    _RECOGNITION_GUIDE = ''
_DEEPSEEK_VISION_MODEL = 'deepseek-v4-flash'
_DEEPSEEK_VISION_URL = 'https://api.deepseek.com'
_VISION_SYSTEM_PROMPT = f'You are an expert PCB analyst assisting an enclosure designer.\nStudy the PCB image carefully and identify every component that needs a\ncutout or opening in the enclosure.\n\n{_RECOGNITION_GUIDE}\n\nGENERAL RULES\n───────────\n• Report EVERY connector, port, button, LED, display, or switch visible.\n• For each, output a structured line:\n    COMPONENT: <name> | WALL: <front/back/left/right/top> | DISTANCE_FROM_CORNER: <N mm> | QTY: <N>\n• After the structured list, add a short paragraph of any extra observations\n  (e.g. tall capacitors, heatsinks, unusual components, board orientation).\n• If you cannot determine a detail, write "unknown" rather than guessing.\n'
_VISION_USER_PROMPT = 'Analyse this PCB render. List every component that needs a cutout or window in the enclosure, using the structured format above.'
def analyse_pcb_image(png_path: str, api_key: str | None=None, timeout: int=60) -> str:
    key = api_key or os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if not key:
        raise RuntimeError('DeepSeek API key not found. Set DEEPSEEK_API_KEY env var or pass api_key=.')
    png_b64 = _encode_image(png_path)
    payload = _build_payload(png_b64)
    response = _post_direct(payload, key, timeout)
    return _extract_text(response)
def _encode_image(png_path: str) -> str:
    path = Path(png_path)
    if not path.is_file():
        raise FileNotFoundError(f'PNG not found: {path}')
    with open(path, 'rb') as fh:
        return base64.b64encode(fh.read()).decode('utf-8')
def _build_payload(png_b64: str) -> dict:
    return {'model': _DEEPSEEK_VISION_MODEL, 'max_tokens': 1024, 'messages': [{'role': 'system', 'content': _VISION_SYSTEM_PROMPT}, {'role': 'user', 'content': '![PCB render](data:image/png;base64,' + png_b64 + ')\n\n' + _VISION_USER_PROMPT}]}
def _post_direct(payload: dict, api_key: str, timeout: int) -> dict:
    import json as _json, urllib.request as _ur
    body = _json.dumps(payload).encode()
    req = _ur.Request(_DEEPSEEK_VISION_URL + '/chat/completions', data=body, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}, method='POST')
    resp = _ur.urlopen(req, timeout=timeout)
    return _json.loads(resp.read().decode())
def _extract_text(response: dict) -> str:
    try:
        content = response['choices'][0]['message']['content']
        if isinstance(content, str):
            return content.strip()
        return '\n'.join((b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f'Unexpected VL2 response: {exc}\nRaw: {json.dumps(response)[:600]}') from exc
if __name__ == '__main__':
    import sys, json
    if len(sys.argv) < 2:
        print('Usage: python vision_pipeline.py <board_render.png>')
        sys.exit(1)
    try:
        print(analyse_pcb_image(sys.argv[1]))
    except Exception as exc:
        print(f'ERROR: {exc}')
        sys.exit(1)
