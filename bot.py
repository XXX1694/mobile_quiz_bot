import asyncio
import hashlib
import html
import json
import os
import random

from aiogram import Bot

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = -1003554574954
STATE_PATH = "state.json"

# Сколько последних тем избегать при выборе следующего вопроса в рамках одного стека.
RECENT_TOPICS_WINDOW = 4

# Конфигурация стеков. По одному квизу на каждый стек за запуск = 3 квиза в день.
#   questions  — путь к банку вопросов
#   topic_id   — message_thread_id топика в группе (forum). ОБЯЗАТЕЛЬНО проставить реальные ID.
#   prefix     — подпись в начале poll-вопроса: "[Flutter] ..."
#   lang       — язык подсветки code-сниппета (dart / swift / kotlin)
STACKS = {
    "flutter": {
        "questions": "questions/flutter.json",
        "topic_id": None,   # TODO: проставить ID топика Flutter
        "prefix": "Flutter",
        "lang": "dart",
    },
    "ios": {
        "questions": "questions/ios.json",
        "topic_id": None,   # TODO: проставить ID топика iOS
        "prefix": "iOS",
        "lang": "swift",
    },
    "android": {
        "questions": "questions/android.json",
        "topic_id": 559,
        "prefix": "Android",
        "lang": "kotlin",
    },
}


def qid(question: dict) -> str:
    src = question["q"] + "\n" + question.get("code", "")
    return hashlib.md5(src.encode("utf-8")).hexdigest()[:10]


def load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def load_questions(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_question(questions: list, seen: set, avoid_topics: list) -> tuple[dict, str, bool]:
    # Сначала отсеиваем уже виденные.
    pool = [q for q in questions if qid(q) not in seen]
    reset = False
    if not pool:
        # Полный цикл пройден — обнуляем seen и стартуем заново.
        pool = list(questions)
        seen.clear()
        reset = True

    # Пытаемся избежать недавних тем для разнообразия.
    avoid = set(avoid_topics)
    diverse_pool = [q for q in pool if q.get("topic") not in avoid]
    if diverse_pool:
        pool = diverse_pool

    quiz = random.choice(pool)
    return quiz, qid(quiz), reset


async def send_stack_quiz(bot: Bot, stack: str, cfg: dict, state: dict) -> None:
    topic_id = cfg["topic_id"]
    if topic_id is None:
        print(f"[{stack}] topic_id не задан — пропускаю")
        return

    questions = load_questions(cfg["questions"])
    if not questions:
        print(f"[{stack}] банк {cfg['questions']} пуст — пропускаю")
        return

    stack_state = state.setdefault(stack, {})
    seen = set(stack_state.get("seen", []))
    recent_topics = list(stack_state.get("recent_topics", []))

    quiz, hash_id, reset = pick_question(
        questions, seen, recent_topics[-RECENT_TOPICS_WINDOW:]
    )

    # Обновляем state стека: hash + скользящее окно тем.
    seen.add(hash_id)
    recent_topics.append(quiz.get("topic", ""))
    recent_topics = recent_topics[-RECENT_TOPICS_WINDOW:]
    stack_state["seen"] = sorted(seen)
    stack_state["recent_topics"] = recent_topics

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

    print(f"[{stack}] sent {hash_id}" + (" (cycle reset)" if reset else ""))


async def main() -> None:
    # STACK=flutter постит только один стек; без переменной — все три.
    only = os.getenv("STACK")
    stacks = [only] if only else list(STACKS.keys())

    state = load_state()
    bot = Bot(token=TOKEN)
    try:
        for stack in stacks:
            cfg = STACKS.get(stack)
            if not cfg:
                print(f"неизвестный стек: {stack}")
                continue
            await send_stack_quiz(bot, stack, cfg, state)
    finally:
        await bot.session.close()

    save_state(state)


if __name__ == "__main__":
    asyncio.run(main())
