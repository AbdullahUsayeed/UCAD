"""
cutout_knowledge_base.py
════════════════════════
Single source of truth for enclosure cutout dimensions and placement rules.

Used by:
  • vision_pipeline.py   — injected into the VL2 prompt so it knows what
                           to look for and what sizes to report
  • context_injector.py  — injected into the chat prompt so DeepSeek Chat
                           can produce correct custom_cutouts JSON
  • enclosure_template.py (optional) — for clamping / validation

All dimensions are in millimetres.
Clearance of +0.4 mm is already baked into every dimension (print tolerance).
"""

from __future__ import annotations


# ════════════════════════════════════════════════════════════════════════════
# COMPONENT CATALOGUE
# Each entry is a dict with:
#   aliases      : list of strings VL2 might say
#   type         : cutout shape ("rectangle" | "round" | "slot" | "cable")
#   width_mm     : cutout width  (X along wall face)
#   height_mm    : cutout height (Z up the wall)
#   y_mm_default : height above enclosure floor (0 = at floor level)
#   wall_hint    : preferred wall(s) — informational, AI decides final
#   notes        : extra guidance for the AI
# ════════════════════════════════════════════════════════════════════════════

COMPONENT_CATALOGUE: list[dict] = [

    # ── USB ─────────────────────────────────────────────────────────────────
    {
        "id": "usb_a",
        "aliases": ["USB-A", "USB Type-A", "USB 2.0 Type A", "USB 3.0 Type A",
                    "USB host", "USB-A female"],
        "type": "rectangle",
        "width_mm": 13.0,
        "height_mm": 7.0,
        "y_mm_default": 2.0,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": (
            "USB 3.0 variant is blue inside — same external cutout. "
            "If stacked (2× vertical), height_mm=15. "
            "If side-by-side (2× horizontal), width_mm=27."
        ),
    },
    {
        "id": "usb_c",
        "aliases": ["USB-C", "USB Type-C", "USB-C female", "USB C port"],
        "type": "rectangle",
        "width_mm": 10.0,
        "height_mm": 4.5,
        "y_mm_default": 2.5,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "Common on modern microcontroller boards (ESP32-S3, RP2040, STM32). Centred on connector body.",
    },
    {
        "id": "usb_micro_b",
        "aliases": ["Micro USB", "Micro-B", "micro USB female", "micro-USB port"],
        "type": "rectangle",
        "width_mm": 9.0,
        "height_mm": 4.5,
        "y_mm_default": 2.0,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "Trapezoid profile — rectangle cutout is safe.",
    },
    {
        "id": "usb_mini_b",
        "aliases": ["Mini USB", "Mini-B", "mini USB female"],
        "type": "rectangle",
        "width_mm": 9.5,
        "height_mm": 5.0,
        "y_mm_default": 2.0,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "Older devices. Trapezoid profile.",
    },

    # ── Power ────────────────────────────────────────────────────────────────
    {
        "id": "barrel_jack_5v",
        "aliases": ["barrel jack", "DC jack", "power jack", "barrel connector",
                    "5.5/2.1", "5.5/2.5", "DC power", "centre-positive"],
        "type": "round",
        "width_mm": 9.5,   # diameter
        "height_mm": 9.5,
        "y_mm_default": 6.0,
        "wall_hint": ["back", "right"],
        "notes": (
            "Most common: OD 9.5 mm (5.5 mm barrel). "
            "Centre height above floor ≈ floor_thickness + standoff + PCB_thickness + 6 mm. "
            "Use round type; width_mm = height_mm = diameter."
        ),
    },
    {
        "id": "xt30",
        "aliases": ["XT30", "XT-30", "XT30 connector"],
        "type": "rectangle",
        "width_mm": 16.0,
        "height_mm": 12.0,
        "y_mm_default": 2.0,
        "wall_hint": ["back", "right"],
        "notes": "High-current connector, common in drones/robots.",
    },
    {
        "id": "xt60",
        "aliases": ["XT60", "XT-60", "XT60 connector"],
        "type": "rectangle",
        "width_mm": 20.0,
        "height_mm": 14.0,
        "y_mm_default": 2.0,
        "wall_hint": ["back", "right"],
        "notes": "Larger high-current connector.",
    },
    {
        "id": "terminal_block_2pin",
        "aliases": ["terminal block", "screw terminal", "2-pin terminal",
                    "KF301", "KF128", "spring terminal"],
        "type": "slot",
        "width_mm": 10.0,   # per 2-pin, 5 mm pitch
        "height_mm": 10.0,
        "y_mm_default": 0.0,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": (
            "width_mm = pin_count × pitch_mm (common: 5.0 or 3.5 mm pitch). "
            "2-pin 5 mm → 10 mm wide. 3-pin → 15 mm. 4-pin → 20 mm. "
            "height_mm = 10 mm for 5 mm pitch, 8 mm for 3.5 mm pitch."
        ),
    },

    # ── Video / Display ──────────────────────────────────────────────────────
    {
        "id": "hdmi_full",
        "aliases": ["HDMI", "HDMI Type A", "full-size HDMI"],
        "type": "rectangle",
        "width_mm": 16.0,
        "height_mm": 7.5,
        "y_mm_default": 2.0,
        "wall_hint": ["back", "left", "right"],
        "notes": "Full-size HDMI. Add 1 mm clearance each side for cable hood.",
    },
    {
        "id": "hdmi_mini",
        "aliases": ["Mini HDMI", "HDMI Type C", "mini-HDMI"],
        "type": "rectangle",
        "width_mm": 11.5,
        "height_mm": 5.5,
        "y_mm_default": 2.0,
        "wall_hint": ["back", "left", "right"],
        "notes": "Common on Raspberry Pi Zero, camera boards.",
    },
    {
        "id": "hdmi_micro",
        "aliases": ["Micro HDMI", "HDMI Type D", "micro-HDMI"],
        "type": "rectangle",
        "width_mm": 7.5,
        "height_mm": 4.0,
        "y_mm_default": 2.0,
        "wall_hint": ["back", "left", "right"],
        "notes": "Common on Raspberry Pi 4.",
    },
    {
        "id": "displayport",
        "aliases": ["DisplayPort", "DP connector", "mini DisplayPort", "mDP"],
        "type": "rectangle",
        "width_mm": 17.0,
        "height_mm": 8.0,
        "y_mm_default": 2.0,
        "wall_hint": ["back"],
        "notes": "Full-size DP. Mini-DP: width=9 height=5.",
    },
    {
        "id": "vga",
        "aliases": ["VGA", "DB15", "D-Sub 15", "HD-15"],
        "type": "rectangle",
        "width_mm": 32.0,
        "height_mm": 16.0,
        "y_mm_default": 2.0,
        "wall_hint": ["back"],
        "notes": "Trapezoidal D-Sub. Rectangle cutout with rounded corners preferred.",
    },

    # ── Audio ────────────────────────────────────────────────────────────────
    {
        "id": "audio_3_5mm",
        "aliases": ["3.5mm jack", "audio jack", "headphone jack", "TRS", "TRRS",
                    "aux port", "3.5 mm audio"],
        "type": "round",
        "width_mm": 7.0,
        "height_mm": 7.0,
        "y_mm_default": 5.0,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "Round hole diameter 7 mm. Centre ~5 mm above floor.",
    },
    {
        "id": "audio_6_35mm",
        "aliases": ["6.35mm jack", "1/4 inch jack", "quarter inch", "TS", "TRS 6.35"],
        "type": "round",
        "width_mm": 11.0,
        "height_mm": 11.0,
        "y_mm_default": 6.0,
        "wall_hint": ["front", "back"],
        "notes": "Instrument/guitar audio. Round hole 11 mm diameter.",
    },
    {
        "id": "xlr",
        "aliases": ["XLR", "XLR-3", "XLR connector", "balanced audio"],
        "type": "round",
        "width_mm": 25.0,
        "height_mm": 25.0,
        "y_mm_default": 13.0,
        "wall_hint": ["front", "back"],
        "notes": "Panel-mount XLR: 24 mm round hole.",
    },

    # ── Network ──────────────────────────────────────────────────────────────
    {
        "id": "rj45",
        "aliases": ["RJ45", "Ethernet", "network port", "LAN port", "RJ-45"],
        "type": "rectangle",
        "width_mm": 16.5,
        "height_mm": 14.5,
        "y_mm_default": 2.0,
        "wall_hint": ["back", "left", "right"],
        "notes": (
            "Includes LEDs in tab: height_mm=14.5 covers full housing. "
            "Stacked (2×): width_mm=33.5."
        ),
    },
    {
        "id": "rj11",
        "aliases": ["RJ11", "RJ-11", "phone jack", "telephone port"],
        "type": "rectangle",
        "width_mm": 11.0,
        "height_mm": 10.0,
        "y_mm_default": 2.0,
        "wall_hint": ["back"],
        "notes": "Narrower than RJ45.",
    },
    {
        "id": "sma_antenna",
        "aliases": ["SMA", "SMA connector", "antenna connector", "RF connector", "U.FL"],
        "type": "round",
        "width_mm": 8.0,
        "height_mm": 8.0,
        "y_mm_default": 6.0,
        "wall_hint": ["back", "left", "right", "top"],
        "notes": "SMA bulkhead: 8 mm hole. RP-SMA same size. U.FL is internal — no wall cutout needed.",
    },

    # ── Storage ──────────────────────────────────────────────────────────────
    {
        "id": "sd_card",
        "aliases": ["SD card", "SD slot", "full-size SD", "SD card slot"],
        "type": "rectangle",
        "width_mm": 15.5,
        "height_mm": 3.0,
        "y_mm_default": 1.5,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "Full-size SD. Slot at floor level (y_mm=1.5).",
    },
    {
        "id": "microsd",
        "aliases": ["microSD", "micro SD", "microSD slot", "TF card", "TF slot"],
        "type": "slot",
        "width_mm": 12.0,
        "height_mm": 2.5,
        "y_mm_default": 1.5,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "Very thin slot. Push-push mechanism: ensure card ejects freely.",
    },
    {
        "id": "usb_flash",
        "aliases": ["USB flash", "USB drive", "USB stick", "USB thumb drive"],
        "type": "rectangle",
        "width_mm": 15.0,
        "height_mm": 8.0,
        "y_mm_default": 2.0,
        "wall_hint": ["front", "back"],
        "notes": "Same as USB-A but wider for drive body clearance.",
    },

    # ── Headers & GPIO ───────────────────────────────────────────────────────
    {
        "id": "pin_header_254",
        "aliases": ["pin header", "2.54mm header", "0.1in header", "GPIO header",
                    "male header", "female header", "through-hole header"],
        "type": "slot",
        "width_mm": None,   # computed: pin_count × 2.54
        "height_mm": 9.0,
        "y_mm_default": 0.0,
        "wall_hint": ["front", "back", "left", "right", "top"],
        "notes": (
            "width_mm = pin_count × 2.54 mm. "
            "2-pin → 5 mm, 4-pin → 10.2 mm, 6-pin → 15.2 mm, "
            "8-pin → 20.3 mm, 40-pin RPi → 102 mm. "
            "height_mm 9 mm covers standard 11 mm tall header. "
            "If on top of PCB pointing up → use wall=top."
        ),
    },
    {
        "id": "pin_header_200",
        "aliases": ["2.0mm header", "2mm pitch header"],
        "type": "slot",
        "width_mm": None,   # pin_count × 2.0
        "height_mm": 7.0,
        "y_mm_default": 0.0,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "width_mm = pin_count × 2.0 mm.",
    },
    {
        "id": "jst_xh",
        "aliases": ["JST", "JST-XH", "JST XH", "JST connector", "JST 2.54"],
        "type": "slot",
        "width_mm": None,   # pin_count × 2.5
        "height_mm": 7.0,
        "y_mm_default": 2.0,
        "wall_hint": ["front", "back"],
        "notes": (
            "JST-XH: 2.5 mm pitch. width_mm = pin_count × 2.5 + 1. "
            "JST-PH: 2.0 mm pitch. JST-SH: 1.0 mm pitch. "
            "All have clip on top — height_mm 7 covers body + clip."
        ),
    },

    # ── Buttons & Switches ───────────────────────────────────────────────────
    {
        "id": "tactile_button",
        "aliases": ["tactile button", "push button", "momentary button",
                    "tact switch", "SPST button", "reset button", "user button"],
        "type": "round",
        "width_mm": 5.0,
        "height_mm": 5.0,
        "y_mm_default": None,   # computed from PCB Z height
        "wall_hint": ["top", "front"],
        "notes": (
            "If on PCB top surface → wall=top, round hole 5 mm. "
            "If on PCB edge → wall=front/back/left/right. "
            "For panel-mount (threaded) button: round hole 16 mm."
        ),
    },
    {
        "id": "toggle_switch",
        "aliases": ["toggle switch", "SPDT switch", "DPDT switch", "bat handle",
                    "rocker switch", "lever switch"],
        "type": "rectangle",
        "width_mm": 8.0,
        "height_mm": 14.0,
        "y_mm_default": 5.0,
        "wall_hint": ["front", "top"],
        "notes": "Panel-mount toggle: 8 mm round hole. Rectangle cutout for rocker: 28×22 mm.",
    },
    {
        "id": "slide_switch",
        "aliases": ["slide switch", "DIP switch", "SPDT slide", "power switch"],
        "type": "slot",
        "width_mm": 10.0,
        "height_mm": 4.0,
        "y_mm_default": 3.0,
        "wall_hint": ["front", "right", "top"],
        "notes": "Slot length = travel + knob width. height_mm 4 mm for 3 mm knob.",
    },
    {
        "id": "rotary_encoder",
        "aliases": ["rotary encoder", "encoder", "knob", "potentiometer", "pot",
                    "volume knob", "trim pot"],
        "type": "round",
        "width_mm": 8.5,
        "height_mm": 8.5,
        "y_mm_default": 8.0,
        "wall_hint": ["front", "top"],
        "notes": (
            "Shaft diameter: 6 mm shaft → 7 mm hole. "
            "Panel-mount pot/encoder: 10 mm hole for M10 thread bushing. "
            "Use wall=top for top-mount knobs."
        ),
    },

    # ── LEDs & Displays ──────────────────────────────────────────────────────
    {
        "id": "led_3mm",
        "aliases": ["3mm LED", "LED indicator", "status LED", "pilot light"],
        "type": "round",
        "width_mm": 3.5,
        "height_mm": 3.5,
        "y_mm_default": None,
        "wall_hint": ["top", "front"],
        "notes": "3 mm LED → 3.5 mm hole. 5 mm LED → 5.2 mm hole. Use wall=top when LED points up.",
    },
    {
        "id": "led_5mm",
        "aliases": ["5mm LED", "5mm indicator"],
        "type": "round",
        "width_mm": 5.2,
        "height_mm": 5.2,
        "y_mm_default": None,
        "wall_hint": ["top", "front"],
        "notes": "5 mm LED → 5.2 mm hole.",
    },
    {
        "id": "oled_display",
        "aliases": ["OLED", "OLED display", "0.96 OLED", "1.3 OLED", "SSD1306",
                    "I2C display", "SPI display"],
        "type": "rectangle",
        "width_mm": 26.0,
        "height_mm": 14.0,
        "y_mm_default": None,
        "wall_hint": ["top", "front"],
        "notes": (
            "0.96\" OLED active area: 21.7×11 mm — cutout 26×14 covers bezel. "
            "1.3\" OLED: cutout 33×18. Use wall=top for upward-facing displays."
        ),
    },
    {
        "id": "tft_lcd",
        "aliases": ["TFT", "LCD", "ILI9341", "ST7789", "2.4 TFT", "2.8 TFT",
                    "display module", "colour display"],
        "type": "rectangle",
        "width_mm": 52.0,
        "height_mm": 40.0,
        "y_mm_default": None,
        "wall_hint": ["top"],
        "notes": (
            "2.4\" TFT: active area 49×37 — cutout 52×40. "
            "2.8\" TFT: active 57×44 — cutout 60×47. "
            "3.5\" TFT: active 73×49 — cutout 76×52. "
            "Always wall=top."
        ),
    },
    {
        "id": "seven_segment",
        "aliases": ["7 segment", "seven segment", "7seg", "numeric display", "digit display"],
        "type": "rectangle",
        "width_mm": None,   # digit_count × 12.7
        "height_mm": 20.0,
        "y_mm_default": None,
        "wall_hint": ["top", "front"],
        "notes": "width_mm = digit_count × 12.7 mm (0.5\" digit). height_mm 20 mm.",
    },

    # ── Cameras & Sensors ────────────────────────────────────────────────────
    {
        "id": "camera_module",
        "aliases": ["camera", "camera module", "OV2640", "OV5640", "Pi Camera",
                    "CSI camera", "webcam module"],
        "type": "rectangle",
        "width_mm": 10.0,
        "height_mm": 10.0,
        "y_mm_default": None,
        "wall_hint": ["top", "front"],
        "notes": (
            "Lens cutout only: 10×10 mm for most compact modules. "
            "RPi Camera v2 lens: 8 mm round hole. "
            "Use wall=top for upward-facing or wall=front for forward-facing."
        ),
    },
    {
        "id": "fpc_connector",
        "aliases": ["FPC", "FFC", "flex cable", "ribbon connector", "flat flex"],
        "type": "slot",
        "width_mm": None,   # cable width + 2
        "height_mm": 3.0,
        "y_mm_default": 1.5,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "width_mm = cable width + 2 mm. Thin slot at floor level for cable exit.",
    },

    # ── Serial / Debug ───────────────────────────────────────────────────────
    {
        "id": "db9_serial",
        "aliases": ["DB9", "RS232", "serial port", "D-Sub 9", "COM port"],
        "type": "rectangle",
        "width_mm": 21.0,
        "height_mm": 13.0,
        "y_mm_default": 2.0,
        "wall_hint": ["back"],
        "notes": "D-Sub 9 female panel-mount. Trapezoidal — rectangle is safe.",
    },
    {
        "id": "db25",
        "aliases": ["DB25", "D-Sub 25", "parallel port", "printer port"],
        "type": "rectangle",
        "width_mm": 40.0,
        "height_mm": 13.0,
        "y_mm_default": 2.0,
        "wall_hint": ["back"],
        "notes": "Wide D-Sub 25.",
    },

    # ── Wireless / Module ────────────────────────────────────────────────────
    {
        "id": "sim_card",
        "aliases": ["SIM card", "SIM slot", "nano SIM", "micro SIM", "full SIM"],
        "type": "slot",
        "width_mm": 15.0,
        "height_mm": 2.5,
        "y_mm_default": 1.5,
        "wall_hint": ["front", "back", "left", "right"],
        "notes": "Nano SIM: 12.3×8.8 mm. Micro SIM: 15×11 mm. Slot at floor level.",
    },

    # ── Ventilation (pseudo-component) ───────────────────────────────────────
    {
        "id": "heatsink_vent",
        "aliases": ["heatsink", "large IC", "power module", "voltage regulator",
                    "mosfet", "hot component"],
        "type": "rectangle",
        "width_mm": None,   # match component footprint + 4
        "height_mm": None,
        "y_mm_default": None,
        "wall_hint": ["top"],
        "notes": (
            "If a large heatsink or power module is visible, add vent slots "
            "in the lid above it. Set ventilation=true and increase headroom_mm "
            "by the heatsink height. No wall cutout needed — increase headroom."
        ),
    },

    # ── Cable Gland / Generic ────────────────────────────────────────────────
    {
        "id": "cable_gland",
        "aliases": ["cable", "wire", "cable gland", "cable entry", "wiring harness"],
        "type": "cable",
        "width_mm": 10.0,
        "height_mm": 10.0,
        "y_mm_default": 0.0,
        "wall_hint": ["back"],
        "notes": "Generic cable exit. width_mm = cable bundle diameter + 2. Use type=cable.",
    },
]


# ════════════════════════════════════════════════════════════════════════════
# LOOKUP HELPERS
# ════════════════════════════════════════════════════════════════════════════

def lookup(component_name: str) -> dict | None:
    """
    Return the catalogue entry whose aliases best match *component_name*.
    Case-insensitive substring match.  Returns None if not found.
    """
    name_lower = component_name.lower()
    for entry in COMPONENT_CATALOGUE:
        for alias in entry["aliases"]:
            if alias.lower() in name_lower or name_lower in alias.lower():
                return entry
    return None


def get_all_aliases() -> list[str]:
    """Flat list of every alias — useful for building VL2 prompt."""
    result = []
    for entry in COMPONENT_CATALOGUE:
        result.extend(entry["aliases"])
    return result


# ════════════════════════════════════════════════════════════════════════════
# PROMPT FRAGMENT GENERATORS
# ════════════════════════════════════════════════════════════════════════════

def generate_vision_prompt_appendix() -> str:
    """
    Returns a compact table injected into the VL2 system prompt so it
    knows what components to look for and what to report.
    """
    lines = [
        "COMPONENT RECOGNITION GUIDE",
        "═══════════════════════════",
        "When you see a component, identify it by name and report:",
        "  • Which board edge it is near (front/back/left/right) or top surface",
        "  • Distance from the nearest corner (estimate in mm)",
        "  • Quantity if more than one",
        "",
        "RECOGNITION HINTS BY CATEGORY",
        "──────────────────────────────",
    ]

    categories = {
        "USB Ports": ["usb_a", "usb_c", "usb_micro_b", "usb_mini_b", "usb_flash"],
        "Power":     ["barrel_jack_5v", "xt30", "xt60", "terminal_block_2pin"],
        "Video":     ["hdmi_full", "hdmi_mini", "hdmi_micro", "displayport", "vga"],
        "Audio":     ["audio_3_5mm", "audio_6_35mm", "xlr"],
        "Network":   ["rj45", "rj11", "sma_antenna"],
        "Storage":   ["sd_card", "microsd"],
        "Headers":   ["pin_header_254", "pin_header_200", "jst_xh", "fpc_connector"],
        "Controls":  ["tactile_button", "toggle_switch", "slide_switch", "rotary_encoder"],
        "Display":   ["led_3mm", "led_5mm", "oled_display", "tft_lcd", "seven_segment"],
        "Serial":    ["db9_serial", "db25"],
        "Other":     ["sim_card", "camera_module", "cable_gland"],
    }

    id_map = {e["id"]: e for e in COMPONENT_CATALOGUE}

    for category, ids in categories.items():
        lines.append(f"\n{category}:")
        for cid in ids:
            entry = id_map.get(cid)
            if not entry:
                continue
            aliases = ", ".join(entry["aliases"][:3])  # first 3 aliases
            lines.append(f"  • {aliases}")
            if entry.get("notes"):
                # One-line hint only
                hint = entry["notes"].split(".")[0]
                lines.append(f"    → {hint}")

    lines += [
        "",
        "For each identified component, output a line like:",
        '  COMPONENT: USB-C | WALL: left | DISTANCE_FROM_CORNER: 12 mm | QTY: 1',
        '  COMPONENT: Barrel Jack | WALL: back | DISTANCE_FROM_CORNER: 25 mm | QTY: 1',
        '  COMPONENT: Tactile Button | WALL: top | DISTANCE_FROM_CORNER: 8 mm | QTY: 2',
    ]

    return "\n".join(lines)


def generate_chat_prompt_appendix() -> str:
    """
    Returns a dimension table injected into the DeepSeek Chat prompt so it
    can convert the VL2 description into precise custom_cutouts JSON.
    """
    lines = [
        "CUTOUT DIMENSION REFERENCE",
        "══════════════════════════",
        "Use these standard dimensions when building custom_cutouts JSON.",
        "All values in mm. Clearance already included.",
        "",
        f"{'Component':<30} {'Type':<12} {'Width':>7} {'Height':>7} {'y_mm':>6}  Notes",
        "─" * 90,
    ]

    for entry in COMPONENT_CATALOGUE:
        w = f"{entry['width_mm']:.1f}" if entry["width_mm"] is not None else "calc"
        h = f"{entry['height_mm']:.1f}" if entry["height_mm"] is not None else "calc"
        y = f"{entry['y_mm_default']:.1f}" if entry["y_mm_default"] is not None else "calc"
        name = entry["aliases"][0]
        lines.append(
            f"{name:<30} {entry['type']:<12} {w:>7} {h:>7} {y:>6}  "
            f"{entry['notes'][:55]}"
        )

    lines += [
        "",
        "CALCULATION RULES",
        "─────────────────",
        "Pin header width  : pin_count × 2.54 mm  (2.0 mm pitch: × 2.0)",
        "Terminal block w  : pin_count × pitch_mm  (common: 5.0 or 3.5 mm)",
        "JST-XH width      : pin_count × 2.5 + 1 mm",
        "7-segment width   : digit_count × 12.7 mm",
        "FPC slot width    : cable_width_mm + 2 mm",
        "",
        "WALL CONVENTION",
        "───────────────",
        "front = Y-min edge (bottom of ASCII map)",
        "back  = Y-max edge (top of ASCII map)",
        "left  = X-min edge",
        "right = X-max edge",
        "top   = lid (for upward-facing components: displays, LEDs, buttons)",
        "",
        "x_mm = distance from the LEFT end of that wall face to the cutout centre",
        "y_mm = height above enclosure floor (0 = floor level, 2 = typical raised port)",
    ]

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# Quick self-test
# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== VISION PROMPT APPENDIX ===\n")
    print(generate_vision_prompt_appendix())
    print("\n\n=== CHAT PROMPT APPENDIX ===\n")
    print(generate_chat_prompt_appendix())
    print("\n\n=== LOOKUP TEST ===")
    for term in ["USB-C", "barrel jack", "RJ45", "unknown widget"]:
        entry = lookup(term)
        print(f"  lookup({term!r}) → {entry['aliases'][0] if entry else 'NOT FOUND'}")
