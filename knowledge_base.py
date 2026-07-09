"""Tiered FreeCAD knowledge base for the AI system prompt.

Three tiers:
  Tier 0 — always included (~3KB of strict rules + version flags)
  Tier 1 — included on keyword match user input
  Tier 2 — included on explicit workflow match

This replaces the single 30KB FREECAD_KNOWLEDGE string, cutting prompt
size by ~67% for most requests.
"""


class KnowledgeBase:
    TIER_0 = """## FREECAD API REFERENCE

### CAPABILITY SCOPE — YOU CAN DO EVERYTHING A USER CAN DO WITH A MOUSE
You have full access to FreeCAD's Python API. You can:
- **Switch any workbench**: `FreeCADGui.activateWorkbench("AnyWorkbenchName")`
- **Use any addon workbench**: SheetMetal, Fasteners, etc.
- **Use any FreeCAD GUI command**: `FreeCADGui.runCommand("Std_Measure")`
- **Access selection**: `FreeCADGui.Selection.getSelection()`
- **Access viewport**: `FreeCADGui.activeView()`
- **Document management**: `FreeCAD.listDocuments()`, `FreeCAD.newDocument()`, `FreeCAD.closeDocument()`
- **Workbench discovery**: Check `FreeCADGui.listWorkbenches()` before assuming a module is missing.

### SANDBOX RULES — DO NOT IGNORE
- **NEVER import any modules.** All imports are blocked. Use only preloaded names: Part, Sketcher, PartDesign, Mesh, Draft, Assembly, TechDraw, SheetMetal, Fasteners, FreeCAD, FreeCADGui, math.
- **NEVER import GUI modules.** `import SketcherGui`, `import PartGui`, `import FreeCADGui` — all crash immediately.
- `Part.show(shape)` works in the sandbox — no import needed.
- Do NOT use `try/except ImportError` to probe for modules.

### THREE PLACEMENT PROPERTIES — KNOW THE DIFFERENCE (MOST COMMON FAILURE)

There are three different ways to position a sketch. They are NOT interchangeable:

| Property | When to use | Wrong use |
|---|---|---|
| `sketch.AttachmentSupport = (obj, "FaceN")` | Attach sketch TO a solid face for Pad/Pocket | Never pass Vector, Placement, or geometry object as second arg |
| `sketch.Placement = FreeCAD.Placement(Vector, Rot)` | Position a free-floating sketch in 3D space (pipe profiles, reference geometry) | Not for face attachment |
| `sketch.AttachmentOffset = FreeCAD.Placement(...)` | Fine-tune position of sketch ALREADY attached via AttachmentSupport | Useless without AttachmentSupport; not for free-floating sketches |

**Rule:** Face-attached → `AttachmentSupport`. Free-floating → `Placement`. Never `AttachmentOffset` as a substitute for `Placement`.

**WARNING:** `AttachmentSupport` second argument MUST be a string (`"Face6"`) or list of strings. Passing `FreeCAD.Vector`, `FreeCAD.Placement`, `Part.Face`, or any geometry object raises `TypeError: type of second element in tuple must be str`.

```python
# WRONG — every one raises TypeError
sketch.AttachmentSupport = (pad, FreeCAD.Vector(0, 0, 80))   # Vector
sketch.AttachmentSupport = (pad, FreeCAD.Placement(...))     # Placement
sketch.AttachmentSupport = (pad, face)                       # Part.Face object

# RIGHT — free-floating sketch at Z=80
sketch.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 80), FreeCAD.Rotation())
```

### MEASUREMENT TOOLS
- `obj.Shape.Volume`, `obj.Shape.Area`, `obj.Shape.BoundBox`, `obj.Shape.CenterOfMass`
- `obj.Shape.distToShape(other_shape)` — minimum distance
- `obj.Placement.Base` — position vector
- `obj.Placement.Rotation` — orientation quaternion

### GUI COMMANDS
- `FreeCADGui.runCommand("Std_New")`, `FreeCADGui.runCommand("Std_Open")`
- `FreeCADGui.runCommand("Std_ViewFitAll")`, `FreeCADGui.runCommand("Std_ViewIsometric")`
- `FreeCADGui.runCommand("Sketcher_NewSketch")`, `FreeCADGui.runCommand("PartDesign_Pad")`
- Run `FreeCADGui.listCommands()` to discover ALL available commands.

### FASTENERS WORKBENCH
- `import Fasteners`; `Fasteners.makeScrew("M6HexHeadScrew", doc=doc)`
- Types: M6HexHeadScrew, M8HexHeadScrew, M6HexNut, M8Washer

### DESIGN WORKFLOW
1. **PartDesign** → Body → Sketch on plane → Pad → features
2. **Part** → boolean ops between bodies (Cut, Fuse, Common)
3. **Draft** → arrays, text, dimension lines
4. **TechDraw** → drawing sheets from 3D model

For simple primitives (boxes, cylinders, spheres, cones), use PartDesign Additive features directly — NO sketch needed:
  - body.newObject("PartDesign::AdditiveBox", "Box") → .Length, .Width, .Height
  - body.newObject("PartDesign::AdditiveCylinder", "Cyl") → .Radius, .Height
  - body.newObject("PartDesign::AdditiveSphere", "Sphere") → .Radius
  - body.newObject("PartDesign::AdditiveCone", "Cone") → .Radius1, .Radius2, .Height
Only use Sketch → Pad workflow for complex 2D profiles. Use standalone Part primitives (Part::Box, Part::Cylinder) only when there is NO Body in the document.

### PART HELPER FUNCTIONS
Define these at the top of your code block:
```python
def v(x,y,z): return FreeCAD.Vector(x,y,z)
def box(lx,ly,lz, x=0,y=0,z=0): return Part.makeBox(lx,ly,lz, v(x,y,z))
def cyl(r,h, x=0,y=0,z=0, ax=None): return Part.makeCylinder(r,h, v(x,y,z), ax or v(0,0,1))
def tube(od,id_,h, x=0,y=0,z=0): return cyl(od/2,h,x,y,z).cut(cyl(id_/2, h+0.2, x,y,z-0.1))
def fuse(*args):
    flat=[]; [flat.extend(a) if isinstance(a,list) else flat.append(a) for a in args]
    r=flat[0]
    for s in flat[1:]: r=r.fuse(s)
    return r
def sub(base,*args):
    r=base
    for a in args:
        if isinstance(a,list):
            for s in a: r=r.cut(s)
        else: r=r.cut(a)
    return r
```
For rounded-corner boxes use `EnclosureBuilder.rrect()`. For rotated boxes use `EnclosureBuilder.rotbox()`.

### COMMON FAILURE MODES — QUICK REFERENCE

| Symptom | Root cause | Fix |
|---|---|---|
| `TypeError: type of second element in tuple must be str` | Passed Vector/Placement/object to `AttachmentSupport` | Use `sketch.Placement` for free-floating sketches; `AttachmentSupport` only with face name strings |
| `AttributeError: has no attribute 'Base'` | Used `pad.Base = sketch` | Use `pad.Profile = sketch` |
| `AttributeError: has no attribute 'Objects'` | Used `body.Objects` | Use `body.Group` |
| `TypeError: not Part.Face` | Passed face object to `AttachmentSupport` | Pass `f"Face{i+1}"` string |
| `AttributeError: has no attribute 'Support'` | Used `sketch.Support` | `sketch.AttachmentSupport = (obj, "FaceN")` |
| `AttributeError: has no attribute 'ReferenceAxis'` | Used `sketch.ReferenceAxis` | Use `sketch.MapMode` + `AttachmentSupport` |
| `AttributeError: has no attribute 'Axis'` on Pad/Pocket | Used `pad.Axis` | Use `pad.Reversed = True` |
| Sketch created outside Body | `doc.addObject("Sketcher::SketchObject", ...)` | Use `body.newObject(...)` |
| Crash on import | `import SketcherGui` or other GUI module | Never import GUI modules — they are preloaded |
"""

    TIER_1_SKETCH = """
### SKETCHER API
- `sketch.addGeometry(geo_list, False)` — add geometry
- `sketch.addConstraint(con_list)` — add constraints
- Geo types: `Part.LineSegment(p1, p2)`, `Part.Circle(center, normal, radius)`, `Part.ArcOfCircle(arc, start, end)`
- Constraint: `Sketcher.Constraint('Distance', GeoId, Value)` — line length
- Constraint: `Sketcher.Constraint('DistanceX', GeoId, Value)` — horizontal projection
- Constraint: `Sketcher.Constraint('DistanceY', GeoId, Value)` — vertical projection
- Constraint: `Sketcher.Constraint('Coincident', g1, v1, g2, v2)` — join points
- Constraint: `Sketcher.Constraint('Horizontal', GeoId)`, `Sketcher.Constraint('Vertical', GeoId)`
- Constraint: `Sketcher.Constraint('Radius', GeoId, Value)`, `Sketcher.Constraint('Diameter', GeoId, Value)`
- Constraint: `Sketcher.Constraint('Angle', GeoId1, GeoId2, Value)` — angle between two lines
- Vertex positions: 1=start, 2=end, 3=center, 4=outer for circles
- Use ```json blocks for sketch geometry (auto-compiled to avoid vertex-index errors)
"""

    TIER_1_PARTDESIGN = """
### PART DESIGN API
- `body = doc.getObject("Body") or doc.addObject("PartDesign::Body", "Body")`
- Features via `body.newObject("PartDesign::FeatureType", "Name")` — NEVER doc.addObject()
- Common features: Pad, Pocket, Hole, Fillet, Chamfer, Revolution, Groove, AdditiveBox, SubtractiveCylinder
- `pad.Profile = sketch` (FreeCAD 1.0+) or `pad.Sketch = sketch` (0.x)
- `pad.Length`, `pad.Length2`, `pad.Type` (0=Dimension, 1=ThroughAll, 2=UpToFace)
- Fillet: `fillet.Base = (edge,)` or `fillet.AddShape = obj`; fillet.Radius = 5
- Chamfer: `chamfer.Size = 2`, `chamfer.Base = (edge,)`
- Hole: `hole.Profile = sketch`; hole.Diameter, hole.Depth, hole.Threaded
"""

    TIER_1_PART = """
### PART PRIMITIVES (Part::*)
| Type | Properties |
|------|-----------|
| Box | .Length, .Width, .Height |
| Cylinder | .Radius, .Height, .Angle |
| Sphere | .Radius, .Angle1-3 |
| Cone | .Radius1, .Radius2, .Height |
| Torus | .Radius1, .Radius2, .Angle |
| Tube | .InnerRadius, .OuterRadius, .Height |
| Helix | .Pitch, .Height, .Radius |
| Prism | .Polygon, .Height |

### Part Modifiers
- Chamfer: `.Base` (shape), `.Size` (float)
- Fillet: `.Base`, `.Radius`
- Thickness: `.Faces`, `.Thickness`, `.Offset` (crash-prone — prefer alternatives)
- `Part.show(obj)` — display a raw shape in the document

### BOOLEAN OPERATIONS
- `shape_a.fuse(shape_b)` — union
- `shape_a.cut(shape_b)` — difference
- `shape_a.common(shape_b)` — intersection (crash-prone with bad geometry)
- `Part.Compound([s1, s2, ...])` — group shapes without boolean
"""

    TIER_1_ASSEMBLY = """
### ASSEMBLY WORKBENCH
- `import Assembly`
- `asm = doc.addObject("Assembly::AssemblyObject", "Assembly")`
- `asm.addObject(obj)` — add part
- `asm.addJoint("Fixed", part1, part2)` — fix relative to each other
- `asm.addJoint("Coincident", face1, face2)` — align faces (FreeCAD 1.0+)
- `asm.addJoint("Parallel", edge1, edge2)` — parallel constraint
- Joint types: Fixed, Coincident, Parallel, Perpendicular, Angle, Distance
- For explicit placement: `obj.Placement.Base = FreeCAD.Vector(x, y, z)`
- `obj.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0,0,1), 45)` — rotate 45° around Z
"""

    TIER_1_TECHDRAW = """
### TECH DRAW WORKBENCH
```python
import TechDraw
page = doc.addObject("TechDraw::DrawPage", "Page")
template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
template.Template = FreeCAD.getResourceDir() + "Mod/TechDraw/Templates/A4_LandscapeTD.svg"
page.Template = template
view = doc.addObject("TechDraw::DrawViewPart", "View")
view.Source = [body]
view.Scale = 1.0
view.Direction = FreeCAD.Vector(0,0,1)  # top: (0,0,1), front: (0,-1,0), right: (1,0,0)
page.addView(view)
```
DrawingGenerator (already in scope) wraps this for simple cases.

### TECH DRAW ADVANCED
- Projection group: `doc.addObject("TechDraw::DrawViewGroup", "Group")` — multi-view from one source
- Section view: `doc.addObject("TechDraw::DrawViewSection", "Section")` — cut view
- Detail view: `doc.addObject("TechDraw::DrawViewDetail", "Detail")` — zoomed area
- Balloon: `doc.addObject("TechDraw::DrawViewBalloon", "Balloon")` — numbered callout
- Dimension: `doc.addObject("TechDraw::DrawViewDimension", "Dim")` — .Type: Distance, Length, Radius, Diameter
- `view.getVisibleEdges()` — list edges for dimensioning
"""

    TIER_2_PCB = """
### PCB ENCLOSURE GENERATION — TEMPLATE-FIRST

The enclosure is built with proven EnclosureBuilder templates — you do NOT write raw FreeCAD geometry.
The template system handles all Part.makeBox/Part.makeCylinder/cut/fuse operations internally.

**EnclosureBuilder workflow (call in this exact order):**
1. `builder = EnclosureBuilder(doc=doc)`
2. `builder.create_base_shell(board_data, wall_t=2.5, floor_t=2.0)`
3. `builder.add_mounting_bosses(board_data, boss_od=6.0)`
4. `builder.add_connector_cutouts(board_data, clearance=0.5, cutout_width=14.0)`
5. `builder.add_snap_fits(count=4, snap_width=6.0, snap_depth=3.0)` — skip for no snaps
6. `builder.add_ventilation(slot_count=3, slot_width=3.0, slot_length=15.0)` — skip for no vents
7. `builder.create_lid(board_data)`

**Static helpers:**
- `EnclosureBuilder.rrect(w, h, r)` — rounded-corner profile
- `EnclosureBuilder.rotbox(w, h, length, deg, cx, cy, z)` — rotated box
- `EnclosureBuilder.rslot(lx, ly, r, depth, x, y, z)` — rounded-corner slot cutout
- `EnclosureBuilder.v(x, y, z)` — FreeCAD.Vector shorthand

**Shortcut (one-call full generation):**
`build_enclosure_from_params(board_data, {"wall_thickness": 2.5, "boss_od": 6.0, "snap_count": 4, "vent_slots": 3})`

**CRITICAL:** NEVER write Part.makeBox, Part.makeCylinder, Part.cut, or Part.fuse for enclosure geometry.
ALWAYS use EnclosureBuilder methods. Raw Part geometry for enclosures will be REJECTED.
"""


    TIER_2_SNAP_FIT = """
### SNAP FIT DESIGN
- Cantilever snap: beam thickness = 1.0-1.5mm, length = 10-15mm, undercut = 0.3-0.5mm
- Annular snap: groove depth = 0.5-0.8mm, engagement angle = 30-45°
- Torsion snap: spring arm length = 8-12mm, deflection = 1.0-1.5mm
- Material considerations: PLA is brittle (avoid sharp undercuts), PETG is flexible (good for snaps)
"""

    TIER_2_VENTILATION = """
### VENTILATION PATTERNS
- Slot vents: width=2-3mm, length=10-20mm, spacing=2-4mm
- Round vents: diameter=3-5mm, spacing=4-8mm
- Honeycomb vents: hexagon side=3-5mm, wall=1-2mm
- Keep vents away from structural edges by at least 2x wall thickness
"""

    TIER_2_GRIDFINITY = """
### GRIDFINITY BASE BLOCKS
- Grid unit: 42mm × 42mm per cell
- Corner radius: 4mm (use EnclosureBuilder.rrect for profile)
- Base height: default 5mm (or 6mm for magnet version)
- Magnet holes: 6.5mm diameter, 2mm deep, center 3.5mm from each corner
- Screw holes (optional): 3.5mm diameter, center 3.5mm from each corner
- Top lip: 0.8mm wide, 1.0mm below top surface
- Lightening cutouts: subtract center area of each cell (leave ~4mm border)
- Recommended workflow: Part::Box for base, Part::Cylinder for holes, Part::Fillet for rounded edges
- Keep Z=0 at bottom of base, build everything upward
"""

    TIER_2_PIPE = """
### ADDITIVE PIPE — SWEEP A PROFILE ALONG A PATH (PartDesign)

The AdditivePipe sweeps one or more cross-sections along a spine (path) to create
smooth 3D geometry. Use this for pipes, hoses, ducts, handrails, and any
variable-diameter swept shape.

#### Recipe 1 — Constant Section (one profile, one spine)

```python
doc = FreeCAD.ActiveDocument
body = doc.addObject("PartDesign::Body", "Body")

# 1. Spine — a wire in 3D space (use Part.makePolygon for straight paths,
#    or multiple segments for curved paths)
path_edge = Part.makePolygon([
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(0, 0, 60)
    # add more points for curved/angled paths
])
path_obj = doc.addObject("Part::Feature", "PathWire")
path_obj.Shape = path_edge
doc.recompute()

# 2. Profile sketch (e.g., a circle on XY plane at path start)
prof_sk = body.newObject("Sketcher::SketchObject", "ProfileSketch")
prof_geo = []
prof_geo.append(Part.Circle(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,0,1), 8.0))
prof_sk.addGeometry(prof_geo)
doc.recompute()

# 3. Create the pipe
pipe = body.newObject("PartDesign::AdditivePipe", "Pipe")
pipe.Profile = prof_sk    # single sketch for constant section
pipe.Spine = path_obj     # Part::Feature wire as spine
doc.recompute()
```

#### Recipe 2 — Multisection / Variable Diameter (CRITICAL — read carefully)

For a pipe that changes diameter (e.g., 10mm radius → 20mm radius over 80mm height),
you MUST pass a LIST of sketches to `.Profile` and set `.SectionTransformation`.
Use a Part::Feature wire as the 3D spine — avoids sketch-plane rotation complexity.

```python
doc = FreeCAD.ActiveDocument
body = doc.addObject("PartDesign::Body", "Body")

# 1. Spine — a vertical wire from Z=0 to Z=80 (NOT a sketch, no rotation needed)
path_edge = Part.makePolygon([FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 80)])
path_obj = doc.addObject("Part::Feature", "PathWire")
path_obj.Shape = path_edge
doc.recompute()

# 2a. Start profile (small diameter) — XY plane at Z=0
start_sk = body.newObject("Sketcher::SketchObject", "StartProfile")
start_geo = []
start_geo.append(Part.Circle(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,0,1), 10.0))
start_sk.addGeometry(start_geo)
start_sk.addConstraint([Sketcher.Constraint('Radius', 0, 10.0)])
doc.recompute()

# 2b. End profile (large diameter) — XY plane, positioned at Z=80
end_sk = body.newObject("Sketcher::SketchObject", "EndProfile")
end_geo = []
end_geo.append(Part.Circle(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,0,1), 20.0))
end_sk.addGeometry(end_geo)
end_sk.addConstraint([Sketcher.Constraint('Radius', 0, 20.0)])
end_sk.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 80), FreeCAD.Rotation())
doc.recompute()

# 3. Create the multisection pipe — LIST of all profile sketches
pipe = body.newObject("PartDesign::AdditivePipe", "VariablePipe")
pipe.Profile = [start_sk, end_sk]   # ← MUST be a LIST, NOT a single sketch
pipe.Spine = path_obj               # Part::Feature wire, no sketch rotation needed
pipe.SectionTransformation = "Multisection"  # ← REQUIRED for variable diameter
doc.recompute()
```

**CRITICAL: `.Profile` is a LIST for multisection.**

| WRONG | RIGHT | Reason |
|-------|-------|--------|
| `pipe.Profile = start_sk` then add sections | `pipe.Profile = [start_sk, end_sk]` | Single sketch = constant section only |
| `pipe.Sections = [end_sk]` | Use `.Profile` list | `.Sections` does not exist on AdditivePipe |
| Missing `.SectionTransformation` | `pipe.SectionTransformation = "Multisection"` | Default is "Constant" — your sections get ignored |

**Additional intermediate sections:**
```python
mid_sk = body.newObject("Sketcher::SketchObject", "MidProfile")
# ... circle at intermediate diameter ...
mid_sk.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 40), FreeCAD.Rotation())
pipe.Profile = [start_sk, mid_sk, end_sk]
```

**Positioning profile sketches along the path:**
- Use `sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(x,y,z), FreeCAD.Rotation())` for free-floating sketches
- The profile sketch local XY plane is moved to the (x,y,z) position in 3D space
- For a vertical path along Z: set the end profile's Z to the path endpoint height
- For a curved/horizontal path: each profile Placement must match its position along that path
- DO NOT use `.AttachmentSupport` for positioning — it requires a face name string, not a vector
- `.AttachmentOffset` only applies when the sketch is already attached to a face via `AttachmentSupport`

**Warping/twisting fix ("abomination" result):**
- Add a mid-profile between start and end to guide the shape
- Ensure all profile sketches have the same number of geometry elements
- Create profiles in order (smallest Z → largest Z) and pass them in that same order to `.Profile`
"""

    # keyword -> tier-1 section name mapping
    KEYWORDS = {
        TIER_1_SKETCH: ["sketch", "constraint", "line", "arc", "circle", "rectangle",
                        "polygon", "coincident", "tangent", "trim", "extend"],
        TIER_1_PARTDESIGN: ["pad", "pocket", "fillet", "chamfer", "body",
                           "feature", "extrude", "revolve", "loft", "sweep",
                           "additive", "subtractive", "hole", "groove", "pipe"],
        TIER_1_PART: ["box", "cylinder", "sphere", "boolean", "union",
                     "cut", "common", "compound", "shell", "prism", "cone", "torus"],
        TIER_1_ASSEMBLY: ["assembly", "joint", "mate", "coincident",
                         "offset", "attach", "placement", "constraint"],
        TIER_1_TECHDRAW: ["drawing", "techdraw", "view", "projection",
                         "dimension", "annotation", "page", "balloon"],
    }

    TIER_2_KEYWORDS = {
        TIER_2_PCB: ["pcb", "kicad", "enclosure", "standoff", "board", "connector"],
        TIER_2_SNAP_FIT: ["snap", "clip", "click", "press", "fit"],
        TIER_2_VENTILATION: ["vent", "hole", "slot", "grill", "cooling", "airflow"],
        TIER_2_GRIDFINITY: ["gridfinity", "gridfinity base", "grid", "base block"],
        TIER_2_PIPE: ["pipe", "sweep", "multisection", "section transformation",
                      "additive pipe", "variable diameter", "hose", "duct",
                      "transition", "spine"],
    }

    def __init__(self):
        self._freecad_version = (0, 21)

    def set_version(self, major, minor):
        self._freecad_version = (major, minor)

    def version_flags(self):
        major, minor = self._freecad_version
        flags = []
        if major >= 1:
            flags.append("VERSION: FreeCAD 1.0+ — use .Profile NOT .Sketch in Loft/Sweep/Pipe")
        else:
            flags.append("VERSION: FreeCAD 0.x — use .Sketch NOT .Profile in Loft/Sweep/Pipe")
        if major >= 1:
            flags.append("Built-in Assembly workbench available (import Assembly)")
        return "\n".join(flags)

    ASK_TIER_0 = """## FREECAD REFERENCE

### CAPABILITY SCOPE
You have full access to FreeCAD's Python API: Part, Sketcher, PartDesign, Draft, Mesh, Assembly, TechDraw, FreeCAD, FreeCADGui.

### KEY WORKBENCHES
- **Part**: Primitives (Box, Cylinder, Sphere), boolean ops (Cut, Fuse, Common), extrude/revolve
- **PartDesign**: Body → Sketch on plane → Pad/Pocket/Revolution features
- **Draft**: 2D drawing tools, arrays, text, dimension lines
- **Sketcher**: 2D constrained sketches for PartDesign features
- **Assembly**: Constrain parts together (v1.0+)

### COMMON API
- `App.ActiveDocument` / `App.newDocument("Name")`
- `obj.Shape` for geometry properties, `obj.Placement` for position
- `doc.recompute()` to update after changes
- `FreeCADGui.Selection.getSelection()` for selected objects
- `FreeCAD.Vector(x, y, z)` for 3D points
- `Part.show(shape)` to display a shape in the document
"""

    def build(self, user_message, mode="build"):
        """Assemble the knowledge base for this request.

        Returns the full knowledge section for the system prompt.
        """
        if mode == "ask":
            sections = [self.ASK_TIER_0]
        else:
            sections = [self.TIER_0]
        sections.append(self.version_flags())

        ml = user_message.lower() if user_message else ""

        # Tier 1 — keyword match
        for section, keywords in self.KEYWORDS.items():
            if any(kw in ml for kw in keywords):
                sections.append(section)

        # Tier 2 — explicit workflow match
        for section, keywords in self.TIER_2_KEYWORDS.items():
            if any(kw in ml for kw in keywords):
                sections.append(section)

        return "\n\n".join(sections)
