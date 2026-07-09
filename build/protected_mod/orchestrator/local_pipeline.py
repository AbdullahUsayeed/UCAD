import json, urllib.request, urllib.error, ssl, re
from .gear_knowledge import should_inject_gear
from .airfoil_knowledge import should_inject_airfoil
from .triangle_knowledge import should_inject_triangle
from .curvedshapes_knowledge import should_inject_curvedshapes
from .addfc_knowledge import should_inject_addfc
def is_local_provider(provider: str) -> bool:
    return provider == 'ollama'
LOCAL_SYSTEM_PROMPT = 'ROLE: FreeCAD Python macro generator.\nOUTPUT: ```python block only. End every response with:\n  doc.recompute(); FreeCADGui.SendMsgToActiveView(\'ViewFit\')\nNO prose. NO markdown outside the fence. NO import FreeCAD (already loaded).\n\n─── QUICK-MATCH: say the word → use exactly this code ───\nrectangle  : Draft.makeRectangle(100,50)\nrect3D     : d.addObject("Part::Box","B"); B.Length=100; B.Width=60; B.Height=40\nbox (3D)   : d.addObject("Part::Box","B"); o.Length=100; o.Width=50; o.Height=30\ncylinder   : d.addObject("Part::Cylinder","C"); o.Radius=25; o.Height=50\nsphere     : d.addObject("Part::Sphere","S"); o.Radius=25\ncone       : d.addObject("Part::Cone","K"); o.Radius1=30; o.Radius2=0; o.Height=50\ntorus      : d.addObject("Part::Torus","T"); o.Radius1=40; o.Radius2=10\ncircle(2D) : Draft.makeCircle(25)\npolygon    : Draft.makePolygon(6,30)\nline       : Draft.makeLine(V(0,0,0),V(100,0,0))\ntriangle   : Draft.makeWire([V(0,0,0),V(50,0,0),V(25,43,0)],closed=True,face=True)\n\n─── PARTDESIGN BOX TEMPLATE (for parametric/sketch-based shapes) ───\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n─── ALIASES (define at top of every script) ───\nd=App.ActiveDocument; V=App.Vector; R=lambda:d.recompute(); S=Part.show\n\n─── MODIFIERS ───\nFuse  : d.addObject("Part::MultiFuse","F"); F.Shapes=[a,b]\nCut   : d.addObject("Part::Cut","C"); C.Base=a; C.Tool=b\nCommon: d.addObject("Part::MultiCommon","I"); I.Shapes=[a,b]\nExtrude: d.addObject("Part::Extrusion","E"); E.Base=wire; E.Dir=V(0,0,h); E.Solid=True\nRevolve: d.addObject("Part::Revolution","V"); V.Source=f; V.Axis=V(0,0,1); V.Angle=360\nLoft  : d.addObject("Part::Loft","L"); L.Sections=[w1,w2]; L.Solid=True\nSweep : d.addObject("Part::Sweep","W"); W.Sections=[pro]; W.Spine=path; W.Solid=True\nFillet: d.addObject("Part::Fillet","F"); F.Base=o; F.Edges=[(1,r,r)]\nMirror: d.addObject("Part::Mirroring","M"); M.Source=o; M.Normal=V(1,0,0)\nOffset: d.addObject("Part::Offset","O"); O.Source=o; O.Value=t\nArray : Draft.makeArray(o,V(dx,dy,dz),V(0,0,0),nx,ny)\nPArray: Draft.makePathArray(o,path,n,0)\n\n─── EXTRUDE FROM WIRE (preferred 3D from 2D) ───\nwire=Draft.makeWire([V(0,0,0),V(50,0,0),V(25,43,0)],closed=True)\nface=Part.Face(wire.Shape); solid=face.extrude(V(0,0,10)); S(solid)\n\n─── DRAFT CURVES ───\nDraft.makeBSpline([V..],closed=True)\nDraft.makeBezCurve([V..])\nDraft.makeArc(R, start_angle_deg, end_angle_deg)\nDraft.makeShapeString(text, font_path, size, 0)\n\n─── PARTDESIGN (for parametric/sketch shapes) ───\n\n\n\n\n\n\n\n\n\n─── SKETCHER CONSTRAINTS (apply after addGeometry) ───\n\n\n\n\n\n─── RULES ───\n1. 1-liner shapes → use QUICK-MATCH table (Draft/Primitives)\n2. Complex/parametric shapes → use PARTDESIGN BOX TEMPLATE pattern\n3. Check obj is not None before .Shape\n4. ViewObject: .ShapeColor=(r,g,b) .Transparency=50 .Selectable=False\n5. Vertex index 1-based. Read before write: old=o.X; o.X=old+5\n6. One object cannot belong to two Bodies\n7. NEVER create a new Body/Sketch/Pad for "fillet", "chamfer", "make taller", "make wider", "change color", "move", "rotate", "mirror" — ADD a feature or EDIT the EXISTING object\n8. Scene shows what already exists. If objects exist, EDIT them. Only create new when user says "new", "create", "add another"\n9. "fillet it" → add Part::Fillet to the LAST created object. "make it taller" → change Height/Length on the LAST created object\n'
LOCAL_GEAR = '─── INVOLUTE GEAR ───\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n'
LOCAL_AIRFOIL = '─── NACA 4-DIGIT AIRFOIL ───\n\n\n\n\n\n\n\n\n\n\n\n\n'
LOCAL_TRIANGLE = '─── TRIANGLE (2D face only, no extrude) ───\n\n\n\n\n\n\n\n\n\n'
LOCAL_CURVEDSHAPES = '─── CURVEDSHAPES WORKBENCH ───\n\n\n\n\n\n\n\n\n\n\n\n\n'
LOCAL_ADDFC = '─── ADDFC WORKBENCH ───\n\n\n\n\n'
def build_messages_local(user_input: str, observation: str='', mode: str='build', history_text: str='') -> list:
    if mode == 'ask':
        parts = ['You are a FreeCAD expert assistant. Answer clearly and concisely. Include short ```python examples when helpful, but do NOT generate complete macros unless asked.']
        if history_text.strip():
            parts.append(f'─── PREVIOUS ROUNDS ───\n{history_text.strip()}')
        parts.append(f"─── CURRENT ───\nScene:{observation or ''}")
        parts.append(f'Question:{user_input}')
        return [{'role': 'user', 'content': '\n'.join(parts)}]
    parts = [LOCAL_SYSTEM_PROMPT]
    if history_text.strip():
        parts.append(f'─── PREVIOUS ROUNDS ───\n{history_text.strip()}')
    if should_inject_gear(user_input):
        parts.append(LOCAL_GEAR)
    if should_inject_airfoil(user_input):
        parts.append(LOCAL_AIRFOIL)
    if should_inject_triangle(user_input):
        parts.append(LOCAL_TRIANGLE)
    if should_inject_curvedshapes(user_input):
        parts.append(LOCAL_CURVEDSHAPES)
    if should_inject_addfc(user_input):
        parts.append(LOCAL_ADDFC)
    parts.append(f"─── CURRENT ───\nScene:{observation or ''}")
    parts.append(f'Request:{user_input}')
    parts.append('[HARD RULE: NEVER use PartDesign::Body/Sketcher/Pad/Pocket. Use Draft or Part::Primitives.]')
    return [{'role': 'user', 'content': '\n'.join(parts)}]
def call_ollama(messages: list, *, stream_callback=None, base_url: str='http://localhost:11434', model: str='llama3', max_tokens: int=None, temperature: float=None) -> str | None:
    if model.startswith('ollama/'):
        model = model[len('ollama/'):]
    base = base_url.rstrip('/')
    url = f'{base}/api/chat'
    body = {'model': model, 'messages': messages, 'stream': bool(stream_callback)}
    opts = {}
    if max_tokens is not None:
        opts['num_predict'] = max_tokens
    if temperature is not None:
        opts['temperature'] = temperature
    if opts:
        body['options'] = opts
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    ctx = ssl.create_default_context()
    try:
        if stream_callback:
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            full = ''
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                content = chunk.get('message', {}).get('content', '')
                if content:
                    full += content
                    stream_callback(content, 'content')
            stream_callback('', 'done')
            return full
        else:
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            result = json.loads(resp.read())
            return result.get('message', {}).get('content', '')
    except Exception as ex:
        print(f'[AI] Ollama call failed: {ex}')
        return None
def extract_code_blocks(response: str) -> list[str]:
    if not response:
        return []
    import re
    blocks = re.findall('```[ \\t]*(?:python|py)[ \\t]*\\r?\\n?(.*?)```', response, re.DOTALL | re.IGNORECASE)
    if not blocks:
        for m in re.finditer('```[ \\t]*([A-Za-z0-9_+-]*)[ \\t]*\\r?\\n?(.*?)```', response, re.DOTALL):
            lang = (m.group(1) or '').lower()
            if lang == 'json':
                continue
            body = m.group(2)
            if body.strip():
                blocks.append(body)
    if not blocks:
        m = re.search('```[ \\t]*(?:python|py)[ \\t]*\\r?\\n?(.+)', response, re.DOTALL | re.IGNORECASE)
        if m:
            blocks = [m.group(1)]
    if not blocks:
        cleaned = re.sub('<API_PLAN>.*?</API_PLAN>', '', response, flags=re.DOTALL | re.IGNORECASE)
        lines = cleaned.strip().splitlines()
        heuristic = [l for l in lines if l.strip() and (l.startswith(('import ', 'from ', 'def ', 'class ', '#')) or '= FreeCAD' in l or '= App' in l or ('.addObject(' in l) or ('.newObject(' in l) or ('doc.recompute()' in l))]
        if heuristic:
            blocks = ['\n'.join(heuristic)]
    return [b.strip() for b in blocks if b.strip()]
def strip_think_blocks(response: str) -> str:
    if not response:
        return response
    import re
    return re.sub('<think>.*?</think>|\\\\boxed\\{.*?\\}|\\\\boxed\\{', '', response, flags=re.DOTALL).strip()
def generate_code_local(messages: list, *, stream_callback=None, base_url: str='http://localhost:11434', model: str='llama3', max_tokens: int=None, temperature: float=None) -> tuple:
    for attempt in range(2):
        response = call_ollama(messages, stream_callback=stream_callback, base_url=base_url, model=model, max_tokens=max_tokens, temperature=temperature)
        if not response:
            return ('', None, False)
        clean = strip_think_blocks(response)
        blocks = extract_code_blocks(clean)
        code = '\n\n'.join(blocks) if blocks else clean
        if code:
            return (response, code, True)
    return (response or '', code or '', bool(code))
