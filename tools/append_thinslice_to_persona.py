#!/usr/bin/env python3
"""
把 thinslice.md 作为稳定区块拼接到 persona.md 末尾。

脚本保持幂等：再次运行会替换旧的薄片心理侧写区块，而不是重复追加。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_MARKER = "<!-- thinslice:start -->"
DEFAULT_END_MARKER = "<!-- thinslice:end -->"


class ChineseArgumentParser(argparse.ArgumentParser):
    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法：", 1)

    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "用法：", 1)
            .replace("\noptions:\n", "\n选项：\n")
        )


def build_block(thinslice: str, marker: str, end_marker: str) -> str:
    cleaned = thinslice.strip()
    return f"{marker}\n\n{cleaned}\n\n{end_marker}"


def replace_or_append(persona: str, block: str, marker: str, end_marker: str) -> str:
    pattern = re.compile(
        rf"\n*{re.escape(marker)}.*?{re.escape(end_marker)}\s*",
        flags=re.DOTALL,
    )

    if pattern.search(persona):
        updated = pattern.sub(f"\n\n{block}\n", persona).rstrip()
    else:
        updated = f"{persona.rstrip()}\n\n{block}"

    return updated.rstrip() + "\n"


def main() -> None:
    parser = ChineseArgumentParser(description="把 thinslice.md 拼接到 persona.md 末尾")
    parser.add_argument("--persona", required=True, metavar="PERSONA", help="persona.md 路径")
    parser.add_argument("--thinslice", required=True, metavar="THINSLICE", help="thinslice.md 路径")
    parser.add_argument(
        "--marker",
        default=DEFAULT_MARKER,
        metavar="MARKER",
        help="薄片侧写区块起始标记",
    )
    parser.add_argument(
        "--end-marker",
        default=DEFAULT_END_MARKER,
        metavar="END_MARKER",
        help="薄片侧写区块结束标记",
    )

    args = parser.parse_args()
    persona_path = Path(args.persona)
    thinslice_path = Path(args.thinslice)

    if not persona_path.exists():
        print(f"错误：persona 文件不存在：{persona_path}", file=sys.stderr)
        sys.exit(1)

    if not thinslice_path.exists():
        print(f"错误：thinslice 文件不存在：{thinslice_path}", file=sys.stderr)
        sys.exit(1)

    try:
        persona = persona_path.read_text(encoding="utf-8", errors="replace")
        thinslice = thinslice_path.read_text(encoding="utf-8", errors="replace")
        block = build_block(thinslice, args.marker, args.end_marker)
        persona_path.write_text(
            replace_or_append(persona, block, args.marker, args.end_marker),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"错误：拼接失败：{exc}", file=sys.stderr)
        sys.exit(1)

    print(f"已拼接 {thinslice_path} -> {persona_path}")


if __name__ == "__main__":
    main()
