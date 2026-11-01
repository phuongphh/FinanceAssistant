"""Agent Loop — tự động hoá vòng issue → code → PR → merge.

Package được gọi bằng ``PYTHONPATH=scripts python -m agent_loop.cli <lệnh>``
từ repo root. Thiết kế: ``docs/architecture/loop-engineering.md``.

Tách thành 3 lớp để test được mà không cần GitHub:
- ``config`` / ``selection`` / ``guard``: hàm thuần, không I/O mạng.
- ``github_api``: bọc ``gh api`` (subprocess), thay bằng fake khi test.
- ``cli``: ghép mọi thứ, đọc env của GitHub Actions.
"""
