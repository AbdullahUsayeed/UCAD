"""Triangle / isosceles construction knowledge, scoped-injected into the system
prompt only when the request is about triangles. No dependency on the
orchestrator core (import-safe)."""

import re

TRIANGLE_KNOWLEDGE = """
\u26a0\ufe0f RULE #0 \u2014 DO NOT EXTRUDE OR PAD THE TRIANGLE
Draft.makeWire with closed=True, face=True already produces a complete
filled face. The shape is done after makeWire. Stop there.

DO NOT call:
  - Part.makeExtrusion()       \u2190 does not exist
  - face.extrude()             \u2190 only if user asks for 3D solid
  - Part.makePad()             \u2190 PartDesign only, wrong workbench
  - any coloring or display modification

The ONLY correct code for a basic triangle is:
  pts = [v1, v2, v3]
  wire = Draft.makeWire(pts, closed=True, face=True)
  doc.recompute()
  That is the complete script. Nothing else.

## Triangle Construction — isosceles triangle by vertex angle + height/base/hypotenuse

### Utility function (adapted from the Macro_Triangle_AH FreeCAD macro)
from math import cos, sin, tan, radians
import Draft, FreeCAD

def triangle_ah(angle, height=0.0, base=0.0, hypo=0.0):
    angle = float(angle)
    height = float(height)
    base = float(base)

    if base != 0:
        height = ((base / 2) / (tan(radians(angle / 2))))
    if hypo != 0:
        height = hypo * (cos(radians(angle / 2)))
    else:
        hypo = height / cos(radians(angle / 2))
    if base == 0:
        base = (tan(radians(angle / 2)) * height) * 2

    def _pt(x1, y1, z1, length, angle2):
        return (x1 + length * cos(radians(angle2)),
                y1 + length * sin(radians(angle2)), z1)

    apex = _pt(0, 0, 0, 0, angle)
    pt_a = _pt(0, 0, 0, hypo, -(angle / 2))
    pt_b = _pt(pt_a[0], pt_a[1], pt_a[2], abs(pt_a[1]) * 2, 90.0)

    wire = Draft.makeWire([
        FreeCAD.Vector(apex),
        FreeCAD.Vector(pt_a),
        FreeCAD.Vector(pt_b),
    ], closed=True, face=True, support=None)
    FreeCAD.ActiveDocument.recompute()
    return wire

### Usage
# triangle_ah(angle=90, height=50)      # default: isosceles, symmetric about X axis
# triangle_ah(angle=60, base=100)       # compute height from base
# triangle_ah(angle=45, hypo=80)        # compute height from hypotenuse

### RULES
# 1. Use Draft.makeWire with closed=True, face=True — never PartDesign/Sketcher for simple triangles
# 2. Vertex is at origin, triangle is symmetric about the X axis
# 3. angle is the vertex angle (apex), the base angles are (180 - angle) / 2 each
# 4. surface area = (base * height) / 2
# 5. For right triangles: angle=90, height=base gives a right isosceles triangle

### PROMPT SHORTCUT
If the user sends a compact prompt like
"Draft.makeWire closed=True face=True triangle apex at origin angle 90 height 50"
treat it as a direct code request \u2014 skip planning, skip steps, output only
the Python code block. No numbered plan. No explanation unless asked.
"""

_TRIANGLE_TRIGGERS = re.compile(
    r"\b(triangle|triangular|isosceles|equilateral|right.?triangle|trigonometry|vertex.?angle)\b",
    re.IGNORECASE,
)


def should_inject_triangle(user_input):
    if not user_input:
        return False
    return bool(_TRIANGLE_TRIGGERS.search(user_input))
