"""FreeCAD knowledge base — used as system prompt for the AI."""
FREECAD_KNOWLEDGE = """
## FREECAD API REFERENCE

### CAPABILITY SCOPE — YOU CAN DO EVERYTHING A USER CAN DO WITH A MOUSE
You have full access to FreeCAD's Python API. You can:
- **Switch any workbench**: `FreeCADGui.activateWorkbench("AnyWorkbenchName")` — discover with `FreeCADGui.listWorkbenches()`
- **Use any addon workbench**: `import SheetMetal`, `import Fasteners`, `import ScrewMaker`, etc.
- **Use any FreeCAD GUI command**: `FreeCADGui.runCommand("Std_Measure")`, `FreeCADGui.runCommand("Sketcher_NewSketch")`
- **Access selection**: `FreeCADGui.Selection.getSelection()`, `FreeCADGui.Selection.addSelection(obj)`
- **Access viewport**: `FreeCADGui.activeView()`, `FreeCAD.activeDocument().ActiveView`
- **Use measurement tools**: `obj.Shape.Volume`, `obj.Shape.Area`, `obj.Shape.BoundBox`, `Part.Geom2d.distToSegment`, `obj.Shape.distToShape(other)`
- **Export/Import**: `import ImportGui`, `import ExportGui`, `FreeCADGui.export([obj], "path.step")`
- **Document management**: `FreeCAD.listDocuments()`, `FreeCAD.setActiveDocument("name")`, `FreeCAD.closeDocument("name")`
- **Workbench discovery**: Before assuming a module is missing, check with `FreeCADGui.listWorkbenches()`. The workbench may be installed but not yet imported.

### MISSING WORKBENCHES — GUIDE THE USER
If you try to import a module and it fails:
```python
try:
    import SheetMetal
except ImportError:
    print("❌ SheetMetal workbench not installed.")
    print("To install: Tools → Addon Manager → search 'SheetMetal' → Install → restart FreeCAD")
    # Stop and tell the user what to do
```
Always guide the user with exact steps: which Addon Manager entry to search for, that they need to restart FreeCAD after install.

### MEASUREMENT TOOLS
- `obj.Shape.Volume` — volume in mm³
- `obj.Shape.Area` — surface area in mm²
- `obj.Shape.BoundBox` — bounding box (XMin, XMax, YMin, YMax, ZMin, ZMax, XLength, YLength, ZLength)
- `obj.Shape.distToShape(other_shape)` — minimum distance between two shapes
- `obj.Shape.CenterOfMass` — center of mass vector
- `obj.Shape.Mass` — mass (if density set)
- `FreeCADGui.Selection.addSelection(obj)` — select an object in the GUI tree
- `FreeCADGui.runCommand("Std_Measure")` — activate the built-in measure tool
- `Part.Vertex(point).distToLine(line_point, line_dir)` — distance from point to line
- `obj.Shape.Vertexes` — list of all vertices with their `.Point` coordinates
- `obj.Shape.Edges` — list of edges with `.Length`, `.Curve`, `.FirstParameter`, `.LastParameter`
- `obj.Shape.Faces` — list of faces with `.Area`, `.Surface`, `.CenterOfMass`
- `obj.Placement.Base` — position (FreeCAD.Vector)
- `obj.Placement.Rotation` — orientation (FreeCAD.Rotation)

### GUI COMMANDS (simulate clicking toolbar buttons)
- `FreeCADGui.runCommand("Std_New")` — new document
- `FreeCADGui.runCommand("Std_Open")` — open file
- `FreeCADGui.runCommand("Std_Measure")` — measure tool
- `FreeCADGui.runCommand("Std_ViewFitAll")` — fit view
- `FreeCADGui.runCommand("Std_ViewIsometric")` — isometric view
- `FreeCADGui.runCommand("Sketcher_NewSketch")` — new sketch
- `FreeCADGui.runCommand("PartDesign_Pad")` — pad
- `FreeCADGui.runCommand("Part_Fillet")` — fillet
- `FreeCADGui.runCommand("Std_Delete")` — delete selected
- `FreeCADGui.SendMsgToActiveView("ViewFit")` — fit view (SINGULAR "View", NOT "Views")
- Run `FreeCADGui.listCommands()` to discover ALL available commands.
- You can call any command by name — no need to know the toolbar location.

### COMMON FREECAD MISTAKES — avoid these:
1. `FreeCADGui.SendMsgToActiveViews` does NOT exist. Use `FreeCADGui.SendMsgToActiveView` (singular) instead.
2. `Units` is NOT a preloaded name. Use `FreeCAD.Units` if you need unit conversion, or just use raw numbers in mm.
3. `import PartGui` or `import FreeCADGui` will FAIL — these modules are already loaded, do NOT import them. The same error message means you tried to import a GUI-only module that isn't in the sandbox.
4. `Part.show(shape)` now WORKS in the sandbox — it creates a `Part::Feature` with the shape. Use it freely.
5. Do NOT use `SketcherGui` — only `Sketcher` is available.
6. `Part.Vertex` coordinates use UPPERCASE `.X`, `.Y`, `.Z` — NOT lowercase `.x`, `.y`, `.z`. Use `vertex.Point.x` to access the point coordinates.
7. `Base.Vector()`, `App.Vector()`, and `FreeCAD.Vector()` are all the same — use any. Do NOT write `Part.Vector()` — it doesn't exist.
8. `sketch.Support` does NOT exist on `Sketcher::SketchObject`. Use `sketch.AttachmentSupport = (target_obj, ["Face6"])` instead — it's a LIST of (object, subelement_string) tuples. Example: `sketch.AttachmentSupport = (pad, "Face6")`.
9. `pad.ReferenceAxis` / `pocket.ReferenceAxis` does NOT exist on PartDesign features. For revolution/groove axes, set `.Axis` to a `FreeCAD.Vector`. For holes, use `.HoleCutDiameter` and `.HoleCutDepth` properties.
10. An object can NOT belong to two Part containers or Bodies at once. If an object is already inside a Part/Group, remove it first with `part_container.removeObject(obj)` before adding to a Body. Use `obj.InList` to check current parent.

### FASTENERS WORKBENCH
- `import Fasteners`
- `Fasteners.makeScrew("SomeType")` — see Fasteners.FASTENER_TYPES for list
- `Fasteners.makeWasher("SomeType")` — see Fasteners.WASHER_TYPES
- `Fasteners.makeNut("SomeType")` — see Fasteners.NUT_TYPES
- Common types: "M6HexHeadScrew", "M8HexHeadScrew", "M6HexNut", "M8Washer"
- Always pass `doc=doc` parameter: `Fasteners.makeScrew("M6HexHeadScrew", doc=doc)`

### SCREW MAKER WORKBENCH (if installed as ScrewMaker)
- `import ScrewMaker`
- `ScrewMaker.makeScrew("M6", "SocketCapScrew", 20, doc=doc)` — screw type, length in mm

### ASSEMBLY WORKBENCH
- `import Assembly`
- `asm = doc.addObject("Assembly::AssemblyObject", "Assembly")`
- `asm.addObject(obj)` — add a part to assembly
- `asm.addJoint("Fixed", part1, part2)` — constrain parts together

### DESIGN WORKFLOW (like a real mechanical engineer)
Follow this order for robust parametric models:
1. **Activate PartDesign** → create a Body → create a Sketch on a face/plane
2. **Activate Sketcher** → draw the 2D profile (lines, arcs, circles) → add constraints
3. **Switch back to PartDesign** → Pad the sketch → add features (Pocket, Fillet, Chamfer)
4. **Switch to Part** → boolean operations between bodies (Cut, Fuse, Common)
5. **Switch to Draft** → arrays, text annotations, dimension lines
6. **Switch to TechDraw** → create drawing sheets from the 3D model

Always prefer PartDesign workflow (Body → Sketch → Pad) over standalone Part primitives for parametric designs. Use Part primitives only for simple standalone shapes that don't need sketches.

### TECH DRAW WORKBENCH
Full TechDraw Python API is available. For simple cases use DrawingGenerator (already in scope):
```python
dg = DrawingGenerator()
ok, msg = dg.create_page(["Body", "Lid"], views=["top", "isometric"], scale=1.0)
```
For advanced drawings (sections, detail views, balloons, exploded views, projection groups), use TechDraw directly:
```python
import TechDraw
page = doc.addObject("TechDraw::DrawPage", "Page")
template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
template.Template = TechDraw.findTemplate("A4_Portrait_ISO.svg")  # or absolute path
page.Template = template

# View
view = doc.addObject("TechDraw::DrawViewPart", "TopView")
view.Source = [body]
view.Direction = (0, 0, 1)   # top: (0,0,1), front: (0,-1,0), right: (1,0,0), isometric: (1,-1,1)
view.Scale = 1.0
page.addView(view)

# Dimension
dim = doc.addObject("TechDraw::DrawViewDimension", "Dim")
dim.References2D = [(view, edge)]  # edge from view.getVisibleEdges()
dim.Type = "Distance"  # Distance, Length, Radius, Diameter
page.addView(dim)

# Projection Group (multi-view from one source)
proj = doc.addObject("TechDraw::DrawViewGroup", "Group")
proj.Source = bodies
proj.Scale = 1.0
page.addView(proj)

# Section view
section = doc.addObject("TechDraw::DrawViewSection", "Section")
section.Source = bodies
section.SectionOrigin = FreeCAD.Vector(50, 0, 0)
section.SectionDirection = (1, 0, 0)  # cut direction
page.addView(section)

# Detail view
detail = doc.addObject("TechDraw::DrawViewDetail", "Detail")
detail.BaseView = view
detail.Radius = 30
detail.Scale = 2.0
page.addView(detail)

# Balloons
balloon = doc.addObject("TechDraw::DrawViewBalloon", "Balloon")
balloon.SourceView = view
balloon.Text = "1"
balloon.OriginX = 10
balloon.OriginY = 20
page.addView(balloon)
```
TechDraw is READ-ONLY for 3D geometry — it only creates 2D projections. You cannot break the 3D model by using it.

### Part Primitives (Part::*)
| Type | Properties | Example |
|------|-----------|---------|
| Box | .Length, .Width, .Height | doc.addObject("Part::Box","Box") |
| Cylinder | .Radius, .Height, .Angle | doc.addObject("Part::Cylinder","Cyl") |
| Sphere | .Radius, .Angle1-3 | doc.addObject("Part::Sphere","Sphere") |
| Cone | .Radius1, .Radius2, .Height | doc.addObject("Part::Cone","Cone") |
| Torus | .Radius1, .Radius2, .Angle | doc.addObject("Part::Torus","Torus") |
| Tube | .InnerRadius, .OuterRadius, .Height | doc.addObject("Part::Tube","Tube") |
| Helix | .Pitch, .Height, .Radius | doc.addObject("Part::Helix","Helix") |
| Prism | .Polygon, .Height | doc.addObject("Part::Prism","Prism") |

### RECIPE: Simple Part::Box (Part workbench — no Body, no Profile needed)
```python
import FreeCAD
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Design")
box = doc.addObject("Part::Box", "EngineBlock")
box.Length = 80.0   # X dimension
box.Width = 100.0   # Y dimension
box.Height = 120.0  # Z dimension
box.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
)
doc.recompute()
```
⚠️ Part::Box does NOT use .Base, .Profile, .Sketch, or .Body.
   Those only exist on PartDesign features. For simple standalone shapes,
   use the Part workbench primitives exactly as shown above.
   For parametric features (pocket, fillet, hole), use PartDesign Body+Sketch instead.

### Part Modifiers
- Chamfer: .Base (shape), .Size (float)
- Fillet: .Base, .Radius
- Mirror: .Source, .Normal (Vector), .Base (Vector)
- Extrude: .Base, .Dir (Vector), .LengthFwd, .LengthRev
- Revolve: .Source, .Axis (Vector), .Angle
- Offset: .Source, .Value (float)
- Thickness: .Faces (list), .Thickness (float)
- Loft: doc.addObject("Part::Loft","N") → .Sections = [wire1, wire2]
- Sweep: doc.addObject("Part::Sweep","N") → .Sections, .Spine (wire)
- Section: doc.addObject("Part::Section","N") → .Base, .Tool (intersection)

### Boolean Operations
- Cut: doc.addObject("Part::Cut","N") → .Base, .Tool
- Fuse: doc.addObject("Part::MultiFuse","N") → .Shapes = [a,b,c]
- Common: doc.addObject("Part::MultiCommon","N") → .Shapes = [a,b]

### SheetMetal Workbench
- `import SheetMetal`
- SMSheet: base sheet → obj = doc.addObject("SheetMetal::Sheetmetal", "Sheet") → obj.Length, obj.Width, obj.Thickness
- SMBend: bend an edge → obj = doc.addObject("SheetMetal::Bend", "Bend") → obj.Base, obj.Angle, obj.Radius
- SMWall: add wall → doc.addObject("SheetMetal::Wall", "Wall") → obj.Length, obj.Angle
- SMFold: fold along line → doc.addObject("SheetMetal::Fold", "Fold") → obj.Base, obj.BendLine
- SMUnfold: unfold → doc.addObject("SheetMetal::Unfold", "Unfold") → obj.Base
- SMFlange: add flange → doc.addObject("SheetMetal::Flange", "Flange") → obj.Length, obj.Angle, obj.Radius

### PartDesign Workbench — TWO CATEGORIES OF FEATURES:

**A) Sketch-based features** (need `.Profile` property — NOTE: FreeCAD 1.0 uses `.Profile`, NOT `.Sketch`): Pad, Pocket, Revolution, Groove, Hole
  - Pad: body.newObject("PartDesign::Pad","N") → .Profile, .Length, .Reversed (bool)
  - Pocket: body.newObject("PartDesign::Pocket","N") → .Profile, .Length
  - Revolution: body.newObject("PartDesign::Revolution","N") → .Profile, .Angle, .Axis
  - Groove: body.newObject("PartDesign::Groove","N") → .Profile, .Angle
  - Hole: body.newObject("PartDesign::Hole","N") → .Profile, .Diameter, .Depth, .Threaded (bool)

**B) Primitive features** (dimension-based, NO `.Profile` property): AdditiveBox, AdditiveCylinder, etc.
  - AdditiveBox: body.newObject("PartDesign::AdditiveBox","N") → .Length, .Width, .Height
  - AdditiveCylinder: body.newObject("PartDesign::AdditiveCylinder","N") → .Radius, .Height
  - AdditiveSphere: body.newObject("PartDesign::AdditiveSphere","N") → .Radius
  - AdditiveCone: body.newObject("PartDesign::AdditiveCone","N") → .Radius1, .Radius2, .Height
  - AdditiveTorus: body.newObject("PartDesign::AdditiveTorus","N") → .Radius1, .Radius2
  - SubtractiveBox/Cylinder/Sphere/Cone/Torus: same pattern, remove material inside Body

- AdditivePipe: body.newObject("PartDesign::AdditivePipe","N") → .Spine, .Profile (single sketch) or .Profile=[sk1,sk2,...] for multisection + .SectionTransformation="Multisection"
- AdditiveLoft: body.newObject("PartDesign::AdditiveLoft","N") → .Sections (list)
- Fillet (PD): body.newObject("PartDesign::Fillet","N") → .Base, .Radius — NO .Profile
- Chamfer (PD): body.newObject("PartDesign::Chamfer","N") → .Base, .Size — NO .Profile
- **CRITICAL**: Only Pad/Pocket/Revolution/Groove/Hole have `.Profile`. Do NOT set `.Profile` on AdditiveBox or other primitives — they don't have it. (In FreeCAD 1.0 the property was renamed from `.Sketch` to `.Profile`.)

### Sketcher — THE KEY FREECAD FEATURE
```python
import Part, Sketcher
body = doc.addObject("PartDesign::Body","Body")
sketch = body.newObject("Sketcher::SketchObject","Sketch")

# Add geometry (vertex indices for constraints: 1=start, 2=end, 3=center)
geo = []
# Lines: (start_vec, end_vec)
geo.append(Part.LineSegment(FreeCAD.Vector(0,0), FreeCAD.Vector(50,0)))   # idx 0
geo.append(Part.LineSegment(FreeCAD.Vector(50,0), FreeCAD.Vector(50,50))) # idx 1
geo.append(Part.LineSegment(FreeCAD.Vector(50,50), FreeCAD.Vector(0,50))) # idx 2
geo.append(Part.LineSegment(FreeCAD.Vector(0,50), FreeCAD.Vector(0,0)))   # idx 3
# Circles:
geo.append(Part.Circle(FreeCAD.Vector(25,25), FreeCAD.Vector(0,0,1), 15)) # idx 4

sketch.addGeometry(geo)

# Constraints: Sketcher.Constraint(Type, args...)
# Lines have vertex 1=start, 2=end. Circles have vertex 3=center.
con = []
# Close the 4-line rectangle with coincident constraints
con.append(Sketcher.Constraint('Coincident', 0, 2, 1, 1))  # line0 end -> line1 start
con.append(Sketcher.Constraint('Coincident', 1, 2, 2, 1))  # line1 end -> line2 start
con.append(Sketcher.Constraint('Coincident', 2, 2, 3, 1))  # line2 end -> line3 start
con.append(Sketcher.Constraint('Coincident', 3, 2, 0, 1))  # line3 end -> line0 start
# Anchor the rectangle at origin (3-arg: GeoIdx, PointIdx, Value)
con.append(Sketcher.Constraint('DistanceX', 0, 1, 0.0))   # fix line0 start at x=0
con.append(Sketcher.Constraint('DistanceY', 0, 1, 0.0))   # fix line0 start at y=0
# Size the rectangle (3-arg horizontal/vertical distance)
con.append(Sketcher.Constraint('DistanceX', 0, 2, 50.0))  # width of line0 = 50
con.append(Sketcher.Constraint('DistanceY', 1, 2, 50.0))  # height of line1 = 50
# Circle radius (2-arg: GeoIdx, Value)
con.append(Sketcher.Constraint('Radius', 4, 15.0))        # circle radius = 15
# Fix circle center position (3-arg: GeoIdx, PointIdx, Value)
con.append(Sketcher.Constraint('DistanceX', 4, 3, 25.0))  # circle center x=25
con.append(Sketcher.Constraint('DistanceY', 4, 3, 25.0))  # circle center y=25

sketch.addConstraint(con)
doc.recompute()

# Then pad:
pad = body.newObject("PartDesign::Pad","Pad")
pad.Profile = sketch
pad.Length = 30.0
pad.Label = "Pad"
doc.recompute()
```

### SKETCH CONSTRAINT REFERENCE — CRITICAL: READ CAREFULLY
- **Vertex indices (1-based, NEVER 0)**: Lines/arcs: 1=start, 2=end. Circles: 3=center.
- **ORDER MATTERS**: Add ALL geometry first with `sketch.addGeometry(geo_list)`, THEN add ALL constraints with `sketch.addConstraint(con_list)`. Indexes are assigned in the order geometry is added. Adding constraints mid-way shifts indexes and breaks everything.
- **Constraint arg patterns**:
  - `Constraint('Coincident', Geo1, Pos1, Geo2, Pos2)` — 4 args: make two vertices touch
  - `Constraint('DistanceX', Geo, Pos, Value)` — **3 args** (NOT 5). Fix X coord of a vertex.
  - `Constraint('DistanceY', Geo, Pos, Value)` — **3 args** (NOT 5). Fix Y coord of a vertex.
  - `Constraint('Distance', Geo1, Pos1, Geo2, Pos2, Value)` — **5 args**. Dist between two vertices.
  - `Constraint('Radius', Geo, Value)` — 2 args: set radius
  - `Constraint('Horizontal', Geo)` — 1 arg: make line horizontal
  - `Constraint('Vertical', Geo)` — 1 arg: make line vertical
  - `Constraint('Parallel', Geo1, Geo2)` — 2 args
  - `Constraint('Perpendicular', Geo1, Geo2)` — 2 args
  - `Constraint('Tangent', Geo1, Geo2)` — 2 args
  - `Constraint('Angle', Geo1, Geo2, Value)` — 3 args
  - `Constraint('Symmetric', Geo1, Pos1, Geo2, Pos2, SymGeo, SymPos)` — 6 args
  - `Constraint('Block', Geo)` — 1 arg
- **WRONG**: `Sketcher.Constraint('DistanceX', 0, 1, 0, 0)` — this passes 5 args to a 3-arg function.
- **RIGHT**: `Sketcher.Constraint('DistanceX', 0, 1, 0.0)` — 3 args: Geo=0, Vertex=1, Value=0.0

### PAD + FILLET APPROACH (preferred over complex sketches)
For rounded profiles (phone cases, enclosures, brackets with rounded corners):
DO NOT sketch arcs and constraints. Instead:
1. Sketch a simple RECTANGLE (4 lines, 4 coincident constraints)
2. PAD it to desired thickness
3. Use `PartDesign::Fillet` on the vertical edges for the corner radius

```python
import FreeCAD, Part, Sketcher
doc = FreeCAD.ActiveDocument
body = doc.addObject("PartDesign::Body", "Body")
sketch = body.newObject("Sketcher::SketchObject", "Sketch")
geo = []
geo.append(Part.LineSegment(FreeCAD.Vector(0,0), FreeCAD.Vector(75,0)))
geo.append(Part.LineSegment(FreeCAD.Vector(75,0), FreeCAD.Vector(75,150)))
geo.append(Part.LineSegment(FreeCAD.Vector(75,150), FreeCAD.Vector(0,150)))
geo.append(Part.LineSegment(FreeCAD.Vector(0,150), FreeCAD.Vector(0,0)))
sketch.addGeometry(geo)
con = []
con.append(Sketcher.Constraint('Coincident', 0, 2, 1, 1))
con.append(Sketcher.Constraint('Coincident', 1, 2, 2, 1))
con.append(Sketcher.Constraint('Coincident', 2, 2, 3, 1))
con.append(Sketcher.Constraint('Coincident', 3, 2, 0, 1))
con.append(Sketcher.Constraint('DistanceX', 0, 1, 0.0))  # 3 args: Geo, Vertex, Value
con.append(Sketcher.Constraint('DistanceY', 0, 1, 0.0))
con.append(Sketcher.Constraint('DistanceX', 0, 2, 75.0))
con.append(Sketcher.Constraint('DistanceY', 1, 2, 150.0))
sketch.addConstraint(con)
doc.recompute()

# Pad the rectangle
pad = body.newObject("PartDesign::Pad", "BodyPad")
pad.Profile = sketch
pad.Length = 10.0
doc.recompute()

# Now fillet the 4 vertical edges for rounded corners
fillet = body.newObject("PartDesign::Fillet", "Fillet")
fillet.Base = (pad, ["Edge1", "Edge2", "Edge3", "Edge4"])
fillet.Radius = 12.0
doc.recompute()
```
This is FAR simpler, more reliable, and avoids all the arc/constraint complexity. Use this approach whenever you need a rounded rectangular profile.

### AUTO-CONSTRAINING EXISTING SKETCHES
You can analyze and constrain any existing sketch — even ones the user drew by hand:
```python
import FreeCAD, Part, Sketcher
doc = FreeCAD.ActiveDocument
sketch = doc.getObject("Sketch")  # get the existing sketch

# Read what's already there
print(f"Geometry: {len(sketch.Geometry)} items")
for i, g in enumerate(sketch.Geometry):
    if hasattr(g, 'TypeId'):
        print(f"  Geo {i}: {g.TypeId}")
print(f"Existing constraints: {len(sketch.Constraints)}")

# Determine what constraints are needed:
# 1. Identify endpoints that overlap (should be coincident but aren't)
# 2. Identify lines that are roughly horizontal/vertical
# 3. Identify parallel/perpendicular pairs
# 4. Identify missing dimension constraints

import math
endpoints = {}  # (x, y) rounded -> [(geo_idx, 1=start or 2=end)]
for i, g in enumerate(sketch.Geometry):
    if hasattr(g, 'StartPoint'):
        eps = (round(g.StartPoint.x, 2), round(g.StartPoint.y, 2))
        eps_r = (round(g.StartPoint.x), round(g.StartPoint.y))
        endpoints.setdefault(eps_r, []).append((i, 1))
    if hasattr(g, 'EndPoint'):
        epe = (round(g.EndPoint.x, 2), round(g.EndPoint.y, 2))
        epe_r = (round(g.EndPoint.x), round(g.EndPoint.y))
        endpoints.setdefault(epe_r, []).append((i, 2))

cons = []  # new constraints to add

# Coincident constraints — join overlapping endpoints
for pos, pts in endpoints.items():
    for a in range(len(pts)):
        for b in range(a+1, len(pts)):
            cons.append(Sketcher.Constraint('Coincident',
                pts[a][0], pts[a][1], pts[b][0], pts[b][1]))

# Horizontal/Vertical for near-straight lines
for i, g in enumerate(sketch.Geometry):
    if hasattr(g, 'StartPoint') and hasattr(g, 'EndPoint'):
        dx = g.EndPoint.x - g.StartPoint.x
        dy = g.EndPoint.y - g.StartPoint.y
        if dx != 0 or dy != 0:
            angle = math.atan2(dy, dx)
            if abs(angle) < 0.05 or abs(angle - math.pi) < 0.05:
                cons.append(Sketcher.Constraint('Horizontal', i))
            elif abs(abs(angle) - math.pi/2) < 0.05:
                cons.append(Sketcher.Constraint('Vertical', i))

# Anchor at origin
cons.append(Sketcher.Constraint('DistanceX', 0, 1, 0.0))
cons.append(Sketcher.Constraint('DistanceY', 0, 1, 0.0))

# Add all new constraints in one call
sketch.addConstraint(cons)
doc.recompute()
print(f"Added {len(cons)} auto-generated constraints")
```
- `sketch.Geometry` — list of Part geometry objects (LineSegment, ArcOfCircle, Circle, etc.)
- `sketch.Constraints` — list of existing constraint objects
- Detect overlapping endpoints: compare `StartPoint`/`EndPoint` positions across geometry indices
- Detect horizontal lines: angle ≈ 0 or π radians from +X axis
- Detect vertical lines: angle ≈ ±π/2 radians from +X axis
- Always anchor at least one point to the origin (DistanceX=0, DistanceY=0)
- You can `addConstraint(cons_list)` multiple times — constraints accumulate, they don't replace

### ORGANIC / CURVED SHAPES (hearts, teardrops, leafs, etc.)
For smooth curved profiles, use Sketcher arcs and BSplines:
```python
import FreeCAD, Part, Sketcher, math
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Design")
body = doc.addObject("PartDesign::Body", "Body")
sketch = body.newObject("Sketcher::SketchObject", "Sketch")

geo = []
# Arc on the left side: center (0,0), radius 30, from 90° (top) to 270° (bottom)
geo.append(Part.ArcOfCircle(
    Part.Circle(FreeCAD.Vector(0,0), FreeCAD.Vector(0,0,1), 30),
    math.radians(90), math.radians(270)))
# BSpline closing the right side: starts at arc end (0,-30), ends at arc start (0,30)
spline = Part.BSplineCurve()
spline.interpolate([
    FreeCAD.Vector(0, -30),
    FreeCAD.Vector(30, -10),
    FreeCAD.Vector(20, 20),
    FreeCAD.Vector(0, 30),
])
geo.append(spline)

sketch.addGeometry(geo)
doc.recompute()
```
- `Part.ArcOfCircle(circle, startAngle, endAngle)` — circle=Part.Circle(center,normal,radius), angles in radians
- `Part.BSplineCurve().interpolate([v1,v2,v3,...])` — smooth curve through points

### Draft Workbench
- import Draft
- Draft.makeLine(v1,v2), Draft.makeWire([v1..vn], closed=True)
- Draft.makeCircle(radius), Draft.makeArc(radius,startangle,endangle)
- Draft.makeRectangle(20,10), Draft.makePolygon(sides=6, radius=10)
- Draft.makeBSpline([v1,v2,v3]), Draft.makeBezCurve([v1,v2,v3])
- Draft.makeArray(obj, FreeCAD.Vector(stepX,0,0), count)
- Draft.makePathArray(obj, path, count)
- Draft.makeShapeString(String="Text", FontFile="C:/Windows/Fonts/arial.ttf", Size=10)
- Draft.makeDimension(v1, v2), Draft.makeText("hello", v1)

### TechDraw
- import TechDraw
- page = doc.addObject("TechDraw::DrawPage","Page")
- template = doc.addObject("TechDraw::DrawSVGTemplate","Template")
- template.Template = FreeCAD.getResourceDir() + "Mod/TechDraw/Templates/A4_LandscapeTD.svg"
- page.Template = template
- view = doc.addObject("TechDraw::DrawViewPart","View")
- view.Source = body_or_part
- view.Scale = 1.0
- view.Direction = FreeCAD.Vector(0,0,1)
- page.addView(view)
- TechDraw.projectToSVG(page)  # export

### App::Part Assembly
- part_container = doc.addObject("App::Part","Assembly")
- part_container.addObject(obj)  # add to assembly
- Each obj keeps its own Placement relative to the assembly
- Group: doc.addObject("App::DocumentObjectGroup","Group") → .addObject(obj)
- Origin: doc.addObject("App::Origin","Origin") → group feature

### Materials
- mat = FreeCAD.Material()
- mat.Material = "Steel"  # or "Aluminum", "Brass", "Copper", "Plastic"
- for obj in objects: obj.ViewObject.Material = mat  # requires Part workbench
- Simple: obj.ViewObject.ShapeMaterial = mat

### Import/Export
- import ImportGui  # STEP import with GUI
- import Import  # console import
- Import.export(objects, "path.step")  # STEP export
- Import.export(objects, "path.stl")  # STL export
- Import.insert("path.step", doc.Name)  # import STEP into doc
- import Mesh; Mesh.export(objects, "path.stl")
- import Mesh; mesh = Mesh.Mesh("path.stl")
- shape = Part.Shape()
- shape.read("path.step")  # deprecated, use import

### PCB / STEP IMPORT + ENCLOSURE GENERATION
You can import any 3D file exported from KiCad (STEP, IGES, BREP, STL) and generate a custom enclosure.

For .kicad_pcb files (not STEP), use the built-in pipeline:
```python
import pcb_parser
from enclosure_template import build_from_parsed

data = pcb_parser.parse("/path/to/board.kicad_pcb")
# Optional config overrides:
params = {
    "wall_thickness": 3.0,
    "margin": 6.0,
    "pcb_standoff_height": 5.0,
    "headroom": 10.0,
    "screw_size": "M3",
    "enable_vents": True,
    "enable_label_recess": True,
    "enable_snaps": False,
}
success, msg = build_from_parsed(data, params)
```
This generates: Shell_Final (tray), Lid_Final (cover), PCB_Board (reference), Components (reference), MountingHole rings — all with correct dimensions, standoffs, boss towers, vent slots, connector cutouts (USB, HDMI, RJ45, etc.), and a snap-fit lip. Use `params` to tweak wall_thickness, margin, headroom, vents, label recess, etc.

For STEP files, import and measure:
```python
import Import
doc = FreeCAD.ActiveDocument
Import.insert("/path/to/pcb.step", doc.Name)
pcb = doc.Objects[-1]
bb = pcb.Shape.BoundBox
```
Then call `build_from_parsed` with a manual board dict:
```python
from enclosure_template import build_from_parsed
data = {
    "dimensions": {"width": bb.XLength, "height": bb.YLength,
                   "x_min": 0, "y_min": 0, "x_max": bb.XLength, "y_max": bb.YLength},
    "mounting_holes": [],
    "components": [],
    "edge_connectors": [],
}
success, msg = build_from_parsed(data, params)
```

ALWAYS use build_from_parsed() for enclosures. Do NOT write raw Part.makeBox/Part.makeCylinder — the template handles wall thickness, standoffs, vents, lip, lid, and connectors automatically.

### Measurement
- obj.Shape.Volume (float, mm^3)
- obj.Shape.Area (float, mm^2)
- obj.Shape.CenterOfMass (FreeCAD.Vector)
- obj.Shape.BoundBox (XMin,YMin,ZMin,XMax,YMax,ZMax)
- obj.Shape.Mass (if density set)
- len(obj.Shape.Faces), len(obj.Shape.Edges), len(obj.Shape.Vertices)
- obj.Shape.BoundBox.DiagonalLength
- Part.show(obj.Shape)  # visualize shape
- Part.show(shape.cut(other_shape))  # visualize boolean without adding to doc

### Document Operations
- FreeCAD.listDocuments() → dict of open documents {name: doc}
- FreeCAD.openDocument("path/to/file.FCStd")  # open file
- FreeCAD.open("path/to/file.step")  # open STEP
- FreeCAD.setActiveDocument("DocName")
- doc = FreeCAD.ActiveDocument
- doc.save()  # save
- doc.saveAs("path/to/new_file.FCStd")
- doc.DocumentName = "NewName"
- FreeCAD.closeDocument("DocName")
- FreeCAD.newDocument("DocName")

### SPATIAL TAGS (user can click geometry in the 3D viewport)
The user can click faces/edges/vertices in the 3D view and they get inserted as tags like `@Box001.Face6` or `@Pad.Edge12`.
- `@ObjectName.Face6` means the 6th face of that object
- `@Cylinder.Edge3` means the 3rd edge of that cylinder
- To reference in code: `obj = doc.getObject("Box001"); face = obj.Shape.Face6`
- The user selected these specifically — use them directly, do NOT try to find them by position or guess Face/Edge numbers.

### MULTI-BODY & MULTI-STEP DESIGN PATTERNS
1. **Each solid needs its own Body**. A PartDesign Body = one contiguous solid. For base+lid, create TWO bodies:
   ```python
   base_body = doc.addObject("PartDesign::Body", "BaseBody")
   lid_body = doc.addObject("PartDesign::Body", "LidBody")
   ```
2. **Creating a sketch on an existing face — CANONICAL BORE/POCKET RECIPE**:
   Use `AttachmentSupport` to map a new sketch onto a Pad's face, with face discovery loop:
   ```python
   import FreeCAD, Part, Sketcher
   doc = FreeCAD.ActiveDocument
   body = doc.getObject("Body")
   
   # Get the most recent solid feature (the one you just padded)
   pad = body.Group[-1]
   
    # Find the correct face by sampling center coordinates — NEVER assume Face6
    target_face = None
    for i, face in enumerate(pad.Shape.Faces):
        center = face.CenterOfMass
        # Top face: highest Z, normal pointing +Z
        if abs(center.z - pad.Shape.BoundBox.ZMax) < 1.0:
            target_face = f"Face{i+1}"    # ← COLLECT THE INDEX AS A STRING
            break                         #    NOT the face object itself
   if target_face is None:
       target_face = "Face6"  # fallback for simple box
   
   # Create sketch and attach to face
   sketch = body.newObject("Sketcher::SketchObject", "FeatureSketch")
   sketch.AttachmentSupport = (pad, target_face)
   sketch.MapMode = "FlatFace"
   doc.recompute()
   
   # Add geometry (e.g. circle for bore) and pocket
   sketch.addGeometry(Part.Circle(FreeCAD.Vector(0,0,0), FreeCAD.Vector(0,0,1), 20), False)
   doc.recompute()
   pocket = body.newObject("PartDesign::Pocket", "Bore")
   pocket.Profile = sketch
   pocket.Depth = 50.0
   pocket.Reversed = True   # True = cut into body from face
   doc.recompute()
   ```
    CRITICAL: Use `body.Group[-1]` to get the most recent feature. Iterate faces by center coordinates. Never assume a hardcoded face number.
    To target a specific face: check `face.CenterOfMass` and `face.normalAt(0,0)` against the desired position/orientation.
    CRITICAL: `AttachmentSupport` takes a face NAME string like "Face6", NOT a Part.Face object.
    Build the face index string in the loop with `f"Face{i+1}"` and pass THAT to AttachmentSupport.
 3. **Cavity/shell from a pad**: After padding a base, create a new sketch on the top face, draw a smaller rectangle inset by wall thickness, then Pocket it to the desired depth.
4. **Standoffs/screw posts inside a body**: Use `AdditiveCylinder` NOT `Part::Cylinder`:
   ```python
   post = body.newObject("PartDesign::AdditiveCylinder", "Standoff1")
   post.Radius, post.Height = 2.5, 8
   post.Placement.Base = FreeCAD.Vector(10, 10, 0)
   ```
5. **Screw holes through standoffs**: Use `SubtractiveCylinder` or Pocket a sketch on the post's top face.
6. **Lid as separate body**: After base is done, create a new Body, sketch the same outer rectangle on XY, Pad to lid thickness (2-3mm), then position it above the base.

### IMPORTANT RULES
1. Always: doc = FreeCAD.ActiveDocument; if not doc: doc = FreeCAD.newDocument("Design")
2. Always: doc.recompute(); FreeCAD.Gui.SendMsgToActiveView("ViewFit") at end
3. PartDesign features (Pad, Pocket, Revolution, Groove, Hole, Fillet, Chamfer) MUST be created via body.newObject() — NEVER via doc.addObject()
4. Sketches for PartDesign MUST be created via body.newObject("Sketcher::SketchObject","Name")
5. Use doc.getObject("InternalName") to find existing objects. NEVER use doc.ObjectName attribute syntax.
6. For PartDesign workflow: Body → Sketch → Pad/Pocket
7. Use obj.Label for display names. Keep names unique.
8. BEFORE accessing .Shape, .Radius, .Length, or any geometry property on an object, ALWAYS check for None:
   obj = doc.getObject("SomeName")
   if obj is None: raise Exception(f"Could not find SomeName")
   if not hasattr(obj, 'Shape') or obj.Shape is None: raise Exception(f"{obj.Label} has no valid Shape")
9. When editing existing objects, read their current properties FIRST, then modify:
   obj = doc.getObject("Pad")
   old_len = obj.Length  # read first
   obj.Length = old_len + 5.0  # then modify
10. Properties like .Selectable live on .ViewObject, not on the object itself: obj.ViewObject.Selectable = False
11. Space objects 200-300mm apart.
12. Color each new object distinctively via .ViewObject.ShapeColor

### PART HELPER FUNCTIONS (use these to write cleaner code):
Define these at the top of your code block for compact geometry:
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
These let you write `box(100,60,40)` instead of `Part.makeBox(100,60,40, FreeCAD.Vector(0,0,0))`,
and `fuse(obj, [list_of_parts])` instead of chaining `.fuse()` calls.
For rounded-corner boxes use `EnclosureBuilder.rrect()` (import from enclosure_builder).
For rotated boxes use `EnclosureBuilder.rotbox()`.
"""


