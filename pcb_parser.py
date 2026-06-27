import re
import math

FOOTPRINT_HEIGHTS = {
    "USB_C_Receptacle": 3.5,
    "USB_Micro": 3.0,
    "USB_A": 8.0,
    "HDMI": 6.0,
    "RJ45": 14.0,
    "Audio_Jack": 12.0,
    "TerminalBlock": 12.0,
    "MountingHole": 0.0,
    "Battery": 5.0,
    "QFN": 2.0,
    "QFP": 3.5,
    "BGA": 2.5,
    "SOT23": 1.5,
    "SOT223": 3.0,
    "SOIC": 3.5,
    "SO8": 3.0,
    "D_PAK": 4.5,
    "TO_220": 16.0,
    "Button": 4.0,
    "SW_Push": 4.0,
    "LED": 2.0,
    "Relay": 15.0,
    "Fuse": 10.0,
    "Diode": 2.0,
    "Crystal": 2.0,
    "Oscillator": 2.5,
}

CONNECTOR_KEYWORDS = ["USB", "HDMI", "RJ45", "Audio", "Terminal", "Connector",
                       "Ethernet", "DSUB", "SIM", "SD", "microSD", "Header",
                       "PinHeader", "Socket", "Barrel_Jack", "DC",
                       "Button", "SW_", "Switch"]

# Larger SMD codes for connector-like parts (e.g., _1005 is actually 1005)
SMD_HEIGHTS = {"0201": 0.3, "0402": 0.5, "0603": 0.8, "0805": 1.3,
               "1005": 3.5, "1206": 1.8, "1210": 2.5, "1806": 2.0,
               "1812": 2.5, "2012": 1.5, "2512": 2.0, "3216": 1.8}

# Matches a balanced ( ... ) block starting at a given position
def _balanced_block(content, start):
    if content[start] != '(':
        return content[start:start + 3000]
    depth = 0
    i = start
    n = min(len(content), start + 12000)
    while i < n:
        ch = content[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return content[start:i + 1]
        elif ch == '"':
            i += 1
            while i < n and content[i] != '"':
                if content[i] == '\\':
                    i += 1
                i += 1
        i += 1
    return content[start:start + 3000]


def _get_height(name):
    name_upper = name.upper()
    for key, h in FOOTPRINT_HEIGHTS.items():
        if key.upper() in name_upper:
            return h
    m = re.search(r"_(\d{4})", name)
    if m:
        code = m.group(1)
        if code in SMD_HEIGHTS:
            return SMD_HEIGHTS[code]
    return 10.0


def _is_connector_footprint(name):
    name_lower = name.lower()
    return any(kw.lower() in name_lower for kw in CONNECTOR_KEYWORDS)


def _parse_footprint_dimensions(block):
    """Extract the footprint's pad bounding box to estimate width/length.
    
    Returns (width_mm, length_mm) or (None, None) if no pads found.
    """
    pad_xs = []
    pad_ys = []
    for pad_m in re.finditer(r'\(pad\s+"[^"]*"\s+\S+\s+\S+\s+\(at\s+([\d.-]+)\s+([\d.-]+)', block):
        px = float(pad_m.group(1))
        py = float(pad_m.group(2))
        pad_xs.append(px)
        pad_ys.append(py)
    if not pad_xs:
        return None, None
    w = round(max(pad_xs) - min(pad_xs), 2)
    h = round(max(pad_ys) - min(pad_ys), 2)
    return max(w, 2.0), max(h, 2.0)


def parse(filepath):
    with open(filepath, encoding="utf-8", errors="replace") as f:
        content = f.read()

    dimensions = _get_board_dimensions(content)
    holes = _get_mounting_holes(content)
    components = _get_components(content, dimensions)
    connectors = _get_edge_connectors(components, dimensions)

    return {
        "dimensions": dimensions,
        "mounting_holes": holes,
        "components": components,
        "edge_connectors": connectors,
    }


def _get_board_dimensions(content):
    xs, ys = [], []

    for m in re.finditer(
        r'\(gr_line[^)]*\(start\s+([\d.-]+)\s+([\d.-]+)\)',
        content,
    ):
        chunk = content[m.start(): m.start() + 1000]
        end_m = re.search(r'\(end\s+([\d.-]+)\s+([\d.-]+)\)', chunk)
        layer_m = re.search(r'\(layer\s+"?Edge\.Cuts"?\)', chunk)
        if end_m and layer_m:
            xs.extend([float(m.group(1)), float(end_m.group(1))])
            ys.extend([float(m.group(2)), float(end_m.group(2))])

    for m in re.finditer(
        r'\(gr_arc[^)]*\(start\s+([\d.-]+)\s+([\d.-]+)\)',
        content,
    ):
        chunk = content[m.start(): m.start() + 1000]
        end_m = re.search(r'\(end\s+([\d.-]+)\s+([\d.-]+)\)', chunk)
        layer_m = re.search(r'\(layer\s+"?Edge\.Cuts"?\)', chunk)
        if end_m and layer_m:
            xs.extend([float(m.group(1)), float(end_m.group(1))])
            ys.extend([float(m.group(2)), float(end_m.group(2))])

    for m in re.finditer(
        r'\(gr_rect[^)]*\(start\s+([\d.-]+)\s+([\d.-]+)\)',
        content,
    ):
        chunk = content[m.start(): m.start() + 1000]
        end_m = re.search(r'\(end\s+([\d.-]+)\s+([\d.-]+)\)', chunk)
        layer_m = re.search(r'\(layer\s+"?Edge\.Cuts"?\)', chunk)
        if end_m and layer_m:
            xs.extend([float(m.group(1)), float(end_m.group(1))])
            ys.extend([float(m.group(2)), float(end_m.group(2))])

    if not xs:
        print("[PCB Parser] No Edge.Cuts geometry found, using defaults")
        return {"width": 100.0, "height": 60.0, "x_min": 0.0, "y_min": 0.0, "x_max": 100.0, "y_max": 60.0}

    x_vals = [x for x in xs if not math.isnan(x) and not math.isinf(x)]
    y_vals = [y for y in ys if not math.isnan(y) and not math.isinf(y)]

    print(f"[PCB Parser] Found outline bounds: x=({min(x_vals)}, {max(x_vals)}), y=({min(y_vals)}, {max(y_vals)})")

    return {
        "width": round(max(x_vals) - min(x_vals), 2),
        "height": round(max(y_vals) - min(y_vals), 2),
        "x_min": round(min(x_vals), 2),
        "y_min": round(min(y_vals), 2),
        "x_max": round(max(x_vals), 2),
        "y_max": round(max(y_vals), 2),
    }


def _get_mounting_holes(content):
    holes = []
    seen = set()
    # KiCad v7+ uses (footprint ...), v6 uses (module ...)
    fp_pat = r'\((?:footprint|module)\s+(?:"([^"]*)"|([^\s(")]+))'

    for m in re.finditer(fp_pat, content):
        name = m.group(1) or m.group(2)
        if "MountingHole" not in name:
            continue
        block = _balanced_block(content, m.start())
        at_m = re.search(r'\(at\s+([\d.-]+)\s+([\d.-]+)', block)
        if not at_m:
            continue
        x = round(float(at_m.group(1)), 2)
        y = round(float(at_m.group(2)), 2)
        if (x, y) in seen:
            continue
        seen.add((x, y))
        dia = _extract_hole_diameter(name, block)
        holes.append({"x": x, "y": y, "diameter": dia, "name": name})

    # np_thru_hole pads in non-MountingHole footprints — include only
    # when the footprint has no signal pads (smd/thru_hole), which indicates
    # the np_thru_holes are board-mount holes rather than component posts.
    for m in re.finditer(fp_pat, content):
        name = m.group(1) or m.group(2)
        if "MountingHole" in name:
            continue
        block = _balanced_block(content, m.start())
        at_m = re.search(r'\(at\s+([\d.-]+)\s+([\d.-]+)', block)
        if not at_m:
            continue
        x = round(float(at_m.group(1)), 2)
        y = round(float(at_m.group(2)), 2)
        if (x, y) in seen:
            continue
        # Skip footprints with signal pads (smd, thru_hole) — these are
        # component mounting posts, not board mounting holes.
        if re.search(r'\(pad\s+"[^"]*"\s+(?:smd|thru_hole)\s', block):
            continue
        # Find np_thru_hole pads with a drill hole
        pad_start = re.search(r'\(pad\s+"[^"]*"\s+np_thru_hole\s+circle', block)
        if not pad_start:
            continue
        pad_block = _balanced_block(block, pad_start.start())
        dm = re.search(r'\(drill\s+([\d.-]+)\)', pad_block)
        if dm:
            drill = round(float(dm.group(1)), 2)
            seen.add((x, y))
            holes.append({"x": x, "y": y, "diameter": drill, "name": name})

    return holes


def _extract_hole_diameter(name, chunk):
    m = re.search(r"MountingHole[_\s]*([\d.]+)", name)
    if m:
        return round(float(m.group(1)), 2)
    dm = re.search(r'\(drill\s+([\d.-]+)\)', chunk)
    if dm:
        return round(float(dm.group(1)), 2)
    return 3.0


def _get_components(content, dimensions):
    components = []
    x_min = dimensions.get("x_min")
    x_max = dimensions.get("x_max")
    y_min = dimensions.get("y_min")
    y_max = dimensions.get("y_max")
    has_edge = None not in (x_min, x_max, y_min, y_max)

    # Use wider edge threshold for larger boards
    board_diag = 0
    if has_edge:
        board_diag = math.sqrt((x_max - x_min)**2 + (y_max - y_min)**2)
    edge_threshold = max(3.0, min(8.0, board_diag * 0.04))

    # KiCad v7+: (footprint ...), KiCad v6: (module ...)
    fp_pat = r'\((?:footprint|module)\s+(?:"([^"]*)"|([^\s(")]+))'
    fp_iter = re.finditer(fp_pat, content)
    for m in fp_iter:
        name = m.group(1) or m.group(2)
        if "MountingHole" in name:
            continue

        block = _balanced_block(content, m.start())
        at_m = re.search(r'\(at\s+([\d.-]+)\s+([\d.-]+)(?:\s+([\d.-]+))?', block)
        if not at_m:
            continue

        x = round(float(at_m.group(1)), 2)
        y = round(float(at_m.group(2)), 2)
        rot_str = at_m.group(3)
        rotation = round(float(rot_str)) if rot_str and rot_str.strip() else 0
        ref = _extract_reference(block)
        height = _get_height(name)

        # Extract pad bounding box for width/length estimation
        fpw, fpl = _parse_footprint_dimensions(block)

        comp = {
            "ref": ref,
            "name": name,
            "x": x,
            "y": y,
            "rotation": rotation,
            "height": height,
            "width": fpw,
            "length": fpl,
            "near_edge": False,
        }

        is_conn = _is_connector_footprint(name)
        if is_conn:
            comp["connector"] = True
        if is_conn and fpw is not None:
            comp["connector_width"] = max(fpw, fpl)

        if has_edge:
            dist_x_min = abs(x - x_min)
            dist_x_max = abs(x - x_max)
            dist_y_min = abs(y - y_min)
            dist_y_max = abs(y - y_max)
            dist = min(dist_x_min, dist_x_max, dist_y_min, dist_y_max)
            comp["near_edge"] = dist < edge_threshold
            # Store explicit face for edge connectors (reliable — no rotation guesswork)
            if comp["near_edge"]:
                edge_dists = {"W": dist_x_min, "E": dist_x_max, "S": dist_y_min, "N": dist_y_max}
                comp["face"] = min(edge_dists, key=edge_dists.get)

        components.append(comp)

    return components


def _extract_reference(chunk):
    m = re.search(r'\(fp_text\s+reference\s+"([^"]*)"', chunk)
    if m:
        return m.group(1)
    m = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', chunk)
    if m:
        return m.group(1)
    return "?"


def _get_edge_connectors(components, dimensions):
    connectors = []
    seen_refs = set()
    for c in components:
        is_near = c.get("near_edge", False)
        is_connector = _is_connector_footprint(c["name"])
        is_panel_mount = c.get("height", 0) >= 5.0 and is_connector
        if is_near and (is_connector or is_panel_mount):
            ref = c.get("ref", "?")
            if ref not in seen_refs:
                seen_refs.add(ref)
                connectors.append(c)
    return connectors


def validate_board_data(data):
    """Check parsed board data for completeness and structural validity.
    
    Returns (is_valid: bool, warnings: list[str]).
    Malformed data can produce crashes in FreeCAD — this catches issues before
    they reach the geometry pipeline.
    """
    warnings = []

    # 1. Top-level keys
    required_keys = ("dimensions", "mounting_holes", "components", "edge_connectors")
    for k in required_keys:
        if k not in data:
            warnings.append(f"Missing top-level key: '{k}' — enclosure will be empty or fallback.")

    dims = data.get("dimensions", {})

    # 2. Dimensions sub-keys
    for k in ("width", "height"):
        v = dims.get(k, 0)
        if not isinstance(v, (int, float)) or v <= 0:
            warnings.append(f"Board {k} is {v} — expected positive number. Board outline may not have been detected.")
    for k in ("x_min", "y_min", "x_max", "y_max"):
        if k not in dims:
            warnings.append(f"Missing dimension key '{k}' — board origin may be wrong.")

    # 3. Components fields
    for i, c in enumerate(data.get("components", [])):
        for f in ("ref", "name", "x", "y", "height"):
            if f not in c:
                warnings.append(f"Component #{i} missing field '{f}' — will use fallback value.")
        for f in ("width", "length"):
            if f in c and c[f] is not None and c[f] <= 0:
                warnings.append(f"Component #{i} ('{c.get('ref','?')}') has {f}={c[f]} — likely mis-parsed.")

    # 4. Mounting holes fields
    for i, h in enumerate(data.get("mounting_holes", [])):
        for f in ("x", "y", "diameter"):
            if f not in h:
                warnings.append(f"Mounting hole #{i} missing field '{f}' — hole may be placed incorrectly.")

    # 5. Warn on structural gaps
    if not data.get("components"):
        warnings.append("No components found on board — check that the file has footprint definitions.")
    if not data.get("mounting_holes"):
        warnings.append("No mounting holes found — enclosure may lack mounting features.")
    for fld in ("x_min", "x_max", "y_min", "y_max"):
        if fld in dims and dims[fld] == 0:
            warnings.append(f"Board {fld} is 0 — board may be positioned at origin unexpectedly.")

    return len(warnings) == 0, warnings


if __name__ == "__main__":
    test_files = [
        r"C:\Users\abdul\Downloads\PCB.kicad_pcb",
        r"C:\Users\abdul\Documents\PowerSupplyKit\PowerSupplyKit.kicad_pcb",
    ]
    for fp in test_files:
        try:
            data = parse(fp)
            dims = data["dimensions"]
            print(f"\n=== {fp.split(chr(92))[-1]} ===")
            print(f"Board: {dims['width']} x {dims['height']} mm")
            print(f"Mounting holes: {len(data['mounting_holes'])}")
            for h in data["mounting_holes"]:
                print(f"  Hole at ({h['x']}, {h['y']}) dia={h['diameter']}mm")
            print(f"Components: {len(data['components'])}")
            tall = sorted(data["components"], key=lambda c: c["height"], reverse=True)[:5]
            for c in tall:
                edge = " [EDGE]" if c.get("near_edge") else ""
                dims = ""
                if c.get("width") and c.get("length"):
                    dims = f" bb={c['width']}x{c['length']}mm"
                print(f"  {c['ref']}: {c['name'][:50]} at ({c['x']},{c['y']}) rot={c['rotation']}° h={c['height']}mm{dims}{edge}")
            print(f"Edge connectors: {len(data['edge_connectors'])}")
            for c in data["edge_connectors"]:
                cw = c.get("connector_width", "?")
                print(f"  {c['ref']}: {c['name'][:50]} at ({c['x']},{c['y']}) rot={c['rotation']}° h={c['height']}mm w={cw}mm")
        except Exception as e:
            import traceback
            print(f"Error parsing {fp}: {e}")
            traceback.print_exc()
