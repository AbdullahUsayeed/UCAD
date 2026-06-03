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
}

CONNECTOR_KEYWORDS = ["USB", "HDMI", "RJ45", "Audio", "Terminal", "Connector",
                       "Ethernet", "DSUB", "SIM", "SD", "microSD", "Header",
                       "PinHeader", "Socket", "Barrel_Jack", "DC",
                       "Button", "SW_", "Switch"]


def _get_height(name):
    name_upper = name.upper()
    for key, h in FOOTPRINT_HEIGHTS.items():
        if key.upper() in name_upper:
            return h
    # SMD passives: extract metric size code like _0402, _0603, etc
    smd = {"0201": 0.3, "0402": 0.5, "0603": 0.8, "0805": 1.3,
           "1005": 3.5, "1206": 1.8, "1210": 2.5, "1806": 2.0,
           "1812": 2.5, "2012": 1.5, "2512": 2.0, "3216": 1.8}
    m = re.search(r"_(\d{4})", name)
    if m:
        code = m.group(1)
        if code in smd:
            return smd[code]
    return 10.0


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
        r'\(gr_line[^)]*\(start\s+([\d.-]+)\s+([\d.-]+)\)[^)]*\(end\s+([\d.-]+)\s+([\d.-]+)\)[^)]*\(layer\s+"Edge\.Cuts"\)',
        content,
    ):
        xs.extend([float(m.group(1)), float(m.group(3))])
        ys.extend([float(m.group(2)), float(m.group(4))])

    for m in re.finditer(
        r'\(gr_arc[^)]*\(start\s+([\d.-]+)\s+([\d.-]+)\)[^)]*\(mid\s+[\d.-]+\s+[\d.-]+\)[^)]*\(end\s+([\d.-]+)\s+([\d.-]+)\)[^)]*\(layer\s+"Edge\.Cuts"\)',
        content,
    ):
        xs.extend([float(m.group(1)), float(m.group(3))])
        ys.extend([float(m.group(2)), float(m.group(4))])

    for m in re.finditer(
        r'\(gr_rect[^)]*\(start\s+([\d.-]+)\s+([\d.-]+)\)',
        content,
    ):
        rest = content[m.end() : m.end() + 200]
        end_m = re.search(r'\(end\s+([\d.-]+)\s+([\d.-]+)\)', rest)
        layer_m = re.search(r'\(layer\s+"Edge\.Cuts"\)', rest)
        if end_m and layer_m:
            xs.extend([float(m.group(1)), float(end_m.group(1))])
            ys.extend([float(m.group(2)), float(end_m.group(2))])

    if not xs:
        return {"width": 100.0, "height": 60.0}

    x_vals = [x for x in xs if not math.isnan(x) and not math.isinf(x)]
    y_vals = [y for y in ys if not math.isnan(y) and not math.isinf(y)]

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

    for m in re.finditer(
        r'\(footprint\s+"([^"]*MountingHole[^"]*)"',
        content,
    ):
        name = m.group(1)
        # Find 'at' near this footprint
        chunk = content[m.start() : m.start() + 500]
        at_m = re.search(r'\(at\s+([\d.-]+)\s+([\d.-]+)', chunk)
        if not at_m:
            continue
        x = round(float(at_m.group(1)), 2)
        y = round(float(at_m.group(2)), 2)
        if (x, y) in seen:
            continue
        seen.add((x, y))
        dia = _extract_hole_diameter(name, chunk)
        holes.append({"x": x, "y": y, "diameter": dia, "name": name})

    # np_thru_hole pads that aren't MountingHole footprints
    fp_iter = re.finditer(
        r'\(footprint\s+"([^"]*)"',
        content,
    )
    for m in fp_iter:
        if "MountingHole" in m.group(1):
            continue
        chunk = content[m.start() : m.start() + 1000]
        at_m = re.search(r'\(at\s+([\d.-]+)\s+([\d.-]+)', chunk)
        if not at_m:
            continue
        x = round(float(at_m.group(1)), 2)
        y = round(float(at_m.group(2)), 2)
        if (x, y) in seen:
            continue
        pad_m = re.search(r'\(pad\s+"[^"]*"\s+np_thru_hole\s+circle[^)]*\(drill\s+([\d.-]+)\)', chunk)
        if pad_m:
            drill = round(float(pad_m.group(1)), 2)
            seen.add((x, y))
            holes.append({"x": x, "y": y, "diameter": drill, "name": m.group(1)})

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

    fp_iter = re.finditer(r'\(footprint\s+"([^"]*)"', content)
    for m in fp_iter:
        name = m.group(1)
        if "MountingHole" in name:
            continue

        chunk = content[m.start() : m.start() + 800]
        at_m = re.search(r'\(at\s+([\d.-]+)\s+([\d.-]+)\s*([\d.-]*)', chunk)
        if not at_m:
            continue

        x = round(float(at_m.group(1)), 2)
        y = round(float(at_m.group(2)), 2)
        rotation = round(float(at_m.group(3))) if at_m.group(3).strip() else 0
        ref = _extract_reference(chunk)
        height = _get_height(name)

        comp = {
            "ref": ref,
            "name": name,
            "x": x,
            "y": y,
            "rotation": rotation,
            "height": height,
            "near_edge": False,
        }

        if has_edge:
            dist = min(abs(x - x_min), abs(x - x_max), abs(y - y_min), abs(y - y_max))
            comp["near_edge"] = dist < 3.0

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
    for c in components:
        is_near = c.get("near_edge", False)
        is_connector = any(kw.lower() in c["name"].lower() for kw in CONNECTOR_KEYWORDS)
        is_tall = c["height"] >= 2.0
        if is_near and (is_connector or is_tall):
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
    import sys
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
                print(f"  {c['ref']}: {c['name'][:50]} at ({c['x']},{c['y']}) h={c['height']}mm{edge}")
            print(f"Edge connectors: {len(data['edge_connectors'])}")
            for c in data["edge_connectors"]:
                print(f"  {c['ref']}: {c['name'][:50]} at ({c['x']},{c['y']}) h={c['height']}mm")
        except Exception as e:
            import traceback
            print(f"Error parsing {fp}: {e}")
            traceback.print_exc()
