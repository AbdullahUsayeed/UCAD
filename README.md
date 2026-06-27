# UCAD Assistant — AI CAD Agent for FreeCAD

Build, edit, and automate parametric designs in FreeCAD through natural language chat. Supports PCB enclosure generation, DXF cleaning, gear design, and multi-step autonomous plan execution.

## Installation

### Option A: FreeCAD Addon Manager (recommended)

1. Open FreeCAD → **Tools → Addon Manager**
2. Go to the **Workbenches** tab
3. Search for **UCAD Assistant** (or **AICompanion**)
4. Click **Install**
5. Restart FreeCAD

The Addon Manager will install pip dependencies automatically (ezdxf, shapely).

### Option B: Manual install from GitHub

1. Download the repo as ZIP or clone:
   ```bash
   git clone https://github.com/AbdullahUsayeed/UCAD.git
   ```
2. Move the folder to FreeCAD's Mod directory:
   - **Windows**: `%APPDATA%\FreeCAD\v1-1\Mod\`
   - **Linux**: `~/.local/share/FreeCAD/Mod/`
   - **macOS**: `~/Library/Preferences/FreeCAD/Mod/`
3. **Install pip dependencies** (required for DXF processing and LLM support):
   ```bash
   # Using FreeCAD's bundled Python (Windows):
   "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m pip install -r requirements.txt

   # Or regenerate the vendored deps directory:
   python tools/update_deps.py
   ```
4. Restart FreeCAD and select **UCAD Assistant** from the workbench dropdown

### Option C: Bundled release (coming soon)

Pre-built ZIPs with all dependencies bundled will be available from the Releases page.

## Quick Start

1. Select the **UCAD Assistant** workbench from the dropdown
2. Click the **Open AI Copilot** button (or press `Ctrl+Shift+A`)
3. Enter your API key in the settings dialog
4. Start typing design requests like:
   - *"Create a 50x30x20mm box with a lid"*
   - *"Add a hole at (25,15,0) with 5mm radius"*
   - *"Generate a gear with 20 teeth and 2mm module"*

## Layout

```
UCAD/
  InitGui.py          — Workbench registration + dep bootstrap
  AICompanionGui.py   — Sidebar UI and command integration
  orchestrator/       — AI orchestration, providers, execution
  tools/              — Build scripts and utilities
  tests/              — Test suite (300+ tests)
  package.xml         — Addon Manager metadata
  requirements.txt    — Python dependencies
  .python-deps/       — Vendored dependencies (generated)
```

## Dependencies

| Package | Required | Purpose |
|---------|----------|---------|
| `litellm` | Yes | Unified LLM API (100+ providers) |
| `ezdxf` | Yes | DXF file processing |
| `shapely` | Yes | 2D geometry operations |
| `keyring` | No | Linux/macOS secret storage |
| `cryptography` | No | Encrypted file fallback |

On Windows, secret storage uses DPAPI natively — no extra packages needed.

## Development

```bash
# Run tests
pytest --tb=short -q

# Regenerate vendored dependencies
python tools/update_deps.py

# Build an obfuscated release
python tools/build_release.py
```

## License

Proprietary — All Rights Reserved. Requires a valid license key. See [licensing server](https://ai-companion-licensing.usayeed10.workers.dev) for purchase.
