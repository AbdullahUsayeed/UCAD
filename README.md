# UCAD Assistant

The most advanced CAD agent is Available on FreeCad

[![Demo Video](https://img.youtube.com/vi/-gEuExxmy0Y/0.jpg)](https://www.youtube.com/watch?v=-gEuExxmy0Y)

## What This Is

UCAD is a FreeCAD workbench that lets you design in plain English. It is not a chatbot wrapper. It is a purpose-built CAD agent with deep knowledge of the FreeCAD API — scoped per workbench, self-correcting on mistakes, and tested against real FreeCAD geometry before it ever reaches your model.

It knows the difference between `Draft.makeWire` and `Part.makePolygon`. It knows that `Part.makeExtrusion()` does not exist. It knows that hull wires in CurvedShapes must lie in a principal plane or you get silent zero-volume output. It knows these things because they were caught in production and baked in — not guessed.

## Three Tools, One Workbench

### AI CAD Assistant

Natural language to FreeCAD Python. Ask for a gear, a bracket, an airfoil, a triangle. The agent classifies your request, injects the right knowledge, validates the code before running it, and retries with a specific fix if something fails.

- 19 always-on API corrections catch hallucinated FreeCAD calls before execution
- Scoped knowledge injection: gear math, triangle geometry, CurvedShapes hull rules, addFC usage — each fires only when relevant
- Simple requests get code immediately. Complex requests get commented sections. No theatrical numbered plans.
- 12 direct CAD tools (close wire, add fillet, set property, measure distance, hide/show) that route without a full LLM round-trip

### DXF Cleaner

Upload a DXF profile. Get back structured geometry — normalized to origin, unit-corrected, with holes separated from outlines, overlaps flagged, and degenerate vertices stripped before they cause `OCCError: Both points are equal`.

- Handles `$INSUNITS=0` (undefined units) by detecting from coordinate extents
- Deduplicates 692 warnings into 5 meaningful ones
- Chains open SPLINEs and ARCs into closed profiles when possible
- Output is injected directly into the AI context for code generation

### PCB Enclosure Generator

Give it a KiCad `.kicad_pcb` file. Get a parametric 3D-printable enclosure with:

- Shell and lid as separate exportable bodies
- Mounting bosses at PCB hole positions with M3 heat-set insert clearance
- Connector cutouts sized per type (USB-A, HDMI, RJ45)
- Ventilation slots, snap arms, label recess — all configurable
- Named model tree (Shell, Lid, Reference, Export_Compound) so you can select, hide, and export individual parts

## What Was Built Before Shipping

300 automated tests. Zero FreeCAD required to run them. Zero real API calls during development.

| Layer | What it covers |
|-------|----------------|
| Exec validation | Every template renders valid Python, executes in a mock FreeCAD namespace, and contains no leaked placeholders |
| Integration | Full prompt → system prompt → template → mock exec round-trips for all 5 knowledge modules |
| Mutation guard | Patches each knowledge injector to confirm knowledge disappears when disabled — no leaking paths |
| Resilience | `render_template()` with bad inputs, wrong types, unknown names — all handled cleanly |
| Trigger edge cases | Partial words, punctuation, mixed case, multi-topic prompts across all 5 modules |
| Error pipeline | Every FreeCAD error pattern translates to a specific fix hint before retry |
| Security | `_validate_exec_code()` called before every exec(). No hardcoded keys. Secrets stored via DPAPI (Windows), keyring, or Fernet-encrypted file |
| DXF processor | Coordinate normalization, unit detection, degenerate vertex dedup, HATCH isolation — all tested against a real production DXF file |
| PCB enclosure | Named model tree, separate shell/lid bodies, standoff placement within cavity bounds |

This is not vibe-coded. Every bug listed below was caught by the test suite before a single user saw it.

**Bugs caught before shipping:**

- `is_curved` gated by `and not is_gear` — curved shapes were suppressed when gear fired
- `render_template()` silently accepted non-dict overrides and unknown template names
- `sys.exit()` in the addFC template would have killed the entire FreeCAD process
- `ViewObject` accessed without headless guard — crashed the enclosure build in console mode
- DXF coordinates at (-33000, -176000) placed geometry miles from origin
- 692 identical warnings from a single DXF file, now deduplicated to 5
- `Part.makeExtrusion()` does not exist — added as always-on API correction
- Hull wires in arbitrary planes produce silent zero-volume CurvedShapes output

## Installation

### Option A — FreeCAD Addon Manager (recommended)

**Tools → Addon Manager → Workbenches → Search "UCAD" → Install → Restart**

Dependencies (`ezdxf`, `shapely`) install automatically via the post-install script. If that fails, see Option B step 3.

### Option B — Manual

**1. Download the repo**

```bash
git clone https://github.com/AbdullahUsayeed/UCAD.git
```
Or download the ZIP from [github.com/AbdullahUsayeed/UCAD](https://github.com/AbdullahUsayeed/UCAD) and extract it.

**2. Place it in FreeCAD's Mod folder**

Copy the `UCAD` folder into your FreeCAD user Mod directory:

| OS | Path |
|----|------|
| **Windows** | `%APPDATA%\FreeCAD\v1-1\Mod\` (create `Mod` if missing) |
| **Linux** | `~/.local/share/FreeCAD/Mod/` |
| **macOS** | `~/Library/Application Support/FreeCAD/Mod/` |

Final layout must be:
```
Mod/
  AICompanion/
    Init.py          ← required for FreeCAD discovery
    InitGui.py
    package.xml
    ...
```

**3. Install Python dependencies**

Open a terminal and run:

```bash
# Windows (FreeCAD 1.1):
"C:\Program Files\FreeCAD 1.1\bin\python.exe" -m pip install -r "<ModPath>\AICompanion\requirements.txt"

# Linux:
/path/to/freecad-python -m pip install -r ~/.local/share/FreeCAD/Mod/AICompanion/requirements.txt
```

Required packages: `ezdxf` (DXF processing), `shapely` (2D geometry).  
Optional: `keyring` + `cryptography` (secret storage on Linux/macOS).

**4. Restart FreeCAD**

Launch FreeCAD. Select **UCAD Assistant** from the workbench dropdown (top-left, next to Part Design / Part).

**5. Open the sidebar**

Click the UCAD Assistant workbench, or use `Ctrl+Shift+A`. The AI copilot panel opens on the right. Enter your API key in Settings and start designing.

## Quick Start

1. Select **UCAD Assistant** from the workbench dropdown
2. Click **Open AI Copilot** (or `Ctrl+Shift+A`)
3. Enter your API key in Settings (or select Ollama for a local model — no key required)
4. Type a request:
   - *"make a gear with 20 teeth and 2mm module"*
   - *"draw a triangle with 90° apex and 50mm height"*
   - *"generate a PCB enclosure for my KiCad board"*
   - *"clean this DXF and extrude the outline"*

**Recommended model:** Claude Opus 4 — the system prompt uses scoped knowledge injection, self-correcting API validation, and response mode classification that benefit from a capable model.

## Supported Workbenches & Topics

| Topic | What the agent knows |
|-------|---------------------|
| Gears | Pure Part API involute construction (FCGear disabled — crashes on FreeCAD ≥1.1) |
| Triangles | `Draft.makeWire` with `closed=True`, `face=True` — no extrusion unless asked |
| CurvedShapes | Hull wire plane rules, `makeCurvedArray` axis requirements, wing bridge pattern |
| Airfoil | NACA profile generation, BSpline construction |
| addFC | Macro path, download fallback, exec() execution |
| PartDesign | Sketch attachment, Pad/Pocket types, Body/Profile patterns |
| Part API | Boolean operations, extrusion, polygon construction |
| Draft | Wire, rectangle, BSpline — 2D geometry patterns |

## Requirements

- FreeCAD 1.1+ (Python 3.11, win_amd64 for bundled deps)
- API key for your chosen LLM provider (Anthropic, OpenAI, Google, Groq, etc. — or use a local model via Ollama with no key needed)
- Windows (primary), Linux/macOS (untested but should work)

| Package | Required | Purpose |
|---------|----------|---------|
| `ezdxf` | Yes | DXF processing |
| `shapely` | Yes | 2D geometry |
| `keyring` | No | Linux/macOS secret storage |
| `cryptography` | No | Encrypted file fallback |

## License

Proprietary. Requires a valid license key.

[Get a license →](https://ai-companion-licensing.usayeed10.workers.dev/checkout?plan=yearly)

---

*Built with the conviction that AI tools for engineering should be held to engineering standards.*
