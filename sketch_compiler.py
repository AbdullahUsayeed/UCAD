import json
import re


class SketchCompiler:
    def compile_all(self, text):
        """Extract ```json blocks from AI response and compile to Python."""
        blocks = re.findall(r"```json\n(.*?)```", text, re.DOTALL)
        parts = []
        for b in blocks:
            b = b.strip()
            if not b:
                continue
            try:
                data = json.loads(b)
            except json.JSONDecodeError:
                continue
            if "sketch" in data:
                parts.append(self._compile(data["sketch"]))
        return "\n\n".join(parts)

    def _compile(self, data):
        body = data.get("body", "Body")
        name = data.get("name", "Sketch")
        primitives = data.get("primitives", [])
        extra = data.get("constraints", [])

        lines = [
            "_geo = []",
            "_con = []",
            f"body = doc.getObject('{body}') or doc.addObject('PartDesign::Body', '{body}')",
            f"sketch = body.newObject('Sketcher::SketchObject', '{name}')",
        ]

        geo_idx = 0
        prev_end = None

        for prim in primitives:
            t = prim["type"]

            if t == "rectangle":
                x, y, w, h = prim["x"], prim["y"], prim["w"], prim["h"]
                pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                for i in range(4):
                    x1, y1 = pts[i]
                    x2, y2 = pts[(i + 1) % 4]
                    lines.append(
                        f"_geo.append(Part.LineSegment(App.Vector({x1},{y1},0), App.Vector({x2},{y2},0)))"
                    )
                for i in range(4):
                    nxt = (i + 1) % 4
                    lines.append(
                        f"_con.append(Sketcher.Constraint('Coincident', {geo_idx + i}, 2, {geo_idx + nxt}, 1))"
                    )
                geo_idx += 4
                prev_end = None

            elif t == "circle":
                cx, cy, r = prim["cx"], prim["cy"], prim["r"]
                lines.append(
                    f"_geo.append(Part.Circle(App.Vector({cx},{cy},0), App.Vector(0,0,1), {r}))"
                )
                geo_idx += 1
                prev_end = None

            elif t == "line":
                x1, y1, x2, y2 = prim["x1"], prim["y1"], prim["x2"], prim["y2"]
                lines.append(
                    f"_geo.append(Part.LineSegment(App.Vector({x1},{y1},0), App.Vector({x2},{y2},0)))"
                )
                if prev_end is not None and abs(prev_end[0] - x1) < 1e-6 and abs(prev_end[1] - y1) < 1e-6:
                    lines.append(
                        f"_con.append(Sketcher.Constraint('Coincident', {geo_idx - 1}, 2, {geo_idx}, 1))"
                    )
                prev_end = (x2, y2)
                geo_idx += 1

            elif t == "polygon":
                pts = prim["points"]
                n = len(pts)
                for i in range(n):
                    x1, y1 = pts[i]
                    x2, y2 = pts[(i + 1) % n]
                    lines.append(
                        f"_geo.append(Part.LineSegment(App.Vector({x1},{y1},0), App.Vector({x2},{y2},0)))"
                    )
                for i in range(n):
                    nxt = (i + 1) % n
                    lines.append(
                        f"_con.append(Sketcher.Constraint('Coincident', {geo_idx + i}, 2, {geo_idx + nxt}, 1))"
                    )
                geo_idx += n
                prev_end = None

        lines.append("sketch.addGeometry(_geo, False)")

        if extra:
            for c in extra:
                ct = c["type"]
                if ct == "DistanceX":
                    lines.append(
                        f"_con.append(Sketcher.Constraint('DistanceX', {c['geo']}, {c['value']}))"
                    )
                elif ct == "DistanceY":
                    lines.append(
                        f"_con.append(Sketcher.Constraint('DistanceY', {c['geo']}, {c['value']}))"
                    )
                elif ct == "Distance":
                    lines.append(
                        f"_con.append(Sketcher.Constraint('Distance', {c['geo']}, {c['value']}))"
                    )
                elif ct == "Coincident":
                    lines.append(
                        f"_con.append(Sketcher.Constraint('Coincident', {c['g1']}, {c['v1']}, {c['g2']}, {c['v2']}))"
                    )
                elif ct == "Horizontal":
                    lines.append(
                        f"_con.append(Sketcher.Constraint('Horizontal', {c['geo']}))"
                    )
                elif ct == "Vertical":
                    lines.append(
                        f"_con.append(Sketcher.Constraint('Vertical', {c['geo']}))"
                    )

        lines.append("sketch.addConstraint(_con)")
        lines.append("doc.recompute()")
        return "\n".join(lines)
