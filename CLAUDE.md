# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A minimal Telegram bot that posts one randomly-chosen interview quiz poll to a specific group topic. There is no long-running process: `bot.py` is a one-shot script that sends a single poll and exits. Scheduling happens in GitHub Actions (`.github/workflows/quiz.yml`). No-repeat state is persisted by committing `state.json` back to the repo from the workflow.

## Architecture

Four coupled pieces:

1. **`bot.py`** — takes a tag (`Swift` | `Kotlin` | `Flutter`) as `sys.argv[1]`. Loads `questions.json` and `state.json`, picks a random question **whose hash is not in `state[tag].seen`**, writes the hash back to `state.json`, then calls `bot.send_poll(... type="quiz" ...)`. The chat (`CHAT_ID`) and topic (`TOPIC_ID`) are hardcoded; only `BOT_TOKEN` comes from the environment. When all questions of a tag have been seen, `seen` is cleared and the cycle restarts — a log line `cycle complete — seen reset` is printed.

2. **`questions.json`** — the question bank. Top-level keys are tags; values are lists of `{"q": str, "a": [str, ...], "c": int, "e": str}` where `c` is the zero-based index of the correct answer and `e` is the explanation shown after the user answers. Telegram poll constraints: `[tag] ` prefix + `q` ≤ 300 chars, each `a` ≤ 100 chars, `e` ≤ 200 chars, 2–10 options. Style is concise interview-grade.

3. **`state.json`** — `{"<tag>": {"seen": [<md5[:10] hash>, ...]}}`. Hashes (not indices) are used so reordering/adding questions doesn't shift tracking; removing a question leaves a harmless stale hash. This file is committed back by the workflow after each run.

4. **`.github/workflows/quiz.yml`** — the scheduler and state committer. Three cron entries per day; a shell block maps UTC hour to a tag:
   - `05:00–08:59 UTC` → `Swift`
   - `09:00–11:59 UTC` → `Kotlin`
   - `12:00–15:59 UTC` → `Flutter` (also the fallback)

   Requires `permissions: contents: write`. Uses a `concurrency: quiz-state` group so overlapping manual dispatches serialize. After `python bot.py`, the workflow stages `state.json`, commits only if there's a diff, and pushes. Pull-rebase before push guards against races if someone pushed meanwhile.

   When adding a new tag/time slot, update **both** the `cron:` list and the `if/elif` ladder — they are not derived from each other. The tag string must be a top-level key in `questions.json`.

## Common tasks

Run locally (requires `BOT_TOKEN` and network):

```bash
source venv/bin/activate
pip install aiogram
BOT_TOKEN=xxx python bot.py Flutter   # tag arg optional, defaults to Flutter
```

Validate `questions.json` (checks TG poll limits, option count, correct-index bounds):

```bash
python3 -c "
import json
d = json.load(open('questions.json'))
for tag, qs in d.items():
    print(tag, len(qs))
    for i, q in enumerate(qs):
        assert 2 <= len(q['a']) <= 10, (tag, i)
        assert 0 <= q['c'] < len(q['a']), (tag, i)
        assert all(len(a) <= 100 for a in q['a']), (tag, i)
        assert len(q.get('e', '')) <= 200, (tag, i)
        assert len(q['q']) + len(tag) + 3 <= 300, (tag, i)
"
```

No tests, linter, or build step.

## Notes

- Comments and UI strings are in Russian; keep that convention.
- `venv/` is committed but treat it as read-only.
- Pushing to `main` does **not** send a quiz — only `schedule` or manual `workflow_dispatch`.
- After merging question edits, `state.json` doesn't need manual reset: hashes based on question text survive additions/reorderings.
