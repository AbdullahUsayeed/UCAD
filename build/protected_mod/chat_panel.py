from compat import QtWidgets, Qt
_sCYAN = '#00f0ff'
_sTEXT = '#ebedf0'
_sSUB = '#8a9099'
_sMUTE = '#4a4f57'
_sBDR = 'rgba(255,255,255,0.05)'
_sBHOV = 'rgba(255,255,255,0.10)'
CHAT_STYLE = f"\n    QTextEdit {{\n        background: rgba(15,16,18,0.60);\n        color: {_sTEXT};\n        font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', Arial, sans-serif;\n        font-size: 13px;\n        border: 1px solid {_sBDR};\n        border-radius: 8px;\n        padding: 10px 12px;\n        selection-background-color: rgba(255,255,255,0.06);\n    }}\n    QScrollBar:vertical {{\n        background: transparent;\n        width: 3px;\n        margin: 0;\n    }}\n    QScrollBar::handle:vertical {{\n        background: rgba(255,255,255,0.08);\n        border-radius: 2px;\n        min-height: 20px;\n    }}\n    QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.15); }}\n    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}\n"
THINKING_STYLE = f"\n    QTextEdit {{\n        background: rgba(8,9,10,0.60);\n        color: {_sSUB};\n        font-family: 'Consolas', 'Cascadia Mono', 'JetBrains Mono', monospace;\n        font-size: 11px;\n        border: 1px solid {_sBDR};\n        border-radius: 8px;\n        padding: 8px 12px;\n    }}\n"
class ThinkingSection(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = True
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)
        self._toggle = QtWidgets.QPushButton('▾  Thinking…')
        self._toggle.setFlat(True)
        self._toggle.setStyleSheet(f'QPushButton{{background:transparent;color:{_sMUTE};font-size:9px;font-weight:600;border:none;text-align:left;padding:2px 4px 0 4px;letter-spacing:0.5px;}}QPushButton:hover{{color:{_sSUB};}}')
        self._toggle.clicked.connect(self._do_toggle)
        root.addWidget(self._toggle)
        self._box = QtWidgets.QTextEdit()
        self._box.setReadOnly(True)
        self._box.setMaximumHeight(180)
        self._box.setStyleSheet(THINKING_STYLE)
        root.addWidget(self._box)
        self.setVisible(False)
    def show_thinking(self, header='Thinking…'):
        self._toggle.setText(f'▾  {header}')
        self.setVisible(True)
    def hide_thinking(self):
        self.setVisible(False)
    def clear(self):
        self._box.clear()
    def setHtml(self, html: str):
        self._box.setHtml(html)
    def insertHtml(self, html: str):
        self._box.insertHtml(html)
    def append(self, text: str, color: str='#c8d8e8'):
        import html as _h
        self._box.insertHtml(f'<br><span style="color:{color}">{_h.escape(text)}</span>')
        sb = self._box.verticalScrollBar()
        sb.setValue(sb.maximum())
    def verticalScrollBar(self):
        return self._box.verticalScrollBar()
    def _do_toggle(self):
        self._expanded = not self._expanded
        self._box.setVisible(self._expanded)
        lbl = self._toggle.text().split('  ', 1)[-1]
        self._toggle.setText(('▾  ' if self._expanded else '▸  ') + lbl)
class ChatPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        self.chat = QtWidgets.QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chat.setStyleSheet(CHAT_STYLE)
        root.addWidget(self.chat, 1)
        self._thinking = ThinkingSection()
        root.addWidget(self._thinking)
    @property
    def _thinking_header(self):
        return self._thinking._toggle
    @_thinking_header.setter
    def _thinking_header(self, value):
        pass
    def msg(self, sender: str, text: str):
        import html as _html
        safe_text = _html.escape(text)
        self.chat.append(f'<div style="margin:4px 0;"><b style="color:{_sCYAN};">{sender}:</b> <span style="color:{_sTEXT};">{safe_text}</span></div>')
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())
    def show_thinking(self, header='Thinking…', visible=True):
        if visible:
            self._thinking.show_thinking(header)
        else:
            self._thinking.hide_thinking()
    def clear_thinking(self):
        self._thinking.clear()
    def append_thinking(self, text: str, color: str='#c8d8e8'):
        self._thinking.append(text, color)
    def embed_viewport_image(self, b64_data: str, label: str='After') -> str:
        if not b64_data:
            return ''
        import html as _html
        safe_label = _html.escape(label)
        html = f'<div style="margin:6px 0;text-align:center;"><div style="color:#8b949e;font-size:9px;margin-bottom:2px;">{safe_label}</div><img src="data:image/png;base64,{b64_data}" style="max-width:100%;border-radius:8px;border:1px solid rgba(255,255,255,0.06);" /></div>'
        self.chat.append(html)
        return html
    def clear(self):
        self.chat.clear()
        self._thinking.clear()
