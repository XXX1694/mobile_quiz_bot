import asyncio
import hashlib
import html
import json
import os
import random
import sys

from aiogram import Bot

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = -1003554574954
TOPIC_ID = 559
QUESTIONS_DIR = "questions"
STATE_PATH = "state.json"

LANG_BY_TAG = {
    "Swift": "swift",
    "Kotlin": "kotlin",
    "Flutter": "dart",
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


def pick_question(questions: list, seen: set) -> tuple[dict, str, bool]:
    pool = [q for q in questions if qid(q) not in seen]
    reset = False
    if not pool:
        pool = list(questions)
        seen.clear()
        reset = True
    quiz = random.choice(pool)
    return quiz, qid(quiz), reset


def load_questions(tag: str) -> list:
    path = os.path.join(QUESTIONS_DIR, f"{tag.lower()}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def send_one_quiz() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "Flutter"

    questions = load_questions(tag)
    if not questions:
        raise SystemExit(f"No questions for tag {tag}")

    state = load_state()
    tag_state = state.setdefault(tag, {"seen": []})
    seen = set(tag_state.get("seen", []))

    quiz, hash_id, reset = pick_question(questions, seen)
    seen.add(hash_id)
    tag_state["seen"] = sorted(seen)
    save_state(state)

    bot = Bot(token=TOKEN)
    try:
        code = quiz.get("code")
        if code:
            lang = LANG_BY_TAG.get(tag, "")
            body = f'<pre><code class="language-{lang}">{html.escape(code)}</code></pre>'
            await bot.send_message(
                chat_id=CHAT_ID,
                message_thread_id=TOPIC_ID,
                text=body,
                parse_mode="HTML",
            )
        await bot.send_poll(
            chat_id=CHAT_ID,
            message_thread_id=TOPIC_ID,
            question=f"[{tag}] {quiz['q']}",
            options=quiz["a"],
            type="quiz",
            correct_option_id=quiz["c"],
            explanation=quiz.get("e", ""),
            is_anonymous=False,
        )
    finally:
        await bot.session.close()

    if reset:
        print(f"[{tag}] cycle complete — seen reset")


if __name__ == "__main__":
    asyncio.run(send_one_quiz())
