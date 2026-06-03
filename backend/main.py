"""Railway backend for AI Companion — proxies AI provider calls."""

import os
import json
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI(title="AI Companion Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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


# ── Routes ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate(req: GenerateRequest):
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
