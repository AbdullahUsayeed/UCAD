import os
from compat import QtWidgets, Qt, Signal
from local_dxf import process_dxf as local_process_dxf, is_available as local_dxf_available, get_deps_status_message
class DxfInputWidget(QtWidgets.QWidget):
    generate_clicked = Signal(dict)
    def __init__(self, orch=None, parent=None):
        super().__init__(parent)
        self.orch = orch
        self._dxf_data = None
        self._dxf_path = None
        self._max_file_size = 100 * 1024 * 1024
        self._build_ui()
    def set_orch(self, orch):
        self.orch = orch
        if self._dxf_data and orch and hasattr(orch, 'set_dxf_context'):
            orch.set_dxf_context(self._dxf_data)
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
        inp_row = QtWidgets.QHBoxLayout()
        inp_row.setContentsMargins(8, 0, 8, 0)
        self._dxf_input = QtWidgets.QLineEdit()
        self._dxf_input.setPlaceholderText("Refine the result... (e.g. 'make it 5mm thick')")
        self._dxf_input.setStyleSheet('\n            QLineEdit {\n                background:\n                border: 1.5px solid\n                padding: 8px 12px; font-size: 12px;\n            }\n            QLineEdit:focus { border-color:\n        ')
        self._dxf_input.returnPressed.connect(self._send_refinement)
        inp_row.addWidget(self._dxf_input, 1)
        send_btn = QtWidgets.QPushButton('Send')
        send_btn.setStyleSheet('\n            QPushButton { background:\n                          border-radius:6px; padding:6px 12px; font-size:12px; font-weight:600; }\n            QPushButton:hover { background:\n            QPushButton:pressed { background:\n        ')
        send_btn.clicked.connect(self._send_refinement)
        inp_row.addWidget(send_btn)
        layout.addLayout(inp_row)
    def _make_drop_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(8)
        self._drop_zone = QtWidgets.QLabel()
        self._drop_zone.setAlignment(Qt.AlignCenter)
        self._drop_zone.setText("<div style='font-size:14px; color:#8b949e;'>DROP .dxf FILE HERE<br><span style='font-size:11px; color:#484f58;'>or click to browse</span></div>")
        self._drop_zone.setFixedHeight(120)
        self._drop_zone.setStyleSheet('\n            QLabel {\n                background:\n                border: 2px dashed\n                border-radius: 12px;\n                padding: 20px;\n            }\n            QLabel:hover {\n                border-color:\n                background:\n            }\n        ')
        self._drop_zone.setCursor(Qt.PointingHandCursor)
        self._drop_zone.mousePressEvent = lambda e: self._browse_file()
        self._drop_zone.setAcceptDrops(True)
        self._drop_zone.dragEnterEvent = self._drag_enter
        self._drop_zone.dropEvent = self._drop_file
        layout.addWidget(self._drop_zone)
        self._loading_label = QtWidgets.QLabel('')
        self._loading_label.setAlignment(Qt.AlignCenter)
        self._loading_label.setStyleSheet('color:#8b949e; font-size:11px;')
        self._loading_label.hide()
        layout.addWidget(self._loading_label)
        layout.addStretch()
        return page
    def _drag_enter(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.dxf'):
                    event.acceptProposedAction()
                    return
        event.ignore()
    def _drop_file(self, event):
        for url in event.mimeData().urls():
            fp = url.toLocalFile()
            if fp.lower().endswith('.dxf'):
                self._load_dxf(fp)
                break
    def _browse_file(self):
        fp, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Select DXF File', '', 'DXF Files (*.dxf);;All Files (*)')
        if fp:
            self._load_dxf(fp)
    def _load_dxf(self, path):
        try:
            file_size = os.path.getsize(path)
            if file_size > self._max_file_size:
                self._show_error(f'File too large ({file_size / 1024 / 1024:.1f}MB > 20MB limit)')
                return
        except OSError as e:
            self._show_error(f'Cannot read file: {e}')
            return
        self._dxf_path = path
        self._drop_zone.setEnabled(False)
        self._loading_label.show()
        self._loading_label.setText('Processing DXF...')
        self._drop_zone.setText("<div style='font-size:13px; color:#dba638;'>Processing...</div>")
        QtWidgets.QApplication.processEvents()
        if not local_dxf_available():
            self._show_error(f'DXF processing dependencies not available. {get_deps_status_message()}')
            self._drop_zone.setEnabled(True)
            self._loading_label.hide()
            return
        self._loading_label.setText('Processing locally...')
        QtWidgets.QApplication.processEvents()
        try:
            response_data = local_process_dxf(path)
            if response_data.get('status') != 'ok':
                raise Exception(response_data.get('error', 'Local processing failed'))
            if 'profiles' not in response_data or 'metadata' not in response_data:
                raise Exception('Invalid response format from local processor')
            self._dxf_data = response_data
            if self.orch and hasattr(self.orch, 'set_dxf_context'):
                self.orch.set_dxf_context(response_data)
            self._drop_zone.setEnabled(True)
            self._loading_label.hide()
            self._show_summary()
        except Exception as ex:
            self._show_error(f'Processing failed: {ex}')
            self._drop_zone.setEnabled(True)
            self._loading_label.hide()
    def _show_error(self, msg):
        self._dxf_data = None
        self._dxf_path = None
        self._drop_zone.setText(f"<div style='font-size:12px; color:#f85149;'>⚠ {msg}<br><span style='font-size:11px; color:#484f58;'>click to try again</span></div>")
    def _make_summary_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._summary_label = QtWidgets.QTextEdit()
        self._summary_label.setReadOnly(True)
        self._summary_label.setMaximumHeight(150)
        self._summary_label.setStyleSheet("\n            QTextEdit {\n                background:\n                border: 1px solid\n                font-size: 11px; padding: 8px;\n                font-family: 'Consolas', monospace;\n            }\n        ")
        layout.addWidget(self._summary_label)
        self._dxf_prompt_input = QtWidgets.QLineEdit()
        self._dxf_prompt_input.setPlaceholderText("Describe what to build from these profiles (e.g., 'create a 3D extrusion of these shapes')...")
        self._dxf_prompt_input.setStyleSheet('\n            QLineEdit {\n                background:\n                border: 1.5px solid\n                padding: 8px 12px; font-size: 12px;\n            }\n            QLineEdit:focus { border-color:\n        ')
        self._dxf_prompt_input.returnPressed.connect(self._on_generate)
        layout.addWidget(self._dxf_prompt_input)
        self._gen_btn = QtWidgets.QPushButton('Generate from DXF')
        self._gen_btn.setStyleSheet('\n            QPushButton {\n                background:\n                border-radius: 8px; padding: 8px; font-size: 13px; font-weight: 600;\n            }\n            QPushButton:hover { background:\n            QPushButton:pressed { background:\n            QPushButton:disabled { background:\n        ')
        self._gen_btn.clicked.connect(self._on_generate)
        layout.addWidget(self._gen_btn)
        self._status = QtWidgets.QLabel('')
        self._status.setStyleSheet('color:#8b949e; font-size:10px;')
        layout.addWidget(self._status)
        layout.addStretch()
        return page
    def _show_summary(self):
        if not self._dxf_data:
            return
        data = self._dxf_data
        meta = data.get('metadata', {})
        profiles = data.get('profiles', [])
        warnings = data.get('warnings', [])
        summary_lines = [f"<b style='color:#58a6ff;'>✓ {os.path.basename(self._dxf_path)} loaded</b><br>", f"<b>Profiles:</b> {meta.get('profile_count', len(profiles))}", f"<b>Layers:</b> {', '.join(meta.get('layers', [])) or 'none'}", f"<b>Units:</b> {meta.get('units', 'unknown')}"]
        bbox = meta.get('bbox')
        if bbox and len(bbox) == 4:
            width = round(bbox[2] - bbox[0], 2)
            height = round(bbox[3] - bbox[1], 2)
            summary_lines.append(f'<b>Bounds:</b> {width} x {height} mm')
        if 'area' in meta:
            summary_lines.append(f"<b>Total Area:</b> {round(meta['area'], 2)} mm²")
        if warnings:
            summary_lines.append("<br><span style='color:#dba638;'><b>⚠ Warnings:</b></span>")
            for warning in warnings[:3]:
                summary_lines.append(f"<span style='color:#dba638;'>• {warning}</span>")
            if len(warnings) > 3:
                summary_lines.append(f"<span style='color:#8b949e;'>... and {len(warnings) - 3} more</span>")
        self._summary_label.setHtml('<br>'.join(summary_lines))
        self.setCurrentIndex(1)
        self._status.setText('Ready. Enter a description above and click Generate.')
        self._status.setStyleSheet('color:#8b949e; font-size:10px;')
    def _on_generate(self):
        prompt = self._dxf_prompt_input.text().strip()
        if not prompt:
            self._status.setText('❌ Please enter a description of what to build.')
            self._status.setStyleSheet('color:#f7c96a; font-size:10px;')
            return
        if not self._dxf_data:
            self._status.setText('❌ No DXF data loaded. Please upload a file first.')
            self._status.setStyleSheet('color:#f85149; font-size:10px;')
            return
        self._gen_btn.setEnabled(False)
        self._status.setText('⏳ Generating...')
        self._status.setStyleSheet('color:#58a6ff; font-size:10px;')
        self.generate_clicked.emit({'prompt': prompt, 'data': self._dxf_data, 'type': 'initial_generation'})
        self._gen_btn.setEnabled(True)
    def show_chat(self):
        self.setCurrentIndex(2)
    def _make_chat_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._dxf_chat = QtWidgets.QTextEdit()
        self._dxf_chat.setReadOnly(True)
        self._dxf_chat.setStyleSheet('\n            QTextEdit {\n                background:\n                border: 1px solid\n                font-size: 12px; padding: 8px;\n            }\n        ')
        layout.addWidget(self._dxf_chat, 1)
        self._dxf_chat.append("<i style='color:#8b949e;'>Chat ready. You can refine the generated results using the input bar below.</i>")
        return page
    def _send_refinement(self):
        text = self._dxf_input.text().strip()
        if not text:
            return
        if not self._dxf_data:
            self._show_error('No DXF loaded. Please upload a DXF file first.')
            self._dxf_input.clear()
            return
        self._dxf_input.clear()
        msg = f"<b style='color:#58a6ff;'>You:</b> {text}"
        if hasattr(self, '_dxf_chat'):
            self._dxf_chat.append(msg)
        self.generate_clicked.emit({'prompt': text, 'data': self._dxf_data, 'type': 'refinement'})
    def add_message(self, msg, is_system=False):
        if not hasattr(self, '_dxf_chat'):
            return
        if is_system:
            formatted_msg = f"<i style='color:#8b949e;'>🤖 {msg}</i>"
        else:
            formatted_msg = msg
        self._dxf_chat.append(formatted_msg)
        scrollbar = self._dxf_chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    def clear_chat(self):
        if hasattr(self, '_dxf_chat'):
            self._dxf_chat.clear()
            self._dxf_chat.append("<i style='color:#8b949e;'>Chat cleared. Ready for new refinements.</i>")
    def reset(self):
        self._dxf_data = None
        self._dxf_path = None
        self.setCurrentIndex(0)
        self._dxf_input.clear()
        if hasattr(self, '_dxf_chat'):
            self._dxf_chat.clear()
            self._dxf_chat.append("<i style='color:#8b949e;'>Chat ready. Upload a DXF file to start.</i>")
        self._drop_zone.setEnabled(True)
        self._drop_zone.setText("<div style='font-size:14px; color:#8b949e;'>DROP .dxf FILE HERE<br><span style='font-size:11px; color:#484f58;'>or click to browse</span></div>")
