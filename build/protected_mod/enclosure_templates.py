import FreeCAD
from enclosure_builder import EnclosureBuilder
def _normalize_board_data(board_data):
    if not isinstance(board_data, dict):
        print(f'[PCB Template] input type: {type(board_data)}')
        raise TypeError(f'board_data must be dict, got {type(board_data).__name__}')
    print(f'[PCB Template] input keys: {list(board_data.keys())}')
    if 'dimensions' in board_data:
        print('[PCB Template]   -> already normalized, returning as-is')
        return board_data
    w = board_data.get('width') or board_data.get('board_width') or board_data.get('length') or board_data.get('board_length') or 100.0
    h = board_data.get('height') or board_data.get('board_height') or board_data.get('depth') or board_data.get('board_depth') or 60.0
    x0 = board_data.get('x_min', 0.0)
    y0 = board_data.get('y_min', 0.0)
    x1 = board_data.get('x_max', x0 + w)
    y1 = board_data.get('y_max', y0 + h)
    return {'dimensions': {'width': float(w), 'height': float(h), 'x_min': float(x0), 'y_min': float(y0), 'x_max': float(x1), 'y_max': float(y1)}, 'mounting_holes': board_data.get('mounting_holes', []), 'components': board_data.get('components', []), 'edge_connectors': board_data.get('edge_connectors', board_data.get('connectors', []))}
def build_enclosure(board_data, wall_thickness=2.5, floor_thickness=2.0, boss_od=6.0, screw_size='M3', standoff_height=None, clearance=0.5, margin=2.0, headroom_mm=2.0, lid_thickness=2.0, snap_count=4, vent_slots=3, boss_indices=None, connector_hint_indices=None):
    print('[PCB Template] ENTER build_enclosure')
    try:
        board_data = _normalize_board_data(board_data)
        print(f'[PCB Template] normalized board_data keys: {list(board_data.keys())}')
        doc = FreeCAD.ActiveDocument
        if doc is None:
            doc = FreeCAD.newDocument('Enclosure')
        builder = EnclosureBuilder(doc=doc)
        builder.create_base_shell(board_data, wall_t=wall_thickness, floor_t=floor_thickness, margin=margin)
        builder.place_board_visual(board_data)
        builder.add_mounting_bosses(board_data, boss_od=boss_od, screw_size=screw_size, standoff_height=standoff_height)
        builder.add_connector_cutouts(board_data, clearance=clearance)
        if snap_count > 0:
            builder.add_snap_fits(count=snap_count)
        if vent_slots > 0:
            builder.add_ventilation(slot_count=vent_slots)
        builder.create_lid(board_data, lid_t=lid_thickness)
        return (True, 'Enclosure generated successfully.', builder)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return (False, f'Enclosure template failed: {type(e).__name__}: {e}', None)
def build_enclosure_from_params(board_data, params):
    print('[PCB Template] ENTER build_enclosure_from_params')
    print(f'[PCB Template]   board_data type: {type(board_data)}')
    if isinstance(board_data, dict):
        print(f'[PCB Template]   board_data keys: {list(board_data.keys())}')
    print(f'[PCB Template]   params: {params}')
    wall_t = params.get('wall_thickness') or params.get('wall_t') or 2.5
    floor_t = params.get('floor_thickness') or params.get('floor_t') or 2.0
    boss_od = params.get('boss_od') or params.get('boss_diameter') or 6.0
    screw_size = params.get('screw_size') or params.get('screw') or 'M3'
    standoff_height = params.get('standoff_height') or params.get('standoff')
    clearance = params.get('clearance') or params.get('lid_clearance') or params.get('connector_clearance') or 0.5
    margin = params.get('margin') or 2.0
    headroom_mm = params.get('headroom_mm') or 2.0
    lid_t = params.get('lid_thickness') or params.get('lid_t') or 2.0
    snap_count = params.get('snap_count')
    if snap_count is None:
        snap_count = params.get('snap_fit_count')
    if snap_count is None:
        snap_count = 4
    vent_slots = params.get('vent_slots')
    if vent_slots is None:
        vent_slots = params.get('ventilation_slots_count')
    if vent_slots is None:
        if params.get('ventilation') is False:
            vent_slots = 0
        else:
            vent_slots = 3
    boss_indices = params.get('boss_indices')
    connector_hint_indices = params.get('connector_hint_indices')
    return build_enclosure(board_data, wall_thickness=float(wall_t), floor_thickness=float(floor_t), boss_od=float(boss_od), screw_size=screw_size, standoff_height=float(standoff_height) if standoff_height else None, clearance=float(clearance), margin=float(margin), headroom_mm=float(headroom_mm), lid_thickness=float(lid_t), snap_count=int(snap_count), vent_slots=int(vent_slots), boss_indices=boss_indices, connector_hint_indices=connector_hint_indices)
def refine_enclosure(board_data, instruction, builder=None):
    import re
    params = {}
    wall_match = re.search('wall(?:\\s+thickness)?\\s*(?:=|is|to|:)?\\s*(\\d+\\.?\\d*)', instruction, re.IGNORECASE)
    if wall_match:
        params['wall_thickness'] = float(wall_match.group(1))
    boss_match = re.search('boss\\s*(?:od|diameter|size)?\\s*(?:=|is|to|:)?\\s*(\\d+\\.?\\d*)', instruction, re.IGNORECASE)
    if boss_match:
        params['boss_od'] = float(boss_match.group(1))
    vent_match = re.search('vent\\w*\\s*(?:count|number|slots)?\\s*(?:=|is|to|:)?\\s*(\\d+)', instruction, re.IGNORECASE)
    if vent_match:
        params['vent_slots'] = int(vent_match.group(1))
    snap_match = re.search('snap\\w*\\s*(?:count|number)?\\s*(?:=|is|to|:)?\\s*(\\d+)', instruction, re.IGNORECASE)
    if snap_match:
        params['snap_count'] = int(snap_match.group(1))
    return build_enclosure_from_params(board_data, params)
_BUILD_ENCLOSURE_CODE = 'import FreeCAD\nfrom enclosure_templates import build_enclosure_from_params\nsuccess, msg, builder = build_enclosure_from_params(board_data, __PARAMS__)\nif not success:\n    raise RuntimeError(msg)\n'.strip()
