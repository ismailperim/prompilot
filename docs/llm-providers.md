# LLM providers

PromPilot talks to the model through one small interface, so the agent loop
is the same whichever provider you pick. `LLM_PROVIDER` selects it; the
default, `openai`, is any endpoint that speaks the OpenAI chat API.

| `LLM_PROVIDER` | Works with | Needs |
| --- | --- | --- |
| `openai` (default) | OpenAI, Ollama, vLLM, LM Studio, OpenRouter, LiteLLM and other gateways, and the OpenAI-compatible endpoints of Anthropic and Gemini | `LLM_BASE_URL`, `LLM_MODEL`, usually `LLM_API_KEY` |
| `azure` | Azure OpenAI | `AZURE_OPENAI_ENDPOINT`, `LLM_API_KEY`, `LLM_MODEL` = deployment name, optional `AZURE_OPENAI_API_VERSION` |
| `anthropic` | Claude via the Anthropic API (native SDK, prompt caching) | `ANTHROPIC_API_KEY` (or `LLM_API_KEY`), `LLM_MODEL` |
| `gemini` | Gemini via AI Studio key or Vertex AI (native SDK) | `GEMINI_API_KEY` (or `LLM_API_KEY`), or `GEMINI_USE_VERTEX=true` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` with application-default credentials; `LLM_MODEL` |

Any model that does function calling well works; the agent needs it for
`search_catalog`, `query_prometheus` and `emit_panel`.

## Examples

**OpenAI**
```
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-…
LLM_MODEL=gpt-4o-mini
```

**Ollama on the same machine** (no key)
```
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen2.5:14b
```

**Anthropic, native** — the system prompt and tool definitions are marked for
prompt caching, so repeated turns reuse the large stable prefix.
```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-…
LLM_MODEL=claude-sonnet-4-5
```
(Anthropic also exposes an OpenAI-compatible endpoint — `LLM_BASE_URL=https://api.anthropic.com/v1/` with the default provider — but without caching.)

**Gemini, API key**
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza…
LLM_MODEL=gemini-2.5-flash
```

**Gemini on Vertex AI** (service account / workload identity; mount or point
`GOOGLE_APPLICATION_CREDENTIALS` at the key file)
```
LLM_PROVIDER=gemini
GEMINI_USE_VERTEX=true
GOOGLE_CLOUD_PROJECT=my-project
GOOGLE_CLOUD_LOCATION=europe-west4
LLM_MODEL=gemini-2.5-pro
```

**Azure OpenAI**
```
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://my-resource.openai.azure.com
AZURE_OPENAI_API_VERSION=2024-10-21
LLM_API_KEY=…
LLM_MODEL=gpt-4o-mini        # the deployment name
```

**A gateway (LiteLLM, Portkey, in-house)** — usually OpenAI-compatible:
```
LLM_BASE_URL=https://ai-gateway.example.com/v1
LLM_API_KEY=…
LLM_MODEL=claude-sonnet-4-5
```

## Common settings

`LLM_TIMEOUT` (120s), `LLM_MAX_TOKENS` (4096), `LLM_TEMPERATURE` (0.2),
`LLM_MAX_TOOL_ITERATIONS` (8) apply to every provider. `LLM_EXTRA_BODY`
(JSON merged into each request) applies to `openai` and `azure`.

Reasoning output — Anthropic extended thinking, `reasoning_content` from
vLLM/DeepSeek, Gemini thoughts — streams to the UI as a collapsible
"model reasoning" block when the model emits it.
