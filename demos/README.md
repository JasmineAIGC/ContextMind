# ContextMind Demos

This directory contains all demonstration and example code for ContextMind v6.0.

## Directory Structure

```
demos/
├── basic/           # Basic usage demos
├── advanced/        # Advanced plugin usage examples
└── applications/    # Sample application templates
```

## Basic Demos (`basic/`)

Simple demonstrations of core ContextMind functionality:

- **interactive_demo.py** - Interactive CLI demo for testing context engineering
- **gradio_demo.py** - Web UI demo using Gradio
- **chat_interactive_demo.py** - Interactive chat mode demo
- **chat_gradio_demo.py** - Chat mode with Gradio web UI

## Advanced Demos (`advanced/`)

Advanced usage patterns and plugin customization:

- **plugin_examples.py** - Demonstrates custom plugin registration and usage

## Applications (`applications/`)

Sample application templates showing real-world usage:

- **callcenter_app.py** - Call center customer service application
- **chat_app.py** - General chat application

## Usage

Each demo is self-contained and can be run directly:

```bash
# Basic demos
python demos/basic/interactive_demo.py
python demos/basic/gradio_demo.py

# Advanced demos
python demos/advanced/plugin_examples.py

# Sample applications
python demos/applications/callcenter_app.py
python demos/applications/chat_app.py
```

## v6.0 Architecture

All demos use the clean v6.0 ContextMind architecture:
- Pure context engineering framework (Steps 1-4 + 6)
- LLM invocation (Step 5) handled externally
- Modular plugin system for all components
