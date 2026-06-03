import FreeCAD
import Part
import math


class EnclosureBuilder:
    def __init__(self, doc=None):
        if doc is None:
            doc = FreeCAD.ActiveDocument
        if doc is None:
            doc = FreeCAD.newDocument("Enclosure")
        self.doc = doc
        self.base_shape = None
        self.lid_shape = None
        self._params = {}

    def create_base_shell(self, board_data, wall_t=2.5, floor_t=2.0):
        dims = board_data["dimensions"]
        bw = dims["width"]
        bd = dims["height"]
        bx = dims.get("x_min", 0)
        by = dims.get("y_min", 0)
        tallest = max((c["height"] for c in board_data["components"]), default=10.0)

        margin = 2.0
        outer_w = bw + 2 * wall_t + 2 * margin
        outer_d = bd + 2 * wall_t + 2 * margin
        outer_h = tallest + floor_t + wall_t + margin

        self._params = {
            "wall_t": wall_t, "floor_t": floor_t, "margin": margin,
            "outer_w": outer_w, "outer_d": outer_d, "outer_h": outer_h,
            "board_x0": bx, "board_y0": by,
            "bw": bw, "bd": bd,
        }

        outer = Part.makeBox(outer_w, outer_d, outer_h)
        inner = Part.makeBox(
            max(0.1, outer_w - 2 * wall_t),
            max(0.1, outer_d - 2 * wall_t),
            max(0.1, outer_h - floor_t),
        )
        inner.translate(FreeCAD.Vector(wall_t, wall_t, floor_t))
        self.base_shape = outer.cut(inner)
        self._add_to_doc("BaseShell", self.base_shape)
        return self.base_shape

    def add_mounting_bosses(self, board_data, boss_od=6.0):
        if self.base_shape is None:
            raise RuntimeError("Call create_base_shell first")
        p = self._params
        wall_t = p["wall_t"]
        floor_t = p["floor_t"]
        margin = p["margin"]
        bx = p["board_x0"]
        by = p["board_y0"]

        holes = board_data.get("mounting_holes", [])
        if holes:
            positions = []
            for h in holes:
                ex = h["x"] - bx + wall_t + margin
                ey = h["y"] - by + wall_t + margin
                positions.append((ex, ey))
        else:
            boss_margin = margin + wall_t + 2.0
            positions = [
                (boss_margin, boss_margin),
                (p["outer_w"] - boss_margin, boss_margin),
                (boss_margin, p["outer_d"] - boss_margin),
                (p["outer_w"] - boss_margin, p["outer_d"] - boss_margin),
            ]

        boss_r = boss_od / 2
        boss_id_r = boss_r - 0.5
        for ex, ey in positions:
            boss = Part.makeCylinder(boss_r, p["outer_h"] - floor_t, FreeCAD.Vector(ex, ey, floor_t))
            hole = Part.makeCylinder(boss_id_r, p["outer_h"], FreeCAD.Vector(ex, ey, 0))
            self.base_shape = self.base_shape.fuse(boss).cut(hole)

        self._add_to_doc("BaseWithBosses", self.base_shape)
        return self.base_shape

    def add_connector_cutouts(self, board_data, clearance=0.5):
        if self.base_shape is None:
            raise RuntimeError("Call create_base_shell first")
        p = self._params
        wall_t = p["wall_t"]
        floor_t = p["floor_t"]
        margin = p["margin"]
        bx = p["board_x0"]
        by = p["board_y0"]

        for conn in board_data.get("edge_connectors", []):
            cx = conn["x"] - bx + wall_t + margin
            cy = conn["y"] - by + wall_t + margin
            cw = 12.0 + clearance * 2
            ch = conn["height"] + clearance * 2
            depth_wall = wall_t + 1

            if cx < margin + 2.0:
                # left wall
                cut = Part.makeBox(depth_wall, cw, ch, FreeCAD.Vector(-0.1, cy - cw / 2, floor_t))
            elif cx > p["outer_w"] - (margin + 2.0):
                # right wall
                cut = Part.makeBox(depth_wall, cw, ch, FreeCAD.Vector(p["outer_w"] - depth_wall + 0.1, cy - cw / 2, floor_t))
            elif cy < margin + 2.0:
                # front wall
                cut = Part.makeBox(cw, depth_wall, ch, FreeCAD.Vector(cx - cw / 2, -0.1, floor_t))
            elif cy > p["outer_d"] - (margin + 2.0):
                # back wall
                cut = Part.makeBox(cw, depth_wall, ch, FreeCAD.Vector(cx - cw / 2, p["outer_d"] - depth_wall + 0.1, floor_t))
            else:
                continue
            self.base_shape = self.base_shape.cut(cut)

        self._add_to_doc("BaseWithCutouts", self.base_shape)
        return self.base_shape

    def create_lid(self, board_data, component_clearance=3.0):
        p = self._params
        wall_t = p["wall_t"]
        outer_w = p["outer_w"]
        outer_d = p["outer_d"]
        outer_h = p["outer_h"]
        lid_h = wall_t
        lip_h = wall_t
        lip_clearance = 0.2

        lid = Part.makeBox(outer_w, outer_d, lid_h, FreeCAD.Vector(0, 0, outer_h))
        lip = Part.makeBox(
            outer_w - wall_t * 2 - lip_clearance,
            outer_d - wall_t * 2 - lip_clearance,
            lip_h,
            FreeCAD.Vector(wall_t + lip_clearance / 2, wall_t + lip_clearance / 2, outer_h + lid_h),
        )
        self.lid_shape = lid.fuse(lip)
        self._add_to_doc("Lid", self.lid_shape)
        return self.lid_shape

    def add_snap_fits(self, base, lid, count=4):
        pass

    def add_ventilation(self, board_data, near_components=None):
        pass

    def _add_to_doc(self, label, shape):
        obj = self.doc.addObject("Part::Feature", label)
        obj.Shape = shape
        self.doc.recompute()
        return obj
