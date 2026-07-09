class _DummyQt:
    class Qt:
        @staticmethod
        def NoPen():
            return 0
        @staticmethod
        def transparent():
            return 0
    class QPoint:
        def __init__(self, *a):
            pass
    class QColor:
        def __init__(self, *a):
            pass
    class QPixmap:
        def __init__(self, *a):
            pass
    class QPainter:
        def __init__(self, *a):
            pass
        def setRenderHint(self, *a):
            pass
        def setBrush(self, *a):
            pass
        def setPen(self, *a):
            pass
        def drawRoundedRect(self, *a):
            pass
        def drawPolygon(self, *a):
            pass
        def drawEllipse(self, *a):
            pass
        def end(self):
            pass
    class QWidget:
        pass
def _detect_qt():
    try:
        import FreeCADGui
        binding = getattr(FreeCADGui, 'qt_binding', None)
        if binding == 'PySide2':
            from PySide2 import QtWidgets, QtCore, QtGui
            from PySide2.QtCore import Qt, Signal
            return (QtWidgets, QtCore, QtGui, Qt, Signal)
        if binding == 'PySide6':
            from PySide6 import QtWidgets, QtCore, QtGui
            from PySide6.QtCore import Qt, Signal
            return (QtWidgets, QtCore, QtGui, Qt, Signal)
    except ImportError:
        pass
    try:
        from PySide6 import QtWidgets, QtCore, QtGui
        from PySide6.QtCore import Qt, Signal
        return (QtWidgets, QtCore, QtGui, Qt, Signal)
    except ImportError:
        try:
            from PySide2 import QtWidgets, QtCore, QtGui
            from PySide2.QtCore import Qt, Signal
            return (QtWidgets, QtCore, QtGui, Qt, Signal)
        except ImportError:
            pass
    return (_DummyQt(), _DummyQt(), _DummyQt(), _DummyQt.Qt(), lambda x: lambda f: f)
QtWidgets, QtCore, QtGui, Qt, Signal = _detect_qt()
