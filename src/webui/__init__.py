"""
WebUI Adapter: OpenAI-compatible API with switchable backends and Governor integration.

This adapter presents a standard OpenAI API surface that Open WebUI (or any
compatible client) can connect to. Underneath, it:
1. Routes requests through ChatBridge to Anthropic or Ollama
2. Applies governor hooks based on context mode (fiction, code, nonfiction)
3. Maintains isolated governor contexts per user/project
"""

__version__ = "0.2.0"
