import FreeCAD
import Part
class EnclosureBuilder:
    SCREW_SIZES = {'M2': (1.6, 2.2, 4.0), 'M2.5': (2.05, 2.7, 5.0), 'M3': (2.5, 3.2, 6.0), 'M3.5': (2.9, 3.7, 7.0), 'M4': (3.3, 4.3, 8.0), 'M5': (4.2, 5.3, 10.0), 'M6': (5.0, 6.4, 12.0)}
    def __init__(self, doc=None):
        if doc is None:
            doc = FreeCAD.ActiveDocument
        if doc is None:
            doc = FreeCAD.newDocument('Enclosure')
        self.doc = doc
        self.base_shape = None
        self.lid_shape = None
        self._params = {}
    def create_base_shell(self, board_data, wall_t=2.5, floor_t=2.0, margin=2.0):
        dims = board_data['dimensions']
        bw = dims['width']
        bd = dims['height']
        bx = dims.get('x_min', 0)
        by = dims.get('y_min', 0)
        tallest = max((c['height'] for c in board_data['components']), default=10.0)
        outer_w = bw + 2 * wall_t + 2 * margin
        outer_d = bd + 2 * wall_t + 2 * margin
        outer_h = tallest + floor_t + wall_t + margin
        self._params = {'wall_t': wall_t, 'floor_t': floor_t, 'margin': margin, 'outer_w': outer_w, 'outer_d': outer_d, 'outer_h': outer_h, 'board_x0': bx, 'board_y0': by, 'bw': bw, 'bd': bd}
        outer = Part.makeBox(outer_w, outer_d, outer_h)
        inner = Part.makeBox(max(0.1, outer_w - 2 * wall_t), max(0.1, outer_d - 2 * wall_t), max(0.1, outer_h - floor_t))
        inner.translate(FreeCAD.Vector(wall_t, wall_t, floor_t))
        self.base_shape = outer.cut(inner)
        self._add_to_doc('BaseShell', self.base_shape)
        return self.base_shape
    def add_mounting_bosses(self, board_data, boss_od=6.0, screw_size='M3', standoff_height=None):
        if self.base_shape is None:
            raise RuntimeError('Call create_base_shell first')
        p = self._params
        wall_t = p['wall_t']
        floor_t = p['floor_t']
        margin = p['margin']
        bx = p['board_x0']
        by = p['board_y0']
        if screw_size in self.SCREW_SIZES:
            tap_dia, clearance_dia, default_od = self.SCREW_SIZES[screw_size]
            screw_r = tap_dia / 2
            if boss_od == 6.0:
                boss_od = default_od
            screw_diameter = tap_dia
        else:
            clearance_dia = boss_od - 1.0
            screw_r = boss_od / 2 - 0.5
            screw_diameter = screw_r * 2
        if standoff_height is None:
            cavity_h = p['outer_h'] - floor_t
            standoff_height = min(max(screw_diameter * 3, 5.0), cavity_h * 0.5)
        holes = board_data.get('mounting_holes', [])
        if holes:
            positions = []
            for h in holes:
                ex = h['x'] - bx + wall_t + margin
                ey = h['y'] - by + wall_t + margin
                positions.append((ex, ey))
        else:
            boss_margin = margin + wall_t + 2.0
            positions = [(boss_margin, boss_margin), (p['outer_w'] - boss_margin, boss_margin), (boss_margin, p['outer_d'] - boss_margin), (p['outer_w'] - boss_margin, p['outer_d'] - boss_margin)]
        boss_r = boss_od / 2
        overlap = 0.05
        for ex, ey in positions:
            boss = Part.makeCylinder(boss_r, standoff_height + overlap, FreeCAD.Vector(ex, ey, floor_t - overlap))
            hole_h = standoff_height + floor_t + overlap * 2
            through_hole = Part.makeCylinder(screw_r, hole_h, FreeCAD.Vector(ex, ey, -overlap))
            self.base_shape = self.base_shape.fuse(boss).cut(through_hole)
        self._boss_positions = positions
        self._clearance_dia = clearance_dia
        self._screw_size = screw_size
        self._add_to_doc('BaseWithBosses', self.base_shape)
        return self.base_shape
    def add_connector_cutouts(self, board_data, clearance=0.5, cutout_width=14.0):
        if self.base_shape is None:
            raise RuntimeError('Call create_base_shell first')
        p = self._params
        wall_t = p['wall_t']
        floor_t = p['floor_t']
        margin = p['margin']
        bx = p['board_x0']
        by = p['board_y0']
        outer_w = p['outer_w']
        outer_d = p['outer_d']
        for conn in board_data.get('edge_connectors', []):
            cx = conn['x'] - bx + wall_t + margin
            cy = conn['y'] - by + wall_t + margin
            rotation = conn.get('rotation', 0) % 360
            conn_w = conn.get('connector_width') or conn.get('width') or cutout_width
            cw = max(conn_w, 8.0) + clearance * 2
            ch = max(conn.get('height', 8.0), 6.0) + clearance * 2
            depth_wall = wall_t + 1
            dist_left = cx
            dist_right = outer_w - cx
            dist_front = cy
            dist_back = outer_d - cy
            min_dist = min(dist_left, dist_right, dist_front, dist_back)
            if min_dist == dist_left:
                side = 'left'
            elif min_dist == dist_right:
                side = 'right'
            elif min_dist == dist_front:
                side = 'front'
            else:
                side = 'back'
            rot_wall = {0: 'right', 90: 'back', 180: 'left', 270: 'front'}
            if rotation in rot_wall:
                side = rot_wall[rotation]
            if side == 'left':
                cut = Part.makeBox(depth_wall, cw, ch, FreeCAD.Vector(-0.1, cy - cw / 2, floor_t))
            elif side == 'right':
                cut = Part.makeBox(depth_wall, cw, ch, FreeCAD.Vector(outer_w - depth_wall + 0.1, cy - cw / 2, floor_t))
            elif side == 'front':
                cut = Part.makeBox(cw, depth_wall, ch, FreeCAD.Vector(cx - cw / 2, -0.1, floor_t))
            else:
                cut = Part.makeBox(cw, depth_wall, ch, FreeCAD.Vector(cx - cw / 2, outer_d - depth_wall + 0.1, floor_t))
            self.base_shape = self.base_shape.cut(cut)
        self._add_to_doc('BaseWithCutouts', self.base_shape)
        return self.base_shape
    def create_lid(self, board_data, component_clearance=3.0, lid_t=None):
        p = self._params
        wall_t = p['wall_t']
        outer_w = p['outer_w']
        outer_d = p['outer_d']
        outer_h = p['outer_h']
        lid_h = lid_t if lid_t is not None else wall_t
        lip_h = wall_t
        lip_clearance = 0.2
        lid = Part.makeBox(outer_w, outer_d, lid_h, FreeCAD.Vector(0, 0, outer_h))
        lip = Part.makeBox(outer_w - wall_t * 2 - lip_clearance, outer_d - wall_t * 2 - lip_clearance, lip_h, FreeCAD.Vector(wall_t + lip_clearance / 2, wall_t + lip_clearance / 2, outer_h + lid_h))
        self.lid_shape = lid.fuse(lip)
        if hasattr(self, '_boss_positions') and hasattr(self, '_clearance_dia'):
            clr_r = self._clearance_dia / 2
            for ex, ey in self._boss_positions:
                hole = Part.makeCylinder(clr_r, lid_h + 0.1, FreeCAD.Vector(ex, ey, outer_h - 0.05))
                self.lid_shape = self.lid_shape.cut(hole)
        self._add_to_doc('Lid', self.lid_shape)
        return self.lid_shape
    @staticmethod
    def v(x, y, z):
        return FreeCAD.Vector(x, y, z)
    @staticmethod
    def rrect(lx, ly, lz, r, x=0, y=0, z=0):
        if r <= 0 or 2 * r >= lx or 2 * r >= ly:
            return Part.makeBox(lx, ly, lz, FreeCAD.Vector(x, y, z))
        r__ = r
        c = Part.makeBox(lx - 2 * r__, ly - 2 * r__, lz, FreeCAD.Vector(x + r__, y + r__, z))
        b = Part.makeBox(lx - 2 * r__, r__, lz, FreeCAD.Vector(x + r__, y, z))
        t = Part.makeBox(lx - 2 * r__, r__, lz, FreeCAD.Vector(x + r__, y + ly - r__, z))
        l = Part.makeBox(r__, ly - 2 * r__, lz, FreeCAD.Vector(x, y + r__, z))
        R = Part.makeBox(r__, ly - 2 * r__, lz, FreeCAD.Vector(x + lx - r__, y + r__, z))
        c1 = Part.makeCylinder(r__, lz, FreeCAD.Vector(x + r__, y + r__, z))
        c2 = Part.makeCylinder(r__, lz, FreeCAD.Vector(x + lx - r__, y + r__, z))
        c3 = Part.makeCylinder(r__, lz, FreeCAD.Vector(x + r__, y + ly - r__, z))
        c4 = Part.makeCylinder(r__, lz, FreeCAD.Vector(x + lx - r__, y + ly - r__, z))
        parts = [c, b, t, l, R, c1, c2, c3, c4]
        result = parts[0]
        for s in parts[1:]:
            result = result.fuse(s)
        return result
    @staticmethod
    def rslot(lx, ly, r, depth, x=0, y=0, z=0):
        r = min(r, lx / 2 - 0.05, ly / 2 - 0.05)
        if r <= 0:
            return Part.makeBox(lx, ly, depth, FreeCAD.Vector(x, y, z))
        r__ = r
        c = Part.makeBox(lx - 2 * r__, ly - 2 * r__, depth, FreeCAD.Vector(x + r__, y + r__, z))
        b = Part.makeBox(lx - 2 * r__, r__, depth, FreeCAD.Vector(x + r__, y, z))
        t = Part.makeBox(lx - 2 * r__, r__, depth, FreeCAD.Vector(x + r__, y + ly - r__, z))
        l = Part.makeBox(r__, ly - 2 * r__, depth, FreeCAD.Vector(x, y + r__, z))
        R = Part.makeBox(r__, ly - 2 * r__, depth, FreeCAD.Vector(x + lx - r__, y + r__, z))
        c1 = Part.makeCylinder(r__, depth, FreeCAD.Vector(x + r__, y + r__, z))
        c2 = Part.makeCylinder(r__, depth, FreeCAD.Vector(x + lx - r__, y + r__, z))
        c3 = Part.makeCylinder(r__, depth, FreeCAD.Vector(x + r__, y + ly - r__, z))
        c4 = Part.makeCylinder(r__, depth, FreeCAD.Vector(x + lx - r__, y + ly - r__, z))
        result = c.fuse(b)
        for s in [t, l, R, c1, c2, c3, c4]:
            result = result.fuse(s)
        return result
    @staticmethod
    def rotbox(lx, ly, lz, deg, cx, cy, z):
        b = Part.makeBox(lx, ly, lz, FreeCAD.Vector(-lx / 2, -ly / 2, 0))
        b.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), deg)
        b.translate(FreeCAD.Vector(cx, cy, z))
        return b
    def add_snap_fits(self, count=4, snap_width=6.0, snap_depth=3.0, snap_height=2.0):
        if self.base_shape is None:
            raise RuntimeError('Call create_base_shell first')
        p = self._params
        wall_t = p['wall_t']
        outer_w = p['outer_w']
        outer_d = p['outer_d']
        outer_h = p['outer_h']
        margin = p['margin']
        snap_z = outer_h - snap_height * 2
        half = count // 2
        snaps = []
        y0 = margin + wall_t
        y1 = outer_d - margin - wall_t
        usable_y = y1 - y0
        for i in range(half):
            y_pos = y0 + usable_y * (i + 1) / (half + 1) - snap_width / 2
            snap = Part.makeBox(snap_depth, snap_width, snap_height, FreeCAD.Vector(0, y_pos, snap_z))
            snaps.append(snap)
        for i in range(count - half):
            y_pos = y0 + usable_y * (i + 1) / (count - half + 1) - snap_width / 2
            snap = Part.makeBox(snap_depth, snap_width, snap_height, FreeCAD.Vector(outer_w - snap_depth, y_pos, snap_z))
            snaps.append(snap)
        for snap in snaps:
            self.base_shape = self.base_shape.fuse(snap)
        self._add_to_doc('BaseWithSnaps', self.base_shape)
        return self.base_shape
    def add_ventilation(self, slot_count=3, slot_width=3.0, slot_length=15.0, slot_spacing=6.0):
        if self.base_shape is None:
            raise RuntimeError('Call create_base_shell first')
        p = self._params
        wall_t = p['wall_t']
        outer_w = p['outer_w']
        outer_d = p['outer_d']
        outer_h = p['outer_h']
        margin = p['margin']
        depth_cut = wall_t + 1.0
        slot_z = outer_h * 0.55
        cuts = []
        usable_w = outer_w - 2 * (margin + wall_t)
        usable_d = outer_d - 2 * (margin + wall_t)
        start_x = margin + wall_t + slot_spacing
        start_y = margin + wall_t + slot_spacing
        for side_x in [-0.1, outer_w - depth_cut + 0.1]:
            for i in range(slot_count):
                y_pos = start_y + usable_d * i / max(slot_count - 1, 1) - slot_length / 2
                slot = Part.makeBox(depth_cut, max(slot_length, 4.0), max(slot_width, 2.0), FreeCAD.Vector(side_x, y_pos, slot_z))
                cuts.append(slot)
        for side_y in [-0.1, outer_d - depth_cut + 0.1]:
            for i in range(slot_count):
                x_pos = start_x + usable_w * i / max(slot_count - 1, 1) - slot_length / 2
                slot = Part.makeBox(max(slot_length, 4.0), depth_cut, max(slot_width, 2.0), FreeCAD.Vector(x_pos, side_y, slot_z))
                cuts.append(slot)
        for cut in cuts:
            self.base_shape = self.base_shape.cut(cut)
        self._add_to_doc('BaseWithVents', self.base_shape)
        return self.base_shape
    def place_board_visual(self, board_data):
        if not isinstance(board_data, dict):
            raise TypeError(f'board_data must be dict, got {type(board_data)}')
        if 'dimensions' not in board_data:
            w = board_data.get('width') or board_data.get('board_width') or 100.0
            h = board_data.get('height') or board_data.get('board_height') or 60.0
            board_data = {'dimensions': {'width': float(w), 'height': float(h), 'x_min': 0.0, 'y_min': 0.0, 'x_max': float(w), 'y_max': float(h)}}
        dims = board_data['dimensions']
        bw = dims['width']
        bd = dims['height']
        p = self._params
        wall_t = p['wall_t']
        floor_t = p['floor_t']
        margin = p['margin']
        board_x = wall_t + margin
        board_y = wall_t + margin
        board_z = floor_t + 1.0
        board_shape = Part.makeBox(bw, bd, 1.6, FreeCAD.Vector(board_x, board_y, board_z))
        obj = self.doc.addObject('Part::Feature', 'PCB_Board')
        obj.Shape = board_shape
        obj.Label = 'PCB Board'
        self.doc.recompute()
        if hasattr(obj, 'ViewObject') and obj.ViewObject:
            try:
                obj.ViewObject.ShapeColor = (0.2, 0.8, 0.2)
                obj.ViewObject.Transparency = 60
            except Exception:
                pass
        return obj
    def add_side_cutouts(self, cutouts, wall_t=None):
        if self.base_shape is None:
            raise RuntimeError('Call create_base_shell first')
        p = self._params
        wt = wall_t or p['wall_t']
        floor_t = p['floor_t']
        outer_w = p['outer_w']
        outer_d = p['outer_d']
        depth_wall = wt + 1
        for c in cutouts:
            side = c.get('side', '').lower()
            x = c['x']
            z = c.get('z', 0)
            cw = c['w']
            ch = c['h']
            if side == 'front':
                cut = Part.makeBox(cw, depth_wall, ch, FreeCAD.Vector(x - cw / 2, -0.1, floor_t + z))
            elif side == 'back':
                cut = Part.makeBox(cw, depth_wall, ch, FreeCAD.Vector(x - cw / 2, outer_d - depth_wall + 0.1, floor_t + z))
            elif side == 'left':
                cut = Part.makeBox(depth_wall, cw, ch, FreeCAD.Vector(-0.1, x - cw / 2, floor_t + z))
            elif side == 'right':
                cut = Part.makeBox(depth_wall, cw, ch, FreeCAD.Vector(outer_w - depth_wall + 0.1, x - cw / 2, floor_t + z))
            else:
                continue
            self.base_shape = self.base_shape.cut(cut)
        self._add_to_doc('BaseWithCutouts', self.base_shape)
        return self.base_shape
    def _add_to_doc(self, label, shape):
        obj = self.doc.addObject('Part::Feature', label)
        obj.Shape = shape
        self.doc.recompute()
        return obj
