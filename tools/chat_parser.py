#!/usr/bin/env python3
"""
lyskill 聊天记录解析器。

本工具会把聊天导出标准化为稳定的 JSON 结构，供后续分块总结使用。
它不会调用 LLM，也不会做最终人格判断。

支持格式：
  - 微信 TXT 导出
  - 微信/PyWxDump 风格 JSON 导出
  - 通用 TXT 行，例如 "[time] sender: content" 或 "sender: content"

示例：
    python3 chat_parser.py --input chat.txt --format auto --output parsed.json
    python3 chat_parser.py --input chat.json --format wechat-json --output parsed.json
    python3 chat_parser.py --input messages.txt --format generic --chunk-size 100
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


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


WECHAT_TXT_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.+?)\s*\n([\s\S]*?)(?=\n\d{4}-\d{2}-\d{2}|\Z)",
    re.MULTILINE,
)

GENERIC_PATTERNS = [
    re.compile(
        r"^\[(\d{4}[-/]\d{2}[-/]\d{2}[T\s]\d{2}:\d{2}(?::\d{2})?)\]\s+(.+?):\s+(.+)$"
    ),
    re.compile(
        r"^(.+?)\s+(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\n(.+)$",
        re.MULTILINE,
    ),
    re.compile(r"^(.+?):\s+(.+)$"),
]

KEYWORDS = {
    "positive": ["爱你", "喜欢", "开心", "高兴", "谢谢", "感谢", "好的", "棒", "太好了", "哈哈", "嘻嘻", "❤", "😊", "😍"],
    "negative": ["生气", "难过", "伤心", "烦", "讨厌", "不想", "算了", "随便", "无所谓", "😢", "😡", "😤"],
    "conflict": ["为什么", "凭什么", "你总是", "你从来", "你根本", "不理我", "冷战", "分手"],
    "affection": ["想你", "想见你", "抱抱", "亲亲", "宝贝", "宝宝", "老婆", "老公", "亲爱的"],
}


def make_message(
    sender: str,
    content: str,
    timestamp: Optional[str] = None,
    msg_type: str = "text",
) -> dict[str, Any]:
    return {
        "sender": sender.strip() if sender else "未知",
        "content": str(content).strip(),
        "timestamp": normalize_timestamp(timestamp),
        "type": str(msg_type or "text"),
    }


def normalize_timestamp(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)

    text = str(value).strip()
    if not text:
        return None

    return text.replace("/", "-").replace("T", " ")


def parse_wechat_txt(text: str) -> list[dict[str, Any]]:
    messages = []
    for match in WECHAT_TXT_PATTERN.finditer(text):
        timestamp = match.group(1)
        sender = match.group(2)
        content = match.group(3)
        if content.strip():
            messages.append(make_message(sender, content, timestamp))
    return messages


def parse_wechat_json(data: list[Any] | dict[str, Any]) -> list[dict[str, Any]]:
    messages = []
    if isinstance(data, dict):
        data = data.get("messages", data.get("data", []))

    if not isinstance(data, list):
        return messages

    for item in data:
        if not isinstance(item, dict):
            continue
        sender = item.get("sender", item.get("from", item.get("nickname", "未知")))
        content = item.get("content", item.get("msg", item.get("text", "")))
        timestamp = item.get("timestamp", item.get("create_time", item.get("time")))
        msg_type = item.get("type", "text")
        if str(content).strip():
            messages.append(make_message(sender, content, timestamp, msg_type))

    return messages


def parse_generic_txt(text: str) -> list[dict[str, Any]]:
    messages = []
    lines = text.strip().splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        matched = False
        for pattern in GENERIC_PATTERNS[:2]:
            match = pattern.match(line)
            if not match:
                continue
            groups = match.groups()
            if len(groups) == 3:
                if line.startswith("["):
                    timestamp, sender, content = groups
                else:
                    sender, timestamp, content = groups
                messages.append(make_message(sender, content, timestamp))
                matched = True
                break

        if matched:
            continue

        match = GENERIC_PATTERNS[2].match(line)
        if match:
            sender, content = match.group(1), match.group(2)
            messages.append(make_message(sender, content))

    return messages


def detect_format(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return "wechat-json"
    if suffix in (".txt", ".md"):
        content = file_path.read_text(encoding="utf-8", errors="replace")[:2000]
        if re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\S", content):
            return "wechat-txt"
        return "generic"
    return "generic"


def add_message_ids(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for index, message in enumerate(messages, start=1):
        normalized.append(
            {
                "id": f"m{index:06d}",
                "sender": message.get("sender", "未知"),
                "content": message.get("content", ""),
                "timestamp": message.get("timestamp"),
                "type": message.get("type", "text"),
                "is_partner": None,
            }
        )
    return normalized


def build_participants(messages: list[dict[str, Any]], my_name: str) -> list[dict[str, Any]]:
    counts = Counter(message.get("sender", "未知") for message in messages)
    participants = []

    for name, count in counts.most_common():
        possible_role = "unknown"
        if my_name and name == my_name:
            possible_role = "self"
        elif my_name:
            possible_role = "target_candidate"

        participants.append(
            {
                "name": name,
                "message_count": count,
                "possible_role": possible_role,
            }
        )

    return participants


def build_stats(messages: list[dict[str, Any]]) -> dict[str, Any]:
    timestamps = [
        message.get("timestamp")
        for message in messages
        if message.get("timestamp")
    ]
    senders = [message.get("sender", "未知") for message in messages]
    keyword_counts = {
        group: sum(
            1
            for message in messages
            if any(keyword in message.get("content", "") for keyword in keywords)
        )
        for group, keywords in KEYWORDS.items()
    }

    return {
        "total_messages": len(messages),
        "date_range": {
            "start": min(timestamps) if timestamps else None,
            "end": max(timestamps) if timestamps else None,
        },
        "top_senders": [
            {"name": name, "message_count": count}
            for name, count in Counter(senders).most_common()
        ],
        "keyword_counts": keyword_counts,
        "conversation_initiations": build_conversation_initiations(messages),
        "analysis_hints": build_analysis_hints(messages, keyword_counts),
    }


def build_conversation_initiations(messages: list[dict[str, Any]]) -> dict[str, int]:
    initiations: Counter[str] = Counter()
    previous_sender = None

    for message in messages:
        sender = message.get("sender", "未知")
        if previous_sender is None or sender != previous_sender:
            initiations[sender] += 1
        previous_sender = sender

    return dict(initiations)


def build_analysis_hints(
    messages: list[dict[str, Any]],
    keyword_counts: dict[str, int],
) -> list[str]:
    hints = []
    total = max(len(messages), 1)

    if keyword_counts.get("conflict", 0) / total > 0.05:
        hints.append(
            "冲突关键词出现频率较高；后续总结时应检查具体语境，不要直接推断人格。"
        )

    if keyword_counts.get("affection", 0) > 10:
        hints.append(
            "亲密或肯定类表达出现较多；后续总结时应区分玩笑、习惯用语和真实偏好。"
        )

    sender_counts = Counter(message.get("sender", "未知") for message in messages)
    if len(sender_counts) > 2:
        hints.append(
            "材料中有三位或更多参与者；生成画像前必须向用户确认目标分析对象。"
        )

    if len(sender_counts) == 2:
        counts = sender_counts.most_common()
        smaller_ratio = counts[-1][1] / total
        if smaller_ratio < 0.2:
            hints.append(
                "双方消息数量明显不均衡；后续只应把它作为互动分布信号，不应直接推断性格。"
            )

    return hints


def build_chunk_plan(
    messages: list[dict[str, Any]],
    chunk_size: int,
) -> list[dict[str, Any]]:
    if chunk_size <= 0:
        raise ValueError("--chunk-size 必须大于 0")

    chunks = []
    for start in range(0, len(messages), chunk_size):
        end = min(start + chunk_size, len(messages))
        chunk_messages = messages[start:end]
        if not chunk_messages:
            continue
        chunks.append(
            {
                "chunk_id": f"c{len(chunks) + 1:03d}",
                "message_start_id": chunk_messages[0]["id"],
                "message_end_id": chunk_messages[-1]["id"],
                "approx_message_count": len(chunk_messages),
            }
        )
    return chunks


def parse_input(input_path: Path, fmt: str) -> tuple[str, list[dict[str, Any]]]:
    detected_format = detect_format(input_path) if fmt == "auto" else fmt

    if detected_format == "wechat-json":
        data = json.loads(input_path.read_text(encoding="utf-8", errors="replace"))
        messages = parse_wechat_json(data)
    elif detected_format == "wechat-txt":
        text = input_path.read_text(encoding="utf-8", errors="replace")
        messages = parse_wechat_txt(text)
    else:
        text = input_path.read_text(encoding="utf-8", errors="replace")
        messages = parse_generic_txt(text)

    return detected_format, messages


def build_output(
    fmt: str,
    messages: list[dict[str, Any]],
    my_name: str,
    chunk_size: int,
) -> dict[str, Any]:
    normalized_messages = add_message_ids(messages)
    return {
        "format": fmt,
        "participants": build_participants(normalized_messages, my_name),
        "messages": normalized_messages,
        "stats": build_stats(normalized_messages),
        "chunk_plan": build_chunk_plan(normalized_messages, chunk_size),
    }


def main() -> None:
    parser = ChineseArgumentParser(add_help=False, description="为 lyskill 标准化聊天记录")
    parser.add_argument("-h", "--help", action="help", help="显示帮助信息并退出")
    parser.add_argument("--input", required=True, metavar="输入文件", help="输入聊天文件路径")
    parser.add_argument(
        "--format",
        metavar="格式",
        default="auto",
        choices=["auto", "wechat-txt", "wechat-json", "generic"],
        help="输入格式。默认自动检测。",
    )
    parser.add_argument("--output", metavar="输出文件", help="输出 JSON 路径。默认输出到标准输出。")
    parser.add_argument("--my-name", default="我", metavar="我的名称", help="如存在，应标记为 `self` 的发送者名称。")
    parser.add_argument("--chunk-size", type=int, default=200, metavar="分块大小", help="每个分块的大致消息数。默认 200。")

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"错误：输入文件不存在：{input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        fmt, raw_messages = parse_input(input_path, args.format)
        result = build_output(fmt, raw_messages, args.my_name, args.chunk_size)
    except Exception as exc:
        print(f"错误：解析聊天记录失败：{exc}", file=sys.stderr)
        sys.exit(1)

    output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"已解析 {len(result['messages'])} 条消息 -> {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
