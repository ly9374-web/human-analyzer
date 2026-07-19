#!/usr/bin/env python3
"""
按 Markdown 标题字段合并 relationship_001.md / memory_001.md 等中间稿。

本工具只做字段级拼接，不做去重、改写、重排结论或智能综合。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
REMOVED_FIELD_RE = re.compile(r"^(\s*)(证据|来源)\s*:\s*.*$")
CONFIDENCE_SOURCE_RE = re.compile(r"^(\s*置信度\s*:\s*)(['\"]?)(高|中|低)(?:（来源：.*?）)?\2\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


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


def split_sections(markdown: str) -> OrderedDict[tuple[tuple[int, str], ...], list[str]]:
    sections: OrderedDict[tuple[tuple[int, str], ...], list[str]] = OrderedDict()
    path: list[tuple[int, str]] = []
    current_key: tuple[tuple[int, str], ...] | None = None

    for line in markdown.splitlines():
        match = HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()

            if level == 1:
                current_key = None
                path = []
                continue

            path = [item for item in path if item[0] < level]
            path.append((level, title))
            current_key = tuple(path)
            sections.setdefault(current_key, [])
            continue

        if current_key is None:
            continue

        sections.setdefault(current_key, []).append(line)

    return sections


def merge_sections(files: list[Path]) -> OrderedDict[tuple[tuple[int, str], ...], list[str]]:
    merged: OrderedDict[tuple[tuple[int, str], ...], list[str]] = OrderedDict()

    for file_path in files:
        sections = split_sections(file_path.read_text(encoding="utf-8", errors="replace"))
        for key, lines in sections.items():
            cleaned = "\n".join(lines).strip()
            merged.setdefault(key, [])
            if cleaned:
                merged[key].append(cleaned)
            elif not merged[key]:
                merged[key].append("")

    return merged


def render_merged(
    title: str,
    merged: OrderedDict[tuple[tuple[int, str], ...], list[str]],
) -> str:
    output: list[str] = [f"# {title}".rstrip(), ""]
    emitted: set[tuple[tuple[int, str], ...]] = set()

    for key, bodies in merged.items():
        for depth in range(1, len(key) + 1):
            heading_key = key[:depth]
            if heading_key in emitted:
                continue
            level, heading = heading_key[-1]
            output.append(f"{'#' * level} {heading}")
            output.append("")
            emitted.add(heading_key)

        non_empty_bodies = [body for body in bodies if body.strip()]
        if non_empty_bodies:
            output.append("\n\n".join(non_empty_bodies).strip())
            output.append("")

    return "\n".join(output).rstrip() + "\n"


def strip_evidence_and_source_fields(markdown: str) -> str:
    output: list[str] = []
    lines = markdown.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        if is_table_header(lines, index):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            output.extend(strip_removed_table_columns(table_lines))
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match and heading_match.group(2).strip() in {"证据", "来源"}:
            level = len(heading_match.group(1))
            index += 1
            while index < len(lines):
                next_heading = HEADING_RE.match(lines[index])
                if next_heading and len(next_heading.group(1)) <= level:
                    break
                index += 1
            continue

        field_match = REMOVED_FIELD_RE.match(line)
        if field_match:
            base_indent = len(field_match.group(1))
            index += 1
            while index < len(lines):
                next_line = lines[index]
                if not next_line.strip():
                    index += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent > base_indent:
                    index += 1
                    continue
                break
            continue

        confidence_match = CONFIDENCE_SOURCE_RE.match(line)
        if confidence_match:
            prefix, quote, level = confidence_match.groups()
            line = f"{prefix}{quote}{level}{quote}"

        output.append(line)
        index += 1

    return "\n".join(output).rstrip() + "\n"


def is_table_header(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].lstrip().startswith("|")
        and TABLE_SEPARATOR_RE.match(lines[index + 1]) is not None
    )


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_table_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def strip_removed_table_columns(table_lines: list[str]) -> list[str]:
    header = split_table_row(table_lines[0])
    removed_indexes = {
        index for index, cell in enumerate(header) if "证据" in cell or "来源" in cell
    }
    if not removed_indexes:
        return table_lines

    cleaned: list[str] = []
    for row_index, line in enumerate(table_lines):
        cells = split_table_row(line)
        kept_cells = [
            cell for cell_index, cell in enumerate(cells) if cell_index not in removed_indexes
        ]
        if row_index == 1:
            kept_cells = ["---" for _ in kept_cells]
        cleaned.append(render_table_row(kept_cells))
    return cleaned


def collect_input_files(input_dir: Path, pattern: str) -> list[Path]:
    files = sorted(input_dir.glob(pattern))
    return [file_path for file_path in files if file_path.is_file()]


def main() -> None:
    parser = ChineseArgumentParser(description="字段级拼接中间 relationship/memory 文档")
    parser.add_argument("--input-dir", required=True, metavar="输入目录", help="中间稿目录")
    parser.add_argument("--pattern", required=True, metavar="匹配模式", help="例如 relationship_*.md")
    parser.add_argument("--output", required=True, metavar="输出文件", help="合并后的输出文件")
    parser.add_argument("--title", required=True, metavar="标题", help="输出文档一级标题")

    args = parser.parse_args()
    input_dir = Path(args.input_dir)

    if not input_dir.exists():
        print(f"错误：输入目录不存在：{input_dir}", file=sys.stderr)
        sys.exit(1)

    files = collect_input_files(input_dir, args.pattern)
    if not files:
        print(f"错误：没有找到匹配文件：{input_dir / args.pattern}", file=sys.stderr)
        sys.exit(1)

    try:
        merged = merge_sections(files)
        output = strip_evidence_and_source_fields(render_merged(args.title, merged))
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    except Exception as exc:
        print(f"错误：合并失败：{exc}", file=sys.stderr)
        sys.exit(1)

    print(f"已合并 {len(files)} 个文件 -> {args.output}")


if __name__ == "__main__":
    main()
