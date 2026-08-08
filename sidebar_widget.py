from compat import QtWidgets, QtCore, QtGui, Qt, Signal
import math

# ══════════════════════════════════════════════════════════════════════════════
#  Usayeed AI — Design System  "Liquid Glass Terminal"
#
#  Concept: Every surface is a floating glass panel hovering above a slow-
#  scrolling holographic dot grid.  A single iridescent top-edge (cyan→violet)
#  acts as the consistent light source across ALL panels, giving the UI depth.
#  Typography is UPPERCASE + tracked throughout — cockpit / mission-control
#  register.  Animations are calm, purposeful, never decorative.
#
#  Signature element: animated dot-matrix background + iridescent panel edges.
# ══════════════════════════════════════════════════════════════════════════════

# ── Named color tokens ────────────────────────────────────────────────────────
_VOID  = QtGui.QColor(8,   9, 10)        # ultra-deep obsidian background
_GS0   = QtGui.QColor(15, 16, 18, 217)   # primary glass surface
_GS1   = QtGui.QColor(22, 23, 26, 178)   # raised glass (header, input)
_GS2   = QtGui.QColor(17, 18, 20, 128)   # low glass (selector bar)
_EDGE  = QtGui.QColor(255, 255, 255, 18) # micro rim highlight
_DOT   = QtGui.QColor(100, 110, 130, 22) # background dot (slate, not cyan)
_CYAN  = QtGui.QColor(0,  240, 255)      # laser accent — use sparingly
_VIO   = QtGui.QColor(192, 132, 252)     # secondary accent
_PINK  = QtGui.QColor(255,  45, 120)     # deep-think / alert accent

# ── CSS string aliases ────────────────────────────────────────────────────────
_sVOID = "#08090a"
_sCYAN = "#00f0ff"
_sVIO  = "#c084fc"
_sPINK = "#ff2d78"
_sTEXT = "#ebedf0"
_sSUB  = "#8a9099"
_sMUTE = "#4a4f57"

_sBDR  = "rgba(255,255,255,0.05)"      # idle border — almost invisible
_sBHOV = "rgba(255,255,255,0.10)"      # hover — still very subtle
_sBACT = "rgba(0,240,255,0.25)"        # active/focus — only place cyan appears
_sEDGE = "rgba(255,255,255,0.06)"      # top-edge sheen

_sGS0  = "rgba(15,16,18,0.85)"
_sGS1  = "rgba(22,23,26,0.70)"
_sGS2  = "rgba(17,18,20,0.50)"


# ══════════════════════════════════════════════════════════════════════════════
#  Stylesheet fragments
# ══════════════════════════════════════════════════════════════════════════════

_SS_COMBO = f"""
    QComboBox {{
        background : {_sGS1};
        color      : {_sTEXT};
        border     : 1px solid {_sBDR};
        border-top : 1px solid {_sEDGE};
        border-radius : 6px;
        font-size  : 9px;
        font-weight: 700;
        letter-spacing : 0.8px;
        padding    : 2px 8px;
    }}
    QComboBox:hover {{
        background : rgba(255,255,255,0.03);
        color      : {_sTEXT};
    }}
    QComboBox:focus  {{ border-color: {_sBACT}; }}
    QComboBox::drop-down {{ border: none; width: 0; }}
    QComboBox QAbstractItemView {{
        background : #0f1012;
        border     : 1px solid rgba(255,255,255,0.08);
        border-radius : 6px;
        color      : {_sTEXT};
        font-size  : 9px;
        font-weight: 600;
        letter-spacing : 0.7px;
        padding    : 4px;
        selection-background-color : rgba(255,255,255,0.06);
        selection-color : {_sTEXT};
        outline    : none;
    }}
    QComboBox QAbstractItemView::item {{
        padding       : 4px 8px;
        border-radius : 3px;
    }}
"""

_SS_HDR_BTN = f"""
    QPushButton {{
        background    : {_sGS1};
        color         : {_sSUB};
        border        : 1px solid {_sBDR};
        border-top    : 1px solid {_sEDGE};
        border-radius : 5px;
        font-size     : 11px;
    }}
    QPushButton:hover {{
        background   : rgba(255,255,255,0.04);
        color        : {_sTEXT};
        border-color : {_sBHOV};
    }}
    QPushButton:pressed {{
        background : rgba(255,255,255,0.08);
    }}
"""

_SS_BUTTON_SMALL = f"""
    QPushButton {{
        background    : {_sGS1};
        color         : {_sSUB};
        border        : 1px solid {_sBDR};
        border-top    : 1px solid {_sEDGE};
        border-radius : 4px;
        font-size     : 11px;
        padding       : 0px;
    }}
    QPushButton:hover {{
        background   : rgba(255,255,255,0.04);
        color        : {_sTEXT};
        border-color : {_sBHOV};
    }}
    QPushButton:pressed {{
        background : rgba(255,255,255,0.08);
    }}
"""

_SS_INPUT = f"""
    QTextEdit {{
        background : transparent;
        color      : {_sTEXT};
        border     : 1px solid transparent;
        border-radius : 4px;
        font-size  : 13px;
        font-family: 'SF Pro Display','Segoe UI','Inter',Arial,sans-serif;
        selection-background-color : rgba(0,240,255,0.18);
        padding    : 2px 4px;
    }}
    QTextEdit:focus {{
        border     : 1px solid rgba(0,240,255,0.12);
        background : rgba(0,240,255,0.02);
    }}
"""

_SS_SEND = f"""
    QPushButton {{
        background    : {_sGS1};
        color         : {_sSUB};
        border        : 1px solid {_sBDR};
        border-top    : 1px solid {_sEDGE};
        border-radius : 5px;
        font-size     : 16px;
    }}
    QPushButton:hover {{
        background   : rgba(0,240,255,0.08);
        color        : {_sCYAN};
        border-color : rgba(0,240,255,0.20);
    }}
    QPushButton:pressed {{
        background : rgba(0,240,255,0.15);
    }}
"""
_SS_MINI = f"""
    QPushButton {{
        background    : {_sGS1};
        color         : {_sSUB};
        border        : 1px solid {_sBDR};
        border-radius : 4px;
        font-size     : 8px;
        font-weight   : 700;
        letter-spacing: 0.7px;
        padding       : 1px 6px;
    }}
    QPushButton:hover {{
        background   : rgba(255,255,255,0.04);
        color        : {_sTEXT};
        border-color : {_sBHOV};
    }}
"""

_SS_TABS = f"""
    QTabWidget::pane {{
        background    : {_sGS0};
        border        : 1px solid {_sBDR};
        border-top    : 1px solid {_sEDGE};
        border-radius : 8px;
    }}
    QTabBar::tab {{
        background         : transparent;
        color              : {_sMUTE};
        border             : none;
        border-bottom      : 1.5px solid transparent;
        padding            : 4px 14px;
        font-size          : 8px;
        font-weight        : 700;
        letter-spacing     : 1.2px;
        margin-right       : 1px;
    }}
    QTabBar::tab:selected {{
        color         : {_sTEXT};
        border-bottom : 1.5px solid {_sTEXT};
    }}
    QTabBar::tab:hover:!selected {{
        color         : {_sSUB};
        border-bottom : 1.5px solid rgba(255,255,255,0.08);
    }}
"""

_SS_SCROLLBAR = """
    QScrollBar:vertical {
        background : transparent;
        width      : 3px;
        margin     : 0;
    }
    QScrollBar::handle:vertical {
        background    : rgba(255,255,255,0.10);
        border-radius : 2px;
        min-height    : 20px;
    }
    QScrollBar::handle:vertical:hover {
        background : rgba(255,255,255,0.18);
    }
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical { height: 0; }
"""


# ══════════════════════════════════════════════════════════════════════════════
#  Helper widgets
# ══════════════════════════════════════════════════════════════════════════════

class _DotGridBg(QtWidgets.QWidget):
    """
    Full-bleed background widget.
    Paints a deep void + a slow-drifting holographic dot matrix.
    Sits behind everything via .lower().
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._phase = 0.0
        t = QtCore.QTimer(self, interval=40)
        t.timeout.connect(self._tick)
        t.start()

    def _tick(self):
        self._phase = (self._phase + 0.018) % (2 * math.pi)
        self.update()

    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(self.rect(), _VOID)

        bloom = QtGui.QRadialGradient(w * 0.5, -h * 0.05, h * 0.6)
        bloom.setColorAt(0.0, QtGui.QColor(30, 35, 45, 30))
        bloom.setColorAt(1.0, QtGui.QColor(0, 0, 0,   0))
        p.fillRect(self.rect(), bloom)

        spacing = 24
        dot_r   = 0.9
        drift   = (self._phase / (2 * math.pi)) * spacing

        p.setPen(QtCore.Qt.NoPen)
        for xi in range(-1, w // spacing + 2):
            for yi in range(-1, h // spacing + 2):
                rx = xi * spacing + drift
                ry = yi * spacing + drift * 0.6
                if not (-spacing <= rx <= w + spacing and
                        -spacing <= ry <= h + spacing):
                    continue
                wave = math.sin(xi * 0.55 + yi * 0.38 + self._phase * 2)
                alpha = int(6 + 8 * wave)
                if alpha < 1:
                    continue
                c = QtGui.QColor(_DOT)
                c.setAlpha(max(0, min(255, alpha)))
                p.setBrush(c)
                p.drawEllipse(QtCore.QPointF(rx, ry), dot_r, dot_r)


class _GlassPanel(QtWidgets.QFrame):
    """
    A container that paints a layered glass-morphism background:
      1. Semi-opaque dark-blue fill
      2. Inner top-sheen gradient
      3. Iridescent top-edge bar
      4. Hairline border
    """

    def __init__(self, radius=10, glass_color=None,
                 accent_top=False, parent=None):
        super().__init__(parent)
        self._r   = radius
        self._gc  = glass_color if glass_color is not None else _GS0
        self._top = accent_top
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rf = QtCore.QRectF(self.rect())

        path = QtGui.QPainterPath()
        path.addRoundedRect(rf, self._r, self._r)

        p.fillPath(path, self._gc)

        sheen = QtGui.QLinearGradient(0, 0, 0, rf.height() * 0.55)
        sheen.setColorAt(0.0, QtGui.QColor(255, 255, 255, 9))
        sheen.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
        p.fillPath(path, sheen)

        if self._top:
            ew = rf.width() - self._r * 1.2
            ex = rf.x() + self._r * 0.6
            edge_rect = QtCore.QRectF(ex, rf.y() + 0.5, ew, 1.0)
            eg = QtGui.QLinearGradient(ex, 0, ex + ew, 0)
            eg.setColorAt(0.00, QtGui.QColor(255, 255, 255,  0))
            eg.setColorAt(0.35, QtGui.QColor(255, 255, 255, 55))
            eg.setColorAt(0.65, QtGui.QColor(255, 255, 255, 55))
            eg.setColorAt(1.00, QtGui.QColor(255, 255, 255,  0))
            p.setPen(QtCore.Qt.NoPen)
            p.fillRect(edge_rect, eg)
        else:
            hl = QtCore.QRectF(rf.x() + self._r * 0.5, rf.y() + 0.5,
                               rf.width() - self._r, 0.8)
            p.setPen(QtCore.Qt.NoPen)
            p.fillRect(hl, _EDGE)

        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 16), 1.0))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawPath(path)


class _BeaconDot(QtWidgets.QWidget):
    """
    Animated status beacon: a solid core dot surrounded by a slow
    breathing pulse ring.
    """

    def __init__(self, color=None, parent=None):
        super().__init__(parent)
        self._color = color if color is not None else _CYAN
        self._phase = 0.0
        self.setFixedSize(12, 12)
        t = QtCore.QTimer(self, interval=35)
        t.timeout.connect(self._tick)
        t.start()

    def _tick(self):
        self._phase = (self._phase + 0.055) % (2 * math.pi)
        self.update()

    def set_color(self, qcolor):
        self._color = qcolor
        self.update()

    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        pulse = (math.sin(self._phase) + 1) / 2

        rr = 4.0 + pulse * 2.2
        rc = QtGui.QColor(self._color)
        rc.setAlpha(int(100 * (1 - pulse)))
        p.setPen(QtGui.QPen(rc, 1.0))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(QtCore.QPointF(cx, cy), rr, rr)

        hc = QtGui.QColor(self._color)
        hc.setAlpha(40)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(hc)
        p.drawEllipse(QtCore.QPointF(cx, cy), 4.0, 4.0)

        solid = QtGui.QColor(self._color)
        solid.setAlpha(255)
        p.setBrush(solid)
        p.drawEllipse(QtCore.QPointF(cx, cy), 2.5, 2.5)


class _ScanLine(QtWidgets.QWidget):
    """1 px horizontal rule that fades from cyan → transparent → violet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)

    def paintEvent(self, _ev):
        p = QtGui.QPainter(self)
        w = self.width()
        g = QtGui.QLinearGradient(0, 0, w, 0)
        g.setColorAt(0.00, QtGui.QColor(255, 255, 255,  0))
        g.setColorAt(0.30, QtGui.QColor(255, 255, 255, 30))
        g.setColorAt(0.70, QtGui.QColor(255, 255, 255, 30))
        g.setColorAt(1.00, QtGui.QColor(255, 255, 255,  0))
        p.fillRect(self.rect(), g)


# ══════════════════════════════════════════════════════════════════════════════
#  SidebarWidget
# ══════════════════════════════════════════════════════════════════════════════

class SidebarWidget(QtWidgets.QWidget):
    """
    Usayeed UCAD Assistant — Liquid Glass Terminal edition.
    """

    send_requested        = Signal(str)
    mode_changed          = Signal(str)
    settings_requested    = Signal()
    new_chat_requested    = Signal()
    stop_requested        = Signal()
    cancel_plan_requested = Signal()
    stop_step_requested   = Signal()
    undo_requested        = Signal()
    refresh_models_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(False)

        self._bg = _DotGridBg(self)
        self._bg.lower()

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(5)

        # ── PANEL 1 — Header ──────────────────────────────────────────
        hdr = _GlassPanel(radius=10, glass_color=_GS1, accent_top=True)
        hdr.setFixedHeight(38)
        hl = QtWidgets.QHBoxLayout(hdr)
        hl.setContentsMargins(8, 0, 6, 0)
        hl.setSpacing(4)

        self._beacon = _BeaconDot(_CYAN)
        hl.addWidget(self._beacon)

        wm = QtWidgets.QLabel()
        wm.setText(
            "<span style='color:#ebedf0;font-size:11px;"
            "font-weight:700;letter-spacing:2.2px;'>"
            "UCAD"
            "</span>"
            "<span style='color:#4a4f57;font-size:11px;"
            "font-weight:700;letter-spacing:2.2px;'>"
            "&thinsp;AI"
            "</span>"
        )
        wm.setTextFormat(QtCore.Qt.RichText)
        wm.setStyleSheet("background: transparent;")
        hl.addWidget(wm)

        hl.addStretch()

        self._status_dot = QtWidgets.QLabel("◆")
        self._status_dot.setToolTip("Backend: disconnected")
        self._status_dot.setStyleSheet(
            f"color:{_sPINK};font-size:8px;background:transparent;padding:0 2px;"
        )
        hl.addWidget(self._status_dot)

        self._login_btn = QtWidgets.QPushButton("⚿")
        self._login_btn.setToolTip("Configure AI Provider & API Keys")
        self._login_btn.setFixedSize(24, 24)
        self._login_btn.setStyleSheet(_SS_HDR_BTN)
        hl.addWidget(self._login_btn)

        for tip, icon, cb in [
            ("New Chat", "+", self.new_chat_requested.emit),
            ("Settings", "⚙", self.settings_requested.emit),
            ("Stop",     "✕", self.stop_requested.emit),
        ]:
            b = QtWidgets.QPushButton(icon)
            b.setToolTip(tip)
            b.setFixedSize(24, 24)
            b.setStyleSheet(_SS_HDR_BTN)
            b.clicked.connect(cb)
            hl.addWidget(b)

        root.addWidget(hdr)

        # ── PANEL 2 — Mode / Provider / Model selectors ──────────────
        sel = _GlassPanel(radius=9, glass_color=_GS2, accent_top=True)
        sel.setFixedHeight(36)
        sl = QtWidgets.QHBoxLayout(sel)
        sl.setContentsMargins(8, 0, 8, 0)
        sl.setSpacing(0)

        def _vdiv():
            d = QtWidgets.QFrame()
            d.setFixedWidth(1)
            d.setFixedHeight(18)
            d.setStyleSheet("background: rgba(255,255,255,0.08);")
            return d

        self._mode_combo = QtWidgets.QComboBox()
        self._mode_items = [
            ("build",  "🛠  BUILD",  "Generate FreeCAD code and execute it automatically"),
            ("plan",   "📋  PLAN",   "Ask AI to design a plan without executing code"),
            ("ask",    "💬  ASK",    "General Q&A — no code generation"),
            ("pcb",    "🔌  PCB",    "PCB enclosure generation from KiCad files"),
            ("dxf",    "📐  DXF",    "DXF import and 2D design conversion"),
        ]
        self._mode_combo.blockSignals(True)
        for key, label, tip in self._mode_items:
            self._mode_combo.addItem(label, key)
            idx = self._mode_combo.count() - 1
            self._mode_combo.setItemData(idx, tip, QtCore.Qt.ToolTipRole)
        self._mode_combo.blockSignals(False)
        self._mode_combo.setMinimumWidth(80)
        self._mode_combo.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        self._mode_combo.setStyleSheet(_SS_COMBO)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed_int)
        sl.addWidget(self._mode_combo, 1)
        sl.addWidget(_vdiv())

        self._provider_combo = QtWidgets.QComboBox()
        self._provider_combo.setMinimumWidth(80)
        self._provider_combo.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        self._provider_combo.setStyleSheet(_SS_COMBO)
        sl.addWidget(self._provider_combo, 1)
        sl.addWidget(_vdiv())

        self._model_combo = QtWidgets.QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._model_combo.setMinimumWidth(100)
        self._model_combo.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)
        self._model_combo.setStyleSheet(_SS_COMBO)
        self._model_combo.lineEdit().setPlaceholderText("Type model or select preset")
        sl.addWidget(self._model_combo, 1)

        self._refresh_btn = QtWidgets.QPushButton("\u21bb")
        self._refresh_btn.setFixedWidth(24)
        self._refresh_btn.setFixedHeight(22)
        self._refresh_btn.setToolTip("Fetch available models from provider")
        self._refresh_btn.setStyleSheet(_SS_BUTTON_SMALL)
        self._refresh_btn.clicked.connect(self.refresh_models_requested.emit)
        sl.addWidget(self._refresh_btn)

        root.addWidget(sel)

        self._mode_desc = QtWidgets.QLabel("")
        self._mode_desc.setStyleSheet(f"""
            color          : {_sMUTE};
            font-size      : 8px;
            font-weight    : 600;
            letter-spacing : 1.0px;
            font-family    : 'Courier New', monospace;
            padding        : 0 4px 2px 4px;
            background     : transparent;
        """)
        root.addWidget(self._mode_desc)
        QtCore.QTimer.singleShot(
            0, lambda: self._on_mode_changed_int(self._mode_combo.currentIndex())
        )

        # ── PANEL 3 — Chat panel (takes all space between selectors and input) ──
        self._chat_panel = None
        self._taskboard  = None
        self._chat_tab_layout = QtWidgets.QVBoxLayout()
        self._chat_tab_layout.setContentsMargins(4, 4, 4, 4)
        self._chat_tab_layout.setSpacing(4)

        root.addLayout(self._chat_tab_layout, 1)

        # ── PANEL 4 — Input area ────────────────────────────────────
        self._inp_card = _GlassPanel(radius=14, glass_color=_GS1, accent_top=True)
        self._inp_card.setFixedHeight(92)
        il = QtWidgets.QVBoxLayout(self._inp_card)
        il.setContentsMargins(12, 8, 12, 7)
        il.setSpacing(3)

        self.inp = QtWidgets.QTextEdit()
        self.inp.setMinimumHeight(42)
        self.inp.setMaximumHeight(54)
        self.inp.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inp.setStyleSheet(_SS_INPUT + _SS_SCROLLBAR)
        self.inp.installEventFilter(self)
        il.addWidget(self.inp, 1)

        il.addWidget(_ScanLine())

        ar = QtWidgets.QHBoxLayout()
        ar.setContentsMargins(0, 1, 0, 0)
        ar.setSpacing(5)

        self._hint_lbl = QtWidgets.QLabel()
        self._hint_lbl.setStyleSheet(f"""
            color       : {_sMUTE};
            font-size   : 9px;
            font-style  : italic;
            font-family : 'Courier New', monospace;
            background  : transparent;
        """)
        ar.addWidget(self._hint_lbl, 1)

        send_btn = QtWidgets.QPushButton("→")
        send_btn.setToolTip("Shift+Enter to send")
        send_btn.setFixedSize(32, 27)
        send_btn.setStyleSheet(_SS_SEND)
        send_btn.clicked.connect(
            lambda: self.send_requested.emit(self.inp.toPlainText().strip())
        )
        ar.addWidget(send_btn)

        il.addLayout(ar)

        self._inp_container = self._inp_card
        root.addWidget(self._inp_card)

        self._hints = [
            "make a 100×60×40 blue box",
            "cylinder r=50 h=100",
            "sketch 50×50 square, pad 30 mm",
            "cut a pocket through the solid",
            "fillet all edges, radius 10",
        ]
        self._hint_idx = 0
        self._hint_timer = QtCore.QTimer(self, interval=4000)
        self._hint_timer.timeout.connect(self._rotate_hint)
        self._hint_timer.start()
        self._rotate_hint()

        # ── Status / HUD bar ────────────────────────────────────────
        self._status_layout = QtWidgets.QHBoxLayout()
        self._status_layout.setSpacing(6)
        self._status_layout.setContentsMargins(4, 0, 4, 0)

        self._status_dot_led = QtWidgets.QLabel("●")
        self._status_dot_led.setFixedWidth(10)
        self._status_dot_led.setStyleSheet(
            f"color:{_sSUB};font-size:9px;background:transparent;"
        )
        self._status_layout.addWidget(self._status_dot_led)

        self._status_text = QtWidgets.QLabel("READY")
        self._status_text.setStyleSheet(f"""
            color          : {_sMUTE};
            font-size      : 8px;
            font-weight    : 600;
            letter-spacing : 1.5px;
            font-family    : 'Courier New', monospace;
            background     : transparent;
        """)
        self._status_layout.addWidget(self._status_text)

        self._stop_step_btn = QtWidgets.QPushButton("⏹  STOP STEP")
        self._stop_step_btn.setFixedHeight(20)
        self._stop_step_btn.setStyleSheet(_SS_MINI)
        self._stop_step_btn.setVisible(False)
        self._stop_step_btn.clicked.connect(self.stop_step_requested.emit)
        self._status_layout.addWidget(self._stop_step_btn)

        self._cancel_plan_btn = QtWidgets.QPushButton("✕  CANCEL PLAN")
        self._cancel_plan_btn.setFixedHeight(20)
        self._cancel_plan_btn.setStyleSheet(_SS_MINI)
        self._cancel_plan_btn.setVisible(False)
        self._cancel_plan_btn.clicked.connect(self.cancel_plan_requested.emit)
        self._status_layout.addWidget(self._cancel_plan_btn)

        self._undo_btn = QtWidgets.QPushButton("↩  UNDO")
        self._undo_btn.setToolTip("Undo last AI action (restore checkpoint or doc.undo)")
        self._undo_btn.setFixedHeight(20)
        self._undo_btn.setStyleSheet(_SS_MINI)
        self._undo_btn.setVisible(True)
        self._undo_btn.clicked.connect(self.undo_requested.emit)
        self._status_layout.addWidget(self._undo_btn)

        self._status_layout.addStretch()
        root.addLayout(self._status_layout)

        # ── Footer — Branding ──────────────────────────────────────────
        footer = QtWidgets.QLabel(
            "<span style='color:#3a3f47;font-size:8px;letter-spacing:1px;'>"
            "PRODUCT OF USAYEED LLC"
            "</span>"
        )
        footer.setAlignment(QtCore.Qt.AlignCenter)
        footer.setStyleSheet("background:transparent;")
        root.addWidget(footer)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bg.setGeometry(self.rect())

    def eventFilter(self, obj, event):
        if obj is self.inp and event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and \
               (event.modifiers() & QtCore.Qt.ShiftModifier):
                self.send_requested.emit(self.inp.toPlainText().strip())
                return True
        return super().eventFilter(obj, event)

    def _rotate_hint(self):
        h = self._hints[self._hint_idx % len(self._hints)]
        self._hint_idx += 1
        self._hint_lbl.setText(f"e.g.  {h}")
        self.inp.setPlaceholderText("Describe what to build\u2026")

    @property
    def current_mode(self):
        return self._mode_combo.currentData() or "build"

    def set_mode(self, mode_key):
        idx = self._mode_combo.findData(mode_key)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)

    @property
    def mode_desc(self):
        return self._mode_desc

    def _on_mode_changed(self, new_mode):
        self._inp_card.setVisible(new_mode not in ("pcb", "dxf"))
        self.mode_changed.emit(new_mode)

    def _on_mode_changed_int(self, idx):
        key = self._mode_combo.itemData(idx)
        if key:
            tip = self._mode_combo.itemData(idx, QtCore.Qt.ToolTipRole) or ""
            self._mode_desc.setText(tip.upper())
            self._mode_desc.setVisible(True)
            self._on_mode_changed(key)

    def set_chat_panel(self, panel):
        self._chat_panel = panel
        self._chat_tab_layout.addWidget(panel, 1)

    def set_taskboard(self, taskboard):
        self._taskboard = taskboard
        self._chat_tab_layout.addWidget(taskboard)

    @property
    def mode_combo(self):        return self._mode_combo
    @property
    def provider_combo(self):    return self._provider_combo
    @property
    def model_combo(self):       return self._model_combo
    @property
    def status_dot(self):        return self._status_dot
    @property
    def status_dot_led(self):    return self._status_dot_led
    @property
    def status_text(self):       return self._status_text
    @property
    def stop_step_btn(self):     return self._stop_step_btn
    @property
    def cancel_plan_btn(self):   return self._cancel_plan_btn
    @property
    def login_btn(self):         return self._login_btn
    @property
    def status_layout(self):     return self._status_layout
    @property
    def inp_container(self):     return self._inp_container
    @property
    def chat_panel(self):        return self._chat_panel
    @property
    def chat_tab_layout(self):   return self._chat_tab_layout

    def set_dot(self, color):
        self._status_dot_led.setStyleSheet(
            f"color:{color};font-size:9px;background:transparent;"
        )
        is_laser = any(c in color for c in ("00f0", "00e5"))
        is_alert = any(c in color for c in ("ff2d", "ff44"))
        is_thinking = "f7c9" in color
        if is_laser:
            self._beacon.set_color(_CYAN)
        elif is_alert:
            self._beacon.set_color(_PINK)
        elif is_thinking:
            self._beacon.set_color(QtGui.QColor(245, 158, 11))
        else:
            self._beacon.set_color(QtGui.QColor(74, 79, 87))
