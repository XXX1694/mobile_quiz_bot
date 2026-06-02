# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A minimal Telegram bot that posts mobile-interview quiz polls to topics (forum threads) in a group. There is no long-running process: `bot.py` is a one-shot script that, on each run, posts **one quiz per stack** and exits. Three stacks are covered — **Flutter (Dart), iOS (Swift), Android (Kotlin)** — so one run = **3 quizzes/day**. Scheduling happens in GitHub Actions (`.github/workflows/quiz.yml`). No-repeat state is persisted by committing `state.json` back to the repo from the workflow.

Questions are practical, interview-style (middle/senior) — code-output ("what does this print?"), patterns, keywords, real-world scenarios — not dry theory. Content is in **English**.

## Architecture

Four coupled pieces:

1. **`bot.py`** — takes no CLI args. The `STACKS` dict configures each stack: `questions` (bank path), `topic_id` (Telegram `message_thread_id`), `prefix` (poll label, e.g. `Flutter`), and `lang` (code highlight: `dart`/`swift`/`kotlin`). On each run it loops over all stacks (or a single one if the `STACK` env var is set, e.g. `STACK=ios`). For each stack it loads the bank + per-stack state, picks a random question **whose hash isn't in that stack's `seen`** AND **whose `topic` isn't in the last `RECENT_TOPICS_WINDOW` (=4) topics** for diversity. If only seen questions remain, the diversity filter is dropped; if everything is seen, `seen` is cleared and the cycle restarts. When a question has a `code` field, the bot first sends an HTML `<pre><code class="language-<lang>">` message to that stack's topic, then sends the poll. The poll question is prefixed `[<prefix>] `. A stack whose `topic_id` is `None` is skipped with a log line. `CHAT_ID` is hardcoded; `BOT_TOKEN` comes from env.

2. **`questions/<stack>.json`** (`flutter.json`, `ios.json`, `android.json`) — each a JSON **array** of `{"q": str, "a": [str,...], "c": int, "e": str, "code"?: str, "topic": str, "type": str}`. `c` is the zero-based index of the correct answer; `e` is the explanation shown after answering. Optional `code` (≤ ~1500 chars) is sent as a separate highlighted block before the poll, in the stack's language. `topic` is a short key used for the diversity window (e.g. `async`, `memory`, `coroutines`). `type` is the question style (`code-output`, `keyword`, `pattern`, `concept`, `practical`) — informational. Telegram poll limits: `[prefix] ` + `q` ≤ 300 chars, each `a` ≤ 100 chars, `e` ≤ 200 chars, 2–10 options. **Answer options must vary in length, but the correct answer must NOT be the single longest option** (otherwise "longest = correct" is a tell). Vary the correct index across questions.

3. **`state.json`** — per-stack: `{"<stack>": {"seen": [<md5[:10] hash>,...], "recent_topics": [<topic key>,...]}, ...}`. Hash is `md5(q + "\n" + code)[:10]`. `recent_topics` is a sliding window trimmed to `RECENT_TOPICS_WINDOW`. Adding/reordering questions doesn't shift tracking; removing one leaves a harmless stale hash; editing `q` or `code` invalidates the hash (re-served as new). Committed back by the workflow after each run.

4. **`.github/workflows/quiz.yml`** — scheduler + state committer. One cron/day (Almaty = UTC+5) runs `python bot.py`, which posts all three stacks. Requires `permissions: contents: write`. A `concurrency: quiz-state` group serializes overlapping manual dispatches. After the run it stages `state.json`, commits only on a diff, pull-rebases, and pushes.

   To spread the 3 quizzes across the day instead of one batch, add more cron entries each invoking `STACK=<stack> python bot.py` for a single stack. To add a stack: add an entry to `STACKS` and create its `questions/<stack>.json`.

## Common tasks

Run locally (requires `BOT_TOKEN` and network):

```bash
source venv/bin/activate
pip install aiogram
BOT_TOKEN=xxx python bot.py            # all stacks
BOT_TOKEN=xxx STACK=flutter python bot.py   # one stack
```

Validate the question banks (TG poll limits, option count, correct-index bounds, code size, "longest≠correct"):

```bash
python3 - <<'PY'
import json
PREFIX = {"flutter":"Flutter","ios":"iOS","android":"Android"}
for stack in PREFIX:
    qs = json.load(open(f"questions/{stack}.json", encoding="utf-8"))
    for i, q in enumerate(qs):
        assert 2 <= len(q['a']) <= 10, (stack, i)
        assert 0 <= q['c'] < len(q['a']), (stack, i)
        assert all(len(a) <= 100 for a in q['a']), (stack, i)
        assert len(q.get('e','')) <= 200, (stack, i)
        assert len(f"[{PREFIX[stack]}] {q['q']}") <= 300, (stack, i)
        assert len(q.get('code','')) <= 1500, (stack, i)
        lens = [len(a) for a in q['a']]
        assert not (lens[q['c']] == max(lens) and lens.count(max(lens)) == 1), f"longest=correct {stack}[{i}]"
    print(f"{stack}: {len(qs)} OK")
PY
```

No tests, linter, or build step.

## Notes

- Quiz content (questions, options, explanations) is in **English**. Repo-internal comments and commit messages remain in Russian.
- `venv/` is committed but treat it as read-only.
- Pushing to `main` does **not** send a quiz — only `schedule` or manual `workflow_dispatch`.
- Adding new questions doesn't need a `state.json` reset.
- Each stack's `code` snippets are highlighted in that stack's language (`dart`/`swift`/`kotlin`).
- **`topic_id` per stack must be a real Telegram forum thread id.** A stack left at `None` is silently skipped.
