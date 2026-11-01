"""Cho phép ``import agent_loop`` (package nằm ở ``scripts/agent_loop``).

Không dùng tên ``scripts`` làm package vì đụng ``backend/scripts``.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
