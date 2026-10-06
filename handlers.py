from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from database import (
    get_or_create_user,
    update_user_skills,
    get_user_skills
)

handler_router = Router()


class ProfileStates(StatesGroup):
    waiting_for_skills = State()


@handler_router.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext
):
    telegram_id = message.from_user.id
    username = message.from_user.username

    await get_or_create_user(
        telegram_id=telegram_id,
        username=username
    )

    await state.set_state(
        ProfileStates.waiting_for_skills
    )

    await message.answer(
        """
👋 Привет!

Я помогу найти вакансии, которые больше всего
соответствуют твоим навыкам.

Напиши свои навыки через запятую.

Например:

Python, FastAPI, PostgreSQL, Docker, Git
"""
    )


@handler_router.message(
    ProfileStates.waiting_for_skills
)
async def skills_handler(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "Отправь навыки обычным текстом."
        )
        return

    raw_skills = message.text.split(",")

    skills = []
    seen = set()

    for skill in raw_skills:
        skill = skill.strip()

        if not skill:
            continue

        key = skill.casefold()

        if key not in seen:
            seen.add(key)
            skills.append(skill)

    if not skills:
        await message.answer(
            "Не удалось найти навыки. "
            "Напиши их через запятую."
        )
        return

    await update_user_skills(
        telegram_id=message.from_user.id,
        skills=skills
    )

    await state.clear()

    skills_text = "\n".join(
        f"• {skill}"
        for skill in skills
    )

    await message.answer(
        f"""
✅ Навыки сохранены!

{skills_text}
"""
    )

@handler_router.message(Command("skills"))
async def show_skills_handler(message: Message):
    # Получаем навыки из БД
    skills = await get_user_skills(
        message.from_user.id
    )

    # Если навыков пока нет
    if not skills:
        await message.answer(
            "У тебя пока нет сохранённых навыков.\n"
            "Напиши /start, чтобы добавить их."
        )
        return

    # Делаем красивый список
    skills_text = "\n".join(
        f"• {skill}"
        for skill in skills
    )

    await message.answer(
        f"🛠 Твои навыки:\n\n{skills_text}"
    )

@handler_router.message(Command("edit_skills"))
async def edit_skills_handler(message: Message,state: FSMContext):
    # Переводим пользователя в режим ожидания новых навыков
    await state.set_state(
        ProfileStates.waiting_for_skills
    )

    await message.answer(
        "Напиши новый список навыков через запятую.\n\n"
        "Например:\n"
        "Python, FastAPI, PostgreSQL, Docker"
    )
