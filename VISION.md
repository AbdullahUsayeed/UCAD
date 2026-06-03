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

### Measure and analyze
- Compute volume, area, center of mass, bounding box of any shape
- Measure distances between faces, edges, vertices
- Detect mounting holes, connector positions, cutouts
- Generate clearance envelopes for enclosure design

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
┌──────▼──────────────┐
│ AIOrchestrator      │  ← Knowledge base, exec scope, transactions
│   - build_messages  │     observation, diff, constraint validation
│   - execute_code    │
│   - call_ai         │
│   - capture_obs     │
│   - validate_sketch │
└─────────────────────┘
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

### Safety mechanisms

1. **Safe exec scope** — blocked imports (os, sys, subprocess, socket, etc.),
   only FreeCAD API + math available
2. **AST validation** — sketch constraint indices checked against running
   geometry counter before execution
3. **Transaction rollback** — abort on any exception, document stays clean
4. **Observation feedback loop** — AI sees exactly what changed after each
   step, enabling self-correction
5. **Maximum retries** — 5 retries per step with error-analysis prompts
6. **Thread safety** — `_cancel` flag suppresses signal handlers after stop;
   threads finish naturally instead of being terminated mid-operation

## Current Limitations

- **No mesh editing** — can import/export STL but can't sculpt or remesh
- **No FEM analysis** — can read results but not set up simulations
- **No reverse engineering** — can't reconstruct parametric features from
  plain meshes (yet)
- **3D view alignment** — works but viewport fit isn't always perfect on
  first attempt
- **Loops in generated code** — AST validator doesn't fully unroll dynamic
  loops (for x in range(N) with non-constant N)

## Why This Didn't Exist Before

Three things had to converge:

1. **LLMs good enough to write CAD code** — DeepSeek, GPT-4o, and similar
   models can now produce FreeCAD Python that correctly handles its unusual
   API (vertex index 1/2 not 0, `AttachmentSupport` not `Support`,
   `InList` not `InListRecursive`)

2. **Orchestration layer** — the hard part isn't the AI call, it's the
   scaffolding around it: safe exec with transactions, diff-based observation
   compression, AST-level constraint validation, multi-step plan state
   machines, provider failover, Qt threading with proper cancellation

3. **Someone willing to grind** — FreeCAD's Python API has undocumented
   edge cases. Half the work was discovering which API objects actually work
   vs what the documentation claims. The sketch constraint validator alone
   required understanding FreeCAD's geo-index tracking at the point of
   constraint creation, not at the end of the code block.

## Competitive Landscape (2026)

| Competitor | Approach | Gap |
|------------|----------|-----|
| **Autodesk** | Cloud generative design | No chat, no Python exec, no FreeCAD |
| **Fusion 360 AI** | Parametric hints | No autonomous execution |
| **SolidWorks** | Demos only | Not shipped |
| **Onshape** | No AI feature | API-only |
| **Generic GPT plugins** | Raw code gen | No safety, no transactions, no validation |

We're the only open-source, fully autonomous CAD agent with rollback safety,
multi-step plan execution, and workbench-agnostic Python execution.

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
- [ ] FEM setup assistant
- [ ] Mesh repair / simplification
- [ ] Image-to-CAD (import picture → trace → extrude)
- [ ] Batch rendering of design variants
- [ ] Export profiles (STL, STEP, SVG, PDF)
