#!/usr/bin/env python3
"""
把 chat_parser.py 的输出或普通文本切成固定字数附近的 chunk。

分块策略：
  - 优先按段落累加。
  - 如果加入下一段会超过限制，就在上一段结束处切块。
  - 如果单段本身超过限制，则在超过限制后的第一个句末切块。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SENTENCE_END_RE = re.compile(r"[。！？!?；;．.]\s*|[\r\n]+")


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


def parsed_json_to_text(data: dict[str, Any]) -> str:
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError("解析 JSON 中缺少 messages 列表")

    paragraphs = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        msg_id = message.get("id", "unknown")
        timestamp = message.get("timestamp") or "未知时间"
        sender = message.get("sender") or "未知"
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        paragraphs.append(f"[{msg_id}] {timestamp} {sender}: {content}")

    return "\n\n".join(paragraphs)


def read_input(path: Path, input_format: str) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if input_format == "text":
        return text
    if input_format == "parsed-json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("parsed-json 输入必须是 JSON 对象")
        return parsed_json_to_text(data)
    if input_format == "auto":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(data, dict) and "messages" in data:
            return parsed_json_to_text(data)
        return text
    raise ValueError(f"未知输入格式：{input_format}")


def split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if paragraphs:
        return paragraphs
    return [line.strip() for line in text.splitlines() if line.strip()]


def split_long_paragraph(paragraph: str, limit: int) -> list[str]:
    pieces = []
    rest = paragraph.strip()

    while len(rest) > limit:
        search_from = limit
        match = SENTENCE_END_RE.search(rest, search_from)
        if match:
            cut_at = match.end()
        else:
            cut_at = len(rest)
        pieces.append(rest[:cut_at].strip())
        rest = rest[cut_at:].strip()

    if rest:
        pieces.append(rest)

    return pieces


def chunk_text(text: str, limit: int) -> list[str]:
    if limit <= 0:
        raise ValueError("--chunk-size 必须大于 0")

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in split_paragraphs(text):
        pieces = split_long_paragraph(paragraph, limit)
        for piece in pieces:
            piece_len = len(piece)
            separator_len = 2 if current else 0

            if current and current_len + separator_len + piece_len > limit:
                chunks.append("\n\n".join(current).strip())
                current = []
                current_len = 0

            current.append(piece)
            current_len += (2 if current_len else 0) + piece_len

    if current:
        chunks.append("\n\n".join(current).strip())

    return chunks


def write_chunks(chunks: list[str], output_dir: Path, prefix: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    width = max(3, len(str(len(chunks))))

    for index, chunk in enumerate(chunks, start=1):
        chunk_id = f"{index:0{width}d}"
        output_path = output_dir / f"{prefix}_{chunk_id}.md"
        output_path.write_text(chunk + "\n", encoding="utf-8")


def main() -> None:
    parser = ChineseArgumentParser(description="按段落和句末把输入材料分成 chunk")
    parser.add_argument("--input", required=True, metavar="输入文件", help="输入文件路径")
    parser.add_argument("--output-dir", required=True, metavar="输出目录", help="chunk 输出目录")
    parser.add_argument(
        "--input-format",
        choices=["auto", "parsed-json", "text"],
        default="auto",
        help="输入格式。默认自动识别 chat_parser.py 产物。",
    )
    parser.add_argument("--chunk-size", type=int, default=15000, metavar="字数", help="每个 chunk 的目标字数。默认 15000。")
    parser.add_argument("--prefix", default="chunk", metavar="文件前缀", help="输出文件前缀。默认 chunk。")

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"错误：输入文件不存在：{input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        text = read_input(input_path, args.input_format)
        chunks = chunk_text(text, args.chunk_size)
        write_chunks(chunks, Path(args.output_dir), args.prefix)
    except Exception as exc:
        print(f"错误：分块失败：{exc}", file=sys.stderr)
        sys.exit(1)

    print(f"已生成 {len(chunks)} 个 chunk -> {args.output_dir}")


if __name__ == "__main__":
    main()
