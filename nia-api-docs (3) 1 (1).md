# Nia API Documentation

> **OpenAI-compatible AI Gateway** — 315+ models from 34+ providers. Drop-in replacement for any OpenAI SDK.

| | |
|---|---|
| **Base URL** | `https://api.nia.naslabs.ai/v1` |
| **Auth** | `Bearer nia_***` |
| **Format** | JSON |

---

## Table of Contents

- [Authentication](#authentication)
- [Quick Start](#quick-start)
- [Models & Providers](#models--providers)
- [Chat Completions](#chat-completions)
- [File Generation](#file-generation)
- [Web Search](#web-search)
- [Embeddings](#embeddings)
- [Image Generation](#image-generation)
- [Audio (TTS / STT)](#audio-tts--stt)
- [Voice Agent](#voice-agent)
- [Video Generation](#video-generation)
- [Reranking](#reranking)
- [Credits & Billing](#credits--billing)
- [Payment Plans & Buying Credits](#payment-plans--buying-credits)
- [API Key Scopes](#api-key-scopes)
- [Response Headers](#response-headers)
- [Error Codes](#error-codes)
- [Rate Limits](#rate-limits)
- [SDK Examples](#sdk-examples)

---

## Authentication

All API requests require a valid API key. Include it in the `Authorization` header as a Bearer token.

```
Authorization: Bearer nia_your_api_key_here
```

### Getting your API Key

1. Log in to Nia → **Settings → Developers → API Keys**
2. Click **Create Key**, give it a name (e.g. `Production Gateway`) and pick the scopes it needs (see [API Key Scopes](#api-key-scopes) — leave blank to grant all)
3. Copy the key immediately — it is shown **once** and looks like `nia_7f3a9c2e1b8d4f6a...`
4. Store it in your server-side environment (never in client-side/browser code)

You can also create keys programmatically (requires a signed-in session, not an API key):

```bash
curl -X POST https://api.nia.naslabs.ai/api/v1/developers/api-keys \
  -H "Content-Type: application/json" \
  -H "Cookie: <session-cookie>" \
  -d '{
    "name": "Production Gateway",
    "environment": "production",
    "scopes": ["gateway:read"]
  }'
```

**Key management:**

| Action | Endpoint |
|---|---|
| List keys | `GET /api/v1/developers/api-keys` |
| Create key | `POST /api/v1/developers/api-keys` |
| Revoke key | `DELETE /api/v1/developers/api-keys/{id}` |
| View usage | `GET /api/v1/developers/api-keys/{id}/usage` |

**Plan limits on number of keys:** Free **2** · Plus **10** · Team **50** · Enterprise **unlimited**

### Viewing token usage for a key

Every gateway request made with a key is logged with its request (input) and response
(output) token counts. You can page through that log for any key you own — the same
data shown in the **Usage** panel in the dashboard's API Keys page:

```bash
curl -s "https://api.nia.naslabs.ai/api/v1/developers/api-keys/{id}/usage?page=1&limit=25" \
  -H "Cookie: <session-cookie>"
```

```json
{
  "success": true,
  "data": {
    "owner": { "id": "usr_123", "name": "Jane Doe", "email": "jane@example.com" },
    "total": 42,
    "page": 1,
    "limit": 25,
    "logs": [
      {
        "id": "tul_abc123",
        "createdAt": "2026-08-31T05:00:00.000Z",
        "model": "gpt-4o",
        "provider": "openai",
        "feature": "completions",
        "chatId": null,
        "inputTokens": 512,
        "outputTokens": 128,
        "totalTokens": 640,
        "totalCost": 0.00193,
        "niaCost": 0.00212,
        "cached": false,
        "latencyMs": 842
      }
    ]
  }
}
```

`inputTokens` is the request-side token count sent to the model; `outputTokens` is the
response-side token count returned. Results are ordered newest first, 25 per page by
default (max 100). Requires a signed-in session (this is a dashboard endpoint, not
callable with an API key itself), and only returns usage for keys you own.

> **Security:** Keep your API key secret. Do not share it in client-side code, public repos, or logs. If compromised, revoke it immediately from the dashboard.
> **Access:** Gateway access requires a **Plus plan or higher** — Free plan requests get `403 plan_restricted`. Requests are billed against your **Gateway Credits** balance, separate from your chat subscription.

---

## Quick Start

Send your first request in 30 seconds:

### cURL

```bash
curl https://api.nia.naslabs.ai/v1/chat/completions \
  -H "Authorization: Bearer nia_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="nia_YOUR_KEY",
    base_url="https://api.nia.naslabs.ai/v1"
)

response = client.chat.completions.create(
    model="google/gemini-2.5-flash",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

### JavaScript / TypeScript

```typescript
import OpenAI from 'openai';

const client = new OpenAI({
  apiKey: 'nia_YOUR_KEY',
  baseURL: 'https://api.nia.naslabs.ai/v1',
});

const response = await client.chat.completions.create({
  model: 'google/gemini-2.5-flash',
  messages: [{ role: 'user', content: 'Hello!' }],
});
console.log(response.choices[0].message.content);
```

### Vercel AI SDK

```typescript
import { createOpenAI } from '@ai-sdk/openai';
import { generateText } from 'ai';

const nia = createOpenAI({
  apiKey: 'nia_YOUR_KEY',
  baseURL: 'https://api.nia.naslabs.ai/v1',
});

const { text } = await generateText({
  model: nia('google/gemini-2.5-flash'),
  prompt: 'Hello!',
});
console.log(text);
```

---

## Models & Providers

Access **329 models from 35 providers** through a single API. All prices shown are Nia's marked-up rates (provider cost + Nia margin). Use the provider-prefixed format: `provider/model-name`.

> **Live pricing:** Call `GET /v1/models` to see real-time prices with your current markup applied.

### `GET /v1/models`

List every available model with live Nia pricing.

```bash
curl https://api.nia.naslabs.ai/v1/models \
  -H "Authorization: Bearer nia_YOUR_KEY"
```

Response: `{object: "list", data: [{id, pricing, nia_input_price_per_1m, nia_output_price_per_1m, ...}]}`

### `GET /v1/models/{creator}/{model}`

Detail + live pricing for a single model.

```bash
curl https://api.nia.naslabs.ai/v1/models/anthropic/claude-sonnet-4-6 \
  -H "Authorization: Bearer nia_YOUR_KEY"
```

---

### Nia Aliases

These are Nia-branded shortcuts that automatically resolve to the best underlying model.

| Alias | Resolves To | Use Case |
|---|---|---|
| `nia-a-1` | `anthropic/claude-sonnet-4-6` | General intelligence, document analysis |
| `nia-think` | `anthropic/claude-sonnet-4-6` | Extended reasoning tasks |
| `nia-mini` | `anthropic/claude-haiku-4-5` | Fast, lightweight tasks |
| `nia-vision` | `openai/gpt-4o` | Image and video analysis |

---

### Language Models

#### OpenAI (56 models)

| Model ID | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| `openai/gpt-5-pro` | $15.00 | $120.00 | Most capable |
| `openai/gpt-5.5-pro` | $30.00 | $180.00 | |
| `openai/gpt-5.5` | $5.00 | $30.00 | |
| `openai/gpt-5.4-pro` | $30.00 | $180.00 | |
| `openai/gpt-5.4` | $2.50 | $15.00 | |
| `openai/gpt-5.4-mini` | $0.75 | $4.50 | |
| `openai/gpt-5.4-nano` | $0.20 | $1.25 | |
| `openai/gpt-5.3-codex` | $1.75 | $14.00 | |
| `openai/gpt-5.2-pro` | $21.00 | $168.00 | |
| `openai/gpt-5.2` | $1.75 | $14.00 | |
| `openai/gpt-5.2-codex` | $1.75 | $14.00 | |
| `openai/gpt-5.1-thinking` | $1.25 | $10.00 | |
| `openai/gpt-5.1-codex-max` | $1.25 | $10.00 | |
| `openai/gpt-5.1-codex` | $1.25 | $10.00 | |
| `openai/gpt-5.1-codex-mini` | $0.25 | $2.00 | |
| `openai/gpt-5.6-sol` | $5.00 | $30.00 | |
| `openai/gpt-5.6-terra` | $2.00 | $12.00 | |
| `openai/gpt-5.6-luna` | $0.20 | $1.20 | |
| `openai/gpt-5` | $1.25 | $10.00 | |
| `openai/gpt-5-codex` | $1.25 | $10.00 | |
| `openai/gpt-5-mini` | $0.25 | $2.00 | |
| `openai/gpt-5-nano` | $0.05 | $0.40 | |
| `openai/gpt-4o` | $2.50 | $10.00 | Vision capable |
| `openai/gpt-4o-mini` | $0.15 | $0.60 | |
| `openai/gpt-4o-mini-search-preview` | $0.15 | $0.60 | Web search |
| `openai/gpt-4.1` | $2.00 | $8.00 | |
| `openai/gpt-4.1-mini` | $0.40 | $1.60 | |
| `openai/gpt-4.1-nano` | $0.10 | $0.40 | |
| `openai/gpt-4-turbo` | $10.00 | $30.00 | |
| `openai/gpt-3.5-turbo` | $0.50 | $1.50 | |
| `openai/gpt-oss-120b` | $0.10 | $0.50 | Open-weight |
| `openai/gpt-oss-20b` | $0.05 | $0.20 | Open-weight |
| `openai/gpt-oss-safeguard-20b` | $0.075 | $0.30 | Safety |
| `openai/o3-pro` | $20.00 | $80.00 | Reasoning |
| `openai/o3` | $2.00 | $8.00 | Reasoning |
| `openai/o3-deep-research` | $10.00 | $40.00 | Deep research |
| `openai/o3-mini` | $1.10 | $4.40 | Reasoning |
| `openai/o4-mini` | $1.10 | $4.40 | Reasoning |
| `openai/o1` | $15.00 | $60.00 | Reasoning |

#### Anthropic (15 models)

| Model ID | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| `anthropic/claude-sonnet-4.6` | $3.00 | $15.00 | **Recommended** |
| `anthropic/claude-sonnet-4.5` | $3.00 | $15.00 | |
| `anthropic/claude-sonnet-4` | $3.00 | $15.00 | |
| `anthropic/claude-sonnet-5` | $2.00 | $10.00 | |
| `anthropic/claude-opus-4.8` | $5.00 | $25.00 | |
| `anthropic/claude-opus-4.8-fast` | $10.00 | $50.00 | |
| `anthropic/claude-opus-4.7` | $5.00 | $25.00 | |
| `anthropic/claude-opus-4.6` | $5.00 | $25.00 | |
| `anthropic/claude-opus-4.5` | $5.00 | $25.00 | |
| `anthropic/claude-opus-4` | $15.00 | $75.00 | |
| `anthropic/claude-opus-5` | $5.00 | $25.00 | |
| `anthropic/claude-opus-5-fast` | $10.00 | $50.00 | |
| `anthropic/claude-fable-5` | $10.00 | $50.00 | |
| `anthropic/claude-haiku-4.5` | $1.00 | $5.00 | Fast |
| `anthropic/claude-3-haiku` | $0.25 | $1.25 | Legacy |

#### Google (18 language models)

| Model ID | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| `google/gemini-2.5-pro` | $1.25 | $10.00 | **Recommended** |
| `google/gemini-2.5-flash` | $0.30 | $2.50 | Fast + vision |
| `google/gemini-2.5-flash-lite` | $0.10 | $0.40 | |
| `google/gemini-3-flash` | $0.50 | $3.00 | |
| `google/gemini-3.1-flash-lite` | $0.25 | $1.50 | |
| `google/gemini-3.1-pro-preview` | $2.00 | $12.00 | |
| `google/gemini-3.5-flash` | $1.50 | $9.00 | |
| `google/gemini-3.5-flash-lite` | $0.30 | $2.50 | |
| `google/gemini-3.6-flash` | $1.50 | $7.50 | |
| `google/gemini-3.7-flash` | $0.75 | $3.75 | |
| `google/gemini-omni-flash-preview` | $1.50 | $9.00 | |
| `google/gemma-4-26b-a4b-it` | $0.15 | $0.60 | Open-weight |
| `google/gemma-4-31b-it` | $0.14 | $0.40 | Open-weight |

#### DeepSeek (10 models)

| Model ID | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| `deepseek/deepseek-v4-pro-0813` | $1.32 | $3.96 | |
| `deepseek/deepseek-v4-pro` | $1.74 | $3.48 | |
| `deepseek/deepseek-v4-flash` | $0.20 | $0.40 | |
| `deepseek/deepseek-v4-flash-0731` | $0.20 | $0.40 | |
| `deepseek/deepseek-v3.2-thinking` | $0.62 | $1.85 | Reasoning |
| `deepseek/deepseek-v3.2` | $0.28 | $0.42 | |
| `deepseek/deepseek-v3.1-terminus` | $0.27 | $1.00 | |
| `deepseek/deepseek-v3.1` | $0.25 | $0.95 | |
| `deepseek/deepseek-v3` | $0.27 | $1.12 | |
| `deepseek/deepseek-r1` | $1.35 | $5.40 | Reasoning |

#### xAI / Grok (language, 19 models)

| Model ID | Input $/1M | Output $/1M |
|---|---|---|
| `xai/grok-4.6` | $2.00 | $6.00 |
| `xai/grok-4.5` | $2.00 | $6.00 |
| `xai/grok-4.3` | $1.25 | $2.50 |
| `xai/grok-4.20-reasoning` | $1.25 | $2.50 |
| `xai/grok-4.20-reasoning-beta` | $1.25 | $2.50 |
| `xai/grok-4.20-non-reasoning` | $1.25 | $2.50 |
| `xai/grok-4.20-non-reasoning-beta` | $1.25 | $2.50 |
| `xai/grok-4.20-multi-agent` | $1.25 | $2.50 |
| `xai/grok-4.20-multi-agent-beta` | $1.25 | $2.50 |
| `xai/grok-4.1-fast-reasoning` | $0.20 | $0.50 |
| `xai/grok-4.1-fast-non-reasoning` | $0.20 | $0.50 |
| `xai/grok-build-0.1` | $1.00 | $2.00 |

#### Mistral (13 language/code models)

| Model ID | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| `mistral/mistral-medium-3.5` | $1.50 | $7.50 | |
| `mistral/mistral-medium` | $0.40 | $2.00 | |
| `mistral/mistral-large-3` | $0.50 | $1.50 | |
| `mistral/mistral-small` | $0.10 | $0.30 | |
| `mistral/mistral-nemo` | $0.15 | $0.15 | |
| `mistral/magistral-medium` | $2.00 | $5.00 | Reasoning |
| `mistral/magistral-small` | $0.50 | $1.50 | Reasoning |
| `mistral/ministral-14b` | $0.20 | $0.20 | |
| `mistral/ministral-8b` | $0.15 | $0.15 | |
| `mistral/ministral-3b` | $0.10 | $0.10 | |
| `mistral/codestral` | $0.30 | $0.90 | Code |
| `mistral/devstral-2` | $0.40 | $2.00 | Code |
| `mistral/devstral-small-2` | $0.10 | $0.30 | Code |
| `mistral/pixtral-12b` | $0.15 | $0.15 | Vision |

#### Meta / Llama (9 models)

| Model ID | Input $/1M | Output $/1M |
|---|---|---|
| `meta/llama-4-maverick` | $0.24 | $0.97 |
| `meta/llama-4-scout` | $0.17 | $0.66 |
| `meta/llama-3.3-70b` | $0.72 | $0.72 |
| `meta/llama-3.1-70b` | $0.72 | $0.72 |
| `meta/llama-3.1-8b` | $0.22 | $0.22 |
| `meta/muse-spark-1.2` | $1.25 | $4.25 |
| `meta/muse-spark-1.1` | $1.25 | $4.25 |
| `meta/muse-spark-1.2-contributor` | $0.10 | $0.20 |
| `meta/muse-glimmer-30b` | $0.35 | $1.50 |

#### Alibaba / Qwen (31 language/multimodal models)

| Model ID | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| `alibaba/qwen3.6-max` | — | — | Preview |
| `alibaba/qwen3.8-max` | $2.00 | $6.00 | |
| `alibaba/qwen3.7-max` | $2.50 | $7.50 | |
| `alibaba/qwen3.6-plus` | $0.50 | $3.00 | |
| `alibaba/qwen3.7-plus` | $0.40 | $1.60 | |
| `alibaba/qwen3.5-plus` | $0.40 | $2.40 | |
| `alibaba/qwen3.6-27b` | $0.60 | $3.60 | |
| `alibaba/qwen3.8-2.4t-a95b` | $2.00 | $6.00 | |
| `alibaba/qwen3-235b` | $0.22 | $0.88 | |
| `alibaba/qwen3-max` | $1.20 | $6.00 | |
| `alibaba/qwen3-max-thinking` | $1.20 | $6.00 | Reasoning |
| `alibaba/qwen3-max-preview` | $1.20 | $6.00 | |
| `alibaba/qwen3-235b-a22b-thinking` | $0.40 | $4.00 | Reasoning |
| `alibaba/qwen3-vl-235b-a22b-instruct` | $0.40 | $1.60 | Vision |
| `alibaba/qwen3-vl-instruct` | $0.40 | $1.60 | Vision |
| `alibaba/qwen3-vl-thinking` | $0.40 | $4.00 | Vision+reasoning |
| `alibaba/qwen3-coder` | $1.50 | $7.50 | Code |
| `alibaba/qwen3-coder-plus` | $1.00 | $5.00 | Code |
| `alibaba/qwen3-coder-next` | $0.50 | $1.20 | Code |
| `alibaba/qwen3-coder-30b-a3b` | $0.15 | $0.60 | Code |
| `alibaba/qwen3-32b` | $0.16 | $0.64 | |
| `alibaba/qwen3-30b` | $0.12 | $0.50 | |
| `alibaba/qwen3-14b` | $0.12 | $0.24 | |
| `alibaba/qwen3.5-flash` | $0.10 | $0.40 | |
| `alibaba/qwen3.7-flash` | $0.03 | $0.13 | |
| `alibaba/qwen3.8-27b` | — | — | |
| `alibaba/qwen3-next-80b-a3b-instruct` | $0.15 | $1.20 | |
| `alibaba/qwen3-next-80b-a3b-thinking` | $0.15 | $1.20 | Reasoning |
| `alibaba/qwen3.6-max-preview` | $1.30 | $7.80 | |

#### ZAI / GLM (15 models)

| Model ID | Input $/1M | Output $/1M |
|---|---|---|
| `zai/glm-5.2-fast` | $2.10 | $6.60 |
| `zai/glm-5.2` | $1.10 | $3.85 |
| `zai/glm-5.1` | $1.40 | $4.40 |
| `zai/glm-5-turbo` | $1.20 | $4.00 |
| `zai/glm-5` | $1.00 | $3.20 |
| `zai/glm-4.7` | $0.60 | $2.20 |
| `zai/glm-4.7-flash` | $0.07 | $0.40 |
| `zai/glm-4.7-flashx` | $0.06 | $0.40 |
| `zai/glm-4.6` | $0.60 | $2.20 |
| `zai/glm-4.6v` | $0.30 | $0.90 |
| `zai/glm-4.6v-flash` | $0.00 | $0.00 |
| `zai/glm-4.5` | $0.60 | $2.20 |
| `zai/glm-4.5-air` | $0.20 | $1.10 |
| `zai/glm-4.5v` | $0.60 | $1.80 |
| `zai/glm-5v-turbo` | $1.20 | $4.00 |

#### MoonshotAI / Kimi (8 models)

| Model ID | Input $/1M | Output $/1M |
|---|---|---|
| `moonshotai/kimi-k3-fast` | $4.50 | $22.50 |
| `moonshotai/kimi-k3` | $3.00 | $15.00 |
| `moonshotai/kimi-k2.7-code-highspeed` | $1.90 | $8.00 |
| `moonshotai/kimi-k2.7-code` | $0.95 | $4.00 |
| `moonshotai/kimi-k2.6` | $0.95 | $4.00 |
| `moonshotai/kimi-k2.5` | $0.60 | $3.00 |
| `moonshotai/kimi-k2` | $0.57 | $2.30 |
| `moonshotai/kimi-k2-thinking` | $0.47 | $2.00 |

#### Amazon / Nova (4 language models)

| Model ID | Input $/1M | Output $/1M |
|---|---|---|
| `amazon/nova-2-lite` | $0.30 | $2.50 |
| `amazon/nova-pro` | $0.80 | $3.20 |
| `amazon/nova-lite` | $0.06 | $0.24 |
| `amazon/nova-micro` | $0.035 | $0.14 |

#### Other Language Models

| Model ID | Provider | Input $/1M | Output $/1M |
|---|---|---|---|
| `cohere/command-a` | Cohere | $2.50 | $10.00 |
| `perplexity/sonar-pro` | Perplexity | — | — |
| `perplexity/sonar` | Perplexity | — | — |
| `perplexity/sonar-reasoning-pro` | Perplexity | — | — |
| `nvidia/nemotron-3-ultra-550b-a55b` | NVIDIA | $0.60 | $2.40 |
| `nvidia/nemotron-3-super-120b-a12b` | NVIDIA | $0.15 | $0.65 |
| `nvidia/nemotron-3-nano-30b-a3b` | NVIDIA | $0.05 | $0.24 |
| `nvidia/nemotron-nano-12b-v2-vl` | NVIDIA | $0.20 | $0.60 |
| `nvidia/nemotron-nano-9b-v2` | NVIDIA | $0.06 | $0.23 |
| `minimax/minimax-m3` | MiniMax | $0.30 | $1.20 |
| `minimax/minimax-m2.7` | MiniMax | $0.30 | $1.20 |
| `minimax/minimax-m2.5` | MiniMax | $0.30 | $1.20 |
| `minimax/minimax-m2.1` | MiniMax | $0.30 | $1.20 |
| `minimax/minimax-m2` | MiniMax | $0.30 | $1.20 |
| `minimax/minimax-m2.7-highspeed` | MiniMax | $0.60 | $2.40 |
| `minimax/minimax-m2.5-highspeed` | MiniMax | $0.60 | $2.40 |
| `minimax/minimax-m2.1-lightning` | MiniMax | $0.30 | $2.40 |
| `minimax/minimax-h3` | MiniMax | — | — |
| `inception/mercury-2` | Inception | $0.25 | $0.75 |
| `inception/mercury-coder-small` | Inception | $0.25 | $1.00 |
| `arcee-ai/trinity-large-thinking` | Arcee AI | $0.25 | $0.90 |
| `arcee-ai/trinity-mini` | Arcee AI | $0.045 | $0.15 |
| `sakana/fugu-ultra` | Sakana | $5.00 | $30.00 |
| `sakana/namazu` | Sakana | $0.95 | $4.00 |
| `thinkingmachines/inkling` | ThinkingMachines | $1.00 | $4.05 |
| `thinkingmachines/inkling-small` | ThinkingMachines | $0.50 | $1.20 |
| `stepfun/step-3.7-flash` | StepFun | $0.20 | $1.15 |
| `stepfun/step-3.5-flash` | StepFun | $0.09 | $0.30 |
| `tencent/hy3` | Tencent | $0.14 | $0.58 |
| `morph/morph-v3-large` | Morph | $0.90 | $1.90 |
| `morph/morph-v3-fast` | Morph | $0.80 | $1.20 |
| `inclusionai/ling-3.0-flash` | InclusionAI | $0.06 | $0.18 |
| `interfaze/interfaze-beta` | Interfaze | $1.50 | $3.50 |
| `kwaipilot/kat-coder-pro-v2.5` | KwaiPilot | $0.74 | $2.96 |
| `kwaipilot/kat-coder-pro-v2` | KwaiPilot | $0.30 | $1.20 |
| `kwaipilot/kat-coder-pro-v1` | KwaiPilot | $0.30 | $1.20 |
| `kwaipilot/kat-coder-air-v2.5` | KwaiPilot | $0.15 | $0.60 |
| `poolside/laguna-s-2.1` | Poolside | $0.10 | $0.20 |
| `poolside/laguna-s-2.1-free` | Poolside | $0.00 | $0.00 |
| `xiaomi/mimo-v2.5-pro` | Xiaomi | $0.435 | $0.87 |
| `xiaomi/mimo-v2.5` | Xiaomi | $0.14 | $0.28 |
| `bytedance/seed-1.8` | ByteDance | $0.25 | $2.00 |
| `bytedance/seed-1.6` | ByteDance | $0.25 | $2.00 |

---

### Embedding Models

| Model ID | Provider | Input $/1M | Notes |
|---|---|---|---|
| `openai/text-embedding-3-small` | OpenAI | $0.02 | **Recommended for RAG** |
| `openai/text-embedding-3-large` | OpenAI | $0.13 | High accuracy |
| `openai/text-embedding-ada-002` | OpenAI | $0.10 | Legacy |
| `google/gemini-embedding-001` | Google | $0.15 | |
| `google/gemini-embedding-2` | Google | $0.20 | |
| `google/text-embedding-005` | Google | $0.025 | |
| `google/text-multilingual-embedding-002` | Google | $0.025 | Multilingual |
| `alibaba/qwen3-embedding-8b` | Alibaba | $0.05 | |
| `alibaba/qwen3-embedding-4b` | Alibaba | $0.02 | |
| `alibaba/qwen3-embedding-0.6b` | Alibaba | $0.01 | |
| `amazon/titan-embed-text-v2` | Amazon | $0.02 | |
| `cohere/embed-v4.0` | Cohere | $0.12 | |
| `mistral/codestral-embed` | Mistral | $0.15 | Code |
| `mistral/mistral-embed` | Mistral | $0.10 | |
| `voyage/voyage-4-large` | Voyage | $0.12 | |
| `voyage/voyage-4` | Voyage | $0.06 | |
| `voyage/voyage-4-lite` | Voyage | $0.02 | |
| `voyage/voyage-3.5` | Voyage | $0.06 | |
| `voyage/voyage-3.5-lite` | Voyage | $0.02 | |
| `voyage/voyage-3-large` | Voyage | $0.18 | |
| `voyage/voyage-code-3` | Voyage | $0.18 | Code |
| `voyage/voyage-code-2` | Voyage | $0.12 | Code |
| `voyage/voyage-finance-2` | Voyage | $0.12 | Finance |
| `voyage/voyage-law-2` | Voyage | $0.12 | Legal |
| `perplexity/pplx-embed-v1-4b` | Perplexity | $0.03 | |
| `perplexity/pplx-embed-v1-0.6b` | Perplexity | $0.004 | |

---

### Image Generation Models

| Model ID | Provider | Notes |
|---|---|---|
| `openai/gpt-image-2` | OpenAI | Latest generation |
| `openai/gpt-image-1.5` | OpenAI | |
| `openai/gpt-image-1` | OpenAI | |
| `openai/gpt-image-1-mini` | OpenAI | |
| `google/gemini-2.5-flash-image` | Google | **Chat-based image output** |
| `google/gemini-3.1-flash-image` | Google | **Chat-based image output** |
| `google/gemini-3.1-flash-image-preview` | Google | **Chat-based image output** |
| `google/gemini-3.1-flash-lite-image` | Google | Chat-based |
| `google/gemini-3-pro-image` | Google | High quality |
| `google/imagen-4.0-generate-001` | Google | |
| `google/imagen-4.0-fast-generate-001` | Google | Fast |
| `google/imagen-4.0-ultra-generate-001` | Google | Ultra quality |
| `bfl/flux-2-max` | BFL | |
| `bfl/flux-2-pro` | BFL | |
| `bfl/flux-2-flex` | BFL | |
| `bfl/flux-2-klein-9b` | BFL | |
| `bfl/flux-2-klein-4b` | BFL | |
| `bfl/flux-kontext-max` | BFL | Context-aware |
| `bfl/flux-kontext-pro` | BFL | Context-aware |
| `bfl/flux-pro-1.1-ultra` | BFL | |
| `bfl/flux-pro-1.1` | BFL | |
| `bfl/flux-pro-1.0-fill` | BFL | Inpainting |
| `recraft/recraft-v4.1-pro` | Recraft | |
| `recraft/recraft-v4.1` | Recraft | |
| `recraft/recraft-v4.1-utility-pro` | Recraft | |
| `recraft/recraft-v4.1-utility` | Recraft | |
| `recraft/recraft-v4-pro` | Recraft | |
| `recraft/recraft-v4` | Recraft | |
| `recraft/recraft-v3` | Recraft | |
| `recraft/recraft-v2` | Recraft | |
| `xai/grok-imagine-image-2.0` | xAI | |
| `xai/grok-imagine-image` | xAI | |
| `bytedance/seedream-5.0-pro` | ByteDance | |
| `bytedance/seedream-5.0-lite` | ByteDance | |
| `bytedance/seedream-4.5` | ByteDance | |
| `bytedance/seedream-4.0` | ByteDance | |
| `meta/muse-spark-*` | Meta | Creative image |
| `prodia/flux-fast-schnell` | Prodia | Fast |

> **Note on Gemini image models:** `gemini-*-image` models return image bytes directly via the chat completions endpoint (set `response_format` or send a multimodal prompt). This is different from `/v1/images/generations` which returns a URL.

---

### Video Generation Models

| Model ID | Provider | Notes |
|---|---|---|
| `google/veo-3.1-generate-001` | Google | Highest quality |
| `google/veo-3.1-fast-generate-001` | Google | Fast |
| `google/veo-3.1-lite-generate-001` | Google | Lite |
| `google/veo-3.0-generate-001` | Google | |
| `google/veo-3.0-fast-generate-001` | Google | |
| `klingai/kling-v3.0-t2v` | KlingAI | Text-to-video |
| `klingai/kling-v3.0-i2v` | KlingAI | Image-to-video |
| `klingai/kling-v3.0-motion-control` | KlingAI | Motion control |
| `klingai/kling-v2.6-t2v` | KlingAI | |
| `klingai/kling-v2.6-i2v` | KlingAI | |
| `klingai/kling-v2.6-motion-control` | KlingAI | |
| `klingai/kling-v2.5-turbo-t2v` | KlingAI | |
| `klingai/kling-v2.5-turbo-i2v` | KlingAI | |
| `alibaba/wan-v2.7-t2v` | Alibaba | Text-to-video |
| `alibaba/wan-v2.7-r2v` | Alibaba | Reference-to-video |
| `alibaba/wan-v2.6-t2v` | Alibaba | |
| `alibaba/wan-v2.6-i2v` | Alibaba | Image-to-video |
| `alibaba/wan-v2.6-r2v` | Alibaba | |
| `alibaba/wan-v2.6-i2v-flash` | Alibaba | Fast |
| `alibaba/wan-v2.6-r2v-flash` | Alibaba | Fast |
| `alibaba/wan-v2.5-t2v-preview` | Alibaba | |
| `bytedance/seedance-2.5` | ByteDance | |
| `bytedance/seedance-2.0` | ByteDance | |
| `bytedance/seedance-2.0-fast` | ByteDance | |
| `bytedance/seedance-v1.5-pro` | ByteDance | |
| `bytedance/seedance-v1.0-pro` | ByteDance | |
| `bytedance/seedance-v1.0-pro-fast` | ByteDance | |
| `xai/grok-imagine-video-1.5` | xAI | |
| `xai/grok-imagine-video-1.5-preview` | xAI | |
| `xai/grok-imagine-video` | xAI | |
| `bfl/flux-3-video` | BFL | |

> Video generation is asynchronous — results may take 30–120 seconds.

---

### Audio Models (TTS / STT / Realtime)

#### Text-to-Speech

| Model ID | Provider | $/1M chars | Notes |
|---|---|---|---|
| `openai/tts-1-hd` | OpenAI | $30.00 | High quality |
| `openai/tts-1` | OpenAI | $15.00 | |
| `xai/grok-tts` | xAI | $15.00 | |
| `fish-audio/s2.1-pro` | Fish Audio | $15.00 | Voice cloning |
| `fish-audio/s2-pro` | Fish Audio | $15.00 | |
| `fish-audio/s1` | Fish Audio | $15.00 | |

Also available via the `/v1/voice/speak` endpoint: language-based TTS with auto voice selection.

#### Speech-to-Text / Transcription

| Model ID | Provider | Notes |
|---|---|---|
| `openai/whisper-1` | OpenAI | WAV, MP3, WebM, OGG |
| `openai/gpt-4o-transcribe` | OpenAI | Higher accuracy |
| `openai/gpt-4o-mini-transcribe` | OpenAI | Faster |
| `openai/gpt-realtime-whisper` | OpenAI | Realtime stream |
| `xai/grok-stt` | xAI | |
| `fish-audio/transcribe-1` | Fish Audio | |

#### Realtime / Voice Agent

| Model ID | Provider | Notes |
|---|---|---|
| `openai/gpt-realtime-2.1` | OpenAI | **Latest**, tool calling supported |
| `openai/gpt-realtime-2` | OpenAI | |
| `openai/gpt-realtime-1.5` | OpenAI | |
| `openai/gpt-realtime-mini` | OpenAI | Lightweight |
| `xai/grok-voice-think-fast-2.0` | xAI | |
| `xai/grok-voice-think-fast-1.0` | xAI | |

> Use `POST /v1/voice/connect` (WebRTC SDP) or `POST /v1/audio/speech` + `POST /v1/audio/transcriptions` for turn-by-turn voice.

---

### Reranking Models

| Model ID | Provider | $/1K docs |
|---|---|---|
| `voyage/rerank-2.5` | Voyage | $0.05 |
| `voyage/rerank-2.5-lite` | Voyage | $0.02 |
| `cohere/rerank-v4-pro` | Cohere | — |
| `cohere/rerank-v4-fast` | Cohere | — |
| `cohere/rerank-v3.5` | Cohere | — |

---

### Provider Summary

| Provider | Models | Types |
|---|---|---|
| OpenAI | 56 | Language, Image, Embedding, Audio, Realtime |
| Alibaba | 39 | Language, Embedding, Video |
| Google | 30 | Language, Image, Video, Embedding |
| xAI | 21 | Language, Image, Video, TTS, STT |
| ZAI | 15 | Language (GLM) |
| Mistral | 16 | Language, Embedding, Code |
| Voyage | 12 | Embedding, Reranking |
| ByteDance | 12 | Language, Image, Video |
| BFL | 11 | Image, Video |
| DeepSeek | 10 | Language |
| MoonshotAI | 8 | Language |
| KlingAI | 8 | Video |
| Recraft | 8 | Image |
| Meta | 9 | Language |
| MiniMax | 9 | Language |
| NVIDIA | 6 | Language |
| Cohere | 5 | Language, Embedding, Reranking |
| Perplexity | 5 | Language (web search), Embedding |
| Fish Audio | 4 | TTS, STT |
| KwaiPilot | 4 | Code |
| Amazon | 5 | Language, Embedding |
| Arcee AI | 2 | Language |
| Inception | 2 | Language |
| Morph | 2 | Language |
| Poolside | 2 | Language |
| Sakana | 2 | Language |
| StepFun | 2 | Language |
| ThinkingMachines | 2 | Language |
| Xiaomi | 2 | Language |
| InclusionAI | 1 | Language |
| Interfaze | 1 | Language |
| Prodia | 1 | Image |
| QuiverAI | 1 | Language |
| Tencent | 1 | Language |
| + more | — | New providers added regularly |

> All prices shown are **Vercel base rates**. Your Nia invoice applies the configured markup on top. Call `GET /v1/models` for real-time Nia-marked-up prices.

---

## Chat Completions

OpenAI-compatible chat completions endpoint. Supports streaming, tool calls, JSON mode, file generation, and web search.

### `POST /v1/chat/completions`

Create a chat completion (streaming or non-streaming).

**Request Body:**

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user", "content": "Hello!" }
  ],
  "stream": false,
  "max_tokens": 1000
}
```

**Response:**

```json
{
  "id": "chatcmpl-...",
  "choices": [{
    "message": { "role": "assistant", "content": "Hi there!" },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 5,
    "total_tokens": 17
  }
}
```

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `model` | string | Yes | Model ID (e.g. `gpt-4o`, `google/gemini-2.5-flash`) |
| `messages` | array | Yes | Array of message objects with `role` and `content` |
| `stream` | boolean | No | Enable SSE streaming (default: false) |
| `max_tokens` | integer | No | Maximum tokens to generate |
| `temperature` | number | No | Sampling temperature (0-2) |
| `top_p` | number | No | Nucleus sampling parameter |
| `web_search` | boolean | No | Nia extension: ground response with web search |
| `file_generation` | boolean | No | Nia extension: generate downloadable files |
| `file_name` | string | No | Filename for file generation (e.g. `report.xlsx`) |

> **Note:** `web_search`, `file_generation`, and `file_name` are optional Nia extensions. Omitting them gives standard OpenAI-compatible behavior.

---

## File Generation

Generate downloadable files (Excel, CSV, JSON, PDF, DOCX, PPTX, code files) via the completions API or the standalone endpoint.

### `POST /v1/chat/completions` (with file generation)

Generate a file via AI — set `file_generation: true`.

```json
{
  "model": "gpt-4o",
  "messages": [
    { "role": "user", "content": "Create a sales report with Q1-Q4 revenue data" }
  ],
  "file_generation": true,
  "file_name": "report.xlsx"
}
```

> Supported file types: xlsx, csv, json, pdf, docx, pptx, py, js, ts, sh, sql, md, html. Requires scope: `files:generate`.

### `POST /v1/files/generate`

Standalone file generation — convert existing content directly to a file (no AI model call).

```json
{
  "format": "pdf",
  "title": "Q1 Sales Report",
  "content": "# Q1 Sales Report\n\nRevenue: $1.2M\n\n## By Region\n- North: $500K\n- South: $700K"
}
```

Returns binary file stream with `Content-Disposition: attachment`. Supported formats: pdf, docx, xlsx, pptx, csv, txt, md, json.

---

## Web Search

Ground AI responses with real-time web search results, or call the standalone search endpoint directly.

### `POST /v1/search`

Standalone web search — returns raw results without calling an AI model.

```json
{
  "query": "latest AI breakthroughs 2025",
  "maxResults": 8
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "results": [
      { "title": "OpenAI releases GPT-5", "url": "https://...", "snippet": "OpenAI today announced..." }
    ],
    "answerBox": "OpenAI announced GPT-5 on..."
  }
}
```

### `POST /v1/chat/completions` (with web search)

AI response grounded with web search — set `web_search: true`.

```json
{
  "model": "gpt-4o",
  "messages": [
    { "role": "user", "content": "What are the latest developments in quantum computing?" }
  ],
  "web_search": true
}
```

> When `web_search` is true, the system searches the web before calling the AI model. Results are injected into context so the AI can cite sources. Works with both streaming and non-streaming. Both `web_search` and `file_generation` can be combined in a single request.

---

## Embeddings

Generate text embeddings for semantic search, clustering, and similarity matching.

### `POST /v1/embeddings`

```json
{
  "model": "openai/text-embedding-3-small",
  "input": "The quick brown fox jumps over the lazy dog"
}
```

**Response:**

```json
{
  "object": "list",
  "data": [{
    "object": "embedding",
    "index": 0,
    "embedding": [0.0023, -0.009, 0.015, "..."]
  }],
  "model": "text-embedding-3-small",
  "usage": { "prompt_tokens": 9, "total_tokens": 9 }
}
```

Supported models include OpenAI (`text-embedding-3-small`, `text-embedding-3-large`), Voyage, Google, Mistral, and Alibaba embedding models.

---

## Image Generation

Generate images from text prompts using DALL-E, Flux, Recraft, and other providers.

### `POST /v1/images/generations`

```json
{
  "model": "openai/dall-e-3",
  "prompt": "A futuristic city at sunset, cyberpunk style",
  "n": 1,
  "size": "1024x1024"
}
```

**Response:**

```json
{
  "created": 1234567890,
  "data": [{
    "url": "https://...",
    "revised_prompt": "A detailed futuristic city..."
  }]
}
```

Also supports: `bfl/flux-pro-1.1-ultra`, `recraft/recraft-v3`, and more image models.

---

## Audio (TTS / STT)

Text-to-speech, speech-to-text transcription, and audio translation.

### `POST /v1/audio/speech`

Text-to-speech — convert text to natural-sounding audio.

```json
{
  "model": "openai/tts-1",
  "input": "Hello, welcome to Nia AI!",
  "voice": "alloy"
}
```

Returns audio binary stream. Voices: alloy, echo, fable, onyx, nova, shimmer.

### `POST /v1/audio/transcriptions`

Speech-to-text — transcribe audio files. Send as `multipart/form-data`.

```bash
curl https://api.nia.naslabs.ai/v1/audio/transcriptions \
  -H "Authorization: Bearer nia_YOUR_KEY" \
  -F "file=@audio.mp3" \
  -F "model=openai/whisper-1"
```

**Response:**

```json
{ "text": "Hello world, this is a test recording." }
```

### `POST /v1/audio/translations`

Translate audio to English text. Send as `multipart/form-data`.

```bash
curl https://api.nia.naslabs.ai/v1/audio/translations \
  -H "Authorization: Bearer nia_YOUR_KEY" \
  -F "file=@spanish_audio.mp3" \
  -F "model=openai/whisper-1"
```

---

## Voice Agent

Real-time voice AI via WebRTC and turn-by-turn endpoints. Supports 80+ languages.

### `POST /v1/voice/respond`

Text in, AI text out (no audio processing).

```json
{
  "text": "What is the weather?",
  "history": "[]"
}
```

### `POST /v1/voice/translate`

Translate text between languages.

```json
{
  "text": "Hello world",
  "from": "English",
  "to": "Spanish"
}
```

**Response:**

```json
{ "success": true, "data": { "translation": "Hola mundo" } }
```

### `POST /v1/voice/speak`

Text-to-speech (returns base64 audio).

```json
{ "text": "Hello from Nia", "lang": "en" }
```

### `POST /v1/voice/transcribe`

Transcribe audio to text (`multipart/form-data`). Supports 38+ languages.

```
FormData:
  audio    (file, required)    — WAV, MP3, WebM, OGG
  language (string, optional)  — ISO-639-1 code (e.g. "en", "fr", "hi")
  detect   (string, optional)  — "true" for auto-detect
```

### `POST /v1/voice/chat`

Full voice chat: audio in → AI text + TTS audio out (`multipart/form-data`).

```
FormData:
  audio    (file)        — Audio recording
  history  (JSON string) — Conversation history
  language (string)      — Language code
```

**Response:**

```json
{
  "userText": "Hi",
  "aiText": "Hello!",
  "audioBase64": "...",
  "audioMimeType": "audio/mpeg"
}
```

### `POST /v1/voice/connect`

Proxy WebRTC SDP offer for real-time speech-to-speech voice agent.

```json
{
  "sdp": "<SDP offer string>",
  "voice": "sage",
  "instructions": "You are a helpful assistant..."
}
```

> For real-time speech-to-speech. Requires WebRTC peer connection on client side.

### `POST /v1/realtime/token`

Mints a short-lived WebRTC session token for realtime voice via the gateway. Supports tool calling.

```json
{
  "model": "gpt-realtime",
  "voice": "sage",
  "tools": [{ "type": "function", "function": { "name": "knowledge_search", "parameters": {} } }],
  "tool_choice": "auto"
}
```

**Response:**

```json
{
  "provider": "openai",
  "token": "eph_...",
  "url": "https://...",
  "model": "gpt-realtime",
  "expires_at": "2026-08-18T12:34:56Z",
  "session_id": "sess_...",
  "ice_servers": [],
  "settings": {}
}
```

---

## Video Generation

Generate videos from text prompts or images using KlingAI and other video models.

### `POST /v1/videos/generations`

```json
{
  "model": "kling-ai/kling-v2-master",
  "prompt": "A cat playing piano in a jazz club"
}
```

Video generation is asynchronous — results may take 30-120 seconds.

---

## Reranking

Rerank documents by relevance to a query for improved search results.

### `POST /v1/rerank`

```json
{
  "model": "voyage/rerank-2",
  "query": "What is machine learning?",
  "documents": [
    "Machine learning is a subset of AI...",
    "The weather today is sunny...",
    "Deep learning uses neural networks..."
  ]
}
```

**Response:**

```json
{
  "results": [
    { "index": 0, "relevance_score": 0.95 },
    { "index": 2, "relevance_score": 0.82 },
    { "index": 1, "relevance_score": 0.05 }
  ]
}
```

---

## Credits & Billing

Check your credit balance and view usage reports.

### `GET /v1/credits`

Check your gateway credit balance.

```bash
curl https://api.nia.naslabs.ai/v1/credits \
  -H "Authorization: Bearer nia_YOUR_KEY"
```

Response: `{balance, dedicated, shared, used_this_month, currency, billing_exempt}`

- `balance` — total usable balance for this key (`dedicated + shared`).
- `dedicated` — credits purchased/granted directly to **this** API key (self-serve "add credits to this key"). This is the number to watch if you're tracking spend per key.
- `shared` — the tenant's pooled balance (plan-included/refresh credits, legacy pooled purchases, admin grants with no key target). Shared across every key on the account.
- Usage debits `dedicated` first, then spills into `shared` once the key's own balance is exhausted.
- `dedicated` / `shared` are `null` when `billing_exempt` is `true`.

### `GET /v1/report`

Get usage report with grouping options (by model, day, etc.).

```bash
curl "https://api.nia.naslabs.ai/v1/report?group_by=model" \
  -H "Authorization: Bearer nia_YOUR_KEY"
```

Query params:

| Param | Values | Default | Notes |
|---|---|---|---|
| `start_date` | `YYYY-MM-DD` | — | Inclusive |
| `end_date` | `YYYY-MM-DD` | — | Inclusive (end of day UTC) |
| `group_by` | `day` \| `model` \| `provider` | `day` | |
| `scope` | `key` \| `tenant` | `key` | `key` = only the calling API key's own spend. `tenant` = account-wide, across every key. |
| `api_key_id` | a key id | — | Overrides `scope` — report spend for a specific key (must belong to your tenant). |

Response: `{object: "report", group_by, scope, data: [...], totals}` — `scope` echoes back `"key"` or `"tenant"` so you can confirm what the numbers cover.

By default (no `scope`/`api_key_id` passed) the report is scoped to the calling key only — pass `?scope=tenant` or an explicit `?api_key_id=` to see totals across other keys on the account.

### `GET /v1/generation?id=...`

Look up cost/usage for a single past request.

```bash
curl "https://api.nia.naslabs.ai/v1/generation?id=gen_abc123" \
  -H "Authorization: Bearer nia_YOUR_KEY"
```

Response: `{id, model, provider, input_tokens, output_tokens, total_tokens, cost_usd, nia_cost_usd, latency_ms, cached, created_at}`

### How billing works

- Costs are metered per request from actual token/media usage and deducted from your **Gateway Credits** balance.
- Nia applies a markup (default 20%) on top of upstream provider cost — always check `GET /v1/models` for the live, current `nia_input_price_per_1m` / `nia_output_price_per_1m` rather than hardcoding prices.
- Media pricing snapshot: images ~$0.04/image, TTS ~$15/1M chars (`tts-1`) or ~$30/1M chars (`tts-1-hd`), transcription ~$0.006/min, video ~$0.20/request, rerank ~$0.002/1K documents.
- Streaming requests are metered from the final `usage` chunk in the SSE stream, deducted asynchronously after the stream closes.

---

## Payment Plans & Buying Credits

Nia has two separate charges: a **monthly subscription** (which plan you're on — gates gateway access and sets limits) and **Gateway Credits** (a prepaid balance every `/v1/*` request draws down from).

### Subscription plans

| Plan | Price | Included tokens/mo | API keys | Spaces | Rate limit | Gateway access |
|---|---|---|---|---|---|---|
| **Free** | $0 | 50K | 2 | 5 | 60 req/min | ❌ (`403 plan_restricted`) |
| **Plus** | $9/mo (**$7/mo** billed annually) | 1M | 10 | Unlimited | 120 req/min | ✅ |
| **Team** | $2/user/mo (**$1/user/mo** billed annually), 1–5 users min | 5M shared pool | 50 | Unlimited | 300 req/min | ✅ |
| **Enterprise** | Custom | Custom | Unlimited | Unlimited | 1000 req/min | ✅ |

- Included tokens cover in-app chat usage (Nia Mini, A-1.0, Think, etc.) and refresh each billing period.
- Gateway (`/v1/*`) calls are billed from **Gateway Credits**, not from the plan's included tokens.
- Manage/upgrade your plan from **Settings → Billing** in the dashboard.

### Buying Gateway Credits

Gateway Credits are a prepaid top-up balance, separate from your subscription, used to pay for `/v1/*` requests.

```bash
# Requires a signed-in session (cookie), not an API key — self-service billing action
curl -X POST https://api.nia.naslabs.ai/api/v1/billing/credits \
  -H "Content-Type: application/json" \
  -H "Cookie: <session-cookie>" \
  -d '{ "amount": 20 }'
```

- `amount` is any USD amount you choose (e.g. `10`, `20`, `50`) — pricing is **1:1**: **$1 purchased = 1 Gateway Credit**.
- Returns a Stripe Checkout URL; credits land in your balance the moment payment succeeds.
- Credits **never expire** and are spent independently of your plan's monthly token allowance.
- Check your balance anytime with [`GET /v1/credits`](#get-v1credits) and see spend history with [`GET /v1/report`](#get-v1report).

---

## API Key Scopes

API keys are created with specific scopes that control access. All `/v1/*` gateway routes require `gateway:read` at minimum. All 14 scopes are granted by default:

| Scope | Description |
|---|---|
| `gateway:read` | All `/v1/*` gateway endpoints (chat, images, audio, embeddings, rerank, video, realtime, credits, generation, report) |
| `completions:write` | Create chat completions |
| `chat:read` | Read chat history |
| `chat:write` | Write/modify chats |
| `files:read` | Read uploaded files |
| `files:write` | Upload files |
| `files:generate` | Generate files via AI |
| `images:generate` | Generate images |
| `voice:session` | Voice chat sessions |
| `voice:agent` | Voice agent (WebRTC) |
| `voice:translate` | Voice translation |
| `voice:transcribe` | Audio transcription |
| `search:web` | Web search |
| `kb:read` | Read knowledge base |
| `kb:write` | Write to knowledge base |
| `billing:exempt` | Internal — bypasses credit deduction and rate limits |

---

## Response Headers

Every gateway response includes:

```
X-Nia-Model: anthropic/claude-sonnet-4-6
X-Nia-Credits-Remaining: 42.123456      (or "unlimited" if billing-exempt)
```

Streaming responses additionally include:

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

---

## Error Codes

| Code | HTTP Status | Description |
|---|---|---|
| `invalid_api_key` | 401 | Missing, invalid, or revoked API key |
| `plan_restricted` | 403 | Your plan does not include this feature |
| `insufficient_credits` | 402 | Not enough credits to complete the request |
| `invalid_request` | 400 | Malformed request body or missing required fields |
| `not_found` | 404 | Unknown resource, e.g. a `generation` id that doesn't exist |
| `upstream_error` | 503 | The upstream AI provider returned an error |
| `gateway_unavailable` | 503 | Gateway is temporarily unavailable |
| `rate_limit_exceeded` | 429 | Too many requests — slow down |
| `service_unavailable` | 503 | Service is undergoing maintenance |

### Error Response Format

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "The API key provided is invalid or has been revoked.",
    "type": "authentication_error"
  }
}
```

---

## Rate Limits

Per-tenant, per-minute, enforced on every `/v1/*` call:

| Plan | Requests / min |
|---|---|
| Free | 60 |
| Plus | 120 |
| Team | 300 |
| Enterprise | 1000 |

On limit exceeded → `429` with headers `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset` (unix seconds).

| Other limits | Value |
|---|---|
| File upload size | **25 MB** max |
| Image generation | May take **5–20 seconds** |
| Video generation | May take **30–120 seconds** |

---

## SDK Examples

Nia is fully OpenAI-compatible. Use any OpenAI SDK — just change the base URL and API key.

### Python — Streaming

```python
from openai import OpenAI

client = OpenAI(
    api_key="nia_YOUR_KEY",
    base_url="https://api.nia.naslabs.ai/v1"
)

stream = client.chat.completions.create(
    model="google/gemini-2.5-flash",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### JavaScript — With Web Search

```javascript
const response = await fetch('https://api.nia.naslabs.ai/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer nia_YOUR_KEY',
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    model: 'gpt-4o',
    messages: [{ role: 'user', content: 'Latest news about AI' }],
    web_search: true,
  }),
});

const data = await response.json();
console.log(data.choices[0].message.content);
```

### Python — Generate Excel File

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Create a budget spreadsheet"}],
    extra_body={
        "file_generation": True,
        "file_name": "budget.xlsx"
    }
)
print(response.choices[0].message.content)
```

### cURL — Image Generation

```bash
curl https://api.nia.naslabs.ai/v1/images/generations \
  -H "Authorization: Bearer nia_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/dall-e-3",
    "prompt": "A serene mountain landscape at dawn",
    "n": 1,
    "size": "1024x1024"
  }'
```

---

**Nia AI Gateway** — 315+ models, one API

Questions? Contact your organization admin or visit the dashboard.
