"""Gear / involute construction knowledge, scoped-injected into the system
prompt only when the request is about gears. No dependency on the
orchestrator core (import-safe)."""

import re

GEAR_KNOWLEDGE = """
## Gear Generation — Part API involute construction (MANDATORY path)

### CRITICAL RULE — Use the make_gear() function below VERBATIM
DO NOT write your own gear math. The following code is the ONLY correct
implementation. Copy-paste it directly. Do not simplify, do not substitute
primitives, do not change the involute equation.

IMPORTANT: After the function definition, the VERY LAST thing in your code
MUST be a call to make_gear() with the desired parameters. Without this call,
nothing will be created. Put the make_gear() call AFTER the function definition.

### MANDATORY GEAR CODE — Exact code the output must contain:
import math, Part, FreeCAD

def involute_point(r_base, angle):
    x = r_base * (math.cos(angle) + angle * math.sin(angle))
    y = r_base * (math.sin(angle) - angle * math.cos(angle))
    return FreeCAD.Vector(x, y, 0)

def make_gear(teeth=20, module=1.0, height=10, bore_radius=6):
    doc = FreeCAD.ActiveDocument if FreeCAD.ActiveDocument else FreeCAD.newDocument("Gear")
    pressure_angle = 20  # degrees
    pitch_r = teeth * module / 2
    base_r  = pitch_r * math.cos(math.radians(pressure_angle))
    addendum_r = pitch_r + module
    dedendum_r = pitch_r - 1.25 * module
    tooth_angle = 2 * math.pi / teeth

    def involute(t):
        return involute_point(base_r, t)

    points = []
    for i in range(teeth):
        offset = i * tooth_angle
        # Root start (right side)
        a_root = offset - tooth_angle * 0.45
        points.append(FreeCAD.Vector(
            dedendum_r * math.cos(a_root),
            dedendum_r * math.sin(a_root), 0))

        # Right involute flank: parameters 0 → involute_max
        involute_max = math.sqrt(addendum_r**2 - base_r**2) / base_r
        for step in range(21):
            t = step * involute_max / 20
            pt = involute(t)
            a = math.atan2(pt.y, pt.x) + offset - tooth_angle * 0.25
            r = math.sqrt(pt.x**2 + pt.y**2)
            points.append(FreeCAD.Vector(r*math.cos(a), r*math.sin(a), 0))

        # Tip arc (addendum)
        a_tip_start = offset + tooth_angle * 0.2
        a_tip_end   = offset + tooth_angle * 0.3
        for step in range(11):
            a = a_tip_start + step * (a_tip_end - a_tip_start) / 10
            points.append(FreeCAD.Vector(
                addendum_r * math.cos(a),
                addendum_r * math.sin(a), 0))

        # Left involute flank: parameters involute_max → 0
        for step in range(21):
            t = (20 - step) * involute_max / 20
            pt = involute(t)
            a = math.atan2(pt.y, pt.x) + offset + tooth_angle * 0.25
            r = math.sqrt(pt.x**2 + pt.y**2)
            points.append(FreeCAD.Vector(r*math.cos(a), r*math.sin(a), 0))

        # Root arc to next tooth
        a_root_end = offset + tooth_angle * 0.45
        points.append(FreeCAD.Vector(
            dedendum_r * math.cos(a_root_end),
            dedendum_r * math.sin(a_root_end), 0))

    wire = Part.makePolygon(points + [points[0]])
    face = Part.Face(wire)
    solid = face.extrude(FreeCAD.Vector(0, 0, height))
    gear_obj = Part.show(solid)
    gear_obj.Label = f"SpurGear_{teeth}t_m{module}"

    # Center bore
    if bore_radius > 0:
        bore = doc.addObject("Part::Cylinder", "Bore")
        bore.Radius = bore_radius
        bore.Height = height + 2
        bore.Placement.Base = FreeCAD.Vector(0, 0, -1)
        cut = doc.addObject("Part::Cut", "SpurGear")
        cut.Base = gear_obj
        cut.Tool = bore

    doc.recompute()
    return gear_obj

### Usage — call make_gear() at the end of your code (this MUST be the last executed line):
gear = make_gear(teeth=20, module=1.0, height=10, bore_radius=6)
FreeCADGui.SendMsgToActiveView("ViewFit")
print(f"Gear: {teeth} teeth, module {module}")

### Path B — FCGear workbench (DISABLED — crashes FreeCAD >=1.1)
# Do NOT import freecad.gears. The init_gui.py crashes on this version.
# Use make_gear() above instead.

### RULES
# 1. ALWAYS use the make_gear() function from this knowledge block — verbatim
# 2. Never use PartDesign Pad for gears — use Part::Face().extrude()
# 3. module = pitch_diameter / num_teeth — expose this param to the user
# 4. After creation, always call App.ActiveDocument.recompute()
# 5. For center bore, use Part::Cylinder + Part::Cut as shown above
# 6. If the involute face construction fails, fall back to Part::MultiFuse
#    of individual extruded tooth solids instead
"""

_GEAR_TRIGGERS = re.compile(
    r"\b(gear|gears|involute|spur|helical|bevel|worm|rack|pinion|tooth|teeth|sprocket|timing belt|cycloid|crown)\b",
    re.IGNORECASE,
)


def should_inject_gear(user_input):
    if not user_input:
        return False
    return bool(_GEAR_TRIGGERS.search(user_input))
