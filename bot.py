import asyncio
import hashlib
import json
import os
import random
import sys

from aiogram import Bot

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = -1003554574954
TOPIC_ID = 559
QUESTIONS_PATH = "questions.json"
STATE_PATH = "state.json"


def qid(question: dict) -> str:
    return hashlib.md5(question["q"].encode("utf-8")).hexdigest()[:10]


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


async def send_one_quiz() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "Flutter"

    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = data.get(tag) or []
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
