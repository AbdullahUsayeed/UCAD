"""AICompanion orchestrator package — re-exports all public names."""

__version__ = "1.0.0"
VERSION = __version__

from .knowledge import FREECAD_KNOWLEDGE
from .local_pipeline import (LOCAL_SYSTEM_PROMPT,
    LOCAL_GEAR, LOCAL_AIRFOIL, LOCAL_TRIANGLE, LOCAL_CURVEDSHAPES, LOCAL_ADDFC,
    is_local_provider, build_messages_local, generate_code_local, call_ollama,
    extract_code_blocks, strip_think_blocks)

from .errors import (ERROR_TRANSLATIONS, ERROR_STRATEGIES, ErrorReport,
                     _ERROR_CATALOGUE, translate_error, deep_extract_freecad_error,
                     _extract_error_location, build_error_report, build_retry_prompt,
                     _highlight_bad_lines, _fallback_strategy_for_category)

from .providers import (PROVIDERS, PROVIDER_CONFIGS, PROVIDER_TUNING, PROVIDER_HELP_URLS,
                        _provider_max_retries, _provider_style_hint,
                        LiteLLMAdapter, PROVIDER_ADAPTERS, LITELLM_PROVIDERS, PRESET_MODELS,
                        MAX_RETRIES, VISION_CAPABLE, MODES,
                        fetch_available_models,
                        ModelRegistry, resolve_default_model)

from .templates import TEMPLATES, TEMPLATE_SCHEMAS, render_template

from .security import (_PRELOADED_MODULES, _safe_import, SAFE_BUILTINS,
                       _SANDBOX_ESCAPE_PATTERNS, _validate_exec_code)

from .observation import SmartObserver, PromptComposer

from .executor import (StepResult, PlanExecutor, _DeltaCResult, _CadDagStub,
                       FAILURE_MODES, classify_failure, summarize_failures,
                       ExecutionContext)

from .airfoil_knowledge import AIRFOIL_KNOWLEDGE, should_inject_airfoil
from .gear_knowledge import GEAR_KNOWLEDGE, should_inject_gear
from .triangle_knowledge import TRIANGLE_KNOWLEDGE, should_inject_triangle
from .curvedshapes_knowledge import CURVEDSHAPES_KNOWLEDGE, CURVEDSHAPES_WING_BRIDGE, should_inject_curvedshapes
from .addfc_knowledge import ADDFC_KNOWLEDGE, should_inject_addfc

from .core import AIOrchestrator


__all__ = [
    # knowledge
    "FREECAD_KNOWLEDGE",
    # local pipeline
    "LOCAL_SYSTEM_PROMPT", "LOCAL_GEAR", "LOCAL_AIRFOIL", "LOCAL_TRIANGLE",
    "LOCAL_CURVEDSHAPES", "LOCAL_ADDFC", "is_local_provider",
    "build_messages_local", "generate_code_local", "call_ollama",
    "extract_code_blocks", "strip_think_blocks",
    # errors
    "ERROR_TRANSLATIONS", "ERROR_STRATEGIES", "ErrorReport",
    "_ERROR_CATALOGUE", "translate_error", "deep_extract_freecad_error",
    "_extract_error_location", "build_error_report", "build_retry_prompt",
    "_highlight_bad_lines", "_fallback_strategy_for_category",
    # providers
    "PROVIDERS", "PROVIDER_TUNING", "PROVIDER_HELP_URLS",
    "_provider_max_retries", "_provider_style_hint",
    "LiteLLMAdapter", "PROVIDER_ADAPTERS",
    "LITELLM_PROVIDERS", "PRESET_MODELS", "MAX_RETRIES", "VISION_CAPABLE", "MODES",
    "fetch_available_models", "ModelRegistry", "resolve_default_model",
    # templates
    "TEMPLATES", "TEMPLATE_SCHEMAS", "render_template",
    # security
    "_PRELOADED_MODULES", "_safe_import", "SAFE_BUILTINS",
    "_SANDBOX_ESCAPE_PATTERNS", "_validate_exec_code",
    # observation
    "SmartObserver", "PromptComposer",
    # executor
    "StepResult", "PlanExecutor", "_DeltaCResult", "_CadDagStub",
    "FAILURE_MODES", "classify_failure", "summarize_failures",
    "ExecutionContext",
    # core
    "AIOrchestrator",
    # airfoil knowledge
    "AIRFOIL_KNOWLEDGE", "should_inject_airfoil",
    # gear knowledge
    "GEAR_KNOWLEDGE", "should_inject_gear",
    # triangle knowledge
    "TRIANGLE_KNOWLEDGE", "should_inject_triangle",
    # curved shapes knowledge
    "CURVEDSHAPES_KNOWLEDGE", "CURVEDSHAPES_WING_BRIDGE", "should_inject_curvedshapes",
    # addFC knowledge
    "ADDFC_KNOWLEDGE", "should_inject_addfc",
]
