"""Curved Shapes / surface morphing knowledge, scoped-injected into the system
prompt only when the request is about curved shapes, blends, or transitions.
No dependency on the orchestrator core (import-safe)."""

import re

CURVEDSHAPES_KNOWLEDGE = """
\u26a0\ufe0f RULE #1 \u2014 HULL WIRES MUST LIE IN A PRINCIPAL PLANE
makeCurvedArray silently produces zero-volume output if hull wires
are not exactly in the XY, XZ, or YZ plane.
- Correct:   all points share a constant Y value (XZ plane)
- Correct:   all points share a constant Z value (XY plane)
- WRONG:     wires at arbitrary angles or mixed coordinates
Always place hull wires in XZ plane (constant Y) unless the user
explicitly specifies otherwise. Never rotate wires after creation.

## Curved Shapes — use the CurvedShapes workbench for surfaces / blends / arrays

### Pre-flight
try:
    import CurvedShapes
    CS_AVAILABLE = True
except ImportError:
    CS_AVAILABLE = False

### Path A — Curved Array (profile scaled within hull curves)
# Wings, fuselages, tapered bodies, boat hulls, ergonomic handles
import FreeCAD, CurvedShapes

# 1. Create the base profile (a closed 2D sketch or wire)
# 2. Create 1+ hull curves (bounding curves in XY/XZ/YZ plane)
# 3. Call makeCurvedArray:

result = CurvedShapes.makeCurvedArray(
    Base=profile,                 # Part::Feature with .Shape to array
    Hullcurves=[root, tip],       # 1+ bounding curves
    Axis=FreeCAD.Vector(1, 0, 0), # array direction
    Items=20,                     # 10-20 for preview, 40-80 for final
    OffsetStart=0,                # shift first rib inward
    OffsetEnd=0,                  # shift last rib inward
    Twist=0,                      # rotation along axis (degrees)
    Surface=True,                 # loft surface over ribs
    Solid=True,                   # closed solid if base is closed
    Distribution='linear',        # linear | parabolic | x³ | sinusoidal | elliptic
    PreserveAspectRatio=False,    # scale uniformly (requires 1 hull curve)
)
FreeCAD.ActiveDocument.recompute()

# Hullcurves MUST lie in a standard plane (XY / XZ / YZ).
# Arbitrary-plane curves silently produce wrong scaling or fail recompute.
# If your curve is off-axis, project it onto the nearest standard plane first.

### Path B — Curved Segment (blend between two different profiles)
# Transition pieces, morphing one shape into another
blend = CurvedShapes.makeCurvedSegment(
    Shape1=circle_profile,         # start shape
    Shape2=square_profile,         # end shape
    Hullcurves=[],                 # optional bounding curves
    Items=15,
    Surface=True,
    Solid=False,
    Twist=0,                       # helical twist between shapes
    InterpolationPoints=16,        # discretization if edge counts differ
)
FreeCAD.ActiveDocument.recompute()

### Path C — Curved Path Array (profile swept along a path)
# Curved ducts, variable-section pipes, ergonomic grips
sweep = CurvedShapes.makeCurvedPathArray(
    Base=profile,
    Path=spine_curve,
    Hullcurves=[top_curve, side_curve],  # optional — scale in X/Y/Z
    Items=30,
    OffsetStart=0,
    OffsetEnd=0,
    Twist=0,
    Surface=True,
    Solid=True,
)
FreeCAD.ActiveDocument.recompute()

### Path D — Interpolated Middle (sharp-corner transitions)
# Bridge a gap between two offset shapes with a smooth middle
middle = CurvedShapes.makeInterpolatedMiddle(
    Shape1=rect_a,
    Shape2=rect_b,
    Surface=True,
    Solid=False,
    InterpolationPoints=16,
    Twist=0,
)
FreeCAD.ActiveDocument.recompute()

### Utility — Surface Cut (parametric cross-section of a solid)
# Extract a face or curve at any plane position
cut = CurvedShapes.cutSurfaces(
    Surfaces=[body],
    Normal=FreeCAD.Vector(1, 0, 0),
    Position=FreeCAD.Vector(50, 0, 0),
    Face=True,                     # return a face (False = wire)
    Simplify=True,                 # reduce curve complexity
)
FreeCAD.ActiveDocument.recompute()

### Utility — Notch Connector (interlocking joints for laser-cut parts)
CurvedShapes.makeNotchConnector(
    Base=part_a,
    Tools=part_b,
    CutDepth=50.0,                 # notch depth in percent
)

### RULES
# 1. Always try CurvedShapes first for curved surfaces / blends / morphs
# 2. Items: 10-20 for preview speed, 40-80 for final quality. >100 is slow.
# 3. After create(), always call FreeCAD.ActiveDocument.recompute()
# 4. If CurvedShapes is unavailable, fall back to Part.makeLoft([wire1, wire2], solid=True, ruled=False)
# 5. Hullcurves must lie in XY / XZ / YZ planes. Off-axis curves corrupt the result silently.
# 6. For wings: use airfoil_knowledge to generate the 2D profile, then use it as Base in CurvedArray.
"""

# NOTE: "blend" and "morph" are intentionally standalone — they don't
# overlap with gear/airfoil/triangle triggers and are strong CurvedShapes cues.
_CURVEDSHAPES_TRIGGERS = re.compile(
    r"\b(curved\s*(?:array|shape|surface|segment|path)|"
    r"blend(\s+surface)?|loft\s+surface|"
    r"morph|fuselage|boat\s*hull|notch\s*connector(?:s)?|"
    r"interpolated\s+middle|hull\s+curve(?:s)?|cross[-\s]section\s+cut)\b",
    re.IGNORECASE,
)

CURVEDSHAPES_WING_BRIDGE = """
### Wing surfacing note
You have both airfoil knowledge and CurvedShapes available.
Use airfoil knowledge to generate the 2D profile wires, then pass one as
Base= and the other(s) as Hullcurves= to CurvedShapes.makeCurvedArray()
for a tapered 3D wing with proper surface/loft.
"""


def should_inject_curvedshapes(user_input):
    if not user_input:
        return False
    return bool(_CURVEDSHAPES_TRIGGERS.search(user_input))
