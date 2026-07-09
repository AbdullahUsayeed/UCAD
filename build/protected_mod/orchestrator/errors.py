import re, ast, textwrap
from dataclasses import dataclass
ERROR_TRANSLATIONS = [('Recursive.*computation', 'circular_dep', 'Circular dependency. The operation would loop infinitely. Try a different modeling approach.'), ('BRep.*Not.*Plane', 'bad_plane', 'Sketch/face is not on a valid plane. Always use a standard plane (XY/XZ/YZ) or a planar face.'), ('no.*solid|NullShape|Shape.*not.*null', 'no_solid', 'No valid solid. The shape is open or non-manifold. Close all loops and ensure watertight geometry.'), ('Unit mismatch|Quantity::operator', 'unit_mismatch', 'Unit/Quantity mismatch in arithmetic. FreeCAD properties like .Length/.Radius return a Quantity (with units). Use .Value to get a plain float before doing math: e.g. h = obj.Length.Value - 2.0  (NOT obj.Length - 2.0), or wrap with float(...).'), ('Wire is not closed|wire.*not.*closed', 'open_wire', 'The profile wire is not closed, so it cannot be padded/extruded. Make all edges connect end-to-end into ONE closed loop. For airfoils, add a straight trailing-edge segment to close the spline, then verify Part.Wire(edges).isClosed() before padding.'), ('BRep_API: command not done|BRep_API', 'brep_fail', 'An OpenCASCADE operation failed (BRep_API: command not done) — usually degenerate/invalid input: open wires, zero-area faces, or self-intersecting/non-planar profiles. Simplify and ensure profiles are closed, planar, and non-self-intersecting.'), ('Null input shape', 'null_input', 'An operation received an empty/null shape — a previous step produced no geometry (often an unclosed profile or a failed feature). Verify the prior feature created a valid .Shape before using it.'), ('Body: object is not allowed|object is not allowed', 'body_not_allowed', "Cannot add that object to a PartDesign Body. Bodies only accept PartDesign features via body.newObject('PartDesign::Pad'|'PartDesign::Pocket'|'Sketcher::SketchObject', name). Do NOT put Part:: primitives (Part::Box/Cylinder) inside a Body — create those standalone with doc.addObject('Part::Box', name)."), ('must be a DAG|graph must be a DAG', 'not_dag', 'Circular dependency created — a feature references an object that (directly or transitively) depends on it. A feature may only reference EARLIER objects, never itself or a later feature. Break the cycle.'), ('AttachEngine3D|subshape not found|PositionBySupport', 'bad_attach_plane', "Wrong sketch attachment. Origin planes (XY_Plane/XZ_Plane/YZ_Plane) are separate objects, NOT subshapes of the Body. Get the plane object and attach with an EMPTY subelement: xy = doc.getObject('XY_Plane'); sketch.AttachmentSupport = (xy, ['']); sketch.MapMode = 'FlatFace'. Inside a Body, find the plane via body.Origin.OutList."), ('ArcOfCircle constructor expects', 'bad_arc', 'Wrong Part.ArcOfCircle usage. Use three points: Part.ArcOfCircle(p1, p2, p3) (each a FreeCAD.Vector), OR a circle + parameter range: Part.ArcOfCircle(Part.Circle(center, normal, radius), startParam, endParam).'), ('failed to recompute', 'recompute_fail', 'Model recompute failed. Likely conflicting constraints or invalid geometry after changes.'), ('null.*pointer|access.*violation|Access violation', 'null_ptr', 'Internal null reference. The object may have been deleted or the reference is stale.'), ('not found|does not exist', 'not_found', 'Object not found in document. Check that the object name/label is correct.'), ('cannot.*compute', 'compute_fail', 'Cannot compute geometry. The input might be too complex or invalid.'), ('Sketch.*invalid|sketch.*constraint', 'bad_sketch', 'Sketch is invalid — open vertices, over-constrained, or overlapping geometry.'), ('no.*shape', 'no_shape', 'Object has no shape. Recompute the document or create the object properly first.'), ("has no attribute 'Sketch'", 'pad_sketch_attr', 'FreeCAD 1.0 renamed .Sketch → .Profile on Pad/Pocket/Revolution/Groove/Hole. Use: pad.Profile = sketch (NOT pad.Sketch = sketch). Also ensure the sketch is inside the body.'), ('AttributeError.*has no attribute', 'bad_attr', 'Object does not have that property/attribute. Check the FreeCAD API reference for correct property names.'), ('AttributeError', 'bad_attr_gen', "AttributeError: the code tried to access a property that doesn't exist on the object."), ('NameError', 'name_error', 'NameError: a variable is undefined. Check for typos or missing imports.'), ('TypeError', 'type_error', 'TypeError: wrong data type passed to a function. E.g., string instead of number.'), ('IndexError', 'index_error', 'IndexError: list index out of range. Check that the list has the expected number of items.'), ('KeyError', 'key_error', 'KeyError: dictionary key not found.'), ('ImportError.*not in the allowlist', 'blocked_import', 'Import blocked: that module is not in the security allowlist. Use only: FreeCAD, FreeCADGui, Part, PartDesign, Sketcher, Mesh, Draft, Import, math.'), ('ImportError', 'import_error', 'ImportError: module not found. Use only standard FreeCAD modules.'), ('ZeroDivisionError', 'div_zero', 'Division by zero in the code.'), ('ValueError', 'value_error', 'ValueError: an operation received an invalid value. Check dimensions are positive.'), ('RuntimeError', 'runtime_error', 'RuntimeError in FreeCAD. Often caused by invalid object state or missing dependencies.'), ('Base::PyException', 'freecad_exception', 'FreeCAD internal error. The Python API call was rejected — check object types and parameters.'), ("has no attribute 'Support'", 'no_support', 'DO NOT use .Support on sketches. Use sketch.AttachmentSupport = (obj, [\\"Face6\\"]) instead — it\'s a tuple of (object, subelement_list).'), ("has no attribute 'ReferenceAxis'", 'no_refaxis', "PartDesign features don't have .ReferenceAxis. For revolution axes use .Axis = FreeCAD.Vector(x,y,z). For other features, check the API reference."), ('single GeoFeatureGroup', 'geo_group', 'Object is already inside another Part/Group/Body. Use obj.InList to find its parent, then parent.removeObject(obj) before adding it elsewhere.'), ("'NoneType' object has no attribute", 'none_type_attr', 'Tried to access an attribute on a None value — the object lookup failed (doc.getObject returned None, or a previous operation returned nothing). Always check for None before accessing .Shape or other attributes: \'if obj is None: raise Exception("Object not found")\'. Use resolve_obj = doc.getObject(\'ExactName\') or iterate doc.Objects to find the right object by TypeId.'), ("'App\\.Document' object has no attribute", 'doc_attr_error', 'Tried to access an object via doc.ObjectName attribute syntax instead of doc.getObject(\'Name\'). FreeCAD documents do NOT support attribute-style access for objects. Always use doc.getObject("ExactInternalName") to retrieve an object by its internal Name.'), ('Both points are equal', 'dup_points', 'OCCError: zero-length edge — consecutive identical coordinates in profile. Deduplicate consecutive identical points before calling Part.makePolygon() or makeWire(). Use: pts = [p for i,p in enumerate(pts) if i==0 or (p-pts[i-1]).Length > 1e-6]. Also check len(pts) >= 3 before calling makePolygon.'), ('OCCError.*points are equal', 'dup_points_occ', 'OCCError: zero-length edge in polygon. Filter duplicate consecutive points. Minimum 3 unique non-collinear points required for Part.makePolygon().')]
ERROR_STRATEGIES = {'bad_plane': 'Instead of using specific planes, create a sketch on a standard plane (XY) and use MapMode or AttachmentOffset.', 'no_solid': 'Use PartDesign workflow: Body -> Sketch -> Pad to ensure watertight solids. Avoid using raw Part::Box if you need booleans later.', 'recompute_fail': 'Simplify the approach. Create one feature at a time with doc.recompute() after each. Verify each step works before adding more.', 'bad_sketch': 'Keep sketches simple. Use only lines, arcs, and circles. Add coincident constraints at all endpoints to ensure closed profiles.', 'bad_attr': 'Check the exact property names. Part::Box uses Length/Width/Height. PartDesign::Pad uses .Profile (FreeCAD 1.0, NOT .Sketch) and .Length. Body uses .newObject().', 'pad_sketch_attr': "FreeCAD 1.0 renamed .Sketch → .Profile. Use pad.Profile = sketch (NOT .Sketch). Example: pad = body.newObject('PartDesign::Pad', 'Pad'); pad.Profile = sketch; pad.Length = 10; doc.recompute().", 'name_error': "You likely referenced a variable that wasn't created yet. Use explicit variable assignments and don't rely on FreeCAD auto-naming.", 'blocked_import': 'Remove that import. The required functionality is available through the allowed modules.', 'freecad_exception': "This usually means you're using the wrong type of object for the operation. Try a different FreeCAD API approach.", 'no_support': 'Replace sketch.Support with sketch.AttachmentSupport = (target_object, [\\"Face6\\"]). It takes a tuple of (object, subelement_list). The subelement list can be empty [] for standard planes.', 'no_refaxis': "PartDesign primitives don't have ReferenceAxis. For revolve/groove axes, set the .Axis property directly on the feature, not on the sketch.", 'geo_group': 'The object is already parented to a Part/Group/Body. Use obj.InList to find the parent, call parent.removeObject(obj), then addObject to the new parent.'}
def translate_error(error_text):
    from .core import AIOrchestrator
    for entry in AIOrchestrator.API_CORRECTIONS:
        if re.search(entry['error_pattern'], error_text, re.IGNORECASE):
            return (f"API error: {entry['mistake']}", f"Fix: {entry['fix']}\nExample: {entry['example']}")
    for pattern, code, hint in ERROR_TRANSLATIONS:
        if re.search(pattern, error_text, re.IGNORECASE):
            strat = ERROR_STRATEGIES.get(code, '')
            if strat:
                return (f'Type: {code}. {hint}', f'Strategy: {strat}')
            return (f'Type: {code}. {hint}', '')
    return ('Unknown error. Check the traceback.', '')
@dataclass
class ErrorReport:
    category: str = 'unknown'
    title: str = ''
    cause: str = ''
    location: str = ''
    fix: str = ''
    example: str = ''
    raw_error: str = ''
    retry_tier: int = 1
    def for_ui(self) -> str:
        parts = [f'❌ {self.title}']
        if self.location:
            parts.append(f'   📍 {self.location}')
        if self.cause:
            parts.append(f'   💥 {self.cause}')
        if self.fix:
            parts.append(f'   ✅ Fix: {self.fix}')
        if self.example:
            parts.append(f"   📝 Example:\n{textwrap.indent(self.example, '      ')}")
        return '\n'.join(parts)
    def for_ai_retry(self) -> str:
        if self.retry_tier == 1:
            return f'### EXECUTION ERROR (attempt {self.retry_tier})\nCategory: {self.category}\nProblem: {self.title}\nFix needed: {self.fix}\nDo NOT repeat the same approach. Choose a different strategy.'
        if self.retry_tier == 2:
            lines = [f'### EXECUTION ERROR (attempt {self.retry_tier})', f'Category: {self.category}', f'Problem: {self.title}']
            if self.location:
                lines.append(f'Failed at: {self.location}')
            if self.cause:
                lines.append(f'Root cause: {self.cause}')
            lines.append(f'Fix: {self.fix}')
            if self.example:
                lines.append(f'Correct pattern:\n```python\n{self.example}\n```')
            lines.append('Rewrite the code from scratch using the fix above.')
            return '\n'.join(lines)
        lines = [f'### EXECUTION ERROR (attempt {self.retry_tier} — FINAL)', f'Category: {self.category}', f'Problem: {self.title}']
        if self.location:
            lines.append(f'Failed at: {self.location}')
        if self.cause:
            lines.append(f'Root cause: {self.cause}')
        if self.raw_error:
            lines.append(f'Raw error: {self.raw_error[:300]}')
        lines.append(f'Fix: {self.fix}')
        if self.example:
            lines.append(f'Correct pattern:\n```python\n{self.example}\n```')
        lines.append('CRITICAL: The previous two attempts failed. This is your last try.\nUse only the simplest possible FreeCAD API path to achieve the goal.\nPrefer Part::Box / Part::Cylinder primitives over PartDesign if uncertain.')
        return '\n'.join(lines)
_ERROR_CATALOGUE: list[dict] = [{'pattern': 'has no attribute [\'\\"]Sketch[\'\\"]', 'report': ErrorReport(category='api_rename', title='Pad/Pocket uses removed .Sketch property (renamed in FreeCAD 1.0)', fix='Replace `.Sketch = sketch` with `.Profile = sketch`', example="pad = body.newObject('PartDesign::Pad', 'Pad')\npad.Profile = sketch\npad.Length = 30.0")}, {'pattern': 'has no attribute [\'\\"]Support[\'\\"]', 'report': ErrorReport(category='api_rename', title='Sketch.Support removed — use .AttachmentSupport', fix="Use `sketch.AttachmentSupport = (target_obj, 'Face6')` — takes a (obj, str) tuple", example="sketch.AttachmentSupport = (pad, 'Face6')\nsketch.MapMode = 'FlatFace'")}, {'pattern': 'has no attribute [\'\\"]ReferenceAxis[\'\\"]', 'report': ErrorReport(category='api_removed', title='.ReferenceAxis does not exist on any FreeCAD feature', fix='For revolution/groove, set `.Axis = FreeCAD.Vector(x,y,z)` on the feature directly', example="rev = body.newObject('PartDesign::Revolution', 'Rev')\nrev.Profile = sketch\nrev.Axis = FreeCAD.Vector(0, 1, 0)\nrev.Angle = 360")}, {'pattern': 'SKETCH CONSTRAINT ERROR|references geo index', 'report': ErrorReport(category='sketch_validation', title='Sketch constraint references invalid geometry index', fix='Add ALL geometry BEFORE adding constraints. Geo indices are 0-based and refer to the ORDER geometry was added. If an addConstraint call references geo index 0 but no addGeometry has been called yet, the index is out of range.\n\nCORRECT ORDER:\n  1. sketch.addGeometry(geo_list, False)  — first\n  2. sketch.addConstraint(con_list)       — second\n\nGeo index 0 = first element added, index 1 = second, etc.', example="geo_list = [Part.LineSegment(p1, p2), Part.LineSegment(p2, p3)]\nsketch.addGeometry(geo_list, False)\ncon_list = [Sketcher.Constraint('Coincident', 0, 2, 1, 1)]\nsketch.addConstraint(con_list)")}, {'pattern': 'Sketch.*invalid|sketch.*constraint|open.*wire|not.*closed', 'report': ErrorReport(category='sketch_open_profile', title='Sketch has an open profile — Pad/Pocket requires a closed wire', fix='Add Coincident constraints at every endpoint pair. Every line end must connect to the next line start. Use the PAD+FILLET approach (rectangle + post-pad fillets) instead of sketching arcs.')}, {'pattern': 'Constraint.*takes \\d+ arg|DistanceX.*5 arg|wrong.*number.*arg', 'report': ErrorReport(category='sketch_constraint_arity', title='Wrong number of arguments to Sketcher.Constraint()', fix='DistanceX/DistanceY take 3 args: (GeoIdx, VertexIdx, Value). Coincident takes 4 args: (Geo1, Pos1, Geo2, Pos2). Radius takes 2 args: (GeoIdx, Value).')}, {'pattern': 'single GeoFeatureGroup|already.*inside.*Part|belongs.*to', 'report': ErrorReport(category='geo_group_conflict', title='Object already belongs to another Part/Body', fix='Check `obj.InList` to find the current parent. Call `parent.removeObject(obj)` before adding to a new Body/Part.')}, {'pattern': 'no active document|ActiveDocument.*None', 'report': ErrorReport(category='no_document', title='No active FreeCAD document', fix="Create one first: `doc = FreeCAD.newDocument('Design')`", example="doc = FreeCAD.ActiveDocument\nif not doc:\n    doc = FreeCAD.newDocument('Design')")}, {'pattern': 'BRep.*Not.*Plane|not.*planar|not.*flat', 'report': ErrorReport(category='non_planar', title='Sketch attachment face is not planar', fix='Use a standard plane (XY/XZ/YZ) or a flat face found by iterating `pad.Shape.Faces` and checking `face.Surface` type. Never hardcode Face6 — iterate to find the correct face by its normal direction.')}, {'pattern': 'NullShape|Shape.*not.*null|no.*solid|invalid.*shape', 'report': ErrorReport(category='null_shape', title='Shape is null or non-manifold — geometry could not be built', fix='Ensure the sketch profile is fully closed and the pad length is positive. Call `doc.recompute()` after every feature. Check that boolean operands (Base/Tool) are valid solids.')}, {'pattern': 'Import.*not in the allowlist|Module.*not available.*sandbox', 'report': ErrorReport(category='blocked_import', title='Import blocked by sandbox', fix='Remove the import statement. The following are pre-loaded and available without importing: FreeCAD, FreeCADGui, Part, PartDesign, Sketcher, Mesh, Draft, Import, TechDraw, math.')}, {'pattern': 'failed to recompute|recompute.*failed', 'report': ErrorReport(category='recompute_failure', title='Model failed to recompute', fix='Call `doc.recompute()` after each feature, not just at the end. Check that all referenced objects exist before using them. Simplify — create one feature at a time.')}]
def deep_extract_freecad_error(exc: BaseException) -> str:
    def _try_extract(obj):
        if isinstance(obj, dict):
            for key in ('sErrMsg', 'message', 'msg', 'error'):
                v = obj.get(key)
                if v and isinstance(v, str) and (len(v) > 3):
                    return v.strip()
        if isinstance(obj, str) and obj.startswith('{'):
            try:
                parsed = ast.literal_eval(obj)
                return _try_extract(parsed)
            except Exception:
                pass
        return None
    candidates = []
    for arg in getattr(exc, 'args', []):
        extracted = _try_extract(arg)
        if extracted:
            candidates.append(extracted)
        elif isinstance(arg, str):
            candidates.append(arg)
    raw = str(exc)
    extracted = _try_extract(raw)
    if extracted:
        candidates.insert(0, extracted)
    else:
        candidates.append(raw)
    meaningful = [c for c in candidates if len(c) > 5 and (not c.startswith('{'))]
    return meaningful[0] if meaningful else raw
def _extract_error_location(tb_string: str) -> str:
    best = ''
    for line in tb_string.split('\n'):
        stripped = line.strip()
        if 'File "<string>"' in stripped:
            best = stripped.replace('File "<string>", ', '')
            break
        if not best and any((stripped.startswith(e) for e in ('NameError', 'AttributeError', 'TypeError', 'ValueError', 'ImportError', 'RuntimeError', 'Base::PyException'))):
            best = stripped
    return best
def build_error_report(exc: BaseException, tb_string: str, retry_tier: int=1) -> ErrorReport:
    error_text = deep_extract_freecad_error(exc)
    location = _extract_error_location(tb_string)
    for entry in _ERROR_CATALOGUE:
        if re.search(entry['pattern'], error_text, re.IGNORECASE):
            t: ErrorReport = entry['report']
            return ErrorReport(category=t.category, title=t.title, cause=error_text[:200], location=location, fix=t.fix, example=t.example, raw_error=error_text, retry_tier=retry_tier)
    cause = error_text
    if len(cause) > 200:
        cause = cause.split('\n')[0][:200]
    return ErrorReport(category='unknown', title=f'Unexpected error: {type(exc).__name__}', cause=cause, location=location, fix='Check the traceback. Simplify — use Part::Box primitives if PartDesign is failing.', raw_error=error_text, retry_tier=retry_tier)
def build_retry_prompt(user_input: str, error_report: ErrorReport, previous_code: str, scene_observation: str, attempt_number: int) -> str:
    report = error_report
    report.retry_tier = attempt_number
    sections = [f'### RETRY {attempt_number}/3 — Previous attempt failed\nOriginal task: {user_input[:200]}', report.for_ai_retry()]
    if scene_observation:
        sections.append(f'### CURRENT SCENE (after failed attempt):\n{scene_observation[:800]}')
    if attempt_number >= 2 and previous_code:
        bad = _highlight_bad_lines(previous_code, report)
        if bad:
            sections.append(f'### LINES THAT LIKELY CAUSED THE ERROR:\n```python\n{bad}\n```\nDo NOT repeat these patterns.')
    if attempt_number >= 3:
        sections.append('### FALLBACK STRATEGY (use this — all other approaches have failed)\n' + _fallback_strategy_for_category(report.category, user_input))
    sections.append("### OUTPUT RULES\n- Write COMPLETE new code, not a patch.\n- Start fresh — do not reference variable names from the previous attempt.\n- One ```python block only.\n- End with `doc.recompute()` and `FreeCADGui.SendMsgToActiveView('ViewFit')`.")
    return '\n\n'.join(sections)
def _highlight_bad_lines(code: str, report: ErrorReport) -> str:
    lines = code.splitlines()
    if not lines:
        return ''
    lineno_match = re.search('line (\\d+)', report.location or '')
    if lineno_match:
        n = int(lineno_match.group(1)) - 1
        start = max(0, n - 2)
        end = min(len(lines), n + 3)
        arrow = '→ '
        return '\n'.join((f"{(arrow if i == n else '  ')}{lines[i]}" for i in range(start, end)))
    BAD_PATTERNS = {'api_rename': ['\\.Sketch\\s*=', '\\.Support\\s*=', '\\.ReferenceAxis\\s*='], 'sketch_open_profile': ['addGeometry', 'Constraint\\('], 'bad_attribute': ['\\.\\w+\\s*='], 'blocked_import': ['^import ', '^from ']}
    patterns = BAD_PATTERNS.get(report.category, [])
    matched = []
    for line in lines:
        for pat in patterns:
            if re.search(pat, line):
                matched.append(f'  {line}')
                break
    return '\n'.join(matched[:5]) if matched else ''
def _fallback_strategy_for_category(category: str, user_input: str) -> str:
    strategies = {'sketch_validation': "You are adding constraints BEFORE adding geometry, or referencing geo indices that don't exist yet.\n\nFIX: Add ALL geometry FIRST, then ALL constraints SECOND:\n  # Step 1 — collect all geometry\n  geo_list = [Part.LineSegment(p1, p2), Part.LineSegment(p2, p3)]\n  sketch.addGeometry(geo_list, False)\n  # Step 2 — collect all constraints\n  con_list = [Sketcher.Constraint('Coincident', 0, 2, 1, 1)]\n  sketch.addConstraint(con_list)\n\nGeo index 0 = first element in geo_list, index 1 = second, etc.", 'sketch_open_profile': 'Use the PAD+FILLET pattern instead of sketching arcs:\n1. Sketch a simple rectangle (4 LineSegments + 4 Coincident constraints)\n2. Pad it\n3. Apply PartDesign::Fillet to the vertical edges for rounded corners\nDo NOT attempt to draw arcs or BSplines in the sketch.', 'api_rename': "You are on FreeCAD 1.0. API changes from 0.21:\n  • pad.Profile = sketch   (NOT pad.Sketch)\n  • sketch.AttachmentSupport = (obj, 'Face6')   (NOT sketch.Support)\nRewrite using only these property names.", 'null_shape': "Use the simplest geometry possible:\n1. doc.addObject('Part::Box', 'Box') with .Length/.Width/.Height\n2. doc.recompute() immediately after\nNo sketches, no booleans, no PartDesign until the basic shape is confirmed."}
    return strategies.get(category, f"Simplify to the minimum viable approach for: '{user_input[:100]}'\nUse Part::Box primitives. No PartDesign, no Sketcher, no booleans.")
