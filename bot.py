import asyncio
import json
import random
import os
import sys
from aiogram import Bot

TOKEN = os.getenv("BOT_TOKEN") # Берем из секретов Гитхаба
CHAT_ID = -1003554574954
TOPIC_ID = 559

bot = Bot(token=TOKEN)

async def send_one_quiz():
    # Определяем тему на основе аргумента из GitHub Actions
    tag = sys.argv[1] if len(sys.argv) > 1 else "Flutter"
    
    with open('questions.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    quiz = random.choice(data.get(tag, []))
    
    await bot.send_poll(
        chat_id=CHAT_ID,
        message_thread_id=TOPIC_ID,
        question=f"[{tag}] {quiz['q']}",
        options=quiz['a'],
        type="quiz",
        correct_option_id=quiz['c'],
        explanation=quiz.get('e', ""),
        is_anonymous=False
    )
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(send_one_quiz())