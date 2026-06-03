"""Read-only TechDraw page generator.

AI code calls this instead of freehanding TechDraw API calls.
Fixed template: create page -> create view -> set projection -> add dimensions.
Read-only — never modifies geometry, no retry loop needed.
"""

import os
import FreeCAD
import FreeCADGui


class DrawingGenerator:
    """Generates TechDraw drawing pages from bodies.

    Usage from AI-generated code::

        from drawing_generator import DrawingGenerator
        dg = DrawingGenerator()
        ok, msg = dg.create_page(
            body_names=["Body", "Lid"],
            views=["top", "front", "right", "isometric"],
            scale=1.0,
        )
        if ok:
            dg.add_dimension(page_view, edge_index=0, dim_type="Distance")
    """

    # View name -> direction vector
    VIEW_DIRECTIONS = {
        "top":       (0, 0, 1),
        "front":     (0, -1, 0),
        "rear":      (0, 1, 0),
        "left":      (-1, 0, 0),
        "right":     (1, 0, 0),
        "isometric": (1, -1, 1),
    }

    def __init__(self, doc=None):
        if doc is None:
            try:
                doc = FreeCAD.ActiveDocument
            except Exception:
                doc = None
        self.doc = doc
        self._template_path = self._find_template()

    @staticmethod
    def _find_template():
        """Locate the default A4_Portrait SVG template shipped with FreeCAD."""
        candidates = [
            os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw",
                         "Templates", "A4_Portrait_ISO.svg"),
            os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw",
                         "Templates", "A4_Portrait_ISO7200.svg"),
            os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw",
                         "Templates", "A4_Landscape_ISO.svg"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        # Last resort — let FreeCAD resolve it
        return "A4_Portrait_ISO.svg"

    def create_page(self, body_names, views=None, scale=1.0, page_label="Drawing"):
        """Create a TechDraw page with views of the named bodies.

        Args:
            body_names: list of object names or labels to include
            views: list from VIEW_DIRECTIONS keys, or None for ["top", "isometric"]
            scale: scale factor applied to all views

        Returns:
            (success: bool, message: str)
        """
        doc = self.doc
        if doc is None:
            return False, "No active document."

        # Resolve body objects
        bodies = []
        missing = []
        for name in body_names:
            obj = self._find(name)
            if obj:
                bodies.append(obj)
            else:
                missing.append(name)
        if not bodies:
            return False, f"No bodies found: {', '.join(missing)}"
        if missing:
            msg = f"Missing objects (skipped): {', '.join(missing)}. "

        try:
            import TechDraw
        except ImportError:
            return False, "TechDraw workbench is not available."

        if views is None:
            views = ["top", "isometric"]

        try:
            # 1. Page
            page = doc.addObject("TechDraw::DrawPage", page_label)
            template = doc.addObject("TechDraw::DrawSVGTemplate", f"{page_label}Template")
            template.Template = self._template_path
            page.Template = template

            # 2. Views
            created_views = []
            for vname in views:
                direction = self.VIEW_DIRECTIONS.get(vname)
                if direction is None:
                    continue
                view_label = f"{page_label}{vname.capitalize()}"
                view = doc.addObject("TechDraw::DrawViewPart", view_label)
                view.Source = bodies
                view.Direction = direction
                view.Scale = scale
                view.XDirection = (1, 0, 0)
                page.addView(view)
                created_views.append(view)

            doc.recompute()
            FreeCADGui.SendMsgToActiveView("ViewFit")

            count = len(created_views)
            extra = f" {msg}" if missing else ""
            return True, f"Created page '{page_label}' with {count} view(s).{extra}"
        except Exception as ex:
            return False, f"TechDraw page creation failed: {ex}"

    def add_dimension(self, view, edge_index=0, dim_type="Distance"):
        """Add a dimension to an existing TechDraw view.

        Args:
            view: TechDraw::DrawViewPart object or its label/name
            edge_index: index into the view's visible edges
            dim_type: "Distance", "Length", "Radius", "Diameter"

        Returns:
            (success: bool, message: str)
        """
        if isinstance(view, str):
            view = self._find(view)
        if not view:
            return False, f"View not found: {view}"

        try:
            import TechDraw
        except ImportError:
            return False, "TechDraw workbench is not available."

        try:
            page = view.Parent
            edges = view.getVisibleEdges()
            if edge_index >= len(edges):
                return False, f"Edge index {edge_index} out of range ({len(edges)} edges)"

            dim = self.doc.addObject("TechDraw::DrawViewDimension", f"Dim_{view.Label}_{edge_index}")
            dim.References2D = [(view, str(edges[edge_index]))]
            dim.Type = dim_type
            page.addView(dim)
            self.doc.recompute()
            return True, f"Added {dim_type} dimension to {view.Label} edge {edge_index}."
        except Exception as ex:
            return False, f"Dimension creation failed: {ex}"

    def add_dimensions_to_view(self, view, dim_specs):
        """Add multiple dimensions to a view.

        Args:
            view: TechDraw view object or label
            dim_specs: list of (edge_index, dim_type) tuples

        Returns:
            (success_count, fail_count, messages)
        """
        ok = 0
        fail = 0
        msgs = []
        for idx, dtype in dim_specs:
            s, m = self.add_dimension(view, idx, dtype)
            if s:
                ok += 1
            else:
                fail += 1
                msgs.append(m)
        return ok, fail, msgs

    # ── Internal ────────────────────────────────────────────
    def _find(self, name_or_label):
        if not self.doc:
            return None
        obj = self.doc.getObject(name_or_label)
        if obj:
            return obj
        for o in self.doc.Objects:
            if o.Label == name_or_label:
                return o
        for o in self.doc.Objects:
            if o.Name.lower() == name_or_label.lower() or o.Label.lower() == name_or_label.lower():
                return o
        return None
