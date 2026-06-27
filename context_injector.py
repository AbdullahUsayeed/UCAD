"""
context_injector.py  (final — integrates cutout_knowledge_base)
---------------------------------------------------------------
build_ai_context(board_ctx, vision_description=None) → (sys_prompt, board_block)

Called by _on_pcb_generate() in AICompanionGui.py after the vision chain runs.
"""

from __future__ import annotations

try:
    from cutout_knowledge_base import generate_chat_prompt_appendix
    _DIMENSION_TABLE = generate_chat_prompt_appendix()
except Exception:
    _DIMENSION_TABLE = "(Dimension table unavailable — cutout_knowledge_base.py missing)"


# ── ASCII layout map ────────────────────────────────────────────────────────

def _render_pcb_layout_map(board_ctx: dict, cols: int = 40, rows: int = 20) -> str:
    dims  = board_ctx.get("dimensions", {})
    w     = dims.get("width",  1) or 1
    h     = dims.get("height", 1) or 1
    x_min = dims.get("x_min",  0)
    y_min = dims.get("y_min",  0)

    edge_refs = {e.get("ref", "") for e in board_ctx.get("edge_connectors", [])}

    grid = [["." for _ in range(cols)] for _ in range(rows)]

    def _place(px, py, ch):
        gx = int((px - x_min) / w * (cols - 1))
        gy = int((py - y_min) / h * (rows - 1))
        grid[max(0, min(rows - 1, gy))][max(0, min(cols - 1, gx))] = ch

    for hole in board_ctx.get("mounting_holes", []):
        _place(hole.get("x", 0), hole.get("y", 0), "\u2218")

    for comp in board_ctx.get("components", []):
        ref  = comp.get("ref", "?")
        ch   = ("J" if ref in edge_refs
                else ("C" if comp.get("connector") else ref[0].upper()))
        _place(comp.get("x", 0), comp.get("y", 0), ch)

    lines = ["+" + "-" * cols + "+"]
    for row in grid:
        lines.append("|" + "".join(row) + "|")
    lines.append("+" + "-" * cols + "+")
    lines.append(
        f"  PCB: {w:.1f} \u00d7 {h:.1f} mm"
        "  (\u2218=mount  J=edge connector  C=connector  letter=component)"
    )
    return "\n".join(lines)


def _board_summary(board_ctx: dict) -> str:
    dims            = board_ctx.get("dimensions", {})
    components      = board_ctx.get("components", [])
    connectors      = [c for c in components if c.get("connector")]
    edge_connectors = board_ctx.get("edge_connectors", [])
    mounting_holes  = board_ctx.get("mounting_holes", [])
    edge_refs       = {e.get("ref", "") for e in edge_connectors}
    lines = [
        f"PCB size        : {dims.get('width', 0):.1f} \u00d7 {dims.get('height', 0):.1f} mm",
        f"Mounting holes  : {len(mounting_holes)}",
        f"Connectors      : {len(connectors)} total, {len(edge_connectors)} near an edge",
        f"Other components: {len(components) - len(connectors)}",
        "",
        "COMPONENT TABLE  (ref | height | rotation | dimensions | position | notes | type)",
        "\u2500" * 65,
    ]
    for c in components:
        ref = c.get("ref", "?")
        h   = c.get("height", 0)
        rot = c.get("rotation", 0)
        w   = c.get("width") or 0
        l   = c.get("length") or 0
        if w and l:
            dims_str = f"{w:.1f}\u00d7{l:.1f}"
        elif w:
            dims_str = f"{w:.1f}\u00d7?"
        elif l:
            dims_str = f"?\u00d7{l:.1f}"
        else:
            dims_str = "    ?    "
        x   = round(c.get("x", 0), 1)
        y   = round(c.get("y", 0), 1)
        name = c.get("name", "")[:30]
        is_edge = c.get("connector") and c.get("ref", "") in edge_refs
        note = "NEAR EDGE" if is_edge else ("CONNECTOR" if c.get("connector") else "")
        lines.append(f"  {ref:<8} {h:>5.1f} mm  {rot:>3}\u00b0    {dims_str}  ({x:>6.1f}, {y:>6.1f})  {note:<12} {name}")
    return "\n".join(lines)


# ── Prompt constants ────────────────────────────────────────────────────────

_SYSTEM_ROLE = (
    "You are a PCB enclosure design agent. "
    "Read the PCB PARSE QUALITY section at the top of the board data. "
    "Use the Confidence percentage to decide how much to trust the parsed data:\n"
    "  \u2022 \u226580% \u2014 use the component table and cutout dimension table as-is.\n"
    "  \u2022 40\u201379% \u2014 generate the enclosure from parsed data but add interior "
    "padding for components whose heights are estimated.\n"
    "  \u2022 <40%  \u2014 do NOT invent cutouts; generate a minimal shell only "
    "and advise the user to re-export the KiCad file.\n"
    "Always honour the COMPONENT TABLE and CUTOUT DIMENSION REFERENCE over "
    "any assumptions. "
    "When a PCB Vision Analysis is present, treat it as the PRIMARY source "
    "for custom_cutouts and cross-reference the dimension table for exact sizes. "
    "The ASCII map confirms component positions.\n\n"
    "IMPORTANT \u2014 Use the COMPONENT TABLE above to decide which components need "
    "lid cutouts (wall=\"top\") vs wall cutouts:\n"
    "  \u2022 wall=\"top\"  = components that sit on the PCB surface and point upward "
    "(buttons, LEDs, displays, pin headers, rotary encoders, switches, OLEDs, "
    "camera modules). These are typically NOT near any board edge and have "
    "height > 0.\n"
    "  \u2022 wall=\"front/back/left/right\" = edge-mounted connectors (USB, HDMI, "
    "RJ45, barrel jack, SD card slot, terminal blocks). These are typically "
    "within 8 mm of a board edge (marked \"NEAR EDGE\" in the table).\n"
    "Do NOT leave custom_cutouts empty \u2014 examine EVERY component and decide "
    "what cutout type it needs."
)

_JSON_SCHEMA = """\
OUTPUT FORMAT
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
Respond ONLY with a valid JSON object \u2014 no markdown fences, no prose, no comments.

{
  "wall_thickness":          <float mm, 1.5\u20134.0>,
  "floor_thickness":         <float mm, 1.5\u20133.0>,
  "margin":                  <float mm, 1.0\u20135.0>,
  "headroom_mm":             <float mm \u2014 clearance above tallest component>,
  "lid_thickness":           <float mm, 1.5\u20133.0>,
  "boss_od":                 <float mm, 4.0\u20138.0>,
  "snap_fit_count":          <int 0 | 2 | 4>,
  "ventilation":             <bool>,
  "ventilation_slots_count": <int 0\u201312>,
  "custom_cutouts": [
    {
      "type":      "rectangle" | "round" | "slot" | "cable",
      "wall":      "front" | "back" | "left" | "right" | "top",
      "x_mm":      <float \u2014 position along wall from left end to cutout centre>,
      "y_mm":      <float \u2014 height above enclosure floor; 0 = floor level>,
      "width_mm":  <float>,
      "height_mm": <float>,
      "label":     "<connector name e.g. USB-C, Barrel Jack, RJ45>"
    }
  ]
}

WALL CONVENTION
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
front = Y-min board edge (bottom of ASCII map)
back  = Y-max board edge (top of ASCII map)
left  = X-min edge   right = X-max edge
top   = lid surface (displays, upward LEDs, top-mount buttons)

GENERAL RULES
\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
\u2022 wall=\"top\" cutouts are for components that SIT ON THE PCB and point UPWARD:
     buttons, LEDs, OLED/TFT displays, pin headers, rotary encoders, switches,
     camera modules, 7-segment displays.  These are in the board INTERIOR, not
     near edges.  Use the COMPONENT TABLE heights and positions to locate them.
\u2022 wall=\"front/back/left/right\" cutouts are for EDGE-MOUNTED connectors:
     USB, HDMI, RJ45, barrel jack, SD card, audio jacks, terminal blocks,
     DB9.  These are within 8 mm of a board edge.
\u2022 Use the CUTOUT DIMENSION REFERENCE table above for exact width_mm / height_mm.
\u2022 Leave custom_cutouts [] only if the board has absolutely NO components
     that need any kind of opening (no connectors, no buttons, no displays).
\u2022 ventilation=true if any large heatsink, power module, or hot IC is visible.
\u2022 Increase headroom_mm for tall capacitors or heatsinks (add their height).
"""


# ── Public entry point ──────────────────────────────────────────────────────

def _assess_parse_quality(board_ctx: dict) -> tuple[str, int]:
    """Evaluate parse completeness and return (quality_block, confidence_pct)."""
    dims       = board_ctx.get("dimensions", {})
    components = board_ctx.get("components", [])
    holes      = board_ctx.get("mounting_holes", [])
    connectors = [c for c in components if c.get("connector")]

    w = dims.get("width", 0)
    h = dims.get("height", 0)
    outline_ok = w > 0 and h > 0
    comps_ok   = len(components) > 0
    holes_ok   = len(holes) > 0
    conns_ok   = len(connectors) > 0

    # Height quality: check how many components have the default fallback (10.0)
    # vs. a known lookup value.
    est_count = sum(1 for c in components if c.get("height", 0) == 10.0)
    known_count = len(components) - est_count
    if not components:
        heights_ok = "N/A (no components)"
    elif known_count == 0:
        heights_ok = "\u2717 fully estimated"
    elif est_count > known_count:
        heights_ok = "\u26a0 mostly estimated"
    elif est_count > 0:
        heights_ok = f"\u26a0 partially estimated ({known_count} known, {est_count} default)"
    else:
        heights_ok = "\u2713"

    # Confidence score (0-100)
    score = 0
    if outline_ok:
        score += 20
    if comps_ok:
        score += 25
    if holes_ok:
        score += 10
    if conns_ok:
        score += 10
    # Height quality (weighted heavily — estimated heights undermine the whole enclosure)
    if components:
        ratio = known_count / len(components)
        if ratio >= 0.95:
            score += 35
        elif ratio >= 0.7:
            score += 20
        elif ratio >= 0.3:
            score += 10
        elif ratio > 0:
            score += 5
        # ratio == 0: no height points, AND penalise component confidence
        if ratio == 0:
            score = int(score * 0.5)

    # Penalise boards where most components are missing
    if not comps_ok:
        score = int(score * 0.3)

    score = min(score, 100)

    check = "\u2713"
    cross = "\u2717"
    lines = [
        "PCB PARSE QUALITY",
        "\u2550" * 30,
        f"  Outline:     {check if outline_ok else cross} ({w:.1f} x {h:.1f} mm)",
        f"  Components:  {check if comps_ok else cross} ({len(components)})",
        f"  Mount holes: {check if holes_ok else cross} ({len(holes)})",
        f"  Connectors:  {check if conns_ok else cross} ({len(connectors)})",
        f"  Heights:     {heights_ok}",
        "",
        f"  Confidence: {score}%",
        "",
    ]
    if score >= 80:
        lines.append("  \u2192 High confidence \u2014 use component table and cutout dimension table as-is.")
    elif score >= 40:
        lines.append("  \u2192 Medium confidence \u2014 generate enclosure; add interior padding for components with estimated heights.")
    else:
        lines.append("  \u2192 Low confidence \u2014 generate a minimal shell without cutouts; advise user to re-export the KiCad file.")

    quality_block = "\n".join(lines)
    return quality_block, score


def _dump_pcb_summary(board_ctx: dict) -> str:
    """Print a concise PCB summary to console and return a text block for the AI prompt."""
    dims       = board_ctx.get("dimensions", {})
    components = board_ctx.get("components", [])
    holes      = board_ctx.get("mounting_holes", [])
    connectors = [c for c in components if c.get("connector")]
    edge_refs  = {e.get("ref", "") for e in board_ctx.get("edge_connectors", [])}

    w = dims.get("width", 0)
    h = dims.get("height", 0)
    lines = [
        "[PCB]",
        f"  Board: {w:.1f} × {h:.1f} mm",
        f"  Components: {len(components)}",
        f"  Mounting holes: {len(holes)}",
    ]

    if connectors:
        lines.append(f"  Connectors ({len(connectors)}):")
        for c in connectors:
            near = " [EDGE]" if c.get("ref", "") in edge_refs else ""
            lines.append(f"    {c['ref']:<6} {c.get('name',''):<30} @ ({c['x']:.1f}, {c['y']:.1f}){near}")
    else:
        lines.append("  Connectors: none detected")

    # Tallest component
    tall = sorted(components, key=lambda c: c.get("height", 0), reverse=True)
    if tall:
        t = tall[0]
        lines.append(f"  Tallest: {t.get('ref','?')}  {t.get('name',''):<30}  height={t['height']:.1f} mm")
    else:
        lines.append("  Tallest: (no components — height will be guessed)")

    summary = "\n".join(lines)
    print(summary)
    return summary


def build_ai_context(
    board_ctx: dict,
    *,
    wall_t: float = 2.5,
    floor_t: float = 2.0,
    margin: float = 2.0,
    headroom_mm: float = 4.0,
    lid_t: float = 2.0,
    vision_description: str | None = None,
) -> tuple[str, str]:
    """
    Returns (sys_prompt, board_block) ready to send to DeepSeek Chat.

    vision_description : plain-text output from VL2 (None \u2192 fallback text).
    """
    if vision_description:
        vision_block = (
            "PCB VISION ANALYSIS  (DeepSeek VL2 \u2014 PRIMARY cutout source)\n"
            "\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n"
            + vision_description.strip() + "\n\n"
            "\u2192 Map each COMPONENT line above to a cutout using the dimension table below."
        )
    else:
        vision_block = (
            "PCB VISION ANALYSIS\n"
            "\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n"
            "(Not available \u2014 kicad-cli missing or VL2 call failed.)\n"
            "\u2192 Use the ASCII map and board data to infer cutouts from connector positions."
        )

    board_block = "\n\n".join([
        "[PCB SUMMARY]",
        _dump_pcb_summary(board_ctx),
        _assess_parse_quality(board_ctx)[0],
        "",
        "BOARD DATA\n\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n" + _board_summary(board_ctx),
        (
            f"DEFAULT PARAMETERS  (adjust as needed)\n"
            f"wall={wall_t} mm  floor={floor_t} mm  margin={margin} mm  "
            f"headroom={headroom_mm} mm  lid={lid_t} mm"
        ),
        "ASCII LAYOUT MAP (top-down)\n\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n"
        + _render_pcb_layout_map(board_ctx),
        vision_block,
        _DIMENSION_TABLE,
        _JSON_SCHEMA,
    ])

    return _SYSTEM_ROLE, board_block


# ── Legacy shim ─────────────────────────────────────────────────────────────

def get_system_prompt(board_ctx: dict) -> str:
    """Backwards-compatible — callers not yet updated to unpack tuple."""
    sys_p, board_b = build_ai_context(board_ctx)
    return sys_p + "\n\n" + board_b


class PrecomputedGeometry:
    """Placeholder for PCB enclosure precomputation results."""
    pass


def precompute(board_data: dict) -> PrecomputedGeometry:
    """Placeholder — runs geometry precomputation on parsed board data."""
    return PrecomputedGeometry()
