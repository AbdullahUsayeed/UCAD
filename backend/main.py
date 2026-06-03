"""Railway backend for AI Companion — auth, models, and provider proxy."""

import os
import json
import secrets
import hashlib
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI(title="AI Companion Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Auth config ────────────────────────────────────────────────

BACKEND_KEY = os.environ.get("BACKEND_KEY", "dev-key-change-me")
USERS_FILE = "users.json"

def _load_users():
    try:
        with open(USERS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()

def _verify_token(authorization: Optional[str] = None) -> str:
    if not authorization:
        raise HTTPException(401, "Missing Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    users = _load_users()
    for uid, data in users.items():
        if data.get("token") == token:
            return uid
    raise HTTPException(401, "Invalid or expired token")


# ── Provider config ────────────────────────────────────────────

PROVIDER_URLS = {
    "deepseek":   "https://api.deepseek.com/chat/completions",
    "openai":     "https://api.openai.com/v1/chat/completions",
    "anthropic":  "https://api.anthropic.com/v1/messages",
    "google":     "https://generativelanguage.googleapis.com/v1beta/models/",
    "xai":        "https://api.x.ai/v1/chat/completions",
    "mistral":    "https://api.mistral.ai/v1/chat/completions",
    "cohere":     "https://api.cohere.ai/v1/chat",
    "perplexity": "https://api.perplexity.ai/chat/completions",
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "together":   "https://api.together.xyz/v1/chat/completions",
    "fireworks":  "https://api.fireworks.ai/inference/v1/chat/completions",
    "github":     "https://models.inference.ai.azure.com/chat/completions",
}

OPENAI_COMPAT = {"deepseek","openai","xai","mistral","cohere","perplexity",
                 "groq","openrouter","together","fireworks","github"}


# ── Request/Response models ────────────────────────────────────

class LoginRequest(BaseModel):
    backend_key: str

class GenerateRequest(BaseModel):
    messages: list
    api_key: str
    provider: str = "deepseek"
    model: str = ""
    api_url: Optional[str] = None


# ── Provider helpers ───────────────────────────────────────────

def _build_openai_request(model: str, messages: list, api_key: str, api_url: str) -> tuple:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    body = {"model": model, "messages": messages}
    return api_url, headers, body

def _build_anthropic_request(model: str, messages: list, api_key: str, api_url: str) -> tuple:
    system = None
    msgs = []
    for m in messages:
        if m.get("role") == "system":
            system = m["content"]
        else:
            role = "user" if m["role"] == "user" else "assistant"
            content = m["content"]
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            msgs.append({"role": role, "content": content})
    body = {"model": model, "max_tokens": 4096, "messages": msgs}
    if system:
        body["system"] = system
    headers = {"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"}
    return api_url, headers, body

def _build_google_request(model: str, messages: list, api_key: str, api_url: str) -> tuple:
    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        text = m["content"]
        if isinstance(text, list):
            text = " ".join(p.get("text", "") for p in text if isinstance(p, dict))
        contents.append({"role": role, "parts": [{"text": text}]})
    system_instruction = None
    for m in messages:
        if m.get("role") == "system":
            system_instruction = m["content"]
            break
    body = {"contents": contents}
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    url = f"{api_url}{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    return url, headers, body

def _parse_openai_response(data: dict) -> str:
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")

def _parse_anthropic_response(data: dict) -> str:
    return data.get("content", [{}])[0].get("text", "")

def _parse_google_response(data: dict) -> str:
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return ""

AVAILABLE_MODELS = [
    {"label": "DeepSeek Flash (V3)", "provider": "deepseek", "model": "deepseek-chat"},
    {"label": "DeepSeek Reasoner R1", "provider": "deepseek", "model": "deepseek-reasoner"},
    {"label": "GPT-4.1", "provider": "openai", "model": "gpt-4.1-2025-04-14"},
    {"label": "GPT-4o", "provider": "openai", "model": "gpt-4o-2024-11-20"},
    {"label": "GPT-4o Mini", "provider": "openai", "model": "gpt-4o-mini"},
    {"label": "Claude Sonnet 4", "provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    {"label": "Claude Opus 4", "provider": "anthropic", "model": "claude-opus-4-20250514"},
    {"label": "Claude Haiku 3.5", "provider": "anthropic", "model": "claude-3-5-haiku-20241022"},
    {"label": "Gemini 2.5 Pro", "provider": "google", "model": "gemini-2.5-pro-exp-03-25"},
    {"label": "Gemini 2.5 Flash", "provider": "google", "model": "gemini-2.5-flash-preview-04-17"},
    {"label": "Grok 3", "provider": "xai", "model": "grok-3"},
    {"label": "Mistral Large", "provider": "mistral", "model": "mistral-large-2501"},
    {"label": "Command R+", "provider": "cohere", "model": "command-r-plus"},
    {"label": "Sonar Pro", "provider": "perplexity", "model": "sonar-pro"},
    {"label": "Llama 3.3 70B (Groq)", "provider": "groq", "model": "llama-3.3-70b-versatile"},
    {"label": "DeepSeek R1 (Groq)", "provider": "groq", "model": "deepseek-r1-distill-llama-70b"},
]


# ── Routes ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0"}


@app.post("/auth/login")
async def login(req: LoginRequest):
    if req.backend_key != BACKEND_KEY:
        raise HTTPException(403, "Invalid backend key")
    users = _load_users()
    user_id = f"user_{secrets.token_hex(8)}"
    token = secrets.token_hex(32)
    users[user_id] = {"token": token, "created": True}
    _save_users(users)
    return {"token": token, "user_id": user_id}


@app.get("/models")
async def list_models(authorization: Optional[str] = Header(None)):
    _verify_token(authorization)
    return {"models": AVAILABLE_MODELS}


@app.post("/generate")
async def generate(req: GenerateRequest, authorization: Optional[str] = Header(None)):
    _verify_token(authorization)
    provider = req.provider
    api_key = req.api_key
    model = req.model or "deepseek-chat"
    api_url = req.api_url or PROVIDER_URLS.get(provider)

    if not api_url:
        raise HTTPException(400, f"Unknown provider: {provider}")

    try:
        if provider == "anthropic":
            url, headers, body = _build_anthropic_request(model, req.messages, api_key, api_url)
        elif provider == "google":
            url, headers, body = _build_google_request(model, req.messages, api_key, api_url)
        elif provider in OPENAI_COMPAT:
            url, headers, body = _build_openai_request(model, req.messages, api_key, api_url)
        else:
            raise HTTPException(400, f"Unsupported provider: {provider}")

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        if provider == "anthropic":
            text = _parse_anthropic_response(data)
        elif provider == "google":
            text = _parse_google_response(data)
        else:
            text = _parse_openai_response(data)

        return {"content": text, "provider": provider, "model": model}

    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"Provider error: {e.response.text}")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Request failed: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))
