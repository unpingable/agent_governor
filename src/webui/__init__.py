"""
WebUI Adapter: OpenAI-compatible API that wraps Ollama with Governor integration.

This adapter presents a standard OpenAI API surface that Open WebUI (or any
compatible client) can connect to. Underneath, it:
1. Routes requests to Ollama
2. Can inject fiction-governor constraints
3. Tracks conversation state for canon/continuity checking
"""

__version__ = "0.1.0"
