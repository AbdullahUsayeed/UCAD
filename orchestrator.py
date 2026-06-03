# orchestrator.py - GOD-TIER AI AGENT FOR FREECAD
import FreeCAD, FreeCADGui
import urllib.request, json, re, math, traceback, os, datetime, ast
from compat import QtCore
from assembly_graph import AssemblyGraph

# ═══════════════════════════════════════════════════════════════
#  FREECAD KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════
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
- Run `FreeCADGui.listCommands()` to discover ALL available commands.
- You can call any command by name — no need to know the toolbar location.

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

- AdditivePipe: body.newObject("PartDesign::AdditivePipe","N") → .Spine, .Profile
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
You can import any 3D file exported from KiCad (STEP, IGES, BREP, STL) and generate a custom enclosure:
```python
import Import
doc = FreeCAD.ActiveDocument
# Import the PCB STEP
Import.insert("/path/to/pcb.step", doc.Name)
pcb = doc.Objects[-1]  # last added is the PCB
bb = pb.BoundBox
```

After import, analyze the board:
- `pcb.Shape.BoundBox` → XLength, YLength, ZLength for overall dimensions
- `pcb.Shape.Faces` → inspect each face, find the top face (largest Z-facing face)
- `pcb.Shape.Edges` → edge lengths, positions
- `pcb.Shape.Vertexes` → vertex positions (mounting holes appear as circular edges)
- `hole_edges = [e for e in pcb.Shape.Edges if isinstance(e.Curve, Part.Circle)]` — find all holes
- `pcb.Shape.distToShape(other_shape)` — measure clearance between board and enclosure wall

Enclosure generation pattern (parametric box with lid):
```python
body = doc.addObject("PartDesign::Body", "Body")
# Bottom box
box = doc.addObject("Part::Box", "EnclosureBase")
box.Length = bb.XLength + 4  # 2mm wall on each side
box.Width = bb.YLength + 4
box.Height = bb.ZLength + 10  # 10mm internal height
# Cutout for the PCB cavity
cavity = doc.addObject("Part::Box", "Cavity")
cavity.Length = bb.XLength
cavity.Width = bb.YLength
cavity.Height = bb.ZLength + 2
cavity.Placement.Base = FreeCAD.Vector(2, 2, 0)  # offset to center
cut = doc.addObject("Part::Cut", "Enclosure")
cut.Base = box
cut.Tool = cavity
# Standoffs for mounting holes (one at each PCB corner)
for v in pcb.Shape.Vertexes:
    if v.Point.z < 0.1:  # only bottom vertices
        standoff = doc.addObject("Part::Cylinder", "Standoff")
        standoff.Radius = 2.5
        standoff.Height = bb.ZLength
        standoff.Placement.Base = v.Point
# Lid
lid = doc.addObject("Part::Box", "Lid")
lid.Length = bb.XLength + 4
lid.Width = bb.YLength + 4
lid.Height = 2
lid.Placement.Base = FreeCAD.Vector(0, 0, bb.ZLength + 5)
doc.recompute()
```
Always import the file first, measure the board dimensions with BoundBox, then build the enclosure parametrically using those dimensions with appropriate wall thickness (typically 2mm) and clearance (0.5mm per side).

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
2. **Creating a sketch on an existing face**: Use `AttachmentSupport` to map a new sketch onto a Pad's face:
   ```python
   sketch = body.newObject("Sketcher::SketchObject", "CavitySketch")
   sketch.AttachmentSupport = (pad_obj, "Face6")  # Face6 is typically the top face of a simple Pad
   sketch.MapMode = "FlatFace"
   ```
   To find the correct face, iterate `pad_obj.Shape.Faces` and check the face normal or center Z height.
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
5. Use doc.getObject("Name") or iterate doc.Objects to find existing objects
6. For PartDesign workflow: Body → Sketch → Pad/Pocket
7. Use obj.Label for display names. Keep names unique.
8. Space objects 200-300mm apart.
9. Color each new object distinctively via .ViewObject.ShapeColor

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

# ═══════════════════════════════════════════════════════════════
#  ERROR TRANSLATION
# ═══════════════════════════════════════════════════════════════
ERROR_TRANSLATIONS = [
    (r"Recursive.*computation", "circular_dep", "Circular dependency. The operation would loop infinitely. Try a different modeling approach."),
    (r"BRep.*Not.*Plane", "bad_plane", "Sketch/face is not on a valid plane. Always use a standard plane (XY/XZ/YZ) or a planar face."),
    (r"no.*solid|NullShape|Shape.*not.*null", "no_solid", "No valid solid. The shape is open or non-manifold. Close all loops and ensure watertight geometry."),
    (r"failed to recompute", "recompute_fail", "Model recompute failed. Likely conflicting constraints or invalid geometry after changes."),
    (r"null.*pointer|access.*violation|Access violation", "null_ptr", "Internal null reference. The object may have been deleted or the reference is stale."),
    (r"not found|does not exist", "not_found", "Object not found in document. Check that the object name/label is correct."),
    (r"cannot.*compute", "compute_fail", "Cannot compute geometry. The input might be too complex or invalid."),
    (r"Sketch.*invalid|sketch.*constraint", "bad_sketch", "Sketch is invalid — open vertices, over-constrained, or overlapping geometry."),
    (r"no.*shape", "no_shape", "Object has no shape. Recompute the document or create the object properly first."),
    (r"has no attribute 'Sketch'", "pad_sketch_attr", "FreeCAD 1.0 renamed .Sketch → .Profile on Pad/Pocket/Revolution/Groove/Hole. Use: pad.Profile = sketch (NOT pad.Sketch = sketch). Also ensure the sketch is inside the body."),
    (r"AttributeError.*has no attribute", "bad_attr", "Object does not have that property/attribute. Check the FreeCAD API reference for correct property names."),
    (r"AttributeError", "bad_attr_gen", "AttributeError: the code tried to access a property that doesn't exist on the object."),
    (r"NameError", "name_error", "NameError: a variable is undefined. Check for typos or missing imports."),
    (r"TypeError", "type_error", "TypeError: wrong data type passed to a function. E.g., string instead of number."),
    (r"IndexError", "index_error", "IndexError: list index out of range. Check that the list has the expected number of items."),
    (r"KeyError", "key_error", "KeyError: dictionary key not found."),
    (r"ImportError.*not in the allowlist", "blocked_import", "Import blocked: that module is not in the security allowlist. Use only: FreeCAD, FreeCADGui, Part, PartDesign, Sketcher, Mesh, Draft, Import, math."),
    (r"ImportError", "import_error", "ImportError: module not found. Use only standard FreeCAD modules."),
    (r"ZeroDivisionError", "div_zero", "Division by zero in the code."),
    (r"ValueError", "value_error", "ValueError: an operation received an invalid value. Check dimensions are positive."),
    (r"RuntimeError", "runtime_error", "RuntimeError in FreeCAD. Often caused by invalid object state or missing dependencies."),
    (r"Base::PyException", "freecad_exception", "FreeCAD internal error. The Python API call was rejected — check object types and parameters."),
]

# Strategy hints for the AI based on error category
ERROR_STRATEGIES = {
    "bad_plane": "Instead of using specific planes, create a sketch on a standard plane (XY) and use MapMode or AttachmentOffset.",
    "no_solid": "Use PartDesign workflow: Body -> Sketch -> Pad to ensure watertight solids. Avoid using raw Part::Box if you need booleans later.",
    "recompute_fail": "Simplify the approach. Create one feature at a time with doc.recompute() after each. Verify each step works before adding more.",
    "bad_sketch": "Keep sketches simple. Use only lines, arcs, and circles. Add coincident constraints at all endpoints to ensure closed profiles.",
    "bad_attr": "Check the exact property names. Part::Box uses Length/Width/Height. PartDesign::Pad uses .Profile (FreeCAD 1.0, NOT .Sketch) and .Length. Body uses .newObject().",
    "pad_sketch_attr": "FreeCAD 1.0 renamed .Sketch → .Profile. Use pad.Profile = sketch (NOT .Sketch). Example: pad = body.newObject('PartDesign::Pad', 'Pad'); pad.Profile = sketch; pad.Length = 10; doc.recompute().",
    "name_error": "You likely referenced a variable that wasn't created yet. Use explicit variable assignments and don't rely on FreeCAD auto-naming.",
    "blocked_import": "Remove that import. The required functionality is available through the allowed modules.",
    "freecad_exception": "This usually means you're using the wrong type of object for the operation. Try a different FreeCAD API approach.",
}

def translate_error(error_text):
    """Returns (short_diagnosis, strategy_tip) or (None, None)."""
    for pattern, code, hint in ERROR_TRANSLATIONS:
        if re.search(pattern, error_text, re.IGNORECASE):
            strat = ERROR_STRATEGIES.get(code, "")
            if strat:
                return f"Type: {code}. {hint}", f"Strategy: {strat}"
            return f"Type: {code}. {hint}", ""
    return "Unknown error. Check the traceback.", ""

# ═══════════════════════════════════════════════════════════════
#  DESIGN TEMPLATES
# ═══════════════════════════════════════════════════════════════
TEMPLATES = {
    "bracket": {
        "desc": "L-bracket with holes",
        "code": """```python
import FreeCAD
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Bracket")
# Vertical plate
vert = doc.addObject("Part::Box", "VerticalPlate")
vert.Length, vert.Width, vert.Height = 10, 80, 120
vert.ViewObject.ShapeColor = (0.5, 0.7, 1.0)
vert.Label = "Vertical Plate"
# Horizontal plate
horiz = doc.addObject("Part::Box", "HorizontalPlate")
horiz.Length, horiz.Width, horiz.Height = 80, 10, 120
horiz.Placement.Base = FreeCAD.Vector(0, -10, 0)
horiz.ViewObject.ShapeColor = (0.5, 0.7, 1.0)
horiz.Label = "Horizontal Plate"
# Fuse them
fuse = doc.addObject("Part::MultiFuse", "BracketBody")
fuse.Shapes = [vert, horiz]
fuse.Label = "Bracket Body"
# Hole in vertical plate
hole1 = doc.addObject("Part::Cylinder", "Hole1")
hole1.Radius, hole1.Height = 6, 20
hole1.Placement.Base = FreeCAD.Vector(5, 40, 60)
hole1.ViewObject.ShapeColor = (0.3, 0.3, 0.3)
cut1 = doc.addObject("Part::Cut", "Cut1")
cut1.Base = fuse
cut1.Tool = hole1
hole2 = doc.addObject("Part::Cylinder", "Hole2")
hole2.Radius, hole2.Height = 6, 20
hole2.Placement.Base = FreeCAD.Vector(5, 40, 20)
cut2 = doc.addObject("Part::Cut", "Cut2")
cut2.Base = cut1
cut2.Tool = hole2
# Fillet edges
fillet = doc.addObject("Part::Fillet", "Fillet")
fillet.Base = cut2
fillet.Radius = 5
fillet.Label = "Bracket"
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")
print("Bracket created!")
```"""
    },
    "flange": {
        "desc": "Circular flange with bolts",
        "code": """```python
import FreeCAD
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Flange")
# Base ring
base = doc.addObject("Part::Cylinder", "BaseRing")
base.Radius, base.Height = 100, 20
base.ViewObject.ShapeColor = (0.6, 0.6, 0.6)
base.Label = "Base Ring"
# Inner hole
inner = doc.addObject("Part::Cylinder", "InnerHole")
inner.Radius, inner.Height = 60, 22
inner.Placement.Base = FreeCAD.Vector(0, 0, -1)
# Cut hole
cut = doc.addObject("Part::Cut", "RingCut")
cut.Base = base
cut.Tool = inner
# Bolt holes
import math
current = cut
for angle in range(0, 360, 60):
    rad = math.radians(angle)
    x = 80 * math.cos(rad)
    y = 80 * math.sin(rad)
    bolt = doc.addObject("Part::Cylinder", f"BoltHole_{angle}")
    bolt.Radius, bolt.Height = 10, 22
    bolt.Placement.Base = FreeCAD.Vector(x, y, -1)
    next_cut = doc.addObject("Part::Cut", f"BoltCut_{angle}")
    next_cut.Base = current
    next_cut.Tool = bolt
    current = next_cut
current.Label = "Flange"
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")
print("Flange created!")
```"""
    },
    "pipe": {
        "desc": "Pipe with fittings",
        "code": """```python
import FreeCAD
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Pipe")
# Outer pipe
outer = doc.addObject("Part::Cylinder", "OuterPipe")
outer.Radius, outer.Height = 50, 200
outer.ViewObject.ShapeColor = (0.7, 0.7, 0.5)
outer.Label = "Pipe Outer"
# Inner hole
inner = doc.addObject("Part::Cylinder", "InnerPipe")
inner.Radius, inner.Height = 40, 202
inner.Placement.Base = FreeCAD.Vector(0, 0, -1)
# Cut
pipe = doc.addObject("Part::Cut", "PipeBody")
pipe.Base = outer
pipe.Tool = inner
pipe.Label = "Pipe"
# Cap on top
cap = doc.addObject("Part::Cylinder", "Cap")
cap.Radius, cap.Height = 55, 10
cap.Placement.Base = FreeCAD.Vector(0, 0, 200)
cap.ViewObject.ShapeColor = (0.5, 0.5, 0.3)
cap.Label = "Cap"
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")
print("Pipe with cap created!")
```"""
    },
    "gear": {
        "desc": "Simple spur gear",
        "code": """```python
import FreeCAD, math
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Gear")
num_teeth = 12
pitch_radius = 50
tooth_height = 12
# Main body
gear = doc.addObject("Part::Cylinder", "GearBody")
gear.Radius, gear.Height = pitch_radius, 20
gear.ViewObject.ShapeColor = (0.6, 0.6, 0.6)
gear.Label = "Gear Body"
# Center hole
hole = doc.addObject("Part::Cylinder", "CenterHole")
hole.Radius, hole.Height = 15, 22
hole.Placement.Base = FreeCAD.Vector(0, 0, -1)
body = doc.addObject("Part::Cut", "GearRing")
body.Base = gear
body.Tool = hole
# Add teeth
current = body
for i in range(num_teeth):
    angle = (360.0 / num_teeth) * i
    rad = math.radians(angle)
    x = pitch_radius * math.cos(rad)
    y = pitch_radius * math.sin(rad)
    tooth = doc.addObject("Part::Box", f"Tooth_{i}")
    tooth.Length, tooth.Width, tooth.Height = tooth_height, 8, 20
    tooth.Placement = FreeCAD.Placement(
        FreeCAD.Vector(x - tooth_height/2, y - 4, -1),
        FreeCAD.Rotation(FreeCAD.Vector(0,0,1), angle)
    )
    fuse = doc.addObject("Part::MultiFuse", f"AddTooth_{i}")
    fuse.Shapes = [current, tooth]
    current = fuse
current.Label = "Gear"
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")
print("Gear created! {} teeth".format(num_teeth))
```"""
    },
    "sketch_box": {
        "desc": "Box with sketched base + pad",
        "code": """```python
import FreeCAD, Part, Sketcher
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("SketchDesign")
body = doc.addObject("PartDesign::Body", "Body")
body.Label = "Main Body"
sketch = body.newObject("Sketcher::SketchObject", "Sketch")
geo = []
geo.append(Part.LineSegment(FreeCAD.Vector(0,0), FreeCAD.Vector(100,0)))
geo.append(Part.LineSegment(FreeCAD.Vector(100,0), FreeCAD.Vector(100,60)))
geo.append(Part.LineSegment(FreeCAD.Vector(100,60), FreeCAD.Vector(0,60)))
geo.append(Part.LineSegment(FreeCAD.Vector(0,60), FreeCAD.Vector(0,0)))
sketch.addGeometry(geo)
con = []
con.append(Sketcher.Constraint('Coincident', 0, 2, 1, 1))
con.append(Sketcher.Constraint('Coincident', 1, 2, 2, 1))
con.append(Sketcher.Constraint('Coincident', 2, 2, 3, 1))
con.append(Sketcher.Constraint('Coincident', 3, 2, 0, 1))
con.append(Sketcher.Constraint('DistanceX', 0, 2, 100.0))
con.append(Sketcher.Constraint('DistanceY', 1, 2, 60.0))
con.append(Sketcher.Constraint('DistanceX', 0, 1, 0.0))
con.append(Sketcher.Constraint('DistanceY', 0, 1, 0.0))
sketch.addConstraint(con)
doc.recompute()
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = sketch
pad.Length = 30
pad.Label = "Pad"
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")
print("Sketched box with pad created!")
```"""
    }
}

# ═══════════════════════════════════════════════════════════════
#  AI PROVIDERS
# ═══════════════════════════════════════════════════════════════
PROVIDERS = {
    "deepseek": {"url": "https://api.deepseek.com/v1/chat/completions", "model": "deepseek-chat", "auth": "Bearer"},
    "openai": {"url": "https://api.openai.com/v1/chat/completions", "model": "gpt-4o-mini", "auth": "Bearer"},
    "ollama": {"url": "http://localhost:11434/api/chat", "model": "llama3", "auth": None},
    "anthropic": {"url": "https://api.anthropic.com/v1/messages", "model": "claude-sonnet-4-20250514", "auth": "x-api-key"},
    "google": {"url": "https://generativelanguage.googleapis.com/v1beta/models/", "model": "gemini-2.5-pro-exp-03-25", "auth": "key"},
    "xai": {"url": "https://api.x.ai/v1/chat/completions", "model": "grok-2", "auth": "Bearer"},
    "mistral": {"url": "https://api.mistral.ai/v1/chat/completions", "model": "mistral-large-2501", "auth": "Bearer"},
    "cohere": {"url": "https://api.cohere.com/v1/chat/completions", "model": "command-r-plus", "auth": "Bearer"},
    "perplexity": {"url": "https://api.perplexity.ai/chat/completions", "model": "sonar-pro", "auth": "Bearer"},
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "model": "llama-3.3-70b-versatile", "auth": "Bearer"},
    "openrouter": {"url": "https://openrouter.ai/api/v1/chat/completions", "model": "openrouter/auto", "auth": "Bearer"},
    "together": {"url": "https://api.together.xyz/v1/chat/completions", "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "auth": "Bearer"},
    "fireworks": {"url": "https://api.fireworks.ai/inference/v1/chat/completions", "model": "accounts/fireworks/models/llama-v3p3-70b-instruct", "auth": "Bearer"},
    "github": {"url": "https://models.inference.ai.azure.com/chat/completions", "model": "gpt-4o", "auth": "Bearer"},
    "backend": {"url": "", "model": "deepseek|deepseek-chat", "auth": "Bearer"},
}

# ── Provider adapters ─────────────────────────────────────

class ProviderAdapterBase:
    """Base class for provider-specific API formatting."""
    def build_request(self, model, messages, api_key=None, api_url=None) -> dict:
        raise NotImplementedError
    def parse_response(self, response_json) -> str:
        raise NotImplementedError

class OpenAICompatibleAdapter(ProviderAdapterBase):
    """For any provider with the /chat/completions schema (OpenAI, DeepSeek, xAI, etc.)."""
    def build_request(self, model, messages, api_key=None, api_url=None):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        data = json.dumps({"model": model, "messages": messages}).encode()
        return {"url": api_url, "data": data, "headers": headers}
    def parse_response(self, response_json):
        return response_json.get("choices", [{}])[0].get("message", {}).get("content", "")

class OllamaAdapter(ProviderAdapterBase):
    def build_request(self, model, messages, api_key=None, api_url=None):
        data = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
        return {"url": api_url, "data": data, "headers": {"Content-Type": "application/json"}}
    def parse_response(self, response_json):
        return response_json.get("message", {}).get("content", "")

class AnthropicAdapter(ProviderAdapterBase):
    """Anthropic Claude API — uses /v1/messages with x-api-key auth."""
    CLAUDE_ROLES = {"user": "user", "assistant": "assistant", "system": "user"}
    def build_request(self, model, messages, api_key=None, api_url=None):
        system = None
        msgs = []
        for m in messages:
            if m.get("role") == "system":
                system = m["content"]
            else:
                r = self.CLAUDE_ROLES.get(m["role"], "user")
                content = m["content"]
                if isinstance(content, list):
                    text = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
                    content = text
                msgs.append({"role": r, "content": content})
        body = {"model": model, "max_tokens": 4096, "messages": msgs}
        if system:
            body["system"] = system
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key or "",
            "anthropic-version": "2023-06-01",
        }
        return {"url": api_url, "data": json.dumps(body).encode(), "headers": headers}
    def parse_response(self, response_json):
        return response_json.get("content", [{}])[0].get("text", "")

class BackendAdapter(ProviderAdapterBase):
    """Proxies to Railway backend instead of calling provider directly.
    The api_url should be the base Railway URL (e.g. http://localhost:8000).
    The adapter appends /generate to reach the generation endpoint."""
    _auth_token: str = ""
    @classmethod
    def set_auth_token(cls, token: str):
        cls._auth_token = token
    def build_request(self, model, messages, api_key=None, api_url=None):
        url = (api_url or "").rstrip("/") + "/generate"
        body = {
            "messages": messages,
            "api_key": api_key or "",
            "provider": model.split("|")[0] if "|" in (model or "") else "deepseek",
            "model": model.split("|")[1] if "|" in (model or "") else model,
            "api_url": None,
        }
        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return {"url": url, "data": json.dumps(body).encode(), "headers": headers}
    def parse_response(self, response_json):
        return response_json.get("content", "")

class GoogleAdapter(ProviderAdapterBase):
    """Google Gemini API — key in URL, different request/response format."""
    def build_request(self, model, messages, api_key=None, api_url=None):
        import re
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            text = m["content"]
            if isinstance(text, list):
                text = " ".join(p.get("text", "") for p in text if isinstance(p, dict))
            # Strip system prefix for Gemini
            if role == "user" and any(m.get("role") == "system" for m in messages):
                pass
            contents.append({"role": role, "parts": [{"text": text}]})
        # Inject system instruction from first system message
        system_instruction = None
        for m in messages:
            if m.get("role") == "system":
                system_instruction = m["content"]
                break
        body = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        url = f"{api_url}{model}:generateContent"
        if api_key:
            url += f"?key={api_key}"
        headers = {"Content-Type": "application/json"}
        return {"url": url, "data": json.dumps(body).encode(), "headers": headers}
    def parse_response(self, response_json):
        try:
            return response_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return ""

PROVIDER_ADAPTERS = {
    "deepseek":   OpenAICompatibleAdapter(),
    "openai":     OpenAICompatibleAdapter(),
    "ollama":     OllamaAdapter(),
    "anthropic":  AnthropicAdapter(),
    "google":     GoogleAdapter(),
    "xai":        OpenAICompatibleAdapter(),
    "mistral":    OpenAICompatibleAdapter(),
    "cohere":     OpenAICompatibleAdapter(),
    "perplexity": OpenAICompatibleAdapter(),
    "groq":       OpenAICompatibleAdapter(),
    "openrouter": OpenAICompatibleAdapter(),
    "together":   OpenAICompatibleAdapter(),
    "fireworks":  OpenAICompatibleAdapter(),
    "github":     OpenAICompatibleAdapter(),
    "backend":    BackendAdapter(),
}

PRESET_MODELS = [
    # ── OpenAI ──
    ("[OpenAI] GPT-4.1", "openai", "gpt-4.1-2025-04-14"),
    ("[OpenAI] GPT-4o", "openai", "gpt-4o-2024-11-20"),
    ("[OpenAI] GPT-4o Mini", "openai", "gpt-4o-mini"),
    ("[OpenAI] o1", "openai", "o1-2024-12-17"),
    ("[OpenAI] o1-mini", "openai", "o1-mini"),
    ("[OpenAI] o3-mini", "openai", "o3-mini-2025-01-31"),
    ("[OpenAI] o4-mini", "openai", "o4-mini"),
    # ── DeepSeek ──
    ("[DeepSeek] Flash (V3)", "deepseek", "deepseek-chat"),
    ("[DeepSeek] Reasoner R1", "deepseek", "deepseek-reasoner"),
    # ── Anthropic ──
    ("[Anthropic] Claude Sonnet 4", "anthropic", "claude-sonnet-4-20250514"),
    ("[Anthropic] Claude Opus 4", "anthropic", "claude-opus-4-20250514"),
    ("[Anthropic] Claude Haiku 3.5", "anthropic", "claude-3-5-haiku-20241022"),
    # ── Google ──
    ("[Google] Gemini 2.5 Pro", "google", "gemini-2.5-pro-exp-03-25"),
    ("[Google] Gemini 2.5 Flash", "google", "gemini-2.5-flash-preview-04-17"),
    # ── xAI ──
    ("[xAI] Grok 3", "xai", "grok-3"),
    ("[xAI] Grok 2", "xai", "grok-2"),
    # ── Mistral ──
    ("[Mistral] Large", "mistral", "mistral-large-2501"),
    ("[Mistral] Codestral", "mistral", "codestral-2501"),
    ("[Mistral] Small", "mistral", "mistral-small-2501"),
    # ── Cohere ──
    ("[Cohere] Command R+", "cohere", "command-r-plus"),
    ("[Cohere] Command R", "cohere", "command-r"),
    # ── Perplexity ──
    ("[Perplexity] Sonar Pro", "perplexity", "sonar-pro"),
    ("[Perplexity] Sonar Deep Research", "perplexity", "sonar-deep-research"),
    # ── Groq ──
    ("[Groq] Llama 3.3 70B", "groq", "llama-3.3-70b-versatile"),
    ("[Groq] DeepSeek R1 Distill", "groq", "deepseek-r1-distill-llama-70b"),
    ("[Groq] Mixtral 8x7B", "groq", "mixtral-8x7b-32768"),
    # ── OpenRouter ──
    ("[OpenRouter] Auto (best model)", "openrouter", "openrouter/auto"),
    ("[OpenRouter] Claude Opus 4", "openrouter", "anthropic/claude-opus-4"),
    ("[OpenRouter] Gemini 2.5 Pro", "openrouter", "google/gemini-2.5-pro-exp-03-25"),
    ("[OpenRouter] GPT-4o", "openrouter", "openai/gpt-4o"),
    # ── Together AI ──
    ("[Together] Llama 3.3 70B", "together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ("[Together] DeepSeek R1", "together", "deepseek-ai/DeepSeek-R1"),
    ("[Together] Qwen 2.5 72B", "together", "Qwen/Qwen2.5-72B-Instruct-Turbo"),
    # ── Fireworks ──
    ("[Fireworks] Llama 3.3 70B", "fireworks", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
    ("[Fireworks] DeepSeek R1", "fireworks", "accounts/fireworks/models/deepseek-r1"),
    # ── GitHub Models ──
    ("[GitHub] GPT-4o", "github", "gpt-4o"),
    ("[GitHub] GPT-4o Mini", "github", "gpt-4o-mini"),
    ("[GitHub] DeepSeek R1", "github", "deepseek-r1"),
    # ── Ollama (local) ──
    ("[Ollama] Llama 3.3 70B (local)", "ollama", "llama3.3-70b"),
    ("[Ollama] Llama 3.1 8B (local)", "ollama", "llama3.1:8b"),
    ("[Ollama] Mistral (local)", "ollama", "mistral"),
    ("[Ollama] DeepSeek R1 (local)", "ollama", "deepseek-r1:7b"),
    ("[Ollama] CodeLlama (local)", "ollama", "codellama"),
    ("[Ollama] Qwen 2.5 (local)", "ollama", "qwen2.5"),
    ("[Ollama] DeepSeek Coder (local)", "ollama", "deepseek-coder"),
    # ── Backend (Railway proxy) ──
    ("[Backend] DeepSeek Flash", "backend", "deepseek|deepseek-chat"),
    ("[Backend] GPT-4o Mini", "backend", "openai|gpt-4o-mini"),
    ("[Backend] Claude Sonnet 4", "backend", "anthropic|claude-sonnet-4-20250514"),
    ("[Backend] Gemini 2.5 Flash", "backend", "google|gemini-2.5-flash-preview-04-17"),
    # ── Templates ──
    ("Templates (no AI)", "templates", ""),
]

MODES = {
    "build": "Build — full autonomy: plan, code, execute, observe",
    "plan": "Plan — outputs a plan only, user confirms before execution",
    "ask": "Ask — Q&A about FreeCAD, no code execution",
    "pcb": "PCB — design enclosures from .kicad_pcb files",
}

MAX_RETRIES = 5



# ═══════════════════════════════════════════════════════════════
#  SECURITY: restricted builtins for exec()
# ═══════════════════════════════════════════════════════════════
BLOCKED_IMPORTS = {"os","sys","subprocess","shutil","ctypes","socket",
                   "http","urllib","requests","pathlib","tempfile",
                   "pickle","shelve","sqlite3","multiprocessing",
                   "threading","webbrowser","tkinter","PySide6","PySide2",
                   "PyQt5","PyQt6"}

def _safe_import(name, *args, **kwargs):
    if not isinstance(name, str):
        raise ImportError("Invalid import name")
    base = name.split(".")[0]
    if base in BLOCKED_IMPORTS:
        raise ImportError(f"Module '{name}' is blocked for security")
    try:
        return __import__(name, *args, **kwargs)
    except ImportError:
        raise ImportError(f"Module '{name}' not available in FreeCAD")

SAFE_BUILTINS = {
    "__import__": _safe_import,
    "True": True, "False": False, "None": None,
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "len": len, "range": range, "print": print,
    "enumerate": enumerate, "zip": zip, "map": map, "filter": filter,
    "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "sorted": sorted, "reversed": reversed, "any": any, "all": all,
    "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
    "setattr": setattr, "type": type, "super": super,
    "iter": iter, "next": next, "slice": slice,
    "open": open,
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "AttributeError": AttributeError,
    "KeyError": KeyError, "IndexError": IndexError,
    "StopIteration": StopIteration, "NotImplementedError": NotImplementedError,
}

# ═══════════════════════════════════════════════════════════════
#  PLAN EXECUTOR (testable, no Qt/FreeCAD dependencies)
# ═══════════════════════════════════════════════════════════════

class StepResult:
    """Result of executing one plan step."""
    def __init__(self):
        self.success = False
        self.message = ""
        self.observation = ""
        self.plan_complete = False
        self.plan_revised = False
        self.blocks = []
        self.raw_text = ""

class PlanExecutor:
    """Orchestrates multi-step plan execution with injectable callables.

    Extracted from AISidebar._on_code_ready for headless testing.
    All FreeCAD and Qt dependencies are injected via the callable constructor params.

    Parameters:
      generate_fn(prompt) -> (raw_text, code_str, used_api)
      execute_fn(code) -> (success, message)
      observe_fn() -> str
      diff_fn() -> ((added, removed, modified), full_or_None)
      extract_blocks_fn(code) -> list[str]
      build_messages_fn(input, mode, retry_context) -> list[msgs]
    """

    def __init__(self, generate_fn, execute_fn, observe_fn, diff_fn,
                 extract_blocks_fn, build_messages_fn):
        self.generate = generate_fn
        self.execute = execute_fn
        self.observe = observe_fn
        self.diff = diff_fn
        self.extract_blocks = extract_blocks_fn
        self.build_messages = build_messages_fn
        self.retries = 0

    def execute_step(self, prompt, plan_steps, step_idx, input_text, max_retries=5):
        """Execute a single plan step. Returns StepResult."""
        result = StepResult()

        raw_text, code, used_api = self.generate(prompt)
        result.raw_text = raw_text or ""

        blocks = self.extract_blocks(code or "")
        if not blocks:
            result.message = "AI returned no code in the response."
            return result

        # Try each block with retries
        for block in blocks:
            success, message = self.execute(block)
            if not success and self.retries < max_retries:
                self.retries += 1
                fresh_obs = self.observe()
                ctx = self.build_messages(input_text, mode="build",
                    retry_context=f"Previous code failed: {message}. "
                                  f"Current scene: {fresh_obs}")
                raw_text2, code2, _ = self.generate(ctx)
                blocks2 = self.extract_blocks(code2 or "")
                if blocks2:
                    block = blocks2[0]
                    success, message = self.execute(block)

            result.success = success
            result.message = message
            result.blocks = blocks
            if not success:
                return result

        result.success = True
        result.message = message

        # Advance plan
        step_idx += 1
        if plan_steps and step_idx >= len(plan_steps):
            result.plan_complete = True

        return result


# ═══════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════
class AIOrchestrator(QtCore.QObject):
    def __init__(self, api_key, provider="deepseek", model=None, api_url=None):
        super().__init__()
        self.api_key = api_key
        self.provider = provider
        self.custom_model = model
        self.custom_url = api_url
        self.conversation_history = []
        self._transaction_active = False
        self.macro_dir = self._get_macro_dir()
        self._prev_objects = []
        self._touched_objects = set()
        self.allow_expensive_fallback = True
        self._board_context = None
        try:
            doc = FreeCAD.ActiveDocument
            self.assembly = AssemblyGraph(doc) if doc else None
        except Exception:
            self.assembly = None
        self._backend_auth_token = os.environ.get("BACKEND_AUTH_TOKEN", "")
        if self.provider == "backend" and self._backend_auth_token:
            BackendAdapter.set_auth_token(self._backend_auth_token)
        # Don't load old conversation on init — each session starts fresh
        
    def _get_macro_dir(self):
        try: return FreeCAD.getUserMacroDir(True)
        except Exception: return os.path.expanduser("~")
    
    def get_provider_config(self):
        cfg = PROVIDERS.get(self.provider, PROVIDERS["deepseek"])
        return (self.custom_url or cfg["url"], self.custom_model or cfg["model"], cfg.get("auth"))
    
    def set_board_context(self, filepath):
        import pcb_parser
        self._board_context = pcb_parser.parse(filepath)

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
        lines.append("- EnclosureBuilder.create_base_shell(wall_t=2.5, floor_t=2.0)")
        lines.append("- EnclosureBuilder.add_mounting_bosses(boss_od=6.0)")
        lines.append("- EnclosureBuilder.add_connector_cutouts(clearance=0.5)")
        lines.append("- EnclosureBuilder.create_lid(component_clearance=3.0)")
        lines.append("- EnclosureBuilder.add_snap_fits(count=4)")
        lines.append("- EnclosureBuilder.add_ventilation(near_components=[...])")
        return "\n".join(lines)

    # ── Context Builders ─────────────────────────────────────
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
            except Exception:
                pass
            try:
                st = s.ShapeType
                if st:
                    parts.append(f"type={st}")
            except Exception:
                pass
            return "[" + " ".join(parts) + "]" if parts else ""
        except Exception:
            return ""

    def _placement_rot(self, obj):
        """Human-readable rotation from Placement."""
        try:
            if not hasattr(obj, 'Placement'):
                return ""
            r = obj.Placement.Rotation
            # Try Euler angles (degrees)
            euler = r.toEuler()
            if euler:
                return f" rot({euler[0]:.0f}°,{euler[1]:.0f}°,{euler[2]:.0f}°)"
            return ""
        except Exception:
            return ""

    def _deps(self, obj):
        """List what this object uses (InList) and what uses it (OutList)."""
        try:
            uses = [dep.Label for dep in obj.InList if dep != obj][:4] if hasattr(obj, 'InList') else []
            used_by = [dep.Label for dep in obj.OutList if dep != obj][:4] if hasattr(obj, 'OutList') else []
            dep_parts = []
            if uses:
                dep_parts.append(f"uses:{','.join(uses)}")
            if used_by:
                dep_parts.append(f"usedBy:{','.join(used_by)}")
            return " | ".join(dep_parts) if dep_parts else ""
        except Exception:
            return ""

    def _body_hierarchy(self, obj, _depth=0):
        """Return the Body/Part ancestor chain if this is a PartDesign feature."""
        if _depth > 10:
            return ""
        try:
            parts = []
            p = obj
            while _depth < 10 and hasattr(p, 'InList') and p.InList:
                parent = p.InList[0]
                if 'PartDesign::Body' in parent.TypeId or 'App::Part' in parent.TypeId:
                    parts.append(parent.Label)
                    p = parent
                    _depth += 1
                else:
                    break
            return " / ".join(reversed(parts)) if parts else ""
        except Exception:
            return ""

    def _sketch_profile(self, obj):
        """If the object is a sketch, describe its geometry and constraints."""
        try:
            if 'Sketcher' not in obj.TypeId:
                return ""
            geo_count = len(obj.Geometry) if hasattr(obj, 'Geometry') else 0
            con_count = len(obj.Constraints) if hasattr(obj, 'Constraints') else 0
            geo_types = {}
            if hasattr(obj, 'Geometry'):
                for g in obj.Geometry:
                    name = type(g).__name__.replace('Geom', '').replace('Sketch', '')
                    geo_types[name] = geo_types.get(name, 0) + 1
            geo_desc = ",".join(f"{k}x{v}" for k, v in sorted(geo_types.items())) if geo_types else ""
            con_desc = ""
            if hasattr(obj, 'Constraints') and obj.Constraints:
                con_counts = {}
                for c in obj.Constraints:
                    con_counts[c.Type] = con_counts.get(c.Type, 0) + 1
                con_desc = " " + " ".join(f"{t}x{c}" for t, c in sorted(con_counts.items()))
            return f" [sketch: {geo_count}geo {con_count}con ({geo_desc}){con_desc}]"
        except Exception:
            return ""

    def _object_line(self, obj, indent="  "):
        t = obj.TypeId.split("::")[-1]
        props = []
        for a in ['Length','Width','Height','Radius','Radius1','Radius2','Angle']:
            if hasattr(obj, a):
                v = getattr(obj, a)
                props.append(f"{a}={v:.1f}" if isinstance(v, float) else f"{a}={v}")
        pos = ""
        if hasattr(obj, 'Placement'):
            b = obj.Placement.Base
            pos = f" @({b.x:.0f},{b.y:.0f},{b.z:.0f})"
        rot = self._placement_rot(obj)
        color = ""
        if hasattr(obj, 'ViewObject') and hasattr(obj.ViewObject, 'ShapeColor'):
            c = obj.ViewObject.ShapeColor
            color = f" c=({c[0]:.2f},{c[1]:.2f},{c[2]:.2f})"
        shape_info = self._shape_summary(obj)
        deps = self._deps(obj)
        hierarchy = self._body_hierarchy(obj)
        sketch = self._sketch_profile(obj)

        line = f"{indent}[{obj.Label}]({obj.Name}) {t}"
        if hierarchy:
            line += f" in:{hierarchy}"
        line += pos + rot
        if props:
            line += f" [{', '.join(props[:6])}]"
        if shape_info:
            line += f" {shape_info}"
        if sketch:
            line += sketch
        if deps:
            line += f" {{{deps}}}"
        if color:
            line += color
        return line

    def get_selection_context(self):
        try:
            sel = FreeCADGui.Selection.getSelection()
            if not sel:
                return ""
            lines = ["### SELECTED OBJECTS (being manipulated):"]
            for obj in sel:
                lines.append(self._object_line(obj, "  - "))
            return "\n".join(lines) + "\n"
        except Exception:
            return ""

    def get_workbench_context(self):
        """Return currently active workbench name."""
        try:
            wb = FreeCADGui.activeWorkbench()
            if wb:
                name = wb.menuText() if hasattr(wb, 'menuText') else wb.__class__.__name__
                return f"Active workbench: **{name}**"
            return "Active workbench: None"
        except Exception:
            return ""

    def get_document_context(self):
        """Full document tree with hierarchy — shows parent/child nesting."""
        docs = FreeCAD.listDocuments()
        if not docs:
            return "### No documents open."
        lines = [self.get_workbench_context()]
        for dname, doc in docs.items():
            is_active = " (ACTIVE)" if doc == FreeCAD.ActiveDocument else ""
            lines.append(f"### [{dname}]{is_active} — {len(doc.Objects)} objects")
            # Build a simple tree: map parent-groups to their children
            root_objs = []
            child_map = {}
            for obj in doc.Objects:
                parents = [p for p in obj.InList if p in doc.Objects]
                if not parents:
                    root_objs.append(obj)
                else:
                    parent = parents[0]
                    child_map.setdefault(parent.Name, []).append(obj)

            def emit_tree(obj_list, depth=0):
                for obj in obj_list:
                    lines.append(self._object_line(obj, "  " * (depth + 1)))
                    for child in child_map.get(obj.Name, []):
                        emit_tree([child], depth + 1)

            emit_tree(root_objs)
        return "\n".join(lines)
    
    def list_documents_text(self):
        docs = FreeCAD.listDocuments()
        if not docs: return "No documents open."
        lines = ["Open documents:"]
        for name, doc in docs.items():
            a = " [ACTIVE]" if doc == FreeCAD.ActiveDocument else ""
            lines.append(f"  {name}{a} — {len(doc.Objects)} objects")
        return "\n".join(lines)
    
    def build_system_prompt(self, mode="build"):
        rules = """### STRICT RULES:
1. Always get doc: FreeCAD.ActiveDocument; if not doc: doc = FreeCAD.newDocument("Design")
2. End each block with: doc.recompute(); FreeCAD.Gui.SendMsgToActiveView("ViewFit")
3. Do NOT use eval(), exec(), os.system, os.popen in generated code.
    You can `import` any FreeCAD workbench module (SheetMetal, Fasteners, Draft, etc.) — they are available.
4. Use reasonable dimensions (20-500mm). Default: 100x60x40 for box, R50 H100 for cylinder.
5. **LOOKING UP EXISTING OBJECTS**: Use `find("NameOrLabel")` — it tries exact name, exact label, then case-insensitive match. Never hardcode `doc.getObject("Name")` — FreeCAD may auto-rename (e.g. `Cylinder_200x500mm` vs `Cylinder`). If `find()` returns None, iterate `doc.Objects` to find by TypeId.
6. Give each new object a clear Label.
7. Place objects 300mm apart on X axis to avoid overlap.
8. Color each new object distinctively using obj.ViewObject.ShapeColor = (R,G,B)
9. PartDesign features MUST be inside a PartDesign::Body. Create body first.
10. PartDesign sketches MUST be created via body.newObject("Sketcher::SketchObject","Name")
11. **WORKBENCHES** — Switch workbenches freely. Check what's available with `_wb` (dict of {{name: workbench}}).
    - `FreeCADGui.activateWorkbench("SketcherWorkbench")` before creating/editing sketches
    - `FreeCADGui.activateWorkbench("PartDesignWorkbench")` before pads/pockets/revolutions
    - `FreeCADGui.activateWorkbench("PartWorkbench")` before booleans/primitives
    - `FreeCADGui.activateWorkbench("DraftWorkbench")` before 2D arrays/text/drafting
12. **DESIGN WORKFLOW** — For parametric models: Sketch → Pad → features → booleans.
    Prefer PartDesign workflow over raw Part primitives for anything that needs sketches.
13. **SIMPLE PRIMITIVES FIRST** — For simple requests like "make a box", "create a cylinder", "add a sphere",
    use direct Part primitives (`Part::Box`, `Part::Cylinder`, `Part::Sphere`) in ONE complete code block.
    Do not start with a sketch unless the user explicitly asks for a sketch, constraints, or PartDesign feature history.
13. **MODIFYING EXISTING BODIES** — If a PartDesign::Body already exists, add new features to it
    via `body.newObject(...)` and set their properties. Do NOT create a new Body or try to
    fuse a Part::Box with a Body's shape — instead add an AdditiveBox/Pad as a Body feature.
    Example: box = body.newObject("PartDesign::AdditiveBox","MyBox"); box.Length = 50
14. Only use Part::Cut/Part::MultiFuse when working with raw Part primitives outside a Body.
Inside a PartDesign Body, use Additive*/Subtractive* features or Pad/Pocket.
15. Keep execution safe: avoid giant loops/arrays and massive object creation in one run.
Prefer incremental operations over one huge script for complex models.
16. Never use unbounded loops (e.g., `while True`) for geometry generation.
If the task is large, split it into smaller batches and recompute between batches.
17. **SKETCH JSON FORMAT** — For sketch geometry, use ```json blocks to avoid vertex index errors.
Supported primitives: rectangle(x,y,w,h), circle(cx,cy,r), line(x1,y1,x2,y2), polygon(points=[[x1,y1],...]).
Example for a 100x50mm rectangle at origin:
```json
{"sketch": {"body": "Body", "name": "RectSketch", "primitives": [
  {"type": "rectangle", "x": 0, "y": 0, "w": 100, "h": 50}
]}}
```
The compiler auto-closes rectangles and chains. After the JSON block, use ```python to operate on the sketch (e.g. pad it).
18. **GEOMETRY CRASH WARNINGS** — These operations can crash FreeCAD (segfault) with invalid parameters:
    - `Part::Loft`: profiles MUST have the SAME number of edges and same winding direction. Use simple profiles (rectangle, circle) not complex splines with different resolutions.
    - `Part::Sweep`: spine MUST be smooth and longer than profile; avoid sharp corners on spine.
    - `Part::Thickness` / `Part::Offset`: extremely crash-prone on complex shapes. Test on simple geometry first.
    - `Part.BSplineCurve().interpolate()`: coordinate list must be closed (first == last) and have at least 4 points. Avoid duplicate points.
    - `Part::Section`: both inputs must be solid shapes, not faces or wires.
    PREFER safer alternatives: use PartDesign AdditivePipe (Sweep) over Part::Sweep; use simple Pad/Pocket over Thickness. If you must use these operations, validate parameters carefully and warn the user.
19. **DEPENDENCY CHAIN CONSISTENCY** — Many models are built as a feature chain
    (e.g. BaseBox → Cavity → Standoff_1..4 → ScrewHole_1..4). When you modify
    a dimension (Height/Length/Width/Depth) of one feature, identify ALL features
    in that dependency chain and apply the SAME delta to each so internal geometry
    stays consistent. Example: if BaseBox.Height increases by 500mm, the Cavity
    depth must also increase by 500mm, all Standoff_N heights by 500mm, and all
    ScrewHole_N depths by 500mm. Always add print() verification showing final
    dimensions of every feature in the chain so the user can confirm consistency.
20. **RELATIVE VS ABSOLUTE INTENT** — Distinguish between relative and absolute changes:
    - "increase by X", "decrease by X", "add X", "make taller by X" = RELATIVE change.
      Get the current value of EVERY feature in the chain, then add/subtract X.
    - "set to X", "make it X", "change to X", "exactly X" = ABSOLUTE change.
      Assign X to EVERY feature in the chain that matches the property.
    When unsure, assume RELATIVE and explicitly check what the user meant.
21. **DEPENDENCY GRAPH** — Before modifying any property, scan the document for objects
    that depend on your target (check `obj.InList` and `obj.OutList` to find the chain).
    The DEPENDENCY CHAIN section in your prompt lists the objects you must keep consistent.
    Update ALL of them, not just the one the user mentioned by name.
22. **Z=0 ARCHITECTURE FOR ENCLOSURES** — Build all enclosure geometry at Z=0 local space:
    - Outer shell and inner cavity both start at Z=0.
    - Apply all cuts (bosses, vents, USB slots, holes) at Z=0 coordinates.
    - Place/final-position objects only AFTER all boolean operations are done.
    This eliminates every Z-offset arithmetic bug (cavity floating, cut missing, etc.).
    The EnclosureBuilder methods follow this pattern automatically.
23. **USE HELPER FUNCTIONS** — For compact geometry code, define and use the helpers
    from the FREECAD API REFERENCE section (v, box, cyl, tube, fuse, sub). For
    rounded-corner boxes use `EnclosureBuilder.rrect()`; for rotated boxes use
    `EnclosureBuilder.rotbox()`. These produce cleaner, less error-prone code than
    raw Part.makeBox / Part.makeCylinder calls."""
        mode_rules = {
            "plan": """### CURRENT MODE: PLAN
Your job is to create a detailed numbered plan for the user's request.
Do NOT output any code. Output a clear step-by-step plan only.
The user must explicitly say "execute" or "go ahead" before any code is generated.""",
            "ask": """### CURRENT MODE: ASK
You are a FreeCAD assistant answering questions. Use the scene context to give specific answers.
Do NOT generate or execute FreeCAD code. Answer concisely using your knowledge of FreeCAD.
If the user asks for measurements or properties of existing objects, say so — do not attempt to compute them.""",
        }

        extra = mode_rules.get(mode, "")
        return f"{FREECAD_KNOWLEDGE}\n\n{rules}\n\n{extra}" if extra else f"{FREECAD_KNOWLEDGE}\n\n{rules}"

    def build_user_prompt(self, user_input):
        context = self.get_document_context()
        selection = self.get_selection_context()
        docs_list = self.list_documents_text()
        history = ""
        if self.conversation_history:
            history = "\n### Previous actions in this session:\n"
            for i, t in enumerate(self.conversation_history[-8:], 1):
                status = "✅" if t.get("success") else "❌"
                obs_data = t.get("observation_data", [])
                if isinstance(obs_data, list) and obs_data:
                    if isinstance(obs_data[0], str):
                        obs = " | ".join(obs_data)
                    else:
                        obs = self.format_observation(obs_data, max_chars=250)
                else:
                    obs = ""
                code_snip = t.get("code", "")[:120].replace("\n", " ")
                history += f"  {i}. {status} User: '{t['user']}'\n     Code: {code_snip}\n     Result: {t['result'][:200]}\n"
                if obs:
                    history += f"     Scene: {obs[:250]}\n"
        
        return f"""### CURRENT SCENE STATE
{docs_list}
{context}
{selection}
Available workbenches: {", ".join(sorted(FreeCADGui.listWorkbenches().keys())) if hasattr(FreeCADGui, 'listWorkbenches') else "N/A"}
{history}

### USER REQUEST: {user_input}

    ### EXECUTION REQUIREMENT:
    - Output COMPLETE executable code for the full request in one response.
    - Use one or more complete ```python blocks that can run immediately.
    - Do not output step-1-only partial code.
    - For simple shape requests (box/cylinder/sphere), create the final shape directly (no sketch-first workflow).

    ### OUTPUT FORMAT:
    Brief analysis (1-2 lines max), then complete ```python code block(s)."""

    def build_dependency_chain_context(self):
        """Build a DEPENDENCY CHAIN section for the AI prompt.
        
        Scans the active document for objects that form feature chains
        (via InList/OutList/Body.Group) and lists them so the AI knows
        exactly which objects must be updated together.
        """
        try:
            doc = FreeCAD.ActiveDocument
            if not doc or not doc.Objects:
                return ""
            obs = self.capture_observation_structured()
            lines = ["### DEPENDENCY CHAIN — update ALL objects in a chain together:"]
            found_any = False
            for e in obs:
                deps = e.get("deps", {})
                name = e.get("label") or e.get("name", "?")
                typ = e.get("type", "")
                # Check if this object has meaningful dependencies
                has_deps = bool(deps.get("parents") or deps.get("children")
                                or deps.get("features") or deps.get("attached_to"))
                if not has_deps:
                    continue
                found_any = True
                dims = []
                obj = doc.getObject(e.get("name", ""))
                if obj:
                    for p in self.DIMENSION_PROPS:
                        v = self._get_dimension_value(obj, p)
                        if v is not None:
                            dims.append(f"{p}={v:.0f}")
                chain_parts = []
                if deps.get("parents"):
                    chain_parts.append(f"depends_on=[{','.join(deps['parents'][:3])}]")
                if deps.get("children"):
                    chain_parts.append(f"used_by=[{','.join(deps['children'][:3])}]")
                if deps.get("features"):
                    chain_parts.append(f"features=[{' → '.join(deps['features'][:5])}]")
                if deps.get("attached_to"):
                    chain_parts.append(f"attached_to={deps['attached_to']}")
                suffix = f" ({', '.join(chain_parts)})" if chain_parts else ""
                dim_str = f" [{', '.join(dims)}]" if dims else ""
                lines.append(f"  - {name}{dim_str}{suffix}")
            if not found_any:
                return ""
            # Also add a flat list of all objects with Height/Length for quick reference
            lines.append("\nAll objects with dimensional properties:")
            for e in obs:
                name = e.get("label") or e.get("name", "?")
                obj = doc.getObject(e.get("name", ""))
                if obj:
                    dims = []
                    for p in self.DIMENSION_PROPS:
                        v = self._get_dimension_value(obj, p)
                        if v is not None:
                            dims.append(f"{p}={v:.0f}")
                    if dims:
                        lines.append(f"  {name}: {', '.join(dims)}")
            # Append assembly constraints
            try:
                self.assembly = AssemblyGraph(doc) if doc else None
                if self.assembly:
                    desc = self.assembly.describe()
                    if desc:
                        lines.append("")
                        lines.append(desc)
            except Exception:
                pass
            return "\n".join(lines)
        except Exception:
            return ""

    # ── Transaction Management ───────────────────────────────
    def _begin_transaction(self, label="AI Operation"):
        try:
            doc = FreeCAD.ActiveDocument
            if doc:
                doc.openTransaction(label)
                self._transaction_active = True
                self._transaction_doc = doc
                return True
        except Exception:
            pass
        self._transaction_doc = None
        return False

    def _commit_transaction(self):
        try:
            doc = self._transaction_doc
            if doc and self._transaction_active:
                doc.commitTransaction()
                self._transaction_active = False
                self._transaction_doc = None
                return True
        except Exception:
            pass
        return False

    def _abort_transaction(self):
        try:
            doc = self._transaction_doc
            if doc and self._transaction_active:
                doc.abortTransaction()
                self._transaction_active = False
                self._transaction_doc = None
                return True
        except Exception:
            pass
        return False
    
    def extract_code_blocks(self, text):
        blocks = re.findall(r"```(?:python|py)?\n(.*?)```", text, re.DOTALL)
        if not blocks:
            return []
        return [b.strip() for b in blocks]

    def extract_json_blocks(self, text):
        blocks = re.findall(r"```json\n(.*?)```", text, re.DOTALL)
        return [b.strip() for b in blocks if b.strip()]

    def call_ai(self, messages):
        """Thread-safe: calls the AI API with the given message list.
        Falls back to secondary provider on failure.
        Iterates through providers in priority order."""
        # Build provider priority list
        provider_list = [self.provider]
        fb = self._fallback_provider()
        if fb and fb != self.provider:
            provider_list.append(fb)

        for attempt_provider in provider_list:
            if attempt_provider != self.provider and not self.allow_expensive_fallback:
                print(f"[AI] Primary provider ({self.provider}) failed. Fallback disabled by allow_expensive_fallback=False.")
                return None

            adapter = PROVIDER_ADAPTERS.get(attempt_provider)
            if not adapter:
                print(f"[AI] Unknown provider: {attempt_provider}")
                continue

            cfg = PROVIDERS.get(attempt_provider, PROVIDERS["deepseek"])
            url = self.custom_url or cfg["url"]
            model = self.custom_model or cfg["model"]

            try:
                if attempt_provider != self.provider:
                    print(f"[AI] Primary provider ({self.provider}) unavailable. Falling back to {attempt_provider}.")
                req_spec = adapter.build_request(model, messages, api_key=self.api_key, api_url=url)
                with urllib.request.urlopen(urllib.request.Request(
                    req_spec["url"], data=req_spec["data"], headers=req_spec["headers"]
                ), timeout=120) as resp:
                    result = json.loads(resp.read().decode())
                return adapter.parse_response(result)
            except Exception as e:
                print(f"[AI] API call failed ({attempt_provider}): {e}")
                continue
        return None

    def _fallback_provider(self):
        """Return a fallback provider when the primary fails."""
        if self.provider == "deepseek":
            return "openai"
        return "deepseek"

    def generate_code(self, api_msgs):
        response = self.call_ai(api_msgs)
        if response:
            sketch_code = ""
            json_blocks = self.extract_json_blocks(response)
            if json_blocks:
                from sketch_compiler import SketchCompiler
                sketch_code = SketchCompiler().compile_all(response)

            py_blocks = self.extract_code_blocks(response)
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
            return response, None, False
        return "", None, False

    def generate_code_safe(self, api_msgs, user_input):
        """Like generate_code but falls back to safe template if AI code contains crash-prone patterns."""
        response, code, used_api = self.generate_code(api_msgs)
        if code and used_api:
            CRASH_STRINGS = [
                "Part::Loft", "Part::Sweep", "Part::Thickness",
                "Part::Offset", "Part::Section", "Part.BSplineCurve",
                "Part.BSplineSurface",
            ]
            if any(s in code for s in CRASH_STRINGS):
                fallback = self.get_fallback_code(user_input)
                if fallback:
                    return response, fallback, False
        return response, code, used_api

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
            if len(self.conversation_history) > 50:
                temp = [e for e in self.conversation_history if e.get("permanent")]
                nonperm = [e for e in self.conversation_history if not e.get("permanent")]
                keep = 50 - len(temp)
                self.conversation_history = temp + nonperm[-keep:]

        except Exception:
            pass

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
        except Exception:
            pass

    def load_session(self):
        """Load conversation history from disk."""
        try:
            path = os.path.join(self.macro_dir, "ai_history.json")
            if os.path.exists(path):
                with open(path) as f:
                    self.conversation_history = json.load(f)
        except Exception:
            pass

    def should_replan(self, remaining_steps, observation):
        """Check if the remaining plan steps need revision after seeing the actual result.
        Returns (bool, str): (True, revised_plan_or_reason) or (False, "")."""
        if not remaining_steps:
            return False, ""
        steps_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(remaining_steps))
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
                new_plan = self.extract_plan(resp)
                if new_plan:
                    return True, "\n".join(f"{i+1}. {s}" for i, s in enumerate(new_plan))
                return True, resp
            return False, ""
        except Exception:
            return False, ""

    def extract_plan(self, text):
        """Extract numbered plan steps from AI response. Returns list of step descriptions or None."""
        import re
        steps = []
        patterns = [
            r"^\s*(?:\d+)[.)]\s+(.+)",           # 1. do X  or  1) do X
            r"^\s*\*\*(?:\d+)\*\*[.)]\s+(.+)",   # **1.** do X  or  **1)** do X
            r"^\s*Step\s+(?:\d+)[:.)]\s+(.+)",    # Step 1: do X  or Step 1. do X
            r"^\s*-\s+(?:Step\s+)?(?:\d+)[:.)]\s+(.+)",  # - Step 1: do X
        ]
        for line in text.split("\n"):
            for pat in patterns:
                m = re.match(pat, line, re.IGNORECASE)
                if m:
                    step_text = m.group(1).strip().rstrip(".:")
                    if step_text and len(step_text) > 3:
                        steps.append(step_text)
                    break
        return steps if len(steps) >= 2 else None

    def build_step_prompt(self, user_input, plan_steps, step_idx,
                          fresh_observation, fresh_context="",
                          prior_observation="", diff_summary=""):
        """Build messages asking the AI to generate code for one specific plan step.
        
        Args:
            fresh_observation: live document state captured at request time
            fresh_context: live get_document_context() captured at request time
            prior_observation: the observation from right after the prior step ran
            diff_summary: short diff string showing what changed since last step
        """
        plan_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan_steps))
        current_step = plan_steps[step_idx]
        done_steps = plan_steps[:step_idx]
        remaining = plan_steps[step_idx+1:]
        remaining_title = f"({len(remaining)} more steps)" if remaining else ""
        
        MAX_PROMPT_CHARS = 12000  # ~3000 tokens
        
        # Core structure — never dropped
        prompt = (
            f"### TASK: {user_input[:200]}\n\n"
            f"### PLAN:\n{plan_text}\n\n"
            f"### STEP {step_idx+1}: {current_step}\n"
        )
        if remaining:
            prompt += f"### REMAINING: {remaining_title}\n"
        if diff_summary:
            prompt += f"\n### CHANGES SINCE LAST STEP:\n{diff_summary}\n"
        prompt += f"\n### CURRENT SCENE (authoritative — this is what the document looks like right now):\n"
        
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
        )
        # Inject dependency chain so AI knows which objects must be updated together
        dep_chain = self.build_dependency_chain_context()
        if dep_chain:
            prompt += f"\n{dep_chain}\n"
        
        msgs = [
            {"role": "system", "content": self.build_system_prompt("build")},
            {"role": "user", "content": prompt}
        ]
        if hist_entry:
            if len(prompt) + len(hist_entry) < MAX_PROMPT_CHARS + 500:
                msgs.append({"role": "user", "content": hist_entry})
        return msgs

    def capture_viewport(self):
        try:
            import base64
            import tempfile
            ad = FreeCADGui.activeDocument()
            if not ad:
                return None
            view = ad.activeView()
            path = os.path.join(tempfile.gettempdir(), "ai_viewport.png")
            view.saveImage(path, 800, 600, "PNG")
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception:
            pass
        return None

    # ── Building messages ──────────────────────────────────────
    def build_messages(self, user_input, retry_context=None, mode="build"):
        """NOT thread-safe: captures current FreeCAD state. Must be called from main thread."""
        instruction = self.build_system_prompt(mode)
        role_label = {
            "build": "You are an autonomous FreeCAD design agent. Keep analysis brief (1-2 sentences max), then output COMPLETE code in ```python blocks. Code that is cut off or truncated will NOT execute — always close your ``` fence.",
            "plan": "You are a FreeCAD planning agent. Briefly analyze, then output a concise numbered plan. Do NOT output code.",
            "ask": "You are a FreeCAD assistant. Answer the user's question concisely in 1-2 paragraphs. Do NOT output code.",
            "pcb": "You are a PCB enclosure design agent. Read the BOARD DATA section below and use it to call the EnclosureBuilder methods. Output COMPLETE code in ```python blocks.",
        }
        if mode == "pcb" and self._board_context:
            board_section = f"\n\n### BOARD DATA (authoritative — use these exact values)\n{self._format_board_data()}"
            instruction += board_section
        context_msg = {"role":"system","content":f"{role_label.get(mode, role_label['build'])}\n\n{instruction}"}
        user_prompt = self.build_user_prompt(user_input)
        if mode in ("build", "plan"):
            dep_chain = self.build_dependency_chain_context()
            if dep_chain:
                user_prompt += f"\n\n{dep_chain}"
        user_msg = {"role":"user","content":user_prompt}
        api_msgs = [context_msg, user_msg]
        if self.provider in ("openai",) and FreeCADGui.activeDocument():
            b64 = self.capture_viewport()
            if b64:
                user_msg["content"] = [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
        if retry_context:
            err_msg = {"role":"user","content":f"Previous code failed. Analyze why, choose a different approach, output corrected code.\nWhat went wrong:\n{retry_context}\nSame task: {user_input}"}
            api_msgs.append(err_msg)
        return api_msgs

    def validate_code(self, code):
        try:
            ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        if len(code) > 120000:
            return False, "Generated code is too large for safe execution. Please ask for a smaller step-by-step operation."
        forbid = ["eval(", "exec(", "os.system", "os.popen"]
        for w in forbid:
            if w in code:
                return False, f"Blocked pattern '{w}'"
        return True, "OK"

    def validate_runtime_risk(self, code):
        """Heuristic runtime guard to reduce native FreeCAD crashes on huge operations."""
        try:
            tree = ast.parse(code)
        except Exception:
            return True, ""

        MAX_RANGE = 400
        MAX_OBJECT_CREATIONS = 250
        MAX_LOOP_DEPTH = 2

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
            tree = ast.parse(code)
        except Exception:
            return True, ""

        CRASH_STRINGS = [
            "Part::Thickness", "Part::Offset",
            "Part.BSplineCurve", "Part.BSplineSurface",
            ".makeBSpline",
        ]
        found = []
        for s in CRASH_STRINGS:
            if s in code:
                found.append(s)

        if found:
            return False, (
                "Safety guard blocked execution because these crash-prone operations "
                f"were detected: {', '.join(found)}. "
                "These operations (Thickness, Offset, BSplineCurve) can segfault "
                "FreeCAD with invalid parameters. Ask the user to explicitly confirm with "
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
            except Exception:
                pass
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
                    except Exception:
                        pass

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
                        except Exception:
                            pass
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
        except Exception:
            pass
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
                self.assembly = AssemblyGraph(doc) if doc else None
            except Exception:
                self.assembly = None
            assembly_issues = self.assembly.verify() if self.assembly else []

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
        except Exception:
            pass
        # Check Pad/Pocket Length
        try:
            if hasattr(obj, 'Length') and prop in ("Height", "Depth"):
                return float(obj.Length)
        except Exception:
            pass
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
                    f"the conversion (e.g. 50cm → 50mm, not 500mm)."
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
                except Exception:
                    pass

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
                        except Exception:
                            pass
                if props:
                    snap[key] = props
            # Include assembly constraint snapshot
            try:
                if doc:
                    asm = AssemblyGraph(doc)
                    asm_snap = asm.snapshot()
                    if asm_snap:
                        snap["__assembly__"] = asm_snap
            except Exception:
                pass
            return snap
        except Exception:
            return {}

    def execute_code(self, code, user_input=""):
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
        self._touched_objects = set()
        self._pre_execution_snapshot = self._capture_dimension_snapshot()

        old_doc_names = set(FreeCAD.listDocuments().keys())
        old_doc_name = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
        old_counts = self._count_objects()
        available = {}
        for mod_name in ["Part", "Sketcher", "Mesh", "Draft", "Import", "Export",
                         "SheetMetal", "Fasteners", "Assembly"]:
            try:
                available[mod_name] = __import__(mod_name)
            except Exception:
                pass
        from enclosure_builder import EnclosureBuilder

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

        scope = {
            "__builtins__": SAFE_BUILTINS,
            "App": FreeCAD, "Gui": FreeCADGui,
            "FreeCAD": FreeCAD, "FreeCADGui": FreeCADGui,
            "doc": FreeCAD.ActiveDocument, "math": math,
            "find": resolve_obj,
            "EnclosureBuilder": EnclosureBuilder,
            "board_data": self._board_context,
            **available,
            "doc_name": FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None,
            "_wb": FreeCADGui.listWorkbenches() if hasattr(FreeCADGui, 'listWorkbenches') else {},
        }
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
            try:
                exec(code, scope)
            finally:
                sys.stdout = _exec_old_stdout
                sys.stderr = _exec_old_stderr
                sys.excepthook = _exec_old_excepthook
            doc = FreeCAD.ActiveDocument
            if doc:
                doc.recompute()
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
                except Exception:
                    pass
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
                    except Exception:
                        pass
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
            print(f"[AI] Error: {e}\n{tb}")
            diagnosis, strategy = translate_error(str(e))
            # Extract the most relevant line from traceback
            tb_short = ""
            for line in tb.split("\n"):
                if 'File "<string>"' in line or line.strip().startswith(("NameError", "AttributeError", "TypeError", "ValueError", "ImportError", "ZeroDivisionError", "KeyError", "IndexError", "RuntimeError")):
                    tb_short += line.strip() + " "
            context = f"Diagnosis: {diagnosis}"
            if strategy:
                context += f"\nStrategy: {strategy}"
            if tb_short:
                context += f"\nAt: {tb_short.strip()}"
            return False, context

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
        for name in ["bracket", "flange", "pipe", "gear"]:
            if name in pl:
                tpl = TEMPLATES.get(name, {})
                code = tpl.get("code", "")
                if code:
                    return code
                break
        if any(w in pl for w in ["wing", "airfoil", "aircraft", "aerofoil"]):
            chord = 200
            span = 1000
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
        if any(w in pl for w in ["cylinder","tube","pipe","round"]):
            r = dim1 / 2 if dim1 < 500 else dim1
            h = dim2 if dim2 != dim1 else dim3
            return f"""import FreeCAD
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Design")
obj = doc.addObject("Part::Cylinder", "Cylinder")
obj.Radius = {r}
obj.Height = {h}
obj.ViewObject.ShapeColor = (0.3, 0.6, 1.0)
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""
        if any(w in pl for w in ["sphere","ball","globe","orb"]):
            r = dim1 / 2
            return f"""import FreeCAD
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Design")
obj = doc.addObject("Part::Sphere", "Sphere")
obj.Radius = {r}
obj.ViewObject.ShapeColor = (0.3, 0.6, 1.0)
doc.recompute()
FreeCAD.Gui.SendMsgToActiveView("ViewFit")"""
        return f"""import FreeCAD
doc = FreeCAD.ActiveDocument
if not doc: doc = FreeCAD.newDocument("Design")
obj = doc.addObject("Part::Box", "Box")
obj.Length, obj.Width, obj.Height = {dim1}, {dim2}, {dim3}
obj.ViewObject.ShapeColor = (0.3, 0.6, 1.0)
doc.recompute()
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
        Modifications are detected by shape_hash (catches transient-object side effects)
        and filtered to only include objects in self._touched_objects
        (objects the AI's code actually created or changed, not recompute noise)."""
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
                    if self._is_datum(obj):
                        continue
                    entry = {
                        "name": obj.Name,
                        "uid": f"{dname}.{obj.Name}",
                        "label": obj.Label if hasattr(obj, 'Label') else obj.Name,
                        "type": obj.TypeId,
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
class ExecutionContext:
    """Snapshots FreeCAD UI state before AI execution and restores it after."""
    def snapshot(self):
        try:
            self.active_doc_name = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
        except Exception:
            self.active_doc_name = None
        try:
            wb = FreeCADGui.activeWorkbench()
            self.active_workbench = wb.name() if wb else None
        except Exception:
            self.active_workbench = None
        self.active_object = None
        self.in_edit = None
        try:
            doc = FreeCAD.ActiveDocument
            if doc:
                self.active_object = doc.ActiveObject
            gdoc = FreeCADGui.getDocument(self.active_doc_name) if self.active_doc_name else None
            if gdoc:
                self.in_edit = gdoc.getInEdit()
        except Exception:
            pass

    def restore(self):
        try:
            doc = FreeCAD.ActiveDocument
            if doc:
                from FreeCADGui import Selection
                Selection.clearSelection()
                if self.active_object:
                    try:
                        Selection.addSelection(self.active_object)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if self.active_workbench:
                FreeCADGui.activateWorkbench(self.active_workbench)
        except Exception:
            pass
        try:
            doc = FreeCAD.ActiveDocument
            if doc:
                doc.recompute()
        except Exception:
            pass

