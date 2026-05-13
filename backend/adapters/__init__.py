"""Transport adapters — concrete implementations of the ports.

Each adapter wraps one external system (Telegram, Notion, DeepSeek,
Anthropic, Gmail, ...). Services depend on the abstract port in
``backend/ports/``, never on these modules directly.
"""
