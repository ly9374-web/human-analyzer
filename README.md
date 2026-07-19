# lyskill
调用skill后上传聊天记录即可分析。（可以在微信中选中聊天记录，点击多选，复制粘贴记录）

`lyskill` is a lightweight workflow for turning source material about a specific person into a reusable Codex skill.

It can work from chat exports, screenshots converted to text, notes, diaries, pasted text, or user-provided background. The generated skill can then be invoked by slug, such as `/ly` or `/yuanyun`, and will answer using local profile files instead of generic personality advice.

## What It Generates

For each target person, `lyskill` creates a folder under `partners/{slug}/`:

```text
partners/{slug}/
├── chunks/
├── intermediate/
├── relationship.md
├── memory.md
├── thinslice.md
├── persona.md
└── SKILL.md
```

- `relationship.md` records interaction patterns, communication strategy, repair style, boundaries, and relationship-specific advice.
- `memory.md` records durable facts, events, preferences, repeated patterns, and concrete details.
- `persona.md` records the stable person profile and includes the appended thin-slice psychological profile.
- `SKILL.md` is the compact Codex controller that tells future agents when to read each supporting file.

## Workflow

```text
source material
-> confirm target person and background
-> parse or chunk material
-> generate relationship/memory intermediate drafts per chunk
-> merge relationship.md and memory.md
-> generate persona.md
-> generate thinslice.md
-> append thinslice.md into persona.md
-> generate partners/{slug}/SKILL.md
```

Before generating final profile files, the workflow asks two required questions:

1. Who should be analyzed in the material?
2. What is this person's core identity/background and known relationship to the user?

## Input Handling

Use the chat parser only for structured or semi-structured chat exports:

```bash
python3 tools/chat_parser.py --input "[input_path]" --format auto --output "partners/{slug}/parsed.json"
```

Then chunk parsed chat:

```bash
python3 tools/chunk_text.py --input "partners/{slug}/parsed.json" --input-format parsed-json --chunk-size 15000 --output-dir "partners/{slug}/chunks" --prefix chunk
```

For normal notes, pasted text, diaries, or screenshot text, chunk the readable text directly:

```bash
python3 tools/chunk_text.py --input "[text_input_path]" --input-format text --chunk-size 15000 --output-dir "partners/{slug}/chunks" --prefix chunk
```

## Merge Commands

After generating per-chunk intermediate files, merge them into final profile documents:

```bash
python3 tools/merge_profiles.py --input-dir "partners/{slug}/intermediate" --pattern "relationship_*.md" --output "partners/{slug}/relationship.md" --title "分关系互动侧写：[目标姓名]"
```

```bash
python3 tools/merge_profiles.py --input-dir "partners/{slug}/intermediate" --pattern "memory_*.md" --output "partners/{slug}/memory.md" --title "记忆档案：[目标姓名]"
```

Append the thin-slice profile into `persona.md`:

```bash
python3 tools/append_thinslice_to_persona.py --persona "partners/{slug}/persona.md" --thinslice "partners/{slug}/thinslice.md"
```

The append script is idempotent: rerunning it replaces the existing thin-slice block instead of duplicating it.

## Prompt Files

The generation prompts live in `prompts/`:

- `relationshipbuilder.md`
- `memorybuilder.md`
- `personabuilder.md`
- `thinslicebuilder.md`
- `generate_slug_skill.md`

## Material Discipline

- Do not invent facts, quotes, motives, diagnoses, or memories.
- Distinguish observed behavior, user-provided context, and inference.
- Preserve evidence references in intermediate drafts.
- Remove standalone `证据` and `来源` fields from final merged `relationship.md` and `memory.md`.
- If material is thin or conflicting, mark uncertainty clearly.
- When local profile files contain concrete material, use them instead of generic psychology.


