import logging
import httpx

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from openai import OpenAIError

from database import (
    get_or_create_user,
    update_user_skills,
    get_user_skills,
    update_search_preferences,
    get_search_preferences
)

from skills_validator import validate_skills
from hh import search_vacancies
from scorer import rank_vacancies


handler_router = Router()


# Состояния пользователя
class ProfileStates(StatesGroup):
    waiting_for_skills = State()
    confirm_skills = State()
    waiting_for_position = State()
    waiting_for_experience = State()


# Подписи опыта
EXPERIENCE_NAMES = {
    "noExperience": "Без опыта",
    "between1And3": "1–3 года",
    "between3And6": "3–6 лет",
    "moreThan6": "Более 6 лет"
}


# Кнопки выбора опыта
def experience_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Без опыта / Junior",
                    callback_data="exp:noExperience"
                )
            ],
            [
                InlineKeyboardButton(
                    text="1–3 года",
                    callback_data="exp:between1And3"
                )
            ],
            [
                InlineKeyboardButton(
                    text="3–6 лет",
                    callback_data="exp:between3And6"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Более 6 лет",
                    callback_data="exp:moreThan6"
                )
            ]
        ]
    )


# -------------------------
# START
# -------------------------

@handler_router.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext
):
    # Регистрируем пользователя
    await get_or_create_user(
        message.from_user.id,
        message.from_user.username
    )

    await state.clear()

    # После навыков спросим должность
    await state.update_data(ask_position=True)
    await state.set_state(ProfileStates.waiting_for_skills)

    await message.answer(
        "👋 Привет!\n\n"
        "Я помогу подобрать вакансии под твои навыки.\n\n"
        "Напиши навыки через запятую.\n\n"
        "Например:\n"
        "Python, FastAPI, PostgreSQL, Docker, Git"
    )


# -------------------------
# SKILLS
# -------------------------

@handler_router.message(Command("skills"))
async def show_skills_handler(message: Message):

    skills = await get_user_skills(message.from_user.id)
    profile = await get_search_preferences(message.from_user.id)

    if not skills:
        await message.answer(
            "Навыки ещё не сохранены. Используй /start"
        )
        return

    skills_text = "\n".join(
        f"• {skill}" for skill in skills
    )

    position = (
        profile.get("desired_position")
        if profile else None
    ) or "Не указана"

    experience = (
        profile.get("experience")
        if profile else None
    )

    experience_name = EXPERIENCE_NAMES.get(
        experience, "Не указан"
    )

    await message.answer(
        f"🛠 Твои навыки:\n\n{skills_text}\n\n"
        f"💼 Должность: {position}\n"
        f"📊 Опыт: {experience_name}"
    )


# -------------------------
# EDIT SKILLS
# -------------------------

@handler_router.message(Command("edit_skills"))
async def edit_skills_handler(
    message: Message,
    state: FSMContext
):
    await get_or_create_user(
        message.from_user.id,
        message.from_user.username
    )

    await state.clear()

    # Меняем только навыки, должность оставляем
    await state.update_data(ask_position=False)
    await state.set_state(ProfileStates.waiting_for_skills)

    await message.answer(
        "✏️ Напиши новый список навыков через запятую."
    )


# -------------------------
# EDIT POSITION
# -------------------------

@handler_router.message(Command("position"))
async def position_command(
    message: Message,
    state: FSMContext
):
    await get_or_create_user(
        message.from_user.id,
        message.from_user.username
    )

    await state.clear()
    await state.set_state(ProfileStates.waiting_for_position)

    await message.answer(
        "💼 Какую должность ты ищешь?\n\n"
        "Например: Python Backend Developer"
    )


# -------------------------
# SEARCH
# -------------------------

@handler_router.message(Command("search"))
async def search_handler(message: Message):

    skills = await get_user_skills(message.from_user.id)

    if not skills:
        await message.answer(
            "Сначала добавь навыки через /start"
        )
        return

    profile = await get_search_preferences(message.from_user.id)

    if not profile or not profile["desired_position"] or not profile["experience"]:
        await message.answer(
            "Сначала укажи должность и опыт через /position"
        )
        return

    await message.answer(
        "🔎 Ищу вакансии и анализирую требования..."
    )

    try:
        # Получаем вакансии HH
        vacancies = await search_vacancies(
            skills,
            position=profile["desired_position"],
            experience=profile["experience"]
        )

        if not vacancies:
            await message.answer(
                "Подходящих вакансий не найдено.\n"
                "Попробуй другую должность или уровень опыта."
            )
            return

        # Обычный score + локальный AI
        results = await rank_vacancies(
            skills,
            vacancies
        )

    except httpx.HTTPStatusError as error:
        status = error.response.status_code

        logging.error(
            "HH API: %s %s",
            status,
            error.response.text[:300]
        )

        if status == 401:
            text = "❌ Ошибка авторизации HH."
        elif status == 403:
            text = "❌ HH отказал в доступе. Проверь логи."
        elif status == 429:
            text = "⚠️ Слишком много запросов. Попробуй позже."
        else:
            text = f"❌ Ошибка HH API: {status}"

        await message.answer(text)
        return

    except httpx.RequestError:
        await message.answer(
            "❌ Не удалось подключиться к HeadHunter."
        )
        return

    except RuntimeError as error:
        logging.error("Ошибка поиска: %s", error)
        await message.answer(
            "❌ Ошибка настройки поиска. Проверь .env и логи."
        )
        return

    await message.answer(
        f"✅ Проанализировано вакансий: {len(vacancies)}\n"
        "Показываю 5 лучших результатов."
    )

    # Показываем ТОП-5
    for item in results[:5]:

        vacancy = item["vacancy"]

        matched = ", ".join(item["matched"]) or "Нет"
        missing = ", ".join(item["missing"]) or "Нет"

        text = (
            f"💼 {vacancy['name']}\n"
            f"🏢 {vacancy['employer']['name']}\n\n"
            f"🎯 Рейтинг: {item['score']}/100\n"
            f"🛠 Совпадение навыков: {item['skill_score']}%\n\n"
            f"✅ Совпало: {matched}\n"
            f"❌ Не хватает: {missing}\n\n"
            f"🔗 {vacancy['alternate_url']}"
        )

        if item["ai_score"] is not None:
            text += f"\n🤖 AI-сходство: {item['ai_score']}/100"

        await message.answer(text)


# -------------------------
# ЗАЩИТА ОТ КОМАНД
# -------------------------

@handler_router.message(
    ProfileStates.waiting_for_skills,
    F.text.startswith("/")
)
async def command_in_skills(message: Message):
    await message.answer(
        "Это команда, а не навык.\n"
        "Напиши навыки через запятую."
    )


# -------------------------
# AI-ПРОВЕРКА НАВЫКОВ
# -------------------------

@handler_router.message(ProfileStates.waiting_for_skills)
async def skills_handler(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer("Отправь навыки текстом.")
        return

    if len(message.text) > 500:
        await message.answer(
            "Слишком длинный список. Максимум 500 символов."
        )
        return

    items = [
        item.strip()
        for item in message.text.split(",")
        if item.strip()
    ]

    if len(items) > 30:
        await message.answer(
            "Можно указать максимум 30 навыков."
        )
        return

    # Команды сразу отклоняем
    commands = [
        item for item in items
        if item.startswith("/")
    ]

    candidates = [
        item for item in items
        if not item.startswith("/")
    ]

    if not candidates:
        await message.answer(
            "Не удалось найти навыки. Попробуй ещё раз."
        )
        return

    await message.answer("🤖 Проверяю навыки...")

    try:
        result = await validate_skills(
            ", ".join(candidates)
        )

    except (OpenAIError, ValueError):
        await message.answer(
            "❌ Ошибка проверки навыков. Попробуй ещё раз."
        )
        return

    # Удаляем повторы
    valid_skills = []
    seen = set()

    for skill in result.valid:
        skill = skill.strip()

        if not skill or skill.startswith("/"):
            continue

        if skill.casefold() not in seen:
            valid_skills.append(skill)
            seen.add(skill.casefold())

    if not valid_skills:
        await message.answer(
            "❌ Навыки не распознаны. Попробуй ещё раз."
        )
        return

    rejected = commands + result.rejected

    valid_text = "\n".join(
        f"• {skill}" for skill in valid_skills
    )

    text = f"✅ Распознаны навыки:\n\n{valid_text}"

    if rejected:
        rejected_text = "\n".join(
            f"• {skill}" for skill in rejected
        )

        text += f"\n\n⚠️ Не распознаны:\n\n{rejected_text}"

    text += "\n\nСохранить эти навыки?"

    await state.update_data(skills=valid_skills)
    await state.set_state(ProfileStates.confirm_skills)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data="skills_save"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Исправить",
                    callback_data="skills_retry"
                )
            ]
        ]
    )

    await message.answer(text, reply_markup=keyboard)


# -------------------------
# SAVE SKILLS
# -------------------------

@handler_router.callback_query(
    ProfileStates.confirm_skills,
    F.data == "skills_save"
)
async def save_skills(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()
    skills = data["skills"]

    # Сохраняем навыки
    await update_user_skills(
        callback.from_user.id,
        skills
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    # После /start спрашиваем должность
    if data.get("ask_position"):
        await state.set_state(
            ProfileStates.waiting_for_position
        )

        await callback.message.answer(
            "✅ Навыки сохранены!\n\n"
            "💼 Какую должность ты ищешь?\n\n"
            "Например: Python Backend Developer"
        )

    else:
        # После /edit_skills просто завершаем
        await state.clear()

        await callback.message.answer(
            "✅ Навыки обновлены!\n\n"
            "Можешь использовать /search"
        )

    await callback.answer()


# -------------------------
# RETRY SKILLS
# -------------------------

@handler_router.callback_query(
    ProfileStates.confirm_skills,
    F.data == "skills_retry"
)
async def retry_skills(
    callback: CallbackQuery,
    state: FSMContext
):
    await state.set_state(
        ProfileStates.waiting_for_skills
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        "✏️ Введи навыки заново через запятую."
    )

    await callback.answer()


# -------------------------
# POSITION
# -------------------------

@handler_router.message(ProfileStates.waiting_for_position)
async def position_handler(
    message: Message,
    state: FSMContext
):
    if not message.text or message.text.startswith("/"):
        await message.answer(
            "Введи название должности текстом."
        )
        return

    position = message.text.strip()

    if len(position) < 3 or len(position) > 100:
        await message.answer(
            "Название должно содержать от 3 до 100 символов."
        )
        return

    # Временно сохраняем должность
    await state.update_data(position=position)

    await state.set_state(
        ProfileStates.waiting_for_experience
    )

    await message.answer(
        "📊 Выбери свой опыт работы:",
        reply_markup=experience_keyboard()
    )


# -------------------------
# EXPERIENCE
# -------------------------

@handler_router.callback_query(
    ProfileStates.waiting_for_experience,
    F.data.startswith("exp:")
)
async def experience_handler(
    callback: CallbackQuery,
    state: FSMContext
):
    experience = callback.data.split(":", 1)[1]

    if experience not in EXPERIENCE_NAMES:
        await callback.answer("Неизвестный вариант.")
        return

    data = await state.get_data()
    position = data["position"]

    # Сохраняем должность и опыт в PostgreSQL
    await update_search_preferences(
        callback.from_user.id,
        position,
        experience
    )

    await state.clear()

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        f"✅ Профиль настроен!\n\n"
        f"💼 Должность: {position}\n"
        f"📊 Опыт: {EXPERIENCE_NAMES[experience]}\n\n"
        f"Теперь используй /search"
    )

    await callback.answer()


# -------------------------
# ОЖИДАНИЕ ОПЫТА
# -------------------------

@handler_router.message(ProfileStates.waiting_for_experience)
async def waiting_experience(message: Message):
    await message.answer(
        "Выбери опыт с помощью кнопок выше."
    )


# -------------------------
# ОЖИДАНИЕ ПОДТВЕРЖДЕНИЯ
# -------------------------

@handler_router.message(ProfileStates.confirm_skills)
async def waiting_confirmation(message: Message):
    await message.answer(
        "Сначала нажми «Сохранить» или «Исправить» "
        "под предыдущим сообщением."
    )