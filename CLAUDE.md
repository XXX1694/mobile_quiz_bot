# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A minimal Telegram bot that posts one randomly-chosen interview quiz poll to a specific group topic. There is no long-running process: `bot.py` is a one-shot script that sends a single poll and exits. Scheduling happens in GitHub Actions (`.github/workflows/quiz.yml`). No-repeat state is persisted by committing `state.json` back to the repo from the workflow.

## Architecture

Four coupled pieces:

1. **`bot.py`** — takes a tag (`Swift` | `Kotlin` | `Flutter`) as `sys.argv[1]`. Loads `questions/<tag.lower()>.json` and `state.json`, picks a random question **whose hash is not in `state[tag].seen`**, writes the hash back to `state.json`, and if the question has a `code` field, first sends an HTML `<pre><code class="language-...">` message (language from `LANG_BY_TAG`: `swift`/`kotlin`/`dart`) to the same topic. Then calls `bot.send_poll(... type="quiz" ...)`. The chat (`CHAT_ID`) and topic (`TOPIC_ID`) are hardcoded; only `BOT_TOKEN` comes from the environment. When all questions of a tag have been seen, `seen` is cleared and the cycle restarts — a log line `cycle complete — seen reset` is printed.

2. **`questions/<tag>.json`** — the question bank, one file per tag: `swift.json`, `kotlin.json`, `flutter.json`. Each file is a JSON **array** (tag is implicit from filename) of `{"q": str, "a": [str, ...], "c": int, "e": str, "code"?: str, "type"?: str}`. `c` is the zero-based index of the correct answer; `e` is the explanation shown after the user answers. The optional `code` field, when present, is sent as a separate HTML code-block message in the same topic **before** the poll — used for questions about code output, bugs, patterns, or language features that don't fit the 300-char poll question. The optional `type` field (`output` | `bug` | `pattern` | `memory` | `coroutines` | `lifecycle`) is metadata for balance and analytics; `bot.py` does not read it. Telegram poll constraints: `[tag] ` prefix + `q` ≤ 300 chars, each `a` ≤ 100 chars, `e` ≤ 200 chars, 2–10 options; keep `code` ≤ ~1500 chars / ~25 lines for readability. Style is concise interview-grade; answer options should be close in length to avoid the "longest = correct" tell.

3. **`state.json`** — `{"<tag>": {"seen": [<md5[:10] hash>, ...]}}`. Hash is `md5(q + "\n" + code)[:10]` — both the short prompt and the code snippet matter, because many questions share a generic `q` like "Что напечатает?". Reordering/adding questions doesn't shift tracking; removing a question leaves a harmless stale hash. Editing either `q` or `code` of an existing question invalidates its hash (treated as a new question). This file is committed back by the workflow after each run.

4. **`.github/workflows/quiz.yml`** — the scheduler and state committer. Three cron entries per day; a shell block maps UTC hour to a tag:
   - `05:00–08:59 UTC` → `Swift`
   - `09:00–11:59 UTC` → `Kotlin`
   - `12:00–15:59 UTC` → `Flutter` (also the fallback)

   Requires `permissions: contents: write`. Uses a `concurrency: quiz-state` group so overlapping manual dispatches serialize. After `python bot.py`, the workflow stages `state.json`, commits only if there's a diff, and pushes. Pull-rebase before push guards against races if someone pushed meanwhile.

   When adding a new tag/time slot, update **both** the `cron:` list and the `if/elif` ladder — they are not derived from each other. The tag string must match a `questions/<tag.lower()>.json` file and needs an entry in `LANG_BY_TAG` in `bot.py` for code-block highlighting.

## Common tasks

Run locally (requires `BOT_TOKEN` and network):

```bash
source venv/bin/activate
pip install aiogram
BOT_TOKEN=xxx python bot.py Flutter   # tag arg optional, defaults to Flutter
```

Validate question banks (checks TG poll limits, option count, correct-index bounds, code size):

```bash
python3 -c "
import json, pathlib
for path in sorted(pathlib.Path('questions').glob('*.json')):
    tag = path.stem.capitalize()
    qs = json.loads(path.read_text())
    print(tag, len(qs))
    for i, q in enumerate(qs):
        assert 2 <= len(q['a']) <= 10, (tag, i)
        assert 0 <= q['c'] < len(q['a']), (tag, i)
        assert all(len(a) <= 100 for a in q['a']), (tag, i)
        assert len(q.get('e', '')) <= 200, (tag, i)
        assert len(q['q']) + len(tag) + 3 <= 300, (tag, i)
        assert len(q.get('code', '')) <= 1500, (tag, i)
"
```

No tests, linter, or build step.

## Notes

- Comments and UI strings are in Russian; keep that convention.
- `venv/` is committed but treat it as read-only.
- Pushing to `main` does **not** send a quiz — only `schedule` or manual `workflow_dispatch`.
- Adding new questions doesn't need a `state.json` reset — old hashes stay, new questions get picked until seen. Editing `q` or `code` of an existing question changes its hash (bot will re-serve it as if new).
