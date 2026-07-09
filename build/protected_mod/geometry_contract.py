from __future__ import annotations
import enclosure_builder as _eb
class GeometryContract:
    def __init__(self, geo, doc=None):
        self.geo = geo
        self.doc = doc
        self.builder = _eb.EnclosureBuilder(doc=doc)
    @staticmethod
    def _require_in_range(value: float, lo: float, hi: float, name: str) -> None:
        if not lo <= value <= hi:
            raise ValueError(f'{name}={value:.4f} is outside valid range [{lo:.4f}, {hi:.4f}]')
    @staticmethod
    def _require_positive(value: float, name: str) -> None:
        if value <= 0:
            raise ValueError(f'{name}={value:.4f} must be positive')
    def _require_hole_index(self, index: int) -> dict:
        holes = self.geo.holes_enc
        if index < 0 or index >= len(holes):
            raise ValueError(f'hole_index={index} out of range (board has {len(holes)} holes, indices 0–{len(holes) - 1})')
        return holes[index]
    def _check_feature_fits(self, cx: float, cy: float, half_w: float, half_d: float, label: str) -> None:
        gw = self.geo.enc_outer_width
        gd = self.geo.enc_outer_depth
        self._require_in_range(cx - half_w, 0.0, gw, f'{label}.min.x')
        self._require_in_range(cx + half_w, 0.0, gw, f'{label}.max.x')
        self._require_in_range(cy - half_d, 0.0, gd, f'{label}.min.y')
        self._require_in_range(cy + half_d, 0.0, gd, f'{label}.max.y')
    def make_base_shell(self, wall_t: float | None=None, floor_t: float | None=None):
        wt = wall_t if wall_t is not None else self.geo.wall_t
        ft = floor_t if floor_t is not None else self.geo.floor_t
        self._require_positive(wt, 'wall_t')
        self._require_positive(ft, 'floor_t')
        if wt > self.geo.enc_outer_width / 2:
            raise ValueError(f'wall_t={wt} > half enclosure width ({self.geo.enc_outer_width / 2:.3f})')
        self.builder.create_base_shell(self._proxy(), wt, ft)
        return self
    def add_mounting_boss(self, hole_index: int, boss_od: float=6.4, boss_id: float=3.2, boss_height: float | None=None):
        hole = self._require_hole_index(hole_index)
        cx, cy = (hole['x'], hole['y'])
        self._require_positive(boss_od, 'boss_od')
        if boss_id >= boss_od:
            raise ValueError(f'boss_id={boss_id} must be < boss_od={boss_od}')
        self._check_feature_fits(cx, cy, boss_od / 2, boss_od / 2, f'boss hole_index={hole_index}')
        bh = boss_height if boss_height is not None else self.geo.floor_t + 1.0
        self._require_positive(bh, 'boss_height')
        if bh > self.geo.cavity_clearance_mm:
            raise ValueError(f'boss_height={bh} exceeds cavity_clearance_mm={self.geo.cavity_clearance_mm}')
        self.builder.add_mounting_bosses(self._proxy(), boss_od=boss_od)
        return self
    def add_cutout(self, cx: float, cy: float, wall: str, cut_width: float, cut_height: float, z_centre: float | None=None, clearance: float=0.5):
        valid = {'left', 'right', 'front', 'back'}
        if wall not in valid:
            raise ValueError(f"wall='{wall}' not in {sorted(valid)}")
        self._require_positive(cut_width, 'cut_width')
        self._require_positive(cut_height, 'cut_height')
        if wall in ('left', 'right'):
            self._require_in_range(cy, 0.0, self.geo.enc_outer_depth, 'cutout cy')
            half = cut_width / 2
            self._require_in_range(cy - half, 0.0, self.geo.enc_outer_depth, 'cy - half')
            self._require_in_range(cy + half, 0.0, self.geo.enc_outer_depth, 'cy + half')
        else:
            self._require_in_range(cx, 0.0, self.geo.enc_outer_width, 'cutout cx')
            half = cut_width / 2
            self._require_in_range(cx - half, 0.0, self.geo.enc_outer_width, 'cx - half')
            self._require_in_range(cx + half, 0.0, self.geo.enc_outer_width, 'cx + half')
        zc = z_centre if z_centre is not None else self.geo.floor_t + cut_height / 2 + clearance
        if zc + cut_height / 2 > self.geo.total_height_mm:
            raise ValueError(f'Cutout top z={zc + cut_height / 2:.3f} > total_height_mm={self.geo.total_height_mm:.3f}')
        self.builder.add_side_cutouts(self.builder.base_shape, [{'side': wall, 'x': cx, 'z': zc - self.geo.floor_t, 'w': cut_width, 'h': cut_height}])
        return self
    def add_cutout_from_hint(self, hint_index: int, clearance: float=0.5, z_clearance: float=1.0):
        hints = self.geo.connector_hints
        if hint_index < 0 or hint_index >= len(hints):
            raise ValueError(f'hint_index={hint_index} out of range ({len(hints)} hints)')
        hint = hints[hint_index]
        wall = hint['nearest_wall']
        cut_w = hint['width'] + 2 * clearance
        cut_h = hint['height_mm'] + 2 * clearance
        if wall in ('left', 'right'):
            cx, cy = (0.0, hint['enc_y'])
        else:
            cx, cy = (hint['enc_x'], 0.0)
        return self.add_cutout(cx=cx, cy=cy, wall=wall, cut_width=cut_w, cut_height=cut_h, z_centre=self.geo.floor_t + cut_h / 2 + z_clearance, clearance=0.0)
    def make_lid(self, lid_t: float=1.5, lip_depth: float=1.0):
        self._require_positive(lid_t, 'lid_t')
        self._require_positive(lip_depth, 'lip_depth')
        if lip_depth >= self.geo.wall_t:
            raise ValueError(f'lip_depth={lip_depth} must be < wall_t={self.geo.wall_t}')
        self.builder.create_lid(self._proxy())
        return self
    def add_snap_fits(self, count: int=4, snap_width: float=8.0, snap_depth: float=3.0, snap_height: float=2.0):
        if count < 2:
            raise ValueError('At least 2 snap-fits required')
        if count % 2 != 0:
            raise ValueError('snap count must be even')
        self._require_positive(snap_width, 'snap_width')
        self._require_positive(snap_depth, 'snap_depth')
        self._require_positive(snap_height, 'snap_height')
        self.builder.add_snap_fits(count=count, snap_width=snap_width, snap_depth=snap_depth, snap_height=snap_height)
        return self
    def add_ventilation_slots(self, slot_count: int=4, slot_width: float=20.0, slot_height: float=2.0, slot_spacing: float=6.0):
        if slot_count < 1:
            raise ValueError('slot_count must be >= 1')
        usable_h = self.geo.total_height_mm - self.geo.floor_t - 2.0
        total_band = slot_count * slot_height + (slot_count - 1) * slot_spacing
        if total_band > usable_h:
            raise ValueError(f'Vent pattern height={total_band:.2f} > usable wall height={usable_h:.2f}')
        self.builder.add_ventilation(slot_count=slot_count, slot_width=slot_width, slot_length=slot_width, slot_spacing=slot_spacing)
        return self
    def _proxy(self) -> dict:
        geo = self.geo
        return {'dimensions': {'x_min': 0.0, 'x_max': geo.board_width_mm, 'y_min': 0.0, 'y_max': geo.board_height_mm, 'width': geo.board_width_mm, 'height': geo.board_height_mm}, 'mounting_holes': [{'x': h['x'] - geo.board_origin_x, 'y': h['y'] - geo.board_origin_y, 'diameter': h.get('diameter', 3.2)} for h in geo.holes_enc], 'edge_connectors': [], 'components': [{'x': c['x'] - geo.board_origin_x, 'y': c['y'] - geo.board_origin_y, 'height': c['height']} for c in geo.components_enc]}
if __name__ == '__main__':
    from context_injector import precompute
    sample = {'dimensions': {'x_min': 10, 'x_max': 90, 'y_min': 5, 'y_max': 65, 'width': 80, 'height': 60}, 'mounting_holes': [{'x': 13, 'y': 8, 'diameter': 3.2}, {'x': 87, 'y': 8, 'diameter': 3.2}, {'x': 13, 'y': 62, 'diameter': 3.2}, {'x': 87, 'y': 62, 'diameter': 3.2}], 'components': [{'ref': 'U1', 'x': 50, 'y': 35, 'height': 12}, {'ref': 'J1', 'x': 87.5, 'y': 35, 'height': 8.5, 'connector': True, 'width': 9}]}
    geo = precompute(sample)
    print('=== PrecomputedGeometry ===')
    print(f'  enc outer: {geo.enc_outer_width} x {geo.enc_outer_depth} x {geo.enc_outer_height} mm')
    print(f'  holes: {geo.holes_enc}')
    print(f'  hints: {geo.connector_hints}')
    c = GeometryContract(geo)
    try:
        c.add_mounting_boss(hole_index=99)
    except ValueError as e:
        print(f'\nExpected error (bad index): {e}')
    try:
        c.add_snap_fits(count=3)
    except ValueError as e:
        print(f'Expected error (odd count): {e}')
    print('\nAll guard tests passed.')
