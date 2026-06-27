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
        """Set orchestrator and propagate DXF context if available"""
        self.orch = orch
        if self._dxf_data and orch and hasattr(orch, 'set_dxf_context'):
            orch.set_dxf_context(self._dxf_data)

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
        """Build the complete user interface"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Stack for different pages
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
        
        self._dxf_input = QtWidgets.QLineEdit()
        self._dxf_input.setPlaceholderText("Refine the result... (e.g. 'make it 5mm thick')")
        self._dxf_input.setStyleSheet("""
            QLineEdit {
                background: #121a2a; color: #e6edf3;
                border: 1.5px solid #3a414a; border-radius: 8px;
                padding: 8px 12px; font-size: 12px;
            }
            QLineEdit:focus { border-color: #58a6ff; }
        """)
        self._dxf_input.returnPressed.connect(self._send_refinement)
        inp_row.addWidget(self._dxf_input, 1)

        send_btn = QtWidgets.QPushButton("Send")
        send_btn.setStyleSheet("""
            QPushButton { background:#1f6feb; color:#fff; border:none;
                          border-radius:6px; padding:6px 12px; font-size:12px; font-weight:600; }
            QPushButton:hover { background:#388bfd; }
            QPushButton:pressed { background:#0969da; }
        """)
        send_btn.clicked.connect(self._send_refinement)
        inp_row.addWidget(send_btn)
        layout.addLayout(inp_row)

    # ── Drop Page ───────────────────────────────────────────

    def _make_drop_page(self):
        """Create the drag-and-drop file upload page"""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(12, 20, 12, 12)
        layout.setSpacing(8)

        self._drop_zone = QtWidgets.QLabel()
        self._drop_zone.setAlignment(Qt.AlignCenter)
        self._drop_zone.setText(
            "<div style='font-size:14px; color:#8b949e;'>"
            "DROP .dxf FILE HERE<br>"
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

        self._loading_label = QtWidgets.QLabel("")
        self._loading_label.setAlignment(Qt.AlignCenter)
        self._loading_label.setStyleSheet("color:#8b949e; font-size:11px;")
        self._loading_label.hide()
        layout.addWidget(self._loading_label)

        layout.addStretch()
        return page

    def _drag_enter(self, event):
        """Handle drag enter events for file drops"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".dxf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _drop_file(self, event):
        """Handle dropped DXF files"""
        for url in event.mimeData().urls():
            fp = url.toLocalFile()
            if fp.lower().endswith(".dxf"):
                self._load_dxf(fp)
                break

    def _browse_file(self):
        """Open file dialog to select DXF file"""
        fp, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select DXF File", "", "DXF Files (*.dxf);;All Files (*)"
        )
        if fp:
            self._load_dxf(fp)

    def _load_dxf(self, path):
        """Load and process a DXF file locally."""
        try:
            file_size = os.path.getsize(path)
            if file_size > self._max_file_size:
                self._show_error(f"File too large ({file_size/1024/1024:.1f}MB > 20MB limit)")
                return
        except OSError as e:
            self._show_error(f"Cannot read file: {e}")
            return

        self._dxf_path = path
        self._drop_zone.setEnabled(False)
        self._loading_label.show()
        self._loading_label.setText("Processing DXF...")
        self._drop_zone.setText(
            "<div style='font-size:13px; color:#dba638;'>Processing...</div>"
        )
        QtWidgets.QApplication.processEvents()

        if not local_dxf_available():
            self._show_error(
                "DXF processing dependencies not available. "
                f"{get_deps_status_message()}"
            )
            self._drop_zone.setEnabled(True)
            self._loading_label.hide()
            return

        self._loading_label.setText("Processing locally...")
        QtWidgets.QApplication.processEvents()
        try:
            response_data = local_process_dxf(path)
            if response_data.get("status") != "ok":
                raise Exception(response_data.get("error", "Local processing failed"))
            if "profiles" not in response_data or "metadata" not in response_data:
                raise Exception("Invalid response format from local processor")
            self._dxf_data = response_data
            if self.orch and hasattr(self.orch, 'set_dxf_context'):
                self.orch.set_dxf_context(response_data)
            self._drop_zone.setEnabled(True)
            self._loading_label.hide()
            self._show_summary()
        except Exception as ex:
            self._show_error(f"Processing failed: {ex}")
            self._drop_zone.setEnabled(True)
            self._loading_label.hide()

    def _show_error(self, msg):
        """Display error message in drop zone"""
        self._dxf_data = None
        self._dxf_path = None
        self._drop_zone.setText(
            f"<div style='font-size:12px; color:#f85149;'>"
            f"⚠ {msg}<br>"
            f"<span style='font-size:11px; color:#484f58;'>click to try again</span>"
            f"</div>"
        )

    # ── Summary Page ────────────────────────────────────────

    def _make_summary_page(self):
        """Create the DXF summary and generation page"""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Summary text area
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

        # Prompt input
        self._dxf_prompt_input = QtWidgets.QLineEdit()
        self._dxf_prompt_input.setPlaceholderText(
            "Describe what to build from these profiles (e.g., 'create a 3D extrusion of these shapes')..."
        )
        self._dxf_prompt_input.setStyleSheet("""
            QLineEdit {
                background: #121a2a; color: #e6edf3;
                border: 1.5px solid #3a414a; border-radius: 8px;
                padding: 8px 12px; font-size: 12px;
            }
            QLineEdit:focus { border-color: #58a6ff; }
        """)
        self._dxf_prompt_input.returnPressed.connect(self._on_generate)
        layout.addWidget(self._dxf_prompt_input)

        # Generate button
        self._gen_btn = QtWidgets.QPushButton("Generate from DXF")
        self._gen_btn.setStyleSheet("""
            QPushButton {
                background: #1f6feb; color: #fff; border: none;
                border-radius: 8px; padding: 8px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #388bfd; }
            QPushButton:pressed { background: #0969da; }
            QPushButton:disabled { background: #3a414a; }
        """)
        self._gen_btn.clicked.connect(self._on_generate)
        layout.addWidget(self._gen_btn)

        # Status label
        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color:#8b949e; font-size:10px;")
        layout.addWidget(self._status)

        layout.addStretch()
        return page

    def _show_summary(self):
        """Display DXF file summary"""
        if not self._dxf_data:
            return
            
        data = self._dxf_data
        meta = data.get("metadata", {})
        profiles = data.get("profiles", [])
        warnings = data.get("warnings", [])

        summary_lines = [
            f"<b style='color:#58a6ff;'>✓ {os.path.basename(self._dxf_path)} loaded</b><br>",
            f"<b>Profiles:</b> {meta.get('profile_count', len(profiles))}",
            f"<b>Layers:</b> {', '.join(meta.get('layers', [])) or 'none'}",
            f"<b>Units:</b> {meta.get('units', 'unknown')}",
        ]
        
        # Add bounding box if available
        bbox = meta.get("bbox")
        if bbox and len(bbox) == 4:
            width = round(bbox[2] - bbox[0], 2)
            height = round(bbox[3] - bbox[1], 2)
            summary_lines.append(f"<b>Bounds:</b> {width} x {height} mm")
        
        # Add area if available
        if "area" in meta:
            summary_lines.append(f"<b>Total Area:</b> {round(meta['area'], 2)} mm²")
        
        # Add warnings
        if warnings:
            summary_lines.append("<br><span style='color:#dba638;'><b>⚠ Warnings:</b></span>")
            for warning in warnings[:3]:
                summary_lines.append(f"<span style='color:#dba638;'>• {warning}</span>")
            if len(warnings) > 3:
                summary_lines.append(f"<span style='color:#8b949e;'>... and {len(warnings) - 3} more</span>")

        self._summary_label.setHtml("<br>".join(summary_lines))
        self.setCurrentIndex(1)
        self._status.setText("Ready. Enter a description above and click Generate.")
        self._status.setStyleSheet("color:#8b949e; font-size:10px;")

    def _on_generate(self):
        """Handle generate button click"""
        prompt = self._dxf_prompt_input.text().strip()
        
        if not prompt:
            self._status.setText("❌ Please enter a description of what to build.")
            self._status.setStyleSheet("color:#f7c96a; font-size:10px;")
            return
            
        if not self._dxf_data:
            self._status.setText("❌ No DXF data loaded. Please upload a file first.")
            self._status.setStyleSheet("color:#f85149; font-size:10px;")
            return
            
        # Disable button during generation
        self._gen_btn.setEnabled(False)
        self._status.setText("⏳ Generating...")
        self._status.setStyleSheet("color:#58a6ff; font-size:10px;")
        
        # Emit signal
        self.generate_clicked.emit({
            "prompt": prompt, 
            "data": self._dxf_data,
            "type": "initial_generation"
        })
        
        # Re-enable button (will be disabled again if needed)
        self._gen_btn.setEnabled(True)

    def show_chat(self):
        """Switch to chat page for refinements"""
        self.setCurrentIndex(2)

    # ── Chat Page ───────────────────────────────────────────

    def _make_chat_page(self):
        """Create the chat/refinement page"""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Chat display area
        self._dxf_chat = QtWidgets.QTextEdit()
        self._dxf_chat.setReadOnly(True)
        self._dxf_chat.setStyleSheet("""
            QTextEdit {
                background: #0f1623; color: #e6edf3;
                border: 1px solid #30363d; border-radius: 8px;
                font-size: 12px; padding: 8px;
            }
        """)
        layout.addWidget(self._dxf_chat, 1)
        
        # Welcome message
        self._dxf_chat.append("<i style='color:#8b949e;'>Chat ready. You can refine the generated results using the input bar below.</i>")
        
        return page

    def _send_refinement(self):
        """Handle refinement message sending"""
        text = self._dxf_input.text().strip()
        
        if not text:
            return
            
        # Validate DXF data exists
        if not self._dxf_data:
            self._show_error("No DXF loaded. Please upload a DXF file first.")
            self._dxf_input.clear()
            return
            
        # Clear input and add user message to chat
        self._dxf_input.clear()
        msg = f"<b style='color:#58a6ff;'>You:</b> {text}"
        
        if hasattr(self, '_dxf_chat'):
            self._dxf_chat.append(msg)
        
        # Emit signal for refinement
        self.generate_clicked.emit({
            "prompt": text, 
            "data": self._dxf_data,
            "type": "refinement"
        })

    def add_message(self, msg, is_system=False):
        """Add a message to the chat display"""
        if not hasattr(self, '_dxf_chat'):
            return
            
        if is_system:
            formatted_msg = f"<i style='color:#8b949e;'>🤖 {msg}</i>"
        else:
            formatted_msg = msg
            
        self._dxf_chat.append(formatted_msg)
        
        # Auto-scroll to bottom
        scrollbar = self._dxf_chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_chat(self):
        """Clear all chat messages"""
        if hasattr(self, '_dxf_chat'):
            self._dxf_chat.clear()
            self._dxf_chat.append("<i style='color:#8b949e;'>Chat cleared. Ready for new refinements.</i>")

    def reset(self):
        """Reset widget to initial state"""
        self._dxf_data = None
        self._dxf_path = None
        self.setCurrentIndex(0)
        self._dxf_input.clear()
        
        if hasattr(self, '_dxf_chat'):
            self._dxf_chat.clear()
            self._dxf_chat.append("<i style='color:#8b949e;'>Chat ready. Upload a DXF file to start.</i>")
        
        self._drop_zone.setEnabled(True)
        self._drop_zone.setText(
            "<div style='font-size:14px; color:#8b949e;'>"
            "DROP .dxf FILE HERE<br>"
            "<span style='font-size:11px; color:#484f58;'>or click to browse</span>"
            "</div>"
        )