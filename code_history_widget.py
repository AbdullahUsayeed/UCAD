from compat import QtWidgets, QtCore

_sCYAN = "#00f0ff"
_sTEXT = "#ebedf0"
_sSUB  = "#8a9099"
_sMUTE = "#4a4f57"
_sBDR  = "rgba(255,255,255,0.05)"
_sBHOV = "rgba(255,255,255,0.10)"

SAVE_STYLE = f"""
    QPushButton {{
        background: transparent;
        color: {_sSUB};
        border: 1px solid {_sBDR};
        border-radius: 4px;
        font-size: 10px;
        padding: 1px 6px;
        min-width: 44px;
    }}
    QPushButton:hover {{
        background: rgba(255,255,255,0.04);
        color: {_sTEXT};
        border-color: {_sBHOV};
    }}
"""

CODE_STYLE = f"""
    QTextEdit {{
        background: rgba(17,18,20,0.50);
        color: {_sTEXT};
        font-family: 'Consolas', 'Cascadia Mono', 'JetBrains Mono', monospace;
        font-size: 11px;
        border: 1px solid {_sBDR};
        border-top: none;
        border-radius: 0 0 6px 6px;
        padding: 8px 12px;
    }}
"""

HEADER_STYLE = f"""
    background: rgba(26,27,30,0.70);
    border: 1px solid {_sBDR};
    border-radius: 6px 6px 0 0;
"""


class CodeEntry(QtWidgets.QWidget):
    def __init__(self, step_label, code, save_callback=None, parent=None):
        super().__init__(parent)
        self._code = code
        self._save_callback = save_callback
        self._expanded = True

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(0)

        self._header = QtWidgets.QWidget()
        self._header.setFixedHeight(28)
        self._header.setStyleSheet(HEADER_STYLE)
        h = QtWidgets.QHBoxLayout(self._header)
        h.setContentsMargins(8, 0, 6, 0)
        h.setSpacing(6)

        self._toggle_btn = QtWidgets.QPushButton(f"\u25be  {step_label}")
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#8a9099;font-size:10px;"
            "font-weight:600;border:none;text-align:left;padding:0;letter-spacing:0.3px;}"
            "QPushButton:hover{color:#ebedf0;}"
        )
        self._toggle_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self._toggle_btn.clicked.connect(self._toggle)
        h.addWidget(self._toggle_btn)

        h.addStretch()

        self._save_btn = QtWidgets.QPushButton("\U0001f4be Save")
        self._save_btn.setToolTip("Save as .FCMacro")
        self._save_btn.setFixedHeight(20)
        self._save_btn.setStyleSheet(SAVE_STYLE)
        self._save_btn.clicked.connect(self._do_save)
        h.addWidget(self._save_btn)

        self._copy_btn = QtWidgets.QPushButton("\U0001f4cb Copy")
        self._copy_btn.setToolTip("Copy code to clipboard")
        self._copy_btn.setFixedHeight(20)
        self._copy_btn.setStyleSheet(SAVE_STYLE)
        self._copy_btn.clicked.connect(self._do_copy)
        h.addWidget(self._copy_btn)

        root.addWidget(self._header)

        self._body = QtWidgets.QWidget()
        self._body.setStyleSheet("background:rgba(20,21,24,0.50);border:none;")
        blay = QtWidgets.QVBoxLayout(self._body)
        blay.setContentsMargins(0, 0, 0, 0)
        blay.setSpacing(0)

        self._editor = QtWidgets.QTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setMinimumHeight(60)
        self._editor.setMaximumHeight(260)
        self._editor.setStyleSheet(CODE_STYLE)
        self._editor.setPlainText(code)
        blay.addWidget(self._editor)

        self._status = QtWidgets.QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:transparent;font-size:10px;padding:2px 4px;")
        self._status.setVisible(False)
        blay.addWidget(self._status)

        root.addWidget(self._body)

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        arrow = "\u25be" if self._expanded else "\u25b8"
        label = self._toggle_btn.text().split("  ", 1)[-1]
        self._toggle_btn.setText(f"{arrow}  {label}")

    def _do_save(self):
        if self._save_callback:
            self._save_callback(self._code)

    def _do_copy(self):
        if not self._code:
            return
        try:
            QtWidgets.QApplication.clipboard().setText(self._code)
            self._set_status("\u2714 Copied to clipboard", ok=True)
            status = self._status
            QtCore.QTimer.singleShot(2000, lambda: self._safe_hide_status(status))
        except Exception as exc:
            self._set_status(f"Copy failed: {exc}", ok=False)

    def _safe_hide_status(self, status):
        try:
            status.setVisible(False)
        except RuntimeError:
            pass

    def _set_status(self, msg, ok=True):
        self._status.setText(msg)
        self._status.setStyleSheet(
            f"color:{'#3fb950' if ok else '#f85149'};font-size:10px;padding:2px 4px;"
        )
        self._status.setVisible(True)

    def set_save_callback(self, cb):
        self._save_callback = cb


class CodeHistoryWidget(QtWidgets.QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        self._container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(2)
        self._layout.addStretch()
        self.setWidget(self._container)

        self._save_callback = None
        self._entries = []

    def append(self, step_label, code):
        entry = CodeEntry(step_label, code, save_callback=self._save_callback)
        self._layout.insertWidget(self._layout.count() - 1, entry)
        self._entries.append(entry)
        QtCore.QTimer.singleShot(50, self._scroll_to_bottom)

    def clear(self):
        for entry in self._entries:
            self._layout.removeWidget(entry)
            entry.deleteLater()
        self._entries = []

    @property
    def count(self):
        return len(self._entries)

    def set_save_callback(self, cb):
        self._save_callback = cb
        for entry in self._entries:
            entry.set_save_callback(cb)

    def _scroll_to_bottom(self):
        try:
            sb = self.verticalScrollBar()
            sb.setValue(sb.maximum())
        except RuntimeError:
            pass
