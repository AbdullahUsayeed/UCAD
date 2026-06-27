# orchestrator/core.py - AIOrchestrator class (extracted from god file)
import FreeCAD, FreeCADGui
import json, re, math, traceback, os, datetime, ast
from compat import QtCore
from assembly_graph import AssemblyGraph
from failure_collector import FailureCollector
from knowledge_base import KnowledgeBase
from task_step import TaskStep

# Import from sibling submodules
from .errors import build_error_report, build_retry_prompt
from .providers import (PROVIDERS, _provider_style_hint, PROVIDER_ADAPTERS,
                        LITELLM_PROVIDERS, VISION_CAPABLE, is_local_provider,
                        _provider_max_tokens, _provider_temperature)
from .local_pipeline import (build_messages_local, generate_code_local)
from .templates import render_template
from .security import _PRELOADED_MODULES, SAFE_BUILTINS, _validate_exec_code
from .executor import _DeltaCResult, _CadDagStub, ExecutionContext
from .airfoil_knowledge import AIRFOIL_KNOWLEDGE, should_inject_airfoil
from .gear_knowledge import GEAR_KNOWLEDGE, should_inject_gear
from .triangle_knowledge import TRIANGLE_KNOWLEDGE, should_inject_triangle
from .curvedshapes_knowledge import CURVEDSHAPES_KNOWLEDGE, CURVEDSHAPES_WING_BRIDGE, should_inject_curvedshapes
from .addfc_knowledge import ADDFC_KNOWLEDGE, should_inject_addfc

# ═══════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════
class AIOrchestrator(QtCore.QObject):
    def __init__(self, api_key, provider="deepseek", model=None, api_url=None, proxy_url=None):
        super().__init__()
        self.api_key = api_key
        self.provider = provider
        self.custom_model = model
        self.custom_url = api_url
        self.proxy_url = proxy_url
        self.conversation_history = []
        self._transaction_active = False
        self.macro_dir = self._get_macro_dir()
        self._prev_objects = []
        self._recompute_settled = True
        self._touched_objects = set()
        self._last_generated_code = ""
        self._last_error_tb = ""
        self._last_error_report = None
        self._retry_count = 0
        self._board_context = None
        self._dxf_context = None
        # Version detection (once at init)
        fc_ver = FreeCAD.Version()
        try:
            self._fc_major = int(fc_ver[0])
            self._fc_minor = int(fc_ver[1])
        except (IndexError, ValueError):
            self._fc_major, self._fc_minor = 0, 21
        # Knowledge base (tiered, version-aware)
        self.kb = KnowledgeBase()
        self.kb.set_version(self._fc_major, self._fc_minor)
        # Failure collector (structured logging for hot-path excepts)
        self.failures = FailureCollector()
        try:
            doc = FreeCAD.ActiveDocument
            self.assembly = AssemblyGraph(doc) if doc else None
        except Exception as ex:
            print(f"[AI] Failed to init AssemblyGraph: {ex}")
            self.assembly = None

        # Local model detection (Ollama) — switches to simpler pipeline
        self.is_local = is_local_provider(provider)
        # Per-provider tuning defaults (overridden by _apply_settings)
        self.max_tokens = _provider_max_tokens(provider)
        self.temperature = _provider_temperature(provider)

        # Sandbox config — process-level subprocess execution when True
        self.use_sandbox = True
        self.cad_dag = _CadDagStub()
        self.last_delta_c = None
        self.last_topology = None
        # Don't load old conversation on init — each session starts fresh
        
    def _get_macro_dir(self):
        try: return FreeCAD.getUserMacroDir(True)
        except Exception: return os.path.expanduser("~")
    
    def get_provider_config(self):
        default_model = PROVIDERS.get(self.provider, PROVIDERS["deepseek"])
        return (self.custom_url or None, self.custom_model or default_model, None)
    
    def set_board_context(self, filepath):
        import pcb_parser
        self._board_context = pcb_parser.parse(filepath)

    def execute_enclosure_template(self, params=None):
        """Run the enclosure template via enclosure_template.build_from_parsed.

        Args:
            params: dict with wall_thickness, floor_thickness, margin, boss_od,
                    lid_clearance, headroom_mm, lid_thickness, etc.

        Returns:
            (success: bool, message: str)
        """
        if not self._board_context:
            return False, "No board data loaded. Drop a .kicad_pcb file first."

        try:
            from enclosure_template import build_from_parsed
            if params is None:
                params = {}
            print(f"[PCB Template] Running with params: {params}")
            success, msg = build_from_parsed(self._board_context, params)
            print(f"[PCB Template] Result: {success} — {msg}")
            return success, msg
        except Exception as e:
            import traceback
            print(f"[PCB Template] Exception: {traceback.format_exc()}")
            return False, f"Template error: {type(e).__name__}: {e}"

    def refine_enclosure_from_text(self, instruction):
        """Extract parameter changes from an instruction and re-run the template.

        Example: "increase wall thickness to 3mm, add 6 vents"
        → extracts wall_thickness=3.0, vent_slots=6 → rebuilds enclosure
        """
        if not self._board_context:
            return False, "No board data loaded."
        try:
            import re
            params = {}
            wall_match = re.search(r'wall(?:\s+thickness)?\s*(?:=|is|to|:)?\s*(\d+\.?\d*)', instruction, re.IGNORECASE)
            if wall_match:
                params["wall_thickness"] = float(wall_match.group(1))
            vent_match = re.search(r'vent\w*\s*(?:count|number|slots)?\s*(?:=|is|to|:)?\s*(\d+)', instruction, re.IGNORECASE)
            if vent_match:
                params["ventilation_slots_count"] = int(vent_match.group(1))
            margin_match = re.search(r'margin\s*(?:=|is|to|:)?\s*(\d+\.?\d*)', instruction, re.IGNORECASE)
            if margin_match:
                params["margin"] = float(margin_match.group(1))
            from enclosure_template import build_from_parsed
            success, msg = build_from_parsed(self._board_context, params)
            return success, msg
        except Exception as e:
            return False, f"Refinement failed: {type(e).__name__}: {e}"

    def _format_board_data(self):
        if not self._board_context:
            return ""
        bd = self._board_context
        dims = bd["dimensions"]
        holes = bd["mounting_holes"]
        components = bd["components"]
        connectors = bd["edge_connectors"]
        tallest = max((c["height"] for c in components), default=0) if components else 0

        lines = [
            f"Board: {dims['width']}mm x {dims['height']}mm",
            f"Mounting holes: {len(holes)}",
        ]
        for h in holes:
            lines.append(f"  - at ({h['x']}, {h['y']}) diameter {h['diameter']}mm")
        lines.append(f"Edge connectors: {len(connectors)}")
        for c in connectors:
            lines.append(f"  - {c['ref']} ({c['name'][:40]}) at ({c['x']}, {c['y']}) height {c['height']}mm")
        if tallest:
            lines.append(f"Tallest component: {tallest}mm")
        lines.append("")
        lines.append("AVAILABLE TOOLS (call these, do not write raw FreeCAD API):")
        lines.append("- from enclosure_template import build_from_parsed")
        lines.append("- success, msg = build_from_parsed(board_data, params_dict)")
        lines.append("")
        lines.append("This uses enclosure_template.py which has a connector type registry with")
        lines.append("correct panel cutout dimensions: USB_A=8.5x5.0mm, USB_C=9.0x3.5mm,")
        lines.append("HDMI=15.5x6.5mm, RJ45=16.0x13.5mm, etc.")
        lines.append("")
        lines.append("NEVER write raw Part.makeBox/Part.makeCylinder for enclosure geometry.")
        return "\n".join(lines)

    def set_dxf_context(self, data):
        """Store processed DXF profile data."""
        self._dxf_context = data

    def _format_dxf_data(self):
        """Format DXF profile data with coordinates for prompt injection."""
        if not self._dxf_context:
            return ""
        profiles = self._dxf_context.get("profiles", [])
        meta = self._dxf_context.get("metadata", {})
        warnings_list = self._dxf_context.get("warnings", [])
        lines = [
            f"\n### DXF PROFILE DATA ({meta.get('profile_count', 0)} profiles, units: {meta.get('units', 'mm')})"
        ]
        lines.append(
            "Below are the 2D profiles extracted from the DXF. Each profile has a "
            "Coordinates array you can pass directly to Part.makePolygon(pts).\n"
            "DO NOT create sketches with individual LineSegments — use the coordinates "
            "as-is with Part.makePolygon() or makeWire().\n"
            "\u26a0\ufe0f COORDINATE SAFETY RULE:\n"
            "Consecutive duplicate points cause OCCError: Both points are equal.\n"
            "Before calling makePolygon, deduplicate:\n"
            "  pts = [p for i, p in enumerate(raw_pts)\n"
            "         if i == 0 or (p - raw_pts[i-1]).Length > 1e-6]\n"
            "Always check len(pts) >= 3 before calling makePolygon.\n")
        for idx, p in enumerate(profiles, 1):
            coords = p.get("coordinates", [])
            holes = p.get("holes", [])
            area = p.get("area", 0)
            bbox = p.get("bbox", [0, 0, 0, 0])
            ptype = p.get("profile_type", "unknown")
            layer = p.get("layer", "?")
            lines.append(
                f"\n  Profile {idx} (Layer '{layer}', type={ptype}): "
                f"area={area}mm², bounds=({bbox[0]:.0f},{bbox[1]:.0f})-({bbox[2]:.0f},{bbox[3]:.0f}), "
                f"{len(holes)} cutout(s)")
            # Include coordinates — compact one-line list
            MAX_VERTS = 200
            if len(coords) <= MAX_VERTS:
                coord_str = ", ".join(f"({c[0]:.3f},{c[1]:.3f})" for c in coords)
                lines.append(f"    Coordinates: [{coord_str}]")
            else:
                # Truncated representation for very large profiles
                front = coords[:50]
                back = coords[-10:]
                coord_str_front = ", ".join(f"({c[0]:.3f},{c[1]:.3f})" for c in front)
                coord_str_back = ", ".join(f"({c[0]:.3f},{c[1]:.3f})" for c in back)
                lines.append(f"    Coordinates: [{coord_str_front}, ...({len(coords)-60} omitted)..., {coord_str_back}]")
                lines.append(f"    (Profile has {len(coords)} vertices — see shortened representation above)")
            # Include hole coordinates
            for hidx, hole in enumerate(holes, 1):
                if len(hole) <= MAX_VERTS:
                    hole_str = ", ".join(f"({h[0]:.3f},{h[1]:.3f})" for h in hole)
                    lines.append(f"    Cutout {hidx}: [{hole_str}]")
                else:
                    lines.append(f"    Cutout {hidx}: ({len(hole)} vertices, omitted for length)")
        if warnings_list:
            lines.append("\nDXF warnings:")
            for w in warnings_list[:5]:
                lines.append(f"  - {w}")
        if self._dxf_context.get("metadata", {}).get("normalized"):
            lines.append(
                "\nDXF COORDINATE RULE: All DXF profile coordinates have been "
                "pre-normalized so the bounding box center is at (0, 0). "
                "Place all geometry relative to Vector(0, 0, 0). "
                "Do NOT add large offsets.")
        return "\n".join(lines)

    def build_user_prompt(self, user_input, mode="build", completed_steps=None):
        context = self.get_document_context()
        selection = self.get_selection_context()
        docs_list = self.list_documents_text()
        history = ""
        if self.conversation_history:
            history = "\n### Previous actions in this session:\n"
            for index, turn in enumerate(self.conversation_history[-8:], 1):
                status = "OK" if turn.get("success") else "FAIL"
                obs_data = turn.get("observation_data", [])
                if isinstance(obs_data, list) and obs_data:
                    if isinstance(obs_data[0], str):
                        obs = " | ".join(obs_data)
                    else:
                        obs = self.format_observation(obs_data, max_chars=250)
                else:
                    obs = ""
                code_snip = turn.get("code", "")[:120].replace("\n", " ")
                history += (
                    f"  {index}. [{status}] User: '{turn['user']}'\n"
                    f"     Code: {code_snip}\n"
                    f"     Result: {turn['result'][:200]}\n"
                )
                if obs:
                    history += f"     Scene: {obs[:250]}\n"

        workbenches = ", ".join(sorted(FreeCADGui.listWorkbenches().keys())) if hasattr(FreeCADGui, "listWorkbenches") else "N/A"
        scene_summary = self._build_scene_summary()
        relevant = self._build_relevant_objects(user_input)
        if mode == "plan":
            completed_section = ""
            if completed_steps:
                lines = ["### COMPLETED STEPS:"]
                for i, step in enumerate(completed_steps, 1):
                    if isinstance(step, TaskStep):
                        lines.append(f"  {i}. {step.title}")
                        if step.summary:
                            lines.append(f"     Scene after: {step.summary[:200]}")
                    else:
                        s0, s1 = step if len(step) == 2 else (step, "")
                        lines.append(f"  {i}. {s0}")
                        if s1:
                            lines.append(f"     Scene after: {s1[:200]}")
                completed_section = "\n".join(lines) + "\n\n"
            single_step = completed_steps is not None
            if single_step:
                plan_instruction = (
                    "Output a single step for the builder to execute next, based ONLY on objects "
                    "that exist in the current scene above.\n"
                    "Describe the target by observable properties (type, attachment, dimensions), not by name.\n"
                    "CRITICAL: The scene description below is CONTEXT ONLY. Do NOT list or describe "
                    "existing objects as steps — only output a NEW build action to perform.\n"
                    "If the request is complete (no more work needed), output exactly: DONE"
                )
            else:
                plan_instruction = (
                    "Output a concise numbered plan breaking the work into discrete build steps.\n"
                    "Each step must be a single, focused operation with specific dimensions/positions.\n"
                    "Describe targets by observable properties (type, attachment, dimensions, position, closure) "
                    "rather than Literal Names.\n"
                    "CRITICAL: The scene description below is CONTEXT ONLY. Do NOT list or describe "
                    "existing objects as numbered steps — only output NEW build actions to perform.\n"
                    "Do NOT output any Python code."
                )
            return f"""### CURRENT SCENE STATE
{scene_summary}
{relevant}
{docs_list}
{context}
{selection}
Available workbenches: {workbenches}
{history}

{completed_section}### USER REQUEST: {user_input}

### PLANNING RULES (MANDATORY):
1. BASE every step on objects actually listed in "CURRENT SCENE STATE" above.
2. DO NOT reference any object that is NOT shown in the scene state. If required geometry does not exist, the first step must create it.
3. Before each step, verify its prerequisites exist. If missing, add a step to create them first.
4. Keep steps small, single-focused, and testable — each should produce a visible result.
5. {plan_instruction}""" 
        return f"""### CURRENT SCENE STATE
{scene_summary}
{relevant}
{docs_list}
{context}
{selection}
Available workbenches: {workbenches}
{history}

### USER REQUEST: {user_input}

### EXECUTION REQUIREMENT:
- Output COMPLETE executable code for the full request in one response.
- Use one or more complete ```python blocks that can run immediately.
- Do not output step-1-only partial code.
- For simple shape requests (box/cylinder/sphere), create the final shape directly (no sketch-first workflow).

### TARGET RESOLUTION (hierarchical — try in order):
1. Selected object — if user has selected something, use it when compatible.
2. Semantic match — find objects matching the planner's description (type, attachment, dimensions).
3. Unique fallback — if exactly one object of the required type exists, use it.
4. Stop — if no unique target, explain what is missing. Do NOT guess object names.
When creating new objects, give them meaningful Names. Do not rely on defaults like "Sketch001".

### OUTPUT FORMAT:
Brief analysis (1-2 lines max), then complete ```python code block(s)."""

    RESPONSE_MODE_HEADER = """
You are an expert, autonomous FreeCAD AI Developer generating production-ready Python code for the user's active macro file (.FCMacro).

RESPONSE FORMAT RULES — follow these before doing anything else:

1. CLASSIFY the request first (internally, do not print this):
   - SIMPLE: single object, single operation, one workbench, no dependencies
     Examples: "draw a triangle", "make a box", "add a circle", "extrude this face"
   - COMPLEX: assembly, multi-part, parametric system, user asked for a plan/steps
     Examples: "design a gear housing", "build a suspension system", "create a parametric wing"

2. FOR SIMPLE REQUESTS:
   - Output a single Python code block immediately
   - No numbered steps, no plan, no explanation before the code
   - No coloring, no display modifications, no extras unless asked
   - Stop after the code block. Done.

3. FOR COMPLEX REQUESTS:
   - Ask ONE clarifying question if genuinely ambiguous
   - Otherwise output the code directly, broken into clearly commented sections
   - No theatrical numbered plans like "Step 1: I will now..."

4. ENVIRONMENT & CONTEXT:
   - Always include proper boilerplate: import FreeCAD as App, FreeCADGui as Gui
   - Check for active document or create one: doc = App.activeDocument() or App.newDocument("Macro_Doc")
   - Always finish geometry with doc.recompute() so the user sees changes instantly
   - Explicitly activate the required workbench before calling its UI methods:
     Gui.activateWorkbench("PartWorkbench")

5. COLOR SCHEME RULES (CRITICAL):
   - ShapeColor must be a tuple of 3 or 4 floats in 0-1 range, e.g. (0.8, 0.5, 0.1)
   - NEVER use hex strings (#FF0000), string names ("gold"), or integers (255, 0, 0)
   - Apply via: obj.ViewObject.ShapeColor = (r, g, b)

6. CODE PRIMACY & OUTPUT STYLE:
   - Prioritize generating functional Python code — eliminate conversational filler
   - If explanation is needed, put it as Python comments (#) inside the code block
   - Output the code block in standard markdown: ```python ... ```
   - Do not ask for confirmation — just output the code

7. NEVER:
   - Add extrusion/padding unless the user explicitly asks for a 3D solid
   - Add color or display changes unless asked
   - Output a plan when code was asked for
   - Use Part.makeExtrusion() — it does not exist
    - Output a function definition without calling it — you MUST include a call
      to the function after its definition or nothing will be created.
    - Output unnamed Part.show() calls — always assign to a named variable and use
      doc.addObject("Part::Feature", "DescriptiveName") with obj.Shape = shape
      instead of Part.show(shape). Part.show() produces unnamed objects.

"""

    def build_system_prompt(self, mode="build"):
        """Assemble the full system prompt: knowledge base + context data."""
        user_msg = getattr(self, '_last_user_input', "")
        kb = self.kb.build(user_msg, mode)
        parts = [self.RESPONSE_MODE_HEADER, kb]
        # Inject API corrections as dynamic COMMON MISTAKES
        corr = self._build_api_corrections_section()
        if corr:
            parts.append(corr)
        # Scoped knowledge — order matters for priority/exclusion
        is_airfoil = should_inject_airfoil(user_msg)
        is_gear = should_inject_gear(user_msg)
        is_curved = should_inject_curvedshapes(user_msg)

        # Scoped airfoil/NACA construction recipe (only for wing/airfoil requests)
        if is_airfoil:
            parts.append(AIRFOIL_KNOWLEDGE)
            # When both airfoil and curved shapes fire (e.g. "wing"),
            # inject the bridge note so the AI connects 2D profile → 3D surfacing
            if is_curved:
                parts.append(CURVEDSHAPES_WING_BRIDGE)
        elif is_curved:
            parts.append(CURVEDSHAPES_KNOWLEDGE)
        # Scoped gear generation recipe (only for gear/tooth requests)
        if is_gear:
            parts.append(GEAR_KNOWLEDGE)
        # Scoped triangle construction recipe (only for triangle requests)
        if should_inject_triangle(user_msg):
            parts.append(TRIANGLE_KNOWLEDGE)
        # Scoped addFC add-on manager recipe (orthogonal to all other topics)
        if should_inject_addfc(user_msg):
            parts.append(ADDFC_KNOWLEDGE)

        # Failures learned in this session
        failure_lessons = self.failures.as_prompt_section()
        if failure_lessons:
            parts.append(failure_lessons)
        # DXF context
        if self._dxf_context:
            parts.append(self._format_dxf_data())
        return "\n\n".join(parts)

    _CAD_KEYWORDS = re.compile(
        r"\b(make|create|draw|add|fillet|chamfer|extrude|cut|fuse|mirror|"
        r"revolve|loft|sweep|pad|pocket|hole|thread|helix|gear|sprocket|"
        r"rectangle|box|cube|circle|sphere|cylinder|cone|torus|tube|"
        r"polygon|hexagon|triangle|line|arc|curve|spline|pipe|"
        r"shape|object|body|sketch|draft|part|feature|face|edge|"
        r"change|move|rotate|scale|color|material|thickness|offset|"
        r"import|export|save|load|merge|split|"
        r"dimension|measure|angle|distance|length|width|height|radius|"
        r"constraint|coincident|horizontal|vertical|tangent|"
        r"shell|rib|draft|array|pattern|"
        r"bend|fold|unfold|flat|expand|"
        r"subtract|intersect|boolean|union|"
        r"larger|smaller|bigger|taller|shorter|wider|thinner|thicker"
        r")\b", re.IGNORECASE)

    def _is_cad_request(self, text):
        """Return True if the user input looks like a FreeCAD request."""
        return bool(self._CAD_KEYWORDS.search(text))

    def _build_messages_local(self, user_input, mode="build"):
        """Delegates to :func:`~.local_pipeline.build_messages_local`.
        
        If the input doesn't look like a CAD request, returns ``None``
        so the caller can show a "not a CAD request" message instead of
        wasting an LLM call."""
        self._last_user_input = user_input
        if not self._is_cad_request(user_input):
            return None
        obs = self.capture_observation()[:600]

        # Format last N history entries as compact text
        history_parts = []
        for entry in self.conversation_history[-4:]:
            inp = entry.get("user", "").strip()
            code = entry.get("code", "").strip()
            obs_data = entry.get("observation_data")
            scene_after = self.format_observation(obs_data, max_chars=300) if obs_data else ""
            result = entry.get("result", "").strip()[:80]
            if not inp and not code:
                continue
            block = f"User: {inp[:120]}"
            if scene_after:
                block += f"\nScene: {scene_after}"
            if code:
                block += f"\nCode:\n```python\n{code[:400]}\n```"
            if result:
                block += f"\nResult: {result}"
            history_parts.append(block)
        history_text = "\n\n".join(history_parts)

        return build_messages_local(user_input, obs, mode=mode,
                                    history_text=history_text)

    @staticmethod
    def _build_api_corrections_section():
        entries = AIOrchestrator.API_CORRECTIONS
        if not entries:
            return ""
        lines = ["### COMMON FREECAD API MISTAKES — avoid these:"]
        lines.append("(The AI code validator checks these before execution — write correct code to avoid retries.)\n")
        for i, e in enumerate(entries, 1):
            lines.append(f"{i}. {e['mistake']}\n   → {e['fix']}")
        return "\n".join(lines)

    # ── Context Builders ─────────────────────────────────────
    def _sketch_summary(self, obj):
        """Return sketch-specific diagnostics: solver, profiles, construction, externals."""
        try:
            parts = []
            # Solver status
            try:
                valid = obj.isValid() if hasattr(obj, "isValid") else True
                conflicts = obj.hasConflicts() if hasattr(obj, "hasConflicts") else False
                redundants = obj.hasRedundants() if hasattr(obj, "hasRedundants") else False
                if not valid:
                    parts.append("Invalid")
                if conflicts:
                    parts.append("Conflicts")
                elif redundants:
                    parts.append("Redundant")
                geo_count = getattr(obj, "GeoCount", 0) or 0
                driving = getattr(obj, "getDrivingConstraints", lambda: 0)()
                parts.append(f"{driving}c/{geo_count}g" if geo_count else "No geo")
                # Profile count from shape wires
                try:
                    if hasattr(obj, "Shape") and obj.Shape:
                        wires = getattr(obj.Shape, "Wires", [])
                        if wires:
                            parts.append(f"{len(wires)} wires")
                except Exception:
                    pass
            except Exception:
                parts.append("?")
            # Construction geometry
            try:
                geo_items = getattr(obj, "Geometry", [])
                cons_count = sum(1 for g in geo_items if getattr(g, "Construction", False))
                if cons_count:
                    parts.append(f"{cons_count} construction")
            except Exception:
                pass
            # External references
            try:
                geo_items = getattr(obj, "Geometry", [])
                ext_count = 0
                for g in geo_items:
                    try:
                        if hasattr(g, "linkedToExternal") and g.linkedToExternal():
                            ext_count += 1
                    except Exception:
                        pass
                if ext_count:
                    parts.append(f"{ext_count} external")
            except Exception:
                pass
            return "; ".join(parts) if parts else ""
        except Exception:
            return ""

    def _object_line(self, obj, prefix="- "):
        try:
            label = getattr(obj, "Label", getattr(obj, "Name", "?"))
            name = getattr(obj, "Name", "?")
            type_id = getattr(obj, "TypeId", "?")
            extras = []
            dims = []
            for prop in getattr(self, "DIMENSION_PROPS", []):
                try:
                    if hasattr(obj, prop):
                        value = getattr(obj, prop)
                        if isinstance(value, (int, float)):
                            dims.append(f"{prop}={value:.0f}")
                except Exception as ex:
                    self.failures.record("object_line.dim", ex, context=f"{name}.{prop}")
            if dims:
                extras.append(", ".join(dims))
            # Sketch-specific: attachment and solver/profile summary
            if "Sketcher::SketchObject" in type_id:
                try:
                    sup = getattr(obj, "AttachmentSupport", None)
                    if sup and len(sup) > 0:
                        ref = sup[0]
                        ref_name = getattr(ref, "Label", getattr(ref, "Name", "?"))
                        extras.append(f"on {ref_name}")
                except Exception:
                    pass
                sk_info = self._sketch_summary(obj)
                if sk_info:
                    extras.append(sk_info)
            # Body: child sketches count
            if "PartDesign::Body" in type_id:
                children = [c for c in getattr(obj, "OutList", []) if hasattr(c, "TypeId")]
                sk_count = sum(1 for c in children if "Sketcher::SketchObject" in c.TypeId)
                feat_count = sum(1 for c in children if "PartDesign" in c.TypeId and "Sketcher" not in c.TypeId)
                feat_parts = []
                if sk_count:
                    feat_parts.append(f"{sk_count} sketches")
                if feat_count:
                    feat_parts.append(f"{feat_count} features")
                if feat_parts:
                    extras.append("(" + ", ".join(feat_parts) + ")")
            ext_text = f" [{'; '.join(extras)}]" if extras else ""
            shape_text = self._shape_summary(obj)
            return f"{prefix}{label} ({name}, {type_id}){ext_text} {shape_text}".rstrip()
        except Exception as ex:
            self.failures.record("object_line", ex)
            return f"{prefix}{getattr(obj, 'Name', '?')}"

    def get_selection_context(self):
        try:
            sel = FreeCADGui.Selection.getSelection()
            if not sel:
                return ""
            lines = ["### SELECTED OBJECTS (being manipulated):"]
            for obj in sel:
                lines.append(self._object_line(obj, "  - "))
            return "\n".join(lines) + "\n"
        except Exception as ex:
            self.failures.record("selection_context", ex)
            return ""

    def get_workbench_context(self):
        try:
            wb = FreeCADGui.activeWorkbench()
            if wb:
                name = wb.menuText() if hasattr(wb, "menuText") else wb.__class__.__name__
                return f"Active workbench: {name}"
            return "Active workbench: None"
        except Exception as ex:
            self.failures.record("workbench_context", ex)
            return ""

    def get_document_context(self):
        docs = FreeCAD.listDocuments()
        if not docs:
            return "### No documents open."
        lines = [self.get_workbench_context()]
        for dname, doc in docs.items():
            is_active = " (ACTIVE)" if doc == FreeCAD.ActiveDocument else ""
            lines.append(f"### [{dname}]{is_active} - {len(doc.Objects)} objects")
            root_objs = []
            child_map = {}
            for obj in doc.Objects:
                try:
                    parents = [parent for parent in getattr(obj, "InList", []) if parent in doc.Objects]
                except Exception as ex:
                    self.failures.record("document_context.parents", ex, context=getattr(obj, "Name", "?"))
                    parents = []
                if not parents:
                    root_objs.append(obj)
                else:
                    child_map.setdefault(parents[0].Name, []).append(obj)

            def emit_tree(obj_list, depth=0):
                for item in obj_list:
                    lines.append(self._object_line(item, "  " * (depth + 1)))
                    for child in child_map.get(item.Name, []):
                        emit_tree([child], depth + 1)

            emit_tree(root_objs)
        return "\n".join(lines)

    def build_dependency_chain_context(self, user_input=""):
        """Scan assembly graph + document for dependent bodies linked to user-requested objects.
        
        Returns a formatted DEPENDENCY CHAIN section for the AI prompt, or empty string.
        """
        try:
            doc = FreeCAD.ActiveDocument
            if not doc:
                return ""
            
            parts = []
            ul = user_input.lower() if user_input else ""
            
            # 1. Assembly constraint edges matching user input
            if self.assembly and self.assembly._ready:
                self.assembly.rebuild()
                at_risk = list(dict.fromkeys(
                    name for e in self.assembly.edges
                    for name in (e.source, e.target)
                    if name.lower() in ul
                ))
                if at_risk:
                    for body_name in at_risk:
                        desc = self.assembly.describe_affected(body_name, max_depth=2)
                        if desc:
                            parts.append(desc)
                else:
                    full_desc = self.assembly.describe(max_edges=10)
                    if full_desc:
                        parts.append(full_desc)
            
            # 2. Document-level: find PartDesign Bodies whose child features reference each other
            body_feature_map = {}
            for obj in doc.Objects:
                if "PartDesign::Body" in obj.TypeId:
                    body_feature_map[obj.Label or obj.Name] = []
                    for child in obj.OutList:
                        if hasattr(child, "Profile") or "PartDesign" in child.TypeId:
                            body_feature_map[obj.Label or obj.Name].append(child.Label or child.Name)
            
            if body_feature_map and any(len(v) > 1 for v in body_feature_map.values()):
                dep_lines = ["### DEPENDENCY CHAIN (linked features within bodies):"]
                for body_name, features in body_feature_map.items():
                    if len(features) > 1:
                        dep_lines.append(f"  {body_name}: {' → '.join(features)}")
                if len(dep_lines) > 1:
                    parts.append("\n".join(dep_lines))
            
            if not parts:
                return ""
            
            return "\n\n".join(parts)
        except Exception as ex:
            self.failures.record("dependency_chain", ex)
            return ""

    def _build_scene_summary(self):
        """Compact high-level overview of the scene, placed before the detailed tree."""
        try:
            doc = FreeCAD.ActiveDocument
            if not doc:
                return "No active document."
            parts = []
            # Workbench
            try:
                wb = FreeCADGui.activeWorkbench()
                wb_name = wb.menuText() if wb and hasattr(wb, "menuText") else "Unknown"
            except Exception:
                wb_name = "Unknown"
            parts.append(f"Workbench: {wb_name}")
            # Count by type
            bodies = []
            sketches = []
            pads = []
            pockets = []
            others = []
            for obj in doc.Objects:
                tid = obj.TypeId
                if "PartDesign::Body" in tid:
                    bodies.append(obj.Label or obj.Name)
                elif "Sketcher::SketchObject" in tid:
                    sketches.append(obj.Label or obj.Name)
                elif "PartDesign::Pad" in tid:
                    pads.append(obj.Label or obj.Name)
                elif "PartDesign::Pocket" in tid:
                    pockets.append(obj.Label or obj.Name)
                else:
                    others.append((obj.Label or obj.Name, tid.split("::")[-1]))
            counts = []
            if bodies:
                counts.append(f"{len(bodies)} Bodies")
            if sketches:
                counts.append(f"{len(sketches)} Sketches")
            if pads:
                counts.append(f"{len(pads)} Pads")
            if pockets:
                counts.append(f"{len(pockets)} Pockets")
            if others:
                counts.append(f"{len(others)} Other")
            parts.append("Objects: " + ", ".join(counts))
            # Selection
            try:
                sel = FreeCADGui.Selection.getSelection()
                if sel:
                    sel_names = ", ".join(getattr(o, "Label", getattr(o, "Name", "?")) for o in sel)
                    parts.append(f"Selected: {sel_names}")
            except Exception:
                pass
            return "### SCENE OVERVIEW\n" + "\n".join(f"  {p}" for p in parts)
        except Exception as ex:
            self.failures.record("scene_summary", ex)
            return ""

    # Keyword → relevant FreeCAD types for inferring intent beyond label matching
    FEATURE_ROLES = {
        "hollow": {"types": ("PartDesign::Pad", "PartDesign::Thickness", "Part::Box", "Part::Thickness"), "weight": 8},
        "shell": {"types": ("PartDesign::Pad", "PartDesign::Thickness", "Part::Box"), "weight": 8},
        "pocket": {"types": ("PartDesign::Pad", "PartDesign::Pocket"), "weight": 6},
        "mount": {"types": ("PartDesign::Pad", "PartDesign::Pocket", "Part::Cylinder"), "weight": 6},
        "lid": {"types": ("PartDesign::Pad", "PartDesign::Pocket"), "weight": 7},
        "cover": {"types": ("PartDesign::Pad",), "weight": 6},
        "cap": {"types": ("PartDesign::Pad",), "weight": 5},
        "fillet": {"types": ("PartDesign::Pad", "PartDesign::Pocket", "Part::Box"), "weight": 4},
        "chamfer": {"types": ("PartDesign::Pad", "PartDesign::Pocket"), "weight": 4},
        "screw": {"types": ("PartDesign::Pocket", "Part::Cylinder"), "weight": 6},
        "bolt": {"types": ("PartDesign::Pocket", "Part::Cylinder"), "weight": 6},
        "thread": {"types": ("PartDesign::Pocket",), "weight": 5},
        "thicken": {"types": ("PartDesign::Pad", "Part::Box"), "weight": 5},
        "thin": {"types": ("PartDesign::Pad", "Part::Box"), "weight": 5},
        "snap": {"types": ("PartDesign::Pad", "PartDesign::Pocket", "Sketcher::SketchObject"), "weight": 5},
        "clip": {"types": ("PartDesign::Pad", "PartDesign::Pocket"), "weight": 5},
        "vent": {"types": ("PartDesign::Pocket", "Sketcher::SketchObject"), "weight": 5},
        "slot": {"types": ("PartDesign::Pocket", "Sketcher::SketchObject"), "weight": 5},
        "cutout": {"types": ("PartDesign::Pocket",), "weight": 6},
        "extrude": {"types": ("Sketcher::SketchObject", "PartDesign::Pad"), "weight": 5},
        "pad": {"types": ("Sketcher::SketchObject",), "weight": 5},
        "rib": {"types": ("Sketcher::SketchObject", "PartDesign::Pad"), "weight": 5},
        "groove": {"types": ("PartDesign::Pad", "PartDesign::Pocket"), "weight": 5},
        "hole": {"types": ("PartDesign::Pocket", "Part::Cylinder"), "weight": 5},
        "boss": {"types": ("PartDesign::Pad", "Part::Cylinder"), "weight": 5},
    }

    RELEVANCE_STOPWORDS = frozenset(
        "a an the this that these those it its my your our we they i you me"
        " do does did done make create build add remove delete modify change"
        " increase decrease grow shrink expand reduce get set put need want"
        " have has can will would should could may might must please help"
        " me with for of in on at to by and or but not is are was were"
        " be been being am mm cm m inch inches mm cm cm3 mm3"
    )

    def _build_relevant_objects(self, user_input):
        """Identify objects in the scene relevant to the user's request."""
        try:
            doc = FreeCAD.ActiveDocument
            if not doc:
                return ""
            # Collect selected objects
            selected = set()
            try:
                sel = FreeCADGui.Selection.getSelection()
                selected_names = set(getattr(o, "Name", "") for o in sel)
                for o in sel:
                    selected.add(o)
            except Exception:
                pass
            # Extract meaningful keywords from user input
            keywords = set()
            if user_input:
                for word in user_input.lower().split():
                    word = word.strip(",.!?;:'\"()[]{}")
                    if word and len(word) > 2 and word not in self.RELEVANCE_STOPWORDS:
                        keywords.add(word)
            # Score objects by relevance
            obj_scores = []
            active_body = None
            for obj in doc.Objects:
                name = getattr(obj, "Name", "")
                label = getattr(obj, "Label", "")
                type_id = getattr(obj, "TypeId", "")
                score = 0
                if name in selected_names:
                    score += 10
                if "PartDesign::Body" in type_id:
                    try:
                        if getattr(obj, "isActive", lambda: False)():
                            active_body = obj
                            score += 5
                    except Exception:
                        pass
                if keywords:
                    label_lower = label.lower()
                    name_lower = name.lower()
                    type_lower = type_id.lower()
                    for kw in keywords:
                        if kw in label_lower:
                            score += 3
                        if kw in name_lower:
                            score += 2
                        if kw in type_lower:
                            score += 1
                        # Feature-role boost: if keyword matches a known CAD operation,
                        # boost objects whose type is relevant to that operation
                        role = self.FEATURE_ROLES.get(kw)
                        if role:
                            for role_type in role["types"]:
                                if role_type in type_id:
                                    score += role["weight"]
                                    break
                if score > 0:
                    obj_scores.append((obj, score))
            # Sort by score descending
            obj_scores.sort(key=lambda x: -x[1])
            if not obj_scores:
                return ""
            lines = []
            lines.append("### RELEVANT OBJECTS")
            # Infer operation from user input
            if user_input:
                ul = user_input.lower()
                matched_ops = [kw for kw in self.FEATURE_ROLES if kw in ul]
                if matched_ops:
                    op_hints = []
                    for kw in matched_ops[:3]:
                        types_short = [t.split("::")[-1] for t in self.FEATURE_ROLES[kw]["types"][:3]]
                        op_hints.append(f"{kw} → {', '.join(types_short)}")
                    lines.append("  Operation: " + "; ".join(op_hints))
            # Selected
            if selected:
                lines.append("Selected:")
                for o in selected:
                    lines.append(f"  - {self._object_line(o, '').strip()}")
            # Top scoring unselected
            top = [o for o, s in obj_scores if o not in selected and s >= 3]
            if top:
                lines.append("Likely targets:")
                for o in top[:5]:
                    lines.append(f"  - {self._object_line(o, '').strip()}")
            # Active body (if not already listed)
            if active_body and active_body not in selected and active_body not in top:
                lines.append("Active body:")
                lines.append(f"  - {self._object_line(active_body, '').strip()}")
            # Dependent features: objects that reference top targets
            top_names = set(getattr(o, "Name", "") for o in top) | selected_names
            dependents = []
            for obj in doc.Objects:
                if getattr(obj, "Name", "") in top_names:
                    continue
                try:
                    inlist = getattr(obj, "InList", [])
                    if any(getattr(p, "Name", "") in top_names for p in inlist):
                        dependents.append(obj)
                except Exception:
                    pass
            if dependents:
                lines.append("Dependent features:")
                for o in dependents[:5]:
                    lines.append(f"  - {self._object_line(o, '').strip()}")
            return "\n".join(lines)
        except Exception as ex:
            self.failures.record("relevant_objects", ex)
            return ""

    def list_documents_text(self):
        docs = FreeCAD.listDocuments()
        if not docs:
            return "No documents open."
        lines = ["Open documents:"]
        for name, doc in docs.items():
            active = " [ACTIVE]" if doc == FreeCAD.ActiveDocument else ""
            lines.append(f"  {name}{active} - {len(doc.Objects)} objects")
        return "\n".join(lines)

    def _shape_summary(self, obj):
        """Deep geometric summary: BB, volume, area, element counts, compound info."""
        try:
            if not hasattr(obj, 'Shape') or not obj.Shape:
                return ""
            s = obj.Shape
            bb = s.BoundBox
            parts = []
            if bb.isValid():
                parts.append(f"BB({bb.XMin:.0f},{bb.YMin:.0f},{bb.ZMin:.0f})-({bb.XMax:.0f},{bb.YMax:.0f},{bb.ZMax:.0f})")
            vol = s.Volume
            if vol > 0:
                parts.append(f"V={vol:.0f}")
            area = s.Area
            if area > 0:
                parts.append(f"A={area:.0f}")
            try:
                nf = len(s.Faces)
                ne = len(s.Edges)
                nv = len(s.Vertexes)
                parts.append(f"F{nf}E{ne}V{nv}")
            except Exception as ex:
                self.failures.record("shape_summary.face_count", ex)
            try:
                st = s.ShapeType
                if st:
                    parts.append(f"type={st}")
            except Exception as ex:
                self.failures.record("shape_summary.shape_type", ex)
            return "[" + " ".join(parts) + "]" if parts else ""
        except Exception as ex:
            self.failures.record("shape_summary", ex)
        return ""

    def call_ai(self, messages, stream_callback=None):
        """Thread-safe: calls the AI API via LiteLLM.
        If stream_callback is provided, uses streaming (tokens arrive in real-time).
        stream_callback(text, type) where type is 'reasoning'|'content'|'done'|'error'."""
        adapter = PROVIDER_ADAPTERS.get(self.provider)
        if not adapter:
            print(f"[AI] Unknown provider: {self.provider}")
            return None

        default_model = PROVIDERS.get(self.provider, PROVIDERS["deepseek"])
        model = self.custom_model or default_model
        url = self.custom_url if self.custom_url else None

        try:
            result = adapter.completion(
                model, messages, api_key=self.api_key, api_url=url,
                stream=bool(stream_callback), on_token=stream_callback,
                max_tokens=self.max_tokens, temperature=self.temperature,
                proxy_url=self.proxy_url,
            )
            return result
        except Exception as ex:
            import traceback as _tb
            tb_text = _tb.format_exc()[:500]
            FreeCAD.Console.PrintError(
                f"[AI] Provider '{self.provider}' failed: {ex}\n{tb_text}\n"
            )
            self.failures.record("call_ai", ex, context=f"provider={self.provider}")
            return None

    def generate_code(self, api_msgs, stream_callback=None):
        response = self.call_ai(api_msgs, stream_callback=stream_callback)
        if response:
            # Strip think blocks before extraction — DeepSeek/Claude extended
            # thinking text can contain crash-prone keywords or fake code fences
            # that contaminate extraction and trigger false fallback switches.
            clean = self._strip_think_blocks(response)
            sketch_code = ""
            json_blocks = self.extract_json_blocks(clean)
            if json_blocks:
                from sketch_compiler import SketchCompiler
                sketch_code = SketchCompiler().compile_all(clean)

            py_blocks = self.extract_code_blocks(clean)
            if py_blocks or sketch_code:
                parts = []
                if sketch_code:
                    parts.append(sketch_code)
                if py_blocks:
                    parts.append("\n\n".join(py_blocks))
                combined = "\n\n".join(parts)
                valid, msg = self.validate_code(combined)
                if valid:
                    return response, combined, True
                try:
                    FreeCAD.Console.PrintWarning(
                        f"[AI] Code extracted but validation rejected it: {msg}\n"
                        f"[AI] Rejected code preview: {combined[:300]}\n"
                    )
                except Exception:
                    pass
            else:
                try:
                    FreeCAD.Console.PrintWarning(
                        "[AI] No code block found in AI response. "
                        f"Response preview: {clean[:400]}\n"
                    )
                except Exception:
                    pass
            return response, None, False
        return "", None, False

    @staticmethod
    def _strip_think_blocks(text):
        """Remove AI reasoning/thinking blocks that can contaminate code extraction."""
        return re.sub(
            r'<think(?:ing)?>.*?</think(?:ing)?>',
            '',
            text,
            flags=re.DOTALL | re.IGNORECASE
        )

    # ── API pattern validator ─────────────────────────────────────────
    # Catches known-wrong FreeCAD API calls before execution, preventing
    # the retry-anchor effect where the AI sees its own broken output
    # and patches only the specific error line while keeping other wrong calls.

    @staticmethod
    def _extract_api_plan(response):
        """Extract the <API_PLAN>...</API_PLAN> section from an AI response."""
        if not response:
            return ""
        m = re.search(r'<API_PLAN>\s*(.*?)\s*</API_PLAN>', response, re.DOTALL)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _build_api_plan_correction_msg(violations, user_input):
        """Build a retry prompt listing API plan violations for the AI to fix."""
        lines = [
            "### API PLAN CORRECTION REQUIRED",
            "Your <API_PLAN> section contains known-wrong FreeCAD API patterns.",
            "Fix them before writing code.",
            "",
            "Violations found:",
        ]
        for i, v in enumerate(violations, 1):
            lines.append(f"{i}. {v}")
        lines.extend([
            "",
            "Output a corrected <API_PLAN> with ALL violations fixed, then the complete Python code.",
            "Same task: " + user_input
        ])
        return "\n".join(lines)

    BANNED_PATTERNS = []  # deprecated — replaced by API_CORRECTIONS table

    # ── Canonical API correction table ──────────────────────────────
    # Single source of truth for wrong→right FreeCAD API patterns.
    # Drives: pre_validate(), translate_error(), COMMON_MISTAKES generation.
    # Context gates: "partdesign" = only validate when code uses PartDesign/Sketcher.

    API_CORRECTIONS = [
        {
            "id": "no_profile",
            "requires_context": "partdesign",
            "pre_pattern": r'\.Base\s*=(?!\s*FreeCAD)',
            "error_pattern": r"has no attribute 'Base'",
            "mistake": "`.Base` does not exist on Pad/Pocket features.",
            "fix": "Use `.Profile` to reference a sketch. Use `AttachmentSupport=(obj, ['Face6'])` to attach a sketch to a face.",
            "example": "pad.Profile = sketch\nsketch.AttachmentSupport = (pad_obj, 'Face6')",
        },
        {
            "id": "no_objects",
            "requires_context": "partdesign",
            "pre_pattern": r'\bbody\.Objects\b',
            "error_pattern": r"has no attribute 'Objects'",
            "mistake": "`.Objects` does not exist on PartDesign Body.",
            "fix": "Use `body.Group` for the ordered feature list, or `body.OutList` for all children.",
            "example": "features = body.Group  # [Sketch, Pad, Pocket, ...]",
        },
        {
            "id": "no_axis_pad",
            "requires_context": "partdesign",
            "pre_pattern": r'\.Axis\b',
            "error_pattern": r"has no attribute 'Axis'",
            "mistake": "`.Axis` only exists on Revolution, Groove, and Hole features, not on Pad/Pocket.",
            "fix": "For Pad/Pocket direction use `.Reversed = True`. For position use `.Placement.Base`.",
            "example": "pocket.Reversed = True\npocket.Placement.Base = FreeCAD.Vector(0, 0, 10)",
        },
        {
            "id": "no_refaxis",
            "requires_context": "partdesign",
            "pre_pattern": r'\.ReferenceAxis\s*=',
            "error_pattern": r"has no attribute 'ReferenceAxis'",
            "mistake": "`.ReferenceAxis` does not exist on any FreeCAD object.",
            "fix": "Use `sketch.AttachmentOffset` for rotation, or set `MapMode` correctly with `AttachmentSupport`.",
            "example": "sketch.MapMode = 'FlatFace'\nsketch.AttachmentSupport = (face_obj, 'Face1')",
        },
        {
            "id": "no_support",
            "requires_context": "partdesign",
            "pre_pattern": r'\.Support\b(?!\w)',
            "error_pattern": r"has no attribute 'Support'",
            "mistake": "`.Support` does not exist on Sketcher::SketchObject.",
            "fix": "Use `.AttachmentSupport = (target_obj, ['Face6'])` — it's a tuple of (object, subelement_list).",
            "example": "sketch.AttachmentSupport = (pad, 'Face6')  # Note: AttachmentSupport is a TUPLE, not a list.",
        },
        {
            "id": "face_object",
            "requires_context": "partdesign",
            "pre_pattern": r'\.AttachmentSupport\s*=\s*\([^)]*,\s*(?:FreeCAD\.Vector|FreeCAD\.Placement|FreeCAD\.Rotation|\w+\.Shape\b|\w+\.Edges?\b|\w+\.Faces?\b|\d+)',
            "error_pattern": r"not Part\.Face|type of second element in tuple must be str",
            "mistake": "AttachmentSupport second argument must be a STRING (face name) or list of strings, not a geometry object or vector.",
            "fix": "For face-attached sketches, use a string like 'Face6' (from iteration index). For free-floating sketches positioned in 3D space, use .Placement = FreeCAD.Placement(Vector, Rotation) or .AttachmentOffset = FreeCAD.Placement(...) instead of AttachmentSupport. AttachmentSupport = (obj, 'FaceN') ONLY for face-attached sketches.",
            "example": "# Attach to a face:\nsketch.AttachmentSupport = (pad, 'Face6')\n\n# Position a free-floating sketch in space:\nsketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0, 0, 80), FreeCAD.Rotation())",
        },
        {
            "id": "gui_recompute",
            "pre_pattern": r'(?:FreeCADGui|Gui)\.(?:active|Active)Document\(\)\.recompute',
            "error_pattern": r"'Gui\.Document' object has no attribute 'recompute'",
            "mistake": "`FreeCADGui.activeDocument().recompute()` is invalid — GUI documents have no recompute().",
            "fix": "Recompute the App document instead: `FreeCAD.ActiveDocument.recompute()`. To fit the view use `FreeCADGui.SendMsgToActiveView('ViewFit')`.",
            "example": "FreeCAD.ActiveDocument.recompute()\nFreeCADGui.SendMsgToActiveView('ViewFit')",
        },
        {
            "id": "view_default_view",
            "pre_pattern": r'\.viewDefaultView\b',
            "error_pattern": r"viewDefaultView",
            "mistake": "`viewDefaultView` is not a valid FreeCAD view method.",
            "fix": "Use `FreeCADGui.SendMsgToActiveView('ViewFit')` to fit the view, or `FreeCADGui.ActiveDocument.ActiveView.viewIsometric()` for an isometric view.",
            "example": "FreeCADGui.SendMsgToActiveView('ViewFit')",
        },
        {
            "id": "pad_type_enum",
            "requires_context": "partdesign",
            "pre_pattern": r"\.Type\s*=\s*['\"]Dimension['\"]",
            "error_pattern": r"is not part of the enumeration",
            "mistake": "`Pad.Type = 'Dimension'` is invalid — 'Dimension' is not a Pad.Type enum value.",
            "fix": "Use a valid Pad.Type: 'Length' (default), 'TwoLengths', 'ThroughAll', 'ToLast', 'ToFirst', 'UpToFace', or 'UpToShape'. For a simple extrusion just set pad.Length and leave Type as 'Length'.",
            "example": "pad.Type = 'Length'\npad.Length = 30",
        },
        {
            "id": "fcgear_not_installed",
            "requires_context": None,
            "pre_pattern": r"freecad\.gears",
            "error_pattern": r"ModuleNotFoundError.*freecad\.gears|ImportError.*freecad\.gears|init_gui.*_SUPPRESS_PATTERNS",
            "mistake": "`freecad.gears` is not usable — its init_gui crashes on this FreeCAD version.",
            "fix": "DO NOT use FCGear. Use the pure Part API involute construction (see GEAR_KNOWLEDGE). Do NOT retry importing freecad.gears.",
            "example": "# Use Part API involute construction:\nimport math, Part\n\npitch_r = teeth * module / 2\nbase_r = pitch_r * math.cos(math.radians(20))\n# ... full involute construction",
        },
        {
            "id": "curvedshapes_not_installed",
            "requires_context": None,
            "pre_pattern": r"CurvedShapes\.",
            "error_pattern": r"ModuleNotFoundError.*CurvedShapes|ImportError.*CurvedShapes",
            "mistake": "`CurvedShapes` workbench is not installed.",
            "fix": "CurvedShapes workbench is not installed. Install via Tools \u2192 Addon Manager \u2192 search 'Curved Shapes'. Fall back to Part.makeLoft([wire1, wire2], solid=True, ruled=False) for simple lofts. CRITICAL: Before calling makeCurvedArray, verify every hull wire lies in a principal plane (XY, XZ, or YZ). A wire at an arbitrary angle produces zero-volume output with no error or warning.",
            "example": "# Fallback: Part.makeLoft([profile1, profile2], solid=True, ruled=False)",
        },
        {
            "id": "addfc_no_install",
            "requires_context": None,
            "pre_pattern": r"addFC\.(?:install|run)\b",
            "error_pattern": r"addFC has no attribute 'install'|addFC has no attribute 'run'",
            "mistake": "`addFC.install()` and `addFC.run()` do not exist — addFC is a GUI-driven macro, not a library.",
            "fix": "Use `FreeCADGui.execCommand('addFC')` to launch the addFC GUI. For silent installation, use the built-in AddonManager: `FreeCADGui.addonManager().installWorkbench(...)`.",
            "example": "# Launch addFC GUI:\nFreeCADGui.execCommand('addFC')\n\n# Silent install via built-in AddonManager:\nFreeCADGui.addonManager().installWorkbench('WorkbenchName')",
        },
        {
            "id": "view_set_draw_style",
            "requires_context": None,
            "pre_pattern": r"\bsetDrawStyle\b|\.DisplayMode\s*=",
            "error_pattern": r"setDrawStyle|DisplayMode",
            "mistake": "`setDrawStyle()` does not exist. `obj.ViewObject.DisplayMode` is also NOT a settable property on most FreeCAD objects.",
            "fix": "Use the Gui ViewProvider's setTransformedShapeNodes or just skip display-modification entirely. The display mode is controlled via FreeCAD's UI (View → Draw Style), not via Python. If you must set it, use: `FreeCADGui.activeDocument().activeView().setActive(True)` — but this is unreliable across FreeCAD versions.",
            "example": "# Display mode cannot be reliably changed via Python.\n# The gear is visible by default — skip display modifications.",
        },
        {
            "id": "view_rotate_wrong_api",
            "requires_context": None,
            "pre_pattern": r"\.(?:rotate|rotateView|setRotation)\s*\(",
            "error_pattern": r"function takes at most \d+ arguments|no attribute 'rotate'|no attribute 'setRotation'",
            "mistake": "View rotation APIs like `.rotate()` or `.rotateView()` do not exist on FreeCAD view objects.",
            "fix": "Use `FreeCADGui.SendMsgToActiveView('ViewFit')` to fit the view, or set camera position via Coin3D: `cam = FreeCADGui.activeDocument().activeView().getCameraNode(); cam.position.setValue(...)`.",
            "example": "# Fit view to see object:\nFreeCADGui.SendMsgToActiveView('ViewFit')",
        },
        {
            "id": "shape_color_format",
            "requires_context": None,
            "pre_pattern": r"\.ShapeColor\s*=\s*[\"'](?:#|[A-Za-z])",
            "error_pattern": r"invalid literal for int|bad color|not a valid color",
            "mistake": "`ShapeColor` must be a tuple of 3 floats in 0-1 range, e.g. `(0.9, 0.75, 0.05)` for gold. Do NOT use hex strings `#...` or color names.",
            "fix": "Use RGB float tuples: `obj.ViewObject.ShapeColor = (0.9, 0.75, 0.05)` for gold, `(0.7, 0.7, 0.7)` for silver, `(0.3, 0.6, 1.0)` for blue.",
            "example": "obj.ViewObject.ShapeColor = (0.9, 0.75, 0.05)  # gold/brass\nobj.ViewObject.LineColor = (0.9, 0.75, 0.05)",
        },
        {
            "id": "no_make_extrusion",
            "requires_context": None,
            "pre_pattern": r"Part\.makeExtrusion",
            "error_pattern": r"has no attribute 'makeExtrusion'",
            "mistake": "`Part.makeExtrusion()` does not exist in FreeCAD.",
            "fix": "To extrude a face: `face.extrude(FreeCAD.Vector(0, 0, height))`. But for a triangle: Draft.makeWire with face=True already produces a filled face \u2014 no extrusion needed. Do not add extrusion unless the user explicitly asks for a 3D solid.",
            "example": "# Correct triangle (2D face, no extrusion):\nwire = Draft.makeWire(pts, closed=True, face=True)\ndoc.recompute()",
        },
        {
            "id": "no_part_show",
            "requires_context": None,
            "error_pattern": r"(?!)",
            "mistake": "`Part.show()` creates unnamed objects invisible in the model tree.",
            "fix": "Always use: obj = doc.addObject('Part::Feature', 'DescriptiveName'); obj.Shape = shape; obj.Label = 'DescriptiveName' This makes the object selectable and visible in the model tree.",
            "example": "# Instead of Part.show(shape):\nobj = doc.addObject('Part::Feature', 'MyObject')\nobj.Shape = shape\nobj.Label = 'MyObject'",
        },
        {
            "id": "no_regular_polygon_for_rect",
            "requires_context": None,
            "pre_pattern": r"Part::RegularPolygon",
            "error_pattern": r"(?!)",
            "mistake": "`Part::RegularPolygon` makes a regular polygon (diamond/hexagon), not a rectangle.",
            "fix": (
                "For a 2D rectangle use Draft.makeRectangle(length, width). "
                "For a 3D box use doc.addObject('Part::Box', 'Box'). "
                "Never use Part::RegularPolygon for rectangles."
            ),
            "example": "# 2D rectangle:\nDraft.makeRectangle(40, 30)\n\n# 3D box:\ndoc.addObject('Part::Box', 'Box')\ndoc.Box.Length = 40\ndoc.Box.Width = 30\ndoc.Box.Height = 20",
        },
        {
            "id": "selectable_on_viewobject",
            "requires_context": None,
            "pre_pattern": r"\.Selectable\s*=",
            "error_pattern": r"has no attribute 'Selectable'",
            "mistake": "`.Selectable` is a property of the ViewObject, not of the Body/feature itself.",
            "fix": "Use `obj.ViewObject.Selectable = False` instead of `obj.Selectable = False`. Only ViewObjects have the Selectable property.",
            "example": "body.ViewObject.Selectable = False\nbody.ViewObject.Visibility = False",
        },
    ]

    @classmethod
    def pre_validate(cls, code):
        """Return list of violation messages, or empty list if clean.
        Derives from API_CORRECTIONS for single-source maintenance.
        Context-gated patterns skip validation when code doesn't reference PartDesign."""
        has_partdesign = bool(re.search(r'\bPartDesign\b|\bSketcher\b|\bbody\.\w+', code))
        violations = []
        for entry in cls.API_CORRECTIONS:
            pre_pat = entry.get("pre_pattern")
            if not pre_pat:
                continue
            if entry.get("requires_context") == "partdesign" and not has_partdesign:
                continue
            if re.search(pre_pat, code):
                violations.append(f"{entry['mistake']} Fix: {entry['fix']}")
        return violations

    # ── Sandbox pre-flight & execution ──────────────────────────────────
    # Runs a read-only variant of generated code in a subprocess to catch
    # import errors and dangerous patterns that regex/ast layer missed.
    # Standalone scripts (no current-document dependency) can be executed
    # entirely in the sandbox via run_in_sandbox().

    def run_in_sandbox(self, code: str, timeout: int = 30) -> dict:
        """Execute *code* in a FreeCAD subprocess and return the result dict.

        Unlike ``execute_code()``, this does NOT operate on the current
        FreeCAD document. Suitable for scripts that create new geometry,
        export STEP, or run calculations without live document dependency.

        Requires ``self.use_sandbox = True``.
        """
        if not self.use_sandbox:
            return {"ok": False, "stderr": "Sandbox disabled (use_sandbox=False)"}
        try:
            from sandbox_runner import run_sandboxed
            return run_sandboxed(code, timeout=timeout)
        except Exception as ex:
            FreeCAD.Console.PrintWarning(
                f"[AICompanion] run_in_sandbox failed: {ex}\n"
            )
            return {"ok": False, "stderr": str(ex)}

    def _sandbox_preflight(self, code: str) -> str | None:
        """Run generated code through sandbox_runner validate_in_sandbox().

        Always runs AST-based static validation (fast, no subprocess).
        When ``self.use_sandbox`` is True, also runs the FreeCAD subprocess
        pre-flight check. If the subprocess is unavailable (FreeCAD not
        found, timeout, etc.), AST validation alone is used as fallback.

        Returns an error string if the code fails validation, or None
        if the code passes.
        """
        try:
            from sandbox_runner import validate_in_sandbox, validate_ast

            if self.use_sandbox:
                # Full pipeline: AST + subprocess (graceful if subprocess missing)
                result = validate_in_sandbox(code)
                if not result["ok"]:
                    stderr = result.get("stderr", "")[:300]
                    return (
                        f"Sandbox pre-flight validation failed.\n"
                        f"Exit code: {result.get('exit_code', -1)}\n"
                        f"{'Timed out' if result.get('timed_out') else ''}\n"
                        f"{stderr}"
                    )
            else:
                # Fast AST-only check — protects against banned imports/calls
                result = validate_ast(code)
                if not result["ok"]:
                    return (
                        f"Sandbox pre-flight validation failed.\n"
                        f"AST check: {result.get('stderr', 'unknown error')}"
                    )
        except Exception as ex:
            # Sandbox is a safety net, not a gate — if it fails to start
            # (e.g. freecad binary not found), log and proceed.
            FreeCAD.Console.PrintWarning(
                f"[AICompanion] Sandbox pre-flight unavailable: {ex}\n"
            )
        return None

    # ── Crash-prone code filters ─────────────────────────────────────
    # POLICY: Block specific dangerous methods, not entire classes.
    # If blocking a class, document exactly which methods make it dangerous
    # and add safe alternatives to SAFE_BSPLINE_PATTERNS.

    # Operations known to segfault FreeCAD with bad parameters
    CRASH_STRINGS = [
        "Part::Loft", "Part::Sweep", "Part::Thickness",
        "Part::Offset", "Part::Section",
        "Part.BSplineSurface",
        ".insertKnot(", ".increaseDegree(", ".setKnot(",
        ".setPole(", ".setWeight(",
    ]

    # BSpline patterns that are safe — stateless, Python-exception on bad input
    SAFE_BSPLINE_PATTERNS = [
        "interpolate(",
        "makeFilletCurve(",
    ]

    @staticmethod
    def _is_crash_prone(code: str) -> bool:
        """Check whether generated code uses crash-prone FreeCAD operations."""
        if "Part.BSplineCurve" in code:
            has_dangerous = any(s in code for s in AIOrchestrator.CRASH_STRINGS)
            has_safe = any(p in code for p in AIOrchestrator.SAFE_BSPLINE_PATTERNS)
            if has_safe and not has_dangerous:
                return False
        return any(s in code for s in AIOrchestrator.CRASH_STRINGS)

    def generate_code_safe(self, api_msgs, user_input, stream_callback=None):
        """Generate code with validation. For remote models, uses two-pass API plan validation.
        For local models, uses one-shot generation with no retry."""
        if not api_msgs:
            return "", None, False
        if self.is_local:
            return self._generate_code_local(api_msgs, stream_callback=stream_callback)

        TWO_PASS_MAX_RETRIES = 3
        api_plan_attempts = 0

        while True:
            response, code, used_api = self.generate_code(api_msgs, stream_callback=stream_callback)
            if not response:
                return "", None, False

            violations = []
            api_plan = self._extract_api_plan(response)
            if api_plan:
                violations.extend(self.pre_validate(api_plan))
            if code:
                code_violations = [v for v in self.pre_validate(code) if v not in violations]
                violations.extend(code_violations)

            if violations:
                api_plan_attempts += 1
                if api_plan_attempts <= TWO_PASS_MAX_RETRIES:
                    correction = self._build_api_plan_correction_msg(violations, user_input)
                    api_msgs = list(api_msgs) + [
                        {"role": "assistant", "content": response},
                        {"role": "user", "content": correction}
                    ]
                    v_ids = [v.split(":")[0].strip("`") if ":" in v else v[:40] for v in violations]
                    print(f"[CodeGen] API plan correction #{api_plan_attempts}: {len(violations)} violations — {', '.join(v_ids)}")
                    continue
                else:
                    v_count = len(violations)
                    print(f"[CodeGen] API plan retries exhausted ({api_plan_attempts}) — {v_count} violations unfixed, proceeding with current code")

            if code and used_api and self._is_crash_prone(code):
                trig = [s for s in self.CRASH_STRINGS if s in code]
                print(f"[CodeGen] Crash-prone patterns {trig} — using fallback for: {user_input[:80]}")
                fallback = self.get_fallback_code(user_input)
                if fallback:
                    return response, fallback, False
            return response, code, used_api

    def _generate_code_local(self, api_msgs, stream_callback=None):
        """Delegates to :func:`~.local_pipeline.generate_code_local`."""
        return generate_code_local(
            api_msgs,
            stream_callback=stream_callback,
            base_url=self.custom_url or "http://localhost:11434",
            model=self.custom_model or PROVIDERS.get(self.provider, "llama3"),
            max_tokens=self.max_tokens, temperature=self.temperature,
        )

    def extract_code_blocks(self, response):
        if not response:
            return []
        import re
        # Strategy 1: explicit python/py fence (case-insensitive), properly closed.
        blocks = re.findall(r"```[ \t]*(?:python|py)[ \t]*\r?\n?(.*?)```",
                            response, re.DOTALL | re.IGNORECASE)
        # Strategy 2: generic fenced block with no language tag or a non-json
        # language (e.g. ```Python, ```  ). Catches models that mis-tag the fence.
        if not blocks:
            for m in re.finditer(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n?(.*?)```",
                                 response, re.DOTALL):
                lang = (m.group(1) or "").lower()
                if lang == "json":
                    continue
                body = m.group(2)
                if body.strip():
                    blocks.append(body)
        # Strategy 3: python fence opened but never closed (truncated stream).
        if not blocks:
            m = re.search(r"```[ \t]*(?:python|py)[ \t]*\r?\n?(.+)",
                          response, re.DOTALL | re.IGNORECASE)
            if m:
                blocks = [m.group(1)]
        # Strategy 4: no fence at all — heuristic. Exclude any <API_PLAN> section
        # so plan-only assignment lines are not mistaken for executable code.
        if not blocks:
            cleaned = re.sub(r"<API_PLAN>.*?</API_PLAN>", "", response,
                             flags=re.DOTALL | re.IGNORECASE)
            lines = cleaned.strip().splitlines()
            py_heuristic = [l for l in lines
                           if l.strip() and (l.startswith(("import ", "from ", "def ", "class ", "#"))
                                             or "= FreeCAD" in l or "= App" in l
                                             or ".addObject(" in l or ".newObject(" in l
                                             or "doc.recompute()" in l)]
            if py_heuristic:
                blocks = ["\n".join(py_heuristic)]
        return [b.strip() for b in blocks if b.strip()]

    def extract_json_blocks(self, response):
        if not response:
            return []
        import re
        blocks = re.findall(r"```json\s*\n?(.*?)```", response, re.DOTALL)
        if not blocks:
            m = re.search(r"```json\s*\n?(.+)", response, re.DOTALL)
            if m:
                blocks = [m.group(1)]
        return [b.strip() for b in blocks if b.strip()]

    def extract_thinking(self, raw_response):
        if not raw_response:
            return ""
        for fence in ("```python", "```py"):
            idx = raw_response.find(fence)
            if idx > 0:
                return raw_response[:idx].strip()
            if idx == 0:
                return ""
        # Fallback: search for bare ``` but only if preceded by whitespace/start
        idx = raw_response.find("\n```")
        if idx > 0:
            return raw_response[:idx].strip()
        if raw_response.startswith("```"):
            return ""
        return ""

    def _is_constraint_entry(self, entry):
        """Check if an entry contains user preferences or constraints that should be permanent."""
        user_text = entry.get("user", "").lower()
        constraint_keywords = [
            "wall thickness", "always", "never", "must be", "required",
            "prefer", "use only", "don't use", "avoid", "exactly",
            "tolerance", "material", "color scheme", "standard"
        ]
        return any(kw in user_text for kw in constraint_keywords)

    def record_result(self, user_input, code, success, message, retries=0,
                      is_plan_step=False, plan_label=""):
        """Append a structured entry to conversation history and persist.
        
        For multi-step plans, call with is_plan_step=True for each step.
        Per-step entries are collapsed on persist.
        """
        try:
            obs_data = self.capture_observation_structured()
            entry = {
                "user": user_input[:200],
                "code": code[:500],
                "success": success,
                "result": message[:300],
                "observation_data": obs_data,  # structured — no truncation
                "retries": retries,
                "plan_step": is_plan_step,
                "plan_label": plan_label[:100] if plan_label else "",
                "permanent": False,
            }
            # Auto-tag constraint entries
            if self._is_constraint_entry(entry):
                entry["permanent"] = True

            self.conversation_history.append(entry)

            # Eviction: keep permanent entries, drop oldest non-permanent first
            max_hist = 5 if self.is_local else 50
            if len(self.conversation_history) > max_hist:
                temp = [e for e in self.conversation_history if e.get("permanent")]
                nonperm = [e for e in self.conversation_history if not e.get("permanent")]
                keep = max_hist - len(temp)
                keep = max(keep, 0)
                self.conversation_history = temp + nonperm[-keep:]

        except Exception as ex:
            self.failures.record("prune_history", ex)

    def _collapse_history_for_persist(self):
        """Collapse per-step entries into single entries for compact persistence."""
        collapsed = []
        buffer = []
        for entry in self.conversation_history:
            if entry.get("permanent"):
                if buffer:
                    collapsed.append(self._merge_step_buffer(buffer))
                    buffer = []
                collapsed.append(entry)
            elif entry.get("plan_step"):
                buffer.append(entry)
            else:
                if buffer:
                    collapsed.append(self._merge_step_buffer(buffer))
                    buffer = []
                collapsed.append(entry)
        if buffer:
            collapsed.append(self._merge_step_buffer(buffer))
        return collapsed

    def _merge_step_buffer(self, steps):
        """Merge a list of per-step entries into one summary entry."""
        if len(steps) == 1:
            s = steps[0]
            return {
                "user": s["user"], "code": "", "success": s["success"],
                "result": f"Completed with {steps[-1]['result']}",
                "observation_data": steps[-1].get("observation_data", []),
                "retries": sum(s.get("retries", 0) for s in steps),
                "plan_step": False,
                "plan_label": f"Plan: {steps[0].get('plan_label','')} ({len(steps)} steps)",
                "permanent": False,
            }
        first = steps[0]
        last = steps[-1]
        return {
            "user": first["user"],
            "code": "",
            "success": last["success"],
            "result": f"{len(steps)} steps, final: {last['result']}",
            "observation_data": last.get("observation_data", []),
            "retries": sum(s.get("retries", 0) for s in steps),
            "plan_step": False,
            "plan_label": f"Plan: {first.get('plan_label','')} ({len(steps)} steps)",
            "permanent": False,
        }

    def save_session(self):
        """Persist conversation history to disk (collapsed per-step entries)."""
        try:
            path = os.path.join(self.macro_dir, "ai_history.json")
            compact = self._collapse_history_for_persist()
            for entry in compact:
                obs = entry.get("observation_data", [])
                if isinstance(obs, list) and len(obs) > 10:
                    entry["observation_data"] = [o.get("summary", o.get("label",""))[:80] for o in obs[:10]]
            with open(path, "w") as f:
                json.dump(compact, f, indent=2)
        except Exception as ex:
            self.failures.record("save_session", ex)

    def load_session(self):
        """Load conversation history from disk."""
        try:
            path = os.path.join(self.macro_dir, "ai_history.json")
            if os.path.exists(path):
                with open(path) as f:
                    self.conversation_history = json.load(f)
        except Exception as ex:
            self.failures.record("load_session", ex)

    def should_replan(self, remaining_steps, observation):
        """Check if the remaining plan steps need revision after seeing the actual result.
        Returns (bool, str): (True, revised_plan_or_reason) or (False, "")."""
        if not remaining_steps:
            return False, ""
        def _title(s):
            return s.title if isinstance(s, TaskStep) else str(s)
        steps_str = "\n".join(f"{i+1}. {_title(s)}" for i, s in enumerate(remaining_steps))
        prompt = (
            f"### REMAINING PLAN:\n{steps_str}\n\n"
            f"### CURRENT SCENE AFTER LAST STEP:\n{observation[:1500]}\n\n"
            f"Are the remaining steps still correct, or do they need revision given the current state?\n"
            f"Reply with exactly one word — CONTINUE — if the plan is still valid as-is.\n"
            f"Reply with REPLAN followed by a revised numbered plan if changes are needed."
        )
        msgs = [
            {"role": "system", "content": "You are a FreeCAD planning agent. Evaluate whether a design plan needs revision."},
            {"role": "user", "content": prompt}
        ]
        try:
            resp = self.call_ai(msgs)
            if resp and "REPLAN" in resp.upper():
                new_plan = self.extract_plan(resp, min_steps=1)
                if new_plan:
                    return True, "\n".join(f"{i+1}. {s}" for i, s in enumerate(new_plan))
                return True, resp
            return False, ""
        except Exception:
            return False, ""

    def extract_plan(self, text, min_steps=1, max_steps=None):
        """Extract numbered/bulleted plan steps from AI response. Returns list of step descriptions or None.
        When max_steps is given, the returned plan is truncated to that many steps."""
        import re
        steps = []
        patterns = [
            r"^\s*(?:\d+)\s*(?:[.)]|[-–—])\s+(.+)",              # 1. do X / 1) do X / 1 - do X / 1 — do X
            r"^\s*\*\*(?:\d+)\*\*\s*(?:[.)]|[-–—])\s+(.+)",  # **1.** do X / **1)** do X / **1** - do X
            r"^\s*Step\s+(?:\d+)\s*(?:[:.)]|[-–—])\s+(.+)",     # Step 1: do X / Step 1. do X / Step 1 — do X
            r"^\s*-\s+(?:Step\s+)?(?:\d+)\s*(?:[:.)]|[-–—])\s+(.+)",  # - Step 1: do X / - Step 1 — do X
            r"^\s*#{1,6}\s+(?:Step\s+)?(?:\d+)\s*(?:[:.)]|[-–—])\s+(.+)",  # ### Step 1 — do X
            r"^\s*[-*•]\s+(.+)",                     # - do X  or  * do X  or  • do X
        ]
        for line in text.split("\n"):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            for pat in patterns:
                m = re.match(pat, line_stripped, re.IGNORECASE)
                if m:
                    step_text = m.group(1).strip().rstrip(".:;,")
                    step_text = re.sub(r"^\*\*(.+)\*\*$", r"\1", step_text).strip()
                    if step_text and len(step_text) > 3 and not step_text.startswith("```"):
                        steps.append(step_text)
                    break
        if len(steps) < max(1, int(min_steps)):
            return None
        if max_steps is not None and len(steps) > int(max_steps):
            steps = steps[:int(max_steps)]
        return steps

    # ── Request complexity classification ───────────────────────────
    def classify_request(self, user_input):
        """Lightweight rule-table classifier for request complexity.

        Returns (label, confident) where label in {'simple','medium','complex'}.
        'confident' is False when signals conflict or are ambiguous — the caller
        may then run classify_request_llm() as a tie-breaker.

        SIMPLE  → single primitive, no relations/constraints (e.g. "a box 10x5x3").
        MEDIUM  → 2-5 objects, simple relationships (stack/align/hole).
        COMPLEX → sketches, constraints, assemblies, booleans, parametric.
        """
        SIMPLE_PRIMITIVES = (
            "box", "cube", "block", "rectangle", "rectangular", "cuboid",
            "cylinder", "sphere", "ball", "cone", "torus", "tube", "pipe",
            "wedge", "prism", "pyramid", "disc", "disk", "plane",
        )
        RELATIONAL_WORDS = (
            "on top of", "on top", "above", "below", "beneath", "underneath",
            "aligned", "align", "next to", "beside", "inside", "centered on",
            "stack", "stacked", "array", "pattern", "through", "concentric",
            "offset from", "mirror", "mirrored", "hole", "holes", "with a hole",
        )
        COMPLEX_WORDS = (
            "parametric", "constrain", "constrained", "constraint", "tangent",
            "fillet", "chamfer", "sketch", "assembly", "assemble", "mate",
            "revolve", "loft", "sweep", "draft", "thread", "gear", "spline",
            "bspline", "boolean", "subtract", "union", "intersect", "pocket",
            "groove", "shell", "rib", "helix", "spring", "airfoil", "wing",
        )
        text = (user_input or "").lower().strip()
        if not text:
            return ("medium", False)
        if any(w in text for w in COMPLEX_WORDS):
            return ("complex", True)
        primitive_hits = [p for p in SIMPLE_PRIMITIVES
                          if re.search(r"\b" + re.escape(p), text)]
        if any(w in text for w in RELATIONAL_WORDS):
            # Relational language implies composition → at least MEDIUM.
            # A single primitive + relation ("box on top of table") is ambiguous.
            return ("medium", len(set(primitive_hits)) <= 1)
        if primitive_hits:
            # Several distinct primitive types implies composition → MEDIUM.
            if len(set(primitive_hits)) >= 2:
                return ("medium", False)
            return ("simple", True)
        # No recognizable primitive and no relational/complex signal → ambiguous.
        return ("medium", False)

    def classify_request_llm(self, user_input):
        """Cheap one-shot LLM tie-breaker for ambiguous requests.

        Network-only (no FreeCAD state access) → safe to call off the main
        thread. Returns 'simple' | 'medium' | 'complex'; falls back to
        'medium' on any error or unrecognized output.
        """
        try:
            msgs = [
                {"role": "system", "content": (
                    "Classify the FreeCAD modeling request into exactly one word:\n"
                    "SIMPLE = one primitive object, no relationships.\n"
                    "MEDIUM = 2-5 objects with simple relations (stack, align, a hole).\n"
                    "COMPLEX = sketches, constraints, assemblies, booleans, or parametric.\n"
                    "Reply with ONLY the single word: SIMPLE, MEDIUM, or COMPLEX."
                )},
                {"role": "user", "content": (user_input or "")[:300]},
            ]
            raw = self.call_ai(msgs)
            if not raw:
                return "medium"
            low = raw.strip().lower()
            for label in ("simple", "medium", "complex"):
                if label in low:
                    return label
            return "medium"
        except Exception:
            return "medium"

    def build_step_prompt(self, user_input, plan_steps, step_idx,
                          fresh_observation, fresh_context="",
                          prior_observation="", diff_summary=""):
        """Build messages asking the AI to generate code for one specific plan step.

        Args:
            plan_steps: list[str] or list[TaskStep]
            fresh_observation: live document state captured at request time
            fresh_context: live get_document_context() captured at request time
            prior_observation: the observation from right after the prior step ran
            diff_summary: short diff string showing what changed since last step
        """
        def _title(s):
            return s.title if isinstance(s, TaskStep) else str(s)
        # Guard against empty plan or out-of-range step index — defer() can fire
        # after _plan_steps was cleared, so this is a real crash path
        if not plan_steps or step_idx < 0 or step_idx >= len(plan_steps):
            return self.build_messages(user_input, mode="build")
        plan_text = "\n".join(f"{i+1}. {_title(s)}" for i, s in enumerate(plan_steps))
        current_step = _title(plan_steps[step_idx])
        remaining = plan_steps[step_idx+1:]
        remaining_title = f"({len(remaining)} more steps)" if remaining else ""

        # ── STEP BOUNDARY CONSTRAINT (at top so model sees it first) ──────────
        # The model has a tendency to see the full plan and "optimize" by creating
        # future-step objects in the current step's code. The constraint has to be
        # at the very top of the prompt, with an explicit anti-pattern example
        # and a self-check instruction, or the model ignores it.
        boundary_rule = f"""
### STEP BOUNDARY — HARD RULE — DO NOT VIOLATE
You are generating code for STEP {step_idx+1} ONLY.

Anti-pattern — DO NOT DO THIS:
  Creating any object whose label, type, or purpose matches a REMAINING or UPCOMING step.
  Example: if step 3 says "create cylinder", do NOT create a cylinder in step {step_idx+1}.

Self-check before returning your code:
  Every addObject(), newObject(), and Body.newObject() call must correspond
  to something explicitly described in STEP {step_idx+1}.
  If a call matches a later step — DELETE IT before returning.

Why this matters:
  Steps that create future objects cause "already exists" errors and force
  a full replan. Keep step boundaries clean.
"""

        MAX_PROMPT_CHARS = 12000  # ~3000 tokens

        # Core structure — never dropped
        prompt = (
            f"### TASK: {user_input[:200]}\n\n"
            f"### PLAN:\n{plan_text}\n\n"
            f"### STEP {step_idx+1}: {current_step}\n"
            f"{boundary_rule}\n"
        )
        if remaining:
            prompt += f"### REMAINING: {remaining_title}\n"
        if diff_summary:
            prompt += f"\n### CHANGES SINCE LAST STEP:\n{diff_summary}\n"
        prompt += "\n### CURRENT SCENE (authoritative — this is what the document looks like right now):\n"
        
        # Determine observation budget
        budget = MAX_PROMPT_CHARS - len(prompt) - 200  # reserve for trailing instructions
        
        # Stage 1: history entries (compress first)
        hist_entry = ""
        if self.conversation_history:
            recent = self.conversation_history[-3:]
            hist_lines = []
            for h in recent:
                label = h.get("plan_label", "") or h["user"][:60]
                hist_lines.append(f"{'✅' if h['success'] else '❌'} {label} → {h['result'][:80]}")
            if hist_lines:
                hist_text = "### SESSION HISTORY:\n" + "\n".join(hist_lines)
                if len(hist_text) < 800:
                    hist_entry = hist_text
                    budget -= len(hist_text)
        
        # Stage 2: scene observation (use most of remaining budget)
        scene_text = fresh_observation
        if len(scene_text) > budget:
            scene_text = scene_text[:budget-100] + "…"
        prompt += scene_text + "\n"
        remaining_ctx_budget = budget - len(scene_text)
        
        # Stage 3: fresh_context if room
        if fresh_context and remaining_ctx_budget > 200:
            ctx_text = fresh_context[:remaining_ctx_budget-100]
            prompt += f"\n{ctx_text}\n"
        
        # Stage 4: remaining steps (always include as a minimal list)
        if remaining:
            prompt += "\n### UPCOMING:\n"
            for i, s in enumerate(remaining):
                step_line = f"  {i+step_idx+2}. {s}"
                if len(prompt) + len(step_line) + 200 > MAX_PROMPT_CHARS:
                    prompt += f"  … ({len(remaining)-i} more not shown)\n"
                    break
                prompt += step_line + "\n"
        
        # Live context is authoritative instruction
        prompt += (
            f"\n### ACTION: Generate Python code for step {step_idx+1} ONLY.\n"
            f"IMPORTANT: The CURRENT SCENE above is the authoritative document state. "
            f"If anything in the history or prior observation differs, the current scene is correct.\n"
            f"TARGET RESOLUTION (try in order):\n"
            f"1. Selected object if compatible.\n"
            f"2. Object matching the step description (type, attachment, dimensions).\n"
            f"3. Only one object of required type — use it.\n"
            f"4. No unique target — explain what is missing. Do NOT guess.\n"
        )
        # Inject dependency chain so AI knows which objects must be updated together
        dep_chain = self.build_dependency_chain_context(user_input=user_input)
        if dep_chain:
            prompt += f"\n{dep_chain}\n"
        
        step_instruction = (
            "You are a FreeCAD code generator. "
            "You must output in TWO PASSES within a single response:\n\n"
            "PASS 1 — <API_PLAN> block: list every FreeCAD property/attribute "
            "assignment and method call you intend to use. One per line. "
            "No imports, no logic — just the API surface. "
            "The plan will be validated against known-wrong API patterns.\n\n"
            "PASS 2 — ```python code block: the complete implementation for this step ONLY.\n\n"
            "The code must exactly match the plan — no extra API calls. "
            "If your plan contains violations, you will receive a correction message "
            "and must regenerate both plan and code from scratch.\n\n"
            "IMPORTANT: First create any prerequisite objects the step needs "
            "(Body, Sketch, workbench activation) if they don't already exist "
            "in the CURRENT SCENE above. Then execute the step's geometry.\n"
            "TARGET RESOLUTION (try in order):\n"
            "1. Selected object if compatible.\n"
            "2. Object matching the step description (type, attachment, dimensions).\n"
            "3. Only one object of required type — use it.\n"
            "4. No unique target — explain what is missing. Do NOT guess."
        )
        msgs = [
            {"role": "system", "content": f"{step_instruction}\n\n{self.build_system_prompt('build')}"},
            {"role": "user", "content": prompt}
        ]
        if hist_entry:
            if len(prompt) + len(hist_entry) < MAX_PROMPT_CHARS + 500:
                msgs.append({"role": "user", "content": hist_entry})
        return msgs

    def capture_viewport(self):
        path = None
        try:
            import base64
            import tempfile
            ad = FreeCADGui.activeDocument()
            if not ad:
                return None
            view = ad.activeView()
            fd, path = tempfile.mkstemp(prefix="ai_viewport_", suffix=".png")
            os.close(fd)
            view.saveImage(path, 800, 600, "PNG")
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception as ex:
            self.failures.record("capture_viewport", ex)
        finally:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception as cleanup_ex:
                    self.failures.record("capture_viewport.cleanup", cleanup_ex)
        return None

    def _capture_viewport_text(self):
        """Return a compact text summary of the 3D viewport geometry.
        Works for all models — no image understanding required.
        Format: bounding box + object count + total volume."""
        try:
            doc = FreeCAD.ActiveDocument
            if not doc:
                return ""
            # o.Shape can throw even when hasattr returns True (PartDesign Body mid-recompute,
            # App::Part containers, etc.) — use per-object try/except instead of list comprehension
            objs = []
            for o in doc.Objects:
                try:
                    if hasattr(o, "Shape") and o.Shape:
                        objs.append(o)
                except Exception:
                    continue
            if not objs:
                return "No visible geometry in scene."
            bb = None
            total_volume = 0.0
            for o in objs:
                try:
                    s = o.Shape
                    if bb is None:
                        bb = s.BoundBox
                    else:
                        bb.add(s.BoundBox)
                    total_volume += s.Volume
                except Exception:
                    continue
            if bb is None:
                return f"{len(objs)} objects (no bounding box)"
            parts = [
                f"Objects: {len(objs)}",
                f"Bounds: {bb.XLength:.0f}×{bb.YLength:.0f}×{bb.ZLength:.0f} mm",
                f"Volume: {total_volume:.0f} mm³",
            ]
            return " | ".join(parts)
        except Exception:
            return ""

    # ── Building messages ──────────────────────────────────────
    def build_messages(self, user_input, retry_context=None, mode="build", completed_steps=None):
        """NOT thread-safe: captures current FreeCAD state. Must be called from main thread."""
        if self.is_local:
            return self._build_messages_local(user_input, mode=mode)

        self._last_user_input = user_input
        instruction = self.build_system_prompt(mode)
        single_step = completed_steps is not None
        plan_role = (
            "You are the CHIEF DESIGNER. Ground every step in the scene state above. "
            "Describe targets by observable properties (type, attachment, dimensions), not names. "
            "Output a single step for the builder to execute next. "
            "IMPORTANT: Each step must produce VISIBLE GEOMETRY. Never output meta-steps like "
            "'activate workbench', 'switch to PartDesign', 'select', 'create document', 'open file', "
            "'create sketch', 'close sketch', or 'attach'. "
            "The builder handles all prerequisites (sketch creation, workbench activation) automatically — "
            "you only plan CONCRETE BUILD actions (draw geometry, pad, pocket, fillet, etc.). "
            "If the request is complete, output exactly: DONE. "
            "Do NOT output code — only a single build step description or DONE."
        ) if single_step else (
            "You are the CHIEF DESIGNER. Ground every step in the scene state above. "
            "Describe targets by observable properties (type, attachment, dimensions), not names. "
            "Output a concise numbered plan. "
            "IMPORTANT: Each numbered step must produce VISIBLE GEOMETRY. Never include meta-steps like "
            "'activate workbench', 'switch to PartDesign', 'select', 'create document', 'open file', "
            "'create sketch', 'close sketch', or 'attach'. "
            "The builder handles all prerequisites (sketch creation, workbench activation) automatically. "
            "Do NOT output code."
        )
        role_label = {
            "build": "You are an autonomous FreeCAD design agent. Keep analysis brief (1-2 sentences max), then output a numbered plan listing each step.\n\nFor each step, output in TWO PASSES within a single response:\nPASS 1 — <API_PLAN> block: every FreeCAD property/attribute assignment you intend to use.\nPASS 2 — ```python code block: the complete implementation.\nThe API plan will be validated against known-wrong patterns before the code executes.\n\nCode that is cut off or truncated will NOT execute — always close your ``` fence.\n\nTARGET RESOLUTION (try in order):\n1. Selected object if compatible.\n2. Object matching the planner description (type, attachment, dimensions).\n3. Only one object of the required type — use it.\n4. No unique target — explain what is missing. Do NOT guess.\n\nFormat:\n1. First step description\n2. Second step description\n...\n\n<API_PLAN>\n... attribute assignments ...\n</API_PLAN>\n\n```python\n# Code for step 1 only\n```",
            "plan": plan_role,
            "simple": "You are a FreeCAD code generator. The request is a SINGLE simple object — do NOT output a numbered plan and do NOT split into steps.\n\nOutput in TWO PASSES within a single response:\nPASS 1 — <API_PLAN> block: every FreeCAD property/attribute assignment and method call you intend to use. One per line.\nPASS 2 — ```python code block: the complete implementation creating ONE object with sensible default dimensions if none are given.\nThe API plan will be validated against known-wrong patterns before the code executes.\n\nCode that is cut off or truncated will NOT execute — always close your ``` fence.\nEnd with doc.recompute() and FreeCADGui.SendMsgToActiveView('ViewFit').",
            "ask": "You are a FreeCAD assistant. Guide the user step by step with clear explanations. Reference relevant FreeCAD workbenches, tools, and API calls. Include short code examples in ```python blocks when they help illustrate the answer. If the user is troubleshooting, help them diagnose by asking about specific error messages or unexpected behavior. Prioritize practical solutions over theory.",
            "dxf": "You are a FreeCAD DXF agent. Read the DXF profile data below and output COMPLETE code in ```python blocks to build the requested 3D geometry from the DXF profiles.",
            "pcb": "You are a PCB enclosure design agent. Read the BOARD DATA section below. Output a single ```json block with parameter overrides for build_from_parsed(). DO NOT output Python code — the template runs automatically. Available params: wall_thickness, margin, pcb_standoff_height, headroom, screw_size, enable_vents, enable_pcb_ref, enable_snaps, enable_label_recess. Example: ```json\n{\"wall_thickness\": 3.0, \"margin\": 6.0, \"enable_pcb_ref\": true}\n```",
        }
        context_msg = {"role":"system","content":f"{role_label.get(mode, role_label['build'])}\n\n{instruction}"}
        user_prompt = self.build_user_prompt(user_input, mode=mode, completed_steps=completed_steps)
        if mode in ("build", "plan"):
            dep_chain = self.build_dependency_chain_context(user_input=user_input)
            if dep_chain:
                user_prompt += f"\n\n{dep_chain}"
        # Clarification turn: if the user's request lacks concrete dimensions,
        # tell the AI to ask clarifying questions instead of guessing values
        # (skip in "plan" mode — the chief AI is expensive and should just plan)
        if mode == "build" and not retry_context:
            ul = user_input.lower()
            has_numbers = any(c.isdigit() for c in ul)
            has_units = any(u in ul for u in ("mm", "cm", "inch", "inches", "m", "feet", "ft"))
            has_relative = any(w in ul for w in ("increase", "decrease", "add", "subtract",
                "plus", "minus", "more", "less", "higher", "lower", "taller", "shorter",
                "wider", "thicker", "thinner", "deeper", "shallower", "grow", "shrink",
                "expand", "reduce", "by "))
            if not (has_numbers or has_units or has_relative):
                clarification = (
                    "\n\n### CLARIFICATION REQUIRED\nThe user's request is vague — it does not specify concrete dimensions, "
                    "numbers, units, or relative changes (e.g. 'increase by 10mm'). Do NOT guess values. "
                    "Instead, respond with a brief question asking for the missing parameters "
                    "(e.g. 'How tall should the box be in mm?' or 'By how much should I increase the height?'). "
                    "Wait for the user to provide specific numbers before generating any code."
                )
                context_msg["content"] += clarification
        # Provider-specific style hint (e.g. weaker models need formatting reminders)
        style_hint = _provider_style_hint(self.provider)
        if style_hint:
            context_msg["content"] += f"\n\n### PROVIDER NOTE\n{style_hint}"
        # Always include text metadata about the viewport (works for all models)
        viewport_text = self._capture_viewport_text()
        if viewport_text:
            user_prompt += f"\n\n### VIEWPORT STATE\n{viewport_text}"
        # For vision-capable models, also include a base64 screenshot
        # Coerce to str — custom_model could in theory be set to a non-string by external code
        current_model = str(self.custom_model) if self.custom_model else ""
        is_vision = any(m in current_model for m in VISION_CAPABLE)
        if is_vision and FreeCADGui.activeDocument():
            b64 = self.capture_viewport()
            if b64:
                user_msg = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    ]
                }
            else:
                user_msg = {"role": "user", "content": user_prompt}
        else:
            user_msg = {"role": "user", "content": user_prompt}
        api_msgs = [context_msg, user_msg]
        if retry_context:
            report = getattr(self, '_last_error_report', None)
            if report is not None and report.title:
                scene = self.capture_observation()[:800] if hasattr(self, 'capture_observation') else ""
                retry_text = build_retry_prompt(
                    user_input=user_input,
                    error_report=report,
                    previous_code=getattr(self, '_last_generated_code', ""),
                    scene_observation=scene,
                    attempt_number=getattr(self, '_retry_count', 1),
                )
                err_msg = {"role": "user", "content": retry_text}
            else:
                err_msg = {"role":"user","content":f"Previous code failed. Analyze why, choose a different approach, output corrected code.\nWhat went wrong:\n{retry_context}\nSame task: {user_input}"}
            api_msgs.append(err_msg)
        return api_msgs

    _FORBIDDEN_PATTERNS = [
        (r'\beval\s*\(', "Direct eval() calls are blocked"),
        (r'\bexec\s*\(', "Direct exec() calls are blocked"),
        (r'\bos\.system\b', "os.system is blocked"),
        (r'\bos\.popen\b', "os.popen is blocked"),
        (r'\b__import__\b', "Direct __import__ calls are blocked — use preloaded modules"),
        (r'\bcompile\s*\(', "compile() is blocked"),
        (r'\bopen\s*\(', "open() is blocked — file I/O is not permitted"),
    ]

    def validate_code(self, code):
        try:
            ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        if len(code) > 120000:
            return False, "Generated code is too large for safe execution. Please ask for a smaller step-by-step operation."
        for pattern, msg in self._FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                return False, f"Blocked: {msg}"
        return True, "OK"

    def validate_runtime_risk(self, code):
        """Heuristic runtime guard to reduce native FreeCAD crashes on huge operations."""
        try:
            tree = ast.parse(code)
        except Exception:
            return True, ""

        MAX_RANGE = 400
        MAX_OBJECT_CREATIONS = 250
        MAX_LOOP_DEPTH = 4

        creation_count = 0
        issues = []

        def _call_name(call):
            fn = call.func
            if isinstance(fn, ast.Name):
                return fn.id
            if isinstance(fn, ast.Attribute):
                return fn.attr
            return ""

        def _is_object_creation(call):
            name = _call_name(call)
            if name in ("addObject", "newObject"):
                return True
            # Part.makeBox, Part.makeCylinder, etc.
            if name.startswith("make"):
                return True
            return False

        def _walk(node, loop_depth=0):
            nonlocal creation_count

            if isinstance(node, ast.While):
                # Guard common infinite loops
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    issues.append("Found 'while True' loop")
                loop_depth += 1
                if loop_depth > MAX_LOOP_DEPTH:
                    issues.append(f"Loop nesting deeper than {MAX_LOOP_DEPTH}")

            if isinstance(node, ast.For):
                loop_depth += 1
                if loop_depth > MAX_LOOP_DEPTH:
                    issues.append(f"Loop nesting deeper than {MAX_LOOP_DEPTH}")
                it = node.iter
                if isinstance(it, ast.Call) and _call_name(it) == "range" and it.args:
                    first = it.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, int):
                        n = first.value
                        if n > MAX_RANGE:
                            issues.append(f"range({n}) is too large")

            if isinstance(node, ast.Call):
                if _is_object_creation(node):
                    creation_count += 1

            for child in ast.iter_child_nodes(node):
                _walk(child, loop_depth)

        _walk(tree)

        if creation_count > MAX_OBJECT_CREATIONS:
            issues.append(f"Too many object creations ({creation_count})")

        if issues:
            return False, (
                "Safety guard blocked this execution because it may crash FreeCAD on complex payloads: "
                + "; ".join(issues[:3])
                + ". Please ask for smaller incremental steps."
            )
        return True, "OK"

    def validate_geometry_risk(self, code):
        """Detect crash-prone geometry operations before execution."""
        try:
            ast.parse(code)
        except Exception:
            return True, ""

        if self._is_crash_prone(code):
            found = [s for s in self.CRASH_STRINGS if s in code]
            return False, (
                "Safety guard blocked execution because these crash-prone operations "
                f"were detected: {', '.join(found)}. "
                "These operations can segfault FreeCAD with invalid parameters. "
                "Ask the user to explicitly confirm with "
                "'YES I understand the crash risk' before generating this code."
            )
        return True, "OK"

    def _get_dimension_str(self, obj):
        """Return a short string describing key dimensions of an object."""
        parts = []
        for p in self.DIMENSION_PROPS:
            v = self._get_dimension_value(obj, p)
            if v is not None:
                parts.append(f"{p}={v:.0f}")
        if hasattr(obj, 'Length') and hasattr(obj, 'TypeId') and 'PartDesign' in obj.TypeId:
            try:
                parts.append(f"Pad={float(obj.Length):.0f}")
            except Exception as ex:
                self.failures.record("get_dimension_str.pad_length", ex)
        return ", ".join(parts) if parts else ""

    def _check_geometry_bounds(self, doc):
        """Post-recompute check for spatial consistency of enclosure features.
        
        Verifies: cavity < box, standoff <= cavity depth, hole <= standoff height.
        Returns list of geometry issue strings.
        """
        issues = []
        try:
            if not doc:
                return issues
            # Find labeled objects by type
            box = cavity = None
            standoffs = []
            holes = []
            for obj in doc.Objects:
                if self._is_datum(obj):
                    continue
                label = (obj.Label or "").lower()
                name = obj.Name.lower()
                if "basebox" in label or "basebox" in name or "base_box" in label:
                    box = obj
                elif "cavity" in label or "cavity" in name:
                    cavity = obj
                elif "standoff" in label or "standoff" in name:
                    standoffs.append(obj)
                elif "screwhole" in label or "screwhole" in name or "screw_hole" in label:
                    holes.append(obj)
                elif "hole" in name and not any(k in label for k in ("datum", "origin")):
                    if obj not in holes and obj not in standoffs:
                        holes.append(obj)

            if box and cavity:
                # Cavity must be smaller than box in all dimensions
                for prop in ("Height", "Length", "Width"):
                    bv = self._get_dimension_value(box, prop)
                    cv = self._get_dimension_value(cavity, prop)
                    if bv is not None and cv is not None and cv >= bv:
                        issues.append(
                            f"Cavity.{prop}={cv:.0f} >= BaseBox.{prop}={bv:.0f} "
                            f"(cavity must be smaller than the box)"
                        )
                # Pad Length (depth) of cavity must be less than box height
                if hasattr(cavity, 'Length'):
                    try:
                        cav_depth = float(cavity.Length)
                        box_h = self._get_dimension_value(box, "Height")
                        if box_h is not None and cav_depth >= box_h:
                            issues.append(
                                f"Cavity Pad depth={cav_depth:.0f} >= Box Height={box_h:.0f}"
                            )
                    except Exception as ex:
                        self.failures.record("geometry_bounds.cavity_depth", ex)

            for s in standoffs:
                s_label = s.Label or s.Name
                s_h = self._get_dimension_value(s, "Height")
                if s_h is not None and box:
                    box_h = self._get_dimension_value(box, "Height")
                    if box_h is not None and s_h > box_h:
                        issues.append(
                            f"{s_label} Height={s_h:.0f} > BaseBox Height={box_h:.0f} "
                            f"(standoff taller than box)"
                        )
                if s_h is not None and cavity:
                    cav_d = None
                    if hasattr(cavity, 'Length'):
                        try:
                            cav_d = float(cavity.Length)
                        except Exception as ex:
                            self.failures.record("geometry_bounds.standoff_depth", ex)
                    if cav_d is None:
                        cav_d = self._get_dimension_value(cavity, "Depth")
                    if cav_d is not None and s_h > cav_d:
                        issues.append(
                            f"{s_label} Height={s_h:.0f} > Cavity depth={cav_d:.0f} "
                            f"(standoff taller than cavity)"
                        )

            for h in holes:
                h_label = h.Label or h.Name
                h_d = self._get_dimension_value(h, "Depth")
                if h_d is not None and standoffs:
                    max_so_h = max(
                        (self._get_dimension_value(so, "Height") or 0) for so in standoffs
                    )
                    if max_so_h > 0 and h_d > max_so_h:
                        issues.append(
                            f"{h_label} Depth={h_d:.0f} > standoff height={max_so_h:.0f} "
                            f"(screw hole deeper than standoff)"
                        )
        except Exception as ex:
            self.failures.record("geometry_bounds.check", ex)
        return issues

    def verify_modifications(self, user_input, code, touched_uids, pre_snapshot=None, retry_tier=1):
        """Post-execution verification: detect if code missed dependent features.
        
        After AI code modifies some objects' dimensions, this checks whether
        objects in the same dependency chain were left behind (e.g. changed
        BaseBox.Height but not Cavity depth or Standoff heights). Also checks
        geometric consistency (cavity must fit inside box, etc.).
        
        Args:
            pre_snapshot: dict from _capture_dimension_snapshot() before execution
            retry_tier: 1=missed objects only, 2=+original values, 3=+code hint
        
        Returns (is_consistent, diagnosis_str).
        """
        if not user_input or not touched_uids:
            return True, ""
        # Classify user intent
        ul = user_input.lower()
        is_relative = any(w in ul for w in ("increase", "decrease", "add", "subtract",
                                             "plus", "minus", "more", "less", "higher",
                                             "lower", "taller", "shorter", "wider",
                                             "thicker", "thinner", "deeper", "shallower",
                                             "grow", "shrink", "expand", "reduce",
                                             "by "))
        is_absolute = any(w in ul for w in ("set to", "set it to", "make it",
                                            "exactly", "precisely", "change to",
                                            "=", "equals"))
        change_kw = ["increase", "decrease", "change", "modify", "update",
                      "set", "height", "length", "width", "depth", "taller",
                      "shorter", "wider", "thicker", "deeper", "resize",
                      "scale", "dimension", "size"]
        if not any(k in ul for k in change_kw):
            return True, ""

        try:
            doc = FreeCAD.ActiveDocument
            if not doc:
                return True, ""

            # Build current observation (has deps info)
            post_obs = self.capture_observation_structured()

            # Map: obj name → entry
            obs_by_name = {}
            for e in post_obs:
                obs_by_name[e["name"]] = e

            # Map: touched UID → name and label
            touched_names = set()
            touched_labels = set()
            for uid in touched_uids:
                if "." in uid:
                    nm = uid.split(".", 1)[1]
                    touched_names.add(nm)
                    obj = doc.getObject(nm)
                    if obj:
                        touched_labels.add(obj.Label or nm)

            # Build dependency graph from observation
            child_map = {}
            for e in post_obs:
                deps = e.get("deps", {})
                parents = deps.get("parents", [])
                for p_label in parents:
                    child_map.setdefault(p_label, []).append(e)

            # For each touched object, find dependents that were NOT touched
            missed = []
            for t_name in touched_names:
                t_entry = obs_by_name.get(t_name)
                if not t_entry:
                    continue
                t_label = t_entry.get("label", t_name)
                dependents = child_map.get(t_label, [])
                for dep in dependents:
                    dep_name = dep.get("name", "")
                    if dep_name in touched_names:
                        continue
                    dep_label = dep.get("label", dep_name)
                    dep_type = dep.get("type", "")
                    dim_type = ("PartDesign" in dep_type or "Part::" in dep_type)
                    if dim_type:
                        missed.append(dep_label)

            # Also check Body-internal feature chains
            for e in post_obs:
                deps = e.get("deps", {})
                features = deps.get("features", [])
                if not features:
                    continue
                body_touched = [f for f in features if any(
                    f == obs_by_name.get(tn, {}).get("label", "") for tn in touched_names
                )]
                if body_touched and len(body_touched) < len(features):
                    body_untouched = [f for f in features if f not in body_touched
                                      and not any(f.startswith(("X-", "Y-", "Z-", "XY", "XZ", "YZ")))]
                    for f in body_untouched:
                        if f not in missed:
                            missed.append(f)

            # Geometry bounds check
            geo_issues = self._check_geometry_bounds(doc)

            # Assembly constraint violation check
            try:
                if doc:
                    if self.assembly is not None:
                        self.assembly.rebuild()
                    else:
                        self.assembly = AssemblyGraph(doc)
            except Exception as ex:
                print(f"[AI] AssemblyGraph verify rebuild failed: {ex}")
                self.assembly = None
            # Compute at-risk bodies from user input (same scan as build_dependency_chain_context)
            at_risk_bodies = []
            if user_input and self.assembly and self.assembly._ready:
                ul = user_input.lower()
                at_risk_bodies = list(dict.fromkeys(
                    name for e in self.assembly.edges
                    for name in (e.source, e.target)
                    if name.lower() in ul
                ))
            assembly_issues = self.assembly.verify(at_risk_bodies=at_risk_bodies or None) if self.assembly and self.assembly._ready else []

            # Build diagnosis
            diagnosis_parts = []

            # Intent classification
            intent_hint = ""
            if is_relative and not is_absolute:
                intent_hint = ("The user asked for a RELATIVE change (increase/decrease by X). "
                               "Compute the current value, apply the delta, then update ALL "
                               "dependent features by the same delta.")
            elif is_absolute and not is_relative:
                intent_hint = ("The user asked for an ABSOLUTE change (set to X). "
                               "Set every feature in the dependency chain to a consistent value.")

            if missed:
                msg = (f"Incomplete: touched {len(touched_names)} object(s) but missed: "
                       f"{', '.join(missed[:8])}.")
                # Add original values from pre_snapshot (tier 2+)
                if pre_snapshot and retry_tier >= 2:
                    orig_lines = []
                    for m in missed[:8]:
                        orig = pre_snapshot.get(m, {}) or {}
                        if orig:
                            vals = ", ".join(f"{p}={v:.0f}" for p, v in sorted(orig.items()))
                            orig_lines.append(f"  {m}: was {vals}")
                        else:
                            # Try finding by label in snapshot keys
                            for snap_key, snap_vals in pre_snapshot.items():
                                if m.lower() in snap_key.lower():
                                    vals = ", ".join(f"{p}={v:.0f}" for p, v in sorted(snap_vals.items()))
                                    orig_lines.append(f"  {m}: was {vals}")
                                    break
                    if orig_lines:
                        msg += "\nOriginal values before execution:\n" + "\n".join(orig_lines)
                    if retry_tier >= 3:
                        msg += ("\nFix pattern: for each missed feature, get its current value, "
                                "add the same delta applied to the touched features, and assign it:\n"
                                "  missed_obj.Height = find('missed_obj').Height + delta")
                if intent_hint:
                    msg += f"\n{intent_hint}"
                diagnosis_parts.append(msg)

            if geo_issues:
                diagnosis_parts.append(
                    "Geometry inconsistency:\n- " + "\n- ".join(geo_issues[:4])
                )

            if assembly_issues:
                diagnosis_parts.append(
                    "Constraint violations:\n- " + "\n- ".join(assembly_issues[:4])
                )

            if diagnosis_parts:
                return False, "\n\n".join(diagnosis_parts)

            return True, ""
        except Exception:
            return True, ""

    # ── Sketch Constraint Validator ────────────────────────────

    CONSTRAINT_ARITY = {
        'Coincident': 4, 'DistanceX': 3, 'DistanceY': 3, 'Distance': 5,
        'Radius': 2, 'Diameter': 2, 'Horizontal': 1, 'Vertical': 1,
        'Parallel': 2, 'Perpendicular': 2, 'Angle': 3,
        'Tangent': 2, 'Equal': 2, 'Symmetric': 6, 'Block': 1,
        'SnellsLaw': 6, 'PointOnObject': 3,
    }

    def validate_sketch_constraints(self, code):
        """Pre-execution AST validation of sketch constraint code.
        Uses sequential AST body traversal to catch geo-index ordering errors.
        Returns (is_valid, list_of_error_strings)."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return True, []

        errors = []
        list_contents = {}     # var_name -> list of item tags
        running_geo = {}       # sketch_var_name -> current geometry count
        geo_types = ('Part.LineSegment', 'Part.ArcOfCircle', 'Part.Circle',
                     'Part.BSplineCurve', 'Part.ArcOfEllipse', 'Part.ArcOfHyperbola',
                     'Part.ArcOfParabola', 'Part.Offset2D',
                     'Part.Line', 'Part.ArcOfCircle', 'Part.ArcOfEllipse',
                     'LineSegment', 'ArcOfCircle', 'Circle', 'BSplineCurve')

        def _is_geo_call(call_node):
            """Check if an ast.Call is a geometry constructor."""
            if not isinstance(call_node, ast.Call):
                return False
            fn = call_node.func
            if isinstance(fn, ast.Attribute):
                fn_repr = f"{fn.value.id}.{fn.attr}" if isinstance(fn.value, ast.Name) else fn.attr
                if any(fn_repr.endswith(t) for t in geo_types):
                    return True
            return False

        def _count_geo_in_arg(arg_node):
            """Count geometry items in an addGeometry argument."""
            if isinstance(arg_node, ast.Name) and arg_node.id in list_contents:
                return sum(1 for item in list_contents[arg_node.id] if item == 'GEO')
            if isinstance(arg_node, ast.List):
                return sum(1 for elt in arg_node.elts if _is_geo_call(elt))
            if isinstance(arg_node, ast.Call) and _is_geo_call(arg_node):
                return 1
            return 0

        def _extract_constraint_calls(arg_node):
            """Extract Constraint call nodes from an addConstraint argument."""
            results = []
            if isinstance(arg_node, ast.Name) and arg_node.id in list_contents:
                for item in list_contents[arg_node.id]:
                    if isinstance(item, tuple) and item[0] == 'CONSTRAINT':
                        results.append(item[1])
            elif isinstance(arg_node, ast.Call):
                results.append(arg_node)
            elif isinstance(arg_node, ast.List):
                for elt in arg_node.elts:
                    if isinstance(elt, ast.Call):
                        results.append(elt)
            return results

        def _count_geo_in_body(body_stmts, sketch_var):
            """Count addGeometry calls in a list of statements (for loop unrolling)."""
            count = 0
            for s in body_stmts:
                if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
                    call = s.value
                    if isinstance(call.func, ast.Attribute) and call.func.attr == 'addGeometry':
                        if isinstance(call.func.value, ast.Name) and call.func.value.id == sketch_var:
                            arg = call.args[0] if call.args else None
                            if arg is not None:
                                count += _count_geo_in_arg(arg)
            return count

        def _mark_opaque_loop(loop_stmt):
            """For non-unrollable loops, increment geo by what's visible in one iteration body."""
            for sketch_var in list(running_geo.keys()):
                per_iter = _count_geo_in_body(loop_stmt.body, sketch_var)
                if per_iter > 0:
                    running_geo[sketch_var] = running_geo.get(sketch_var, 0) + per_iter

        # Sequential traversal — execution order matters
        for stmt in tree.body:
            # name = []
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and isinstance(stmt.value, ast.List):
                        list_contents[target.id] = []

            # for x in range(N): ...  (Option B — unroll small constant loops)
            if isinstance(stmt, ast.For) and isinstance(stmt.iter, ast.Call):
                iter_fn = stmt.iter.func
                if (isinstance(iter_fn, ast.Name) and iter_fn.id == 'range'
                        and stmt.iter.args and isinstance(stmt.iter.args[0], ast.Constant)):
                    n = stmt.iter.args[0].value
                    if isinstance(n, int) and 0 < n <= 10:
                        # Unroll: for each sketch_var, count geo in loop body * n
                        for sketch_var in list(running_geo.keys()):
                            per_iter = _count_geo_in_body(stmt.body, sketch_var)
                            running_geo[sketch_var] = running_geo.get(sketch_var, 0) + per_iter * n
                        # Also track list contents from loop .append calls
                        for s in stmt.body:
                            if (isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
                                    and isinstance(s.value.func, ast.Attribute)
                                    and s.value.func.attr == 'append'
                                    and isinstance(s.value.func.value, ast.Name)):
                                lst_name = s.value.func.value.id
                                if lst_name not in list_contents or not s.value.args:
                                    continue
                                arg = s.value.args[0]
                                if _is_geo_call(arg):
                                    list_contents[lst_name].extend(['GEO'] * n)
                                elif (isinstance(arg, ast.Call) and
                                      isinstance(arg.func, ast.Attribute) and
                                      arg.func.attr == 'Constraint'):
                                    list_contents[lst_name].extend([('CONSTRAINT', arg)] * n)
                        continue
                # Fall through to opaque handling for non-unrollable loops
                # Option A — treat as opaque, skip validation inside
                _mark_opaque_loop(stmt)
                continue

            if isinstance(stmt, (ast.For, ast.While)):
                # Option A — treat as opaque, skip validation inside
                _mark_opaque_loop(stmt)
                continue

            # name.append(...) or sketch.addGeometry(...) or sketch.addConstraint(...)
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                if not isinstance(call.func, ast.Attribute):
                    continue

                # list.append(value)
                if call.func.attr == 'append' and isinstance(call.func.value, ast.Name):
                    lst_name = call.func.value.id
                    if lst_name not in list_contents or not call.args:
                        continue
                    arg = call.args[0]
                    if _is_geo_call(arg):
                        list_contents[lst_name].append('GEO')
                    elif (isinstance(arg, ast.Call) and
                          isinstance(arg.func, ast.Attribute) and
                          arg.func.attr == 'Constraint'):
                        list_contents[lst_name].append(('CONSTRAINT', arg))
                    else:
                        list_contents[lst_name].append(arg)

                # sketch.addGeometry(...)
                elif call.func.attr == 'addGeometry' and isinstance(call.func.value, ast.Name):
                    sketch_var = call.func.value.id
                    arg = call.args[0] if call.args else None
                    if arg is not None:
                        geo_added = _count_geo_in_arg(arg)
                        running_geo[sketch_var] = running_geo.get(sketch_var, 0) + geo_added

                # sketch.addConstraint(...)
                elif call.func.attr == 'addConstraint' and isinstance(call.func.value, ast.Name):
                    sketch_var = call.func.value.id
                    arg = call.args[0] if call.args else None
                    if arg is not None:
                        current_count = running_geo.get(sketch_var, 0)
                        for cnode in _extract_constraint_calls(arg):
                            self._validate_one_constraint_seq(
                                cnode, sketch_var, current_count, errors)

        return len(errors) == 0, errors

    def _validate_one_constraint_seq(self, cnode, sketch_var, geo_count, errors):
        """Validate a constraint call node against the running geo count at that point."""
        if not isinstance(cnode, ast.Call):
            return
        fn = cnode.func
        is_constraint = (
            (isinstance(fn, ast.Attribute) and fn.attr == 'Constraint')
            or (isinstance(fn, ast.Name) and fn.id == 'Constraint'))
        if not is_constraint:
            return

        args = cnode.args
        if not args:
            errors.append(f"In {sketch_var}.addConstraint(): Constraint() needs a type string. "
                          f"Usage: Sketcher.Constraint('Coincident', geo1, pos1, geo2, pos2)")
            return

        type_arg = args[0]
        if not isinstance(type_arg, ast.Constant) or not isinstance(type_arg.value, str):
            return
        ctype = type_arg.value
        arg_count = len(args) - 1
        expected = self.CONSTRAINT_ARITY.get(ctype)

        if expected is None:
            errors.append(f"In {sketch_var}.addConstraint(): Unknown constraint type '{ctype}'. "
                          f"Valid: {', '.join(sorted(self.CONSTRAINT_ARITY.keys()))}")
            return

        if arg_count != expected:
            errors.append(
                f"In {sketch_var}.addConstraint(): '{ctype}' takes {expected} arg(s) "
                f"but got {arg_count}. Signature: Sketcher.Constraint('{ctype}', ...)")
            return

        # Check vertex positions (never 0 for lines)
        pos_indices = self._constraint_pos_arg_indices(ctype)
        for i_abs, val in pos_indices:
            if i_abs < len(args):
                arg = args[i_abs]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and arg.value == 0:
                    errors.append(
                        f"In {sketch_var}.addConstraint(): Vertex position {arg.value} in arg {i_abs} "
                        f"of '{ctype}' is invalid. Use 1 (start) or 2 (end) for lines/arcs, "
                        f"3 (center) for circles.")

        # Check geo indices against running count at this point in execution
        geo_indices = self._constraint_geo_arg_indices(ctype)
        for i_abs in geo_indices:
            if i_abs < len(args):
                arg = args[i_abs]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                    val = arg.value
                    if val < 0 or val >= geo_count:
                        errors.append(
                            f"In {sketch_var}.addConstraint(): {ctype} references geo index {val} "
                            f"(arg {i_abs}) but at that point sketch has only {geo_count} geometry "
                            f"element(s) (indices 0..{geo_count-1}). "
                            f"addGeometry calls before this constraint: {geo_count}. "
                            f"You may need to reorder: add all geometry before constraints.")

    def _constraint_pos_arg_indices(self, ctype):
        """Return list of (arg_index, expected_max) for vertex-position args in a constraint type."""
        if ctype == 'Coincident':
            return [(2, 2), (4, 2)]   # args 2 and 4 are Pos1, Pos2
        if ctype in ('Distance', 'Symmetric'):
            return [(2, 2), (4, 2)]
        if ctype in ('DistanceX', 'DistanceY'):
            return [(2, 2)]
        if ctype in ('Tangent', 'Perpendicular'):
            return [(2, 2), (4, 2)]
        return []

    def _constraint_geo_arg_indices(self, ctype):
        """Return list of arg indices that are geometry references."""
        if ctype == 'Coincident':
            return [1, 3]
        if ctype == 'Radius':
            return [1]
        if ctype in ('DistanceX', 'DistanceY'):
            return [1]
        if ctype in ('Horizontal', 'Vertical', 'Block'):
            return [1]
        if ctype in ('Distance', 'Symmetric'):
            return [1, 3]
        if ctype in ('Parallel', 'Perpendicular', 'Tangent', 'Angle', 'Equal'):
            return [1, 2]
        if ctype == 'PointOnObject':
            return [1, 2]
        return []

    def validate_and_report_sketch(self, code):
        """Run sketch constraint validation and return a formatted error or None."""
        valid, errs = self.validate_sketch_constraints(code)
        if valid:
            return None
        msg = "### SKETCH CONSTRAINT ERROR(S) — fix before execution:\n"
        for e in errs:
            msg += f"- {e}\n"
        msg += ("\nCheck the SKETCH CONSTRAINT REFERENCE in the system prompt for correct argument patterns. "
                "Remember: vertex indices for lines are 1=start, 2=end (never 0). "
                "Add all geometry BEFORE adding constraints.")
        return msg

    def _count_objects(self):
        docs = FreeCAD.listDocuments()
        return {n: len(d.Objects) for n, d in docs.items()}



    # ── Dimension Sanity Checks ───────────────────────────────
    DIMENSION_PROPS = {"Height", "Length", "Width", "Radius", "Depth", "Thickness"}

    def _get_dimension_value(self, obj, prop):
        """Safely get a numeric dimension property from an object, or None."""
        try:
            val = getattr(obj, prop, None)
            if val is not None:
                return float(val)
        except Exception as ex:
            self.failures.record("get_dimension_value.getattr", ex)
        # Check Pad/Pocket Length
        try:
            if hasattr(obj, 'Length') and prop in ("Height", "Depth"):
                return float(obj.Length)
        except Exception as ex:
            self.failures.record("get_dimension_value.length", ex)
        return None

    def validate_dimension_sanity(self, code, user_input=""):
        """Pre-execution check: flag physically unreasonable dimension assignments.
        
        Detects when the AI blindly converts units (e.g. 50cm → 500mm) for a context
        where the value is obviously wrong (e.g. 500mm tall PCB enclosure).
        
        Returns (safe, warning_message).
        """
        try:
            tree = ast.parse(code)
        except Exception:
            return True, ""

        # Find all assignments to dimensional properties
        assignments = []  # [(lineno, obj_var, prop, value)]
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        prop_name = target.attr
                        if prop_name in self.DIMENSION_PROPS:
                            val = None
                            if isinstance(node.value, ast.Constant):
                                val = node.value.value
                            elif isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
                                if isinstance(node.value.operand, ast.Constant):
                                    val = -node.value.operand.value
                            if val is not None and isinstance(val, (int, float)):
                                base = target.value
                                var = ""
                                if isinstance(base, ast.Name):
                                    var = base.id
                                elif isinstance(base, ast.Attribute):
                                    var = base.attr
                                assignments.append((node.lineno, var, prop_name, float(val)))

        if not assignments:
            return True, ""

        # Get current document context for size comparison
        warnings = []
        try:
            doc = FreeCAD.ActiveDocument
            existing_max = 0.0
            existing_min = float('inf')
            if doc:
                for obj in doc.Objects:
                    if self._is_datum(obj):
                        continue
                    for p in self.DIMENSION_PROPS:
                        v = self._get_dimension_value(obj, p)
                        if v is not None:
                            existing_max = max(existing_max, v)
                            existing_min = min(existing_min, v)
        except Exception:
            existing_max = 0.0
            existing_min = float('inf')

        for lineno, var, prop, val in assignments:
            # Absolute magnitude check: > 500mm on small objects is suspicious
            if val > 500 and existing_max > 0 and existing_max < 60:
                desc = f"{var}.{prop}" if var else prop
                warnings.append(
                    f"Line {lineno}: {desc} = {val}mm is very large (>500mm) while existing "
                    f"objects are ~{existing_max:.0f}mm. If the user specified cm, verify "
                    f"the conversion (e.g. 5cm → 50mm is correct; 50cm → 5000mm would be wrong)."
                )
            # Disproportionate change: new value > 20x any existing dimension
            if existing_min != float('inf') and val > existing_max * 20 and existing_max > 0:
                desc = f"{var}.{prop}" if var else prop
                if not any(f"Line {lineno}: {desc}" in w for w in warnings):
                    warnings.append(
                        f"Line {lineno}: {desc} = {val}mm is >20x larger than any existing "
                        f"dimension ({existing_max:.0f}mm). This is likely a unit error."
                    )
            # Specific enclosure context: cavity > box or standoff > cavity
            if var and prop in ("Height", "Length", "Width", "Depth"):
                try:
                    if doc:
                        obj = doc.getObject(var)
                        if obj is None:
                            for o in doc.Objects:
                                if o.Label == var or o.Name.lower() == var.lower():
                                    obj = o
                                    break
                        if obj and hasattr(obj, prop):
                            current = float(getattr(obj, prop))
                            ratio = val / current if current > 0 else float('inf')
                            if ratio > 10 and current > 0:
                                warnings.append(
                                    f"Line {lineno}: {var}.{prop} changes from {current:.0f}mm to "
                                    f"{val:.0f}mm ({ratio:.0f}x increase). If this is a relative "
                                    f"change (e.g. 'increase by X'), compute current+X instead."
                                )
                except Exception as ex:
                    self.failures.record("validate_dimension_sanity.match", ex)

        if warnings:
            return False, "⚠️ DIMENSION SANITY CHECK:\n" + "\n".join(warnings[:3])
        return True, ""

    def _capture_dimension_snapshot(self):
        """Snapshot of all objects' dimensional properties before execution.
        
        Stored as dict[object_name_or_label][prop_name] = float_value.
        Used by verify_modifications to report original values in retry context.
        """
        try:
            doc = FreeCAD.ActiveDocument
            if not doc:
                return {}
            snap = {}
            for obj in doc.Objects:
                if self._is_datum(obj):
                    continue
                key = obj.Label or obj.Name
                props = {}
                for p in self.DIMENSION_PROPS:
                    v = self._get_dimension_value(obj, p)
                    if v is not None:
                        props[p] = v
                if hasattr(obj, 'TypeId') and 'PartDesign' in obj.TypeId:
                    for fp in ("Length", "Depth"):
                        try:
                            v = float(getattr(obj, fp, 0))
                            if v > 0:
                                props[fp] = v
                        except Exception as ex:
                            self.failures.record("capture_snapshot.length", ex)
                if props:
                    snap[key] = props
            # Include assembly constraint snapshot
            try:
                if doc:
                    if self.assembly is not None:
                        self.assembly.rebuild()
                    else:
                        self.assembly = AssemblyGraph(doc)
                    if self.assembly._ready:
                        asm_snap = self.assembly.snapshot()
                        if asm_snap:
                            snap["__assembly__"] = asm_snap
            except Exception as ex:
                print(f"[AI] AssemblyGraph snapshot failed: {ex}")
            return snap
        except Exception:
            return {}

    def _save_checkpoint(self):
        """Save a timestamped copy of the active document before AI execution.
        
        Creates checkpoint files in <tempdir>/aifc_checkpoints/.
        Keeps the last 5 checkpoints per document to avoid unbounded disk use.
        Stores the path in self._last_checkpoint for backtracking recovery.
        This is the last line of defense against C++ segfaults inside FreeCAD
        that bypass Python's exception handling entirely.
        """
        import tempfile, os, glob, time
        self._last_checkpoint = None
        try:
            doc = FreeCAD.ActiveDocument
            if not doc:
                return
            ck_dir = os.path.join(tempfile.gettempdir(), "aifc_checkpoints")
            os.makedirs(ck_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (doc.Label or doc.Name))
            path = os.path.join(ck_dir, f"{safe_name}_{ts}.FCStd")
            doc.saveCopy(path)
            self._last_checkpoint = path
            # Keep only the 5 most recent checkpoints for this document
            prefix = os.path.join(ck_dir, f"{safe_name}_")
            existing = sorted((p for p in glob.glob(prefix + "*.FCStd")), reverse=True)
            for old in existing[5:]:
                try:
                    os.remove(old)
                except Exception as ex:
                    self.failures.record("checkpoint.cleanup", ex, context=str(old))
        except Exception as ex:
            print(f"[AI] Checkpoint save failed (non-fatal): {ex}")

    def execute_code(self, code, user_input="", extra_scope=None, skip_validation=False):
        if not skip_validation:
            # Pre-execution syntax and runtime-risk validation
            valid, msg = self.validate_code(code)
            if not valid:
                return False, msg
            safe, risk_msg = self.validate_runtime_risk(code)
            if not safe:
                return False, risk_msg
            # Pre-execution geometry crash risk validation
            geo_safe, geo_msg = self.validate_geometry_risk(code)
            if not geo_safe:
                return False, geo_msg
            # Pre-execution sketch constraint validation
            sketch_err = self.validate_and_report_sketch(code)
            if sketch_err:
                return False, sketch_err
            # Pre-execution dimension sanity check
            dim_safe, dim_warn = self.validate_dimension_sanity(code, user_input)
            if not dim_safe:
                return False, dim_warn
            # Pre-execution API pattern validation — catch known-wrong FreeCAD calls
            api_violations = self.pre_validate(code)
            if api_violations:
                return False, (
                    "Pre-execution API validation failed. These patterns are known-wrong "
                    "FreeCAD API calls:\n" +
                    "\n".join(f"  • {v}" for v in api_violations)
                )

            # Pre-flight sandbox validation — runs a read-only variant in a subprocess
            # to catch import errors and dangerous patterns that regex layer missed.
            sandbox_err = self._sandbox_preflight(code)
            if sandbox_err:
                return False, sandbox_err

        self._touched_objects = set()
        self._pre_execution_snapshot = self._capture_dimension_snapshot()
        self._save_checkpoint()

        old_doc_names = set(FreeCAD.listDocuments().keys())
        old_doc_name = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
        old_counts = self._count_objects()
        _initial_obj_count = len(FreeCAD.ActiveDocument.Objects) if FreeCAD.ActiveDocument else 0
        available = {}
        for mod_name in ["Part", "Sketcher", "SketcherGui", "Mesh", "Draft", "Import", "Export",
                         "SheetMetal", "Fasteners", "Assembly", "TechDraw"]:
            try:
                available[mod_name] = __import__(mod_name)
            except Exception as ex:
                self.failures.record("execute_code.module_import", ex, context=mod_name)
        from enclosure_builder import EnclosureBuilder
        from enclosure_template import (BoardData, EnclosureConfig, Component,
                                        MountingHole, build_from_parsed,
                                        CONNECTOR_TYPES)
        from enclosure_templates import build_enclosure_from_params
        from drawing_generator import DrawingGenerator
        from geometry_contract import GeometryContract
        from context_injector import precompute, PrecomputedGeometry

        def resolve_obj(name_or_label, doc=None):
            """Find object by exact name/label, case-insensitive match, or type fallback."""
            d = doc or FreeCAD.ActiveDocument
            if not d:
                return None
            obj = d.getObject(name_or_label)
            if obj:
                return obj
            for o in d.Objects:
                if o.Label == name_or_label:
                    return o
            for o in d.Objects:
                if o.Name.lower() == name_or_label.lower() or o.Label.lower() == name_or_label.lower():
                    return o
            return None

        doc = FreeCAD.ActiveDocument
        if doc is None:
            return False, "No active document. Please open or create a FreeCAD document first."
        scope = {
            "__builtins__": SAFE_BUILTINS,
            "__name__": "__main__",
            "App": FreeCAD, "Gui": FreeCADGui, "Base": FreeCAD,
            "FreeCAD": FreeCAD, "FreeCADGui": FreeCADGui,
            "doc": doc, "math": math,
            "Vector": FreeCAD.Vector, "Units": FreeCAD.Units,
            "Rotation": FreeCAD.Rotation, "Placement": FreeCAD.Placement,
            "find": resolve_obj,
            "EnclosureBuilder": EnclosureBuilder,
            "build_from_parsed": build_from_parsed,
            "build_enclosure_from_params": build_enclosure_from_params,
            "BoardData": BoardData,
            "EnclosureConfig": EnclosureConfig,
            "Component": Component,
            "MountingHole": MountingHole,
            "CONNECTOR_TYPES": CONNECTOR_TYPES,
            "DrawingGenerator": DrawingGenerator,
            "GeometryContract": GeometryContract,
            "precompute": precompute,
            "PrecomputedGeometry": PrecomputedGeometry,
            "board_data": self._board_context,
            **available,
            "doc_name": FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None,
            "_wb": FreeCADGui.listWorkbenches() if hasattr(FreeCADGui, 'listWorkbenches') else {},
        }
        if extra_scope:
            scope.update(extra_scope)
        # Patch Part.show() to work in the sandbox (normally imports PartGui internally)
        if "Part" in scope and hasattr(scope["Part"], 'show'):
            _orig_part_show = scope["Part"].show
            def _safe_part_show(shape, name="Shape"):
                doc = FreeCAD.ActiveDocument
                if doc is None:
                    return _orig_part_show(shape, name) if _orig_part_show else None
                obj = doc.addObject("Part::Feature", name)
                obj.Shape = shape
                doc.recompute()
                return obj
            scope["Part"].show = _safe_part_show
        self._last_generated_code = code
        self._begin_transaction()
        ctx = ExecutionContext()
        ctx.snapshot()
        try:
            # Capture pre-execution object state for touched tracking
            pre_obs = self.capture_observation_structured()
            pre_uids = set()
            pre_hashes = {}
            for o in pre_obs:
                uid = o["uid"]
                pre_uids.add(uid)
                pre_hashes[uid] = o.get("shape_hash", None)

            # Auto-fix: wrap doc in a proxy that redirects PartDesign features
            # to body.newObject — works regardless of variable name (doc, d, mydoc, etc.)
            _body_for_fix = None
            for o in (FreeCAD.ActiveDocument.Objects if FreeCAD.ActiveDocument else []):
                if 'PartDesign::Body' in o.TypeId:
                    if hasattr(o, 'Group') and o.Group:
                        _body_for_fix = o  # body with features is best
                        break
                    if _body_for_fix is None:
                        _body_for_fix = o  # first empty body as fallback
            if _body_for_fix and 'doc' in scope and scope['doc'] is not None:
                class _DocProxy:
                    def __init__(self, real_doc, fix_body):
                        self._real = real_doc
                        self._body = fix_body
                    def addObject(self, ptype, name, *args):
                        if (isinstance(ptype, str) and ptype.startswith('PartDesign::')
                                and any(ptype.endswith(t) for t in ('Pad','Pocket','Revolution','Groove','Hole'))):
                            return self._body.newObject(ptype, name)
                        return self._real.addObject(ptype, name, *args)
                    def __getattr__(self, name):
                        return getattr(self._real, name)
                scope['doc'] = _DocProxy(scope['doc'], _body_for_fix)
                # Also rewrite FreeCAD/App.ActiveDocument.addObject to hit the proxy
                code = re.sub(
                    r'(?:FreeCAD|App)\.ActiveDocument\.addObject\((["\'])PartDesign::(Pad|Pocket|Revolution|Groove|Hole)\1',
                    r'doc.addObject(\1PartDesign::\2\1',
                    code
                )

            import io, sys
            _exec_stdout = io.StringIO()
            _exec_stderr = io.StringIO()
            _exec_old_stdout = sys.stdout
            _exec_old_stderr = sys.stderr
            _exec_old_excepthook = sys.excepthook
            _exec_unhandled = None
            def _exec_excepthook(typ, val, tb):
                nonlocal _exec_unhandled
                _exec_unhandled = f"{typ.__name__}: {val}"
            sys.excepthook = _exec_excepthook
            sys.stdout = _exec_stdout
            sys.stderr = _exec_stderr
            # Strip imports for modules that are already preloaded in scope
            _import_pat = re.compile(
                r'^\s*(?:import\s+(?:' + '|'.join(re.escape(m) for m in _PRELOADED_MODULES) + r')'
                r'(?:\s*,\s*(?:' + '|'.join(re.escape(m) for m in _PRELOADED_MODULES) + r'))*'
                r'|from\s+(?:' + '|'.join(re.escape(m) for m in _PRELOADED_MODULES) + r')\s+import\s+)'
                r'.*$',
                re.MULTILINE
            )
            code = _import_pat.sub('', code)
            _validate_exec_code(code)
            print(f"[execute_code] Running code ({len(code)} chars):")
            for i, line in enumerate(code.splitlines()[:5], 1):
                print(f"  L{i}: {line}")
            print(f"  ... ({len(code.splitlines())} total lines)")
            try:
                exec(code, scope)
            finally:
                sys.stdout = _exec_old_stdout
                sys.stderr = _exec_old_stderr
                sys.excepthook = _exec_old_excepthook
            doc = FreeCAD.ActiveDocument
            if doc:
                if not self.force_sync_recompute(initial_object_count=_initial_obj_count):
                    self.failures.record("execute_code.recompute", None,
                        context=f"timeout waiting for recompute after {_initial_obj_count} initial objects")
                from compat import QtWidgets
                QtWidgets.QApplication.processEvents()
                # Force all objects visible in the viewport
                for o in doc.Objects:
                    if hasattr(o, 'ViewObject') and o.ViewObject:
                        o.ViewObject.Visibility = True
                # Force body visibility
                for o in doc.Objects:
                    if 'PartDesign::Body' in o.TypeId and hasattr(o, 'ViewObject') and o.ViewObject:
                        o.ViewObject.Visibility = True
                # Restore pre-execution UI state (workbench, selection, edit mode)
                ctx.restore()
                # Flush GUI events so FreeCAD viewport actually updates
                try:
                    from compat import QtWidgets
                    QtWidgets.QApplication.processEvents()
                except Exception as ex:
                    self.failures.record("execute_code.process_events", ex)
            # Track which objects this execution touched (for diff noise filtering)
            post_obs = self.capture_observation_structured()
            touched = set()
            post_uids = set()
            for o in post_obs:
                uid = o["uid"]
                post_uids.add(uid)
                if uid not in pre_uids:
                    touched.add(uid)  # newly created
                elif pre_hashes.get(uid) != o.get("shape_hash", None):
                    touched.add(uid)  # shape changed (catches transient side effects)
            self._touched_objects = touched
            new_doc_names = set(FreeCAD.listDocuments().keys())
            new_docs = new_doc_names - old_doc_names
            if new_docs:
                names = ", ".join(sorted(new_docs))
                # Ensure new document has an active viewport
                for dname in new_docs:
                    try:
                        gdoc = FreeCADGui.getDocument(dname)
                        if gdoc:
                            FreeCADGui.setActiveDocument(gdoc)
                            if gdoc.ActiveView:
                                gdoc.ActiveView.viewAxometric()
                                gdoc.ActiveView.fitAll()
                    except Exception as ex:
                        self.failures.record("execute_code.new_doc_gui", ex, context=dname)
                self._commit_transaction()
                return True, f"Created doc(s): {names}"
            new_doc_name = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
            if old_doc_name and new_doc_name and old_doc_name != new_doc_name:
                self._commit_transaction()
                return True, f"Switched to '{new_doc_name}'"
            new_counts = self._count_objects()
            total_created = 0
            new_objs = []
            for dname, cnt in new_counts.items():
                old_cnt = old_counts.get(dname, 0)
                diff = cnt - old_cnt
                if diff > 0:
                    total_created += diff
                    d = FreeCAD.listDocuments()[dname]
                    new_objs.extend([o.Label for o in d.Objects[-diff:]])
            if total_created > 0:
                self._commit_transaction()
                return True, f"Created {total_created}: {', '.join(new_objs[-5:])}"
            # No new objects — check if existing objects were modified
            self._commit_transaction()
            if self._touched_objects:
                return True, "Done (modified existing objects)"
            # Truly nothing happened — code likely has a silent error.
            # Harvest any captured exception, stdout, or stderr to give a useful diagnosis.
            _exec_output = _exec_stdout.getvalue()
            _exec_err_output = _exec_stderr.getvalue()
            _clues = []
            if _exec_unhandled:
                _clues.append(f"Unhandled exception: {_exec_unhandled}")
            if _exec_err_output:
                _clues.append(f"stderr: {_exec_err_output[:500].strip()}")
            if _exec_output:
                _trimmed = _exec_output[:500].strip()
                if any(kw in _trimmed.lower() for kw in ("error", "fail", "exception", "invalid", "warning", "traceback")):
                    _clues.append(f"stdout: {_trimmed}")
            # Also check if recompute reported failures
            _recompute_errors = []
            if doc and hasattr(doc, 'Objects'):
                for o in doc.Objects:
                    if hasattr(o, 'State') and o.State:
                        _recompute_errors.append(f"'{o.Label}': {o.State}")
            if _recompute_errors:
                _clues.append(f"Recompute errors: {'; '.join(_recompute_errors[:5])}")
            if not _clues:
                _clues.append("Code executed successfully but produced no visible changes")
            return False, "Code ran but created nothing and modified nothing. " + " | ".join(_clues)
        except BaseException as e:
            self._abort_transaction()
            tb = traceback.format_exc()
            self._last_error_tb = tb
            print(f"[AI] Error: {e}\n{tb}")

            retry_tier = getattr(self, '_retry_count', 0) + 1
            report = build_error_report(e, tb, retry_tier=retry_tier)
            self._last_error_report = report

            return False, report.for_ui()

    def _begin_transaction(self):
        doc = FreeCAD.ActiveDocument
        if doc and hasattr(doc, 'openTransaction'):
            doc.openTransaction("AICompanion")

    def _commit_transaction(self):
        doc = FreeCAD.ActiveDocument
        if doc and hasattr(doc, 'commitTransaction'):
            doc.commitTransaction()

    def _abort_transaction(self):
        doc = FreeCAD.ActiveDocument
        if doc and hasattr(doc, 'abortTransaction'):
            doc.abortTransaction()

    def save_macro(self, code, name=None):
        try:
            if not name:
                name = f"AI_Macro_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            path = os.path.join(self.macro_dir, f"{name}.FCMacro")
            with open(path, 'w') as f:
                f.write(f"# AI Copilot Macro — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
                f.write(code)
            return True, path
        except Exception as e:
            return False, str(e)

    def get_fallback_code(self, user_input, mid_plan=False):
        if mid_plan:
            return ""
        pl = user_input.lower()
        if any(w in pl for w in ["undo", "rollback", "revert"]):
            return self._gen_undo_code()
        if any(w in pl for w in ["new file","new document","new doc","create document","create file"]):
            return self._gen_newdoc_code(user_input)
        for name in ["bracket", "flange", "pipe", "gear", "triangle", "curvedshapes", "addfc"]:
            if name in pl:
                code = render_template(name)
                if code:
                    return code
                break
        if any(w in pl for w in ["wing", "airfoil", "aircraft", "aerofoil"]):
            chord = 200
            thickness = 20
            return f"""import FreeCAD
doc = FreeCAD.ActiveDocument if FreeCAD.ActiveDocument else FreeCAD.newDocument("Wing")
import Part
# Airfoil section: extruded NACA-like profile using safe Part::Box as base
# Using simple primitives to avoid BSpline/Loft segfault risk
body = doc.addObject("Part::Box", "WingRoot")
body.Length = {thickness}
body.Width = {chord}
body.Height = 100
body.ViewObject.ShapeColor = (0.7, 0.7, 0.7)
doc.recompute()
# Tapered tip
tip = doc.addObject("Part::Box", "WingTip")
tip.Length = {thickness} / 3
tip.Width = {chord} * 0.3
tip.Height = 100
tip.Placement.Base = (0, 0, 900)
tip.ViewObject.ShapeColor = (0.7, 0.7, 0.7)
doc.recompute()
# Loft between root and tip for tapered wing
loft = doc.addObject("Part::Loft", "WingLoft")
loft.Sections = [body.Shape, tip.Shape]
loft.Solid = True
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""
        # Simple dimension extraction: "100x60x40" or "100 by 60 by 40"
        dims = re.findall(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:x|by|\*|×)\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:x|by|\*|×)\s*(\d+(?:\.\d+)?)", pl, re.IGNORECASE)
        if dims:
            dim1, dim2, dim3 = float(dims[0][0]), float(dims[0][1]), float(dims[0][2])
        elif re.search(r"radius.*?(\d+(?:\.\d+)?)", pl, re.IGNORECASE):
            dim1 = dim2 = float(re.search(r"radius.*?(\d+(?:\.\d+)?)", pl, re.IGNORECASE).group(1)) * 2
            dim3 = dim1
        else:
            dim1, dim2, dim3 = 100, 60, 40
        # Enclosure / box with lid / mounting bosses / snap-fit
        if any(w in pl for w in ["enclosure", "enclos", "mounting boss", "snap.fit", "electronic box"]):
            return f"""import FreeCAD, Part
doc = FreeCAD.ActiveDocument if FreeCAD.ActiveDocument else FreeCAD.newDocument("Enclosure")
W, D, H = {dim1}, {dim2}, {dim3}
WT = 2.0
# Shell (Part.Shape operations — same pattern as EnclosureBuilder)
outer = Part.makeBox(W, D, H)
inner = Part.makeBox(W - 2*WT, D - 2*WT, H - WT, FreeCAD.Vector(WT, WT, WT))
shell = outer.cut(inner)
# Mounting bosses (4x corners)
for x, y in [(5,5), (W-5,5), (5,D-5), (W-5,D-5)]:
    boss = Part.makeCylinder(3, 8, FreeCAD.Vector(x, y, WT))
    shell = shell.fuse(boss)
# USB-C slot on left face
slot = Part.makeBox(4, 9, 3, FreeCAD.Vector(-1, D/2 - 4.5, H/2 - 1.5))
shell = shell.cut(slot)
# Add to document
base = doc.addObject("Part::Feature", "Base")
base.Shape = shell
base.ViewObject.ShapeColor = (0.75, 0.75, 0.75)
# Lid with snap-fit lip
lid_shape = Part.makeBox(W, D, 3, FreeCAD.Vector(0, 0, H))
lip_shape = Part.makeBox(W - 4, D - 4, WT, FreeCAD.Vector(2, 2, H - WT))
lid_shape = lid_shape.fuse(lip_shape)
lid = doc.addObject("Part::Feature", "Lid")
lid.Shape = lid_shape
lid.ViewObject.ShapeColor = (0.55, 0.75, 1.0)
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""
        if any(w in pl for w in ["cylinder","tube","pipe","round"]):
            r = dim1 / 2 if dim1 < 500 else dim1
            h = dim2 if dim2 != dim1 else dim3
            return f"""import FreeCAD, Part, Sketcher, math
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Design")
body = doc.addObject("PartDesign::Body", "Body")
sketch = body.newObject("Sketcher::SketchObject", "Sketch")
geo = [Part.Circle(FreeCAD.Vector(0,0), FreeCAD.Vector(0,0,1), {r})]
sketch.addGeometry(geo)
sketch.addConstraint([Sketcher.Constraint('Radius', 0, {r})])
doc.recompute()
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = sketch
pad.Length = {h}
doc.recompute()
body.ViewObject.ShapeColor = (0.3, 0.6, 1.0)
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""
        if any(w in pl for w in ["sphere","ball","globe","orb"]):
            r = dim1 / 2
            return f"""import FreeCAD, Part, Sketcher, math
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Design")
body = doc.addObject("PartDesign::Body", "Body")
sketch = body.newObject("Sketcher::SketchObject", "Sketch")
# Half-circle profile for revolution
arc = Part.ArcOfCircle(
    Part.Circle(FreeCAD.Vector(0,0), FreeCAD.Vector(0,0,1), {r}),
    0, math.radians(180))
line = Part.LineSegment(FreeCAD.Vector({r}, 0), FreeCAD.Vector(-{r}, 0))
geo = [arc, line]
sketch.addGeometry(geo)
sketch.addConstraint([
    Sketcher.Constraint('Coincident', 0, 1, 1, 1),
    Sketcher.Constraint('Coincident', 0, 2, 1, 2),
    Sketcher.Constraint('Horizontal', 1),
    Sketcher.Constraint('DistanceX', 0, 3, 0.0),
    Sketcher.Constraint('DistanceY', 0, 3, 0.0),
])
doc.recompute()
rev = body.newObject("PartDesign::Revolution", "Revolution")
rev.Profile = sketch
rev.Angle = 360
doc.recompute()
body.ViewObject.ShapeColor = (0.3, 0.6, 1.0)
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""
        if any(w in pl for w in ["gridfinity", "grid"]):
            return self._gen_gridfinity_code(pl)
        return f"""import FreeCAD, Part, Sketcher
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Design")
body = doc.addObject("PartDesign::Body", "Body")
body.Label = "Body"
sketch = body.newObject("Sketcher::SketchObject", "Sketch")
geo = [
    Part.LineSegment(FreeCAD.Vector(-{dim1}/2, -{dim2}/2), FreeCAD.Vector({dim1}/2, -{dim2}/2)),
    Part.LineSegment(FreeCAD.Vector({dim1}/2, -{dim2}/2), FreeCAD.Vector({dim1}/2, {dim2}/2)),
    Part.LineSegment(FreeCAD.Vector({dim1}/2, {dim2}/2), FreeCAD.Vector(-{dim1}/2, {dim2}/2)),
    Part.LineSegment(FreeCAD.Vector(-{dim1}/2, {dim2}/2), FreeCAD.Vector(-{dim1}/2, -{dim2}/2)),
]
sketch.addGeometry(geo)
sketch.addConstraint([
    Sketcher.Constraint('Coincident', 0, 2, 1, 1),
    Sketcher.Constraint('Coincident', 1, 2, 2, 1),
    Sketcher.Constraint('Coincident', 2, 2, 3, 1),
    Sketcher.Constraint('Coincident', 3, 2, 0, 1),
    Sketcher.Constraint('DistanceX', 0, 2, {dim1}),
    Sketcher.Constraint('DistanceY', 1, 2, {dim2}),
    Sketcher.Constraint('DistanceX', 0, 1, 0.0),
    Sketcher.Constraint('DistanceY', 0, 1, 0.0),
])
doc.recompute()
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = sketch
pad.Length = {dim3}
pad.Label = "Pad"
doc.recompute()
body.ViewObject.ShapeColor = (0.3, 0.6, 1.0)
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""

    def _gen_undo_code(self):
        return """import FreeCAD
doc = FreeCAD.ActiveDocument
if doc:
    doc.undo()
    doc.recompute()
    FreeCAD.Gui.SendMsgToActiveView("ViewFit")
    print("Undo successful!")
else:
    print("No active document to undo.")"""

    def _gen_newdoc_code(self, user_input):
        return """import FreeCAD
doc = FreeCAD.newDocument("AI_Design")
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""

    def _gen_gridfinity_code(self, user_input):
        import re
        cols, rows, base_h, magnet_d = 3, 2, 6.0, 6.5
        m = re.search(r"(\d+)\s*(?:x|by)\s*(\d+)", user_input)
        if m:
            cols, rows = int(m.group(1)), int(m.group(2))
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm\s*)?base", user_input)
        if m:
            base_h = float(m.group(1))
        m = re.search(r"(\d+)\s*unit", user_input)
        if m:
            units = int(m.group(1))
            base_h = max(base_h, units * 7.0)
        m = re.search(r"magnet.*?(\d+(?:\.\d+)?)", user_input)
        if m:
            magnet_d = float(m.group(1))
        return f"""import FreeCAD, Part
doc = FreeCAD.ActiveDocument if FreeCAD.ActiveDocument else FreeCAD.newDocument("Gridfinity")
UC, BASE_H = 42.0, {base_h}
COLS, ROWS = {cols}, {rows}
W, D = COLS * UC, ROWS * UC
# Base plate
outer = Part.makeBox(W, D, BASE_H)
inner = Part.makeBox(W - 2.4, D - 2.4, BASE_H - 1.2, FreeCAD.Vector(1.2, 1.2, 1.2))
shell = outer.cut(inner)
# Magnet holes at corners of each cell (6.5mm dia, 2mm deep)
mag_r = {magnet_d / 2}
mag_h = min(2.5, BASE_H - 0.5)
for ci in range(COLS):
    for rj in range(ROWS):
        cx, cy = ci * UC + 3.5, rj * UC + 3.5
        for dx, dy in [(0,0), (UC-7,0), (0,UC-7), (UC-7,UC-7)]:
            hole = Part.makeCylinder(mag_r, BASE_H + 0.1, FreeCAD.Vector(cx+dx, cy+dy, -0.05))
            shell = shell.cut(hole)
# Center cutouts on each cell for weight saving
for ci in range(COLS):
    for rj in range(ROWS):
        cx, cy = ci * UC + 4, rj * UC + 4
        cutout = Part.makeBox(UC - 8, UC - 8, BASE_H - 1.5, FreeCAD.Vector(cx, cy, 1.5))
        shell = shell.cut(cutout)
obj = doc.addObject("Part::Feature", "GridfinityBase")
obj.Shape = shell
obj.ViewObject.ShapeColor = (0.2, 0.5, 0.8)
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""

    def _is_datum(self, obj):
        """Check if an object is internal Origin group geometry (axes, planes, etc)."""
        tid = getattr(obj, 'TypeId', '')
        if tid in ('App::Line', 'App::Plane', 'App::Origin'):
            return True
        label = getattr(obj, 'Label', '') or ''
        if label in ('X-axis', 'Y-axis', 'Z-axis', 'XY-plane', 'XZ-plane', 'YZ-plane'):
            return True
        return False

    def _diff_observation(self, prev, curr):
        """Diff two structured observations by stable UID (Document.Name.Object.Name).
        Returns (added, removed, modified) lists of {'uid': ..., 'summary': ...} dicts.
        Modifications are detected by shape_hash — compares ALL common objects, not just
        _touched_objects, so recompute cascades (Feature A changes → Feature B changes shape)
        are captured automatically. Touched-object filtering is done at the call site."""
        prev_map = {o["uid"]: o for o in prev}
        curr_map = {o["uid"]: o for o in curr}
        prev_uids = set(prev_map.keys())
        curr_uids = set(curr_map.keys())
        added_uids = curr_uids - prev_uids
        removed_uids = prev_uids - curr_uids
        common_uids = curr_uids & prev_uids
        added = []
        for uid in sorted(added_uids):
            added.append({"uid": uid, "summary": curr_map[uid]["summary"]})
        removed = []
        for uid in sorted(removed_uids):
            removed.append({"uid": uid, "summary": prev_map[uid]["summary"]})
        modified = []
        for uid in sorted(common_uids):
            prev_h = prev_map[uid].get("shape_hash")
            curr_h = curr_map[uid].get("shape_hash")
            if prev_h != curr_h:
                modified.append({"uid": uid, "summary": curr_map[uid]["summary"]})
        return added, removed, modified

    def capture_structured_diff(self):
        """Capture structured observation and return only the delta from the last call.
        On first call or reset, returns the full observation.
        Returns (diff, full) where diff is (added, removed, modified) lists
        of dicts with keys 'uid' and 'summary'."""
        curr = self.capture_observation_structured()
        if not self._prev_objects:
            self._prev_objects = curr
            return None, curr  # No diff available — first call
        added, removed, modified = self._diff_observation(self._prev_objects, curr)
        self._prev_objects = curr
        return (added, removed, modified), None

    def format_diff(self, diff_result):
        """Format a diff result (from capture_structured_diff) as a short string."""
        diff, full = diff_result
        if diff is None and full is not None:
            return self.format_observation(full)
        added, removed, modified = diff
        parts = []
        if added:
            parts.append(f"+{len(added)}: {'; '.join(a['summary'] for a in added[:5])}")
        if removed:
            parts.append(f"-{len(removed)}: {'; '.join(r['summary'] for r in removed[:5])}")
        if modified:
            parts.append(f"~{len(modified)}: {'; '.join(m['summary'] for m in modified[:5])}")
        if not parts:
            return "(no change)"
        result = " | ".join(parts)
        if len(result) > 1000:
            result = result[:1000] + "…"
        return result

    def reset_observation_tracker(self):
        """Reset the diff tracker so the next observation is a full dump."""
        self._prev_objects = []
        self._touched_objects = set()
        self._recompute_settled = True

    def force_sync_recompute(self, initial_object_count=0, timeout_s=8.0, poll_ms=50):
        """Block until FreeCAD's recompute queue is empty and no object is still dirty.

        Args:
            initial_object_count: number of objects before execution began.
                The poll refuses to exit until at least this many objects exist,
                preventing a vacuous pass on a freshly-created document.
        Returns True if stable within timeout, False if it timed out.

        Threading: this runs on the main Qt thread. To keep the UI responsive
        during the recompute wait, the sleep is chunked (~1 frame at 60fps)
        with processEvents() between chunks. Without this, the main thread
        blocks for poll_ms with no event pumping, freezing paint and input.
        """
        import time
        try:
            from compat import QtWidgets as QW
        except ImportError:
            from PySide2 import QtWidgets as QW

        doc = FreeCAD.ActiveDocument
        if doc is None:
            self._recompute_settled = True
            print("[RecomputeGuard] No active document — settled trivially")
            return True

        deadline = time.monotonic() + timeout_s
        chunk_s = min(0.016, poll_ms / 1000.0)  # ~1 frame at 60fps
        while time.monotonic() < deadline:
            doc.recompute()
            QW.QApplication.processEvents()

            if len(doc.Objects) < initial_object_count:
                continue

            still_dirty = []
            for obj in doc.Objects:
                # Per-object try/except: partially-loaded docs can throw on
                # State/TypeId access (see CRASH PATTERN 2 in AICompanionGui.py).
                try:
                    state = getattr(obj, "State", None)
                    if state in (["Recomputing"], ["Invalid"]):
                        still_dirty.append(obj.Label)
                        continue
                    type_id = getattr(obj, "TypeId", "") or ""
                    if "PartDesign::Body" in type_id:
                        tip = getattr(obj, "Tip", None)
                        if tip is not None:
                            tip_state = getattr(tip, "State", None)
                            if tip_state in (["Recomputing"], ["Invalid"]):
                                still_dirty.append(f"{obj.Label}/Tip")
                except Exception:
                    continue
            if not still_dirty:
                self._recompute_settled = True
                QW.QApplication.processEvents()  # final repaint on clean exit
                return True

            # Chunked sleep: pump Qt events every ~16ms so the UI stays
            # responsive while we wait for the next recompute to settle.
            slept = 0.0
            while slept < poll_ms / 1000.0 and time.monotonic() < deadline:
                time.sleep(chunk_s)
                QW.QApplication.processEvents()
                slept += chunk_s

        self._recompute_settled = False
        return False

    def _shape_hash(self, obj):
        if hasattr(obj, 'Shape') and obj.Shape:
            try:
                return hash(obj.Shape.exportBrepToString())
            except Exception:
                return None
        return None

    def capture_observation_structured(self):
        """Return structured list of dicts describing ALL open documents' state.
        Scans every document (not just ActiveDocument) because the active
        document can change during execution."""
        try:
            objects = []
            for dname, doc in FreeCAD.listDocuments().items():
                if not doc.Objects:
                    continue
                for obj in doc.Objects:
                    try:
                        if self._is_datum(obj):
                            continue
                        entry = {
                            "name": obj.Name,
                            "uid": f"{dname}.{obj.Name}",
                            "label": obj.Label if hasattr(obj, 'Label') else obj.Name,
                            "type": getattr(obj, 'TypeId', '?'),
                            "summary": self._object_line(obj).strip(),
                            "shape_hash": self._shape_hash(obj),
                        }
                        deps = {}
                        if hasattr(obj, 'InList') and obj.InList:
                            parents = [p.Label or p.Name for p in obj.InList[-3:] if not self._is_datum(p)]
                            if parents:
                                deps["parents"] = parents
                        if hasattr(obj, 'OutList') and obj.OutList:
                            children = [c.Label or c.Name for c in obj.OutList[-3:] if not self._is_datum(c)]
                            if children:
                                deps["children"] = children
                        if hasattr(obj, 'TypeId') and 'Body' in obj.TypeId and hasattr(obj, 'Group'):
                            features = [f.Label or f.Name for f in obj.Group if not self._is_datum(f)]
                            if features:
                                deps["features"] = features
                        if hasattr(obj, 'AttachmentSupport') and obj.AttachmentSupport:
                            sup = obj.AttachmentSupport[0]
                            if sup and not self._is_datum(sup):
                                deps["attached_to"] = sup.Label or sup.Name
                        if deps:
                            entry["deps"] = deps
                        objects.append(entry)
                    except Exception:
                        # Skip problematic object — log to failures for diagnostics
                        self.failures.record("observation_structured", None,
                            context=getattr(obj, 'Name', '?'))
                        continue
            return objects
        except Exception:
            return []

    def format_observation(self, obs_data, max_chars=1500):
        """Format structured observation data into a string, respecting max_chars."""
        if not obs_data:
            return "Empty scene — no objects."
        parts = []
        for obj in obs_data:
            line = obj.get("summary", obj.get("label", "?"))
            deps = obj.get("deps")
            if deps:
                dep_strs = []
                if "parents" in deps:
                    dep_strs.append(f"depends_on=[{','.join(deps['parents'])}]")
                if "children" in deps:
                    dep_strs.append(f"used_by=[{','.join(deps['children'])}]")
                if "features" in deps:
                    dep_strs.append(f"features=[{' → '.join(deps['features'])}]")
                if "attached_to" in deps:
                    dep_strs.append(f"attached_to={deps['attached_to']}")
                if dep_strs:
                    line += " (" + "; ".join(dep_strs) + ")"
            parts.append(line)
        result = "Scene now: " + " | ".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "…"
        return result

    def capture_observation(self):
        """Return formatted string — convenience wrapper."""
        data = self.capture_observation_structured()
        return self.format_observation(data)

    # ── Stub methods for planned but unimplemented features ─────────────────

    def extract_constraint_graph(self, user_input):
        pass

    def build_dag_from_plan(self, steps):
        if not hasattr(self, 'cad_dag') or self.cad_dag is None:
            self.cad_dag = _CadDagStub()
        self.cad_dag._rebuild(steps)

    def compute_delta_c(self):
        return _DeltaCResult()

    def verify_topology_min(self):
        return {}

    def check_fast_exit(self, delta_c):
        return True, ""

    def retrieve_repair(self, summaries):
        return []

    def record_repair(self, user_input, code, observation, success, message):
        pass

    def explain_spec_deviation(self, user_input, code, delta_c, topo_results):
        return ""

    def redecompose_step(self, failed_title, failure_summary, original_request,
                         remaining_steps=None, executed_steps=None, observations=None,
                         **kwargs):
        return None

    def validate_step_output(self, doc, step_label="", skip_for_category=None):
        return True, ""

    # ── Tool-calling integration ────────────────────────────────

    _TOOL_INTENT_PATTERNS = re.compile(
        r'\b(close|fillet|chamfer|pad|pocket|select|delete|hide|show|'
        r'measure|list|fit|recompute|set|rename|move|rotate|mirror)\b',
        re.IGNORECASE
    )

    def _should_use_tool(self, user_input: str) -> bool:
        """Returns True if the request looks like a direct CAD operation
        that a registered tool can handle (avoiding an LLM round-trip)."""
        if not user_input:
            return False
        return bool(self._TOOL_INTENT_PATTERNS.search(user_input))

    def route_as_tool(self, user_input: str) -> tuple:
        """
        Try to handle user_input as a tool call.
        Returns (handled: bool, message: str).
        If handled=False, caller should fall through to code generation.
        """
        from tools.registry import call_tool, list_tools
        import tools.freecad_operations  # noqa: F401 — registers tools

        ul = user_input.lower().strip()
        tool_name, args = self._match_tool(ul, user_input)
        if not tool_name:
            return False, "No matching tool found."

        result = call_tool(tool_name, args)
        return True, str(result)

    def _match_tool(self, ul: str, original: str) -> tuple:
        """Match user input to a tool name and extract arguments.
        Returns (tool_name: str|None, args: dict)."""
        from tools.registry import list_tools
        import tools.freecad_operations  # noqa: F401

        tools = list_tools()

        # Direct keyword matching for common commands
        if "close" in ul and ("wire" in ul or "sketch" in ul):
            return "close_wire", self._extract_sketch_name(original)

        if "fillet" in ul:
            return "add_fillet", self._extract_fillet_args(original)

        if ("box" in ul or "cube" in ul or "block" in ul) and any(c.isdigit() for c in ul):
            return "make_box", self._extract_box_dims(original)

        if "pad" in ul:
            return "make_pad", self._extract_pad_args(original)

        if "select" in ul:
            return "select_object", self._extract_name_arg(original)

        if "delete" in ul or "remove" in ul:
            return "delete_object", self._extract_name_arg(original)

        if "hide" in ul:
            return "set_visibility", {**self._extract_name_arg(original), "visible": False}

        if "show" in ul:
            return "set_visibility", {**self._extract_name_arg(original), "visible": True}

        if "measure" in ul or "distance" in ul:
            return "measure_distance", self._extract_two_names(original)

        if "list" in ul or "objects" in ul:
            return "list_objects", {}

        if "fit" in ul and ("view" in ul or "all" in ul):
            return "fit_view", {}

        if "recompute" in ul:
            return "recompute", {}

        if "set " in ul and any(p in ul for p in ("length", "width", "height", "radius")):
            return "set_property", self._extract_set_property_args(original)

        return None, {}

    @staticmethod
    def _extract_sketch_name(text: str) -> dict:
        import re
        m = re.search(r'(?:sketch|in)\s+["\']?(\w+)["\']?', text, re.IGNORECASE)
        if m:
            return {"sketch_name": m.group(1)}
        return {}

    @staticmethod
    def _extract_fillet_args(text: str) -> dict:
        import re
        args = {}
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:mm\s*)?radius', text, re.IGNORECASE)
        if m:
            args["radius"] = float(m.group(1))
        m = re.search(r'(?:on|of|for)\s+["\']?(\w+)["\']?', text, re.IGNORECASE)
        if m:
            args["object_name"] = m.group(1)
        if "radius" not in args:
            args["radius"] = 5.0
        return args

    @staticmethod
    def _extract_box_dims(text: str) -> dict:
        import re
        args = {"length": 100, "width": 60, "height": 40}
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:x|by|\*|\u00d7)\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:x|by|\*|\u00d7)\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if m:
            args.update(length=float(m.group(1)), width=float(m.group(2)), height=float(m.group(3)))
        m = re.search(r'name\s+["\']?(\w+)["\']?', text, re.IGNORECASE)
        if m:
            args["name"] = m.group(1)
        return args

    @staticmethod
    def _extract_pad_args(text: str) -> dict:
        import re
        args = {"length": 10, "symmetric": False}
        m = re.search(r'(\d+(?:\.\d+)?)\s*mm', text)
        if m:
            args["length"] = float(m.group(1))
        m = re.search(r'(?:sketch|of)\s+["\']?(\w+)["\']?', text, re.IGNORECASE)
        if m:
            args["sketch_name"] = m.group(1)
        if "symmetric" in text.lower():
            args["symmetric"] = True
        return args

    @staticmethod
    def _extract_name_arg(text: str) -> dict:
        import re
        words = text.split()
        for w in reversed(words):
            clean = w.strip(".,!?;:'\"()[]{}")
            if clean and not any(c.isdigit() for c in clean) and clean.lower() not in (
                "select", "delete", "remove", "hide", "show", "the", "a", "an",
                "object", "this", "that", "please", "could", "would", "can"
            ):
                return {"name": clean}
        return {}

    @staticmethod
    def _extract_two_names(text: str) -> dict:
        import re
        names = re.findall(r'["\']?(\w+)["\']?', text)
        cad_keywords = {"select", "delete", "remove", "hide", "show", "the", "a", "an",
                       "object", "this", "that", "please", "measure", "distance",
                       "between", "and", "to", "from", "of", "for", "in", "on", "at"}
        objects = [n for n in names if n.lower() not in cad_keywords]
        if len(objects) >= 2:
            return {"obj1": objects[0], "obj2": objects[1]}
        return {"obj1": "", "obj2": ""}

    @staticmethod
    def _extract_set_property_args(text: str) -> dict:
        import re
        args = {}
        m = re.search(r'(?:of|for|on)\s+["\']?(\w+)["\']?', text, re.IGNORECASE)
        if m:
            args["object_name"] = m.group(1)
        for prop in ("length", "width", "height", "radius"):
            if prop in text.lower():
                args["property"] = prop.capitalize()
                v = re.search(rf'(?:{prop})\s*(?:=|\s+)?(\d+(?:\.\d+)?)', text, re.IGNORECASE)
                if v:
                    args["value"] = float(v.group(1))
                break
        return args
