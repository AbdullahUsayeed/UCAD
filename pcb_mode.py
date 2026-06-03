import os
import json
from compat import QtWidgets, QtCore, QtGui, Qt, Signal


class PcbInputWidget(QtWidgets.QStackedWidget):
    generate_clicked = Signal(dict)

    def __init__(self, orch=None, parent=None):
        super().__init__(parent)
        self.orch = orch
        self._board_path = None
        self._board_data = None
        self._build_ui()

    def set_orch(self, orch):
        self.orch = orch

    def _build_ui(self):
        self._drop_page = self._make_drop_page()
        self._summary_page = self._make_summary_page()
        self._chat_page = self._make_chat_page()
        self.addWidget(self._drop_page)
        self.addWidget(self._summary_page)
        self.addWidget(self._chat_page)
        self.setCurrentIndex(0)

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
            from pcb_parser import parse
            self._board_data = parse(fp)
        except Exception as e:
            self._show_error(f"Failed to parse: {e}")
            return

        if self.orch:
            self.orch._board_context = self._board_data

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
        self._gen_btn.setStyleSheet("""
            QPushButton {
                background: #1f6feb; color: #fff; border: none;
                border-radius: 8px; padding: 8px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #388bfd; }
            QPushButton:pressed { background: #0969da; }
        """)
        self._gen_btn.clicked.connect(self._on_generate)
        layout.addWidget(self._gen_btn)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color:#8b949e; font-size:10px;")
        layout.addWidget(self._status)

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
        except Exception:
            pass

        summary = [
            f"<b style='color:#58a6ff;'>✓ {os.path.basename(self._board_path)} loaded</b><br>",
            f"Board: {dims['width']} x {dims['height']} mm",
            f"Mounting holes: {len(holes)}",
            f"Edge connectors: {len(connectors)}",
        ]
        for c in connectors[:3]:
            summary.append(f"&nbsp;&nbsp;{c['ref']}: {c['name'][:40]} (h={c['height']}mm)")
        if tallest:
            summary.append(f"Tallest component: {tallest}mm")

        self._summary_label.setHtml("<br>".join(summary))
        self.setCurrentIndex(1)

    def _on_generate(self):
        params = {
            "wall_thickness": self._wall_t_spin.value(),
            "lid_clearance": self._lid_clr_spin.value(),
            "boss_od": self._boss_od_spin.value(),
            "material": self._material_combo.currentText(),
        }
        self._status.setText("Generating enclosure...")
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

        inp_row = QtWidgets.QHBoxLayout()
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

        return page

    def _send_refinement(self):
        text = self._pcb_input.text().strip()
        if text:
            self._pcb_chat.append(f"<b style='color:#58a6ff;'>You:</b> {text}")
            self._pcb_input.clear()
            self.generate_clicked.emit({"refinement": text})

    def add_message(self, msg):
        self._pcb_chat.append(msg)
