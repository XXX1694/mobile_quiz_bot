import asyncio
import hashlib
import html
import json
import os
import random

from aiogram import Bot

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = -1003554574954
TOPIC_ID = 559
QUESTIONS_PATH = "questions/android.json"
STATE_PATH = "state.json"

# Сколько последних тем избегать при выборе следующего вопроса.
# 4 = в течение дня (5 постов) каждый раз будет новая тема.
RECENT_TOPICS_WINDOW = 4

# Префиксы для poll-вопроса по полю `type`.
TOPIC_LABELS = {
    "kotlin_advanced": "Kotlin Advanced",
    "jvm": "JVM",
    "compose": "Compose",
    "kmp": "KMP",
    "clean_arch": "Clean Arch",
    "solid": "SOLID",
    "di": "DI",
    "gradle": "Gradle",
    "build_variants": "Build",
    "testing": "Testing",
    "security": "Security",
    "ai_ar": "AI/AR",
    "ecosystem": "Ecosystem",
}

# Все code-сниппеты — Kotlin (или Gradle DSL — тоже подсветится как kotlin).
LANG = "kotlin"


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


def load_questions() -> list:
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
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

    # Пытаемся избежать недавних тем для разнообразия в течение дня.
    avoid = set(avoid_topics)
    diverse_pool = [q for q in pool if q.get("type") not in avoid]
    if diverse_pool:
        pool = diverse_pool

    quiz = random.choice(pool)
    return quiz, qid(quiz), reset


async def send_one_quiz() -> None:
    questions = load_questions()
    if not questions:
        raise SystemExit("questions/android.json пуст")

    state = load_state()
    seen = set(state.get("seen", []))
    recent_topics = list(state.get("recent_topics", []))

    quiz, hash_id, reset = pick_question(questions, seen, recent_topics[-RECENT_TOPICS_WINDOW:])

    # Обновляем state: hash + скользящее окно тем.
    seen.add(hash_id)
    topic = quiz.get("type", "")
    recent_topics.append(topic)
    recent_topics = recent_topics[-RECENT_TOPICS_WINDOW:]

    state["seen"] = sorted(seen)
    state["recent_topics"] = recent_topics
    save_state(state)

    label = TOPIC_LABELS.get(topic, topic)

    bot = Bot(token=TOKEN)
    try:
        code = quiz.get("code")
        if code:
            body = f'<pre><code class="language-{LANG}">{html.escape(code)}</code></pre>'
            await bot.send_message(
                chat_id=CHAT_ID,
                message_thread_id=TOPIC_ID,
                text=body,
                parse_mode="HTML",
            )
        await bot.send_poll(
            chat_id=CHAT_ID,
            message_thread_id=TOPIC_ID,
            question=f"[{label}] {quiz['q']}",
            options=quiz["a"],
            type="quiz",
            correct_option_id=quiz["c"],
            explanation=quiz.get("e", ""),
            is_anonymous=False,
        )
    finally:
        await bot.session.close()

    if reset:
        print("cycle complete — seen reset")


if __name__ == "__main__":
    asyncio.run(send_one_quiz())
