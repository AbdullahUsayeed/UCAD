from dataclasses import dataclass, field
from typing import Optional
from task_step import TaskStep
@dataclass
class AppContext:
    sidebar: Optional[object] = None
    orchestrator: Optional[object] = None
    plan_steps: list[TaskStep] = field(default_factory=list)
    pending_input: str = ''
    mode: str = 'build'
_ctx: Optional[AppContext] = None
def get_ctx() -> AppContext:
    global _ctx
    if _ctx is None:
        _ctx = AppContext()
    return _ctx
def reset_ctx():
    global _ctx
    _ctx = None
