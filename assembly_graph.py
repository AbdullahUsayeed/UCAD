import FreeCAD
import Part


class AssemblyGraph:
    """Constraint graph between bodies in a FreeCAD document.

    Nodes = bodies (PartDesign::Body, Part::Feature, etc.)
    Edges = constraints (Assembly::Joint, Part::Attachment, implicit placement)

    Injects constraint context into AI prompts so the AI knows which bodies
    are linked together.  After execution, ``verify()`` checks whether
    constrained bodies still satisfy their constraints and reports violations
    into the retry context — exactly the same pattern as the existing
    ``_check_geometry_bounds()`` for feature chains.
    """

    # ── Constraint edge ────────────────────────────────────
    class Edge:
        """A single constraint between two bodies."""

        def __init__(self, source: str, target: str, ctype: str, params: dict):
            self.source = source   # label or name of body A
            self.target = target   # label or name of body B
            self.type = ctype      # "fixed", "revolute", "offset", "parallel", "coincident", "attachment"
            self.params = params   # {"distance": 5.0, "axis": (0,0,1), ...}

        def describe(self) -> str:
            base = f"{self.source} ──[{self.type}]── {self.target}"
            if self.params:
                extras = ", ".join(f"{k}={v}" for k, v in self.params.items())
                base += f"  ({extras})"
            return base

        def violation(self, measured_distance: float, tolerance: float = 0.1) -> str | None:
            """Return a human-readable violation string if this constraint is broken, else None."""
            if self.type in ("fixed", "coincident"):
                if measured_distance > tolerance:
                    return (
                        f"{self.source} and {self.target} should be coincident "
                        f"(distance={measured_distance:.2f}mm > {tolerance:.1f}mm)"
                    )
            return None

    # ── Init ───────────────────────────────────────────────
    def __init__(self, doc):
        self.doc = doc
        self.edges: list[AssemblyGraph.Edge] = []
        self._used_doc_name = doc.Name if doc else ""
        self._ready = False
        if doc:
            self._scan()
            self._ready = True

    def rebuild(self):
        """Re-scan the document. Call before each execution. Safe if doc is None."""
        self.edges.clear()
        self._ready = False
        try:
            self.doc = FreeCAD.ActiveDocument
        except Exception:
            self.doc = None
        if self.doc:
            self._scan()
            self._ready = True

    # ── Scan ───────────────────────────────────────────────
    def _scan(self):
        """Walk the document and build constraint edges."""
        self.edges.clear()
        if not self.doc:
            return

        # 1. Assembly::Joint objects (Assembly Workbench)
        self._scan_joints()

        # 2. Part::Attachment / PartDesign::CoordinateSystem
        self._scan_attachments()

        # 3. Implicit placement (bodies at nearly the same position)
        self._scan_implicit()

    def _scan_joints(self):
        """Find Assembly::Joint objects and extract the two linked parts."""
        for obj in self.doc.Objects:
            if "Assembly::Joint" not in obj.TypeId:
                continue
            try:
                p1 = getattr(obj, "Object1", None)
                p2 = getattr(obj, "Object2", None)
                if not p1 or not p2:
                    continue
                s_label = p1.Label or p1.Name
                t_label = p2.Label or p2.Name
                jtype = getattr(obj, "Type", "Fixed")
                self.edges.append(AssemblyGraph.Edge(
                    source=s_label, target=t_label,
                    ctype=str(jtype).lower(),
                    params={"joint_name": obj.Label or obj.Name},
                ))
            except Exception:
                pass

    def _scan_attachments(self):
        """Find objects with AttachmentSupport (e.g. PartDesign bodies attached to other bodies)."""
        for obj in self.doc.Objects:
            try:
                supp = getattr(obj, "AttachmentSupport", None)
                if not supp:
                    # Check for MapMode / Sketch attachment
                    if hasattr(obj, "MapMode") and hasattr(obj, "AttachmentSupport"):
                        supp = obj.AttachmentSupport
                if not supp or not hasattr(supp, "__getitem__"):
                    continue
                parent = supp[0]
                if parent and parent != obj and not self._is_datum(parent):
                    offset = getattr(obj, "AttachmentOffset", None)
                    dist = 0.0
                    if offset and hasattr(offset, "Base"):
                        dist = offset.Base.Length
                    self.edges.append(AssemblyGraph.Edge(
                        source=parent.Label or parent.Name,
                        target=obj.Label or obj.Name,
                        ctype="attachment",
                        params={"offset_distance": round(dist, 2)},
                    ))
            except Exception:
                pass

    def _scan_implicit(self):
        """Detect bodies at nearly the same position — strong hint they should be constrained."""
        bodies = [o for o in self.doc.Objects
                  if hasattr(o, "Placement") and not self._is_datum(o)]
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                a, b = bodies[i], bodies[j]
                try:
                    d = a.Placement.Base.distToPoint(b.Placement.Base)
                    if d < 0.5:
                        self.edges.append(AssemblyGraph.Edge(
                            source=a.Label or a.Name,
                            target=b.Label or b.Name,
                            ctype="coincident",
                            params={"distance": round(d, 2)},
                        ))
                except Exception:
                    pass

    @staticmethod
    def _is_datum(obj) -> bool:
        tid = getattr(obj, "TypeId", "")
        if tid in ("App::Line", "App::Plane", "App::Origin"):
            return True
        label = getattr(obj, "Label", "") or ""
        return label in ("X-axis", "Y-axis", "Z-axis", "XY-plane", "XZ-plane", "YZ-plane")

    # ── Prompt injection ───────────────────────────────────
    def describe(self, max_edges: int = 20) -> str:
        """Return a formatted CONSTRAINTS section for the AI prompt."""
        if not self.edges:
            return ""
        lines = ["### CONSTRAINTS BETWEEN BODIES:"]
        for e in self.edges[:max_edges]:
            lines.append(f"  {e.describe()}")
        return "\n".join(lines)

    # ── Verification ───────────────────────────────────────
    def verify(self) -> list[str]:
        """Check all constraints are still satisfied after recompute.

        Returns a list of human-readable violation strings (empty = all satisfied).
        """
        violations = []
        for e in self.edges:
            obj_a = self._find(e.source)
            obj_b = self._find(e.target)
            if not obj_a or not obj_b:
                continue
            try:
                pa = obj_a.Placement.Base
                pb = obj_b.Placement.Base
                dist = pa.distToPoint(pb)
                v = e.violation(dist)
                if v:
                    violations.append(v)
            except Exception:
                pass
        return violations

    def _find(self, label_or_name: str):
        """Find an object by label or name."""
        if not self.doc:
            return None
        obj = self.doc.getObject(label_or_name)
        if obj:
            return obj
        for o in self.doc.Objects:
            if o.Label == label_or_name:
                return o
        for o in self.doc.Objects:
            if o.Name.lower() == label_or_name.lower() or o.Label.lower() == label_or_name.lower():
                return o
        return None

    # ── Snapshot ───────────────────────────────────────────
    def snapshot(self) -> dict[str, dict]:
        """Capture current placements of all constrained bodies for retry context.

        Returns {label: {"placement": (x,y,z), "rotation": (q0,q1,q2,q3)}}.
        """
        snap = {}
        seen = set()
        for e in self.edges:
            for name in (e.source, e.target):
                if name in seen:
                    continue
                seen.add(name)
                obj = self._find(name)
                if not obj or not hasattr(obj, "Placement"):
                    continue
                try:
                    p = obj.Placement.Base
                    r = obj.Placement.Rotation
                    snap[name] = {
                        "placement": (round(p.x, 2), round(p.y, 2), round(p.z, 2)),
                        "rotation": (round(r.Q[0], 4), round(r.Q[1], 4),
                                     round(r.Q[2], 4), round(r.Q[3], 4)),
                    }
                except Exception:
                    pass
        return snap
