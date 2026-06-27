"""Airfoil / NACA construction knowledge, scoped-injected into the system
prompt only when the request is about wings/airfoils. No dependency on the
orchestrator core (import-safe) — just the snippet, a trigger regex, and a
detector."""

import re

AIRFOIL_KNOWLEDGE = """
## NACA Airfoil Construction (authoritative recipe for wing / airfoil / NACA requests)

# DO NOT write import statements — they are DISABLED in the sandbox.
# FreeCAD, Part, Draft, math, doc are ALREADY available as names. Just use them.
# (importAirfoilDAT / reading .dat files is NOT available in the sandbox.)

### 1. Generate NACA 4-digit points (math is pre-available, no import)
def naca4(number, n=60):
    # number e.g. "2412": camber=2%, camber-pos=40%, thickness=12%
    m, p, t = int(number[0]) / 100.0, int(number[1]) / 10.0, int(number[2:]) / 100.0
    xs = [0.5 * (1 - math.cos(math.pi * i / (n - 1))) for i in range(n)]
    yt = [5 * t * (0.2969 * xc ** 0.5 - 0.1260 * xc - 0.3516 * xc ** 2
                   + 0.2843 * xc ** 3 - 0.1015 * xc ** 4) for xc in xs]
    yc = [(m / p ** 2 * (2 * p * xc - xc ** 2)) if (p > 0 and xc < p)
          else ((m / (1 - p) ** 2 * (1 - 2 * p + 2 * p * xc - xc ** 2)) if p > 0 else 0.0)
          for xc in xs]
    upper = [(x, c + tk) for x, c, tk in zip(xs, yc, yt)]   # LE -> TE
    lower = [(x, c - tk) for x, c, tk in zip(xs, yc, yt)]   # LE -> TE
    return upper, lower

### 2. PREFERRED: closed profile via Draft.make_bspline(closed=True)
# This is the proven community pattern — it AUTO-CLOSES the loop, so you never
# get "Wire is not closed". No manual trailing-edge segment needed.
def airfoil_bspline(number, chord=100.0):
    upper, lower = naca4(number)
    ordered = upper + list(reversed(lower))   # single closed loop: upper LE->TE, lower TE->LE
    pts = [FreeCAD.Vector(x * chord, y * chord, 0) for x, y in ordered]
    spline = Draft.make_bspline(pts, closed=True)   # closed=True is the key
    doc.recompute()
    return spline

### 3. Pad to wingspan with Part.Face + extrude (NOT PartDesign Pad)
foil = airfoil_bspline("2412", chord=100.0)
face = Part.Face(foil.Shape.Wires[0])               # closed Draft wire -> planar face
solid = face.extrude(FreeCAD.Vector(0, 0, 300.0))   # span in mm (plain float)
Part.show(solid, "Wing")
doc.recompute()

### ALTERNATIVE (no Draft): build the closed wire manually with Part
# pu = [FreeCAD.Vector(x*chord, y*chord, 0) for x, y in upper]
# pl = [FreeCAD.Vector(x*chord, y*chord, 0) for x, y in reversed(lower)]
# su = Part.BSplineCurve(); su.interpolate(pu)
# sl = Part.BSplineCurve(); sl.interpolate(pl)
# te = Part.LineSegment(pu[-1], pl[0])   # trailing edge segment closes the loop
# le = Part.LineSegment(pl[-1], pu[0])   # leading edge segment (if a gap remains)
# wire = Part.Wire([su.toShape(), te.toShape(), sl.toShape(), le.toShape()])
# assert wire.isClosed()   # verify before Part.Face / extrude

### HARD RULES
# - NO import statements (sandbox blocks them); Part/Draft/FreeCAD/math/doc are pre-bound.
# - PREFER Draft.make_bspline(points, closed=True) for a guaranteed-closed airfoil loop.
# - Verify the loop is closed before Part.Face/extrude (prevents "Null input shape").
# - Use Part.Face + .extrude for airfoils — NOT PartDesign Pad/Sketch.
# - Never mix a Quantity with a float: use .Value (e.g. obj.Length.Value).
# - Pad.Type 'Dimension' is INVALID; if you must use PartDesign, Pad.Type = 'Length'.
# - Use plain floats for chord/span; keep all points planar (z=0) before extruding.
"""


_AIRFOIL_TRIGGERS = re.compile(
    r"\b(airfoil|aerofoil|naca|wing|winglet|chord|wingspan|lift\s+surface)\b",
    re.IGNORECASE,
)


def should_inject_airfoil(user_input):
    """Return True when the request is about wings/airfoils and the NACA
    construction recipe should be injected into the system prompt."""
    if not user_input:
        return False
    return bool(_AIRFOIL_TRIGGERS.search(user_input))
