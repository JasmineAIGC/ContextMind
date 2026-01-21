# LLM Integration for ContextMind v7.1 Demos

## Overview

In ContextMind v7.1, **LLM invocation is external to the core framework**. This means:
- The ContextMind framework handles **context engineering** (Steps 1-4 + 6)
- Your application is responsible for **calling the LLM** (Step 5)

For demo purposes, we provide `SimpleLLMClient` - a lightweight OpenAI-compatible client.

## Quick Start

### 1. Install Dependencies

```bash
pip install openai python-dotenv
```

### 2. Configure .env File

Create a `.env` file in the project root with your LLM configuration:

```env
# Qwen3 API Configuration (example)
QWEN3_API_KEY=sk-your-api-key-here
QWEN3_BASE_URL=http://your-server:port/v1
QWEN3_MODEL=Qwen3-32B
QWEN3_MAX_TOKENS=8192

# Or use generic LLM_ prefix for compatibility
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=http://your-server:port/v1
LLM_MODEL=Qwen3-32B
```

### 3. Run Demos

```bash
# With real LLM (default)
python interactive_demo.py

# With simulated responses (for testing without LLM)
python interactive_demo.py --no-llm

# With detailed logging
python interactive_demo.py --detailed

# With debug logging
python interactive_demo.py --debug
```

## Supported LLM Providers

The client supports any OpenAI-compatible API:

- **Qwen** (Alibaba Cloud)
- **DeepSeek**
- **OpenAI**
- **vLLM** (self-hosted)
- **LocalAI**
- **Ollama** (with OpenAI compatibility)
- And more...

## Environment Variables

The client checks these variables in order:

### API Key (Required)
- `QWEN3_API_KEY`
- `CONTEXTMIND_API_KEY`
- `LLM_API_KEY`
- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`

### Base URL (Optional)
- `QWEN3_BASE_URL`
- `CONTEXTMIND_BASE_URL`
- `LLM_BASE_URL`
- `OPENAI_BASE_URL`
- `DEEPSEEK_BASE_URL`

### Model Name (Optional, default: Qwen3-32B)
- `QWEN3_MODEL`
- `LLM_MODEL`
- `OPENAI_MODEL`

### Other Parameters
- `LLM_TEMPERATURE` (default: 0.6)
- `LLM_MAX_TOKENS` (default: 8192)
- `LLM_TOP_K` (default: 20)
- `LLM_ACCESS_KEY` (for certain gateways)

## Using in Your Application

```python
from demos.llm_client import SimpleLLMClient, LLMConfig

# Option 1: Load from .env (recommended)
llm_client = SimpleLLMClient()

# Option 2: Manual configuration
config = LLMConfig(
    api_key="sk-your-key",
    base_url="http://your-server:port/v1",
    model="Qwen3-32B",
    temperature=0.6,
    max_tokens=8192
)
llm_client = SimpleLLMClient(config)

# Generate response
reasoning, response = llm_client.generate(prompt)
# or async version
reasoning, response = await llm_client.generate_async(prompt)
```

## Integration with ContextMind

The demo applications show the complete workflow:

```python
from contextmind import ContextEngine
from demos.callcenter_app import CallCenterApplication

# 1. Create ContextMind engine (context engineering)
engine = ContextEngine(app_name="my-app", user_id="user123")

# 2. Create application with LLM client
app = CallCenterApplication(
    context_engine=engine,
    use_real_llm=True  # Enable real LLM (default)
)

# 3. Process user input
response = await app.process_turn("Hello!")
# Internally:
#   - ContextEngine optimizes context (Steps 1-4)
#   - SimpleLLMClient calls LLM (Step 5)
#   - ContextEngine post-processes output (Step 6)
```

## Architecture Notes

- **ContextMind Framework**: Pure context engineering (no LLM dependencies)
- **Demo Applications**: Show how to integrate LLM calls
- **SimpleLLMClient**: Lightweight demo client (for production, consider your own implementation)

This separation ensures:
✅ ContextMind works with ANY LLM provider
✅ You control LLM selection and configuration
✅ Easy to swap or upgrade LLM without changing framework

## Troubleshooting

### "Missing API key" Error
Make sure `.env` file exists and contains `LLM_API_KEY` or one of the supported variants.

### Connection Errors
Check that `LLM_BASE_URL` points to a valid OpenAI-compatible endpoint.

### Import Errors
Install required package: `pip install openai`

### Using Without Real LLM
For testing without LLM access:
```bash
python interactive_demo.py --no-llm
```

This uses simulated responses instead of calling a real LLM.
