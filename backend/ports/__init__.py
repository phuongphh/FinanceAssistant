"""Ports — abstract interfaces the service layer depends on.

Services program against the ports (``Notifier``, later ``LLM``,
``Cache``, ...) rather than importing concrete adapter modules like
``telegram_service``. This keeps domain services:
- testable without mocking HTTP (swap in a fake adapter)
- swappable (send via email / SMS / web push by adding a new adapter)
- free of transport concerns that don't belong in business logic

See docs/strategy/scaling-refactor-B.md §B3.
"""
