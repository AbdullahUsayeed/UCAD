# AICompanionGui.py - GOD-TIER AI SIDEBAR V4
#
# =============================================================================
# THREADING MODEL (read this before debugging concurrency issues)
# =============================================================================
# - CodeWorker (line 88) runs in a QThread started by _launch_worker.
#   Its run() method calls orch.generate_code_safe() / generate_plan_with_chief()
#   which do network I/O only (API call + token streaming).
# - When CodeWorker emits finished, the slot _on_code_ready runs on the MAIN
#   THREAD (receiver lives on the main thread, worker thread has already quit).
#   This is where execute_code() is called — it touches FreeCAD.ActiveDocument,
#   Part::FeatureAPI, force_sync_recompute(), etc. All FreeCAD API access is
#   main-thread-only by design.
# - _defer(action, ...) uses QTimer.singleShot(25, ...) to re-enter the worker
#   flow (e.g. next step, replan) without synchronous re-entry into _on_code_ready.
#   This breaks the call stack and avoids event-loop re-entry crashes.
# Implication: any crash inside execute_code(), capture_observation(),
# show_code(), _refresh_taskboard(), or any other GUI/state mutation is a
# MAIN-THREAD crash — Qt widget lifetime and FreeCAD object stability are the
# relevant constraints, NOT thread synchronization.
# =============================================================================
#
# =============================================================================
# CRASH PATTERN LIBRARY
# =============================================================================
# When debugging a new crash, check whether it fits one of the three patterns
# below. If it does, the fix approach is the same as the prior cases.
#
# PATTERN 1: Qt widget lifetime mismatches
# ----------------------------------------
# Calling refresh/repaint/show on a widget after it's been deleted (closed
# panel, removed row, or destroyed during layout clear). Symptoms: RuntimeError
# "wrapped C/C++ object has been deleted", segfault on next paint event.
# Examples fixed in this file:
#   - _refresh_taskboard called on every _on_stream token (widget churn)
#   - mousePressEvent lambda captured deleted row reference
#   - QTextEdit code panel recreated without preserving scene fingerprint
# Mitigation: gate refreshes to meaningful state transitions; wrap lambdas
# bound to deleted widget lifetimes in try/except RuntimeError; or use
# sip.isdeleted() before touching widgets.
#
# PATTERN 2: FreeCAD object access before stable state
# ----------------------------------------------------
# Reading o.Shape / o.BoundBox / o.TypeId / iterating doc.Objects before the
# document is fully loaded, or while another operation is mid-recompute.
# Symptoms: AttributeError, TypeError, "listcomp raised StopIteration",
# or silently empty results that cascade into IndexError downstream.
# Examples fixed in this file:
#   - mkstemp fd not closed before view.saveImage (Windows file lock)
#   - o.Shape throws inside list comprehension on partially-loaded doc
#   - o.TypeId missing/non-string on some feature types
#   - _capture_viewport_b64 called on inactive (not isVisible) view
# Mitigation: per-object try/except in comprehensions; force_sync_recompute()
# before observation; check view.isVisible() before capture; coerce types
# defensively (str(), getattr with default).
#
# PATTERN 3: State machine re-entry
# ---------------------------------
# Same object transition triggered twice, or transition triggered while
# already in target state. Symptoms: AttributeError on None, double-execution
# (file written twice, widget refreshed twice, list appended twice), or
# corruption of paired data structures.
# Examples fixed in this file:
#   - TaskStep.start() / finish() called twice on same step
#   - Deepthink single-step path created phantom TaskStep in
#     _completed_steps BEFORE the step ran, so finish() was a no-op and the
#     step appeared in both _plan_steps and _completed_steps
#   - base64 image embedded inside self.msg() which html.escape()'d into
#     a broken <img> tag, then rendered twice on refresh
# Mitigation: idempotent guards on state transitions (start()/finish() check
# current state); assert preconditions with _assert_step_invariant() BEFORE
# the transition; never trust call site ordering — verify with assertions.
# =============================================================================

import FreeCAD, FreeCADGui
from compat import QtWidgets, QtCore, QtGui, Qt
import os, json, datetime, re, html as _html
from orchestrator import AIOrchestrator, TEMPLATES, render_template, MAX_RETRIES, PRESET_MODELS, PROVIDERS, LITELLM_PROVIDERS, _provider_max_retries, classify_failure, summarize_failures, ModelRegistry
from companion_app import CodeWorker, ClassifyWorker
from sidebar_widget import SidebarWidget
from chat_panel import ChatPanel

from pcb_mode import PcbInputWidget
from dxf_mode import DxfInputWidget
from secret_store import atomic_write_json, has_legacy_plaintext, load_json_file, read_secret, store_secret
from task_step import TaskStep, StepState

# Launcher integration — when launched via UCAD Launcher, read config centrally
_UCAD_HOME = os.environ.get("UCAD_HOME", "")
if _UCAD_HOME:
    try:
        from launcher.config_adapter import merge_configs, get_api_key, load_launcher_config
    except ImportError:
        _UCAD_HOME = ""  # fall back to legacy behavior

PROVIDERS_WITHOUT_KEYS = {"ollama", "templates"}


def _report_gui_error(source, ex):
    FreeCAD.Console.PrintError(f"[AICompanion] {source}: {type(ex).__name__}: {ex}\n")

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
        self._pending_update = None
        self._recompute_timer = QtCore.QTimer(self)
        self._recompute_timer.setSingleShot(True)
        self._recompute_timer.timeout.connect(self._flush_pending_update)
    
    def _pick(self, obj):
        c = QtWidgets.QColorDialog.getColor()
        if c.isValid() and hasattr(obj, 'ViewObject') and obj.ViewObject is not None and hasattr(obj.ViewObject, 'ShapeColor'):
            obj.ViewObject.ShapeColor = (c.red()/255, c.green()/255, c.blue()/255)

    def _set_pos(self, obj, axis, value):
        p = obj.Placement
        setattr(p.Base, axis, value)
        obj.Placement = p
        doc = FreeCAD.ActiveDocument
        if doc:
            doc.recompute()

    def _queue_numeric_update(self, obj, prop_name, value):
        self._pending_update = (obj, prop_name, value)
        self._recompute_timer.start(120)

    def _flush_pending_update(self):
        if not self._pending_update:
            return
        obj, prop_name, value = self._pending_update
        self._pending_update = None
        setattr(obj, prop_name, value)
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
                inp.valueChanged.connect(lambda v,o=obj,pr=p: self._queue_numeric_update(o, pr, v))
                self.grid.addWidget(lbl,row,0); self.grid.addWidget(inp,row,1)
                self.wids[p]=inp; row+=1
        if hasattr(obj,'ViewObject') and hasattr(obj.ViewObject,'ShapeColor'):
            c=obj.ViewObject.ShapeColor
            lbl=QtWidgets.QLabel("Color:"); lbl.setStyleSheet("color:#ccc;font-size:10px;")
            btn=QtWidgets.QPushButton(); btn.setFixedSize(60,20)
            btn.setStyleSheet(f"background-color:rgb({int(c[0]*255)},{int(c[1]*255)},{int(c[2]*255)})")
            btn.clicked.connect(lambda *_, o=obj: self._pick(o))
            self.grid.addWidget(lbl,row,0); self.grid.addWidget(btn,row,1)
            row += 1

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
        self.itemDoubleClicked.connect(lambda i,c: self._sel(i.data(0,Qt.UserRole)) if i.data(0,Qt.UserRole) else None)
        self._t=QtCore.QTimer(self); self._t.timeout.connect(self.refresh); self._t.start(5000)
        self._filter=""
        self._last_snapshot = None
    
    def set_filt(self, t): self._filter=t.lower() if t else ""; self.refresh(force=True)

    def _snapshot_state(self):
        docs = FreeCAD.listDocuments()
        active = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else ""
        try:
            selection = tuple(sorted(o.Name for o in FreeCADGui.Selection.getSelection()))
        except Exception:
            selection = ()
        doc_state = tuple(sorted((name, len(doc.Objects)) for name, doc in docs.items()))
        return (doc_state, active, selection, self._filter)
    
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
            m.exec(self.mapToGlobal(pos))
            return
        m=QtWidgets.QMenu(self)
        a1=m.addAction("🔍 Select"); a1.triggered.connect(lambda *_, n=name: self._sel(n))
        a2=m.addAction("✏ Copy Name"); a2.triggered.connect(lambda *_, n=name: QtWidgets.QApplication.clipboard().setText(n))
        a3=m.addAction("📏 Measure"); a3.triggered.connect(lambda *_, n=name: self._meas(n))
        a4=m.addAction("🎨 Color"); a4.triggered.connect(lambda *_, n=name: self._col(n))
        a5=m.addAction("🗑 Delete"); a5.triggered.connect(lambda *_, n=name: self._del(n))
        m.exec(self.mapToGlobal(pos))
    
    def _activate(self, doc_name):
        try:
            docs = FreeCAD.listDocuments()
            if doc_name in docs:
                d = docs[doc_name]
                FreeCAD.setActiveDocument(doc_name)
                FreeCADGui.setActiveDocument(FreeCADGui.getDocument(doc_name))
                d.recompute()
                FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception as ex:
            _report_gui_error("tree.activate", ex)

    def _sel(self, n):
        try:
            o, _ = self._find_obj(n)
            if o: FreeCADGui.Selection.clearSelection(); FreeCADGui.Selection.addSelection(o)
        except Exception as ex:
            _report_gui_error("tree.select", ex)
    def _meas(self, n):
        try:
            o, _ = self._find_obj(n)
            if o and hasattr(o,'Shape'):
                bb=o.Shape.BoundBox; v=o.Shape.Volume; a=o.Shape.Area
                QtWidgets.QMessageBox.information(None,f"📏 {o.Label}",
                    f"Bounds: X{bb.XMin:.0f}-{bb.XMax:.0f} Y{bb.YMin:.0f}-{bb.YMax:.0f} Z{bb.ZMin:.0f}-{bb.ZMax:.0f}\nVolume: {v:.0f} mm³\nArea: {a:.0f} mm²")
        except Exception as ex:
            _report_gui_error("tree.measure", ex)
    def _del(self, n):
        try:
            o, doc = self._find_obj(n)
            if o and QtWidgets.QMessageBox.question(None,"Delete",f"Delete '{o.Label}'?",QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)==QtWidgets.QMessageBox.Yes:
                doc.removeObject(n); doc.recompute()
        except Exception as ex:
            _report_gui_error("tree.delete", ex)
    def _col(self, n):
        try:
            o, doc = self._find_obj(n)
            if o and hasattr(o,'ViewObject'):
                c=QtWidgets.QColorDialog.getColor()
                if c.isValid(): o.ViewObject.ShapeColor=(c.redF(),c.greenF(),c.blueF()); doc.recompute()
        except Exception as ex:
            _report_gui_error("tree.color", ex)
    
    def refresh(self, force=False):
        if not force and not self.isVisible():
            return
        snapshot = self._snapshot_state()
        if not force and snapshot == self._last_snapshot:
            return
        self.clear()
        docs = FreeCAD.listDocuments()
        active = FreeCAD.ActiveDocument
        if not docs:
            r=QtWidgets.QTreeWidgetItem(["📄 No document"]); r.setForeground(0,QtGui.QColor("#6b6b80")); self.addTopLevelItem(r); self._last_snapshot = snapshot; return
        try: sel_names = [o.Name for o in FreeCADGui.Selection.getSelection()]
        except Exception: sel_names = []
        for dname, doc in docs.items():
            is_active = " ★" if doc == active else ""
            root=QtWidgets.QTreeWidgetItem([f"📄 {doc.Name} ({len(doc.Objects)} objs){is_active}"])
            fg = QtGui.QColor("#ebedf0") if doc == active else QtGui.QColor("#4a4f57")
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
        self._last_snapshot = snapshot

    # ── Selection Watcher (spatial tagging) ─────────────────────
class SelectionWatcher(QtCore.QObject):
    tagSelected = QtCore.Signal(str)
    def __init__(self):
        super().__init__()
        self._obs = None
        self._registered = False
    def start(self):
        try:
            if not self._registered:
                self._obs = FreeCADGui.Selection.addObserver(self)
                self._registered = True
        except Exception as ex:
            print(f"[AI] SelectionWatcher.start failed: {ex}")
    def stop(self):
        try:
            if self._registered:
                # FreeCAD observer APIs are inconsistent across versions. Try token first, then self.
                if self._obs is not None:
                    FreeCADGui.Selection.removeObserver(self._obs)
                else:
                    FreeCADGui.Selection.removeObserver(self)
        except Exception as ex:
            try:
                FreeCADGui.Selection.removeObserver(self)
            except Exception:
                print(f"[AI] SelectionWatcher.stop failed: {ex}")
        self._registered = False
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
_dock_instance = None
_creating_dock = False

class AISidebar(QtWidgets.QWidget):

    def __init__(self):
        global si
        super().__init__(); si=self
        self.setObjectName("AICopilotPopup")
        self.setMinimumSize(420, 620)
        self._worker_thread = None
        self._code_worker = None
        self._launching = False
        self._deferred = None
        self._defer_attempts = 0
        self._retries = 0
        self._pending_input = ""
        self._pending_msgs = None
        self._step_retry_state = None
        self._plan_steps: list[TaskStep] = []
        self._plan_step_idx = 0
        self._plan_paused = False
        self._direct_execute = False
        self._complexity = "complex"
        self._use_llm_classifier = False
        self._run_baseline_names: set = set()
        self._classify_thread = None
        self._classify_worker = None
        self._step_widgets: dict = {}
        self._completed_steps: list[TaskStep] = []
        self._replan_per_step = False
        self._abandoned = False
        self._worker_gen = 0
        self._code_visible = False
        self._ready = False
        self._closed = False
        self._mode = "build"
        self.orch = None
        self._session_metrics = {
            "attempts_per_step": [],
            "retries_per_step": [],
            "failure_categories": {},
            "backtrack_count": 0,
            "step_outcomes": [],
        }
        self._provider_models = {}
        self._provider_order = []

        # Settings (defaults match settings_dialog.DEFAULT_SETTINGS)
        self._retries_per_step = 5
        self._auto_replan = False
        self._sandbox_mode = True
        self._max_defer_attempts = 15
        self._ollama_url = "http://localhost:11434"
        self._ollama_model = "llama3"
        self._theme = "dark"
        self._chat_font_size = 13
        self._code_font_size = 12
        self._temperature = 0.7
        self._max_history_length = 50
        self.max_tokens = 16384

        # ── Initialize layout ──────────────────────────────────
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Modular Widgets ───────────────────────────────────
        self.sidebar_widget = SidebarWidget(self)
        main_layout.addWidget(self.sidebar_widget)

        self.chat_panel = ChatPanel(self)
        self.sidebar_widget.set_chat_panel(self.chat_panel)

        # ── Setup TaskBoard Widget ─────────────────────────────
        self._taskboard_container = QtWidgets.QScrollArea()
        self._taskboard_container.setWidgetResizable(True)
        self._taskboard_container.setStyleSheet("QScrollArea{background:rgba(15,16,18,0.85); border:1px solid rgba(255,255,255,0.05); border-radius:8px;} QScrollBar:vertical{width:3px;background:transparent;} QScrollBar::handle:vertical{background:rgba(255,255,255,0.1);border-radius:2px;}")
        self._taskboard_container.setVisible(False)
        self._taskboard_container.setMinimumHeight(120)
        self._taskboard = QtWidgets.QWidget()
        self._taskboard.setStyleSheet("background:transparent;border:none;")
        self._tb_layout = QtWidgets.QVBoxLayout(self._taskboard)
        self._tb_layout.setContentsMargins(10, 8, 10, 8)
        self._tb_layout.setSpacing(6)
        self._taskboard_container.setWidget(self._taskboard)

        self._scene_fingerprint = QtWidgets.QLabel("")
        self._scene_fingerprint.setVisible(False)
        self._scene_fingerprint.setStyleSheet("color:#00f0ff;font-size:9px;padding:2px 4px;border:none;background:transparent;")
        self._tb_layout.addWidget(self._scene_fingerprint)

        self.sidebar_widget.set_taskboard(self._taskboard_container)

        # ── Map Legacy Element Aliases ─────────────────────────
        self._mode_combo = self.sidebar_widget.mode_combo
        self._provider_combo = self.sidebar_widget.provider_combo
        self._model_combo = self.sidebar_widget.model_combo
        self._status_dot = self.sidebar_widget.status_dot
        self._login_btn = self.sidebar_widget.login_btn
        self._stop_step_btn = self.sidebar_widget.stop_step_btn
        self._cancel_plan_btn = self.sidebar_widget.cancel_plan_btn
        self._status_text = self.sidebar_widget.status_text
        self._inp_container = self.sidebar_widget.inp_container
        self.inp = self.sidebar_widget.inp
        self.st = self.sidebar_widget.status_dot_led

        self.chat = self.chat_panel.chat
        self._thinking_header = self.chat_panel._thinking_header
        self._thinking = self.chat_panel._thinking

        

        # Spin animation compatibility
        self.spin = Spinner(self)
        self.spin.setVisible(False)
        self.sidebar_widget.status_layout.insertWidget(0, self.spin)

        # Mascot compatibility — keep hidden (parented to sidebar to avoid orphan window)
        self._mascot = QtWidgets.QWidget(self.sidebar_widget)
        self._mascot.setVisible(False)

        # ── Connect Aliased UI Signals ────────────────────────
        self.sidebar_widget.send_requested.connect(self._do_send)
        self.sidebar_widget.mode_changed.connect(self._on_mode_changed)
        self.sidebar_widget.settings_requested.connect(self.sets)
        self.sidebar_widget.new_chat_requested.connect(self._new_chat)
        self.sidebar_widget.stop_requested.connect(self.stop)
        self.sidebar_widget.stop_step_requested.connect(self._on_stop_step)
        self.sidebar_widget.cancel_plan_requested.connect(lambda: (self.stop(), setattr(self, '_plan_steps', [])))
        self.sidebar_widget.undo_requested.connect(self._on_undo)
        self.sidebar_widget.refresh_models_requested.connect(self._on_refresh_models)
        self._login_btn.clicked.connect(self._show_ai_setup_dialog)

        # Build provider index and populate
        self._build_provider_model_index()
        self._populate_provider_combo()
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)

        # ── Selection Watcher (spatial tagging) ───────────────
        self._sel_watcher = SelectionWatcher()
        self._sel_watcher.tagSelected.connect(self._on_tag_selected)
        self._sel_watcher.start()

        # ── PCB Mode Widget ────────────────────────────────────
        self._pcb_widget = PcbInputWidget(orch=self.orch)
        self._pcb_widget.setVisible(False)
        self._pcb_widget.generate_clicked.connect(self._on_pcb_generate)
        self.sidebar_widget.chat_tab_layout.addWidget(self._pcb_widget)

        # ── DXF Mode Widget ────────────────────────────────────
        self._dxf_widget = DxfInputWidget(orch=self.orch)
        self._dxf_widget.setVisible(False)
        self._dxf_widget.generate_clicked.connect(self._on_dxf_generate)
        self.sidebar_widget.chat_tab_layout.addWidget(self._dxf_widget)

        # Load configuration & build initial orchestrator
        self.load()
        self._rebuild()
        self._pcb_widget.set_vision_info(model=self.c_model or "", api_key=getattr(self, "api_key", "") or "")

        # Clear any stale history — each session is fresh
        if self.orch:
            self.orch.conversation_history.clear()
        self._ready = True
        self._create_viewport_overlay()

    # ── Viewport overlay ─────────────────────────────────────────
    def _create_viewport_overlay(self):
        self._vp_overlay = None
        self._vp_overlay_label = None
        try:
            mw = FreeCADGui.getMainWindow()
            if not mw:
                return
            view3d = None
            for w in mw.findChildren(QtWidgets.QWidget):
                if 'View3DInventor' in w.metaObject().className():
                    view3d = w
                    break
            if not view3d:
                return
            self._vp_overlay = QtWidgets.QWidget(view3d)
            self._vp_overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            self._vp_overlay.setStyleSheet("background:rgba(8,9,10,0.35);")
            self._vp_overlay.setVisible(False)
            self._vp_overlay_label = QtWidgets.QLabel(
                "<div style='text-align:center;padding-top:40%;'>"
                "<span style='color:#00f0ff;font-size:16px;font-weight:700;"
                "letter-spacing:2px;font-family:Consolas,monospace;'>"
                "AI PROCESSING"
                "</span><br>"
                "<span style='color:#4a4f57;font-size:11px;"
                "letter-spacing:1px;'>"
                "GENERATING DESIGN"
                "</span></div>",
                self._vp_overlay,
            )
            self._vp_overlay_label.setAlignment(QtCore.Qt.AlignCenter)
            self._vp_overlay_label.setStyleSheet("background:transparent;")
            self._vp_overlay_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        except Exception:
            pass

    def _show_viewport_overlay(self):
        try:
            if self._vp_overlay:
                view3d = self._vp_overlay.parentWidget()
                if view3d:
                    self._vp_overlay.setGeometry(view3d.rect())
                self._vp_overlay.setVisible(True)
                self._vp_overlay.raise_()
                if self._vp_overlay_label:
                    self._vp_overlay_label.setGeometry(self._vp_overlay.rect())
        except Exception:
            pass

    def _hide_viewport_overlay(self):
        try:
            if self._vp_overlay:
                self._vp_overlay.setVisible(False)
        except Exception:
            pass

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
            fallback_model = PROVIDERS.get(provider, "")
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
        if isinstance(entry, dict):
            return entry
        text = self._model_combo.currentText().strip()
        if text:
            return {"model": text, "label": text, "display": text}
        return {"model": "", "label": ""}

    def _provider_requires_key(self, provider):
        return provider not in PROVIDERS_WITHOUT_KEYS

    def _on_provider_changed(self, _idx):
        provider = self._current_provider()
        self._populate_model_combo(provider)
        self.c_model = self._current_model_entry().get("model", "")
        # Check for provider-key mismatch
        key = getattr(self, 'api_key', '') or ''
        if provider == "anthropic" and key and not key.startswith("sk-ant-"):
            self.msg(
                "Warning",
                f"⚠️ The stored API key doesn't look like an Anthropic key "
                f"(should start with 'sk-ant-').\n"
                f"Open **Settings → API Keys** to enter the correct key."
            )
        elif provider == "deepseek":
            # DeepSeek keys vary (sk-, ds-, etc.) — no strict prefix check
            pass
        self._rebuild()
        self.msg("System", f"Provider: **{self._pretty_provider(provider)}**")
        is_local = provider == "ollama"
        self._model_combo.setVisible(not is_local)
        self._model_combo.setEnabled(not is_local)

    def _on_model_changed(self, _idx):
        entry = self._current_model_entry()
        self.c_model = entry.get("model", "")
        self._rebuild()
        display = entry.get("display") or entry.get("model") or "Default"
        self.msg("System", f"Model: **{display}**")
        if hasattr(self, "_pcb_widget"):
            self._pcb_widget.set_vision_info(model=self.c_model, api_key=getattr(self, "api_key", "") or "")

    def _on_refresh_models(self):
        provider = self._current_provider()
        entry = self._current_model_entry()
        current_model = entry.get("model", "")

        if provider == "ollama":
            api_url = self._ollama_url.rstrip("/") if self._ollama_url else "http://localhost:11434"
        else:
            api_url = self.c_url or ""

        self.msg("System", f"\u21bb Fetching available models from {self._pretty_provider(provider)}...")
        QtWidgets.QApplication.processEvents()

        from orchestrator import fetch_available_models
        fetched = fetch_available_models(provider, api_url=api_url, api_key=self.api_key or "")

        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        seen = set()
        for item in self._provider_models.get(provider, []):
            self._model_combo.addItem(item["display"], item)
            seen.add(item["model"])
        if fetched:
            added = 0
            for m in fetched:
                if m not in seen:
                    display = m.split("/", 1)[1] if "/" in m else m
                    self._model_combo.addItem(display, {"model": m, "label": m, "display": display})
                    added += 1
            if added:
                self.msg("System", f"\u21bb Found {added} additional model(s)")
        else:
            self.msg("System", "Could not fetch models from provider — using presets")

        idx = self._model_combo.findData(current_model, role=Qt.UserRole, flags=Qt.MatchExactly | Qt.MatchCaseSensitive)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        elif current_model:
            self._model_combo.setEditText(current_model)
        self._model_combo.blockSignals(False)

    def load(self):
        p = os.path.join(os.path.dirname(__file__), "config.json")
        cfg = load_json_file(p)

        # If launched by UCAD Launcher, merge centralized config on top
        if _UCAD_HOME:
            cfg = merge_configs(cfg)
            FreeCAD.Console.PrintLog("[AI] Using centralized launcher config\n")

        key_raw = read_secret(cfg, "api_key") or cfg.get("api_key")
        # If no key found in config and we have launcher, try direct
        if not key_raw and _UCAD_HOME:
            try:
                key_raw = get_api_key()
            except Exception:
                pass

        self.api_key = key_raw
        self.c_model = cfg.get("model", "")
        self.c_url = cfg.get("url", "")
        provider = cfg.get("provider", "")
        FreeCAD.Console.PrintLog(
            f"[AI] load: provider={provider} model={self.c_model} "
            f"api_key={'<SET>' if key_raw else '<EMPTY>'} "
            f"(prefix={key_raw[:7] if key_raw else 'N/A'}...)\n"
        )


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
        is_local = selected_provider == "ollama"
        self._model_combo.setVisible(not is_local)
        self._model_combo.setEnabled(not is_local)

        md = cfg.get("mode", "build")
        self.sidebar_widget.set_mode(md)

        # Read general settings
        self._retries_per_step = int(cfg.get("retries_per_step", 5))
        self._auto_replan = bool(cfg.get("auto_replan", False))
        self._sandbox_mode = bool(cfg.get("sandbox_mode", True))
        self._max_defer_attempts = int(cfg.get("max_defer_attempts", 15))
        self._ollama_url = str(cfg.get("ollama_url", "http://localhost:11434"))
        self._ollama_model = str(cfg.get("ollama_model", "llama3"))
        self._proxy_url = str(cfg.get("proxy_url", ""))
        self._theme = str(cfg.get("theme", "dark"))
        self._chat_font_size = int(cfg.get("chat_font_size", 13))
        self._code_font_size = int(cfg.get("code_font_size", 12))
        self._temperature = float(cfg.get("temperature", 0.7))
        self._max_history_length = int(cfg.get("max_history_length", 50))
        raw_tokens = cfg.get("max_tokens", 16384)
        self.max_tokens = int(raw_tokens) if raw_tokens else None

        self._replan_per_step = self._auto_replan

        if has_legacy_plaintext(cfg):
            self._write_config(self.api_key, selected_provider, model=self.c_model, url=self.c_url)

        self._apply_theme(self._theme)

    def _write_config(self, key, prov, model="", url=""):
        if _UCAD_HOME:
            # Write to launcher's centralized config instead
            try:
                import json as _json
                lc_path = os.path.join(_UCAD_HOME, "Config", "config.json")
                cfg = {
                    "provider": prov,
                    "model": model,
                    "url": url,
                    "provider_label": self._provider_combo.currentText(),
                    "model_label": self._current_model_entry().get("label", self._model_combo.currentText()),
                    "mode": self.sidebar_widget.current_mode,
                    "retries_per_step": self._retries_per_step,
                    "auto_replan": self._auto_replan,
                    "sandbox_mode": self._sandbox_mode,
                    "max_defer_attempts": self._max_defer_attempts,
                    "ollama_url": self._ollama_url,
                    "ollama_model": self._ollama_model,
                    "theme": self._theme,
                    "chat_font_size": self._chat_font_size,
                    "code_font_size": self._code_font_size,
                    "temperature": self._temperature,
                    "max_history_length": self._max_history_length,
                    "max_tokens": self.max_tokens or 0,
                    "proxy_url": getattr(self, '_proxy_url', ''),
                }
                os.makedirs(os.path.dirname(lc_path), exist_ok=True)
                tmp = lc_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    _json.dump(cfg, f, indent=2)
                os.replace(tmp, lc_path)
                # Write secret separately
                secret_path = os.path.join(_UCAD_HOME, "Secrets", "secret.bin")
                os.makedirs(os.path.dirname(secret_path), exist_ok=True)
                # Use launcher's encryption if possible
                try:
                    from launcher.config_manager import set_secret
                    set_secret("api_key", key)
                except Exception:
                    pass
                FreeCAD.Console.PrintLog("[AI] Config saved to launcher config\n")
                return
            except Exception as e:
                FreeCAD.Console.PrintError(f"[AI] Failed to write launcher config: {e}\n")

        # Legacy: write to Mod-relative config.json
        cfg = {
            "provider": prov,
            "model": model,
            "url": url,
            "api_key": "",  # placeholder; actual key stored encrypted via store_secret below
            "provider_label": self._provider_combo.currentText(),
            "model_label": self._current_model_entry().get("label", self._model_combo.currentText()),
            "mode": self.sidebar_widget.current_mode,
            # General settings
            "retries_per_step": self._retries_per_step,
            "auto_replan": self._auto_replan,
            "sandbox_mode": self._sandbox_mode,
            "max_defer_attempts": self._max_defer_attempts,
            "ollama_url": self._ollama_url,
            "ollama_model": self._ollama_model,
            "theme": self._theme,
            "chat_font_size": self._chat_font_size,
            "code_font_size": self._code_font_size,
            "temperature": self._temperature,
            "max_history_length": self._max_history_length,
            "max_tokens": self.max_tokens or 0,
            "proxy_url": getattr(self, '_proxy_url', ''),
        }
        store_secret(cfg, "api_key", key)
        atomic_write_json(os.path.join(os.path.dirname(__file__),"config.json"), cfg)
    
    def save(self, key, prov, model="", url=""):
        old_prefix = (self.api_key[:7] + "...") if self.api_key else "<EMPTY>"
        new_prefix = (key[:7] + "...") if key else "<EMPTY>"
        FreeCAD.Console.PrintLog(
            f"[AI] save: provider={prov} model={model} "
            f"old_key_prefix={old_prefix} new_key_prefix={new_prefix}\n"
        )
        self.api_key = key
        self.c_model = model
        self.c_url = url
        self._write_config(key, prov, model=model, url=url)
        self._rebuild()
        self.msg("System","✅ Settings saved!")
    
    def _show_ai_setup_dialog(self):
        """Open the AI Setup dialog (Standard + Pro Mode tabs)."""
        from ai_setup_dialog import show_ai_setup_dialog
        show_ai_setup_dialog(self)

    def _require_orch(self):
        """Raise if orchestrator is not initialized. Guards all methods that access self.orch."""
        if not self.orch:
            raise RuntimeError(
                "Orchestrator not initialized. Use Settings → Rebuild or restart the workbench."
            )

    def _rebuild(self):
        prov = self._current_provider()
        entry = self._current_model_entry()
        mdl = self.c_model or entry.get("model") or PROVIDERS.get(prov, "")
        if prov == "ollama" and self._ollama_url:
            api_url = self._ollama_url.rstrip("/")
        else:
            api_url = self.c_url if self.c_url else None
        key = self.api_key if prov != "templates" else ""
        FreeCAD.Console.PrintLog(
            f"[AI] _rebuild: provider={prov} model={mdl} "
            f"api_key={'<SET>' if key else '<EMPTY>'} "
            f"(prefix={key[:7] if key else 'N/A'}...)\n"
        )
        self.orch=AIOrchestrator(
            key,
            provider=prov,
            model=mdl,
            api_url=api_url,
            proxy_url=getattr(self, '_proxy_url', '') or None,
        )

        # Validate presets against live model list.
        warnings = []
        if key and prov in LITELLM_PROVIDERS and prov != "ollama":
            models = ModelRegistry.discover(prov, api_key=key, api_url=api_url or "")
            if models:
                preset_keys = [e[2] for e in PRESET_MODELS if e[1] == prov and e[2]]
                for full_id in preset_keys:
                    raw = full_id.split("/", 1)[-1] if "/" in full_id else full_id
                    if raw not in models:
                        warnings.append(
                            f"[AI] Preset model '{full_id}' is not available "
                            f"for '{prov}'. "
                            f"Available: {', '.join(models[:5])}...\n"
                        )
        for w in warnings:
            FreeCAD.Console.PrintWarning(w)
            FreeCAD.Console.PrintLog(w)

        if hasattr(self, '_pcb_widget') and self._pcb_widget:
            self._pcb_widget.set_orch(self.orch)
            if self._pcb_widget._board_data:
                self.orch._board_context = self._pcb_widget._board_data
        if hasattr(self, '_dxf_widget') and self._dxf_widget:
            self._dxf_widget.set_orch(self.orch)
            if self._dxf_widget._dxf_data:
                self.orch._dxf_context = self._dxf_widget._dxf_data
        # Apply general settings to orchestrator
        if self.orch:
            self.orch.use_sandbox = self._sandbox_mode
            if hasattr(self, '_temperature'):
                self.orch.temperature = self._temperature
            if hasattr(self, 'max_tokens') and self.max_tokens is not None:
                self.orch.max_tokens = self.max_tokens
    
    def _apply_settings(self, settings):
        """Called by settings_dialog to apply all general settings."""
        self._retries_per_step = int(settings.get("retries_per_step", 5))
        self._auto_replan = bool(settings.get("auto_replan", False))
        self._sandbox_mode = bool(settings.get("sandbox_mode", False))
        self._max_defer_attempts = int(settings.get("max_defer_attempts", 15))
        self._ollama_url = str(settings.get("ollama_url", "http://localhost:11434"))
        self._ollama_model = str(settings.get("ollama_model", "llama3"))
        self._theme = str(settings.get("theme", "dark"))
        self._chat_font_size = int(settings.get("chat_font_size", 13))
        self._code_font_size = int(settings.get("code_font_size", 12))
        self._temperature = float(settings.get("temperature", 0.7))
        self._max_history_length = int(settings.get("max_history_length", 50))
        self.max_tokens = int(settings.get("max_tokens", 0)) or None

        # Persist to config.json
        cfg = self._read_cfg_raw()
        from settings_dialog import SETTINGS_KEYS
        for k in SETTINGS_KEYS:
            cfg[k] = settings.get(k)

        if _UCAD_HOME:
            # Write to launcher's centralized config
            try:
                import json as _json
                lc_path = os.path.join(_UCAD_HOME, "Config", "config.json")
                os.makedirs(os.path.dirname(lc_path), exist_ok=True)
                existing = {}
                if os.path.exists(lc_path):
                    with open(lc_path, "r", encoding="utf-8") as f:
                        existing = _json.load(f)
                existing.update(cfg)
                tmp = lc_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    _json.dump(existing, f, indent=2)
                os.replace(tmp, lc_path)
            except Exception as e:
                FreeCAD.Console.PrintError(f"[AI] Failed to write launcher config: {e}\n")

        from secret_store import atomic_write_json
        atomic_write_json(os.path.join(os.path.dirname(__file__), "config.json"), cfg)

        self._apply_theme(self._theme)
        self._replan_per_step = self._auto_replan

        # Apply settings to orchestrator
        if self.orch:
            self.orch.use_sandbox = self._sandbox_mode
            self.orch.temperature = self._temperature
            if self.max_tokens is not None:
                self.orch.max_tokens = self.max_tokens

        # Apply font sizes to chat
        if hasattr(self, 'chat') and self.chat:
            font = self.chat.font()
            font.setPointSize(self._chat_font_size)
            self.chat.setFont(font)

        self.msg("System", f"\u2705 Settings saved! Theme: {self._theme}")

    def _apply_theme(self, theme_name):
        """Apply light or dark theme to the sidebar and chat panel."""
        if theme_name == "light":
            # Light theme: override styles on main widgets
            self.sidebar_widget.setStyleSheet("""
                QWidget#AICopilotPopup { background:#f5f5f5; }
                QWidget { color:#1a1a1a; }
            """)
            self.chat_panel.chat.setStyleSheet("""
                QTextEdit {
                    background: #ffffff;
                    color: #1a1a1a;
                    font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', Arial, sans-serif;
                    font-size: 13px;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    padding: 10px 12px;
                    selection-background-color: rgba(0,120,215,0.2);
                }
                QScrollBar:vertical { background:transparent; width:3px; margin:0; }
                QScrollBar::handle:vertical { background:rgba(0,0,0,0.15); border-radius:2px; }
            """)
            self._status_text.setStyleSheet("color:#555;font-size:10px;font-weight:500;letter-spacing:0.5px;")
            self._status_dot.setStyleSheet("color:#374766;font-size:12px;padding:0 4px;")
        else:
            # Dark theme (default)
            self.sidebar_widget.setStyleSheet("")
            self.chat_panel.chat.setStyleSheet("")
            self._status_text.setStyleSheet("color:#8a9099;font-size:10px;font-weight:500;letter-spacing:0.5px;")

    def _read_cfg_raw(self):
        """Read the raw config dict from disk."""
        p = os.path.join(os.path.dirname(__file__), "config.json")
        from secret_store import load_json_file
        return load_json_file(p)

    def _save_entry_code(self, code):
        self._require_orch()
        if code:
            ok, path = self.orch.save_macro(code)
            self._status_text.setText("\U0001f4be Saved!" if ok else f"\u274c {path}")
            self._status_text.setStyleSheet(
                f"color:{'#00f0ff' if ok else '#ff2d78'};font-size:10px;font-weight:500;letter-spacing:0.5px;"
            )
            QtCore.QTimer.singleShot(3000, lambda: self._reset_status_after_save())

    def msg(self, s, t, chat=False):
        import html as htmlmod
        if s == "System" and not chat:
            plain = re.sub(r"\*\*(.*?)\*\*", r"\1", str(t or "")).replace("\n", " ").strip()
            if plain:
                self._status_text.setText(plain[:120])
            return

        # Track code blocks from AI responses for the Apply button
        if s not in ("You", "System", "Error"):
            raw = str(t or "")
            blocks = re.findall(r"```(?:\w+)?\n(.*?)```", raw, re.DOTALL)
        text_html = htmlmod.escape(str(t or ""))
        # Fenced code blocks → styled <pre><code> (before <br> to preserve newlines)
        text_html = re.sub(
            r'```(\w*)\n(.*?)```',
            lambda m: (
                f'<pre style="background:rgba(16,30,62,0.6);color:#00f0ff;'
                f'padding:10px 14px;border:1px solid rgba(255,255,255,0.07);'
                f'border-radius:6px;font-family:Consolas,monospace;font-size:12px;'
                f'line-height:1.5;overflow-x:auto;margin:6px 0;white-space:pre-wrap;">'
                f'<code style="background:transparent;color:inherit;padding:0;'
                f'font-size:inherit;">{m.group(2)}</code></pre>'
            ),
            text_html,
            flags=re.DOTALL,
        )
        text_html = text_html.replace("\n", "<br>")
        text_html = re.sub(
            r'`([^`]+)`',
            r'<code style="background:rgba(16,30,62,0.6);color:#00f0ff;padding:2px 6px;'
            r'border:1px solid rgba(255,255,255,0.07);border-radius:5px;'
            r'font-family:Consolas,monospace;font-size:12px;">\1</code>',
            text_html,
        )
        _G = "rgba(8,18,44,0.75)"
        _B = "rgba(255,255,255,0.07)"
        _BP = "rgba(255,255,255,0.09)"
        _CY = "#00f0ff"
        _VI = "#c084fc"
        _PI = "#ff2d78"
        _TX = "#eef2ff"
        _SX = "#6b7fa3"

        if s == "System":
            block = (
                f'<div style="margin:5px 0;display:flex;justify-content:center;">'
                f'<div style="background:{_G};border:1px solid {_B};'
                f'border-top:1px solid {_BP};border-radius:14px;padding:4px 14px;max-width:92%;">'
                f'<div style="color:{_SX};font-size:11px;line-height:1.5;'
                f'text-align:center;">{text_html}</div>'
                f'</div></div>'
            )
        elif s == "Error":
            block = (
                f'<div style="margin:10px 0;display:flex;justify-content:flex-start;">'
                f'<div style="background:rgba(44,8,24,0.75);border:1px solid rgba(255,45,120,0.3);'
                f'border-left:3px solid {_PI};border-radius:10px;padding:8px 12px;'
                f'max-width:95%;">'
                f'<div style="color:{_PI};font-size:10px;font-weight:700;'
                f'letter-spacing:1.2px;margin-bottom:3px;">ERROR</div>'
                f'<div style="color:#f0d0dd;font-size:13px;line-height:1.55;">{text_html}</div>'
                f'</div></div>'
            )
        elif s == "You":
            block = (
                f'<div style="margin:10px 0 4px 0;display:flex;'
                f'justify-content:flex-end;">'
                f'<div style="background:rgba(16,30,62,0.6);border:1px solid {_B};'
                f'border-top:1px solid {_BP};border-radius:10px 10px 4px 10px;'
                f'padding:8px 12px;max-width:84%;">'
                f'<div style="color:{_SX};font-size:9px;font-weight:800;'
                f'letter-spacing:1.8px;margin-bottom:2px;">YOU</div>'
                f'<div style="color:{_TX};font-size:13px;line-height:1.55;">{text_html}</div>'
                f'</div></div>'
            )
        elif s == "Plan":
            block = (
                f'<div style="margin:6px 0;display:flex;justify-content:flex-start;">'
                f'<div style="background:rgba(24,8,60,0.65);border:1px solid rgba(192,132,252,0.2);'
                f'border-left:3px solid {_VI};border-radius:10px;padding:8px 12px;'
                f'max-width:92%;">'
                f'<div style="color:{_VI};font-size:9px;font-weight:800;'
                f'letter-spacing:1.2px;margin-bottom:3px;">PLAN</div>'
                f'<div style="color:#ddd6fe;font-size:13px;line-height:1.6;">{text_html}</div>'
                f'</div></div>'
            )
        elif s == "Code":
            block = (
                f'<div style="margin:6px 0;display:flex;justify-content:flex-start;">'
                f'<div style="background:rgba(8,44,24,0.65);border:1px solid rgba(0,240,255,0.15);'
                f'border-left:3px solid {_CY};border-radius:10px;padding:8px 12px;'
                f'max-width:92%;">'
                f'<div style="color:{_CY};font-size:9px;font-weight:800;'
                f'letter-spacing:1.2px;margin-bottom:3px;">CODE</div>'
                f'<div style="color:#d0f0e0;font-size:13px;line-height:1.6;">{text_html}</div>'
                f'</div></div>'
            )
        elif s == "Result":
            block = (
                f'<div style="margin:6px 0 10px 0;display:flex;justify-content:flex-start;">'
                f'<div style="background:rgba(8,30,44,0.65);border:1px solid rgba(0,240,255,0.15);'
                f'border-left:3px solid {_CY};border-radius:10px;padding:8px 12px;'
                f'max-width:92%;">'
                f'<div style="color:{_CY};font-size:9px;font-weight:800;'
                f'letter-spacing:1.2px;margin-bottom:3px;">RESULT</div>'
                f'<div style="color:#cce8f0;font-size:13px;line-height:1.55;">{text_html}</div>'
                f'</div></div>'
            )
        else:
            block = (
                f'<div style="margin:4px 0 8px 0;display:flex;'
                f'justify-content:flex-start;">'
                f'<div style="background:rgba(8,18,44,0.75);border:1px solid {_B};'
                f'border-top:1px solid {_BP};border-left:3px solid {_CY};'
                f'border-radius:10px 10px 10px 4px;padding:8px 12px;max-width:92%;">'
                f'<div style="color:{_CY};font-size:9px;font-weight:800;'
                f'letter-spacing:1.8px;margin-bottom:2px;">AI</div>'
                f'<div style="color:{_TX};font-size:13px;line-height:1.6;">{text_html}</div>'
                f'</div></div>'
            )

        if self._mascot.isVisible():
            self._mascot.hide()
        self.chat.append(block)
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())
        QtWidgets.QApplication.processEvents()
    
    def _append_thinking_to_chat(self, text):
        escaped = _html.escape(text)
        html = (
            '<details style="margin:2px 0 6px 20px;">'
            '<summary style="color:#6b7fa3;font-size:11px;font-weight:600;'
            'cursor:pointer;padding:2px 0;letter-spacing:0.5px;">'
            '\U0001f4ad Reasoning</summary>'
            '<div style="color:#6b7fa3;font-size:11px;line-height:1.5;'
            'padding:6px 10px;border-left:2px solid #c084fc;margin-top:4px;">'
            f'{escaped}</div></details>'
        )
        self.chat.append(html)
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def _tp(self):
        if not hasattr(self, 'pe'):
            return
        v=not self.pe.isVisible(); self.pe.setVisible(v)
        if v:
            try:
                s=FreeCADGui.Selection.getSelection()
                if s: self.pe.show_obj(s[-1])
            except Exception as ex:
                _report_gui_error("panel.property_toggle", ex)
    
    def _tpl(self):
        d=TemplateDialog(self)
        if d.exec() and d.selected:
            name=d.selected
            code=render_template(name).replace("```python\n","").replace("\n```","")
            self._do_send(f"use template {name}")
    
    def _newdoc(self):
        self.inp.setText("create a new document called AI_Design"); self.send()
    
    def _reset_status_after_save(self):
        try:
            if not self._closed and self._status_text:
                self._set_dot("#8a9099")
                self._status_text.setText("READY")
                self._status_text.setStyleSheet("color:#8a9099;font-size:10px;font-weight:500;letter-spacing:0.5px;")
        except RuntimeError:
            pass

    def _set_dot(self, color):
        self.st.setStyleSheet(f"color:{color};font-size:9px;background:transparent;")
    
    def _toggle_objects(self):
        if not hasattr(self, '_obj_container'):
            return
        v = not self._obj_container.isVisible()
        self._obj_container.setVisible(v)
        self._obj_arrow.setText("▾" if v else "▸")
        self._obj_arrow.setStyleSheet("color:#8da2bb;font-size:10px;font-weight:bold;")
        if v: self.tree.refresh()

    def closeEvent(self, e):
        self._closed = True
        if hasattr(self.sidebar_widget, '_hint_timer'):
            self.sidebar_widget._hint_timer.stop()
        self.stop()
        if hasattr(self, '_sel_watcher'):
            self._sel_watcher.stop()
        super().closeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self._closed = False
        if hasattr(self.sidebar_widget, '_hint_timer') and not self.sidebar_widget._hint_timer.isActive():
            self.sidebar_widget._hint_timer.start(4000)
            self.sidebar_widget._rotate_hint()
        # Reset to build mode so chat input is always visible on reopen
        if self.sidebar_widget.current_mode != "build":
            self.sidebar_widget.set_mode("build")

    def _rotate_hint(self):
        if hasattr(self.sidebar_widget, '_rotate_hint'):
            self.sidebar_widget._rotate_hint()
    
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
        except Exception as ex:
            print(f"[AI] _on_sel failed: {ex}")
    
    def _new_chat(self):
        """Reset conversation: clear chat, history, and state; show mascot."""
        self._require_orch()
        if self._code_worker:
            self._code_worker.cancel()
        self.orch.conversation_history.clear()
        self.chat.clear()
        self._mascot.setVisible(True)
        self._plan_steps = []
        self._plan_step_idx = 0
        self._plan_paused = False
        self._step_widgets = {}
        self._scene_fingerprint.setVisible(False)
        self._pending_input = ""
        self._pending_msgs = None
        self._step_retry_state = None
        self._retries = 0
        self._set_dot("#8a9099")
        self._status_text.setText("READY"); self._status_text.setStyleSheet("color:#8a9099;font-size:10px;font-weight:500;letter-spacing:0.5px;")
        self.spin.setVisible(False)
        # Reset DXF state
        if self.orch:
            self.orch._dxf_context = None
        if hasattr(self, '_dxf_widget') and self._dxf_widget:
            self._dxf_widget._dxf_data = None
            self._dxf_widget._dxf_path = None
            self._dxf_widget.setCurrentIndex(0)
            self._dxf_widget._drop_zone.setText(
                "<div style='font-size:14px; color:#8b949e;'>"
                "DROP .dxf FILE HERE<br>"
                "<span style='font-size:11px; color:#484f58;'>or click to browse</span>"
                "</div>"
            )

    def stop(self):
        self._hide_viewport_overlay()
        self._abandoned = True
        if self._code_worker:
            self._code_worker.cancel()
            self._worker_gen += 1
        # Cancel the current plan step so its state reflects the abandonment
        if self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
            try:
                self._plan_steps[self._plan_step_idx].cancel()
            except Exception:
                pass
        # Do NOT quit() or wait() the thread — let it finish its current
        # operation naturally. The _cancel flag and _abandoned flag
        # suppress signal handlers. The thread's cleanup signals
        # (finished → thread.quit → deleteLater) still fire safely.
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
            self._status_text.setText("💬 Exported"); self._status_text.setStyleSheet("color:#6af7b8;font-size:11px;font-weight:500;")
            QtCore.QTimer.singleShot(5000,lambda: (self._set_dot("#8a9099"), self._status_text.setText("READY"), self._status_text.setStyleSheet("color:#8a9099;font-size:10px;font-weight:500;letter-spacing:0.5px;")))
        except Exception: self._status_text.setText("❌ Export failed"); self._status_text.setStyleSheet("color:#f76a6a;font-size:11px;font-weight:500;")
    
    def undo(self): self._do_send("undo last operation")
    
    def sets(self):
        from settings_dialog import show_settings_dialog
        show_settings_dialog(self)
    
    # ── Send ──────────────────────────────────────────────────
    def _launch_worker(self, api_msgs, user_input):
        """Start CodeWorker in a background QThread for the API call only."""
        if self._closed or self._abandoned:
            return False
        self._require_orch()
        self._cleanup_dead_worker_refs()
        if self._launching:
            return False
        if self._is_worker_thread_running():
            self._worker_thread.quit()
            self._worker_thread.wait(300)
            self._worker_thread = None
            self._code_worker = None
        if self._worker_thread:
            self._worker_thread = None
        self._code_worker = None
        self._launching = True
        self._abandoned = False
        self._worker_gen += 1
        gen = self._worker_gen
        try:
            self._worker_thread = QtCore.QThread()
            plan_steps = self._plan_steps if self._plan_steps else []
            step_index = max(0, min(self._plan_step_idx, len(plan_steps) - 1)) if plan_steps else 0
            scene = self.orch.capture_scene() if hasattr(self.orch, 'capture_scene') else {}
            self._code_worker = CodeWorker(
                self.orch,
                api_msgs=api_msgs,
                user_input=user_input,
                plan_steps=plan_steps,
                step_index=step_index,
                scene=scene,
                mode=self._mode,
                gen=gen,
                api_key=self.api_key,
                provider=self._current_provider(),
            )
            model_name = getattr(self.orch, 'custom_model', '') or 'AI'
            self._status_text.setText(f"🔧 Builder {model_name}")
            self._thinking_header.setText(f"⚡ Builder ({model_name}) is generating:")
            self._thinking_header.setVisible(True)
            self._thinking.setVisible(True)
            self._thinking.clear()
            self._code_worker.moveToThread(self._worker_thread)
            self._worker_thread.started.connect(self._code_worker.run)
            self._code_worker.finished.connect(self._on_code_ready)
            self._code_worker.error.connect(self._on_worker_err)
            self._code_worker.stream.connect(self._on_stream)
            self._code_worker.finished.connect(self._worker_thread.quit)
            self._code_worker.finished.connect(self._code_worker.deleteLater)
            self._code_worker.error.connect(self._worker_thread.quit)
            self._code_worker.error.connect(self._code_worker.deleteLater)
            self._worker_thread.finished.connect(lambda th=self._worker_thread: self._on_worker_thread_finished(th))
            self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        finally:
            self._launching = False
        self._show_viewport_overlay()
        self._worker_thread.start()
        return True

    def _cleanup_dead_worker_refs(self):
        """Clear Python refs when underlying Qt objects were deleted, or force-stop a stale worker."""
        if self._worker_thread is None:
            return
        try:
            if self._worker_thread.isRunning():
                self._worker_thread.quit()
                self._worker_thread.wait(300)
                self._worker_thread = None
                self._code_worker = None
        except RuntimeError:
            self._worker_thread = None
            self._code_worker = None

    def _is_worker_thread_running(self):
        """Return running state without raising if QThread C++ object was deleted."""
        if self._worker_thread is None:
            return False
        try:
            return self._worker_thread.isRunning()
        except RuntimeError:
            self._worker_thread = None
            self._code_worker = None
            return False

    def _on_worker_thread_finished(self, thread_obj):
        """Drop refs only when the finished signal belongs to the active worker thread."""
        if self._worker_thread is thread_obj:
            self._worker_thread = None
            self._code_worker = None

    def _do_send(self, text):
        self._require_orch()
        # Cancel any running step/plan from prior session, even if the worker
        # thread already finished.  Without this, stale _plan_steps from a
        # closeEvent (which doesn't call _finish()) would survive into the new
        # request and execute unexpected steps after the new code runs.
        if self._is_worker_thread_running() or self._plan_steps:
            if self._is_worker_thread_running():
                self._on_stop_step()
            if not self._plan_paused:
                self._finish()
                self.msg("System", "⏹ Stopped prior session for new request.", chat=True)
        if self._is_worker_thread_running():
            self._on_stop_step()
        self.msg("You", text)
        self.spin.setVisible(True)
        self._set_dot("#00f0ff")
        self._status_text.setText("🤔 THINKING..."); self._status_text.setStyleSheet("color:#00f0ff;font-size:10px;font-weight:500;letter-spacing:0.5px;")
        self.msg("System", "🤔 Thinking...", chat=True)
        self._retries = 0
        self._step_retry_state = None
        tl = text.lower().strip()
        if self._plan_paused and any(w in tl for w in ("execute", "go ahead", "run", "do it", "proceed", "continue", "yes")):
            self._plan_paused = False
            original = self._pending_input or text
            self._pending_input = original
            self._mode = "build"
            self.sidebar_widget.set_mode("build")
            self._stop_step_btn.setVisible(True)
            self._cancel_plan_btn.setVisible(True)
            self.msg("System", "▶️ Executing plan...", chat=True)
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
        elif self._plan_paused and any(w in tl for w in ("revise", "modify", "change")):
            self._plan_paused = False
            self.msg("System", "🔄 Revising plan based on your feedback...", chat=True)
            msgs = self.orch.build_messages(text, mode="plan", completed_steps=self._completed_steps)
            self._pending_msgs = msgs
            self._pending_input = text
            self._launch_worker(msgs, text)
            return
        elif self._plan_paused and any(w in tl for w in ("explain", "why", "what", "analyze", "review")):
            delta_c = self.orch.last_delta_c
            topo_results = self.orch.last_topology
            explanation = self.orch.explain_spec_deviation(
                self._pending_input or "",
                "", delta_c, topo_results
            )
            self.msg("System", f"🔍 ΔS analysis:\n{explanation[:500]}", chat=True)
            return
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
                self.msg("System", f"▶️ Resuming plan at step {step_idx+1}", chat=True)
                self._launch_worker(msgs, original_request)
                return
        self._pending_input = ""
        self._pending_msgs = None
        self._plan_steps = []
        self._plan_step_idx = 0
        self._plan_paused = False
        self._session_metrics = {
            "attempts_per_step": [],
            "retries_per_step": [],
            "failure_categories": {},
            "backtrack_count": 0,
            "step_outcomes": [],
        }
        self._capture_run_baseline()
        self._mode = self.sidebar_widget.current_mode
        if self.orch.is_local:
            # Local model: skip planning/complexity, go straight to code gen
            self._pending_msgs = self.orch.build_messages(text, mode=self._mode)
            if not self._pending_msgs:
                self.msg("AI", "I can only help with FreeCAD modeling tasks like creating shapes, applying operations, or modifying objects.")
                self._finish()
                return
            self._pending_input = text
            self._launch_worker(self._pending_msgs, text)
            return
        if self._mode == "build":
            # Complexity-driven dispatch: classify the request, then route to
            # the SIMPLE direct-execute path or the MEDIUM/COMPLEX plan path.
            label, confident = self.orch.classify_request(text)
            if not confident and self._use_llm_classifier:
                # Optional cheap LLM tie-breaker on a background thread. The
                # result slot (_on_classified) runs on the main thread and
                # builds messages there (build_messages is main-thread-only).
                # Disabled by default — the rule-table label is used directly.
                self._pending_input = text
                self._launch_classify_worker(text, fallback_label=label)
                return
            self._dispatch_build(text, label)
            return
        self._pending_msgs = self.orch.build_messages(text, mode=self._mode)
        self._pending_input = text
        self._launch_worker(self._pending_msgs, text)

    def _capture_run_baseline(self):
        """Snapshot the document object names at the start of a fresh request.
        The goal-check compares against this baseline so pre-existing geometry
        in a stale scene cannot trigger a false 'task complete' mid-sequence."""
        self._run_baseline_names = self._capture_doc_names()

    def _dispatch_build(self, text, label):
        """Route a classified build request to the right execution path."""
        self._complexity = label
        self._capture_run_baseline()

        # Tool dispatch: simple CAD commands skip the LLM entirely.
        handled, usage = self._try_tool_dispatch(text)
        if handled:
            return

        # Request-level dedup pre-flight (main thread, resolves before dispatch).
        if label in ("simple", "medium"):
            if not self._dedup_preflight(text, label):
                return  # user cancelled; _dedup_preflight already called _finish()
        if label == "simple":
            self._direct_execute = True
            self._pending_msgs = self.orch.build_messages(text, mode="simple")
        else:
            self._direct_execute = False
            self._pending_msgs = self.orch.build_messages(text, mode="build")
        self._pending_input = text
        self._launch_worker(self._pending_msgs, text)

    def _try_tool_dispatch(self, text: str) -> tuple:
        """Attempt to handle text with a registered CAD tool.
        Returns (handled: bool, usage: str).
        If handled=False, caller should continue to normal LLM dispatch."""
        if not text or not self.orch:
            return False, ""
        # Only attempt tool dispatch when the request matches a known tool keyword.
        # The JSON router (LLM-based) is NOT used for routing — it is too unreliable
        # and tends to pick the wrong tool for non-tool requests.
        if self.orch._should_use_tool(text):
            handled, message = self.orch.route_as_tool(text)
            if handled:
                self.msg("AI", message)
                self.orch.record_result(text, "", True, message, 0)
                self._finish()
                return True, "tool"
        return False, ""

    def _primitive_typeids_for(self, text):
        """Map primitive nouns in a SIMPLE request to likely Part TypeIds.
        Used by the dedup pre-flight to detect an existing duplicate."""
        t = (text or "").lower()
        mapping = [
            (("box", "cube", "block", "rectangle", "rectangular", "cuboid", "square"), "Part::Box"),
            (("cylinder", "tube", "pipe", "shaft", "rod"), "Part::Cylinder"),
            (("sphere", "ball"), "Part::Sphere"),
            (("cone",), "Part::Cone"),
            (("torus", "ring", "donut"), "Part::Torus"),
        ]
        out = []
        for kws, tid in mapping:
            if any(re.search(r"\b" + re.escape(k), t) for k in kws):
                out.append(tid)
        return out

    def _dedup_preflight(self, text, label):
        """If the scene already contains object(s) matching the request, ask the
        user whether to replace them, keep both, or cancel.

        Runs fully on the main thread (modal dialog) BEFORE any worker is
        launched, so there is no race with the worker. Returns True to proceed
        with dispatch, False to abort.

        SIMPLE: triggers when any matching primitive already exists.
        MEDIUM: triggers only when EVERY primitive type the request mentions is
        already present (full composition) — avoids false positives on a scene
        that only partially matches. COMPLEX is never pre-flighted here."""
        if label not in ("simple", "medium"):
            return True
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return True
        target_tids = self._primitive_typeids_for(text)
        if not target_tids:
            return True
        present_tids = {tid for tid in target_tids
                        if any((getattr(o, "TypeId", "") or "") == tid for o in doc.Objects)}
        if label == "simple":
            trigger = bool(present_tids)
        else:  # medium
            trigger = present_tids == set(target_tids)
        if not trigger:
            return True
        existing = [o for o in doc.Objects
                    if (getattr(o, "TypeId", "") or "") in present_tids]
        if not existing:
            return True
        try:
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Object already exists")
            names = ", ".join(o.Label for o in existing[:5])
            box.setText(
                f"The scene already contains {len(existing)} matching object(s): {names}.\n\n"
                "Replace them, keep both, or cancel?"
            )
            replace_btn = box.addButton("Replace", QtWidgets.QMessageBox.DestructiveRole)
            keep_btn = box.addButton("Keep both", QtWidgets.QMessageBox.AcceptRole)
            cancel_btn = box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
            box.setDefaultButton(keep_btn)
            box.exec()
            clicked = box.clickedButton()
        except Exception:
            return True  # never block on a dialog failure
        if clicked is cancel_btn:
            self.msg("System", "Cancelled — kept existing object(s).", chat=True)
            self._finish()
            return False
        if clicked is replace_btn:
            try:
                doc.openTransaction("AICompanion: replace existing")
                for o in existing:
                    try:
                        doc.removeObject(o.Name)
                    except Exception:
                        continue
                doc.commitTransaction()
                doc.recompute()
                self.msg("System", f"Removed {len(existing)} existing object(s) (undoable).", chat=True)
            except Exception as ex:
                self.msg("System", f"Could not remove existing objects: {ex}", chat=True)
        return True

    def _launch_classify_worker(self, text, fallback_label="medium"):
        """Run the cheap LLM complexity tie-breaker on a background thread."""
        if self._closed:
            return
        self._require_orch()
        # Tear down any prior classify worker.
        self._cleanup_classify_worker()
        self._set_dot("#00f0ff")
        self._status_text.setText("🧭 Classifying...")
        self._classify_thread = QtCore.QThread()
        self._classify_worker = ClassifyWorker(
            self.orch, user_input=text, fallback_label=fallback_label, gen=self._worker_gen
        )
        self._classify_worker.moveToThread(self._classify_thread)
        self._classify_thread.started.connect(self._classify_worker.run)
        self._classify_worker.finished.connect(self._on_classified)
        self._classify_worker.finished.connect(self._classify_thread.quit)
        self._classify_worker.finished.connect(self._classify_worker.deleteLater)
        self._classify_thread.finished.connect(self._classify_thread.deleteLater)
        self._classify_thread.start()

    def _cleanup_classify_worker(self):
        if self._classify_worker is not None:
            try:
                self._classify_worker.cancel()
            except Exception:
                pass
        if self._classify_thread is not None:
            try:
                if self._classify_thread.isRunning():
                    self._classify_thread.quit()
                    self._classify_thread.wait(300)
            except RuntimeError:
                pass
        self._classify_thread = None
        self._classify_worker = None

    def _on_classified(self, label, text, gen):
        """Main-thread slot: resolved complexity label from the LLM tie-breaker."""
        self._classify_thread = None
        self._classify_worker = None
        if self._closed or self._abandoned:
            return
        if label not in ("simple", "medium", "complex"):
            label = "medium"
        self._dispatch_build(text, label)

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
    MAX_DEFER_ATTEMPTS = 15

    def _defer(self, action, *args):
        """Schedule a single action for the next event-loop tick (outside signal chain).
        For 'next_step' actions, applies a 2-second pacing delay so the user can
        see the just-built geometry before the next step's API call begins.
        The delay runs as a QTimer on the main thread, so the UI stays responsive
        (paint, input) during the wait.
        """
        if self._closed:
            return
        if self._deferred is not None:
            return
        self._deferred = (action, args, self._worker_gen)
        self._defer_attempts = 0
        self.spin.setVisible(False)
        delay_ms = 2000 if action == "next_step" else 25
        QtCore.QTimer.singleShot(delay_ms, self._flush_deferred)

    def _flush_deferred(self):
        """Execute deferred action — retry if old thread is still draining."""
        if self._closed:
            return
        action_args = self._deferred
        self._deferred = None
        if action_args is None:
            return
        action, args, gen = action_args
        if gen != self._worker_gen:
            return
        self._defer_attempts += 1
        if self._defer_attempts > self.MAX_DEFER_ATTEMPTS:
            self.msg("Error", "Deferred action exhausted — giving up.", chat=True)
            self._launching = False
            self._finish()
            return
        launched = False
        try:
            if action == "next_step":
                launched = self._request_next_step(*args)
            elif action == "retry":
                launched = self._launch_worker(*args)
        except Exception as ex:
            import traceback as _tb
            try:
                FreeCAD.Console.PrintError(
                    f"[AICompanion] deferred '{action}' failed:\n{_tb.format_exc()}\n"
                )
            except Exception:
                pass
            self.msg("Error", f"Deferred '{action}' failed: {ex}", chat=True)
            self._finish()
            return
        if not launched:
            if self._deferred is None:
                self._deferred = (action, args, gen)
                QtCore.QTimer.singleShot(25, self._flush_deferred)

    def _on_code_ready(self, raw_text, code, used_api, gen=0):
        self._require_orch()
        try:
            if self._closed or self._abandoned:
                return
            if gen != 0 and gen != self._worker_gen:
                return
            if raw_text and code:
                thinking = self.orch.extract_thinking(raw_text)
                if thinking:
                    self._append_thinking_to_chat(thinking[:800])

            # Build mode — auto-plan detection for multi-step requests.
            # Skipped on the SIMPLE direct-execute path, which runs one block.
            if self._mode == "build" and not self._plan_steps and not self._direct_execute:
                plan_source = raw_text or code or ""
                # MEDIUM requests are capped to a short guided plan; COMPLEX is uncapped.
                cap = 3 if self._complexity == "medium" else None
                steps = self.orch.extract_plan(plan_source, max_steps=cap)
                if steps and len(steps) >= 2:
                    self._plan_steps = [TaskStep(s) for s in steps] if steps else []
                    if steps:
                        self.orch.build_dag_from_plan(steps)
                    self._plan_step_idx = 0
                    self._plan_paused = False
                    self._refresh_taskboard()
                    plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
                    self.msg("Plan", f"Plan ({len(steps)} steps):\n{plan_text}")
                    self._defer("next_step", self.orch.capture_observation())
                    return

            # Plan mode — extract plan and pause
            if self._mode == "plan":
                plan_source = raw_text or code
                steps = self.orch.extract_plan(plan_source)
                self._plan_steps = [TaskStep(s) for s in steps] if steps else []
                if self._plan_steps:
                    self.orch.build_dag_from_plan(steps)
                    plan_text = "\n".join(f"  {i+1}. {s.title}" for i, s in enumerate(self._plan_steps))
                    self.msg("Plan", f"Plan ({len(steps)} steps):\n{plan_text}")
                    self.msg("System", "Send **execute** or **go ahead** to run this plan.", chat=True)
                    self._plan_paused = True
                    self._pending_input = self._pending_input or raw_text
                self._finish(keep_plan=True)
                return

            # PCB mode — switch to chat after generation
            if self._mode == "pcb":
                raw = raw_text or code or ""
                json_match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
                if json_match:
                    try:
                        config_dict = json.loads(json_match.group(1))
                        success, message = self.orch.execute_enclosure_template(params=config_dict)
                        obs = self.orch.capture_observation()
                        icon = "\u2705" if success else "\u274c"
                        result_text = f"{icon} Enclosure: {message}"
                        if obs:
                            result_text += f"\n{obs}"
                        self._pcb_widget.show_chat()
                        self._pcb_widget.add_message(f"<b style='color:#58a6ff;'>AI:</b> {result_text}")
                        self._pcb_widget._status.setText("Done" if success else "Failed")
                        self._finish()
                        return
                    except Exception as err:
                        self._pcb_widget.show_chat()
                        self._pcb_widget._status.setText("JSON parse failed")
                        self._pcb_widget.add_message(
                            f"<b style='color:#ff6b6b;'>AI:</b> JSON parsing error: {err}"
                        )
                        self._finish()
                        return
                if code:
                    success, message = self.orch.execute_code(code)
                    if hasattr(FreeCADGui, '_telemetry') and FreeCADGui._telemetry:
                        FreeCADGui._telemetry.record_ai_script(self._pending_input, code, success, message)
                    obs = self.orch.capture_observation()
                    icon = "\u2705" if success else "\u274c"
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

            # DXF mode — switch to chat after generation
            if self._mode == "dxf":
                if code:
                    success, message = self.orch.execute_code(code)
                    if hasattr(FreeCADGui, '_telemetry') and FreeCADGui._telemetry:
                        FreeCADGui._telemetry.record_ai_script(self._pending_input, code, success, message)
                    obs = self.orch.capture_observation()
                    icon = "✅" if success else "❌"
                    result_text = f"{icon} DXF: {message}"
                    if obs:
                        result_text += f"\n{obs}"
                    self._dxf_widget.show_chat()
                    self._dxf_widget.add_message(f"<b style='color:#58a6ff;'>AI:</b> {result_text}")
                    self._dxf_widget._status.setText("Done" if success else "Failed")
                else:
                    self._dxf_widget._status.setText("No code generated")
                self._finish()
                return

            # Ask mode — show AI response as text, never execute
            if self._mode == "ask":
                display = raw_text or code or "(no response)"
                self.msg("AI", display)
                self.orch.record_result(self._pending_input, code or "", True, "Responded with text", self._retries)
                self._finish()
                return

            # Build mode — execute code sequentially
            # NOTE: `code` is already extracted from fences by generate_code(), use it directly
            if self.orch.is_local:
                # Local model: one-shot execution, no retry/planning
                if not code:
                    self.msg("AI", raw_text or "(no code generated)")
                    self.orch.record_result(self._pending_input, "", True, "No code from local model", 0)
                    self.msg("System", "The model didn't produce code. Try a more specific request.", chat=True)
                    self._finish()
                    return
                success, message = self.orch.execute_code(code, user_input=self._pending_input, skip_validation=True)
                icon = "\u2705" if success else "\u274c"
                self.msg("Result", f"{icon} {message}")
                if success:
                    obs = self.orch.capture_observation()
                    if obs:
                        self.msg("Observation", obs)
                else:
                    self.msg("Error", f"The local model produced code but execution failed: {message[:300]}", chat=True)
                # Record result so next request has scene context
                self.orch.record_result(self._pending_input, code, success, message, 0)
                if hasattr(FreeCADGui, '_telemetry') and FreeCADGui._telemetry:
                    FreeCADGui._telemetry.record_ai_script(self._pending_input, code, success, message)
                self._finish()
                return

            if not code:
                if not used_api and not raw_text:
                    self.msg("Error",
                        "⚠️ The AI provider did not return a response. "
                        "Check your API key and model configuration in **Settings → API Keys**.",
                        chat=True)
                    self.orch.record_result(
                        self._pending_input, "", False,
                        "API returned no response", self._retries)
                    self._finish()
                    return
                self.msg("AI", raw_text)
                self.orch.record_result(self._pending_input, code or "", True, "Responded with text", self._retries)
                self._finish()
                return

            combined_code = code
            # Pre-execution snapshot for scope diagnostics
            pre_snap = self._capture_doc_names()
            # Extract constraint graph from user input before execution
            if self._pending_input:
                self.orch.extract_constraint_graph(self._pending_input)
            success, message = self.orch.execute_code(combined_code, user_input=self._pending_input)
            # Track whether a failure mode was already recorded for this attempt
            # to prevent double-counting: validation + main gate would otherwise
            # add 2 entries per attempt, skewing escalation thresholds.
            _attempt_recorded = False
            # Step output validation
            if success:
                doc = FreeCAD.ActiveDocument
                if doc is not None:
                    step_label = ""
                    skip_cat = None
                    if self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
                        step_label = self._plan_steps[self._plan_step_idx].title
                        step_lower = step_label.lower()
                        if any(w in step_lower for w in
                               ["new document", "new file", "new doc", "create document"]):
                            skip_cat = "new_document"
                    valid, v_msg = self.orch.validate_step_output(
                        doc, step_label=step_label, skip_for_category=skip_cat
                    )
                    if not valid:
                        success = False
                        message = f"Output validation: {v_msg}"
                        if not _attempt_recorded:
                            self._record_step_failure(message)
                            _attempt_recorded = True
            # DC: Post-execution constraint verification
            if success:
                delta_c = self.orch.compute_delta_c()
                topo_results = self.orch.verify_topology_min()
                # Fast-path exit: if ΔC passes strongly, skip deeper checks
                should_exit, fail_reason = self.orch.check_fast_exit(delta_c)
                topology_ok = all(t.min_pass for t in topo_results.values())
                if should_exit and topology_ok:
                    pass  # strong pass — proceed
                else:
                    # ΔC or topology failed — record repair trajectory
                    issues = []
                    if fail_reason:
                        issues.append(fail_reason)
                    if not topology_ok:
                        bad = [n for n, t in topo_results.items() if not t.min_pass]
                        issues.append(f"topology failures: {bad}")
                    if issues:
                        self.msg("System", f"🔍 ΔC verification found issues: {'; '.join(issues)}", chat=True)
                    # Check memory for similar repairs
                    if delta_c.deltas:
                        similar = self.orch.retrieve_repair([d.summary for d in delta_c.deltas[:5]])
                        if similar:
                            self.msg("System",
                                f"📚 Found {len(similar)} similar repair(s) in CAD memory",
                                chat=True)
            # Post-execution snapshot and over-generation warning
            post_snap = self._capture_doc_names()
            if success and self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
                if self._step_scope_warning(
                    pre_snap, post_snap,
                    self._plan_steps[self._plan_step_idx].title
                ):
                    self.msg("Result", "⏹ Plan halted after runaway object creation. Created objects kept — use Undo to revert if needed.")
                    self._finish()
                    return
            # Post-execution verification: check if code missed dependent features
            if success:
                next_tier = min(self._retries + 1, 3)
                consistent, v_diag = self.orch.verify_modifications(
                    self._pending_input, combined_code, self.orch._touched_objects,
                    pre_snapshot=self.orch._pre_execution_snapshot,
                    retry_tier=next_tier
                )
                if not consistent:
                    success = False
                    message = v_diag
                    if not _attempt_recorded:
                        self._record_step_failure(message)
                        _attempt_recorded = True
            total_steps = len(self._plan_steps) if self._plan_steps else 1
            self._status_text.setText(f"⚡ Step {self._plan_step_idx + 1}/{total_steps}")

            max_r = self._retries_per_step if hasattr(self, '_retries_per_step') and self._retries_per_step else (_provider_max_retries(self.orch.provider) if self.orch else MAX_RETRIES)
            if not success and self._should_force_safe_fallback(message, self._pending_input):
                fallback = self.orch.get_fallback_code(
                    self._pending_input,
                    mid_plan=bool(self._plan_steps and self._plan_step_idx < len(self._plan_steps))
                )
                if fallback:
                    fb_success, fb_message = self.orch.execute_code(fallback, user_input=self._pending_input)
                    if fb_success:
                        combined_code = fallback
                        success = True
                        message = f"Used safe fallback: {fb_message}"
                        self.msg("System", "🛟 Switched to a safe fallback generator after repeated sketch/runtime errors.", chat=True)
                        # Record repair trajectory
                        delta_c = self.orch.compute_delta_c()
                        self.orch.record_repair(
                            self._pending_input,
                            [d.summary for d in delta_c.deltas[:5]],
                            "safe_fallback",
                            {"fallback": True},
                            success=True,
                            error_type="execution"
                        )
                    else:
                        self.msg("Error", f"Safe fallback also failed: {fb_message}", chat=True)
                        self.msg("Error", "⛔ AI code and safe fallback both failed. Try describing your request differently or check the FreeCAD document state.", chat=True)
                        if hasattr(FreeCADGui, '_telemetry') and FreeCADGui._telemetry:
                            FreeCADGui._telemetry.record_ai_script(self._pending_input, combined_code, False, message)
                        self._session_metrics["attempts_per_step"].append(self._retries + 1)
                        self._session_metrics["retries_per_step"].append(self._retries)
                        self._session_metrics["step_outcomes"].append("failed")
                        self._finish()
                        return
            if not success:
                if not _attempt_recorded:
                    self._record_step_failure(message)
                cur = (self._plan_steps[self._plan_step_idx]
                       if self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps)
                       else None)
                if cur and cur.should_escalate:
                    cur.escalated = True
                    self._status_text.setText(f"🚀 Retry step {self._plan_step_idx + 1}/{total_steps}")
                    self.msg("System",
                        f"🚀 Step failed {len(cur.failure_modes)} times — retrying with full context.",
                        chat=True)
            if not success and self._retries < max_r and used_api:
                self._retries += 1
                self.orch._retry_count = self._retries
                self._status_text.setText(f"🔄 Retry {self._retries}/{max_r}")
                # Track retry on current plan step
                if self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
                    self._plan_steps[self._plan_step_idx].add_retry(message[:150])
                    self._refresh_taskboard()
                fresh_obs = self.orch.capture_observation()
                ctx = self.orch.build_messages(self._pending_input,
                    mode="build",
                    retry_context=f"Previous code failed: {message}. Current scene: {fresh_obs}"
                )
                self._pending_msgs = ctx
                self._defer("retry", ctx, self._pending_input)
                return
            elif not success:
                # Sandbox import errors are permanent — never retry
                if "is not available in the AI sandbox" in message:
                    self.msg("System", f"⛔ Sandbox block: {message[:150]}", chat=True)
                    self.msg("Error", "Code used a module not in the AI sandbox. Try a different approach or report this as a missing module.", chat=True)
                    self._session_metrics["attempts_per_step"].append(self._retries + 1)
                    self._session_metrics["retries_per_step"].append(self._retries)
                    self._session_metrics["step_outcomes"].append("failed")
                    self._finish()
                    return
                # Plan backtracking: restore checkpoint and ask AI for a different approach
                ck_path = getattr(self.orch, '_last_checkpoint', None)
                in_plan = bool(self._plan_steps) and self._plan_step_idx > 0 and self._plan_step_idx < len(self._plan_steps)
                if in_plan and ck_path and os.path.exists(ck_path):
                    try:
                        FreeCAD.open(ck_path)
                        # Keep old document open — user may want to inspect the failed state.
                        # Checkpoint doc becomes active for continued work.
                        # Do NOT closeDocument(old_name) — that would destroy user's work.
                        self._plan_step_idx -= 1
                        self._session_metrics["backtrack_count"] += 1
                        self._retries = 0
                        # DAG rollback: cascade to downstream ops
                        self.orch.cad_dag.rollback_to(f"step_{self._plan_step_idx}")
                        self._replan_per_step = False
                        # Filter is defensive — in normal build, _completed_steps is empty here
                        # (finished steps stay in _plan_steps). No-op in current paths.
                        # Don't remove without auditing all call sites.
                        self._completed_steps = [s for s in self._completed_steps if s.state != StepState.PENDING]
                        self._step_retry_state = None
                        step_num = self._plan_step_idx + 1
                        bt_max = self._retries_per_step if hasattr(self, '_retries_per_step') and self._retries_per_step else (_provider_max_retries(self.orch.provider) if self.orch else MAX_RETRIES)
                        self.msg("System",
                            f"🔄 Step {step_num} failed after {bt_max} attempts. "
                            f"Rolled back to pre-step state. Proposing alternative approach.",
                            chat=True
                        )
                        fresh_obs = self.orch.capture_observation()
                        ctx = self.orch.build_messages(self._pending_input,
                            mode="build",
                            retry_context=(
                                f"Step {step_num} failed: {message}. "
                                "Your approach did not work. Propose a FUNDAMENTALLY DIFFERENT approach "
                                f"for step {step_num} that avoids this failure. "
                                f"Do NOT retry the same approach. Current scene: {fresh_obs}"
                            )
                        )
                        self._pending_msgs = ctx
                        self._defer("retry", ctx, self._pending_input)
                        return
                    except Exception as ex:
                        self.msg("Error", f"Backtrack restore failed: {ex}, falling back to hard failure.")
                bt_used = self._retries_per_step if hasattr(self, '_retries_per_step') and self._retries_per_step else (_provider_max_retries(self.orch.provider) if self.orch else MAX_RETRIES)
                self.msg("Error", f"❌ Step failed after {bt_used} attempts" + (f" — {message[:120]}" if message else ""), chat=True)
                if self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
                    self._plan_steps[self._plan_step_idx].finish(False, summary=message[:100])
                    self._plan_steps[self._plan_step_idx].code = combined_code
                    self._plan_steps[self._plan_step_idx].touched_labels = self._compute_touched_labels()
                    self._refresh_taskboard()
                self._session_metrics["attempts_per_step"].append(self._retries + 1)
                self._session_metrics["retries_per_step"].append(self._retries)
                self._session_metrics["step_outcomes"].append("failed")
                self.orch.record_result(self._pending_input, combined_code, False, message, self._retries)
                if hasattr(FreeCADGui, '_telemetry') and FreeCADGui._telemetry:
                    FreeCADGui._telemetry.record_ai_script(self._pending_input, combined_code, False, message)
                self._update_scene_fingerprint()
                self._finish()
                return
            if hasattr(FreeCADGui, '_telemetry') and FreeCADGui._telemetry:
                FreeCADGui._telemetry.record_ai_script(self._pending_input, combined_code, True, message)
            self._plan_step_idx += 1
            self._session_metrics["attempts_per_step"].append(self._retries + 1)
            self._session_metrics["retries_per_step"].append(self._retries)
            self._session_metrics["step_outcomes"].append("success")
            self._retries = 0
            # Assert BEFORE the RUNNING -> DONE transition for the just-finished
            # step so we catch any pre-existing violation before this transition.
            self._assert_step_invariant()
            if self._plan_steps and self._plan_step_idx > 0:
                prev = self._plan_steps[self._plan_step_idx - 1]
                prev.finish(True, summary=message[:100])
                prev.code = combined_code
                # Populate touched_labels from the fingerprint diff
                prev.touched_labels = self._compute_touched_labels()
                # Highlight affected objects in the 3D viewport
                self._highlight_step_objects(prev.touched_labels)
                # DAG: mark completed step as validated
                prev_idx = self._plan_step_idx - 1
                self.orch.cad_dag.mark_validated(f"step_{prev_idx}")
                self.orch.cad_dag.mark_executed(f"step_{prev_idx}")

            # Success — observe and decide next action
            obs = self.orch.capture_observation()
            step_label = f"Step {self._plan_step_idx}" if self._plan_steps else ""
            obs_short = (obs or "")[:180]
            if obs and len(obs) > 180:
                obs_short += "…"
            # Show completion with step title for clear visibility
            step_title = ""
            if self._plan_steps and self._plan_step_idx > 0:
                step_title = self._plan_steps[self._plan_step_idx - 1].title
            completion_prefix = f"✅ {step_label} complete" + (f" — {step_title}" if step_title else "")
            self.msg("Result", f"{completion_prefix}\n{message or 'OK'}\n{obs_short}".strip())
            # Full scene dump in the thinking panel for reference
            if obs and len(obs) > 200:
                self._thinking_header.setText("📐 Scene details")
                self._thinking_header.setVisible(True)
                self._thinking.setVisible(True)
                self._thinking.setHtml(f'<div style="color:#8aa9d0;font-size:10px;line-height:1.4;">{_html.escape(obs[:1200])}</div>')
            if self._plan_steps and self._plan_step_idx > 0:
                p = self._plan_steps[self._plan_step_idx - 1]
                entry_label = f"Step {self._plan_step_idx}: {p.title}"
            elif self._plan_steps:
                entry_label = f"Step {self._plan_step_idx + 1}"
            else:
                entry_label = "Generated Code"
            if hasattr(self, 'tree') and self.tree:
                self.tree.refresh()
            self._refresh_taskboard()
            self._update_scene_fingerprint()

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
                        new_steps = self.orch.extract_plan(replan_text, min_steps=1)
                        if new_steps and len(new_steps) >= 1:
                            self._plan_steps = self._plan_steps[:self._plan_step_idx] + [TaskStep(s) for s in new_steps]
                            self._refresh_taskboard()
                            plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(new_steps))
                            self.msg("Plan", f"Revised for remaining steps:\n{plan_text}")
                        else:
                            self.msg("Plan", f"Revised: {replan_text[:200]}")

            if self._plan_steps and self._plan_step_idx < len(self._plan_steps):
                # Goal-check: if newly-created geometry already satisfies the
                # request's explicit expected types, stop early instead of
                # running remaining (now-redundant) steps. since_baseline keeps
                # this mid-sequence-safe against pre-existing geometry.
                if self._task_appears_complete(since_baseline=True, require_explicit_expected=True):
                    self.msg("System", "✅ Goal already satisfied — stopping plan early.", chat=True)
                    obs_text = obs or ""
                    result = f"Done! {message}" + (f"\n\n{obs_text}" if obs_text else "")
                    self.msg("Result", result)
                    self._finish()
                else:
                    next_num = self._plan_step_idx + 1
                    next_title = ""
                    if self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
                        next_title = self._plan_steps[self._plan_step_idx].title
                    preamble = f"▶️  Next: Step {next_num}/{len(self._plan_steps) or '?'}"
                    if next_title:
                        preamble += f" — {next_title}"
                    self.msg("System", preamble, chat=True)
                    self._defer("next_step", obs)
            else:
                obs_text = obs or ""
                result = f"Done! {message}" + (f"\n\n{obs_text}" if obs_text else "")
                self.msg("Result", result)
                self._finish()
        except Exception as ex:
            self.msg("Error", f"Error processing AI response: {ex}")
            self._finish()

    def _request_next_step(self, observation_prelim):
        """Ask the AI to generate code for the next plan step. Re-reads document fresh."""
        if self._closed:
            return False
        self._require_orch()
        # Assert BEFORE the PENDING -> RUNNING transition so we catch any
        # pre-existing violation before this transition makes it worse.
        self._assert_step_invariant()
        # Mark the current step as running
        if 0 <= self._plan_step_idx < len(self._plan_steps):
            self._plan_steps[self._plan_step_idx].start()
            self._plan_steps[self._plan_step_idx].touched_labels = []
            # Update DAG: mark the current op as executed
            self.orch.cad_dag.mark_executed(f"step_{self._plan_step_idx}")
            self._refresh_taskboard()
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
        # Announce step start in chat for clear visibility
        if self._plan_steps and 0 <= step_idx < len(self._plan_steps):
            step_title = self._plan_steps[step_idx].title
            self.msg("System", f"▶️  Starting step {step_idx+1}: {step_title}", chat=True)
        return self._launch_worker(msgs, self._pending_input)

    def _on_mode_changed(self, new_mode):
        """Handle mode switch — preserve plan state across the transition."""
        if not self._ready:
            self._mode = new_mode
            return
        self._require_orch()
        if self._code_worker is not None or self._is_worker_thread_running():
            self._on_stop_step()
        self._mode = new_mode
        self.msg("System", f"Mode: **{new_mode}**", chat=True)
        if new_mode == "pcb":
            self._inp_container.setVisible(False)
            self._pcb_widget.setVisible(True)
            self._dxf_widget.setVisible(False)
            self._mascot.setVisible(False)
        elif new_mode == "dxf":
            self._inp_container.setVisible(False)
            self._pcb_widget.setVisible(False)
            self._dxf_widget.setVisible(True)
            self._mascot.setVisible(False)
        else:
            self._pcb_widget.setVisible(False)
            self._dxf_widget.setVisible(False)
            self._inp_container.setVisible(True)
            self._mascot.setVisible(True)
        if self._plan_paused and self._plan_steps:
            if new_mode == "build":
                self.msg("System",
                    f"Plan paused at step {self._plan_step_idx+1}/{len(self._plan_steps)} — "
                    f"send any message to resume.",
                    chat=True
                )
            else:
                self.msg("System",
                    f"⏸️ Plan paused at step {self._plan_step_idx+1}/{len(self._plan_steps)} — "
                    f"switch back to **Build** mode to resume.",
                    chat=True
                )

    def _on_pcb_generate(self, params):
        """Handle PCB enclosure generation via AI config + template."""
        self._require_orch()
        if not self.orch._board_context:
            self.msg("System", "No board loaded. Drop a .kicad_pcb file first.", chat=True)
            return

        board_data = self.orch._board_context

        if params.get("refinement"):
            success, message = self.orch.refine_enclosure_from_text(params["refinement"])
            self.msg("System", f"\U0001f527 {message}", chat=True)
            return

        # ── Vision chain (background thread to keep UI responsive) ──────────
        vision_description = None
        pcb_path = getattr(self._pcb_widget, "_board_path", None)
        api_key = getattr(self, "api_key", None) or ""
        model = getattr(self, "c_model", "") or ""

        from pcb_vision_deps import get_vision_deps_status, get_vision_deps_message, VisionDeps
        status = get_vision_deps_status(api_key=api_key, model=model)
        if status != VisionDeps.OK:
            msg = get_vision_deps_message(status)
            self.msg("System", msg, chat=True)
        else:
            self.msg("System", "\U0001f4f7 Analysing PCB render with vision AI\u2026", chat=True)
            try:
                from threading import Thread
                _result = [None]
                _exc_info = [None]
                def _run_vision():
                    try:
                        from kicad_renderer import render_pcb_png
                        from vision_pipeline import analyse_pcb_image
                        png_path = render_pcb_png(pcb_path)
                        FreeCAD.Console.PrintMessage(f"[vision] PNG rendered: {png_path}\n")
                        _result[0] = analyse_pcb_image(png_path, api_key=api_key)
                        FreeCAD.Console.PrintMessage(f"[vision] Analysis ({len(_result[0])} chars)\n")
                    except Exception as e:
                        _exc_info[0] = e
                t = Thread(target=_run_vision, daemon=True)
                t.start()
                while t.is_alive():
                    QtWidgets.QApplication.processEvents()
                    t.join(timeout=0.05)
                if _exc_info[0] is not None:
                    raise _exc_info[0]
                vision_description = _result[0]
            except RuntimeError as e:
                self.msg("System", f"\u26a0\ufe0f Vision failed: {e} — continuing without vision.", chat=True)
            except Exception as e:
                self.msg("System", f"\u26a0\ufe0f Vision error: {e} — continuing without vision.", chat=True)
        # ────────────────────────────────────────────────────────────────────

        from context_injector import build_ai_context
        wall_t = params.get("wall_thickness", 2.5)
        margin = params.get("margin", 2.0)
        headroom = params.get("headroom_mm", 2.0)
        lid_t = params.get("lid_thickness", 2.0)

        sys_prompt, board_block = build_ai_context(
            board_data,
            wall_t=wall_t,
            floor_t=2.0,
            margin=margin,
            headroom_mm=headroom,
            lid_t=lid_t,
            vision_description=vision_description,
        )

        config_prompt = (
            f"{sys_prompt}\n\n"
            f"{board_block}\n\n"
            f"Based on the board context above, output exactly one markdown JSON block "
            f"with these keys (no other text):\n\n"
            f"- wall_thickness: float (2.0\u20133.0)\n"
            f"- floor_thickness: float (1.5\u20132.5)\n"
            f"- margin: float (1.0\u20133.0)\n"
            f"- headroom_mm: float (1.0\u20135.0)\n"
            f"- lid_thickness: float (1.0\u20132.0)\n"
            f"- boss_od: float (4.0\u20138.0)\n"
            f"- snap_fit_count: int, even >= 2 (typical: 4)\n"
            f"- ventilation: bool\n"
            f"- ventilation_slots_count: int (used only if ventilation=true)\n"
            f"- custom_cutouts: list of dict (optional, see system prompt for format)\n\n"
            f"The system will automatically detect connector types from the PCB footprints "
            f"and use the correct panel cutout dimensions (USB_A=8.5\u00d75.0mm, USB_C=9.0\u00d73.5mm, "
            f"HDMI=15.5\u00d76.5mm, RJ45=16.0\u00d713.5mm, etc.)."
        )
        msgs = self.orch.build_messages(config_prompt, mode="pcb")
        self._pending_input = config_prompt
        self._launch_worker(msgs, config_prompt)

    def _try_parse_json_config(self, text):
        """Try to parse AI response as a JSON config dict. Returns None on failure."""
        import json, re
        blocks = self.orch.extract_json_blocks(text) if hasattr(self.orch, 'extract_json_blocks') else []
        for b in blocks:
            try:
                return json.loads(b)
            except json.JSONDecodeError:
                continue
        if not blocks:
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
            m = re.search(r'\{[^{}]*"boss_indices"[^{}]*\}', text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        return None

    def _on_dxf_generate(self, params):
        """Handle DXF generation request from the DXF widget."""
        self._require_orch()
        if not self.orch._dxf_context:
            self.msg("System", "No DXF data loaded. Drop a .dxf file first.")
            return
        prompt = params.get("prompt", "")
        if not prompt:
            self.msg("System", "Enter a description of what to build from the DXF profiles.")
            return
        self._dxf_widget._status.setText("Generating...")
        self._mode = "dxf"
        full_prompt = f"DXF profiles loaded. User request: {prompt}"
        self._pending_msgs = self.orch.build_messages(full_prompt, mode="dxf")
        self._pending_input = full_prompt
        self._launch_worker(self._pending_msgs, full_prompt)

    def _on_undo(self):
        """Roll back the last AI action — checkpoint restore, then doc.undo() fallback."""
        try:
            ck_path = getattr(self.orch, '_last_checkpoint', None)
            if ck_path and os.path.exists(ck_path):
                FreeCAD.open(ck_path)
                self.msg("System", f"↩ Restored checkpoint: {os.path.basename(ck_path)}", chat=True)
            else:
                doc = FreeCAD.ActiveDocument
                if doc:
                    doc.undo()
                    doc.recompute()
                    self.msg("System", "↩ Undo: last action reverted via doc.undo()", chat=True)
                else:
                    self.msg("System", "↩ No active document to undo.", chat=True)
            if hasattr(self, 'tree') and self.tree:
                self.tree.refresh()
        except Exception as e:
            self.msg("Error", f"↩ Undo failed: {e}", chat=True)

    def _on_stop_step(self):
        """Stop the current step but keep the plan paused & resumable."""
        self.stop()
        if self._plan_steps and self._plan_step_idx < len(self._plan_steps):
            self._plan_paused = True
            self.msg("System",
                f"⏸️ Step {self._plan_step_idx+1}/{len(self._plan_steps)} stopped. "
                f"Send any message to resume.",
                chat=True
            )
        else:
            self.msg("System", "⏸️ Operation stopped.", chat=True)
    
    def _on_stream(self, text, typ):
        """Handle streamed tokens from the AI during generation."""
        if typ == "done" or not text or self._closed:
            return
        if typ == "error":
            self._thinking.append(f"\n⚠️ Error: {text}")
            return
        # During plan execution, suppress raw code content — show only one-line step status
        # Do NOT call _refresh_taskboard here — it destroys/recreates widgets on every token
        if typ == "content" and self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
            self._status_text.setText(f"⚡ Generating step {self._plan_step_idx+1}/{len(self._plan_steps)}...")
            return
        safe = _html.escape(text)
        color = "#374766" if typ == "reasoning" else "#6b7fa3"
        self._thinking.insertHtml(f'<span style="color:{color}">{safe}</span>')
        scroll = self._thinking.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def _should_force_safe_fallback(self, message, user_input):
        text = f"{user_input or ''} {message or ''}".lower()
        request_hits = any(k in text for k in (
            "patterned block", "patterned square block", "square block", "pattern block",
             "enclosure", "pcb", "snap fit", "snap-fit", "gridfinity", "grid"
        ))
        error_hits = any(k in text for k in (
            "sketch constraint", "empty sketch", "no geometry", "support",
            "partgui", "partdesigngui", "partgui is not available", "index out of range",
            "takes 3 arg", "takes 5 arg", "created nothing and modified nothing",
            "didn't create anything", "invalid sketch", "missing geometry",
            "attributeerror", "runtimeerror", "nameerror", "typeerror",
            "output validation"
        ))
        return request_hits and error_hits

    def _on_worker_err(self, e, gen=0):
        if gen != 0 and gen != self._worker_gen:
            return
        if self._closed:
            return
        self.msg("Error", f"Worker error: {e}", chat=True)
        self._finish()

    def _finish(self, keep_plan=False):
        self._hide_viewport_overlay()
        self._deferred = None
        if self._session_metrics["attempts_per_step"]:
            ok = sum(1 for o in self._session_metrics["step_outcomes"] if o == "success")
            fail = sum(1 for o in self._session_metrics["step_outcomes"] if o == "failed")
            fc = dict(sorted(self._session_metrics["failure_categories"].items(), key=lambda x: -x[1]))
            print(f"[AIC] Session: {ok}/{ok+fail} steps | "
                  f"{sum(self._session_metrics['attempts_per_step'])} attempts | "
                  f"{sum(self._session_metrics['retries_per_step'])} retries | "

                  f"{self._session_metrics['backtrack_count']} backtracks | "
                  f"failures: {fc}")
        if not self._closed:
            self.spin.setVisible(False)
            self._thinking_header.setVisible(False)
            self._thinking.setVisible(False)
            self._thinking.clear()
            self._set_dot("#3fb950")
            self._status_text.setText("Ready"); self._status_text.setStyleSheet("color:#8a9099;font-size:10px;font-weight:500;letter-spacing:0.5px;")
        self._worker_thread = None
        self._code_worker = None
        self._cleanup_classify_worker()
        self._direct_execute = False
        self._retries = 0
        self._step_retry_state = None
        if not keep_plan:
            self._pending_input = ""
            self._pending_msgs = None
            self._plan_paused = False
            self._plan_steps = []
            self._plan_step_idx = 0
            self._stop_step_btn.setVisible(False)
            self._cancel_plan_btn.setVisible(False)
        if hasattr(self, 'tree') and self.tree:
            self.tree.refresh()
        self._refresh_taskboard()

    def _is_meta_step(self, text):
        """Detect steps that are prerequisites, not geometry-producing actions."""
        tl = text.lower().strip()
        meta_patterns = [
            "activate", "switch to", "switch to the", "select the", "select ",
            "set up the", "set up ", "create document", "open file", "save ",
            "delete the", "remove the", "clean up", "cleanup", "clear ",
            "navigate to", "go to", "open the"
        ]
        if any(tl.startswith(p) for p in meta_patterns):
            return True
        if any(tl == p for p in meta_patterns):
            return True
        return False

    def _handle_meta_step(self, text):
        """Execute a meta-step silently — workbench activation, cleanup, etc."""
        tl = text.lower()
        try:
            if "partdesign" in tl or "part design" in tl:
                FreeCADGui.activateWorkbench("PartDesignWorkbench")
                self.msg("System", "⚙️ Auto: activated PartDesign workbench", chat=True)
            elif "sketcher" in tl:
                FreeCADGui.activateWorkbench("SketcherWorkbench")
                self.msg("System", "⚙️ Auto: activated Sketcher workbench", chat=True)
            elif "part" in tl and "workbench" in tl:
                FreeCADGui.activateWorkbench("PartWorkbench")
                self.msg("System", "⚙️ Auto: activated Part workbench", chat=True)
            elif any(w in tl for w in ("delete", "remove", "clean", "clear")):
                self.msg("System", "⚠️ Skipping cleanup step — undo manually if needed.", chat=True)
            else:
                self.msg("System", f"⚙️ Auto: skipped meta-step '{text[:60]}'", chat=True)
        except Exception as e:
            self.msg("System", f"⚠️ Meta-step failed: {e}", chat=True)

    def _refresh_taskboard(self):
        """Rebuild the plan step list with rich state colors, collapsible code, and result tags."""
        # Preserve scene fingerprint label — remove and re-add after rebuild
        fingerprint_visible = self._scene_fingerprint.isVisible()
        fp_text = self._scene_fingerprint.text()
        while self._tb_layout.count():
            item = self._tb_layout.takeAt(0)
            w = item.widget() if item else None
            if w and w is not self._scene_fingerprint:
                w.deleteLater()
        if not self._plan_steps:
            self._tb_layout.insertWidget(0, self._scene_fingerprint)
            self._scene_fingerprint.setVisible(fingerprint_visible)
            if fingerprint_visible and fp_text:
                self._scene_fingerprint.setText(fp_text)
            self._taskboard_container.setVisible(False)
            return
        self._taskboard_container.setVisible(True)
        self._step_widgets = {}
        # DAG status line
        dag = self.orch.cad_dag
        if dag and dag.ops:
            done = sum(1 for o in dag.ops.values() if o.executed)
            total = len(dag.ops)
            dag_label = QtWidgets.QLabel(f"<span style='color:#5a7a9a;font-size:10px;'>DAG: {done}/{total} committed</span>")
            dag_label.setContentsMargins(4, 2, 4, 2)
            self._tb_layout.addWidget(dag_label)
        for i, step in enumerate(self._plan_steps):
            is_current = (i == self._plan_step_idx and step.state in (StepState.PENDING, StepState.RUNNING))
            is_done = step.state == StepState.DONE
            is_failed = step.state == StepState.FAILED
            is_running = step.state == StepState.RUNNING

            # ── Color scheme (glass theme) ────────────────────
            bg_color = "rgba(8,18,44,0.75)"
            border_color = "rgba(255,255,255,0.07)"
            if is_running:
                bg_color = "rgba(0,240,255,0.10)"
                border_color = "#00f0ff"
            elif is_done:
                bg_color = "rgba(192,132,252,0.10)"
                border_color = "#c084fc"
            elif is_failed:
                bg_color = "rgba(255,45,120,0.10)"
                border_color = "#ff2d78"
            elif is_current:
                bg_color = "rgba(0,240,255,0.06)"
                border_color = "#00f0ff"

            step_icon = step.state.icon
            if is_running:
                step_icon = "⏳"
            elif is_done:
                step_icon = "✅"
            elif is_failed:
                step_icon = "❌"
            elif step.state == StepState.CANCELLED:
                step_icon = "⊘"

            title_color = "#eef2ff" if is_current or is_running else "#6b7fa3"
            if is_done:
                title_color = "#c084fc"
            elif is_failed:
                title_color = "#ff2d78"

            # ── Row container ──────────────────────────────────
            row = QtWidgets.QWidget()
            row.setStyleSheet(f"background:{bg_color};border:1px solid {border_color};border-radius:8px;")
            rl = QtWidgets.QVBoxLayout(row)
            rl.setContentsMargins(12, 8, 12, 8)
            rl.setSpacing(4)

            # Header line: icon + title + state badge + duration
            hdr = QtWidgets.QWidget()
            hdr.setStyleSheet("border:none;background:transparent;")
            hl = QtWidgets.QHBoxLayout(hdr)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(6)

            icon_lbl = QtWidgets.QLabel(step_icon)
            icon_lbl.setFixedWidth(20)
            icon_lbl.setStyleSheet("border:none;background:transparent;font-size:12px;")
            hl.addWidget(icon_lbl)

            title_text = step.title[:60]
            title_lbl = QtWidgets.QLabel(f"<span style='color:{title_color};font-weight:600;font-size:11px;'>{i+1}. {title_text}</span>")
            title_lbl.setStyleSheet("border:none;background:transparent;")
            hl.addWidget(title_lbl)
            hl.addStretch()

            if step.state != StepState.PENDING:
                state_colors = {"running":"#00f0ff","done":"#c084fc","failed":"#ff2d78","cancelled":"#374766"}
                sc = state_colors.get(step.state.value, "#5a7a9a")
                badge_text = step.state.label
                if step.state == StepState.DONE and step.started_at and step.finished_at:
                    dur = step.finished_at - step.started_at
                    badge_text = f"✓ {dur:.1f}s"
                elif step.state == StepState.RUNNING:
                    badge_text = "● Running"
                st = QtWidgets.QLabel(f"<span style='color:{sc};font-size:9px;font-weight:600;'>{badge_text}</span>")
                st.setStyleSheet("border:none;background:transparent;")
                hl.addWidget(st)

            rl.addWidget(hdr)

            # ── Summary / result tag line ──────────────────────
            if step.summary or step.state == StepState.DONE or step.state == StepState.FAILED:
                summ = step.summary[:80] if step.summary else ("OK" if step.state == StepState.DONE else "Failed")
                result_color = "#c084fc" if step.state == StepState.DONE else "#ff2d78"
                summ_lbl = QtWidgets.QLabel(f"<span style='color:{result_color};font-size:9px;'>{summ}</span>")
                summ_lbl.setStyleSheet("border:none;background:transparent;")
                summ_lbl.setWordWrap(True)
                rl.addWidget(summ_lbl)

            self._tb_layout.addWidget(row)
            self._step_widgets[i] = {
                "row": row,
                "icon_lbl": icon_lbl, "title_lbl": title_lbl,
            }

        # ── Re-add scene fingerprint strip at top ─────────────
        self._scene_fingerprint.setParent(self._taskboard)
        self._tb_layout.insertWidget(0, self._scene_fingerprint)
        self._scene_fingerprint.setVisible(fingerprint_visible)
        if fingerprint_visible and fp_text:
            self._scene_fingerprint.setText(fp_text)

    def _update_scene_fingerprint(self):
        """Update the scene fingerprint label with current document object info."""
        try:
            doc = FreeCAD.ActiveDocument
            if not doc:
                self._scene_fingerprint.setVisible(False)
                return
            objs = doc.Objects
            counts = {}
            for o in objs:
                # TypeId can be missing or non-string on partially-initialized objects
                try:
                    tid = o.TypeId.split("::")[-1] if o.TypeId else "?"
                except Exception:
                    tid = "?"
                counts[tid] = counts.get(tid, 0) + 1
            count_str = ", ".join(f"{n}×{k}" for k, n in sorted(counts.items()))
            if count_str:
                self._scene_fingerprint.setText(f"📐 Scene: {len(objs)} objects — {count_str}")
                self._scene_fingerprint.setVisible(True)
            else:
                self._scene_fingerprint.setVisible(False)
        except Exception:
            self._scene_fingerprint.setVisible(False)

    # ── ΔS: Semantic clarification UI ──────────────────────────

    def _request_semantic_clarification(self, delta_c, topo_results):
        """When ΔC is ambiguous (exact+tol pass, derived/semantic fail),
        pause the plan and ask the user for clarification."""
        if not self._plan_steps:
            return False
        if self._plan_paused:
            return False
        if delta_c.strong_pass or not delta_c.weak_pass:
            return False
        issues = []
        if not delta_c.derived_pass:
            issues.append("derived constraints (symmetry, clearance) may be off")
        if not delta_c.semantic_pass:
            issues.append("semantic ambiguity detected")
        if topo_results:
            bad = [n for n, t in topo_results.items() if t and not t.min_pass]
            if bad:
                issues.append(f"topology warnings on: {', '.join(bad[:3])}")
        if not issues:
            return False
        self.msg("System",
            f"🔍 ΔS clarification needed: {'; '.join(issues)}.\n"
            "Options: **continue** to proceed, **revise** to change plan, "
            "**stop** to abort.",
            chat=True)
        self._plan_paused = True
        return True

    def _check_semantic_resume(self, text: str) -> bool:
        """Check if the user responded to a ΔS clarification."""
        if not self._plan_paused:
            return False
        tl = text.lower().strip()
        if tl in ("continue", "proceed", "go ahead", "yes"):
            self._plan_paused = False
            return True
        if tl in ("revise", "modify", "change"):
            self._plan_paused = False
            # Signal to caller that revision is needed
            return True
        return False

    def _compute_touched_labels(self):
        """Convert _touched_objects UIDs to human-readable labels for display and selection."""
        labels = []
        for uid in getattr(self.orch, '_touched_objects', set()):
            try:
                parts = uid.split(".", 1)
                doc_name = parts[0] if len(parts) > 1 else None
                obj_name = parts[-1]
                doc = FreeCAD.listDocuments().get(doc_name) if doc_name else FreeCAD.ActiveDocument
                if doc:
                    obj = doc.getObject(obj_name)
                    if obj:
                        labels.append(obj.Label or obj.Name)
            except Exception:
                continue
        return labels

    def _assert_step_invariant(self):
        """Debug helper: no TaskStep should appear in both _plan_steps and _completed_steps.
        A step lives in _plan_steps while active, moves to _completed_steps when done.
        On violation, log detailed info (step titles, list sizes) and defensively
        remove the overlapping step from _plan_steps to break any further state
        corruption. The fix is opportunistic — the warning identifies the problem,
        the cleanup prevents downstream invariant cascades.
        Gate behind a debug flag in production; left unconditional for now to catch regressions early."""
        active_ids = {id(s): s for s in self._plan_steps}
        completed_ids = {id(s): s for s in self._completed_steps}
        overlap_ids = set(active_ids) & set(completed_ids)
        if overlap_ids:
            overlap_titles = [active_ids[oid].title[:50] for oid in overlap_ids]
            FreeCAD.Console.PrintWarning(
                f"[AICompanion] Step invariant violated: {len(overlap_ids)} step(s) "
                f"appear in both _plan_steps (n={len(self._plan_steps)}) and "
                f"_completed_steps (n={len(self._completed_steps)}). "
                f"Titles: {overlap_titles}\n"
            )
            # Defensive cleanup: remove the overlapping step from _plan_steps so
            # future assertions pass and downstream code doesn't act on stale state.
            # The step stays in _completed_steps where it belongs post-finish().
            self._plan_steps = [s for s in self._plan_steps if id(s) not in overlap_ids]

    def _record_step_failure(self, message):
        """Classify and record a failure mode on the current plan step."""
        if self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
            mode = classify_failure(message)
            self._plan_steps[self._plan_step_idx].record_failure(mode)
            self._session_metrics["failure_categories"][mode] = self._session_metrics["failure_categories"].get(mode, 0) + 1

    def _capture_doc_names(self):
        """Snapshot of (Name, TypeId) tuples in the active document.
        Returns empty set on no active doc or any per-object failure."""
        snap = set()
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return snap
        for o in doc.Objects:
            try:
                snap.add((o.Name, getattr(o, "TypeId", "") or ""))
            except Exception:
                continue
        return snap

    def _step_scope_warning(self, pre_snap, post_snap, step_text):
        """Detect runaway object creation within a single step and halt the plan.

        Counts only significant geometry objects — the Origin/datum scaffolding
        FreeCAD auto-creates with a Body is excluded, so legitimate Body creation
        (which spawns ~9 helper objects) is not falsely flagged. Returns True if
        the plan should HALT (more than one object beyond what the step implied),
        otherwise False.
        """
        IGNORED_PREFIXES = (
            "App::Origin", "App::Plane", "App::Line", "App::Point",
            "App::DocumentObjectGroup", "App::Part", "App::Link",
        )
        significant = 0
        for entry in (post_snap - pre_snap):
            tid = entry[1] if isinstance(entry, tuple) and len(entry) > 1 else ""
            if not tid or any(tid.startswith(p) for p in IGNORED_PREFIXES):
                continue
            significant += 1
        verb_count = len([
            w for w in (step_text or "").lower().split()
            if w in ("create", "add", "make", "draw", "build", "sketch", "pad", "pocket")
        ])
        expected_new = max(1, verb_count)
        if significant > expected_new + 5:
            self.msg("System",
                f"[StepGuard] Step created {significant} geometry objects, "
                f"expected ~{expected_new} — halting plan to prevent runaway duplication.",
                chat=True
            )
            return True
        return False

    def _count_objects_by_type(self, only_new=False):
        """Returns dict of TypeId -> count for active document objects.
        Used by _task_appears_complete to detect duplication.
        When only_new is True, counts only objects created since the current
        request's baseline (see _capture_run_baseline) so pre-existing geometry
        in a stale scene is ignored.
        """
        counts = {}
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return counts
        baseline = self._run_baseline_names if only_new else None
        for o in doc.Objects:
            try:
                if baseline is not None:
                    key = (o.Name, getattr(o, "TypeId", "") or "")
                    if key in baseline:
                        continue
                tid = getattr(o, "TypeId", "") or ""
                counts[tid] = counts.get(tid, 0) + 1
            except Exception:
                continue
        return counts

    def _infer_expected_types(self, user_request):
        """Map user request keywords to expected FreeCAD feature TypeIds.
        Returns a list of expected TypeId strings. Used by _task_appears_complete
        to determine if the scene has the right kind of objects.
        """
        text = (user_request or "").lower()
        expected = []
        if any(kw in text for kw in ("box", "block", "cube", "rectangular", "pad", "extrude", "square")):
            expected.append("PartDesign::Pad")
        if any(kw in text for kw in ("cylinder", "round", "bore", "shaft")):
            expected.append("PartDesign::AdditiveCylinder")
        if any(kw in text for kw in ("pocket", "cut", "subtract", "remove", "groove")):
            expected.append("PartDesign::Pocket")
        if any(kw in text for kw in ("fillet", "round edges", "edge fillet")):
            expected.append("PartDesign::Fillet")
        if any(kw in text for kw in ("chamfer",)):
            expected.append("PartDesign::Chamfer")
        if any(kw in text for kw in ("hole", "drill")):
            expected.append("PartDesign::Hole")
        return expected

    def _task_appears_complete(self, since_baseline=False, require_explicit_expected=False):
        """Scene-based completion check. Returns True if the user's task
        appears to be done based on the current document state. Returns
        False if the scene is empty, has duplication (multiple Bodies,
        too many Pads/Pockets), or is missing expected features.

        since_baseline: count only objects created during the current request
        (ignores pre-existing geometry, so a stale scene cannot trigger a
        false positive mid-sequence).
        require_explicit_expected: when True, return False if the request did
        not map to explicit expected types — avoids halting a plan early on a
        vague "any PartDesign object" heuristic.
        """
        type_counts = self._count_objects_by_type(only_new=since_baseline)
        if not type_counts:
            return False

        body_count = type_counts.get("PartDesign::Body", 0)
        if body_count > 1:
            self.msg("System",
                f"[Chief] Multiple Bodies detected ({body_count}) — refusing to claim complete",
                chat=True
            )
            return False

        for tid in ("PartDesign::Pad", "PartDesign::Pocket", "PartDesign::Fillet", "PartDesign::Chamfer"):
            if type_counts.get(tid, 0) > 2:
                self.msg("System",
                    f"[Chief] {type_counts.get(tid)}×{tid} detected — possible duplication",
                    chat=True
                )
                return False

        expected = self._infer_expected_types(self._pending_input)
        if not expected:
            if require_explicit_expected:
                return False
            return any(t.startswith("PartDesign::") for t in type_counts)

        for et in expected:
            if et not in type_counts:
                return False

        return True

    def _highlight_step_objects(self, touched_labels):
        """Select objects in the FreeCAD 3D viewport and fit the view to them.
        Uses FreeCADGui.Selection (not document color changes) so highlights
        persist until the user clicks elsewhere — no timer needed, no document save risk."""
        try:
            if not touched_labels:
                return
            doc = FreeCAD.ActiveDocument
            if not doc:
                return
            FreeCADGui.Selection.clearSelection()
            for label in touched_labels:
                objs = doc.getObjectsByLabel(label)
                if objs:
                    FreeCADGui.Selection.addSelection(objs[0])
                else:
                    for o in doc.Objects:
                        if o.Name == label:
                            FreeCADGui.Selection.addSelection(o)
                            break
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception as ex:
            _report_gui_error("highlight_objects", ex)

    def _capture_viewport_b64(self):
        """Capture the active FreeCAD 3D viewport as a base64-encoded PNG.
        Returns None if the viewport is not visible or unavailable."""
        try:
            gdoc = FreeCADGui.ActiveDocument
            if not gdoc:
                return None
            view = gdoc.ActiveView
            if not view or not view.isVisible():
                return None
            import tempfile, base64
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)  # release fd before saveImage writes to the path
            try:
                view.saveImage(path, 800, 600, "PNG")
                with open(path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("ascii")
                return data
            finally:
                try:
                    os.unlink(path)
                except Exception:
                    pass
        except Exception as ex:
            _report_gui_error("capture_viewport", ex)
            return None

    def _embed_viewport_image(self, b64_data, label="After"):
        """Return an HTML img tag for a base64-encoded viewport image."""
        if not b64_data:
            return ""
        return (
            f'<div style="margin:6px 0;text-align:center;">'
            f'<div style="color:#8b949e;font-size:9px;margin-bottom:2px;">{label}</div>'
            f'<img src="data:image/png;base64,{b64_data}" '
            f'style="max-width:100%;border-radius:8px;border:1px solid #2a3648;" />'
            f'</div>'
        )

_dock_instance = None


def show_sidebar():
    global si, _dock_instance, _creating_dock
    if _creating_dock:
        return None

    # If dock instance exists, just show it (reliable guard against duplicates)
    if _dock_instance is not None:
        try:
            _dock_instance.setVisible(True)
            _dock_instance.raise_()
            si = _dock_instance.widget()
            sw = getattr(si, 'sidebar_widget', None)
        except Exception:
            _dock_instance = None
        else:
            return _dock_instance

    _creating_dock = True
    try:
        mw = FreeCADGui.getMainWindow()
        if not mw:
            return None

        # If dock already exists in widget hierarchy, just show it
        dock = mw.findChild(QtWidgets.QDockWidget, "AICompanionDock")
        if dock:
            dock.setVisible(True)
            dock.raise_()
            _dock_instance = dock
            return dock

        # First-time creation: wrap AISidebar in a QDockWidget
        sidebar = AISidebar()
        dock = QtWidgets.QDockWidget("AI Companion", mw)
        dock.setObjectName("AICompanionDock")
        dock.setWidget(sidebar)
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable |
            QtWidgets.QDockWidget.DockWidgetClosable
        )
        mw.addDockWidget(Qt.RightDockWidgetArea, dock)
        si = sidebar
        _dock_instance = dock
        dock.show()
        return dock
    finally:
        _creating_dock = False
