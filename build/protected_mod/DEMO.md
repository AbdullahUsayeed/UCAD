# AI Companion — Live Demo Script

This demo walks through 7 capabilities that no other CAD AI can do.
Open FreeCAD, switch to the AI Companion workbench, and run each prompt in order.

---

## 1. Natural language → parametric 3D

```
design a 3D-printed phone stand with:
- a sloped face at 60 degrees
- a cable management hole on the back
- rounded edges
- 120mm wide, 80mm deep, 150mm tall
```

What happens: The AI plans the steps, creates a sketch, pads it, cuts the hole, adds fillets.
Each step is shown in the object tree as it builds. The 3D view updates live.

---

## 2. Multi-step autonomous construction

```
build a parametric bracket that connects two perpendicular 40x40 aluminum extrusions
with 4 bolt holes and a lightening pocket
```

What happens: The AI generates a 5-6 step plan (sketch → pad → cut holes → pocket → fillets),
executes it sequentially, and self-corrects if any step fails. The plan is visible as progress:
"Step 2/6: Cutting bolt holes ✓"

---

## 3. Auto-constrain a hand-drawn sketch

1. In FreeCAD, draw a rough rectangle with the polyline tool (don't add constraints)
2. Type:

```
add constraints to this sketch to make it fully constrained, then pad it 20mm
```

What happens: The AI reads the sketch geometry, detects overlapping endpoints,
adds coincident + horizontal + vertical + dimension constraints, then pads it.
Your sloppy polyline becomes an accurate parametric rectangle.

---

## 4. Measure and analyze

```
measure the volume and center of mass of everything in this document
```

What happens: The AI reads all shapes, computes volume/area/center of mass/bounding box
for each, and reports the results in the chat.

---

## 5. Edit existing files

Open any existing FreeCAD file and type:

```
make this 50% larger while keeping the proportions, and add a mounting flange
```

What happens: The AI reads every object in the document, adjusts the dimensions
proportionally, and creates a new flange feature. It works on any FreeCAD file.

---

## 6. Multi-document workflow

```
create a new document with a 100x60x40 box, then switch back to the previous document
and add a hole to the first object
```

What happens: The AI manages multiple documents, switches between them,
creates objects in one, edits objects in another. All visible in the 3D view.

---

## 7. The "I'm too lazy to model this" special

```
import this step file and generate a 2mm wall enclosure with standoffs at the PCB corners
```

What happens: The AI imports the STEP, reads the PCB's bounding box and hole positions,
generates a parametric enclosure with the exact cutouts needed.

(Requires a STEP file on disk — adjust the path.)

---

## How the AI sees your document

The AI reads the full FreeCAD document state before every response:

```
what is in the current document?
```

It will list every object, its type, dimensions, position, sketch geometry/constraints,
material color, and parent-child relationships — all from the live document.

---

## Pro tips

- Say **"make a plan first"** to see the AI's strategy before it executes
- Say **"undo that"** to roll back the last operation
- Click **"✚"** in the header to start a completely fresh conversation
- The ⚙ button lets you switch between DeepSeek, GPT-4o, and local Ollama models
- The OBJECTS panel shows live updates of the FreeCAD document tree
- Click **"Show generated code"** to inspect the Python the AI wrote
