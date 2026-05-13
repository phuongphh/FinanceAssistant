"""Intent handler implementations.

Concrete handlers live in their own module; the package is split this
way so a new handler can be dropped in without touching a manifest
file. The dispatcher imports them lazily to avoid a startup-time DB
session attach.
"""
