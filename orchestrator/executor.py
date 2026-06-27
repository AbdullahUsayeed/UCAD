"""Plan executor, failure classification, and execution context."""
import FreeCAD, FreeCADGui
from collections import Counter


class StepResult:
    """Result of executing one plan step."""
    def __init__(self):
        self.success = False
        self.message = ""
        self.observation = ""
        self.plan_complete = False
        self.plan_revised = False
        self.blocks = []
        self.raw_text = ""


class PlanExecutor:
    """Orchestrates multi-step plan execution with injectable callables."""

    def __init__(self, generate_fn, execute_fn, observe_fn, diff_fn,
                 extract_blocks_fn, build_messages_fn):
        self.generate = generate_fn
        self.execute = execute_fn
        self.observe = observe_fn
        self.diff = diff_fn
        self.extract_blocks = extract_blocks_fn
        self.build_messages = build_messages_fn
        self.retries = 0

    def execute_step(self, prompt, plan_steps, step_idx, input_text, max_retries=5):
        """Execute a single plan step. Returns StepResult."""
        result = StepResult()

        raw_text, code, used_api = self.generate(prompt)
        result.raw_text = raw_text or ""

        blocks = self.extract_blocks(code or "")
        if not blocks:
            result.message = "AI returned no code in the response."
            return result

        for block in blocks:
            success, message = self.execute(block)
            if not success and self.retries < max_retries:
                self.retries += 1
                fresh_obs = self.observe()
                ctx = self.build_messages(input_text, mode="build",
                    retry_context=f"Previous code failed: {message}. "
                                  f"Current scene: {fresh_obs}")
                raw_text2, code2, _ = self.generate(ctx)
                blocks2 = self.extract_blocks(code2 or "")
                if blocks2:
                    block = blocks2[0]
                    success, message = self.execute(block)

            result.success = success
            result.message = message
            result.blocks = blocks
            if not success:
                return result

        result.success = True
        result.message = message

        step_idx += 1
        if plan_steps and step_idx >= len(plan_steps):
            result.plan_complete = True

        return result


class _DeltaCResult:
    """Minimal delta-C result stub."""
    class Delta:
        def __init__(self):
            self.summary = ""
        def __repr__(self):
            return "Delta()"
    def __init__(self):
        self.deltas = []
    def __repr__(self):
        return "_DeltaCResult(deltas=[])"


class _CadDagStub:
    """Minimal CAD DAG stub — stores step labels, never crashes."""
    class _Op:
        def __init__(self, label):
            self.label = label
            self.executed = False
    def __init__(self):
        self.ops = {}
    def _rebuild(self, steps):
        self.ops = {f"step_{i}": self._Op(s) for i, s in enumerate(steps)}
    def rollback_to(self, step_id):
        for sid, op in self.ops.items():
            if sid >= step_id:
                op.executed = False
    def mark_validated(self, step_id):
        pass
    def mark_executed(self, step_id):
        op = self.ops.get(step_id)
        if op:
            op.executed = True
    def commit_frontier(self):
        return [sid for sid, op in self.ops.items() if not op.executed]


FAILURE_MODES = {
    "syntax": ["SyntaxError", "IndentationError", "TabError", "NameError",
               "invalid syntax", "unexpected indent", "unmatched"],
    "geometry": ["Part::", "BRep", "TopoDS", "Shape", "null shape",
                 "Failed to create", "cannot compute", "infinite"],
    "execution": ["TypeError", "ValueError", "AttributeError", "KeyError",
                  "IndexError", "ZeroDivisionError", "RuntimeError",
                  "'NoneType'", "is not defined", "module 'Part'"],
    "api": ["FreeCAD", "App::", "Gui::", "Document", "Object", "Property",
            "no active document", "is not attached", "not found"],
    "timeout": ["timeout", "timed out", "Timeout", "TimeoutError"],
    "memory": ["MemoryError", "out of memory", "Kernel"],
    "ai_format": ["exceeded maximum context", "rate_limit", "content_filter",
                  "API key", "401", "403", "429", "insufficient_quota"],
}


def classify_failure(message: str) -> str:
    if not message:
        return "unknown"
    msg_lower = message.lower()
    for mode, patterns in FAILURE_MODES.items():
        for p in patterns:
            if p.lower() in msg_lower:
                return mode
    return "unknown"


def summarize_failures(modes: list) -> str:
    if not modes:
        return ""
    counts = Counter(modes)
    parts = [f"{mode} (x{n})" for mode, n in counts.most_common(5)]
    return "; ".join(parts)


class ExecutionContext:
    """Snapshots FreeCAD UI state before AI execution and restores it after."""
    def snapshot(self):
        try:
            self.active_doc_name = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
        except Exception:
            self.active_doc_name = None
        try:
            wb = FreeCADGui.activeWorkbench()
            self.active_workbench = wb.name() if wb else None
        except Exception:
            self.active_workbench = None
        self.active_object = None
        self.in_edit = None
        try:
            doc = FreeCAD.ActiveDocument
            if doc:
                self.active_object = doc.ActiveObject
            gdoc = FreeCADGui.getDocument(self.active_doc_name) if self.active_doc_name else None
            if gdoc:
                self.in_edit = gdoc.getInEdit()
        except Exception as ex:
            print(f"[AI] ExecutionContext.snapshot failed: {ex}")

    def restore(self):
        try:
            doc = FreeCAD.ActiveDocument
            if doc:
                from FreeCADGui import Selection
                Selection.clearSelection()
                if self.active_object:
                    try:
                        Selection.addSelection(self.active_object)
                    except Exception as ex:
                        print(f"[AI] ExecutionContext.restore selection failed: {ex}")
        except Exception as ex:
            print(f"[AI] ExecutionContext.restore outer failed: {ex}")
        try:
            if self.active_workbench:
                FreeCADGui.activateWorkbench(self.active_workbench)
        except Exception as ex:
            print(f"[AI] ExecutionContext.restore workbench failed: {ex}")
        try:
            doc = FreeCAD.ActiveDocument
            if doc:
                doc.recompute()
        except Exception as ex:
            print(f"[AI] ExecutionContext.restore recompute failed: {ex}")
