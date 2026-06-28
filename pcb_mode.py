import os
from compat import QtWidgets, Qt, Signal


class PcbInputWidget(QtWidgets.QWidget):
    generate_clicked = Signal(dict)

    def __init__(self, orch=None, parent=None):
        super().__init__(parent)
        self.orch = orch
        self._board_path = None
        self._board_data = None
        self._vision_model = ""
        self._vision_api_key = ""
        self._build_ui()

    def set_vision_info(self, model: str = "", api_key: str = ""):
        self._vision_model = model
        self._vision_api_key = api_key

    def set_orch(self, orch):
        self.orch = orch

    # Forward QStackedWidget interface to internal stack
    def setCurrentIndex(self, idx):
        self._stack.setCurrentIndex(idx)

    def currentIndex(self):
        return self._stack.currentIndex()

    def addWidget(self, w):
        return self._stack.addWidget(w)

    def widget(self, idx):
        return self._stack.widget(idx)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._stack = QtWidgets.QStackedWidget()
        self._drop_page = self._make_drop_page()
        self._summary_page = self._make_summary_page()
        self._chat_page = self._make_chat_page()
        self._stack.addWidget(self._drop_page)
        self._stack.addWidget(self._summary_page)
        self._stack.addWidget(self._chat_page)
        self._stack.setCurrentIndex(0)
        layout.addWidget(self._stack, 1)

        # Persistent input bar (visible on all pages)
        inp_row = QtWidgets.QHBoxLayout()
        inp_row.setContentsMargins(8, 0, 8, 0)
        self._pcb_input = QtWidgets.QLineEdit()
        self._pcb_input.setPlaceholderText("Refine enclosure... (e.g. 'move USB cutout up 2mm')")
        self._pcb_input.setStyleSheet("""
            QLineEdit {
                background: #121a2a; color: #e6edf3;
                border: 1.5px solid #3a414a; border-radius: 8px;
                padding: 8px 12px; font-size: 12px;
            }
            QLineEdit:focus { border-color: #58a6ff; }
        """)
        self._pcb_input.returnPressed.connect(self._send_refinement)
        inp_row.addWidget(self._pcb_input, 1)

        send_btn = QtWidgets.QPushButton("Send")
        send_btn.setStyleSheet("""
            QPushButton { background:#1f6feb; color:#fff; border:none;
                          border-radius:6px; padding:6px 12px; font-size:12px; font-weight:600; }
            QPushButton:hover { background:#388bfd; }
        """)
        send_btn.clicked.connect(self._send_refinement)
        inp_row.addWidget(send_btn)
        layout.addLayout(inp_row)

    # ── Drop Page ───────────────────────────────────────────

    def _make_drop_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(8)

        self._drop_zone = QtWidgets.QLabel()
        self._drop_zone.setAlignment(Qt.AlignCenter)
        self._drop_zone.setText(
            "<div style='font-size:14px; color:#8b949e;'>"
            "DROP .kicad_pcb FILE HERE<br>"
            "<span style='font-size:11px; color:#484f58;'>or click to browse</span>"
            "</div>"
        )
        self._drop_zone.setFixedHeight(120)
        self._drop_zone.setStyleSheet("""
            QLabel {
                background: #161b22;
                border: 2px dashed #30363d;
                border-radius: 12px;
                padding: 20px;
            }
            QLabel:hover {
                border-color: #58a6ff;
                background: #1c2128;
            }
        """)
        self._drop_zone.setCursor(Qt.PointingHandCursor)
        self._drop_zone.mousePressEvent = lambda e: self._browse_file()
        self._drop_zone.setAcceptDrops(True)
        self._drop_zone.dragEnterEvent = self._drag_enter
        self._drop_zone.dropEvent = self._drop_file
        layout.addWidget(self._drop_zone)

        layout.addStretch()
        return page

    def _drag_enter(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().endswith(".kicad_pcb"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _drop_file(self, event):
        for url in event.mimeData().urls():
            fp = url.toLocalFile()
            if fp.endswith(".kicad_pcb"):
                self._load_board(fp)
                break

    def _browse_file(self):
        fp, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select KiCad PCB File", "", "KiCad PCB (*.kicad_pcb)"
        )
        if fp:
            self._load_board(fp)

    def _load_board(self, fp):
        self._board_path = fp
        try:
            from pcb_parser import parse, validate_board_data
            self._board_data = parse(fp)
            _, parse_warnings = validate_board_data(self._board_data)
            if parse_warnings:
                for w in parse_warnings[:3]:
                    print(f"[PCB] Warning: {w}")
                if len(parse_warnings) > 3:
                    print(f"[PCB] ... and {len(parse_warnings) - 3} more warnings")
        except Exception as e:
            self._show_error(f"Failed to parse: {e}")
            return

        # Show parsed dimensions immediately so user knows if parsing worked.
        # The 100x60 check is a heuristic (real 100x60mm boards will false-trigger);
        # the robust fix is a used_fallback flag returned by the parser, not done here.
        dims = self._board_data.get("dimensions", {})
        w = dims.get("width", 0)
        h = dims.get("height", 0)
        holes = len(self._board_data.get("mounting_holes", []))
        connectors = len(self._board_data.get("edge_connectors", []))
        comps = len(self._board_data.get("components", []))

        print(f"[PCB] Board context set. Keys: {list(self._board_data.keys())}")
        print(f"[PCB]   dimensions: {dims}")
        print(f"[PCB]   width={w}, height={h}")
        if self.orch:
            self.orch._board_context = self._board_data
            print(f"[PCB] Stored board context type={type(self.orch._board_context).__name__}")

        # ── Status + import hint ──────────────────────────────────────────────
        if w == 100.0 and h == 60.0:
            self._status.setText(
                "\u26a0 No Edge.Cuts found \u2014 using 100\u00d760mm default. "
                "Check your KiCad file has a board outline."
            )
            self._status.setStyleSheet("color:#ff6b6b; font-size:11px;")
        else:
            self._status.setText(
                f"\u2713 {w}mm \u00d7 {h}mm  |  "
                f"{comps} components  |  "
                f"{holes} mounting holes  |  "
                f"{connectors} edge connectors"
            )
            self._status.setStyleSheet("color:#22c55e; font-size:11px;")

        self._drop_zone.setText(
            "<div style='font-size:11px; color:#8b949e; text-align:center;'>"
            "\u2713 PCB data loaded. "
            "Now use <b>File \u2192 Import \u2192 KiCad PCB</b> to see the 3D board."
            "</div>"
        )

        self._show_summary()

    def _show_error(self, msg):
        self._drop_zone.setText(
            f"<div style='font-size:12px; color:#f85149;'>"
            f"{msg}<br>"
            f"<span style='font-size:11px; color:#484f58;'>click to try again</span>"
            f"</div>"
        )

    # ── Summary Page ────────────────────────────────────────

    def _make_summary_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._summary_label = QtWidgets.QTextEdit()
        self._summary_label.setReadOnly(True)
        self._summary_label.setMaximumHeight(150)
        self._summary_label.setStyleSheet("""
            QTextEdit {
                background: #161b22; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 8px;
                font-size: 11px; padding: 8px;
                font-family: 'Consolas', monospace;
            }
        """)
        layout.addWidget(self._summary_label)

        # Parameter controls
        params = QtWidgets.QWidget()
        pl = QtWidgets.QGridLayout(params)
        pl.setSpacing(4)
        pl.setContentsMargins(0, 0, 0, 0)

        row = 0
        self._wall_t_spin = self._make_spin(1.0, 10.0, 2.5)
        pl.addWidget(QtWidgets.QLabel("Wall thickness:"), row, 0)
        pl.addWidget(self._wall_t_spin, row, 1)
        row += 1

        self._lid_clr_spin = self._make_spin(0.5, 10.0, 3.0)
        pl.addWidget(QtWidgets.QLabel("Lid clearance:"), row, 0)
        pl.addWidget(self._lid_clr_spin, row, 1)
        row += 1

        self._boss_od_spin = self._make_spin(3.0, 15.0, 6.0)
        pl.addWidget(QtWidgets.QLabel("Boss outer Ø:"), row, 0)
        pl.addWidget(self._boss_od_spin, row, 1)
        row += 1

        self._material_combo = QtWidgets.QComboBox()
        self._material_combo.addItems(["FDM", "SLA", "ABS", "PETG", "Nylon", "Polycarb"])
        self._material_combo.setStyleSheet("""
            QComboBox { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                        border-radius:6px; font-size:11px; padding:3px 6px; }
            QComboBox:hover { border-color:#58a6ff; }
        """)
        pl.addWidget(QtWidgets.QLabel("Material:"), row, 0)
        pl.addWidget(self._material_combo, row, 1)
        row += 1

        layout.addWidget(params)

        self._gen_btn = QtWidgets.QPushButton("Generate Enclosure")
        self._gen_btn.setToolTip(
            "AI analyzes the PCB and generates a custom enclosure with connector cutouts"
        )
        self._gen_btn.setStyleSheet("""
            QPushButton {
                background: #7c3aed; color: #fff; border: none;
                border-radius: 8px; padding: 10px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #8b5cf6; }
            QPushButton:pressed { background: #6d28d9; }
        """)
        self._gen_btn.clicked.connect(self._on_generate)

        layout.addWidget(self._gen_btn)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color:#8b949e; font-size:10px;")
        layout.addWidget(self._status)

        layout.addStretch()
        return page

    def _make_spin(self, min_v, max_v, default):
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(min_v, max_v)
        s.setValue(default)
        s.setSingleStep(0.5)
        s.setSuffix(" mm")
        s.setStyleSheet("""
            QDoubleSpinBox {
                background: #21262d; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 6px;
                font-size: 11px; padding: 3px 6px;
            }
            QDoubleSpinBox:focus { border-color: #58a6ff; }
        """)
        return s

    def _show_summary(self):
        bd = self._board_data
        if not bd:
            return
        dims = bd["dimensions"]
        holes = bd["mounting_holes"]
        connectors = bd["edge_connectors"]
        components = bd["components"]
        tallest = max((c["height"] for c in components), default=0) if components else 0

        # Suggest defaults from examples
        try:
            from examples.suggest_params import suggest_parameters
            params = suggest_parameters(bd)
            self._wall_t_spin.setValue(params["wall_thickness"])
            self._lid_clr_spin.setValue(params["lid_clearance"])
            if params.get("boss_od"):
                self._boss_od_spin.setValue(params["boss_od"])
        except Exception as ex:
            print(f"[AI] PcbInputWidget.load_board parameter suggestion failed: {ex}")

        # Hammond fit finder — instant, no AI
        hammond_fits = []
        try:
            from enclosure_templates_v2 import find_hammond_for_board
            hammond_fits = find_hammond_for_board(
                dims["width"], dims["height"], component_height=tallest
            )
        except Exception as ex:
            print(f"[PCB] Hammond fit finder failed: {ex}")

        pcb_area = dims["width"] * dims["height"]

        # Vision status indicator
        try:
            from pcb_vision_deps import get_vision_deps_status, get_vision_deps_message, VisionDeps
            _vstatus = get_vision_deps_status(api_key=self._vision_api_key, model=self._vision_model)
            if _vstatus == VisionDeps.OK:
                _vdot = '<span style="color:#22c55e;font-size:14px;">\u25cf</span> <span style="color:#8b949e;font-size:10px;">Vision ready</span>'
            else:
                _vmsg = get_vision_deps_message(_vstatus)
                _vdot = (
                    '<span style="color:#eab308;font-size:14px;">\u25cf</span> '
                    '<span style="color:#8b949e;font-size:10px;" title="{}">Vision unavailable</span>'
                ).format(_vmsg.replace('"', "&quot;"))
        except Exception:
            _vdot = ""

        summary = [
            f"<b style='color:#58a6ff;'>\u2713 {os.path.basename(self._board_path)} loaded</b> {_vdot}<br>",
            f"Board: {dims['width']} \u00d7 {dims['height']} mm ({pcb_area:.0f}mm\u00b2)",
            f"Mounting holes: {len(holes)}",
            f"Edge connectors: {len(connectors)}",
        ]
        for c in connectors[:3]:
            summary.append(f"&nbsp;&nbsp;{c['ref']}: {c['name'][:40]} (h={c['height']}mm)")
        if tallest:
            summary.append(f"Tallest component: {tallest}mm")

        # Show top 5 Hammond fits
        if hammond_fits:
            summary.append("<br><b style='color:#f7c96a;'>📦 Best Hammond fits:</b>")
            for mid, spec in hammond_fits[:5]:
                ml = spec["outer_l"]
                mw = spec["outer_w"]
                mh = spec["outer_h"]
                il = spec["interior_l"]
                iw = spec["interior_w"]
                ih = spec["interior_h"]
                margin_w = round(il - dims["width"], 1)
                margin_h = round(iw - dims["height"], 1)
                margin_z = round(ih - tallest, 1)
                summary.append(
                    f"<span style='color:#e6edf3;'>"
                    f"  {mid}  {ml}×{mw}×{mh}mm  "
                    f"(+{margin_w}W +{margin_h}H +{margin_z}Z margin)</span>"
                )

        self._summary_label.setHtml("<br>".join(summary))
        self.setCurrentIndex(1)

    def _on_generate(self):
        if not self._board_data:
            return
        params = {
            "wall_thickness": self._wall_t_spin.value(),
            "lid_clearance": self._lid_clr_spin.value(),
            "boss_od": self._boss_od_spin.value(),
            "margin": 2.0,
            "headroom_mm": 2.0,
            "material": self._material_combo.currentText(),
            "ai_mode": True,
        }
        self._status.setText("AI analyzing PCB and generating enclosure...")
        self._status.setStyleSheet("color:#f7c96a; font-size:10px;")
        self.generate_clicked.emit(params)

    def show_chat(self):
        self.setCurrentIndex(2)

    # ── Chat Page ───────────────────────────────────────────

    def _make_chat_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._pcb_chat = QtWidgets.QTextEdit()
        self._pcb_chat.setReadOnly(True)
        self._pcb_chat.setStyleSheet("""
            QTextEdit {
                background: #0f1623; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 8px;
                font-size: 12px; padding: 8px;
            }
        """)
        layout.addWidget(self._pcb_chat, 1)

        return page

    def _send_refinement(self):
        text = self._pcb_input.text().strip()
        if text:
            self._pcb_input.clear()
            self._pcb_chat.append(f"<b style='color:#58a6ff;'>You:</b> {text}")
            self.generate_clicked.emit({"refinement": text})

    def add_message(self, msg):
        self._pcb_chat.append(msg)
