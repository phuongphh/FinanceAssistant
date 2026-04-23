"""Background workers — consume work enqueued by routers.

Routers that receive user-facing traffic (webhooks) should do the
minimum needed to return 200 quickly, then hand off to a worker via
``asyncio.create_task``. The worker owns the transaction and calls
services/handlers.

See docs/strategy/scaling-refactor-A.md for the overall runtime path.
"""
