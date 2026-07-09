# AI Copilot for FreeCAD — Vision & Capabilities

## The Mission

Make FreeCAD as accessible as ChatGPT while being more powerful than any CAD
software on the market — by giving you an AI agent that can *do everything you
can do with a mouse*, only faster, in parallel, and without the repetitive
clicking.

We're not building a chat overlay. We're building an autonomous CAD engineer
that lives inside FreeCAD, reads your intent, writes parametric Python, and
executes it with transaction rollback, real-time observation feedback, and
multi-step plan correction.

## What It Can Do

### Create anything from scratch
- Boxes, cylinders, spheres, cones, toruses, tubes, helices
- Complex sketcher profiles (rectangles, circles, arcs, B-Splines, polygons)
- Extrude/pad/revolve/pocket/groove any sketch
- PartDesign Bodies with additive/subtractive features
- Boolean operations (cut, fuse, common)
- Fillet, chamfer, mirror, thickness, offset

### Edit anything you have open
- Open any existing FreeCAD file — the assistant reads the live document state
- Modify existing sketches: add dimensions, close profiles, fix constraints
- Add features to existing bodies (pads, pockets, holes, fillets)
- Repair under-constrained sketches automatically

### Use any workbench
- PartDesign, Sketcher, Part, Draft, TechDraw, Mesh, Assembly
- Addon workbenches: SheetMetal, Fasteners, ScrewMaker
- If a workbench isn't installed, the assistant tells you exactly how to
  install it from the Addon Manager

### Generate 3D-printable PCB enclosures
- Drop a `.kicad_pcb` file — no KiCad workbench needed, parses S-expressions
  directly (Edge.Cuts outline, mounting holes, component positions, connector
  types via USB/HDMI/RJ45 keyword matching)
- AI config mode: sends board geometry to the LLM, which returns a JSON
  param block (wall thickness, margin, boss OD, snap fit count, etc.)
- Direct template mode: bypasses AI, generates enclosure instantly from
  parsed board data
- Parametric shell with standoffs, lid with screw counterbores, M3 heat-set
  insert holes, interlocking tongue-and-groove, ventilation slots, snap-fit
  cantilever arms, cable-tie anchor posts, label recess
- Connector cutouts: USB-A/C, HDMI, barrel jack, RJ45, DB9, SMA — auto-sized
  from a type registry with safe-zone collision clipping
- Hammond instant matching: search a 30+ model catalog (1551/1553/1590/1455/
  1591 series) for the smallest fitting off-the-shelf enclosure

### Multi-step autonomous plans
- "Design a 3D-printable enclosure for this PCB": imports the STEP, measures
  the board, generates a box with standoffs, creates a lid with screw holes,
  exports STL — all in one chain
- If a step fails, the assistant retries with a different approach
- If the result doesn't match expectations, it replans the remaining steps

### Undo and rollback
- Every code execution runs inside a FreeCAD transaction (Abort/Commit)
- Failed operations roll back cleanly — no orphaned geometry, no corrupted
  documents
- If the AI generates bad code, the document state is unchanged

### Parameterized template execution
- Templates: bracket, flange, pipe, gear, triangle, curved shapes, addFC,
  sketch box, PCB enclosure
- Schema-validated parameters prevent AI from generating dimensionally
  degenerate geometry (negative wall thickness, zero radii)
- Templates produce valid executable Python verified by AST pass before exec

### Gear generation (pure Part API)
- Full involute gear profile with addendum/dedendum circles, root arcs,
  tip arcs, both flank involutes — no FCGear dependency
- Falls back to MultiFuse of extruded tooth profiles if single boolean
  operation fails
- FCGear (`freecad.gears`) is disabled: it crashes FreeCAD >=1.1 through
  the InitGui.py wrapper chain

### DXF processing
- Reads R2010 ASCII/binary DXF files via ezdxf
- Extracts closed polylines/lines/arcs/circles as clean profile groups
- Warning deduplication: 692 identical lines compressed to 5 meaningful
  warning groups
- Unit auto-detection: $INSUNITS=0 → coordinate-extent heuristic
  (coords >5000 → inches, >500 → mm_uncertain, else → mm)
- Largest-area outline fallback when no layer name matches OUTLINE/BORDER/EDGE
- HATCH boundary per-entity try/except — one bad boundary never kills all
  hatches
- Open SPLINE chaining with two-pass greedy + 5% perimeter gap closure

## Architecture

```
┌─────────────────────┐
│   AISidebar (Qt)    │  ← Popup dialog, QTextEdit chat, collapsible panels
└──────┬──────────────┘
       │ QThread worker (non-blocking API calls)
┌──────▼──────────────┐
│   CodeWorker        │  ← HTTP to LLM, emits code on main thread
└──────┬──────────────┘
       │ signals
┌──────▼──────────────┐
│   _on_code_ready    │  ← Main thread: validate, execute, observe
└──────┬──────────────┘
       │
┌──────▼─────────────────────────────────────────────────┐
│ AIOrchestrator                                          │
│   - build_system_prompt()   knowledge injection engine  │
│       · RESPONSE_MODE_HEADER classifies simple/complex   │
│       · Priority/exclusion: curved shapes excluded when  │
│         gear fires; airfoil+curved co-inject wing bridge │
│       · 5 knowledge modules: gear, triangle, curved      │
│         shapes, airfoil, addFC — each with trigger regex │
│       · Always-on API corrections: view/display color    │
│         format, .rotate() fix, no makeExtrusion, hull    │
│         wire plane requirement, curved shapes pre-flight │
│   - execute_code()           sandboxed exec + transaction │
│   - call_ai()                provider dispatch + fallback │
│   - capture_obs()            diff-based observation       │
│   - validate_sketch()        AST-level constraint check   │
│   - set_board_context()      .kicad_pcb → board data      │
│   - execute_enclosure_template()  direct geometry gen     │
│   - get_fallback_code()      quick-code dispatch          │
│   - exec_macro()             runs addFC.FCMacro           │
└──────────────────────────┬──────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                  │
         ▼                 ▼                  ▼
   ┌──────────┐    ┌──────────────┐    ┌───────────┐
   │  Secret   │    │  Templates   │    │ Provider  │
   │  Store    │    │  render +    │    │ Adapters  │
   │ DPAPI/   │    │  validate    │    │ Anthropic │
   │ keyring/ │    │  bracket,    │    │ Ollama    │
   │ Fernet   │    │  flange, addFC│   │ Google    │
   └──────────┘    └──────────────┘    └───────────┘
         │
         ▼
   ┌─────────────────────────────────────────────┐
   │         PCB Enclosure Pipeline              │
   │                                             │
   │  .kicad_pcb → pcb_parser.parse()            │
   │       ↓                                     │
   │  PrecomputedGeometry (context_injector)     │
   │       ↓                                     │
   │  AI returns JSON config OR direct params    │
   │       ↓                                     │
   │  enclosure_template.build_from_parsed()     │
   │       ↓                                     │
   │  EnclosureGeometry (derived dims + shapes)  │
   │       ↓                                     │
   │  DocumentBuilder (Part::Feature + colors)   │
   │       ↓                                     │
   │  FreeCAD doc: Base, Lid, PCB ref, snaps     │
   └─────────────────────────────────────────────┘
         │
         ▼
   ┌─────────────────────────────────────────────┐
   │            DXF Pipeline                     │
   │                                             │
   │  .dxf → dxf_processor.process_dxf()         │
   │       ↓                                     │
   │  Close SPLINE chains + deduplicate warnings │
   │       ↓                                     │
   │  Profile groups: outline, holes, cutouts    │
   └─────────────────────────────────────────────┘
```

### Key design decisions

| Decision | Why |
|----------|-----|
| **Popup window, not docked** | Users want Copilot-like floating overlay, not embedded in FreeCAD's layout |
| **QThread for API calls** | UI never freezes during LLM requests (which take 2-30 seconds) |
| **Transactions for every exec** | Failed code leaves zero side effects in the document |
| **Diff-based observation** | After step 1, each step sends only ~200 token delta instead of 3000 token full scene |
| **AST-level sketch validation** | Catches bad geometry indices before exec() — no C++ crash |
| **Shape-hash diff** | Detects modifications through transient intermediate objects |
| **Provider adapters** | Drop-in support for any OpenAI-compatible LLM or Ollama local model |
| **Knowledge injection with priority/exclusion** | Curved shapes suppressed when gear fires; airfoil+curved co-inject wing bridge; addFC always orthogonal — prevents contradictory advice |
| **Response mode header** | System prompt starts with SIMPLE/COMPLEX classifier — simple requests get code without planning preamble, reducing latency and hallucinated steps |
| **Templates over raw code gen** | Schema-validated templates produce dimensionally safe geometry; AI only fills JSON params, never writes raw Part primitives |
| **Direct ViewObject guard** | `_set_color()` wraps all display API calls in hasattr checks — no crash in headless FreeCAD console mode |

### Safety mechanisms

1. **Safe exec scope** — blocked imports (os, sys, subprocess, socket, etc.),
   only FreeCAD API + math available
2. **AST validation** — sketch constraint indices checked against running
   geometry counter before execution; template code validated before any mock
   exec
3. **Transaction rollback** — abort on any exception, document stays clean
4. **Observation feedback loop** — AI sees exactly what changed after each
   step, enabling self-correction
5. **Maximum retries** — 5 retries per step with error-analysis prompts
6. **Thread safety** — `_cancel` flag suppresses signal handlers after stop;
   threads finish naturally instead of being terminated mid-operation
7. **Mutation guard tests** — every knowledge module's `should_inject_*`
   can be toggled off independently; always-on API corrections survive all
   toggles
8. **Secret store** — three backends (Windows DPAPI, system keyring, Fernet
   encrypted file) prevent API keys from leaking into plain-text config

## Current Limitations

- **No mesh editing** — can import/export STL but can't sculpt or remesh
- **No FEM analysis** — can read results but not set up simulations
- **No reverse engineering** — can't reconstruct parametric features from
  plain meshes (yet)
- **3D view alignment** — works but viewport fit isn't always perfect on
  first attempt
- **Loops in generated code** — AST validator doesn't fully unroll dynamic
  loops (for x in range(N) with non-constant N)
- **PCB enclosure FreeCAD verification** — geometric output cannot be
  visually verified without a real FreeCAD instance (CI runs headless)
- **DXF SPLINE chaining** — greedy endpoint matching works for gaps <5%
  perimeter; wider gaps between disconnected SPLINE segments are not
  bridged

## Why This Didn't Exist Before

Three things had to converge:

1. **LLMs good enough to write CAD code** — DeepSeek, GPT-4o, and similar
   models can now produce FreeCAD Python that correctly handles its unusual
   API (vertex index 1/2 not 0, `AttachmentSupport` not `Support`,
   `InList` not `InListRecursive`)

2. **Orchestration layer** — the hard part isn't the AI call, it's the
   scaffolding around it: safe exec with transactions, diff-based observation
   compression, AST-level constraint validation, multi-step plan state
   machines, knowledge injection with priority/exclusion, template execution
   with schema validation, provider failover, Qt threading with proper
   cancellation, secret storage, and 238+ automated tests

3. **Someone willing to grind** — FreeCAD's Python API has undocumented
   edge cases. Half the work was discovering which API objects actually work
   vs what the documentation claims. The sketch constraint validator alone
   required understanding FreeCAD's geo-index tracking at the point of
   constraint creation, not at the end of the code block. The enclosure
   generator required reverse-engineering KiCad's S-expression format to
   avoid any workbench dependency.

## Competitive Landscape (2026)

| Competitor | Approach | Gap |
|------------|----------|-----|
| **Autodesk** | Cloud generative design | No chat, no Python exec, no FreeCAD |
| **Fusion 360 AI** | Parametric hints | No autonomous execution |
| **SolidWorks** | Demos only | Not shipped |
| **Onshape** | No AI feature | API-only |
| **Generic GPT plugins** | Raw code gen | No safety, no transactions, no validation |

We're the only open-source, fully autonomous CAD agent with rollback safety,
multi-step plan execution, workbench-agnostic Python execution, PCB enclosure
generation, parameterized template validation, DXF processing with closed
profile extraction, and headless-safe geometry building with 238 integration
tests running in CI without FreeCAD installed.

## Near-Term Roadmap

- [x] Chat UI with mode/model selection
- [x] Build / Plan / Ask modes
- [x] Multi-step plan execution
- [x] Transaction rollback
- [x] Sketch constraint AST validator
- [x] Diff-based observation compression
- [x] Provider fallback + adapters
- [x] Thread-safe cancellation
- [x] Mode-preserving plan state
- [x] Self-critique hook
- [x] Knowledge injection engine (5 modules, priority/exclusion, API corrections)
- [x] Parameterized template system (bracket, flange, pipe, gear, triangle, addFC)
- [x] Gear generation via pure Part API (FCGear disabled)
- [x] Secret store (DPAPI / keyring / Fernet)
- [x] PCB enclosure pipeline (parser → precompute → template → DocumentBuilder)
- [x] DXF processor with warning de (simple/complex classification)
- [x] View/display API corrections (always-on)
- [x] 238 automated tests (zero FreeCAD required, zero API calls)duplication, unit detection, SPLINE chaining
- [x] Response mode header
- [ ] FEM setup assistant
- [ ] Mesh repair / simplification
- [ ] Image-to-CAD (import picture → trace → extrude)
- [ ] Batch rendering of design variants
- [ ] Export profiles (STL, STEP, SVG, PDF)
- [ ] Manual FreeCAD verification of Part API gear, enclosure, and DXF output
