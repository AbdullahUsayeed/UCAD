# InitGui.py - FreeCAD AI Companion Workbench V4
import FreeCAD, FreeCADGui

def _make_icon():
    from compat import QtCore, QtGui
    pm = QtGui.QPixmap(32, 32)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setBrush(QtGui.QColor("#0e639c"))
    p.setPen(QtCore.Qt.NoPen)
    p.drawRoundedRect(5, 3, 22, 26, 5, 5)
    p.setBrush(QtGui.QColor("#6af7b8"))
    p.drawPolygon([QtCore.QPoint(16, 9), QtCore.QPoint(23, 18), QtCore.QPoint(9, 18)])
    p.setBrush(QtGui.QColor("#f7c96a"))
    p.drawEllipse(20, 11, 4, 4)
    p.end()
    return pm

class AICompanionCommand:
    def GetResources(self):
        try:
            pix = _make_icon()
        except Exception:
            pix = None
        return {
            'Pixmap': pix if pix else "",
            'MenuText': 'Open AI Copilot',
            'ToolTip': 'Open AI design assistant (Ctrl+Shift+A)',
            'Accel': 'Ctrl+Shift+A'
        }
    
    def Activated(self):
        try:
            from AICompanionGui import show_sidebar
            show_sidebar()
        except Exception as e:
            import traceback
            FreeCAD.Console.PrintError(f"AICompanion: {e}\n{traceback.format_exc()}\n")

# Register command
try:
    FreeCADGui.addCommand('AI_Companion_Command', AICompanionCommand())
except Exception as e:
    FreeCAD.Console.PrintError(f"AICompanion: failed to register command: {e}\n")

class AICompanionWorkbench(FreeCADGui.Workbench):
    MenuText = "AI Companion"
    ToolTip = "AI CAD Agent: Sketches, Booleans, Templates, Multi-Docs"
    
    def Initialize(self):
        self.appendToolbar("AI Tools", ["AI_Companion_Command"])
        self.appendMenu("AI Copilot", ["AI_Companion_Command"])
        # Auto-show sidebar when switching to this workbench
        try:
            from AICompanionGui import show_sidebar
            show_sidebar()
        except Exception:
            pass
    
    def Activated(self):
        # Show sidebar every time this workbench is activated
        try:
            from AICompanionGui import show_sidebar
            show_sidebar()
        except Exception:
            pass
    
    def GetClassName(self):
        return "Gui::PythonWorkbench"

# Register workbench
try:
    FreeCADGui.addWorkbench(AICompanionWorkbench())
except Exception as e:
    FreeCAD.Console.PrintError(f"AICompanion: failed to register workbench: {e}\n")
