"""Local LLM pipeline — standalone module for Ollama direct API.

Contains the ultra-compact system prompt, keyword-triggered knowledge
snippets, message builder, and direct Ollama HTTP caller.

Edit this file to customize local-model behaviour without touching the
orchestrator core."""
import json, urllib.request, urllib.error, ssl, re
from .gear_knowledge import should_inject_gear
from .airfoil_knowledge import should_inject_airfoil
from .triangle_knowledge import should_inject_triangle
from .curvedshapes_knowledge import should_inject_curvedshapes
from .addfc_knowledge import should_inject_addfc


def is_local_provider(provider: str) -> bool:
    """True when provider is ``"ollama"`` (currently the only local provider)."""
    return provider == "ollama"


# ─────────────────────────────────────────────────────────────────────────────
# CORE SYSTEM PROMPT
# Target: ~420 tokens  (down from ~900)
# ─────────────────────────────────────────────────────────────────────────────

LOCAL_SYSTEM_PROMPT = """\
ROLE: FreeCAD Python macro generator.
OUTPUT: ```python block only. End every response with:
  doc.recompute(); FreeCADGui.SendMsgToActiveView('ViewFit')
NO prose. NO markdown outside the fence. NO import FreeCAD (already loaded).

─── QUICK-MATCH: say the word → use exactly this code ───
rectangle  : Draft.makeRectangle(100,50)           # 1-liner simple
rect3D     : d.addObject("Part::Box","B"); B.Length=100; B.Width=60; B.Height=40
box (3D)   : d.addObject("Part::Box","B"); o.Length=100; o.Width=50; o.Height=30
cylinder   : d.addObject("Part::Cylinder","C"); o.Radius=25; o.Height=50
sphere     : d.addObject("Part::Sphere","S"); o.Radius=25
cone       : d.addObject("Part::Cone","K"); o.Radius1=30; o.Radius2=0; o.Height=50
torus      : d.addObject("Part::Torus","T"); o.Radius1=40; o.Radius2=10
circle(2D) : Draft.makeCircle(25)
polygon    : Draft.makePolygon(6,30)          # 6=hexagon
line       : Draft.makeLine(V(0,0,0),V(100,0,0))
triangle   : Draft.makeWire([V(0,0,0),V(50,0,0),V(25,43,0)],closed=True,face=True)

─── PARTDESIGN BOX TEMPLATE (for parametric/sketch-based shapes) ───
# body=d.addObject("PartDesign::Body","Body"); body.Label="Body"
# sk=body.newObject("Sketcher::SketchObject","Sketch"); sk.MapMode="Deactivated"
# W=100; H=60
# sk.addGeometry([Part.LineSegment(V(-W/2,-H/2,0),V(W/2,-H/2,0)),    # bottom
#                 Part.LineSegment(V(W/2,-H/2,0),V(W/2,H/2,0)),       # right
#                 Part.LineSegment(V(W/2,H/2,0),V(-W/2,H/2,0)),       # top
#                 Part.LineSegment(V(-W/2,H/2,0),V(-W/2,-H/2,0))],    # left
#                False)
# sk.addConstraint([Sketcher.Constraint('Coincident',0,2,1,1),Sketcher.Constraint('Coincident',1,2,2,1),
#                   Sketcher.Constraint('Coincident',2,2,3,1),Sketcher.Constraint('Coincident',3,2,0,1),
#                   Sketcher.Constraint('Horizontal',0),Sketcher.Constraint('Horizontal',2),
#                   Sketcher.Constraint('Vertical',1),Sketcher.Constraint('Vertical',3),
#                   Sketcher.Constraint('DistanceX',0,W),Sketcher.Constraint('DistanceY',1,H)])
# pad=body.newObject("PartDesign::Pad","Pad"); pad.Profile=sk; pad.Length=40

─── ALIASES (define at top of every script) ───
d=App.ActiveDocument; V=App.Vector; R=lambda:d.recompute(); S=Part.show

─── MODIFIERS ───
Fuse  : d.addObject("Part::MultiFuse","F"); F.Shapes=[a,b]
Cut   : d.addObject("Part::Cut","C"); C.Base=a; C.Tool=b
Common: d.addObject("Part::MultiCommon","I"); I.Shapes=[a,b]
Extrude: d.addObject("Part::Extrusion","E"); E.Base=wire; E.Dir=V(0,0,h); E.Solid=True
Revolve: d.addObject("Part::Revolution","V"); V.Source=f; V.Axis=V(0,0,1); V.Angle=360
Loft  : d.addObject("Part::Loft","L"); L.Sections=[w1,w2]; L.Solid=True
Sweep : d.addObject("Part::Sweep","W"); W.Sections=[pro]; W.Spine=path; W.Solid=True
Fillet: d.addObject("Part::Fillet","F"); F.Base=o; F.Edges=[(1,r,r)]
Mirror: d.addObject("Part::Mirroring","M"); M.Source=o; M.Normal=V(1,0,0)
Offset: d.addObject("Part::Offset","O"); O.Source=o; O.Value=t
Array : Draft.makeArray(o,V(dx,dy,dz),V(0,0,0),nx,ny)
PArray: Draft.makePathArray(o,path,n,0)

─── EXTRUDE FROM WIRE (preferred 3D from 2D) ───
wire=Draft.makeWire([V(0,0,0),V(50,0,0),V(25,43,0)],closed=True)
face=Part.Face(wire.Shape); solid=face.extrude(V(0,0,10)); S(solid)

─── DRAFT CURVES ───
Draft.makeBSpline([V..],closed=True)
Draft.makeBezCurve([V..])
Draft.makeArc(R, start_angle_deg, end_angle_deg)
Draft.makeShapeString(text, font_path, size, 0)

─── PARTDESIGN (for parametric/sketch shapes) ───
# See PARTDESIGN BOX TEMPLATE above for a complete rectangle example.
# General pattern:
# 1. body=doc.addObject("PartDesign::Body","Body")
# 2. sk=body.newObject("Sketcher::SketchObject","Sketch"); sk.MapMode="Deactivated"
# 3. sk.addGeometry([Part.LineSegment(V(x1,y1,0),V(x2,y2,0)), ...], False)
# 4. sk.addConstraint([Sketcher.Constraint('Coincident',...), ...])  # close loop
# 5. sk.addConstraint(...Horizontal/Vertical/DistanceX/DistanceY)     # size+angle
# 6. pad=body.newObject("PartDesign::Pad","Pad"); pad.Profile=sk; pad.Length=h

─── SKETCHER CONSTRAINTS (apply after addGeometry) ───
# sk.addConstraint(Sketcher.Constraint(TYPE, geo_idx, ...))
# Types+args: Coincident(gi,pi,gj,pj) DistanceX(gi,pi,val)
#             Distance(gi,pi,gj,pj,val) Radius(gi,val)
#             Horizontal(gi) Vertical(gi) Tangent(gi,gj) Angle(gi,val)

─── RULES ───
1. 1-liner shapes → use QUICK-MATCH table (Draft/Primitives)
2. Complex/parametric shapes → use PARTDESIGN BOX TEMPLATE pattern
3. Check obj is not None before .Shape
4. ViewObject: .ShapeColor=(r,g,b) .Transparency=50 .Selectable=False
5. Vertex index 1-based. Read before write: old=o.X; o.X=old+5
6. One object cannot belong to two Bodies
7. NEVER create a new Body/Sketch/Pad for "fillet", "chamfer", "make taller", "make wider", "change color", "move", "rotate", "mirror" — ADD a feature or EDIT the EXISTING object
8. Scene shows what already exists. If objects exist, EDIT them. Only create new when user says "new", "create", "add another"
9. "fillet it" → add Part::Fillet to the LAST created object. "make it taller" → change Height/Length on the LAST created object
"""


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE SNIPPETS  — injected only when triggered
# Each is a pure algorithm comment: no English prose, just math + API
# ─────────────────────────────────────────────────────────────────────────────

LOCAL_GEAR = """\
─── INVOLUTE GEAR ───
# make_gear(teeth=20, module=1, height=10, bore_r=6)
# pitch_r=teeth*module/2; base_r=pitch_r*cos(radians(20))
# addendum_r=pitch_r+module; dedendum_r=pitch_r-1.25*module
# tooth_angle=2*pi/teeth
# inv(rb,a)=V(rb*(cos(a)+a*sin(a)), rb*(sin(a)-a*cos(a)), 0)
# i_max=sqrt(addendum_r**2-base_r**2)/base_r
# For each tooth i (0..teeth-1):
#   a0=i*tooth_angle
#   root_L  = V(dedendum_r*cos(a0-.45*ta), dedendum_r*sin(a0-.45*ta), 0)
#   flank_R = [inv(base_r,t*(i_max/20)) rotated by a0-.25*ta  for t in range(21)]
#   tip     = [V(addendum_r*cos(a0+.2*ta+s*.1*ta/10), ...) for s in range(11)]
#   flank_L = flank_R mirrored (reverse t, offset +.25*ta)
#   root_R  = V(dedendum_r*cos(a0+.45*ta), dedendum_r*sin(a0+.45*ta), 0)
# pts=root_L+flankR+tip+flankL+root_R (per tooth, all teeth concatenated)
# wire=Part.makePolygon(pts+[pts[0]])
# gear=Part.Face(wire).extrude(V(0,0,height))
# bore=Part.makeCylinder(bore_r, height+2)
# S(gear.cut(bore))
"""

LOCAL_AIRFOIL = """\
─── NACA 4-DIGIT AIRFOIL ───
# naca4(code="2412", chord=100, span=200, pts=60)
# m=int(code[0])/100; p=int(code[1])/10; t=int(code[2:])/100
# xs=[0.5*(1-cos(pi*i/(pts-1))) for i in range(pts)]
# yt=[5*t*(0.2969*x**.5-0.1260*x-0.3516*x**2+0.2843*x**3-0.1015*x**4) for x in xs]
# yc: x<p → m/p**2*(2p*x-x**2)   x>=p → m/(1-p)**2*(1-2p+2p*x-x**2)  (0 if p==0)
# upper=[(x, yc[i]+yt[i]) for i,x in enumerate(xs)]
# lower=[(x, yc[i]-yt[i]) for i,x in enumerate(xs)]
# verts=[V(x*chord, y*chord, 0) for x,y in upper+list(reversed(lower))]
# profile=Draft.makeBSpline(verts, closed=True)
# face=Part.Face(profile.Shape)
# S(face.extrude(V(0,0,span)))
# NO external files. NO PartDesign. NO imports.
"""

LOCAL_TRIANGLE = """\
─── TRIANGLE (2D face only, no extrude) ───
# equilateral(s):  pts=[V(0,0,0),V(s,0,0),V(s/2,s*sqrt(3)/2,0)]
# right(a,b):      pts=[V(0,0,0),V(a,0,0),V(0,b,0)]
# isoceles apex angle α, height h:
#   half_base=h*tan(radians(α/2))
#   pts=[V(-half_base,0,0),V(half_base,0,0),V(0,h,0)]
# ANY triangle:
#   pts=[V(x0,y0,0),V(x1,y1,0),V(x2,y2,0)]
# ALWAYS: Draft.makeWire(pts,closed=True,face=True); R()
# NEVER extrude/pad a triangle unless user asks for 3D prism
"""

LOCAL_CURVEDSHAPES = """\
─── CURVEDSHAPES WORKBENCH ───
# import CurvedShapes  (workbench must be installed)
# CurvedArray:   CurvedShapes.makeCurvedArray(Base=profile,
#                    Hullcurves=[curve],Axis=V(1,0,0),Items=20,
#                    Surface=True,Solid=True)
# CurvedSegment: CurvedShapes.makeCurvedSegment(Shape1,Shape2,Items=15,Surface=True)
# PathArray:     CurvedShapes.makeCurvedPathArray(Base=pro,Path=spine,Items=30,
#                    Surface=True,Solid=True)
# InterpMiddle:  CurvedShapes.makeInterpolatedMiddle(S1,S2,Surface=True,InterpolationPoints=16)
# cutSurfaces:   CurvedShapes.cutSurfaces(Surfaces=[body],Normal=V,Position=V,Face=True)
# CONSTRAINTS: Hullcurves MUST lie in XY, XZ, or YZ plane. Items 10–80.
# FALLBACK (no workbench): Part.makeLoft([w1,w2],solid=True,ruled=False)
# WING workflow: naca4_profile → CurvedArray with tip+root hullcurves
"""

LOCAL_ADDFC = """\
─── ADDFC WORKBENCH ───
# AddFC is a GUI macro launcher, NOT a Python library.
# Launch:  FreeCADGui.execCommand('addFC')
# Install: FreeCADGui.addonManager().installWorkbench('AddFC')
# Do NOT call .install() or .run() — they do not exist.
"""


# ── Message builder ──────────────────────────────────────────────────





def build_messages_local(user_input: str, observation: str = "",
                         mode: str = "build",
                         history_text: str = "") -> list:
    """Build a single user message for local model.

    Small local models often ignore ``role: system``, so *everything* is
    inlined into a single user message. The hard rules are placed
    at the end where the model's attention window ends.

    Args:
        history_text: compact text summary of previous rounds
            (user input + code + scene after) so the model knows what exists.
    """
    if mode == "ask":
        parts = ["You are a FreeCAD expert assistant. Answer clearly and concisely. Include short ```python examples when helpful, but do NOT generate complete macros unless asked."]
        if history_text.strip():
            parts.append(f"─── PREVIOUS ROUNDS ───\n{history_text.strip()}")
        parts.append(f"─── CURRENT ───\nScene:{observation or ''}")
        parts.append(f"Question:{user_input}")
        return [{"role": "user", "content": "\n".join(parts)}]

    parts = [LOCAL_SYSTEM_PROMPT]
    if history_text.strip():
        parts.append(f"─── PREVIOUS ROUNDS ───\n{history_text.strip()}")
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
    parts.append(f"Request:{user_input}")
    parts.append("[HARD RULE: NEVER use PartDesign::Body/Sketcher/Pad/Pocket. Use Draft or Part::Primitives.]")
    return [{"role": "user", "content": "\n".join(parts)}]


# ── Ollama HTTP caller ───────────────────────────────────────────────

def call_ollama(messages: list, *,
                stream_callback=None,
                base_url: str = "http://localhost:11434",
                model: str = "llama3",
                max_tokens: int = None,
                temperature: float = None) -> str | None:
    """Send messages to a local Ollama server via the ``/api/chat`` endpoint.

    Returns the raw response text, or ``None`` on failure.
    Handles both streaming and non-streaming modes.
    """
    if model.startswith("ollama/"):
        model = model[len("ollama/"):]
    base = base_url.rstrip("/")
    url = f"{base}/api/chat"

    body = {"model": model, "messages": messages,
            "stream": bool(stream_callback)}
    opts = {}
    if max_tokens is not None:
        opts["num_predict"] = max_tokens
    if temperature is not None:
        opts["temperature"] = temperature
    if opts:
        body["options"] = opts

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    ctx = ssl.create_default_context()

    try:
        if stream_callback:
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            full = ""
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    full += content
                    stream_callback(content, "content")
            stream_callback("", "done")
            return full
        else:
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            result = json.loads(resp.read())
            return result.get("message", {}).get("content", "")
    except Exception as ex:
        print(f"[AI] Ollama call failed: {ex}")
        return None


# ── Code extraction helpers ──────────────────────────────────────────

def extract_code_blocks(response: str) -> list[str]:
    """Extract Python code blocks from an LLM response.

    Tries up to 4 strategies: explicit `````python`` fences, generic
    fences, truncated fences, and heuristic detection.
    """
    if not response:
        return []
    import re
    blocks = re.findall(
        r"```[ \t]*(?:python|py)[ \t]*\r?\n?(.*?)```",
        response, re.DOTALL | re.IGNORECASE)
    if not blocks:
        for m in re.finditer(
                r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n?(.*?)```",
                response, re.DOTALL):
            lang = (m.group(1) or "").lower()
            if lang == "json":
                continue
            body = m.group(2)
            if body.strip():
                blocks.append(body)
    if not blocks:
        m = re.search(r"```[ \t]*(?:python|py)[ \t]*\r?\n?(.+)",
                      response, re.DOTALL | re.IGNORECASE)
        if m:
            blocks = [m.group(1)]
    if not blocks:
        cleaned = re.sub(r"<API_PLAN>.*?</API_PLAN>", "", response,
                         flags=re.DOTALL | re.IGNORECASE)
        lines = cleaned.strip().splitlines()
        heuristic = [l for l in lines
                     if l.strip() and (l.startswith(
                         ("import ", "from ", "def ", "class ", "#"))
                         or "= FreeCAD" in l or "= App" in l
                         or ".addObject(" in l or ".newObject(" in l
                         or "doc.recompute()" in l)]
        if heuristic:
            blocks = ["\n".join(heuristic)]
    return [b.strip() for b in blocks if b.strip()]


def strip_think_blocks(response: str) -> str:
    """Remove  thinking...`` blocks that some models output."""
    if not response:
        return response
    import re
    return re.sub(r"<think>.*?</think>|\\boxed\{.*?\}|\\boxed\{",
                  "", response, flags=re.DOTALL).strip()


# ── High-level one-shot generation ───────────────────────────────────

def generate_code_local(messages: list, *,
                        stream_callback=None,
                        base_url: str = "http://localhost:11434",
                        model: str = "llama3",
                        max_tokens: int = None,
                        temperature: float = None) -> tuple:
    """One-shot code generation via direct Ollama call.

    Retries once if the output contains no extractable code block.

    Returns ``(raw_response, extracted_code, success)``.
    """
    for attempt in range(2):
        response = call_ollama(messages, stream_callback=stream_callback,
                               base_url=base_url, model=model,
                               max_tokens=max_tokens,
                               temperature=temperature)
        if not response:
            return "", None, False
        clean = strip_think_blocks(response)
        blocks = extract_code_blocks(clean)
        code = "\n\n".join(blocks) if blocks else clean
        if code:
            return response, code, True
    return response or "", code or "", bool(code)
