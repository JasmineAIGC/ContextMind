# ContextMind Demos

This directory contains example code for ContextMind v7.2.

## Files

All demonstration files are in the `demos/` directory with a **flat structure** (no subdirectories):

- **plugin_examples.py** - Demonstrates custom plugin registration and usage
- **callcenter_app.py** - Call center customer service application template
- **chat_app.py** - General chat application template

## Root Demo Files

Four main demo files are located at the **repository root** for easy access:

- **interactive_demo.py** - Interactive CLI demo for testing context engineering
- **gradio_demo.py** - Web UI demo using Gradio
- **chat_interactive_demo.py** - Interactive chat mode demo
- **chat_gradio_demo.py** - Chat mode with Gradio web UI

## Usage

Each demo is self-contained and can be run directly:

```bash
# Root demos (in repository root directory)
python interactive_demo.py
python gradio_demo.py
python chat_interactive_demo.py
python chat_gradio_demo.py

# Example code (in demos/ directory)
python demos/plugin_examples.py
python demos/callcenter_app.py
python demos/chat_app.py
```

## v7.2 Architecture

All demos use the clean v7.2 ContextMind architecture:
- Pure context engineering framework (Steps 1-4 + 6)
- LLM invocation (Step 5) handled externally by user code
- Modular plugin system for all components (extractors, retrievers, updaters)
- Flat directory structure - no unnecessary nesting
