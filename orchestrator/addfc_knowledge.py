"""addFC add-on manager knowledge, scoped-injected into the system
prompt when the user asks about installing workbenches or running
macros via addFC. No dependency on the orchestrator core (import-safe)."""

import re

ADDFC_KNOWLEDGE = """

## addFC — FreeCAD Add-on Manager (NOT the built-in Addon Manager)

addFC is a third-party add-on manager / macro runner for FreeCAD, distinct
from FreeCAD's built-in Tools → AddonManager. Use it to install, update, and
manage workbenches and macros from community repositories.

### Programmatic usage (headless / macro):

1. Download `addFC.FCMacro` from https://github.com/triplus/Add (or another trusted source)
2. Place it in FreeCAD's macro directory
3. Execute with:

```python
import addFC  # or exec(open('path/to/addFC.FCMacro').read())

# Run the addFC GUI (not headless — requires GUI)
FreeCADGui.execCommand("addFC")

# To check available workbenches programmatically, list the addFC module:
if hasattr(addFC, 'available_workbenches'):
    wbs = addFC.available_workbenches()
```

### Important notes:
1. addFC is NOT the same as FreeCAD.Tools.AddonManager — do not confuse them.
2. addFC has no `.install()` or `.run()` method — it is a GUI-driven macro.
   Use `FreeCADGui.execCommand('addFC')` to launch its GUI.
3. For SILENT / unattended installation, use the built-in AddonManager:
   `FreeCADGui.addonManager().installWorkbench('WorkbenchName')`
4. Version compatibility: some addFC versions may lag behind FreeCAD releases.
   If addFC errors on import, the user may need the latest version from GitHub.
5. To call addFC from headless mode: not supported — it requires the GUI.
"""

_ADDFC_TRIGGERS = re.compile(
    r"\b(addfc|add-fc|addon\s*manager|macro\s*runner|install\s+addon|install\s+macro)\b",
    re.IGNORECASE,
)

ADDFC_API_CORRECTION = {
    "id": "addfc_no_install",
    "requires_context": None,
    "pre_pattern": r"addFC\.(?:install|run)\b",
    "error_pattern": r"addFC has no attribute 'install'|addFC has no attribute 'run'",
    "mistake": "`addFC.install()` and `addFC.run()` do not exist — addFC is a GUI-driven macro, not a library.",
    "fix": "Use `FreeCADGui.execCommand('addFC')` to launch the addFC GUI. For silent installation, use the built-in AddonManager: `FreeCADGui.addonManager().installWorkbench(...)`.",
    "example": "# Launch addFC GUI:\nFreeCADGui.execCommand('addFC')\n\n# Silent install via built-in AddonManager:\nFreeCADGui.addonManager().installWorkbench('WorkbenchName')",
}


def should_inject_addfc(user_input):
    """Check if user input triggers addFC knowledge injection."""
    if not user_input:
        return False
    return bool(_ADDFC_TRIGGERS.search(user_input))
