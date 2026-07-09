"""AI provider definitions — LiteLLM unified adapter for all providers."""

import json, os, sys, time
import FreeCAD

# ── Provider default model strings (LiteLLM format: "provider_prefix/model_name") ──

PROVIDERS = {
    "deepseek":   "deepseek/deepseek-v4-flash",
    "openai":     "openai/gpt-4o-mini",
    "ollama":     "ollama/llama3",
    "anthropic":  "anthropic/claude-sonnet-5",
    "google":     "gemini/gemini-2.5-pro-exp-03-25",
    "xai":        "xai/grok-2",
    "mistral":    "mistral/mistral-large-2501",
    "cohere":     "cohere/command-r-plus",
    "perplexity": "perplexity/sonar-pro",
    "groq":       "groq/llama-3.3-70b-versatile",
    "openrouter": "openrouter/openrouter/auto",
    "together":   "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "fireworks":  "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct",
    "github":     "github/gpt-4o",
    "moonshot":   "moonshot/moonshot-v1-8k",
}

_PROVIDER_NAMES = {
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "ollama": "Ollama (Local)",
    "anthropic": "Anthropic",
    "google": "Google",
    "xai": "xAI",
    "mistral": "Mistral",
    "cohere": "Cohere",
    "perplexity": "Perplexity",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "together": "Together",
    "fireworks": "Fireworks",
    "github": "GitHub Models",
    "moonshot": "Moonshot (Kimi)",
    "templates": "Templates",
}

PROVIDER_HELP_URLS = {
    "openai": "https://platform.openai.com/api-keys",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "anthropic": "https://console.anthropic.com/settings/keys",
    "google": "https://aistudio.google.com/app/apikey",
    "xai": "https://console.x.ai/",
    "mistral": "https://console.mistral.ai/api-keys/",
    "cohere": "https://dashboard.cohere.com/api-keys",
    "perplexity": "https://www.perplexity.ai/settings/api",
    "groq": "https://console.groq.com/keys",
    "openrouter": "https://openrouter.ai/keys",
    "together": "https://api.together.xyz/settings/api-keys",
    "fireworks": "https://app.fireworks.ai/settings/users/api-keys",
    "github": "https://github.com/settings/tokens",
    "moonshot": "https://platform.moonshot.cn/console/api-keys",
}

PROVIDER_TUNING = {
    "deepseek":   {"max_retries": 5, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "openai":     {"max_retries": 5, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "ollama":     {"max_retries": 8, "style_hint": "Be extra careful with ``` fence formatting \u2014 output the closing ``` on its own line.", "max_tokens": None, "temperature": 0.2},
    "anthropic":  {"max_retries": 5, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.5},
    "google":     {"max_retries": 5, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "xai":        {"max_retries": 6, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "mistral":    {"max_retries": 6, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "cohere":     {"max_retries": 6, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.3},
    "perplexity": {"max_retries": 6, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "groq":       {"max_retries": 6, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "openrouter": {"max_retries": 5, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "together":   {"max_retries": 6, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "fireworks":  {"max_retries": 6, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "github":     {"max_retries": 5, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
    "moonshot":   {"max_retries": 5, "style_hint": "",                              "max_tokens": 16384, "temperature": 0.7},
}

_DEFAULT_TUNING = {"max_retries": 5, "style_hint": "", "max_tokens": 16384, "temperature": 0.7}

LITELLM_PROVIDERS = {k for k in PROVIDERS if k != "templates"}


def _provider_tuning(provider):
    return PROVIDER_TUNING.get(provider, _DEFAULT_TUNING)


def _provider_max_retries(provider):
    return _provider_tuning(provider)["max_retries"]


def _provider_style_hint(provider):
    return _provider_tuning(provider)["style_hint"]


def _provider_max_tokens(provider):
    return _provider_tuning(provider)["max_tokens"]


def _provider_temperature(provider):
    return _provider_tuning(provider)["temperature"]


# ── OpenAI-compatible endpoints for direct HTTP calls ────────────────

_OPENAI_COMPATIBLE = {
    "deepseek", "openai", "xai", "mistral", "cohere",
    "perplexity", "groq", "openrouter", "together", "fireworks", "github",
}

_OPENAI_ENDPOINTS = {
    "deepseek":   "https://api.deepseek.com/chat/completions",
    "openai":     "https://api.openai.com/v1/chat/completions",
    "xai":        "https://api.x.ai/v1/chat/completions",
    "mistral":    "https://api.mistral.ai/v1/chat/completions",
    "cohere":     "https://api.cohere.com/v1/chat/completions",
    "perplexity": "https://api.perplexity.ai/chat/completions",
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "together":   "https://api.together.xyz/v1/chat/completions",
    "fireworks":  "https://api.fireworks.ai/inference/v1/chat/completions",
    "github":     "https://models.inference.ai.azure.com/chat/completions",
}


def _resolve_endpoint(provider, api_url):
    if api_url:
        raw = api_url.rstrip("/")
        if not raw.endswith("/chat/completions"):
            raw += "/chat/completions"
        return raw
    return _OPENAI_ENDPOINTS.get(provider, "")


def _direct_completion(model, messages, api_key, api_url=None,
                       max_tokens=None, temperature=None,
                       stream=False, on_token=None):
    import urllib.request, json, ssl
    provider = model.split("/")[0] if "/" in model else ""
    endpoint = _resolve_endpoint(provider, api_url)
    if not endpoint:
        raise ValueError(f"No endpoint for {model}")

    model_name = model.split("/", 1)[-1] if "/" in model else model
    body = {"model": model_name, "messages": messages}
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    if stream:
        body["stream"] = True

    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        endpoint, data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    ctx = ssl.create_default_context()
    if not stream:
        resp = urllib.request.urlopen(req, timeout=120, context=ctx)
        data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"] or ""

    # Streaming via SSE
    resp = urllib.request.urlopen(req, timeout=120, context=ctx)
    full_text = ""
    try:
        while True:
            line = resp.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text or text == "data: [DONE]":
                continue
            if text.startswith("data: "):
                chunk = json.loads(text[6:])
                choices = chunk.get("choices") or []
                for c in choices:
                    delta = c.get("delta") or {}
                    content = delta.get("content") or ""
                    reasoning = delta.get("reasoning_content") or ""
                    if reasoning and on_token:
                        on_token(reasoning, "reasoning")
                    if content:
                        full_text += content
                        if on_token:
                            on_token(content, "content")
    except Exception as ex:
        if on_token:
            on_token(str(ex), "error")
        raise
    if on_token:
        on_token("", "done")
    return full_text


# ── Per-provider configs for model discovery ─────────────────────
# Each entry defines:
#   models_url  — full URL to the models endpoint (used as-is when no api_url override)
#   auth_header — callable(api_key) → dict of headers (empty dict if api_key is empty)
#   env_key     — env var name to check for a configured key (None = not needed)
#   models_path — alternative path suffix for deriving URL from api_url (default /v1/models)

PROVIDER_CONFIGS: dict = {
    "anthropic": {
        "models_url": "https://api.anthropic.com/v1/models",
        "auth_header": lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"} if key else {},
        "env_key": "ANTHROPIC_API_KEY",
        "models_path": "/v1/models",
    },
    "openai": {
        "models_url": "https://api.openai.com/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "OPENAI_API_KEY",
        "models_path": "/v1/models",
    },
    "deepseek": {
        "models_url": "https://api.deepseek.com/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "DEEPSEEK_API_KEY",
        "models_path": "/v1/models",
    },
    "google": {
        "models_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "auth_header": lambda key: {"x-goog-api-key": key} if key else {},
        "env_key": "GEMINI_API_KEY",
        "models_path": "/models",
    },
    "xai": {
        "models_url": "https://api.x.ai/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "XAI_API_KEY",
        "models_path": "/v1/models",
    },
    "mistral": {
        "models_url": "https://api.mistral.ai/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "MISTRAL_API_KEY",
        "models_path": "/v1/models",
    },
    "cohere": {
        "models_url": "https://api.cohere.com/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "COHERE_API_KEY",
        "models_path": "/v1/models",
    },
    "perplexity": {
        "models_url": "https://api.perplexity.ai/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "PERPLEXITY_API_KEY",
        "models_path": "/v1/models",
    },
    "groq": {
        "models_url": "https://api.groq.com/openai/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "GROQ_API_KEY",
        "models_path": "/v1/models",
    },
    "openrouter": {
        "models_url": "https://openrouter.ai/api/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "OPENROUTER_API_KEY",
        "models_path": "/v1/models",
    },
    "together": {
        "models_url": "https://api.together.xyz/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "TOGETHER_API_KEY",
        "models_path": "/v1/models",
    },
    "fireworks": {
        "models_url": "https://api.fireworks.ai/inference/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "FIREWORKS_API_KEY",
        "models_path": "/v1/models",
    },
    "github": {
        "models_url": "https://models.inference.ai.azure.com/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "GITHUB_API_KEY",
        "models_path": "/v1/models",
    },
    # Moonshot/Kimi — OpenAI-compatible, not yet in LiteLLM by default
    "moonshot": {
        "models_url": "https://api.moonshot.cn/v1/models",
        "auth_header": lambda key: {"Authorization": f"Bearer {key}"} if key else {},
        "env_key": "MOONSHOT_API_KEY",
        "models_path": "/v1/models",
    },
}

# Static fallbacks for providers whose /models endpoint is unreliable or gated
_MODEL_FALLBACKS: dict = {
    "ollama": ["llama3.1:8b", "llama3:8b", "mistral", "codellama", "deepseek-coder:7b"],
    "openrouter": [],  # OpenRouter routes by model ID, no fixed list
}

# ── Model Registry — live discovery + caching ─────────────────────

_MODEL_CACHE_TTL = 3600
_model_cache = {}  # {provider: {"models": [str], "ts": float}}

_MODEL_FAMILIES = {
    "anthropic": ["claude-sonnet", "claude-opus", "claude-haiku", "claude-fable", "claude"],
    "openai":     ["gpt-4o", "gpt-4", "o4", "o3", "o1", "gpt-3.5"],
    "deepseek":   ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4", "deepseek-r1-0528"],
    "google":     ["gemini-2.5", "gemini-2.0", "gemini-1.5"],
    "xai":        ["grok-3", "grok-2"],
    "mistral":    ["mistral-large", "codestral", "mistral-small", "open-mistral", "ministral"],
    "cohere":     ["command-r", "command-a", "command"],
    "perplexity": ["sonar"],
    "groq":       ["llama", "mixtral", "gemma", "qwen", "deepseek"],
    "together":   ["Meta-Llama", "DeepSeek", "Qwen"],
    "fireworks":  ["llama", "deepseek", "mixtral", "qwen"],
    "github":     ["gpt-4o", "gpt-4", "o3", "o4", "deepseek", "claude", "gemini", "mistral"],
    "moonshot":   ["moonshot-v1"],
}

_VISION_PREFIXES = {
    "anthropic": ["claude-sonnet", "claude-opus", "claude-fable"],
    "openai":    ["gpt-4o", "gpt-4.1", "o1", "o3", "o4"],
    "google":    ["gemini-2.5", "gemini-2.0"],
}


class ModelRegistry:
    """Live model discovery, ranking, and caching.

    Provider-agnostic — every provider gets a config entry in
    :data:`PROVIDER_CONFIGS` and discovery just looks it up.

    Usage::

        models = ModelRegistry.discover("anthropic", api_key="...")
        best = ModelRegistry.pick_best(models, "anthropic")
    """

    # ── configuration / key detection ─────────────────────────────

    @staticmethod
    def get_config(provider: str) -> dict | None:
        """Return the PROVIDER_CONFIGS entry for *provider*, or None."""
        return PROVIDER_CONFIGS.get(provider)

    @staticmethod
    def is_configured(provider: str, api_key: str = "") -> bool:
        """Return True if *provider* has a usable API key available.

        Checks the explicit *api_key* argument first, then the configured
        environment variable.  Local providers (ollama) always return True.
        """
        if provider == "ollama":
            return True
        if api_key:
            return True
        cfg = PROVIDER_CONFIGS.get(provider)
        if cfg and cfg.get("env_key"):
            return bool(os.environ.get(cfg["env_key"]))
        return False

    # ── discovery + caching ───────────────────────────────────────

    @staticmethod
    def discover(
        provider: str,
        api_key: str = "",
        api_url: str = "",
    ) -> list[str]:
        """Return available model *IDs* (no provider prefix) for *provider*.

        Results are cached for ``_MODEL_CACHE_TTL`` seconds.
        On failure returns stale cache or static fallback list.
        """
        now = time.time()
        cached = _model_cache.get(provider)
        if cached and now - cached["ts"] < _MODEL_CACHE_TTL:
            return cached["models"]

        try:
            models = ModelRegistry._fetch(provider, api_key, api_url)
            if models:
                _model_cache[provider] = {"models": models, "ts": now}
            return models
        except Exception:
            if cached:
                return cached["models"]
            return list(_MODEL_FALLBACKS.get(provider, []))

    @staticmethod
    def _fetch(provider: str, api_key: str, api_url: str) -> list[str]:
        import urllib.request, urllib.error, json, ssl

        # ── local Ollama ──────────────────────────────────────
        if provider == "ollama":
            ctx = ssl.create_default_context()
            base = api_url.rstrip("/") if api_url else "http://localhost:11434"
            req = urllib.request.Request(base + "/api/tags")
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode())
            return [m["name"] for m in data.get("models", []) if m.get("name")]

        # ── remote providers ──────────────────────────────────
        cfg = PROVIDER_CONFIGS.get(provider)
        if not cfg:
            return []

        # Resolve URL: prefer api_url override, else use configured models_url
        if api_url:
            base = api_url.rstrip("/")
            # Strip known path suffixes so the models path can be appended cleanly
            for suffix in ["/v1/messages", "/v1/chat/completions", "/chat/completions", "/v1"]:
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            url = base + cfg.get("models_path", "/v1/models")
        else:
            url = cfg["models_url"]

        # Guard: avoid double /v1/ when base already ends with it
        if "/v1/v1/" in url:
            url = url.replace("/v1/v1/", "/v1/")

        # Build headers
        headers = dict(cfg["auth_header"](api_key))  # type: ignore[arg-type]

        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode())

        return [m["id"] for m in data.get("data", []) if m.get("id")]

    # ── model selection ───────────────────────────────────────────

    @staticmethod
    def pick_best(
        models: list[str],
        provider: str,
        family_hint: str = "",
    ) -> str | None:
        """Return the most capable available model ID for *provider*.

        Picks the first matching family from ``_MODEL_FAMILIES[provider]``
        and returns the alphabetically-last (newest) ID in that family.
        """
        if not models:
            return None

        families = _MODEL_FAMILIES.get(provider, [])
        if family_hint:
            families = [family_hint] + [f for f in families if f != family_hint]

        for prefix in families:
            candidates = [m for m in models if m.startswith(prefix)]
            if candidates:
                candidates.sort(reverse=True)
                return candidates[0]

        return models[0]

    @staticmethod
    def default_model(
        provider: str,
        api_key: str = "",
        api_url: str = "",
        fallback: str = "",
    ) -> str:
        """Return the LiteLLM-format default model string for *provider*.

        Uses live discovery then ``pick_best``. Falls back to *fallback*
        or the static ``PROVIDERS`` entry if discovery fails.
        """
        models = ModelRegistry.discover(provider, api_key, api_url)
        if models:
            best = ModelRegistry.pick_best(models, provider)
            if best:
                return f"{provider}/{best}"
        if fallback:
            return fallback
        return PROVIDERS.get(provider, "")

    @staticmethod
    def is_vision_capable(model_id: str) -> bool:
        """Return True if *model_id* likely supports image inputs."""
        for prefix_list in _VISION_PREFIXES.values():
            for p in prefix_list:
                if model_id.startswith(p):
                    return True
        return False

    @staticmethod
    def validate_presets(provider: str, preset_keys: list[str]) -> list[str]:
        """Return warning messages for preset model IDs that are unavailable."""
        models = _model_cache.get(provider, {}).get("models", [])
        if not models:
            return []
        warnings = []
        for full_id in preset_keys:
            raw = full_id.split("/", 1)[-1] if "/" in full_id else full_id
            if raw not in models:
                warnings.append(
                    f"[AI] Preset model '{full_id}' is not in the live model list "
                    f"for '{provider}'. Available: {', '.join(models[:6])}..."
                )
        return warnings


def resolve_default_model(
    provider: str,
    api_key: str = "",
    api_url: str = "",
) -> str:
    """Convenience wrapper — :func:`ModelRegistry.default_model`."""
    return ModelRegistry.default_model(provider, api_key, api_url)


# ── Adapters ───────────────────────────────────────────────────────


class DirectAdapter:
    """HTTP adapter for OpenAI-compatible providers — uses urllib directly,
    bypassing LiteLLM/httpx entirely. Supports both streaming and non-streaming."""

    def completion(self, model, messages, api_key=None, api_url=None,
                   stream=False, on_token=None, max_tokens=None,
                   temperature=None, proxy_url=None) -> str | None:
        try:
            FreeCAD.Console.PrintLog(
                f"[AIC] DirectAdapter.completion ENTERED: model={model} "
                f"msgs={len(messages) if messages else 0} key={'SET' if api_key else 'NONE'}\n"
            )
        except Exception:
            pass
        try:
            provider = model.split("/")[0] if "/" in model else ""
            ep = _resolve_endpoint(provider, api_url) or "(none)"
            FreeCAD.Console.PrintMessage(
                f"[AI] Direct: {model} → {ep}\n"
            )
            FreeCAD.Console.PrintLog(
                f"[AI] Direct {model}: "
                f"api_key={'<SET>' if api_key else '<EMPTY>'} "
                f"(prefix={api_key[:7] if api_key else 'N/A'}...)\n"
            )
            return _direct_completion(
                model, messages, api_key=api_key, api_url=api_url,
                max_tokens=max_tokens, temperature=temperature,
                stream=stream, on_token=on_token,
            )
        except Exception:
            import traceback
            FreeCAD.Console.PrintError(
                f"[AI] Direct call failed:\n{traceback.format_exc()}\n"
            )
            raise


class LiteLLMAdapter:
    """Adapter for providers that require LiteLLM (Anthropic, Google, Ollama)."""

    def completion(self, model, messages, api_key=None, api_url=None,
                   stream=False, on_token=None, max_tokens=None,
                   temperature=None, proxy_url=None) -> str | None:
        try:
            import FreeCAD as _fc
            _fc.Console.PrintLog(
                f"[AIC] LiteLLMAdapter.completion ENTERED: model={model} "
                f"msgs={len(messages) if messages else 0} key={'SET' if api_key else 'NONE'}\n"
            )
        except Exception:
            pass
        try:
            import litellm
        except ImportError:
            raise ImportError(
                "LiteLLM package is required for this provider.\n"
                "Run: & \"C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe\" -m pip install litellm\n"
                "Or reinstall the AI Companion addon via Addon Manager."
            )
        litellm.ssl_verify = False
        proxy = proxy_url
        if not proxy:
            for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
                val = os.environ.get(var)
                if val:
                    proxy = val
                    break
        if proxy:
            litellm.proxy = proxy
        kwargs = {"model": model, "messages": messages, "stream": stream}
        # Anthropic requires explicit api_base and version header — LiteLLM's
        # defaults can be overridden by env vars or lost in the handler chain.
        if model.startswith("anthropic/"):
            kwargs["api_base"] = "https://api.anthropic.com/v1/messages"
            kwargs.setdefault("headers", {})["anthropic-version"] = "2023-06-01"
        if api_key:
            kwargs["api_key"] = api_key
            FreeCAD.Console.PrintLog(
                f"[AI] {model}: api_key={'<SET>' if api_key else '<EMPTY>'} "
                f"(prefix={api_key[:7]}...)\n"
            )
        else:
            FreeCAD.Console.PrintLog(f"[AI] {model}: api_key=<NOT PROVIDED>\n")
        if api_url:
            kwargs["api_base"] = api_url
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            if not stream:
                resp = litellm.completion(**kwargs)
                return resp.choices[0].message.content or ""

            response = litellm.completion(**kwargs)
            full_text = ""
            try:
                for chunk in response:
                    if not hasattr(chunk, 'choices') or not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    reasoning = getattr(delta, 'reasoning_content', None) or ''
                    content = getattr(delta, 'content', None) or ''
                    if reasoning and on_token:
                        on_token(reasoning, "reasoning")
                    if content:
                        full_text += content
                        if on_token:
                            on_token(content, "content")
            except Exception as ex:
                if on_token:
                    on_token(str(ex), "error")
                raise
            if on_token:
                on_token("", "done")
            return full_text
        except Exception:
            import traceback
            FreeCAD.Console.PrintError(
                f"[AI] LiteLLM call failed:\n{traceback.format_exc()}\n"
            )
            raise


LITELLM_ONLY_PROVIDERS = {"anthropic", "google", "ollama"}

PROVIDER_ADAPTERS = {}
for p in LITELLM_PROVIDERS:
    PROVIDER_ADAPTERS[p] = LiteLLMAdapter() if p in LITELLM_ONLY_PROVIDERS else DirectAdapter()


# ── Model presets for UI ───────────────────────────────────────────────

PRESET_MODELS = [
    # OpenAI
    ("[OpenAI] GPT-4.1", "openai", "openai/gpt-4.1-2025-04-14"),
    ("[OpenAI] GPT-4.1 Nano", "openai", "openai/gpt-4.1-nano-2025-04-14"),
    ("[OpenAI] GPT-4.1 Mini", "openai", "openai/gpt-4.1-mini-2025-04-14"),
    ("[OpenAI] GPT-4o", "openai", "openai/gpt-4o-2024-11-20"),
    ("[OpenAI] GPT-4o Mini", "openai", "openai/gpt-4o-mini"),
    ("[OpenAI] o1", "openai", "openai/o1-2024-12-17"),
    ("[OpenAI] o1-mini", "openai", "openai/o1-mini"),
    ("[OpenAI] o1-pro", "openai", "openai/o1-pro"),
    ("[OpenAI] o3-mini", "openai", "openai/o3-mini-2025-01-31"),
    ("[OpenAI] o4-mini", "openai", "openai/o4-mini"),
    ("[OpenAI] o4-mini-high", "openai", "openai/o4-mini-high"),
    ("[OpenAI] GPT-4 Turbo", "openai", "openai/gpt-4-turbo"),
    ("[OpenAI] GPT-4", "openai", "openai/gpt-4"),
    ("[OpenAI] GPT-3.5 Turbo", "openai", "openai/gpt-3.5-turbo"),
    # DeepSeek
    ("[DeepSeek] V4 Flash", "deepseek", "deepseek/deepseek-v4-flash"),
    ("[DeepSeek] V4 Pro", "deepseek", "deepseek/deepseek-v4-pro"),
    # Anthropic
    ("[Anthropic] Claude Sonnet 5", "anthropic", "anthropic/claude-sonnet-5"),
    ("[Anthropic] Claude Opus 4.8", "anthropic", "anthropic/claude-opus-4-8"),
    ("[Anthropic] Claude Sonnet 4.6", "anthropic", "anthropic/claude-sonnet-4-6"),
    ("[Anthropic] Claude Opus 4.6", "anthropic", "anthropic/claude-opus-4-6"),
    ("[Anthropic] Claude Haiku 4.5", "anthropic", "anthropic/claude-haiku-4-5-20251001"),
    ("[Anthropic] Claude Sonnet 4.5", "anthropic", "anthropic/claude-sonnet-4-5-20250929"),
    ("[Anthropic] Claude Opus 4.5", "anthropic", "anthropic/claude-opus-4-5-20251101"),
    # Google
    ("[Google] Gemini 2.5 Pro", "google", "gemini/gemini-2.5-pro-exp-03-25"),
    ("[Google] Gemini 2.5 Flash", "google", "gemini/gemini-2.5-flash-preview-04-17"),
    ("[Google] Gemini 2.0 Flash", "google", "gemini/gemini-2.0-flash-exp"),
    ("[Google] Gemini 1.5 Pro", "google", "gemini/gemini-1.5-pro"),
    ("[Google] Gemini 1.5 Flash", "google", "gemini/gemini-1.5-flash"),
    # xAI
    ("[xAI] Grok 3", "xai", "xai/grok-3"),
    ("[xAI] Grok 3 Mini", "xai", "xai/grok-3-mini"),
    ("[xAI] Grok 3 Mini Fast", "xai", "xai/grok-3-mini-fast"),
    ("[xAI] Grok 3 Fast", "xai", "xai/grok-3-fast"),
    ("[xAI] Grok 2", "xai", "xai/grok-2"),
    # Mistral
    ("[Mistral] Large 2", "mistral", "mistral/mistral-large-2407"),
    ("[Mistral] Large 3", "mistral", "mistral/mistral-large-2501"),
    ("[Mistral] Codestral", "mistral", "mistral/codestral-2501"),
    ("[Mistral] Small 3", "mistral", "mistral/mistral-small-2501"),
    ("[Mistral] Small 3.1", "mistral", "mistral/mistral-small-3.1-2025-01-24"),
    ("[Mistral] Nemo", "mistral", "mistral/open-mistral-nemo"),
    ("[Mistral] Ministral 3B", "mistral", "mistral/ministral-3b-2410"),
    ("[Mistral] Ministral 8B", "mistral", "mistral/ministral-8b-2410"),
    # Cohere
    ("[Cohere] Command R+", "cohere", "cohere/command-r-plus"),
    ("[Cohere] Command R", "cohere", "cohere/command-r"),
    ("[Cohere] Command R7", "cohere", "cohere/command-r7-12-2024"),
    ("[Cohere] Command A", "cohere", "cohere/command-a-03-2025"),
    ("[Cohere] Embed English", "cohere", "cohere/embed-english-v3.0"),
    # Perplexity
    ("[Perplexity] Sonar Pro", "perplexity", "perplexity/sonar-pro"),
    ("[Perplexity] Sonar", "perplexity", "perplexity/sonar"),
    ("[Perplexity] Sonar Deep Research", "perplexity", "perplexity/sonar-deep-research"),
    ("[Perplexity] Sonar Reason Pro", "perplexity", "perplexity/sonar-reasoning-pro"),
    ("[Perplexity] Sonar Reason", "perplexity", "perplexity/sonar-reasoning"),
    # Groq
    ("[Groq] Llama 3.3 70B", "groq", "groq/llama-3.3-70b-versatile"),
    ("[Groq] Llama 3.1 8B", "groq", "groq/llama-3.1-8b-instant"),
    ("[Groq] Llama 3 70B", "groq", "groq/llama3-70b-8192"),
    ("[Groq] Llama 3 8B", "groq", "groq/llama3-8b-8192"),
    ("[Groq] DeepSeek R1 Distill Llama 70B", "groq", "groq/deepseek-r1-distill-llama-70b"),
    ("[Groq] Mixtral 8x7B", "groq", "groq/mixtral-8x7b-32768"),
    ("[Groq] Gemma 2 9B", "groq", "groq/gemma2-9b-it"),
    ("[Groq] Qwen 2.5 32B", "groq", "groq/qwen-qwq-32b"),
    # OpenRouter
    ("[OpenRouter] Auto (best model)", "openrouter", "openrouter/openrouter/auto"),
    ("[OpenRouter] Claude Opus 4", "openrouter", "openrouter/anthropic/claude-opus-4"),
    ("[OpenRouter] Claude Sonnet 4", "openrouter", "openrouter/anthropic/claude-sonnet-4"),
    ("[OpenRouter] Gemini 2.5 Pro", "openrouter", "openrouter/google/gemini-2.5-pro-exp-03-25"),
    ("[OpenRouter] GPT-4o", "openrouter", "openrouter/openai/gpt-4o"),
    ("[OpenRouter] DeepSeek V4", "openrouter", "openrouter/deepseek/deepseek-v4"),
    ("[OpenRouter] DeepSeek V4 Flash", "openrouter", "openrouter/deepseek/deepseek-v4-flash"),
    ("[OpenRouter] DeepSeek V4 Pro", "openrouter", "openrouter/deepseek/deepseek-v4-pro"),
    ("[OpenRouter] DeepSeek R1", "openrouter", "openrouter/deepseek/deepseek-r1"),
    ("[OpenRouter] Mistral Large 3", "openrouter", "openrouter/mistral/mistral-large-2501"),
    ("[OpenRouter] Qwen 2.5 72B", "openrouter", "openrouter/qwen/qwen-2.5-72b-instruct"),
    # Together
    ("[Together] Llama 3.3 70B", "together", "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ("[Together] DeepSeek R1", "together", "together_ai/deepseek-ai/DeepSeek-R1"),
    ("[Together] DeepSeek V3", "together", "together_ai/deepseek-ai/DeepSeek-V3"),
    ("[Together] Qwen 2.5 72B", "together", "together_ai/Qwen/Qwen2.5-72B-Instruct-Turbo"),
    ("[Together] Qwen 2.5 32B", "together", "together_ai/Qwen/Qwen2.5-32B-Instruct-Turbo"),
    ("[Together] Llama 3.1 8B", "together", "together_ai/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"),
    ("[Together] Llama 3.1 70B", "together", "together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"),
    ("[Together] Llama 3.1 405B", "together", "together_ai/meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo"),
    # Fireworks
    ("[Fireworks] Llama 3.3 70B", "fireworks", "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct"),
    ("[Fireworks] DeepSeek R1", "fireworks", "fireworks_ai/accounts/fireworks/models/deepseek-r1"),
    ("[Fireworks] Llama 3.1 8B", "fireworks", "fireworks_ai/accounts/fireworks/models/llama-v3p1-8b-instruct"),
    ("[Fireworks] Llama 3.1 70B", "fireworks", "fireworks_ai/accounts/fireworks/models/llama-v3p1-70b-instruct"),
    ("[Fireworks] Mixtral 8x7B", "fireworks", "fireworks_ai/accounts/fireworks/models/mixtral-8x7b-instruct"),
    ("[Fireworks] Qwen 2.5 72B", "fireworks", "fireworks_ai/accounts/fireworks/models/qwen2p5-72b-instruct"),
    # GitHub Models
    ("[GitHub] GPT-4o", "github", "github/gpt-4o"),
    ("[GitHub] GPT-4o Mini", "github", "github/gpt-4o-mini"),
    ("[GitHub] DeepSeek R1", "github", "github/deepseek-r1"),
    ("[GitHub] DeepSeek V3", "github", "github/deepseek-v3"),
    ("[GitHub] GPT-4.1", "github", "github/gpt-4.1"),
    ("[GitHub] GPT-4.1 Mini", "github", "github/gpt-4.1-mini"),
    ("[GitHub] o3-mini", "github", "github/o3-mini"),
    ("[GitHub] o4-mini", "github", "github/o4-mini"),
    ("[GitHub] Claude Sonnet 4", "github", "github/claude-sonnet-4"),
    ("[GitHub] Gemini 2.5 Pro", "github", "github/gemini-2.5-pro"),
    ("[GitHub] Gemini 2.5 Flash", "github", "github/gemini-2.5-flash"),
    ("[GitHub] Mistral Large 3", "github", "github/mistral-large-2501"),
    # Moonshot / Kimi
    ("[Moonshot] v1-8k", "moonshot", "moonshot/moonshot-v1-8k"),
    ("[Moonshot] v1-32k", "moonshot", "moonshot/moonshot-v1-32k"),
    ("[Moonshot] v1-128k", "moonshot", "moonshot/moonshot-v1-128k"),
    # Ollama
    ("[Ollama] Llama 3.3 70B (local)", "ollama", "ollama/llama3.3-70b"),
    ("[Ollama] Llama 3.1 8B (local)", "ollama", "ollama/llama3.1:8b"),
    ("[Ollama] Llama 3 8B (local)", "ollama", "ollama/llama3:8b"),
    ("[Ollama] Mistral (local)", "ollama", "ollama/mistral"),
    ("[Ollama] DeepSeek R1 (local)", "ollama", "ollama/deepseek-r1:7b"),
    ("[Ollama] CodeLlama (local)", "ollama", "ollama/codellama"),
    ("[Ollama] Qwen 2.5 (local)", "ollama", "ollama/qwen2.5"),
    ("[Ollama] Qwen 2.5 32B (local)", "ollama", "ollama/qwen2.5:32b"),
    ("[Ollama] DeepSeek Coder (local)", "ollama", "ollama/deepseek-coder"),
    ("[Ollama] Llama 3.2 3B (local)", "ollama", "ollama/llama3.2:3b"),
    ("[Ollama] Llama 3.2 1B (local)", "ollama", "ollama/llama3.2:1b"),
    ("[Ollama] Gemma 2 9B (local)", "ollama", "ollama/gemma2:9b"),
    ("[Ollama] Gemma 2 2B (local)", "ollama", "ollama/gemma2:2b"),
    ("[Ollama] Phi-3 Mini (local)", "ollama", "ollama/phi3:mini"),
    ("[Ollama] Phi-3 Medium (local)", "ollama", "ollama/phi3:medium"),
    # Templates
    ("Templates (no AI)", "templates", ""),
]

MODES = {
    "build": "Build — full autonomy: plan, code, execute, observe",
    "plan": "Plan — outputs a plan only, user confirms before execution",
    "ask": "Ask — Q&A about FreeCAD, no code execution",
    "pcb": "PCB — design enclosures from .kicad_pcb files",
    "dxf": "DXF — import 2D profiles from DXF files and build 3D geometry",
}

MAX_RETRIES = 5

VISION_CAPABLE = {
    "openai/gpt-4o", "openai/gpt-4o-2024-11-20", "openai/gpt-4o-mini",
    "openai/gpt-4.1", "openai/gpt-4.1-2025-04-14",
    "openai/o1", "openai/o1-2024-12-17", "openai/o3-mini", "openai/o3-mini-2025-01-31", "openai/o4-mini",
    "anthropic/claude-sonnet-5", "anthropic/claude-opus-4-8",
    "anthropic/claude-sonnet-4-6", "anthropic/claude-sonnet-4-5-20250929",
    "anthropic/claude-haiku-4-5-20251001",
    "gemini/gemini-2.5-pro-exp-03-25", "gemini/gemini-2.5-flash-preview-04-17",
}


def is_local_provider(provider: str, api_url: str = "") -> bool:
    """Detect whether a provider uses a local model.

    Currently returns True only when the provider is ``"ollama"``.
    Custom API URLs are ignored — the provider selection is the single
    source of truth so that users can freely set a custom URL (e.g. a
    local LiteLLM proxy) while keeping the full remote pipeline for
    providers like Anthropic or OpenAI.
    """
    return provider == "ollama"


def fetch_available_models(provider: str, api_url: str = "", api_key: str = "") -> list[str]:
    """Fetch available models from the provider in LiteLLM format.
    Returns list of LiteLLM model strings (e.g. ['ollama/llama3.1:8b', ...]).
    Falls back to empty list on any error (UI will show presets + editable field).

    Delegates to :class:`ModelRegistry` under the hood.
    """
    if provider == "ollama":
        base = api_url.rstrip("/") if api_url else "http://localhost:11434"
        url = base + "/api/tags"
        import urllib.request, ssl, json
        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode())
            return sorted(
                f"ollama/{m['name']}" for m in data.get("models", []) if m.get("name")
            )
        except Exception:
            return []

    try:
        models = ModelRegistry.discover(provider, api_key=api_key, api_url=api_url)
        return sorted(f"{provider}/{m}" for m in models)
    except Exception:
        return []
