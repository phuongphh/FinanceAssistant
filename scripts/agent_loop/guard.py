"""Guard: chặn patch của agent đụng vào vùng cấm trước khi push.

Chạy trong job ``publish`` (job có PAT) trên patch đã ``git apply --index``,
nên dù agent bị prompt-injection cũng không thể đẩy thay đổi vào ``.env``,
``.github/workflows/**`` hay sửa migration đã apply.

Input là output của ``git diff --cached --name-status -M <base>`` và
``git diff --cached -U0 <base>`` (để tìm conflict marker còn sót).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from agent_loop.config import LoopConfig

_CONFLICT_MARKERS = ("+<<<<<<< ", "+>>>>>>> ", "+<<<<<<<\n", "+>>>>>>>\n")


@dataclass
class GuardResult:
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_markdown(self) -> str:
        if not self.violations and not self.warnings:
            return "### 🛡️ Guard\n\n✅ Không đụng vùng cấm.\n"
        lines = ["### 🛡️ Guard", ""]
        lines += [f"- ❌ {v}" for v in self.violations]
        lines += [f"- ⚠️ {w}" for w in self.warnings]
        return "\n".join(lines) + "\n"


def matches(path: str, patterns: Iterable[str]) -> bool:
    """Pattern không chứa ``/`` so với basename (``.env.*`` bắt mọi thư mục);
    pattern có ``/`` so với full path (``**`` hoạt động như ``*`` của fnmatch)."""
    name = PurePosixPath(path).name
    for pattern in patterns:
        target = path if "/" in pattern else name
        if fnmatch.fnmatchcase(target, pattern):
            return True
        # "dir/**" cũng phải bắt chính các file nằm sâu bên trong dir.
        if pattern.endswith("/**") and path.startswith(pattern[:-2]):
            return True
    return False


def parse_name_status(lines: Iterable[str]) -> list[tuple[str, str]]:
    """``M\\tpath`` / ``R100\\told\\tnew`` → [(status, path)].

    Rename/copy được tách thành xoá path cũ (chỉ với R) + thêm path mới,
    để không lách được guard bằng cách đổi tên file cấm.
    """
    changes: list[tuple[str, str]] = []
    for raw in lines:
        parts = raw.rstrip("\n").split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        status = parts[0][0]
        if status in "RC" and len(parts) >= 3:
            if status == "R":
                changes.append(("D", parts[1]))
            changes.append(("A", parts[2]))
        else:
            changes.append((status, parts[1]))
    return changes


def check(
    name_status_lines: Iterable[str],
    cfg: LoopConfig,
    diff_text: str = "",
    existed_in_base: Callable[[str], bool] | None = None,
) -> GuardResult:
    """``existed_in_base(path)`` cho biết file immutable đã có trên base branch
    chưa. File do chính PR này thêm (chưa merge, chưa apply) thì được sửa —
    cần cho mode fix, khi agent sửa migration nó vừa tạo ở lần trước."""
    result = GuardResult()
    for status, path in parse_name_status(name_status_lines):
        if matches(path, cfg.forbidden_paths) and not matches(path, cfg.allowed_paths):
            result.violations.append(f"`{path}` nằm trong vùng cấm (status {status})")
            continue
        if matches(path, cfg.immutable_existing):
            if status == "A" or (existed_in_base is not None and not existed_in_base(path)):
                result.warnings.append(f"`{path}` là file mới trong vùng immutable — review kỹ")
            else:
                result.violations.append(
                    f"`{path}` đã tồn tại và không được sửa/xoá (status {status})"
                )
    for line in diff_text.splitlines(keepends=True):
        if line.startswith(_CONFLICT_MARKERS):
            result.violations.append("Patch còn conflict marker (`<<<<<<<`/`>>>>>>>`)")
            break
    return result
