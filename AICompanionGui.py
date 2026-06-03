# AICompanionGui.py - GOD-TIER AI SIDEBAR V4
import FreeCAD, FreeCADGui
from compat import QtWidgets, QtCore, QtGui, Qt, Signal
import os, json, datetime, re
from orchestrator import AIOrchestrator, TEMPLATES, MAX_RETRIES, PRESET_MODELS, MODES, PROVIDERS
from pcb_mode import PcbInputWidget

PROVIDER_HELP_URLS = {
    "openai": "https://platform.openai.com/api-keys",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "anthropic": "https://console.anthropic.com/settings/keys",
    "google": "https://aistudio.google.com/app/apikey",
    "xai": "https://console.x.ai/",
    "mistral": "https://console.mistral.ai/api-keys/",
    "cohere": "https://dashboard.cohere.com/api-keys",
    "perplexity": "https://www.perplexity.ai/settings/api",
    "groq": "https://console.groq.com/keys",
    "openrouter": "https://openrouter.ai/keys",
    "together": "https://api.together.xyz/settings/api-keys",
    "fireworks": "https://app.fireworks.ai/settings/users/api-keys",
    "github": "https://github.com/settings/tokens",
}

PROVIDERS_WITHOUT_KEYS = {"ollama", "templates"}

# ── Worker ───────────────────────────────────────────────────

class CodeWorker(QtCore.QObject):
    finished = QtCore.Signal(str, str, bool, int)
    error = QtCore.Signal(str, int)
    def __init__(self, orch, api_msgs, user_input, mid_plan=False, gen=0):
        super().__init__()
        self.orch = orch
        self.api_msgs = api_msgs
        self.user_input = user_input
        self.mid_plan = mid_plan
        self._cancel = False
        self._gen = gen
    def run(self):
        try:
            raw, code, used_api = self.orch.generate_code_safe(self.api_msgs, self.user_input)
            if not code:
                code = self.orch.get_fallback_code(self.user_input, self.mid_plan)
                used_api = False
            if not self._cancel:
                self.finished.emit(raw or "", code or "", used_api, self._gen)
        except Exception as e:
            if not self._cancel:
                self.error.emit(str(e), self._gen)
    def cancel(self): self._cancel = True

# ── Spinner ──────────────────────────────────────────────────
class Spinner(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedSize(16,16); self._a=0
        self._t=QtCore.QTimer(self); self._t.timeout.connect(lambda: (setattr(self,'_a',(self._a+30)%360),self.update())); self._t.start(50)
    def paintEvent(self, e):
        p=QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.translate(8,8)
        for i in range(8):
            p.setPen(QtGui.QPen(QtGui.QColor(88,166,255,255-i*28),2.5))
            p.drawLine(0,-6,0,-3); p.rotate(45)
        p.end()

# ── Property Editor ──────────────────────────────────────────
class PropEditor(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        l=QtWidgets.QVBoxLayout(self); l.setContentsMargins(2,2,2,2); l.setSpacing(2)
        self.hdr=QtWidgets.QLabel("Select an object in the tree")
        self.hdr.setStyleSheet("color:#6b6b80;font-size:10px;")
        l.addWidget(self.hdr)
        self.grid=QtWidgets.QGridLayout(); l.addLayout(self.grid)
        self.cur=None; self.wids={}
    
    def _pick(self, obj):
        c = QtWidgets.QColorDialog.getColor()
        if c.isValid() and hasattr(obj, 'ViewObject'):
            obj.ViewObject.ShapeColor = (c.red()/255, c.green()/255, c.blue()/255)

    def _set_pos(self, obj, axis, value):
        p = obj.Placement
        setattr(p.Base, axis, value)
        obj.Placement = p
        doc = FreeCAD.ActiveDocument
        if doc:
            doc.recompute()
    
    def show_obj(self, obj):
        self.clear(); self.cur=obj
        if not obj: self.hdr.setText("Select an object in the tree"); return
        self.hdr.setText(f"<b>{obj.Label}</b> <span style='color:#6b6b80'>({obj.TypeId.split('::')[-1]})</span>")
        row=0
        for p in ['Length','Width','Height','Radius','Radius1','Radius2','Angle']:
            if hasattr(obj,p):
                lbl=QtWidgets.QLabel(f"{p}:"); lbl.setStyleSheet("color:#ccc;font-size:10px;")
                inp=QtWidgets.QDoubleSpinBox(); inp.setRange(0.1,100000); inp.setDecimals(1)
                inp.setValue(getattr(obj,p)); inp.setSuffix(" mm")
                inp.valueChanged.connect(lambda v,o=obj,pr=p: (setattr(o,pr,v), (FreeCAD.ActiveDocument.recompute() if FreeCAD.ActiveDocument else None)))
                self.grid.addWidget(lbl,row,0); self.grid.addWidget(inp,row,1)
                self.wids[p]=inp; row+=1
        if hasattr(obj,'ViewObject') and hasattr(obj.ViewObject,'ShapeColor'):
            c=obj.ViewObject.ShapeColor
            lbl=QtWidgets.QLabel("Color:"); lbl.setStyleSheet("color:#ccc;font-size:10px;")
            btn=QtWidgets.QPushButton(); btn.setFixedSize(60,20)
            btn.setStyleSheet(f"background-color:rgb({int(c[0]*255)},{int(c[1]*255)},{int(c[2]*255)})")
            btn.clicked.connect(lambda *_, o=obj: self._pick(o))

    def clear(self):
        for i in reversed(range(self.grid.count())):
            item=self.grid.itemAt(i)
            if item and item.widget(): item.widget().deleteLater()
        self.wids={}

# ── Template Browser ─────────────────────────────────────────
class TemplateDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("🏗 Design Templates"); self.setMinimumSize(500,400)
        l=QtWidgets.QVBoxLayout(self)
        l.addWidget(QtWidgets.QLabel("<b>Select a design template to generate:</b>"))
        self.list=QtWidgets.QListWidget()
        self.selected=None
        for name,tpl in TEMPLATES.items():
            item=QtWidgets.QListWidgetItem(f"{name.upper()} — {tpl['desc']}")
            item.setData(Qt.UserRole,name)
            item.setData(Qt.UserRole+1,tpl['code'])
            self.list.addItem(item)
        self.list.setStyleSheet("QListWidget{background:#1e1e1e;color:#ccc;border:1px solid #3c3c3c;font-size:12px;} QListWidget::item{padding:6px;} QListWidget::item:selected{background:#094771;}")
        l.addWidget(self.list)
        btns=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok|QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(lambda: (setattr(self,'selected',self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None),self.accept()))
        btns.rejected.connect(self.reject)
        l.addWidget(btns)

# ── Tree ─────────────────────────────────────────────────────
class ModelTree(QtWidgets.QTreeWidget):
    sel_sig = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabel("Document Objects")
        self.setIndentation(15); self.setAnimated(True)
        self.setStyleSheet("""
            QTreeWidget {
                background: #101926;
                color: #d9e4f0;
                border: 1px solid #2a3648;
                border-radius: 10px;
                font-size: 11px;
                padding: 4px;
            }
            QTreeWidget::item {
                padding: 3px 4px;
                border-radius: 5px;
            }
            QTreeWidget::item:hover { background: #162438; }
            QTreeWidget::item:selected { background: #1f3960; color: #eff6ff; }
        """)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx)
        self.itemDoubleClicked.connect(lambda i,c: self.sel_sig.emit(i.data(0,Qt.UserRole)) if i.data(0,Qt.UserRole) else None)
        self._t=QtCore.QTimer(self); self._t.timeout.connect(self.refresh); self._t.start(2000)
        self._filter=""
    
    def set_filt(self, t): self._filter=t.lower() if t else ""; self.refresh()
    
    def _find_obj(self, name):
        for doc in FreeCAD.listDocuments().values():
            o = doc.getObject(name)
            if o: return o, doc
        return None, None

    def _ctx(self, pos):
        item=self.itemAt(pos); name=item.data(0,Qt.UserRole) if item else None
        if not name: return
        raw = item.data(0, Qt.UserRole) if item else ""
        if isinstance(raw, str) and raw.startswith("__doc__:"):
            doc_name = raw.split(":", 1)[1]
            m=QtWidgets.QMenu(self)
            a1=m.addAction("★ Activate"); a1.triggered.connect(lambda *_, n=doc_name: self._activate(n))
            m.exec_(self.mapToGlobal(pos))
            return
        m=QtWidgets.QMenu(self)
        a1=m.addAction("🔍 Select"); a1.triggered.connect(lambda *_, n=name: self._sel(n))
        a2=m.addAction("✏ Modify"); a2.triggered.connect(lambda *_, n=name: self.sel_sig.emit(n))
        a3=m.addAction("📏 Measure"); a3.triggered.connect(lambda *_, n=name: self._meas(n))
        a4=m.addAction("🎨 Color"); a4.triggered.connect(lambda *_, n=name: self._col(n))
        a5=m.addAction("🗑 Delete"); a5.triggered.connect(lambda *_, n=name: self._del(n))
        m.exec_(self.mapToGlobal(pos))
    
    def _activate(self, doc_name):
        try:
            docs = FreeCAD.listDocuments()
            if doc_name in docs:
                d = docs[doc_name]
                FreeCAD.setActiveDocument(doc_name)
                FreeCADGui.setActiveDocument(FreeCADGui.getDocument(doc_name))
                d.recompute()
                FreeCAD.Gui.SendMsgToActiveView("ViewFit")
        except Exception: pass

    def _sel(self, n):
        try:
            o, _ = self._find_obj(n)
            if o: FreeCADGui.Selection.clearSelection(); FreeCADGui.Selection.addSelection(o)
        except Exception: pass
    def _meas(self, n):
        try:
            o, _ = self._find_obj(n)
            if o and hasattr(o,'Shape'):
                bb=o.Shape.BoundBox; v=o.Shape.Volume; a=o.Shape.Area
                QtWidgets.QMessageBox.information(None,f"📏 {o.Label}",
                    f"Bounds: X{bb.XMin:.0f}-{bb.XMax:.0f} Y{bb.YMin:.0f}-{bb.YMax:.0f} Z{bb.ZMin:.0f}-{bb.ZMax:.0f}\nVolume: {v:.0f} mm³\nArea: {a:.0f} mm²")
        except Exception: pass
    def _del(self, n):
        try:
            o, doc = self._find_obj(n)
            if o and QtWidgets.QMessageBox.question(None,"Delete",f"Delete '{o.Label}'?",QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)==QtWidgets.QMessageBox.Yes:
                doc.removeObject(n); doc.recompute()
        except Exception: pass
    def _col(self, n):
        try:
            o, doc = self._find_obj(n)
            if o and hasattr(o,'ViewObject'):
                c=QtWidgets.QColorDialog.getColor()
                if c.isValid(): o.ViewObject.ShapeColor=(c.redF(),c.greenF(),c.blueF()); doc.recompute()
        except Exception: pass
    
    def refresh(self):
        self.clear()
        docs = FreeCAD.listDocuments()
        active = FreeCAD.ActiveDocument
        if not docs:
            r=QtWidgets.QTreeWidgetItem(["📄 No document"]); r.setForeground(0,QtGui.QColor("#6b6b80")); self.addTopLevelItem(r); return
        try: sel_names = [o.Name for o in FreeCADGui.Selection.getSelection()]
        except Exception: sel_names = []
        for dname, doc in docs.items():
            is_active = " ★" if doc == active else ""
            root=QtWidgets.QTreeWidgetItem([f"📄 {doc.Name} ({len(doc.Objects)} objs){is_active}"])
            fg = QtGui.QColor("#6af7b8") if doc == active else QtGui.QColor("#8b949e")
            root.setForeground(0, fg)
            font = root.font(0)
            font.setBold(doc == active)
            root.setFont(0, font)
            root.setData(0, Qt.UserRole, f"__doc__:{doc.Name}")
            self.addTopLevelItem(root)
            for o in doc.Objects:
                t=o.TypeId.split("::")[-1]
                if self._filter and self._filter not in o.Label.lower() and self._filter not in o.Name.lower() and self._filter not in t.lower(): continue
                icon="📦"
                if "PartDesign" in o.TypeId: icon="⚙"
                elif "Sketcher" in o.TypeId: icon="✏"
                elif "Draft" in o.TypeId: icon="📐"
                elif "Cut" in o.TypeId: icon="🔷"
                elif "Fuse" in o.TypeId or "MultiFuse" in o.TypeId: icon="🔶"
                elif "Group" in o.TypeId: icon="📁"
                elif "Body" in o.TypeId: icon="🧱"
                elif "Part" in o.TypeId: icon="🧩"
                item=QtWidgets.QTreeWidgetItem([f"{icon} {o.Label}"]); item.setToolTip(0,f"Doc:{doc.Name}  Name:{o.Name}  Type:{t}")
                item.setData(0,Qt.UserRole,o.Name)
                if o.Name in sel_names: item.setBackground(0,QtGui.QColor("#094771"))
                if hasattr(o,'Placement'):
                    b=o.Placement.Base
                    c=QtWidgets.QTreeWidgetItem([f"📍({b.x:.0f},{b.y:.0f},{b.z:.0f})"]); c.setForeground(0,QtGui.QColor("#6b6b80")); item.addChild(c)
                ps=[]
                for p in ['Length','Width','Height','Radius','Radius1','Radius2','Angle']:
                    if hasattr(o,p): ps.append(f"{p}={getattr(o,p)}")
                if ps:
                    c=QtWidgets.QTreeWidgetItem([", ".join(ps)]); c.setForeground(0,QtGui.QColor("#569cd6")); item.addChild(c)
                if hasattr(o,'ViewObject') and hasattr(o.ViewObject,'ShapeColor'):
                    co=o.ViewObject.ShapeColor; hx=f"#{int(co[0]*255):02x}{int(co[1]*255):02x}{int(co[2]*255):02x}"
                    c=QtWidgets.QTreeWidgetItem([f"🎨{hx}"]); c.setForeground(0,QtGui.QColor(hx)); item.addChild(c)
                root.addChild(item)
            root.setExpanded(True)

    # ── Selection Watcher (spatial tagging) ─────────────────────
class SelectionWatcher(QtCore.QObject):
    tagSelected = QtCore.Signal(str)
    def __init__(self):
        super().__init__()
        self._obs = None
    def start(self):
        try:
            if self._obs is None:
                self._obs = FreeCADGui.Selection.addObserver(self)
        except Exception:
            pass
    def stop(self):
        try:
            if self._obs is not None:
                FreeCADGui.Selection.removeObserver(self._obs)
        except Exception:
            pass
        self._obs = None
    def addSelection(self, doc_name, obj_name, sub, pnt):
        if sub and sub.strip() and not obj_name.startswith("__"):
            self.tagSelected.emit(f"@{obj_name}.{sub}")
    def addSelectionEx(self, doc_name, obj_name, subs, pnt):
        if subs:
            for sub in subs:
                if sub.strip() and not obj_name.startswith("__"):
                    self.tagSelected.emit(f"@{obj_name}.{sub}")

    # ── Sidebar ──────────────────────────────────────────────────
si=None

class AISidebar(QtWidgets.QDialog):
    _hints = [
        "make a 100x60x40 blue box",
        "cylinder radius 50 height 100",
        "sketch a 50x50 square and pad 30mm",
        "cut a hole through the box",
        "fillet edges radius 10",
    ]

    def __init__(self):
        global si
        super().__init__(FreeCADGui.getMainWindow()); si=self
        self.setWindowTitle("AI Copilot")
        self.setObjectName("AICopilotPopup")
        self.setMinimumSize(420, 620)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
        self._last_code=""
        self._worker_thread = None
        self._code_worker = None
        self._retries = 0
        self._pending_input = ""
        self._pending_msgs = None
        self._step_retry_state = None
        self._plan_steps = []
        self._plan_step_idx = 0
        self._plan_paused = False
        self._abandoned = False
        self._worker_gen = 0
        self._code_visible = False
        self._hint_idx = 0
        self._closed = False
        self._mode = "build"
        self._provider_models = {}
        self._provider_order = []

        self.setStyleSheet("""
            QDialog#AICopilotPopup {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0d1625, stop:0.6 #0a1320, stop:1 #09111b);
            }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Header ─────────────────────────────────────────────
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(6)
        hdr.setContentsMargins(4, 0, 4, 0)
        _dd_style = """
            QComboBox {
                background: #121c2c;
                color: #e8f0f9;
                border: 1px solid #2e3e56;
                border-radius: 8px;
                font-size: 11px;
                padding: 4px 9px;
                font-weight: 600;
            }
            QComboBox:hover { border-color: #63a5ff; }
            QComboBox:focus { border-color: #79b8ff; }
            QComboBox::drop-down { border: none; width: 16px; }
            QComboBox::down-arrow { width: 0; border: 0; }
        """
        # Mode selector
        self._mode_combo = QtWidgets.QComboBox()
        self._mode_combo.addItems(["build", "plan", "ask", "pcb"])
        self._mode_combo.setFixedWidth(60)
        self._mode_combo.setStyleSheet(_dd_style)
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        hdr.addWidget(self._mode_combo)
        # Provider selector
        self._provider_combo = QtWidgets.QComboBox()
        self._provider_combo.setMinimumWidth(110)
        self._provider_combo.setStyleSheet(_dd_style)
        hdr.addWidget(self._provider_combo)
        # Model selector
        self._model_combo = QtWidgets.QComboBox()
        self._model_combo.setMinimumWidth(175)
        self._model_combo.setStyleSheet(_dd_style)
        hdr.addWidget(self._model_combo)
        self._build_provider_model_index()
        self._populate_provider_combo()
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        hdr.addStretch()
        # Connection status + login
        self._status_dot = QtWidgets.QLabel("●")
        self._status_dot.setToolTip("Backend: disconnected")
        self._status_dot.setStyleSheet("color:#ff4444;font-size:12px;padding:0 4px;")
        hdr.addWidget(self._status_dot)
        self._login_btn = QtWidgets.QPushButton("🔑")
        self._login_btn.setToolTip("Login to Railway backend")
        self._login_btn.setFixedSize(26, 24)
        self._login_btn.setStyleSheet("""
            QPushButton { background:#121c2c; color:#9eb3cb; border:1px solid #2e3e56; border-radius:8px; font-size:11px; }
            QPushButton:hover { background:#17263a; color:#e6f0fc; border-color:#63a5ff; }
        """)
        self._login_btn.clicked.connect(self._show_login_dialog)
        hdr.addWidget(self._login_btn)
        # Header action buttons
        for tip, icon, cb in [("New Chat", "✚", self._new_chat), ("Settings", "⚙", self.sets), ("Stop", "✕", self.stop)]:
            b = QtWidgets.QPushButton(icon)
            b.setToolTip(tip)
            b.setFixedSize(26, 24)
            b.setStyleSheet("""
                QPushButton {
                    background: #121c2c;
                    color: #9eb3cb;
                    border: 1px solid #2e3e56;
                    border-radius: 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: #17263a;
                    color: #e6f0fc;
                    border-color: #63a5ff;
                }
            """)
            b.clicked.connect(lambda *_, cb=cb: cb())
            hdr.addWidget(b)
        layout.addLayout(hdr)

        # Keep mascot object for compatibility, but do not show it in minimal UI
        self._mascot = QtWidgets.QWidget()
        self._mascot.setVisible(False)

        # ── Selection tagger ────────────────────────────────────
        self._sel_watcher = SelectionWatcher()
        self._sel_watcher.tagSelected.connect(self._on_tag_selected)
        self._sel_watcher.start()

        # ── Chat ───────────────────────────────────────────────
        self.chat = QtWidgets.QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chat.setStyleSheet("""
            QTextEdit {
                background: #0f1a2a;
                color: #e6edf3;
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
                font-size: 13px;
                border: 1px solid #2b3a50;
                border-radius: 12px;
                padding: 12px 14px;
                selection-background-color: #264f78;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #334861;
                border-radius: 5px;
                min-height: 34px;
            }
            QScrollBar::handle:vertical:hover { background: #466183; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        layout.addWidget(self.chat, 1)

        # No Objects panel and no collapsible code header in minimal UI

        self.cp = QtWidgets.QTextEdit()
        self.cp.setReadOnly(True)
        self.cp.setMaximumHeight(180)
        self.cp.setVisible(False)
        self.cp.setPlaceholderText("Generated code")
        self.cp.setStyleSheet("""
            QTextEdit {
                background: #101a29;
                color: #d9e6f7;
                font-family: 'Consolas', 'Cascadia Mono', monospace;
                font-size: 11px;
                border: 1px solid #2e3f57;
                border-radius: 10px;
                padding: 8px 12px;
            }
            QTextEdit::placeholder { color: #61758d; }
        """)
        layout.addWidget(self.cp)

        # Code action buttons (save/copy) — inline after code area
        code_actions = QtWidgets.QHBoxLayout()
        code_actions.setSpacing(4)
        code_actions.setContentsMargins(4, 0, 4, 0)
        self.macro_btn = QtWidgets.QPushButton("💾")
        self.macro_btn.setToolTip("Save as .FCMacro")
        self.macro_btn.setFixedSize(24, 22)
        self.macro_btn.setVisible(False)
        self.macro_btn.setStyleSheet("QPushButton{background:#121d2d;color:#9ab0c8;border:1px solid #2e3e56;border-radius:7px;font-size:10px;} QPushButton:hover{background:#1a2b41;color:#edf5ff;border-color:#67abff;}")
        self.macro_btn.clicked.connect(lambda *_: self._savem())
        code_actions.addWidget(self.macro_btn)
        self.copy_btn = QtWidgets.QPushButton("📋")
        self.copy_btn.setToolTip("Copy code")
        self.copy_btn.setFixedSize(24, 22)
        self.copy_btn.setVisible(False)
        self.copy_btn.setStyleSheet("QPushButton{background:#121d2d;color:#9ab0c8;border:1px solid #2e3e56;border-radius:7px;font-size:10px;} QPushButton:hover{background:#1a2b41;color:#edf5ff;border-color:#67abff;}")
        self.copy_btn.clicked.connect(lambda *_: self._copy())
        code_actions.addWidget(self.copy_btn)
        code_actions.addStretch()
        layout.addLayout(code_actions)

        # ── Input ──────────────────────────────────────────────
        self._inp_container = QtWidgets.QFrame()
        self._inp_container.setFixedHeight(100)
        self._inp_container.setStyleSheet("QFrame{background:#0f1a2a;border:1px solid #2b3a50;border-radius:12px;}")
        inp_lay = QtWidgets.QGridLayout(self._inp_container)
        inp_lay.setContentsMargins(10, 8, 10, 10)
        inp_lay.setSpacing(6)
        inp_lay.setContentsMargins(10, 10, 10, 10)
        self.inp = QtWidgets.QTextEdit()
        self.inp.setMinimumHeight(44)
        self.inp.setMaximumHeight(64)
        self.inp.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inp.setStyleSheet("""
            QTextEdit {
                background: #0f1927;
                color: #e9f1fb;
                border: 1.5px solid #30435f;
                border-radius: 11px;
                padding: 10px 100px 10px 16px;
                font-size: 13px;
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
                selection-background-color: #264f78;
            }
            QTextEdit:focus {
                border-color: #6dafff;
                background: #142338;
            }
            QTextEdit:hover:!focus {
                border-color: #446183;
            }
        """)
        # Shift+Enter to send, Enter for newline
        self.inp.installEventFilter(self)
        inp_lay.addWidget(self.inp, 0, 0, 1, 2)
        # Inline actions overlaid on the right of the input
        inp_actions = QtWidgets.QWidget()
        inp_actions.setFixedHeight(30)
        ial = QtWidgets.QHBoxLayout(inp_actions)
        ial.setContentsMargins(0, 0, 6, 0)
        ial.setSpacing(2)
        # Send button
        send_btn = QtWidgets.QPushButton("→")
        send_btn.setToolTip("Shift+Enter to send")
        send_btn.setFixedSize(30, 26)
        send_btn.setStyleSheet("QPushButton{background:#1b3b63;color:#e9f3ff;border:1px solid #4c7fba;border-radius:7px;font-size:15px;font-weight:700;} QPushButton:hover{background:#255289;color:#ffffff;border-color:#79b5ff;}")
        send_btn.clicked.connect(lambda *_: self.send())
        ial.addWidget(send_btn)
        inp_lay.addWidget(inp_actions, 0, 1, Qt.AlignRight | Qt.AlignVCenter)

        # Rotating placeholder timer
        self._hint_timer = QtCore.QTimer(self)
        self._hint_timer.timeout.connect(self._rotate_hint)
        self._hint_timer.start(4000)
        self._rotate_hint()

        layout.addWidget(self._inp_container)

        # ── Status ─────────────────────────────────────────────
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        bar.setContentsMargins(4, 0, 4, 0)
        self.spin = Spinner()
        self.spin.setVisible(False)
        bar.addWidget(self.spin)
        self.st = QtWidgets.QLabel("●")
        self.st.setFixedWidth(8)
        self.st.setStyleSheet("color:#4fd37a;font-size:14px;")
        bar.addWidget(self.st)
        self._status_text = QtWidgets.QLabel("Ready")
        self._status_text.setStyleSheet("color:#91a7c1;font-size:11px;font-weight:500;")
        bar.addWidget(self._status_text)

        # Plan action buttons (hidden by default)
        _plan_btn_style = "QPushButton{background:#121d2d;color:#dbe9fb;border:1px solid #2f4058;border-radius:7px;padding:3px 10px;font-size:10px;font-weight:600;} QPushButton:hover{background:#1a2c43;color:#f0f7ff;border-color:#69adff;}"
        self._stop_step_btn = QtWidgets.QPushButton("⏹ Stop Step")
        self._stop_step_btn.setFixedHeight(22)
        self._stop_step_btn.setStyleSheet(_plan_btn_style)
        self._stop_step_btn.setVisible(False)
        self._stop_step_btn.clicked.connect(self._on_stop_step)
        bar.addWidget(self._stop_step_btn)
        self._cancel_plan_btn = QtWidgets.QPushButton("✕ Cancel Plan")
        self._cancel_plan_btn.setFixedHeight(22)
        self._cancel_plan_btn.setStyleSheet(_plan_btn_style)
        self._cancel_plan_btn.setVisible(False)
        self._cancel_plan_btn.clicked.connect(lambda: (self.stop(), self._finish(), self.msg("System", "❌ Plan cancelled.")))
        bar.addWidget(self._cancel_plan_btn)

        bar.addStretch()
        layout.addLayout(bar)

        self.load()
        self._rebuild()
        # ── PCB Mode Widget (created after orch is ready) ──────
        self._pcb_widget = PcbInputWidget(orch=self.orch)
        self._pcb_widget.setVisible(False)
        self._pcb_widget.generate_clicked.connect(self._on_pcb_generate)
        layout.addWidget(self._pcb_widget)
        # Clear any stale history — each session is fresh
        if self.orch:
            self.orch.conversation_history.clear()
    
    # ── Core ──────────────────────────────────────────────────
    def _pretty_provider(self, provider):
        return {
            "openai": "OpenAI",
            "deepseek": "DeepSeek",
            "anthropic": "Anthropic",
            "google": "Google",
            "xai": "xAI",
            "mistral": "Mistral",
            "cohere": "Cohere",
            "perplexity": "Perplexity",
            "groq": "Groq",
            "openrouter": "OpenRouter",
            "together": "Together",
            "fireworks": "Fireworks",
            "github": "GitHub Models",
            "ollama": "Ollama (Local)",
            "templates": "Templates",
        }.get(provider, provider.title())

    def _model_display_name(self, label, provider):
        return re.sub(rf"^\[{re.escape(self._pretty_provider(provider))}\]\s*", "", label).strip()

    def _build_provider_model_index(self):
        self._provider_models = {}
        self._provider_order = []
        seen = set()
        for label, provider, model in PRESET_MODELS:
            if provider not in self._provider_models:
                self._provider_models[provider] = []
            self._provider_models[provider].append({
                "label": label,
                "display": self._model_display_name(label, provider),
                "model": model,
            })
            if provider not in seen:
                seen.add(provider)
                self._provider_order.append(provider)
        for provider in PROVIDERS.keys():
            if provider not in seen:
                self._provider_order.append(provider)
                self._provider_models.setdefault(provider, [])

    def _populate_provider_combo(self, selected_provider=None):
        if not selected_provider:
            selected_provider = "deepseek"
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()
        for provider in self._provider_order:
            self._provider_combo.addItem(self._pretty_provider(provider), provider)
        idx = self._provider_combo.findData(selected_provider)
        self._provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._provider_combo.blockSignals(False)
        self._populate_model_combo(selected_provider)

    def _populate_model_combo(self, provider, selected_label=None, selected_model=None):
        models = self._provider_models.get(provider, [])
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        for item in models:
            self._model_combo.addItem(item["display"], item)
        if not models:
            fallback_model = PROVIDERS.get(provider, {}).get("model", "")
            self._model_combo.addItem(fallback_model or "Default", {
                "label": fallback_model or "Default",
                "display": fallback_model or "Default",
                "model": fallback_model,
            })

        target_idx = -1
        if selected_label:
            for i in range(self._model_combo.count()):
                item = self._model_combo.itemData(i)
                if item and item.get("label") == selected_label:
                    target_idx = i
                    break
        if target_idx < 0 and selected_model:
            for i in range(self._model_combo.count()):
                item = self._model_combo.itemData(i)
                if item and item.get("model") == selected_model:
                    target_idx = i
                    break

        self._model_combo.setCurrentIndex(target_idx if target_idx >= 0 else 0)
        self._model_combo.blockSignals(False)

    def _current_provider(self):
        provider = self._provider_combo.currentData()
        return provider or "deepseek"

    def _current_model_entry(self):
        entry = self._model_combo.currentData()
        return entry if isinstance(entry, dict) else {"model": "", "label": ""}

    def _provider_requires_key(self, provider):
        return provider not in PROVIDERS_WITHOUT_KEYS

    def _on_provider_changed(self, _idx):
        provider = self._current_provider()
        self._populate_model_combo(provider)
        self.c_model = self._current_model_entry().get("model", "")
        self._rebuild()
        self._update_connection_status()
        self.msg("System", f"Provider: **{self._pretty_provider(provider)}**")

    def _on_model_changed(self, _idx):
        entry = self._current_model_entry()
        self.c_model = entry.get("model", "")
        self._rebuild()
        self.msg("System", f"Model: **{entry.get('display') or entry.get('model') or 'Default'}**")

    def load(self):
        p=os.path.join(os.path.dirname(__file__),"config.json")
        cfg = {}
        if os.path.exists(p):
            with open(p) as f: cfg=json.load(f)
        self.api_key = cfg.get("api_key", "")
        self.c_model = cfg.get("model", "")
        self.c_url = cfg.get("url", "")
        self.backend_key = cfg.get("backend_key", "")
        self.auth_token = cfg.get("auth_token", "")
        if self.auth_token:
            from orchestrator import BackendAdapter
            BackendAdapter.set_auth_token(self.auth_token)

        selected_provider = cfg.get("provider", "")
        if not selected_provider:
            ml = cfg.get("model_label", "")
            if ml:
                for label, provider, _ in PRESET_MODELS:
                    if label == ml:
                        selected_provider = provider
                        break
        if not selected_provider:
            selected_provider = "deepseek"

        self._populate_provider_combo(selected_provider)
        self._populate_model_combo(selected_provider,
                                  selected_label=cfg.get("model_label", ""),
                                  selected_model=cfg.get("model", ""))

        md = cfg.get("mode", "build")
        i = self._mode_combo.findText(md)
        if i >= 0:
            self._mode_combo.setCurrentIndex(i)
    
    def save(self, key, prov, model="", url=""):
        cfg = {"api_key":key,"provider":prov,"model":model,"url":url,
               "provider_label": self._provider_combo.currentText(),
               "model_label": self._current_model_entry().get("label", self._model_combo.currentText()),
               "mode": self._mode_combo.currentText(),
               "backend_key": getattr(self, 'backend_key', ''),
               "auth_token": getattr(self, 'auth_token', '')}
        with open(os.path.join(os.path.dirname(__file__),"config.json"),'w') as f:
            json.dump(cfg, f)
        self.api_key = key
        self.c_model = model
        self.c_url = url
        self._rebuild()
        self.msg("System","✅ Settings saved!")
        self._update_connection_status()
    
    def _update_connection_status(self):
        """Update the status dot color based on backend connection state."""
        prov = self._current_provider()
        if prov != "backend" or not self.c_url:
            self._status_dot.setStyleSheet("color:#666666;font-size:12px;padding:0 4px;")
            self._status_dot.setToolTip("Backend not configured")
            return
        if getattr(self, 'auth_token', ''):
            self._status_dot.setStyleSheet("color:#44ff44;font-size:12px;padding:0 4px;")
            self._status_dot.setToolTip(f"Backend: connected to {self.c_url}")
        else:
            self._status_dot.setStyleSheet("color:#ff4444;font-size:12px;padding:0 4px;")
            self._status_dot.setToolTip("Backend: not logged in (click 🔑)")

    def _show_login_dialog(self):
        """Dialog to configure backend URL + backend key and get auth token."""
        d = QtWidgets.QDialog(self)
        d.setWindowTitle("Backend Login")
        d.setMinimumWidth(420)
        d.setStyleSheet("""
            QDialog { background:#0d1625; color:#e6edf3; }
            QLabel { color:#c8d6e8; font-size:12px; }
            QLineEdit { background:#121c2c; color:#e8f0f9; border:1px solid #2e3e56;
                        border-radius:6px; padding:6px 10px; font-size:12px; }
            QLineEdit:focus { border-color:#63a5ff; }
            QPushButton { background:#1e3a5f; color:#e6f0fc; border:none;
                          border-radius:8px; padding:8px 20px; font-size:12px; font-weight:600; }
            QPushButton:hover { background:#2a4d7a; }
        """)
        l = QtWidgets.QVBoxLayout(d)
        l.setSpacing(10)

        title = QtWidgets.QLabel("<b>Connect to Railway Backend</b>")
        title.setStyleSheet("font-size:14px;color:#e6edf3;")
        l.addWidget(title)

        l.addWidget(QtWidgets.QLabel("Backend URL"))
        url_inp = QtWidgets.QLineEdit()
        url_inp.setText(getattr(self, 'c_url', ''))
        url_inp.setPlaceholderText("https://your-app.railway.app")
        l.addWidget(url_inp)

        l.addWidget(QtWidgets.QLabel("Backend Key"))
        key_inp = QtWidgets.QLineEdit()
        key_inp.setEchoMode(QtWidgets.QLineEdit.Password)
        key_inp.setText(getattr(self, 'backend_key', ''))
        key_inp.setPlaceholderText("Enter your Railway backend key")
        l.addWidget(key_inp)

        info = QtWidgets.QLabel("The backend key is shared with your Railway backend deployment (set via BACKEND_KEY env var).")
        info.setWordWrap(True)
        info.setStyleSheet("color:#7f93ad;font-size:11px;")
        l.addWidget(info)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)

        def _do_login():
            url = url_inp.text().strip().rstrip("/")
            bkey = key_inp.text().strip()
            if not url or not bkey:
                QtWidgets.QMessageBox.warning(d, "Missing Info", "Both URL and backend key are required.")
                return
            try:
                import urllib.request
                req = urllib.request.Request(
                    f"{url}/auth/login",
                    data=json.dumps({"backend_key": bkey}).encode(),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
                token = data.get("token", "")
                if not token:
                    raise Exception("No token in response")
                self.auth_token = token
                self.backend_key = bkey
                self.c_url = url
                from orchestrator import BackendAdapter
                BackendAdapter.set_auth_token(token)
                self.save(self.api_key, self._current_provider(), model=self.c_model, url=url)
                self._update_connection_status()
                self.msg("System", f"✅ Connected to backend at {url}")
                d.accept()
            except Exception as e:
                QtWidgets.QMessageBox.critical(d, "Login Failed", f"Could not connect to backend:\n{e}")

        btns.accepted.connect(_do_login)
        btns.rejected.connect(d.reject)
        l.addWidget(btns)
        d.exec_()

    def _rebuild(self):
        prov = self._current_provider()
        entry = self._current_model_entry()
        mdl = self.c_model or entry.get("model") or PROVIDERS.get(prov, {}).get("model")
        self.orch=AIOrchestrator(
            self.api_key if prov != "templates" else "",
            provider=prov,
            model=mdl,
            api_url=self.c_url if self.c_url else None
        )
        if prov == "backend" and getattr(self, 'auth_token', ''):
            from orchestrator import BackendAdapter
            BackendAdapter.set_auth_token(self.auth_token)
        if hasattr(self, '_pcb_widget') and self._pcb_widget:
            self._pcb_widget.set_orch(self.orch)
            if self._pcb_widget._board_data:
                self.orch._board_context = self._pcb_widget._board_data
    
    def msg(self, s, t):
        import html as htmlmod
        if s == "System":
            # Keep UI noise low: route system notes to status line instead of chat bubbles
            plain = re.sub(r"\*\*(.*?)\*\*", r"\1", str(t or "")).replace("\n", " ").strip()
            if plain:
                self._status_text.setText(plain[:120])
            return
        text_html = htmlmod.escape(t)
        text_html = text_html.replace("\n", "<br>")
        text_html = re.sub(r'`([^`]+)`', r'<code style="background:#132235;color:#9dd0ff;padding:2px 6px;border:1px solid #2f4562;border-radius:5px;font-family:Consolas,monospace;font-size:12px;">\1</code>', text_html)

        if s == "Error":
            block = (
                f'<div style="margin:10px 0;display:flex;justify-content:flex-start;">'
                f'<div style="background:#311b20;border:1px solid #7a303d;border-left:4px solid #ef6b73;border-radius:10px;padding:10px 12px;max-width:95%;">'
                f'<div style="color:#ffb9bf;font-size:12px;font-weight:700;letter-spacing:0.4px;margin-bottom:5px;">ERROR</div>'
                f'<div style="color:#f8d8db;font-size:13px;line-height:1.55;">{text_html}</div>'
                f'</div></div>'
            )
        elif s == "You":
            block = (
                f'<div style="margin:8px 0;display:flex;justify-content:flex-end;">'
                f'<div style="background:#1d3f66;border:1px solid #4d79a8;border-radius:10px;padding:8px 11px;max-width:84%;">'
                f'<div style="color:#f3f9ff;font-size:13px;line-height:1.55;">{text_html}</div>'
                f'</div></div>'
            )
        elif s == "AI":
            block = (
                f'<div style="margin:8px 0;display:flex;justify-content:flex-start;">'
                f'<div style="background:#121f30;border:1px solid #32465e;border-radius:10px;padding:8px 11px;max-width:92%;">'
                f'<div style="color:#e6f0fd;font-size:13px;line-height:1.6;">{text_html}</div>'
                f'</div>'
                f'</div>'
            )
        else:
            block = f'<div style="margin:6px 0;color:#9cb1c9;font-size:12px;">{text_html}</div>'

        if self._mascot.isVisible():
            self._mascot.hide()
        self.chat.append(block)
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())
        QtWidgets.QApplication.processEvents()
    
    def show_code(self, code):
        self._last_code=code
        if code and len(code.strip())>10:
            self.cp.setPlainText(code[:1000])
            self.cp.setVisible(True)
            self.macro_btn.setVisible(True); self.copy_btn.setVisible(True)
            try:
                # Bring panel forward when code is generated
                self.show()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass
        else:
            self.cp.clear(); self.cp.setVisible(False); self.macro_btn.setVisible(False); self.copy_btn.setVisible(False)
    
    def _savem(self):
        if self._last_code:
            ok,path=self.orch.save_macro(self._last_code)
            self._status_text.setText("💾 Saved!" if ok else f"❌ {path}")
            self._status_text.setStyleSheet(f"color:{'#6af7b8' if ok else '#f76a6a'};font-size:11px;font-weight:500;")
            QtCore.QTimer.singleShot(3000,lambda: (self._set_dot("#3fb950"), self._status_text.setText("Ready"), self._status_text.setStyleSheet("color:#8b949e;font-size:11px;font-weight:500;")))
    
    def _copy(self):
        if self._last_code:
            QtWidgets.QApplication.clipboard().setText(self._last_code)
            self._status_text.setText("📋 Copied!"); self._status_text.setStyleSheet("color:#6af7b8;font-size:11px;font-weight:500;")
            QtCore.QTimer.singleShot(2000,lambda: (self._set_dot("#3fb950"), self._status_text.setText("Ready"), self._status_text.setStyleSheet("color:#8b949e;font-size:11px;font-weight:500;")))
    
    def _tp(self):
        if not hasattr(self, 'pe'):
            return
        v=not self.pe.isVisible(); self.pe.setVisible(v)
        if v:
            try:
                s=FreeCADGui.Selection.getSelection()
                if s: self.pe.show_obj(s[-1])
            except Exception: pass
    
    def _tpl(self):
        d=TemplateDialog(self)
        if d.exec_() and d.selected:
            name=d.selected
            code=TEMPLATES[name]['code'].replace("```python\n","").replace("\n```","")
            self.show_code(code)
            self._do_send(f"use template {name}")
    
    def _newdoc(self):
        self.inp.setText("create a new document called AI_Design"); self.send()

    def _set_dot(self, color):
        self.st.setStyleSheet(f"color:{color};font-size:14px;")

    def _toggle_objects(self):
        if not hasattr(self, '_obj_container'):
            return
        v = not self._obj_container.isVisible()
        self._obj_container.setVisible(v)
        self._obj_arrow.setText("▾" if v else "▸")
        self._obj_arrow.setStyleSheet("color:#8da2bb;font-size:10px;font-weight:bold;")
        if v: self.tree.refresh()

    def _toggle_code(self):
        if not hasattr(self, 'cp'):
            return
        v = not self.cp.isVisible()
        self.cp.setVisible(v)
        self.macro_btn.setVisible(v and bool(self._last_code))
        self.copy_btn.setVisible(v and bool(self._last_code))
        if hasattr(self, '_code_arrow'):
            self._code_arrow.setText("▾" if v else "▸")
            self._code_arrow.setStyleSheet("color:#8da2bb;font-size:10px;font-weight:bold;")
        if hasattr(self, '_code_label'):
            self._code_label.setText("Hide generated code" if v else "Show generated code")
            self._code_label.setStyleSheet("color:#8da2bb;font-size:10px;font-weight:700;letter-spacing:1px;")

    def closeEvent(self, e):
        self._closed = True
        self._hint_timer.stop()
        if hasattr(self, '_sel_watcher'):
            self._sel_watcher.stop()
        super().closeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self._closed = False
        if not self._hint_timer.isActive():
            self._hint_timer.start(4000)
            self._rotate_hint()

    def _rotate_hint(self):
        self._hint_idx = (self._hint_idx + 1) % len(self._hints)
        try:
            self.inp.setPlaceholderText(self._hints[self._hint_idx])
        except RuntimeError:
            pass
    
    def _on_srch(self, t):
        if hasattr(self, 'tree') and self.tree:
            self.tree.set_filt(t)
    
    def _on_sel(self, n):
        if not hasattr(self, 'tree') or not hasattr(self, 'pe'):
            return
        try:
            obj, doc = self.tree._find_obj(n)
            if obj:
                self.pe.show_obj(obj); self.pe.setVisible(True)
        except Exception:
            pass
    
    def _new_chat(self):
        """Reset conversation: clear chat, history, and state; show mascot."""
        if self._code_worker:
            self._code_worker.cancel()
        self.orch.conversation_history.clear()
        self.chat.clear()
        self._mascot.setVisible(True)
        self._plan_steps = []
        self._plan_step_idx = 0
        self._plan_paused = False
        self._pending_input = ""
        self._pending_msgs = None
        self._step_retry_state = None
        self._retries = 0
        self.cp.clear()
        self.macro_btn.setVisible(False)
        self.copy_btn.setVisible(False)
        self._set_dot("#3fb950")
        self._status_text.setText("Ready"); self._status_text.setStyleSheet("color:#8b949e;font-size:11px;font-weight:500;")
        self.spin.setVisible(False)

    def stop(self):
        self._abandoned = True
        if self._code_worker:
            self._code_worker.cancel()
        # Do NOT quit() or wait() the thread — let it finish its current
        # operation naturally. The _cancel flag and _abandoned flag
        # suppress signal handlers. The thread's cleanup signals
        # (finished → thread.quit → deleteLater) still fire safely.
        self._code_worker = None
        self._worker_thread = None
        self.spin.setVisible(False)
        self._set_dot("#f7c96a")
        self._status_text.setText("⏹ Stopped"); self._status_text.setStyleSheet("color:#f7c96a;font-size:11px;font-weight:500;")
    
    def exp(self):
        h=self.chat.toHtml(); ts=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        p=os.path.join(os.path.expanduser("~"),f"AI_Chat_{ts}.html")
        try:
            with open(p,'w',encoding='utf-8') as f:
                f.write(f"<html><head><meta charset='utf-8'><title>AI Copilot Chat</title>"
                    f"<style>body{{background:#1e1e1e;color:#d4d4d4;font-family:sans-serif;padding:20px;}}</style></head><body>{h}</body></html>")
            self._status_text.setText(f"💬 Exported"); self._status_text.setStyleSheet("color:#6af7b8;font-size:11px;font-weight:500;")
            QtCore.QTimer.singleShot(5000,lambda: (self._set_dot("#3fb950"), self._status_text.setText("Ready"), self._status_text.setStyleSheet("color:#8b949e;font-size:11px;font-weight:500;")))
        except Exception as e: self._status_text.setText("❌ Export failed"); self._status_text.setStyleSheet("color:#f76a6a;font-size:11px;font-weight:500;")
    
    def undo(self): self._do_send("undo last operation")
    
    def sets(self):
        d = QtWidgets.QDialog(self)
        d.setWindowTitle("AI Provider & Model")
        d.setMinimumWidth(560)
        l = QtWidgets.QVBoxLayout(d)
        l.setSpacing(8)

        title = QtWidgets.QLabel("<b>Choose AI Provider and Model</b>")
        title.setStyleSheet("font-size:13px;")
        l.addWidget(title)

        pc = QtWidgets.QComboBox()
        for provider in self._provider_order:
            pc.addItem(self._pretty_provider(provider), provider)
        cur_provider = self._current_provider()
        i = pc.findData(cur_provider)
        pc.setCurrentIndex(i if i >= 0 else 0)

        mc = QtWidgets.QComboBox()

        def fill_models(provider, selected_model=None):
            mc.clear()
            for item in self._provider_models.get(provider, []):
                mc.addItem(item["display"], item)
            if mc.count() == 0:
                default_model = PROVIDERS.get(provider, {}).get("model", "")
                mc.addItem(default_model or "Default", {
                    "label": default_model or "Default",
                    "display": default_model or "Default",
                    "model": default_model,
                })
            if selected_model:
                for idx in range(mc.count()):
                    item = mc.itemData(idx)
                    if item and (item.get("model") == selected_model or item.get("label") == selected_model):
                        mc.setCurrentIndex(idx)
                        break

        fill_models(cur_provider, selected_model=self._current_model_entry().get("model") or self.c_model)

        key_label = QtWidgets.QLabel("API Key")
        key_input = QtWidgets.QLineEdit()
        key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        key_input.setText(self.api_key)
        key_input.setPlaceholderText("Paste your API key")

        url_label = QtWidgets.QLabel("API URL (optional override)")
        url_input = QtWidgets.QLineEdit()
        url_input.setText(self.c_url)
        url_input.setPlaceholderText("Leave blank to use provider default")

        custom_model_label = QtWidgets.QLabel("Custom model (optional override)")
        custom_model_input = QtWidgets.QLineEdit()
        custom_model_input.setText(self.c_model)
        custom_model_input.setPlaceholderText("Leave blank to use selected model")

        help_link = QtWidgets.QLabel("")
        help_link.setOpenExternalLinks(True)
        help_link.setStyleSheet("font-size:11px;")

        req_hint = QtWidgets.QLabel("")
        req_hint.setStyleSheet("color:#8ea3bc;font-size:11px;")

        def refresh_provider_state():
            provider = pc.currentData() or "deepseek"
            fill_models(provider)
            is_backend = provider == "backend"
            url_label.setText("Railway Backend URL" if is_backend else "API URL (optional override)")
            url_input.setPlaceholderText("https://your-app.railway.app" if is_backend else "Leave blank to use provider default")
            needs_key = self._provider_requires_key(provider)
            key_label.setText("API Key" + (" (required)" if needs_key else " (optional)"))
            req_hint.setText(
                "Enter your actual AI provider key. Plugin sends it to backend, backend forwards to provider." if is_backend else
                ("This provider requires your own key." if needs_key else
                "No key needed for this provider in most setups.")
            )
            link = PROVIDER_HELP_URLS.get(provider, "")
            if link and not is_backend:
                help_link.setText(f'<a href="{link}">Get {self._pretty_provider(provider)} API key</a>')
                help_link.setVisible(True)
            else:
                help_link.setVisible(False)

        pc.currentIndexChanged.connect(refresh_provider_state)
        refresh_provider_state()

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Provider", pc)
        form.addRow("Model", mc)
        form.addRow(key_label, key_input)
        form.addRow(url_label, url_input)
        form.addRow(custom_model_label, custom_model_input)
        l.addLayout(form)
        l.addWidget(req_hint)
        l.addWidget(help_link)

        info = QtWidgets.QLabel(
            "Workflow: choose provider -> choose model -> add your key -> save. "
            "Header selectors will stay in sync."
        )
        info.setStyleSheet("color:#7f93ad;font-size:11px;")
        info.setWordWrap(True)
        l.addWidget(info)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)

        def _accept():
            provider = pc.currentData() or "deepseek"
            model_entry = mc.currentData() if isinstance(mc.currentData(), dict) else {"model": ""}
            model = custom_model_input.text().strip() or model_entry.get("model") or PROVIDERS.get(provider, {}).get("model", "")
            key = key_input.text().strip()
            url = url_input.text().strip()
            if provider == "backend" and not url:
                QtWidgets.QMessageBox.warning(d, "Backend URL Required", "Please enter your Railway backend URL (e.g. https://your-app.railway.app).")
                return
            if self._provider_requires_key(provider) and not key:
                QtWidgets.QMessageBox.warning(d, "API Key Required", f"Please enter an API key for {self._pretty_provider(provider)}.")
                return

            # Sync header selectors with chosen provider/model
            pidx = self._provider_combo.findData(provider)
            if pidx >= 0:
                self._provider_combo.setCurrentIndex(pidx)
            # Ensure model combo is repopulated for provider before selecting model
            self._populate_model_combo(provider, selected_model=model_entry.get("model"), selected_label=model_entry.get("label"))

            self.save(key, provider, model=model, url=url)
            d.accept()

        btns.accepted.connect(_accept)
        btns.rejected.connect(d.reject)
        l.addWidget(btns)
        d.exec_()
    
    # ── Send ──────────────────────────────────────────────────
    def _launch_worker(self, api_msgs, user_input):
        """Start CodeWorker in a background QThread for the API call only."""
        self._abandoned = False  # reset stop state for fresh worker
        self._worker_gen += 1
        gen = self._worker_gen
        self._worker_thread = QtCore.QThread()
        mid_plan = bool(self._plan_steps) and self._plan_step_idx < len(self._plan_steps)
        self._code_worker = CodeWorker(self.orch, api_msgs, user_input, mid_plan=mid_plan, gen=gen)
        self._code_worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._code_worker.run)
        self._code_worker.finished.connect(self._on_code_ready)
        self._code_worker.error.connect(self._on_worker_err)
        self._code_worker.finished.connect(self._worker_thread.quit)
        self._code_worker.finished.connect(self._code_worker.deleteLater)
        self._code_worker.error.connect(self._worker_thread.quit)
        self._code_worker.error.connect(self._code_worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _do_send(self, text):
        self.msg("You", text)
        self.spin.setVisible(True)
        self._set_dot("#f7c96a")
        self._status_text.setText("🤔 Thinking..."); self._status_text.setStyleSheet("color:#f7c96a;font-size:11px;font-weight:500;")
        self._retries = 0
        self._step_retry_state = None
        # "execute" confirmation for plan mode — use the stored plan steps
        tl = text.lower().strip()
        if self._plan_paused and any(w in tl for w in ("execute", "go ahead", "run", "do it", "proceed")):
            self._plan_paused = False
            original = self._pending_input or text
            self._pending_input = original
            self._mode = "build"
            self._mode_combo.setCurrentText("build")
            self._stop_step_btn.setVisible(True)
            self._cancel_plan_btn.setVisible(True)
            self.msg("System", "▶️ Executing plan...")
            if self._plan_steps:
                self._plan_step_idx = 0
                self.orch.reset_observation_tracker()
                diff_result = self.orch.capture_structured_diff()
                fresh_obs = self.orch.format_diff(diff_result)
                fresh_ctx = self.orch.get_document_context()
                msgs = self.orch.build_step_prompt(
                    original, self._plan_steps, 0,
                    fresh_obs, fresh_ctx
                )
                self._pending_msgs = msgs
            else:
                self._pending_msgs = self.orch.build_messages(original, mode="build")
            self._launch_worker(self._pending_msgs, original)
            return
        # Handle plan resume (multi-step execution paused by API error, not plan-mode preview)
        if self._plan_paused and self._mode == "build":
            self._plan_paused = False
            self._stop_step_btn.setVisible(True)
            self._cancel_plan_btn.setVisible(True)
            fresh_obs = self.orch.capture_observation()
            fresh_ctx = self.orch.get_document_context()
            step_idx = self._plan_step_idx
            original_request = self._pending_input
            if step_idx < len(self._plan_steps):
                msgs = self.orch.build_step_prompt(
                    original_request, self._plan_steps, step_idx,
                    fresh_obs, fresh_ctx,
                    prior_observation="(plan resumed after API interruption)"
                )
                self.msg("System", f"▶️ Resuming plan at step {step_idx+1}")
                self._launch_worker(msgs, original_request)
                return
        self._pending_input = ""
        self._pending_msgs = None
        self._plan_steps = []
        self._plan_step_idx = 0
        self._plan_paused = False
        self._mode = self._mode_combo.currentText()
        # Build messages on main thread (captures FreeCAD state)
        self._pending_msgs = self.orch.build_messages(text, mode=self._mode)
        self._pending_input = text
        self._launch_worker(self._pending_msgs, text)

    def _on_tag_selected(self, tag):
        """Insert a spatial tag (e.g. @Box001.Face6) at cursor in the input box."""
        cursor = self.inp.textCursor()
        cursor.insertText(tag)
        self.inp.setFocus()

    def send(self):
        t=self.inp.toPlainText().strip()
        if not t: return
        self.inp.clear()
        self._do_send(t)

    def eventFilter(self, obj, event):
        if obj is self.inp and event.type() == QtCore.QEvent.KeyPress:
            if (event.key() == QtCore.Qt.Key_Return or event.key() == QtCore.Qt.Key_Enter) and (event.modifiers() & QtCore.Qt.ShiftModifier):
                self.send()
                return True
        return super().eventFilter(obj, event)

    # ── Callbacks ─────────────────────────────────────────────
    def _on_code_ready(self, raw_text, code, used_api, gen=0):
        try:
            if self._closed or self._abandoned:
                return
            # Ignore stale responses from older workers
            if gen != 0 and gen != self._worker_gen:
                return
            # Show AI reasoning as a subtle system label (not a chat bubble)
            if raw_text:
                thinking = self.orch.extract_thinking(raw_text)
                if thinking:
                    self.msg("System", f"💭 {thinking[:200]}")

            # Plan mode — extract plan and pause
            if self._mode == "plan":
                plan_source = raw_text or code
                self._plan_steps = self.orch.extract_plan(plan_source)
                if self._plan_steps:
                    plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(self._plan_steps))
                    self.msg("System", f"📋 Plan:\n{plan_text}")
                    self.msg("System", "Send **execute** or **go ahead** to run this plan.")
                    self._plan_paused = True
                    self._pending_input = self._pending_input or raw_text
                self._finish()
                return

            # PCB mode — switch to chat after generation
            if self._mode == "pcb":
                if code:
                    success, message = self.orch.execute_code(code)
                    obs = self.orch.capture_observation()
                    icon = "✅" if success else "❌"
                    result_text = f"{icon} Enclosure: {message}"
                    if obs:
                        result_text += f"\n{obs}"
                    self._pcb_widget.show_chat()
                    self._pcb_widget.add_message(f"<b style='color:#58a6ff;'>AI:</b> {result_text}")
                    self._pcb_widget._status.setText("Done" if success else "Failed")
                else:
                    self._pcb_widget._status.setText("No code generated")
                self._finish()
                return

            # Build mode — execute code sequentially
            # NOTE: `code` is already extracted from fences by generate_code(), use it directly
            if not code:
                self.msg("AI", raw_text)
                self.orch.record_result(self._pending_input, code, True, "Responded with text", self._retries)
                self._finish()
                return

            combined_code = code
            success, message = self.orch.execute_code(combined_code)
            total_steps = len(self._plan_steps) if self._plan_steps else 1
            self._status_text.setText(f"⚡ Step {self._plan_step_idx + 1}/{total_steps}")

            if not success and self._retries < MAX_RETRIES:
                self._retries += 1
                fresh_obs = self.orch.capture_observation()
                ctx = self.orch.build_messages(self._pending_input,
                    mode="build",
                    retry_context=f"Previous code failed: {message}. Current scene: {fresh_obs}"
                )
                self._pending_msgs = ctx
                self._launch_worker(ctx, self._pending_input)
                return
            elif not success:
                self.msg("Error", f"❌ Failed after {MAX_RETRIES} retries: {message}")
                self.orch.record_result(self._pending_input, combined_code, False, message, self._retries)
                self._finish()
                return
            self._plan_step_idx += 1

            # Success — observe and decide next action
            obs = self.orch.capture_observation()
            step_label = f"Step {self._plan_step_idx}" if self._plan_steps else ""
            self.msg("System", f"✅ {step_label} {message} {obs or ''}".strip())
            self.show_code(combined_code)
            if hasattr(self, 'tree') and self.tree:
                self.tree.refresh()

            # Check if remaining plan needs revision — only when diff shows unexpected changes
            if self._plan_steps and self._plan_step_idx < len(self._plan_steps):
                diff_result = self.orch.capture_structured_diff()
                diff, full = diff_result
                needs_replan_check = False
                if diff is not None:
                    added, removed, modified = diff
                    added_uids = set(a["uid"] for a in added)
                    unexpected_mods = [m for m in modified
                                       if m["uid"] not in added_uids
                                       and m["uid"] not in self.orch._touched_objects]
                    if unexpected_mods:
                        needs_replan_check = True

                if needs_replan_check:
                    remaining = self._plan_steps[self._plan_step_idx:]
                    needs_replan, replan_text = self.orch.should_replan(remaining, obs)
                    if needs_replan:
                        new_steps = self.orch.extract_plan(replan_text)
                        if new_steps and len(new_steps) >= 1:
                            self._plan_steps = self._plan_steps[:self._plan_step_idx] + new_steps
                            plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(new_steps))
                            self.msg("System", f"🔄 Plan revised for remaining steps:\n{plan_text}")
                        else:
                            self.msg("System", f"🔄 Plan revised: {replan_text[:200]}")

            if self._plan_steps and self._plan_step_idx < len(self._plan_steps):
                self._request_next_step(obs)
            else:
                obs_text = obs or ""
                result = f"✅ **Done!** {message}" + (f"\n\n_{obs_text}_" if obs_text else "")
                self.msg("AI", result)
                self._finish()
        except Exception as ex:
            self.msg("Error", f"Error processing AI response: {ex}")
            self._finish()

    def _request_next_step(self, observation_prelim):
        """Ask the AI to generate code for the next plan step. Re-reads document fresh."""
        step_idx = self._plan_step_idx
        fresh_context = self.orch.get_document_context()
        diff_result = self.orch.capture_structured_diff()
        diff_str = self.orch.format_diff(diff_result)
        # Use the full live scene observation (not just the diff) so the AI
        # has exact dimensions and positions for precise multi-step positioning
        full_obs = self.orch.capture_observation()
        msgs = self.orch.build_step_prompt(
            self._pending_input, self._plan_steps, step_idx,
            full_obs, fresh_context,
            prior_observation=observation_prelim,
            diff_summary=diff_str
        )
        self._pending_msgs = msgs
        self._status_text.setText(f"⚡ Step {step_idx+1}/{len(self._plan_steps)}")
        self._launch_worker(msgs, self._pending_input)

    def _on_mode_changed(self, new_mode):
        """Handle mode switch — preserve plan state across the transition."""
        if self._code_worker is not None or (self._worker_thread and self._worker_thread.isRunning()):
            self._on_stop_step()
        self._mode = new_mode
        self.msg("System", f"Mode: **{new_mode}**")
        if new_mode == "pcb":
            self._inp_container.setVisible(False)
            self._pcb_widget.setVisible(True)
            self._mascot.setVisible(False)
        else:
            self._pcb_widget.setVisible(False)
            self._inp_container.setVisible(True)
            self._mascot.setVisible(True)
        if self._plan_paused and self._plan_steps:
            if new_mode == "build":
                self.msg("System",
                    f"Plan paused at step {self._plan_step_idx+1}/{len(self._plan_steps)} — "
                    f"send any message to resume."
                )
            else:
                self.msg("System",
                    f"⏸️ Plan paused at step {self._plan_step_idx+1}/{len(self._plan_steps)} — "
                    f"switch back to **Build** mode to resume."
                )

    def _on_pcb_generate(self, params):
        """Handle PCB enclosure generation request."""
        if not self.orch._board_context:
            self.msg("System", "No board loaded. Drop a .kicad_pcb file first.")
            return
        refinement = params.get("refinement", "")
        if refinement:
            full_prompt = f"Refine the enclosure: {refinement}"
        else:
            full_prompt = (
                f"Generate enclosure with wall_t={params['wall_thickness']}, "
                f"lid_clearance={params['lid_clearance']}, boss_od={params['boss_od']}, "
                f"material={params['material']}"
            )
        self._pcb_widget._status.setText("Generating...")
        self._mode = "pcb"
        self._pending_msgs = self.orch.build_messages(full_prompt, mode="pcb")
        self._pending_input = full_prompt
        self._launch_worker(self._pending_msgs, full_prompt)

    def _on_stop_step(self):
        """Stop the current step but keep the plan paused & resumable."""
        self.stop()
        if self._plan_steps and self._plan_step_idx < len(self._plan_steps):
            self._plan_paused = True
            self.msg("System",
                f"⏸️ Step {self._plan_step_idx+1}/{len(self._plan_steps)} stopped. "
                f"Send any message to resume."
            )
        else:
            self.msg("System", "⏸️ Operation stopped.")
    
    def _on_worker_err(self, e, gen=0):
        if self._abandoned:
            return
        if gen != 0 and gen != self._worker_gen:
            return
        if self._plan_steps and self._plan_step_idx < len(self._plan_steps):
            self._plan_paused = True
            self.msg("System",
                f"⏸️ Plan paused at step {self._plan_step_idx+1}/{len(self._plan_steps)} "
                f"due to API error. Send any message to resume."
            )
            self.spin.setVisible(False)
            self._worker_thread = None
            self._code_worker = None
        else:
            self.msg("Error", str(e))
            self._finish()

    def _finish(self):
        self.spin.setVisible(False)
        self._worker_thread = None
        self._code_worker = None
        self._retries = 0
        self._pending_input = ""
        self._pending_msgs = None
        self._step_retry_state = None
        self._plan_paused = False
        self._plan_steps = []
        self._plan_step_idx = 0
        self._stop_step_btn.setVisible(False)
        self._cancel_plan_btn.setVisible(False)
        self._set_dot("#3fb950")
        self._status_text.setText("Ready"); self._status_text.setStyleSheet("color:#8b949e;font-size:11px;font-weight:500;")
        if hasattr(self, 'tree') and self.tree:
            self.tree.refresh()

def show_sidebar():
    global si
    if si is None: si=AISidebar()
    si.show()
    si.raise_()
    si._update_connection_status()
    # Ensure FreeCAD's native Combo View (left panel with Model/Tasks tabs) is visible
    try:
        mw = FreeCADGui.getMainWindow()
        combo = mw.findChild(QtWidgets.QDockWidget, "Combo View")
        if combo and not combo.isVisible():
            combo.show()
    except Exception:
        pass
