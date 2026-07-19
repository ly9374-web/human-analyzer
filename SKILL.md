---
name: lyskill
description: "根据聊天记录、笔记、描述、截图文本和其他来源材料，生成轻量的个人专属 Codex 技能。用于把关于某个人的材料通过 personabuilder.md、relationshipbuilder.md、memorybuilder.md、thinslicebuilder.md 转成 persona.md、relationship.md、memory.md、thinslice.md，以及可调用的 /{slug} 技能；适用于创建、配置、更新或验证人物侧写技能。"
---

# lyskill

`lyskill` 会为某个具体的人创建可复用的个人侧写技能。它不限于亲密关系，也可用于伴侣、朋友、同事、协作者、家人、客户，或来源材料中呈现的任何其他人物。

目标流程是：

```text
来源材料 -> 确认分析目标与背景 -> chat_parser.py -> chunk_text.py -> relationshipbuilder/memorybuilder 中间稿 -> relationship.md/memory.md -> personabuilder -> persona.md -> thinslicebuilder -> thinslice.md -> append_thinslice_to_persona.py -> persona.md -> {slug}/SKILL.md
```

生成的 `{slug}` 技能应能在 Codex 中通过 `/{slug}` 调用。

## 输入

支持的来源材料：

| 输入 | 处理方式 |
|---|---|
| 聊天导出 TXT/JSON | 先运行 `tools/chat_parser.py`，再运行 `tools/chunk_text.py` 分块 |
| 聊天截图 | 提取可见内容保存为文本，再运行 `tools/chunk_text.py` 分块 |
| 笔记、日记、文档、粘贴文本 | 保存为文本，再运行 `tools/chunk_text.py` 分块 |
| 用户描述 | 作为明确的补充上下文处理 |

不要强制所有输入都经过聊天解析器。只有当材料是结构化或半结构化聊天记录时，才使用 `tools/chat_parser.py`；所有长材料都应经过 `tools/chunk_text.py` 分块。

## 创建流程

### 第 1 步：接收来源材料

请用户提供原始材料。如果用户已经提供文件或粘贴文本，就直接基于这些材料继续。

整个流程都要保持材料依据。撰写中间侧写文件时，保留依据引用，例如文件名、分块文件、消息 id、时间范围，或用户提供的笔记；最终合并后的 `relationship.md` 和 `memory.md` 会删除独立的 `证据`、`来源` 字段。


### 第 2 步：询问两个必答问题

接收来源材料后、解析和分块前，询问用户：

1. 这份材料里应该分析谁？
2. 分析目标的核心身份与背景、以及与用户的已知关系/上下文是什么？

在这两个问题得到回答之前，不要生成最终侧写文件；除非用户明确表示无需补充、继续即可。

### 第 3 步：解析并按字数分块

问完两个必答问题后，如果材料是聊天导出，先把聊天材料解析成标准 JSON：

```bash
python3 tools/chat_parser.py --input "[input_path]" --format auto --output "partners/{slug}/parsed.json"
```

然后把解析后的可读文本按 15000 字左右分块：

```bash
python3 tools/chunk_text.py --input "partners/{slug}/parsed.json" --input-format parsed-json --chunk-size 15000 --output-dir "partners/{slug}/chunks" --prefix chunk
```

如果材料不是聊天导出，而是普通笔记、日记、文档粘贴文本或截图提取文本，则保存为文本文件后直接分块：

```bash
python3 tools/chunk_text.py --input "[text_input_path]" --input-format text --chunk-size 15000 --output-dir "partners/{slug}/chunks" --prefix chunk
```

分块规则：

- 按段落累加。
- 如果加入下一段会超过 15000 字，则在当前段落结束后切块。
- 如果单段本身超过 15000 字，则在超过 15000 字后的第一个句末切块。
- chunk 文件名使用 `chunk_001.md`、`chunk_002.md`、`chunk_003.md`。

单 chunk 上下文规则：

- 以 `partners/{slug}/chunks/` 下最终只有 `chunk_001.md` 一个文件作为判断标准。
- 如果只有一个 chunk，后续生成 `persona.md` 和 `thinslice.md` 时，除 `relationship.md`、`memory.md`、目标人物核心身份与背景外，还必须把用户输入记录作为补充上下文带入。
- 这里的“用户输入记录”指进入 `chunk_text.py` 前的可读材料：聊天导出使用解析后的可读记录或完整 `chunk_001.md` 内容；普通文本、笔记、截图提取文本使用原始可读文本或完整 `chunk_001.md` 内容。
- 单 chunk 补充上下文可以用于补充和校正 `relationship.md`、`memory.md` 中没有完整保留的细节；如果它与 `relationship.md`、`memory.md` 冲突，必须明确说明材料冲突或降低置信度，不要悄悄覆盖。
- 如果有两个或更多 chunk，后续 `persona.md` 和 `thinslice.md` 不读取用户输入记录、原始聊天、截图、parsed.json、chunk 文件或中间稿。

### 第 4 步：逐个 chunk 生成中间侧写

每个 chunk 单独走一遍 `relationshipbuilder.md` 和 `memorybuilder.md` 的生成流程。按顺序一个一个生成，不要同时生成。

中间文件输出到：

```text
partners/{slug}/intermediate/
├── relationship_001.md
├── memory_001.md
├── relationship_002.md
├── memory_002.md
└── ...
```

对 `chunk_001.md`：

1. 使用 `prompts/relationshipbuilder.md` 和 `chunk_001.md` -> 生成 `intermediate/relationship_001.md`
2. 使用 `prompts/memorybuilder.md` 和 `chunk_001.md` -> 生成 `intermediate/memory_001.md`

对 `chunk_002.md`、`chunk_003.md` 等重复同样流程，编号必须连续。即使某个 chunk 没有足够信息，也要生成对应编号的空结构中间文件，方便追溯和合并。

### 第 5 步：字段级拼接中间侧写

所有 chunk 都完成后，使用 Python 把中间稿字段级拼接为最终文档。合并先做同名 Markdown 字段下的顺序拼接，不去重、不重写、不额外总结，也不额外保留 chunk 来源标记；拼接完成后删除最终文档中的独立 `证据` 和 `来源` 字段及其内容，并把置信度保留为 `高`、`中` 或 `低`。

```bash
python3 tools/merge_profiles.py --input-dir "partners/{slug}/intermediate" --pattern "relationship_*.md" --output "partners/{slug}/relationship.md" --title "分关系互动侧写：[目标姓名]"
```

```bash
python3 tools/merge_profiles.py --input-dir "partners/{slug}/intermediate" --pattern "memory_*.md" --output "partners/{slug}/memory.md" --title "记忆档案：[目标姓名]"
```

### 第 6 步：生成 persona.md

在目标输出目录中生成这些文件：

```text
partners/{slug}/
├── parsed.json
├── chunks/
├── intermediate/
├── relationship.md
├── memory.md
└── persona.md
```

将最终合并后的 `relationship.md` 和 `memory.md` 作为输入，结合用户提供的目标人物核心身份与背景，调用 `prompts/personabuilder.md` -> 生成 `persona.md`。

默认情况下，`persona.md` 不读取原始聊天、截图、parsed.json、chunk 文件或中间稿，只读取最终合并后的 `relationship.md`、`memory.md` 和用户提供的核心身份与背景。

如果第 3 步最终只有一个 `chunk_001.md`，则生成 `persona.md` 时必须额外带入用户输入记录作为补充上下文。它可以补充和校正 `relationship.md`、`memory.md` 中没有完整保留的细节；若材料冲突，必须明确说明冲突或降低置信度，不要悄悄覆盖。

### 第 7 步：生成 thinslice.md 并拼接到 persona.md

在 `persona.md` 生成后，再把最终合并后的 `relationship.md` 和 `memory.md` 作为上下文，结合用户提供的目标人物核心身份与背景，调用 `prompts/thinslicebuilder.md` -> 生成 `partners/{slug}/thinslice.md`。

如果第 3 步最终只有一个 `chunk_001.md`，则生成 `thinslice.md` 时也必须额外带入用户输入记录作为补充上下文。它可以补充和校正 `relationship.md`、`memory.md` 中没有完整保留的细节；若材料冲突，必须用低置信度或谨慎措辞处理，不要悄悄覆盖。

`thinslice.md` 独立生成，但随后必须被拼接进 `persona.md` 末尾，成为 `persona.md` 的一部分。使用 Python 执行拼接：

```bash
python3 tools/append_thinslice_to_persona.py --persona "partners/{slug}/persona.md" --thinslice "partners/{slug}/thinslice.md"
```

拼接脚本应保持幂等：如果 `persona.md` 中已经有旧的薄片心理侧写区块，再次运行时替换旧区块，不重复追加。

`thinslicebuilder.md` 可以使用大五人格、if-then 情境反应句、特质激活理论和分关系双维度侧写；这些心理学框架只限于 `thinslicebuilder.md` 使用，不改变 `personabuilder.md` 的生成边界。

`thinslice.md` 的所有输出都必须有 `relationship.md`、`memory.md`、单 chunk 用户输入记录或用户明确提供背景支撑，但不要在正文中输出具体来源、证据或“根据什么判断”的文字；可以在判断后加入高/中/低置信度。

此步骤完成后，目标输出目录包含：

```text
partners/{slug}/
├── parsed.json
├── chunks/
├── intermediate/
├── relationship.md
├── memory.md
├── thinslice.md
└── persona.md
```

### 第 8 步：生成可调用技能

使用 `prompts/generate_slug_skill.md` 合并：

- `persona.md`（已拼接 `thinslice.md`）
- `relationship.md`
- `memory.md`
- 用户补充信息

推荐的 Codex 输出为：

```text
partners/{slug}/SKILL.md
```

文件头元数据中的 `name` 必须正好是 `{slug}`，这样技能才能通过以下方式调用：

```text
/{slug}
```

如果用户特别要求单个命名文件，也可以允许 `{slug}skill.md`，但要说明标准 Codex 技能发现机制期望的是包含 `SKILL.md` 的文件夹。

## 生成的技能文件规则

生成的 `{slug}/SKILL.md` 应是紧凑的控制器，而不是所有材料的复制。它应说明何时读取本地支持文件：

| 文件 | 何时读取 |
|---|---|
| `persona.md` | 默认优先参考。用于表达风格、人格结构、偏好、边界、反应模式、稳定特质，以及已拼接的薄片心理侧写。 |
| `relationship.md` | 用于互动策略、沟通建议、关系动态、请求、反馈、修复、节奏和边界设定。 |
| `memory.md` | 用于过去事件、长期偏好、重要经历、重复模式和具体事实核查。 |

如果不确定哪个文件适用，先读 `persona.md`，再根据用户问题需要读取 `relationship.md` 或 `memory.md`。复杂问题按以下顺序综合：

```text
persona -> relationship -> memory
```

当本地文件包含具体材料时，不要只凭通用心理学回答。

## Codex 与 API 用法差异

在 Codex 或 Claude Code 风格的技能环境中，生成的技能可以指示代理读取本地文件，例如 `persona.md`、`relationship.md` 和 `memory.md`。

在普通 API 调用或通用网页聊天界面中，模型不会因为提示词提到本地文件就自动看到这些文件。外层应用必须把文件内容注入对话，或提供文件读取工具。

生成最终说明时要利用这个区别：

- Codex 技能：把文件读取规则写入 `SKILL.md`。
- 普通 API 或网页模型：在 system/user 上下文中包含或注入相关文件内容。

## 材料规则
- 不要编造事实、原话、动机、诊断或记忆。
- 清楚区分材料中观察到的内容、用户提供的说法和推断。
- 当材料薄弱或互相冲突时，要明确说明。
- 保持生成的侧写实用且有依据。除非材料支持且能帮助用户，否则避免过重的心理学理论。
