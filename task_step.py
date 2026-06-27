"""TaskStep state model for plan tracking — replaces parallel _plan_steps/_completed_steps."""
import time
from enum import Enum


class StepState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def icon(self):
        return {
            StepState.PENDING: "⬜",
            StepState.RUNNING: "⏳",
            StepState.DONE: "✅",
            StepState.FAILED: "❌",
            StepState.CANCELLED: "⊘",
        }.get(self, "⬜")

    @property
    def label(self):
        return self.value.capitalize()


class TaskStep:
    def __init__(self, title, step_id=None):
        self.id = step_id or str(int(time.time() * 1000))
        self.title = title
        self.state = StepState.PENDING
        self.retries_used = 0
        self.started_at = None
        self.finished_at = None
        self.summary = ""
        self.code = ""
        self.error = ""
        self.detail_log = []
        self.touched_labels: list[str] = []
        self.failure_modes: list[str] = []
        self.escalated = False

    def start(self):
        # Guard: don't reset a finished step back to RUNNING — that would
        # double-execute work and lose the finished_at timestamp
        if self.state in (StepState.DONE, StepState.FAILED, StepState.CANCELLED):
            return
        self.state = StepState.RUNNING
        self.started_at = time.time()
        self.detail_log.append({"msg": "Started", "level": "info", "ts": time.time()})

    def finish(self, success, summary="", code=""):
        # Guard: don't overwrite a finished step — protects against double-finish
        # from race conditions (success path + backtrack path firing in the same cycle)
        if self.state in (StepState.DONE, StepState.FAILED, StepState.CANCELLED):
            return
        self.state = StepState.DONE if success else StepState.FAILED
        self.finished_at = time.time()
        self.summary = summary
        if code:
            self.code = code
        level = "success" if success else "error"
        self.detail_log.append({"msg": summary or ("OK" if success else "Failed"), "level": level, "ts": self.finished_at})

    def record_failure(self, mode: str):
        self.failure_modes.append(mode)

    @property
    def should_escalate(self) -> bool:
        return len(self.failure_modes) >= 3

    def add_retry(self, error_msg=""):
        self.retries_used += 1
        self.detail_log.append({"msg": f"Retry {self.retries_used}: {error_msg[:200]}", "level": "retry", "ts": time.time()})

    def cancel(self):
        self.state = StepState.CANCELLED
        self.finished_at = time.time()
        self.detail_log.append({"msg": "Cancelled", "level": "info", "ts": time.time()})

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "state": self.state.value,
            "retries_used": self.retries_used,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "code": self.code,
            "error": self.error,
            "detail_log": self.detail_log[-50:],
            "touched_labels": self.touched_labels,
        }

    def __repr__(self):
        return f"<TaskStep {self.id[:8]}[{self.state.value}] '{self.title[:40]}'>"
