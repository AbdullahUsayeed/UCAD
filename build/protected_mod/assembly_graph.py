import FreeCAD
class AssemblyGraph:
    class Edge:
        def __init__(self, source: str, target: str, ctype: str, params: dict):
            self.source = source
            self.target = target
            self.type = ctype
            self.params = params
        def describe(self) -> str:
            base = f'{self.source} ──[{self.type}]── {self.target}'
            if self.params:
                extras = ', '.join((f'{k}={v}' for k, v in self.params.items()))
                base += f'  ({extras})'
            return base
        def violation(self, measured_distance: float, tolerance: float=0.1) -> str | None:
            if self.type in ('fixed', 'coincident'):
                if measured_distance > tolerance:
                    return f'{self.source} and {self.target} should be coincident (distance={measured_distance:.2f}mm > {tolerance:.1f}mm)'
            return None
    def __init__(self, doc):
        self.doc = doc
        self.edges: list[AssemblyGraph.Edge] = []
        self._used_doc_name = doc.Name if doc else ''
        self._ready = False
        if doc:
            self._scan()
            self._ready = True
    def rebuild(self):
        self.edges.clear()
        self._ready = False
        try:
            self.doc = FreeCAD.ActiveDocument
        except Exception as ex:
            print(f'[AI] AssemblyGraph.rebuild failed: {ex}')
            self.doc = None
        if self.doc:
            self._scan()
            self._ready = True
    def _scan(self):
        self.edges.clear()
        if not self.doc:
            return
        self._scan_joints()
        self._scan_attachments()
        self._scan_implicit()
    def _scan_joints(self):
        for obj in self.doc.Objects:
            if 'Assembly::Joint' not in obj.TypeId:
                continue
            try:
                p1 = getattr(obj, 'Object1', None)
                p2 = getattr(obj, 'Object2', None)
                if not p1 or not p2:
                    continue
                s_label = p1.Label or p1.Name
                t_label = p2.Label or p2.Name
                jtype = getattr(obj, 'Type', 'Fixed')
                self.edges.append(AssemblyGraph.Edge(source=s_label, target=t_label, ctype=str(jtype).lower(), params={'joint_name': obj.Label or obj.Name}))
            except Exception as ex:
                print(f'[AI] AssemblyGraph._scan_joints failed: {ex}')
    def _scan_attachments(self):
        for obj in self.doc.Objects:
            try:
                supp = getattr(obj, 'AttachmentSupport', None)
                if not supp:
                    if hasattr(obj, 'MapMode') and hasattr(obj, 'AttachmentSupport'):
                        supp = obj.AttachmentSupport
                if not supp or not hasattr(supp, '__getitem__'):
                    continue
                parent = supp[0]
                if isinstance(parent, tuple):
                    parent = parent[0]
                if parent and parent != obj and (not self._is_datum(parent)):
                    offset = getattr(obj, 'AttachmentOffset', None)
                    dist = 0.0
                    if offset and hasattr(offset, 'Base'):
                        dist = offset.Base.Length
                    self.edges.append(AssemblyGraph.Edge(source=parent.Label or parent.Name, target=obj.Label or obj.Name, ctype='attachment', params={'offset_distance': round(dist, 2)}))
            except Exception as ex:
                print(f'[AI] AssemblyGraph._scan_attachments failed: {ex}')
    def _scan_implicit(self):
        bodies = [o for o in self.doc.Objects if hasattr(o, 'Placement') and (not self._is_datum(o))]
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                a, b = (bodies[i], bodies[j])
                try:
                    d = (a.Placement.Base - b.Placement.Base).Length
                    if d < 0.5:
                        self.edges.append(AssemblyGraph.Edge(source=a.Label or a.Name, target=b.Label or b.Name, ctype='coincident', params={'distance': round(d, 2)}))
                except Exception as ex:
                    print(f'[AI] AssemblyGraph._scan_implicit failed: {ex}')
    @staticmethod
    def _is_datum(obj) -> bool:
        tid = getattr(obj, 'TypeId', '')
        if tid in ('App::Line', 'App::Plane', 'App::Origin'):
            return True
        label = getattr(obj, 'Label', '') or ''
        return label in ('X-axis', 'Y-axis', 'Z-axis', 'XY-plane', 'XZ-plane', 'YZ-plane')
    def describe(self, max_edges: int=20) -> str:
        if not self.edges:
            return ''
        lines = ['### CONSTRAINTS BETWEEN BODIES:']
        for e in self.edges[:max_edges]:
            lines.append(f'  {e.describe()}')
        return '\n'.join(lines)
    def verify(self, at_risk_bodies=None):
        edges_to_check = self.edges
        if at_risk_bodies:
            body_set = set(at_risk_bodies)
            edges_to_check = [e for e in self.edges if e.source in body_set or e.target in body_set]
            if not edges_to_check:
                return []
        violations = []
        checked_pairs: set[tuple[str, str]] = set()
        for e in edges_to_check:
            obj_a = self._find(e.source)
            obj_b = self._find(e.target)
            if not obj_a or not obj_b:
                continue
            try:
                pa = obj_a.Placement.Base
                pb = obj_b.Placement.Base
                dist = (pa - pb).Length
                v = e.violation(dist)
                if v:
                    violations.append(v)
            except Exception as ex:
                print(f'[AI] AssemblyGraph.verify failed: {ex}')
            pair_key = tuple(sorted([e.source, e.target]))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            try:
                shape_a = getattr(obj_a, 'Shape', None)
                shape_b = getattr(obj_b, 'Shape', None)
                if shape_a is None or shape_b is None:
                    continue
                bb_a = shape_a.BoundBox
                bb_b = shape_b.BoundBox
                if not bb_a.intersect(bb_b):
                    continue
                common = shape_a.common(shape_b)
                if common and common.Volume > 1e-06:
                    violations.append(f'{e.source} and {e.target} INTERFERE — overlap volume={common.Volume:.1f}mm³')
            except Exception as ex:
                print(f'[AI] AssemblyGraph.verify interference failed: {ex}')
        return violations
    def _find(self, label_or_name: str):
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
    def snapshot(self) -> dict[str, dict]:
        snap = {}
        seen = set()
        for e in self.edges:
            for name in (e.source, e.target):
                if name in seen:
                    continue
                seen.add(name)
                obj = self._find(name)
                if not obj or not hasattr(obj, 'Placement'):
                    continue
                try:
                    p = obj.Placement.Base
                    r = obj.Placement.Rotation
                    snap[name] = {'placement': (round(p.x, 2), round(p.y, 2), round(p.z, 2)), 'rotation': (round(r.Q[0], 4), round(r.Q[1], 4), round(r.Q[2], 4), round(r.Q[3], 4))}
                except Exception as ex:
                    print(f'[AI] AssemblyGraph.snapshot failed: {ex}')
        return snap
    def affected_constraints(self, body_name: str, max_depth: int=3) -> list[tuple]:
        visited_bodies = {body_name}
        visited_edges: set[int] = set()
        queue: list[tuple[str, int]] = [(body_name, 0)]
        results: list[tuple[str, str, str, int]] = []
        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for idx, edge in enumerate(self.edges):
                if idx in visited_edges:
                    continue
                neighbor = None
                if edge.source == current:
                    neighbor = edge.target
                elif edge.target == current:
                    neighbor = edge.source
                if neighbor is None:
                    continue
                visited_edges.add(idx)
                results.append((edge.describe(), neighbor, edge.type, depth + 1))
                if neighbor not in visited_bodies:
                    visited_bodies.add(neighbor)
                    queue.append((neighbor, depth + 1))
        return results
    def describe_affected(self, body_name: str, max_depth: int=3) -> str:
        hits = self.affected_constraints(body_name, max_depth)
        if not hits:
            return ''
        lines = [f'### CONSTRAINTS AT RISK (via {body_name}):']
        for desc, neighbor, ctype, depth in hits:
            marker = '⚠️' if depth == 1 else '  ⚡'
            lines.append(f'  {marker} {desc}')
        return '\n'.join(lines)
