from compat import QtWidgets, QtCore, QtGui, Qt
_EDITOR_STYLE = "\nQPlainTextEdit {\n    background: rgba(8,9,10,0.85);\n    color:\n    font-family: 'Consolas', 'Cascadia Mono', 'JetBrains Mono', monospace;\n    font-size: 12px;\n    border: 1px solid rgba(255,255,255,0.04);\n    border-radius: 5px;\n    padding: 8px 10px;\n    selection-background-color: rgba(0,240,255,0.12);\n}\nQPlainTextEdit:focus {\n    border-color: rgba(0,240,255,0.12);\n}\n"
_COMPLETION_PROMPT = 'Complete the FreeCAD Python code at the cursor (marked as <CURSOR>).\nRules:\n- Output ONLY the text to replace <CURSOR> — no explanation, no markdown, no code fences.\n- Use proper FreeCAD API: import FreeCAD, check/create document, doc.recompute() at end.\n- Colors must be (r,g,b) tuples of floats 0-1, NOT hex strings.\n- Keep it concise (1-5 lines).\n- If explanation needed, put it as\n\n```python\n{code}\n```'
class CopilotEditor(QtWidgets.QPlainTextEdit):
    completion_applied = QtCore.Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._orch = None
        self.setStyleSheet(_EDITOR_STYLE)
        self.setTabStopDistance(QtGui.QFontMetrics(self.font()).horizontalAdvance(' ') * 4)
        self.setPlaceholderText('Write a FreeCAD Python macro here...\nCtrl+Space for AI inline completion')
        try:
            _SC = QtWidgets.QShortcut
        except AttributeError:
            _SC = QtGui.QShortcut
        self._shortcut = _SC(QtGui.QKeySequence('Ctrl+Space'), self)
        self._shortcut.activated.connect(self._do_complete)
    def set_orchestrator(self, orch):
        self._orch = orch
    def insert_at_cursor(self, text: str):
        cursor = self.textCursor()
        cursor.insertText(text)
        self.setTextCursor(cursor)
    def _code_with_cursor(self) -> str:
        cursor = self.textCursor()
        pos = cursor.position()
        code = self.toPlainText()
        return code[:pos] + '<CURSOR>' + code[pos:]
    def _clean_completion(self, text: str) -> str:
        import re
        text = re.sub('^```(?:python)?\\s*', '', text)
        text = re.sub('\\s*```$', '', text)
        text = text.strip()
        if text.startswith('<CURSOR>'):
            text = text[len('<CURSOR>'):].strip()
        if text.endswith('<CURSOR>'):
            text = text[:-len('<CURSOR>')].strip()
        return text
    def _do_complete(self):
        if not self._orch:
            return
        code = self.toPlainText()
        if not code.strip():
            return
        try:
            code_wc = self._code_with_cursor()
            prompt = _COMPLETION_PROMPT.format(code=code_wc)
            ctx = self._build_context()
            messages = [{'role': 'system', 'content': f'You are a FreeCAD macro autocomplete assistant. Write clean Python code for .FCMacro files. Colors must be (r,g,b) float tuples, not hex. Always include doc.recompute() at end.\n{ctx}'}, {'role': 'user', 'content': prompt}]
            raw = self._orch.call_ai(messages)
            if not raw:
                return
            completion = self._clean_completion(raw.strip())
            if completion:
                self.insert_at_cursor(completion)
                self.completion_applied.emit(completion)
        except Exception:
            pass
    def _build_context(self) -> str:
        try:
            import FreeCAD
            doc = FreeCAD.ActiveDocument
            if not doc:
                return 'No active FreeCAD document.'
            objs = []
            for o in doc.Objects:
                tid = getattr(o, 'TypeId', '?')
                objs.append(f"{o.Label} ({tid.split('::')[-1]})")
            ctx = f"Document: {doc.Name}, objects: {', '.join(objs[:10])}"
            if len(objs) > 10:
                ctx += f' (+{len(objs) - 10} more)'
            try:
                from FreeCADGui import activeWorkbench
                wb = activeWorkbench()
                if wb:
                    ctx += f", workbench: {(wb.menuText() if hasattr(wb, 'menuText') else type(wb).__name__)}"
            except Exception:
                pass
            return ctx
        except Exception:
            return ''
