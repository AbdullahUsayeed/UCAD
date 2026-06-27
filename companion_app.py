import FreeCAD
from compat import QtCore, Signal
from orchestrator import AIOrchestrator


# ── Worker ───────────────────────────────────────────────────

class CodeWorker(QtCore.QObject):
    finished = QtCore.Signal(str, str, bool, int)
    error = QtCore.Signal(str, int)
    stream = QtCore.Signal(str, str)

    def __init__(self, orch, api_msgs=None, user_input="", mid_plan=False, gen=0,
                 plan_steps=None, step_index=0, scene=None, mode="build",
                 api_key="", provider="", **kwargs):
        super().__init__()
        self.orch = orch
        self.api_msgs = api_msgs
        self.user_input = user_input
        self.mid_plan = mid_plan
        self._cancel = False
        self._gen = gen
        self._mode = mode
        self._plan_steps = plan_steps or []
        self._step_index = step_index
        self._scene = scene or {}
        self._api_key = api_key
        self._provider = provider

    def run(self):
        try:
            def _on_token(text, typ):
                if not self._cancel:
                    self.stream.emit(text, typ)
            raw, code, used_api = self.orch.generate_code_safe(self.api_msgs, self.user_input, stream_callback=_on_token)
            if not code:
                code = self.orch.get_fallback_code(self.user_input, self.mid_plan)
                used_api = False
            if not self._cancel:
                self.finished.emit(raw or "", code or "", used_api, self._gen)
        except Exception as e:
            if not self._cancel:
                self.error.emit(str(e), self._gen)

    def cancel(self):
        self._cancel = True


class ClassifyWorker(QtCore.QObject):
    """Background worker for the cheap LLM complexity tie-breaker.

    Only calls orch.classify_request_llm() — a network-only operation with no
    FreeCAD state access — so it is safe off the main thread. The resolved
    label is emitted back to the main thread, which then builds messages and
    launches the real CodeWorker (message building must stay on the main thread).
    """
    finished = QtCore.Signal(str, str, int)  # label, user_input, gen

    def __init__(self, orch, user_input="", fallback_label="medium", gen=0):
        super().__init__()
        self.orch = orch
        self.user_input = user_input
        self.fallback_label = fallback_label
        self._gen = gen
        self._cancel = False

    def run(self):
        try:
            label = self.orch.classify_request_llm(self.user_input)
        except Exception:
            label = self.fallback_label
        if not self._cancel:
            self.finished.emit(label or self.fallback_label, self.user_input, self._gen)

    def cancel(self):
        self._cancel = True


class Coordinator(QtCore.QObject):
    """Orchestrates AI worker threads, plan state, and sidebar coordination.

    Owns the AIOrchestrator, CodeWorker lifecycle, plan step tracking,
    retry/defer logic, and mode switching. Emits signals so the UI layer
    can react without tight coupling.
    """

    plan_changed = Signal()          # emitted when plan steps are added/removed
    worker_started = Signal(str)     # status text
    worker_finished = Signal()       # all done
    stream_received = Signal(str, str)  # text, type
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.orch = AIOrchestrator()
        self._worker_thread = None
        self._code_worker = None
        self._launching = False
        self._worker_gen = 0
        self._deferred = None
        self._defer_attempts = 0
        self._closed = False

        # Plan state
        self._plan_steps: list = []
        self._plan_step_idx = 0
        self._plan_paused = False
        self._completed_steps: list = []
        self._replan_per_step = False
        self._pending_input = ""
        self._pending_msgs = None

        # Deep think
        self._deep_think = False
        self._chief_step_count = 0
        self._retries = 0
        self._step_retry_state = None
        self._abandoned = False

        self._mode = "build"

    # ── Worker lifecycle ──────────────────────────────────────

    def launch_worker(self, api_msgs, user_input, use_chief=False):
        if self._closed:
            return False
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
            mid_plan = bool(self._plan_steps) and self._plan_step_idx < len(self._plan_steps)
            self._code_worker = CodeWorker(
                self.orch, api_msgs, user_input,
                mid_plan=mid_plan, gen=gen, use_chief=use_chief
            )
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
            self._launching = False
        except Exception:
            self._launching = False
            return False
        self._worker_thread.start()
        return True

    def stop(self):
        if self._code_worker:
            try:
                self._code_worker.cancel()
            except RuntimeError:
                pass
        if self._worker_thread:
            try:
                self._worker_thread.quit()
                self._worker_thread.wait(300)
            except RuntimeError:
                pass
            self._worker_thread = None
            self._code_worker = None

    def _cleanup_dead_worker_refs(self):
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
        if self._worker_thread is None:
            return False
        try:
            return self._worker_thread.isRunning()
        except RuntimeError:
            self._worker_thread = None
            self._code_worker = None
            return False

    def _on_worker_thread_finished(self, thread_obj):
        if self._worker_thread is thread_obj:
            self._worker_thread = None
            self._code_worker = None

    # ── Signal handlers (override in subclass or connect) ─────

    def _on_token(self, text, typ):
        pass

    def _on_code_ready(self, raw_text, code, used_api, gen=0):
        pass

    def _on_worker_err(self, e, gen=0):
        pass

    def _on_stream(self, text, typ):
        self.stream_received.emit(text, typ)

    # ── Deferred execution ────────────────────────────────────

    MAX_DEFER_ATTEMPTS = 15

    def defer(self, action, *args):
        if self._closed:
            return
        if self._deferred is not None:
            return
        self._deferred = (action, args)
        self._defer_attempts = 0
        delay_ms = 2000 if action == "next_step" else 25
        QtCore.QTimer.singleShot(delay_ms, self._flush_deferred)

    def _flush_deferred(self):
        if self._closed:
            return
        action_args = self._deferred
        self._deferred = None
        if action_args is None:
            return
        action, args = action_args
        self._defer_attempts += 1
        if self._defer_attempts > self.MAX_DEFER_ATTEMPTS:
            self._deferred = None
            self._launching = False
            return
        launched = False
        if action == "next_step":
            launched = self._request_next_step(*args)
        elif action == "retry":
            launched = self.launch_worker(*args)
        elif action == "replan":
            launched = self._request_next_plan_step(*args)
        if not launched:
            self._deferred = (action, args)
            QtCore.QTimer.singleShot(25, self._flush_deferred)

    # ── Plan management ───────────────────────────────────────

    def _request_next_step(self, observation_prelim):
        if self._closed:
            return False
        self._assert_step_invariant()
        if 0 <= self._plan_step_idx < len(self._plan_steps):
            self._plan_steps[self._plan_step_idx].start()
            self._plan_steps[self._plan_step_idx].touched_labels = []
            self.plan_changed.emit()
        step_idx = self._plan_step_idx
        fresh_context = self.orch.get_document_context()
        diff_result = self.orch.capture_structured_diff()
        diff_str = self.orch.format_diff(diff_result)
        full_obs = self.orch.capture_observation()
        msgs = self.orch.build_step_prompt(
            self._pending_input, self._plan_steps, step_idx,
            full_obs, fresh_context,
            prior_observation=observation_prelim,
            diff_summary=diff_str
        )
        self._pending_msgs = msgs
        self.worker_started.emit(f"Step {step_idx+1}/{len(self._plan_steps)}")
        return self.launch_worker(msgs, self._pending_input)

    def _request_next_plan_step(self, observation_prelim, last_message):
        if self._closed:
            return False
        self._assert_step_invariant()
        self._chief_step_count += 1
        if self._chief_step_count > 5:
            self._pending_input = ""
            self._plan_steps = []
            return True
        if self._plan_steps and 0 <= self._plan_step_idx < len(self._plan_steps):
            finished = self._plan_steps[self._plan_step_idx]
            finished.finish(success=True, summary=observation_prelim or last_message)
            self._completed_steps.append(finished)
        self._plan_steps = []
        self._plan_step_idx = 0
        self._assert_step_invariant()
        if self._task_appears_complete():
            self._finish()
            return True
        full_input = (
            f"COMPLETED:\n"
            f"  {self._completed_steps[-1].title} \u2192 {last_message[:200]}\n\n"
            f"ORIGINAL REQUEST: {self._pending_input}"
        )
        msgs = self.orch.build_messages(full_input, mode="plan", completed_steps=self._completed_steps)
        self._pending_msgs = msgs
        self._mode = "deepthink"
        self.worker_started.emit(f"Step {len(self._completed_steps) + 1}")
        return self.launch_worker(msgs, full_input, use_chief=True)

    def finish(self, keep_plan=False):
        self._deferred = None
        self._retries = 0
        self._step_retry_state = None
        if not keep_plan:
            self._pending_input = ""
            self._pending_msgs = None
            self._plan_paused = False
            self._plan_steps = []
            self._plan_step_idx = 0
        self.worker_finished.emit()

    # ── Helpers ───────────────────────────────────────────────

    def _assert_step_invariant(self):
        active_ids = {id(s): s for s in self._plan_steps}
        completed_ids = {id(s): s for s in self._completed_steps}
        overlap_ids = set(active_ids) & set(completed_ids)
        if overlap_ids:
            overlap_titles = [active_ids[oid].title[:50] for oid in overlap_ids]
            FreeCAD.Console.PrintWarning(
                f"[Coordinator] Step invariant violated: {len(overlap_ids)} step(s) "
                f"appear in both _plan_steps (n={len(self._plan_steps)}) and "
                f"_completed_steps (n={len(self._completed_steps)}). "
                f"Titles: {overlap_titles}\n"
            )
            self._plan_steps = [s for s in self._plan_steps if id(s) not in overlap_ids]

    def _task_appears_complete(self):
        type_counts = self._count_objects_by_type()
        if not type_counts:
            return False
        body_count = type_counts.get("PartDesign::Body", 0)
        if body_count > 1:
            return False
        for tid in ("PartDesign::Pad", "PartDesign::Pocket", "PartDesign::Fillet", "PartDesign::Chamfer"):
            if type_counts.get(tid, 0) > 2:
                return False
        return True

    def _count_objects_by_type(self):
        counts = {}
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return counts
        for o in doc.Objects:
            try:
                tid = getattr(o, "TypeId", "") or ""
                counts[tid] = counts.get(tid, 0) + 1
            except Exception:
                continue
        return counts

    @property
    def plan_steps(self):
        return self._plan_steps

    @plan_steps.setter
    def plan_steps(self, value):
        self._plan_steps = value
        self.plan_changed.emit()

    @property
    def plan_step_idx(self):
        return self._plan_step_idx

    @plan_step_idx.setter
    def plan_step_idx(self, value):
        self._plan_step_idx = value
        self.plan_changed.emit()

    @property
    def plan_paused(self):
        return self._plan_paused

    @plan_paused.setter
    def plan_paused(self, value):
        self._plan_paused = value

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        self._mode = value
