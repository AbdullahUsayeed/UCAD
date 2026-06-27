from tools.registry import cad_tool, ToolResult


def _get_sketch(doc, name=None):
    if name:
        obj = doc.getObject(name)
        if obj:
            return obj
        for o in doc.Objects:
            if o.Label == name:
                return o
        return None
    sketches = [o for o in doc.Objects if o.TypeId == "Sketcher::SketchObject"]
    return sketches[-1] if sketches else None


def _find_by_label(doc, label: str):
    matches = [o for o in doc.Objects if o.Label == label]
    return matches[0] if matches else None


def _get_or_create_body(doc):
    bodies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]
    if bodies:
        return bodies[0]
    return doc.addObject("PartDesign::Body", "Body")


@cad_tool(
    "Close the open wire in a sketch by connecting start and end points",
    params={"sketch_name": "Name of the sketch (optional, uses active sketch if omitted)"}
)
def close_wire(sketch_name: str = None) -> ToolResult:
    try:
        import FreeCAD, Sketcher, Part
        doc = FreeCAD.ActiveDocument
        sketch = _get_sketch(doc, sketch_name)
        if not sketch:
            return ToolResult(False, "No sketch found. Open a sketch first.")
        edges = sketch.Shape.Edges
        open_edges = [e for e in edges if not e.isClosed()]
        if not open_edges:
            return ToolResult(False, "No open wire found in sketch.")
        first_pt = open_edges[0].firstVertex().Point
        last_pt = open_edges[-1].lastVertex().Point
        sketch.addGeometry(Part.LineSegment(last_pt, first_pt), False)
        doc.recompute()
        return ToolResult(True, "Wire closed successfully.")
    except Exception as e:
        return ToolResult(False, f"close_wire failed: {e}")


@cad_tool(
    "Add a fillet to edges of a solid object",
    params={
        "object_name": "Name of the Part object",
        "radius": "Fillet radius in mm",
        "edge_indices": "List of edge indices to fillet (omit for all edges)"
    }
)
def add_fillet(object_name: str, radius: float, edge_indices: list = None) -> ToolResult:
    try:
        import FreeCAD, Part
        doc = FreeCAD.ActiveDocument
        obj = doc.getObject(object_name) or _find_by_label(doc, object_name)
        if not obj:
            return ToolResult(False, f"Object {object_name!r} not found.")
        shape = obj.Shape
        edges = shape.Edges
        if edge_indices:
            target_edges = [edges[i] for i in edge_indices if i < len(edges)]
        else:
            target_edges = edges
        filleted = shape.makeFillet(radius, target_edges)
        fillet_obj = doc.addObject("Part::Feature", f"{object_name}_Fillet")
        fillet_obj.Shape = filleted
        fillet_obj.Label = f"{object_name} Fillet r{radius}"
        obj.Visibility = False
        doc.recompute()
        return ToolResult(True, f"Fillet r={radius} applied to {len(target_edges)} edges.",
                         {"object": fillet_obj.Name})
    except Exception as e:
        return ToolResult(False, f"add_fillet failed: {e}")


@cad_tool(
    "Create a box primitive",
    params={"length": "X dimension mm", "width": "Y dimension mm",
            "height": "Z dimension mm", "name": "Object name (optional)"}
)
def make_box(length: float, width: float, height: float, name: str = "Box") -> ToolResult:
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("Unnamed")
        box = doc.addObject("Part::Box", name)
        box.Length, box.Width, box.Height = length, width, height
        box.Label = name
        doc.recompute()
        return ToolResult(True, f"Box {length}\u00d7{width}\u00d7{height} created.",
                         {"object": box.Name})
    except Exception as e:
        return ToolResult(False, f"make_box failed: {e}")


@cad_tool(
    "Pad (extrude) a sketch into a 3D solid",
    params={"sketch_name": "Name of the sketch", "length": "Extrusion length mm",
            "symmetric": "Extrude symmetrically (default False)"}
)
def make_pad(sketch_name: str, length: float, symmetric: bool = False) -> ToolResult:
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        sketch = _get_sketch(doc, sketch_name)
        if not sketch:
            return ToolResult(False, f"Sketch {sketch_name!r} not found.")
        body = _get_or_create_body(doc)
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = length
        pad.Symmetric = symmetric
        doc.recompute()
        return ToolResult(True, f"Pad created: length={length}mm.",
                         {"object": pad.Name})
    except Exception as e:
        return ToolResult(False, f"make_pad failed: {e}")


@cad_tool(
    "Select a FreeCAD object by name or label",
    params={"name": "Object Name or Label to select"}
)
def select_object(name: str) -> ToolResult:
    try:
        import FreeCAD, FreeCADGui
        doc = FreeCAD.ActiveDocument
        obj = doc.getObject(name) or _find_by_label(doc, name)
        if not obj:
            return ToolResult(False, f"Object {name!r} not found.")
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(obj)
        return ToolResult(True, f"Selected: {obj.Label}")
    except Exception as e:
        return ToolResult(False, f"select_object failed: {e}")


@cad_tool(
    "Delete a FreeCAD object by name or label",
    params={"name": "Object Name or Label to delete"}
)
def delete_object(name: str) -> ToolResult:
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        obj = doc.getObject(name) or _find_by_label(doc, name)
        if not obj:
            return ToolResult(False, f"Object {name!r} not found.")
        label = obj.Label
        doc.removeObject(obj.Name)
        doc.recompute()
        return ToolResult(True, f"Deleted: {label}")
    except Exception as e:
        return ToolResult(False, f"delete_object failed: {e}")


@cad_tool(
    "Hide or show a FreeCAD object",
    params={"name": "Object Name or Label", "visible": "True to show, False to hide"}
)
def set_visibility(name: str, visible: bool = False) -> ToolResult:
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        obj = doc.getObject(name) or _find_by_label(doc, name)
        if not obj:
            return ToolResult(False, f"Object {name!r} not found.")
        if hasattr(obj, "ViewObject") and obj.ViewObject:
            obj.ViewObject.Visibility = visible
        else:
            obj.Visibility = visible
        doc.recompute()
        state = "shown" if visible else "hidden"
        return ToolResult(True, f"{obj.Label} {state}.")
    except Exception as e:
        return ToolResult(False, f"set_visibility failed: {e}")


@cad_tool(
    "Measure distance between two objects or points",
    params={"obj1": "First object name", "obj2": "Second object name"}
)
def measure_distance(obj1: str, obj2: str) -> ToolResult:
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        o1 = doc.getObject(obj1) or _find_by_label(doc, obj1)
        o2 = doc.getObject(obj2) or _find_by_label(doc, obj2)
        if not o1 or not o2:
            return ToolResult(False, "One or both objects not found.")
        c1 = o1.Shape.BoundBox.Center
        c2 = o2.Shape.BoundBox.Center
        dist = (c2 - c1).Length
        return ToolResult(True, f"Distance {obj1}\u2194{obj2}: {dist:.2f} mm",
                         {"distance_mm": round(dist, 4)})
    except Exception as e:
        return ToolResult(False, f"measure_distance failed: {e}")


@cad_tool(
    "List all objects in the active FreeCAD document",
    params={}
)
def list_objects() -> ToolResult:
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        if not doc:
            return ToolResult(False, "No active document.")
        objects = [{"name": o.Name, "label": o.Label, "type": o.TypeId}
                   for o in doc.Objects]
        summary = "\n".join(f"  {o['label']} ({o['type']})" for o in objects)
        return ToolResult(True, f"Document has {len(objects)} objects:\n{summary}",
                         {"objects": objects})
    except Exception as e:
        return ToolResult(False, f"list_objects failed: {e}")


@cad_tool(
    "Fit the FreeCAD viewport to show all objects",
    params={}
)
def fit_view() -> ToolResult:
    try:
        import FreeCADGui
        FreeCADGui.SendMsgToActiveView("ViewFit")
        return ToolResult(True, "View fitted.")
    except Exception as e:
        return ToolResult(False, f"fit_view failed: {e}")


@cad_tool(
    "Recompute the active FreeCAD document",
    params={}
)
def recompute() -> ToolResult:
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        if not doc:
            return ToolResult(False, "No active document.")
        doc.recompute()
        return ToolResult(True, "Document recomputed.")
    except Exception as e:
        return ToolResult(False, f"recompute failed: {e}")


@cad_tool(
    "Set a property on a FreeCAD object",
    params={"object_name": "Object name or label",
            "property": "Property name (e.g. Length, Height)",
            "value": "Value to set"}
)
def set_property(object_name: str, property: str, value) -> ToolResult:
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
        obj = doc.getObject(object_name) or _find_by_label(doc, object_name)
        if not obj:
            return ToolResult(False, f"Object {object_name!r} not found.")
        if not hasattr(obj, property):
            return ToolResult(False, f"{obj.Label} has no property {property!r}.")
        setattr(obj, property, value)
        doc.recompute()
        return ToolResult(True, f"{obj.Label}.{property} = {value}")
    except Exception as e:
        return ToolResult(False, f"set_property failed: {e}")
