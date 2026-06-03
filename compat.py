# compat.py — PySide2/PySide6 compatibility shim
import sys as _sys

class _DummyQt:
    class Qt:
        @staticmethod
        def NoPen(): return 0
        @staticmethod
        def transparent(): return 0
    class QPoint:
        def __init__(self, *a): pass
    class QColor:
        def __init__(self, *a): pass
    class QPixmap:
        def __init__(self, *a): pass
    class QPainter:
        def __init__(self, *a): pass
        def setRenderHint(self, *a): pass
        def setBrush(self, *a): pass
        def setPen(self, *a): pass
        def drawRoundedRect(self, *a): pass
        def drawPolygon(self, *a): pass
        def drawEllipse(self, *a): pass
        def end(self): pass
    class QWidget:
        pass

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Qt, Signal
except ImportError:
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
        from PySide2.QtCore import Qt, Signal
    except ImportError:
        QtWidgets = _DummyQt()
        QtCore = _DummyQt()
        QtGui = _DummyQt()
        Qt = _DummyQt.Qt()
        Signal = lambda x: (lambda f: f)
