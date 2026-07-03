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
    try:
        with open(USED_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    data.setdefault("recent_topics", {})
    for stack in STACKS:
        data.setdefault(stack, [])
        data["recent_topics"].setdefault(stack, [])
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
