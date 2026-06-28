# UCAD Assistant

CAD should not require a manual.

[![Demo Video](https://img.youtube.com/vi/-gEuExxmy0Y/0.jpg)](https://www.youtube.com/watch?v=-gEuExxmy0Y)

## The Problem

A brilliant engineer had a hardware product ready to launch. The circuit boards were done. The firmware was done. Then he opened a CAD tool.

Months passed. The product never shipped.

Not because he wasn't smart enough. Because CAD tools were designed for people who already know CAD.

That ends today.

## What UCAD Is

UCAD is a FreeCAD workbench that understands what you want to build — and builds it.

You type. It designs.

Not with a chatbot that guesses and crashes. With a purpose-built engineering agent that knows FreeCAD's API at the level of someone who has shipped real hardware — because every mistake it doesn't make was caught in production first.

## Three Things It Does

**Design anything in plain English.** Gears, brackets, airfoils, enclosures. Type what you need. Get working geometry. No commands to memorize. No documentation to read.

**Turn a DXF file into a 3D model.** Upload a raw profile. UCAD cleans it, normalizes it, and builds the 3D shape — handling the edge cases that crash every other tool.

**Generate a PCB enclosure from your KiCad file.** Drop in your `.kicad_pcb`. Get a production-ready, 3D-printable enclosure with the lid and shell as separate bodies, mounting bosses at your hole positions, and cutouts sized exactly for your connectors.

## Why It Works When Others Don't

Most AI CAD tools are a language model with a FreeCAD import. They hallucinate APIs. They crash silently. They produce geometry that looks right and measures wrong.

UCAD is different because we did the work nobody else wanted to do.

We found that `Part.makeExtrusion()` does not exist — and built a correction so the AI never tries it. We found that hull wires in CurvedShapes must lie in a principal plane or you get silent zero-volume output — and made that rule #1. We found that a single DXF file can generate 692 identical warnings — and reduced it to 5 meaningful ones.

300 automated tests. Zero FreeCAD required to run them. Every bug below was caught before a single user saw it:

- Curved shapes were silently suppressed whenever a gear was requested
- A single line would have killed the entire FreeCAD process on addFC install
- PCB enclosure crashed in headless mode due to a missing viewport guard
- DXF coordinates placed geometry 33 kilometers from the origin
- Degenerate vertices caused unrecoverable geometry errors with no explanation

This is not vibe-coded. This is engineered.

## Getting Started

### Install

```
git clone https://github.com/AbdullahUsayeed/UCAD.git
```

Copy the `UCAD` folder to your FreeCAD Mod directory:

| OS | Path |
|----|------|
| Windows | `%APPDATA%\FreeCAD\v1-1\Mod\` |
| Linux | `~/.local/share/FreeCAD/Mod/` |
| macOS | `~/Library/Application Support/FreeCAD/Mod/` |

Install dependencies:

```
# Windows
"C:\Program Files\FreeCAD 1.1\bin\python.exe" -m pip install -r requirements.txt

# Linux / macOS
/path/to/freecad-python -m pip install -r ~/.local/share/FreeCAD/Mod/UCAD/requirements.txt
```

### Start

1. Open FreeCAD — select **UCAD Assistant** from the workbench dropdown
2. Press **Ctrl+Shift+A** to open the copilot
3. Enter your API key in Settings
4. Type what you want to build

**Recommended model:** Claude Opus 4. UCAD's knowledge injection means you get great results on smaller models too — but Opus follows the engineering rules precisely.

## What It Knows

| Topic | Depth |
|-------|-------|
| Gears | Full involute math via Part API — FCGear disabled, it crashes FreeCAD >=1.1 |
| CurvedShapes | Hull wire plane rules baked in — the mistake that silently breaks every wing |
| PartDesign | Sketch attachment, Pad/Pocket types, Body patterns |
| DXF | Unit detection, coordinate normalization, profile repair, degenerate vertex removal |
| PCB | KiCad parser, enclosure geometry, connector sizing, named model tree |

## Requirements

- FreeCAD 1.1+
- An API key from Anthropic, OpenAI, Google, Groq — or run locally with Ollama (no key needed)
- Windows primary — Linux and macOS should work

## License

Proprietary. Requires a valid license key.

[Get UCAD →](https://ai-companion-licensing.usayeed10.workers.dev/checkout?plan=yearly)

---

*The best CAD tool is the one that gets out of your way.*
