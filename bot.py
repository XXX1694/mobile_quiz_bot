import asyncio
import hashlib
import html
import json
import os
import random
from datetime import datetime, timezone

from aiogram import Bot

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = -1003554574954
USED_PATH = "used_questions.json"

# Сколько последних тем избегать при выборе следующего вопроса в рамках одного стека.
RECENT_TOPICS_WINDOW = 4

# По одному квизу на каждый стек за запуск. Показанные вопросы уходят в used_questions.json
# и больше не повторяются, пока не добавишь новые в банк.
STACKS = {
    "ios": {
        "questions": "questions/ios.json",
        "topic_id": 559,
        "prefix": "iOS",
        "lang": "swift",
    },
    "android": {
        "questions": "questions/android.json",
        "topic_id": 559,
        "prefix": "Android",
        "lang": "kotlin",
    },
    "general": {
        "questions": "questions/general.json",
        "topic_id": 559,
        "prefix": "Mobile",
        "lang": "kotlin",
    },
}


def qid(question: dict) -> str:
    src = question["q"] + "\n" + question.get("code", "")
    return hashlib.md5(src.encode("utf-8")).hexdigest()[:10]


def load_used() -> dict:
    """Загружает архив показанных вопросов.

    Ожидаемый формат:
      { "<stack>": [{hash, posted_at, ...q}, ...], "recent_topics": { "<stack>": [...] } }

    Старый плоский формат { "questions": [...], "recent_topics": [...] } мигрируется
    в per-stack структуру по совпадению hash с банками вопросов.
    """
    try:
        with open(USED_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    if not isinstance(data, dict):
        data = {}

    # Нормализуем recent_topics: раньше мог быть list вместо dict по стекам.
    recent = data.get("recent_topics")
    if not isinstance(recent, dict):
        legacy_topics = recent if isinstance(recent, list) else []
        data["recent_topics"] = {}
    else:
        legacy_topics = []

    for stack in STACKS:
        if not isinstance(data.get(stack), list):
            data[stack] = []
        rt = data["recent_topics"].get(stack)
        if not isinstance(rt, list):
            data["recent_topics"][stack] = []

    # Миграция legacy flat-архива {"questions": [...]} → раскладываем по стекам.
    legacy_questions = data.pop("questions", None)
    if isinstance(legacy_questions, list) and legacy_questions:
        bank_hashes: dict[str, set[str]] = {}
        for stack, cfg in STACKS.items():
            try:
                bank_hashes[stack] = {qid(q) for q in load_questions(cfg["questions"])}
            except FileNotFoundError:
                bank_hashes[stack] = set()

        for entry in legacy_questions:
            if not isinstance(entry, dict):
                continue
            h = entry.get("hash") or qid(entry)
            entry = {**entry, "hash": h}
            for stack, hashes in bank_hashes.items():
                if h in hashes:
                    # не дублируем, если уже есть
                    if h not in used_hashes(data, stack):
                        data[stack].append(entry)
                    break

        # Плоский recent_topics относился к единственному стеку (ios) до рефакторинга.
        if legacy_topics and not any(data["recent_topics"][s] for s in STACKS):
            first = next(iter(STACKS))
            data["recent_topics"][first] = list(legacy_topics)[-RECENT_TOPICS_WINDOW:]

    return data


def save_used(data: dict) -> None:
    with open(USED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def load_questions(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def used_hashes(used: dict, stack: str) -> set:
    return {entry["hash"] for entry in used.get(stack, []) if "hash" in entry}


def pick_question(
    questions: list, seen: set, avoid_topics: list
) -> tuple[dict, str] | tuple[None, None]:
    pool = [q for q in questions if qid(q) not in seen]
    if not pool:
        return None, None

    avoid = set(avoid_topics)
    diverse_pool = [q for q in pool if q.get("topic") not in avoid]
    if diverse_pool:
        pool = diverse_pool

    quiz = random.choice(pool)
    return quiz, qid(quiz)


def archive_question(used: dict, stack: str, quiz: dict, hash_id: str) -> None:
    entry = {
        "hash": hash_id,
        "posted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **quiz,
    }
    used.setdefault(stack, []).append(entry)


async def send_stack_quiz(bot: Bot, stack: str, cfg: dict, used: dict) -> None:
    topic_id = cfg["topic_id"]
    if topic_id is None:
        print(f"[{stack}] topic_id не задан — пропускаю")
        return

    questions = load_questions(cfg["questions"])
    if not questions:
        print(f"[{stack}] банк {cfg['questions']} пуст — пропускаю")
        return

    seen = used_hashes(used, stack)
    recent_topics = list(used["recent_topics"].get(stack, []))

    quiz, hash_id = pick_question(questions, seen, recent_topics[-RECENT_TOPICS_WINDOW:])
    if quiz is None:
        remaining = len(questions) - len(seen)
        print(
            f"[{stack}] все {len(questions)} вопросов уже показаны "
            f"(в архиве: {len(seen)}) — добавь новые в {cfg['questions']}"
        )
        return

    archive_question(used, stack, quiz, hash_id)
    recent_topics.append(quiz.get("topic", ""))
    used["recent_topics"][stack] = recent_topics[-RECENT_TOPICS_WINDOW:]

    code = quiz.get("code")
    if code:
        body = f'<pre><code class="language-{cfg["lang"]}">{html.escape(code)}</code></pre>'
        await bot.send_message(
            chat_id=CHAT_ID,
            message_thread_id=topic_id,
            text=body,
            parse_mode="HTML",
        )
    await bot.send_poll(
        chat_id=CHAT_ID,
        message_thread_id=topic_id,
        question=f"[{cfg['prefix']}] {quiz['q']}",
        options=quiz["a"],
        type="quiz",
        correct_option_id=quiz["c"],
        explanation=quiz.get("e", ""),
        is_anonymous=False,
    )

    left = len(questions) - len(used_hashes(used, stack))
    print(f"[{stack}] sent {hash_id} (осталось новых: {left})")


async def main() -> None:
    # STACK=ios постит только один стек; без переменной — все.
    only = os.getenv("STACK")
    stacks = [only] if only else list(STACKS.keys())

    used = load_used()
    bot = Bot(token=TOKEN)
    try:
        for stack in stacks:
            cfg = STACKS.get(stack)
            if not cfg:
                print(f"неизвестный стек: {stack}")
                continue
            await send_stack_quiz(bot, stack, cfg, used)
    finally:
        await bot.session.close()

    save_used(used)


if __name__ == "__main__":
    asyncio.run(main())
