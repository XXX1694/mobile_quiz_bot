# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A minimal Telegram bot that posts one randomly-chosen Android Advanced interview quiz poll to a specific group topic. There is no long-running process: `bot.py` is a one-shot script that sends a single poll and exits. Scheduling happens in GitHub Actions (`.github/workflows/quiz.yml`). No-repeat state is persisted by committing `state.json` back to the repo from the workflow.

The bot covers the **INFT3137 Android Advanced** course topics: Kotlin Advanced, JVM & Memory Model, Jetpack Compose Internals, Kotlin Multiplatform, Clean Architecture & Modularization, SOLID & Code Design, Dependency Injection, Build System & Tooling, Build Variants & App Distribution, Testing/Debugging/Monitoring, Security, AI & AR, Android Ecosystem.

## Architecture

Four coupled pieces:

1. **`bot.py`** — takes no CLI arguments. Loads `questions/android.json` and `state.json`, picks a random question **whose hash is not in `state.seen`** AND **whose `type` is not in the last `RECENT_TOPICS_WINDOW` (=4) entries of `state.recent_topics`**. The recent-topics filter ensures all 5 daily polls land on different topics. If only seen questions remain, the diversity filter is dropped before falling back. If everything has been seen, `seen` is cleared and the cycle restarts (`cycle complete — seen reset` is logged). When a question has a `code` field, the bot first sends an HTML `<pre><code class="language-kotlin">` message to the same topic, then calls `bot.send_poll(... type="quiz" ...)`. The poll question is prefixed with `[<TOPIC_LABELS[type]>] ` (e.g. `[Compose] ...`). `CHAT_ID` and `TOPIC_ID` are hardcoded; only `BOT_TOKEN` comes from env.

2. **`questions/android.json`** — single JSON **array** of `{"q": str, "a": [str, ...], "c": int, "e": str, "code"?: str, "type": str}`. `c` is the zero-based index of the correct answer; `e` is the explanation shown after answering. The optional `code` field (≤ ~1500 chars / ~25 lines, always Kotlin or Gradle DSL) is sent as a separate HTML code block before the poll. The required `type` field is one of the 13 topic keys in `TOPIC_LABELS` (`kotlin_advanced`, `jvm`, `compose`, `kmp`, `clean_arch`, `solid`, `di`, `gradle`, `build_variants`, `testing`, `security`, `ai_ar`, `ecosystem`). Telegram poll constraints: `[label] ` prefix + `q` ≤ 300 chars, each `a` ≤ 100 chars, `e` ≤ 200 chars, 2–10 options. Style is concise interview-grade (middle/senior); **answer options must be close in length so that "longest = correct" is not a tell, and the correct answer must NOT be the longest/most-detailed option**.

3. **`state.json`** — `{"seen": [<md5[:10] hash>, ...], "recent_topics": [<topic key>, ...]}`. Hash is `md5(q + "\n" + code)[:10]` — both the short prompt and the code snippet matter, because many questions share a generic `q` like "Что напечатает?". `recent_topics` is a sliding window of the last few topics posted (trimmed to `RECENT_TOPICS_WINDOW`). Reordering/adding questions doesn't shift tracking; removing a question leaves a harmless stale hash. Editing either `q` or `code` of an existing question invalidates its hash (treated as a new question). This file is committed back by the workflow after each run.

4. **`.github/workflows/quiz.yml`** — the scheduler and state committer. Five cron entries per day (Almaty = UTC+5): 09:13, 12:27, 15:42, 18:55, 21:33 local. The bot picks the topic itself based on `state.recent_topics`, so the workflow no longer needs an `if/elif` topic-mapping ladder — it just runs `python bot.py`. Requires `permissions: contents: write`. Uses a `concurrency: quiz-state` group so overlapping manual dispatches serialize. After `python bot.py`, the workflow stages `state.json`, commits only if there's a diff, and pushes. Pull-rebase before push guards against races if someone pushed meanwhile.

   When adding a new topic, update **both** `TOPIC_LABELS` in `bot.py` and add questions with the new `type` key to `android.json`. Adding/changing the schedule only requires editing the `cron:` list (no per-slot logic).

## Common tasks

Run locally (requires `BOT_TOKEN` and network):

```bash
source venv/bin/activate
pip install aiogram
BOT_TOKEN=xxx python bot.py
```

Validate the question bank (checks TG poll limits, option count, correct-index bounds, code size, type validity):

```bash
python3 -c "
import json
from bot import TOPIC_LABELS
qs = json.loads(open('questions/android.json').read())
print(f'total: {len(qs)}')
counts = {}
for i, q in enumerate(qs):
    assert 2 <= len(q['a']) <= 10, i
    assert 0 <= q['c'] < len(q['a']), i
    assert all(len(a) <= 100 for a in q['a']), i
    assert len(q.get('e', '')) <= 200, i
    label = TOPIC_LABELS.get(q['type'], q['type'])
    assert len(q['q']) + len(label) + 3 <= 300, i
    assert len(q.get('code', '')) <= 1500, i
    assert q['type'] in TOPIC_LABELS, (i, q['type'])
    counts[q['type']] = counts.get(q['type'], 0) + 1
for k, v in sorted(counts.items()):
    print(f'  {k}: {v}')
"
```

No tests, linter, or build step.

## Notes

- Quiz content (question text, answer options, explanations) is in **English** to match the course/syllabus style. Repo-internal comments and commit messages remain in Russian.
- `venv/` is committed but treat it as read-only.
- Pushing to `main` does **not** send a quiz — only `schedule` or manual `workflow_dispatch`.
- Adding new questions doesn't need a `state.json` reset — old hashes stay, new questions get picked until seen. Editing `q` or `code` of an existing question changes its hash (bot will re-serve it as if new).
- All `code` snippets are highlighted as Kotlin (covers Kotlin, Gradle Kotlin DSL, and code that's "Kotlin-shaped").
