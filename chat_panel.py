from compat import QtWidgets, Qt


# ── Obsidian palette ────────────────────────────────────────────────────────
_sCYAN = "#00f0ff"
_sTEXT = "#ebedf0"
_sSUB  = "#8a9099"
_sMUTE = "#4a4f57"
_sBDR  = "rgba(255,255,255,0.05)"
_sBHOV = "rgba(255,255,255,0.10)"

CHAT_STYLE = f"""
    QTextEdit {{
        background: rgba(15,16,18,0.60);
        color: {_sTEXT};
        font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', Arial, sans-serif;
        font-size: 13px;
        border: 1px solid {_sBDR};
        border-radius: 8px;
        padding: 10px 12px;
        selection-background-color: rgba(255,255,255,0.06);
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 3px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(255,255,255,0.08);
        border-radius: 2px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.15); }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

THINKING_STYLE = f"""
    QTextEdit {{
        background: rgba(8,9,10,0.60);
        color: {_sSUB};
        font-family: 'Consolas', 'Cascadia Mono', 'JetBrains Mono', monospace;
        font-size: 11px;
        border: 1px solid {_sBDR};
        border-radius: 8px;
        padding: 8px 12px;
    }}
"""


class ThinkingSection(QtWidgets.QWidget):
    """Collapsible thinking panel with a minimal header."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = True

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        self._toggle = QtWidgets.QPushButton("\u25be  Thinking\u2026")
        self._toggle.setFlat(True)
        self._toggle.setStyleSheet(
            f"QPushButton{{background:transparent;color:{_sMUTE};font-size:9px;"
            f"font-weight:600;border:none;text-align:left;padding:2px 4px 0 4px;"
            f"letter-spacing:0.5px;}}"
            f"QPushButton:hover{{color:{_sSUB};}}"
        )
        self._toggle.clicked.connect(self._do_toggle)
        root.addWidget(self._toggle)

        self._box = QtWidgets.QTextEdit()
        self._box.setReadOnly(True)
        self._box.setMaximumHeight(180)
        self._box.setStyleSheet(THINKING_STYLE)
        root.addWidget(self._box)

        self.setVisible(False)

    def show_thinking(self, header="Thinking\u2026"):
        self._toggle.setText(f"\u25be  {header}")
        self.setVisible(True)

    def hide_thinking(self):
        self.setVisible(False)

    def clear(self):
        self._box.clear()

    def setHtml(self, html: str):
        self._box.setHtml(html)

    def insertHtml(self, html: str):
        self._box.insertHtml(html)

    def append(self, text: str, color: str = "#c8d8e8"):
        import html as _h
        self._box.insertHtml(f'<br><span style="color:{color}">{_h.escape(text)}</span>')
        sb = self._box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def verticalScrollBar(self):
        return self._box.verticalScrollBar()

    def _do_toggle(self):
        self._expanded = not self._expanded
        self._box.setVisible(self._expanded)
        lbl = self._toggle.text().split("  ", 1)[-1]
        self._toggle.setText(("\u25be  " if self._expanded else "\u25b8  ") + lbl)


class ChatPanel(QtWidgets.QWidget):
    """
    Message display + collapsible thinking section.

    Layout (top \u2192 bottom):
        [chat display \u2014 stretches]
        [Thinking section \u2014 collapsible]
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── Chat display ────────────────────────────────────────────────
        self.chat = QtWidgets.QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.chat.setStyleSheet(CHAT_STYLE)
        root.addWidget(self.chat, 1)

        # ── Thinking section ────────────────────────────────────────────
        self._thinking = ThinkingSection()
        root.addWidget(self._thinking)

    # ── Legacy aliases ─────────────────────────────────────────────────

    @property
    def _thinking_header(self):
        return self._thinking._toggle

    @_thinking_header.setter
    def _thinking_header(self, value):
        pass  # read-only alias

    # ── Chat helpers ────────────────────────────────────────────────────

    def msg(self, sender: str, text: str):
        import html as _html
        safe_text = _html.escape(text)
        self.chat.append(
            f'<div style="margin:4px 0;">'
            f'<b style="color:{_sCYAN};">{sender}:</b> '
            f'<span style="color:{_sTEXT};">{safe_text}</span>'
            f'</div>'
        )
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Thinking helpers ────────────────────────────────────────────────

    def show_thinking(self, header="Thinking\u2026", visible=True):
        if visible:
            self._thinking.show_thinking(header)
        else:
            self._thinking.hide_thinking()

    def clear_thinking(self):
        self._thinking.clear()

    def append_thinking(self, text: str, color: str = "#c8d8e8"):
        self._thinking.append(text, color)

    # ── Viewport image ──────────────────────────────────────────────────

    def embed_viewport_image(self, b64_data: str, label: str = "After") -> str:
        if not b64_data:
            return ""
        import html as _html
        safe_label = _html.escape(label)
        html = (
            f'<div style="margin:6px 0;text-align:center;">'
            f'<div style="color:#8b949e;font-size:9px;margin-bottom:2px;">{safe_label}</div>'
            f'<img src="data:image/png;base64,{b64_data}" '
            f'style="max-width:100%;border-radius:8px;border:1px solid rgba(255,255,255,0.06);" />'
            f'</div>'
        )
        self.chat.append(html)
        return html

    # ── Global clear ────────────────────────────────────────────────────

    def clear(self):
        self.chat.clear()
        self._thinking.clear()
