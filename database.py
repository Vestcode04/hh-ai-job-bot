import asyncpg
from dotenv import load_dotenv
from os import getenv

load_dotenv()


# Подключение к PostgreSQL
async def get_connection():
    return await asyncpg.connect(
        user=getenv("DB_USER"),
        password=getenv("DB_PASSWORD"),
        database=getenv("DB_NAME"),
        host=getenv("DB_HOST"),
        port=int(getenv("DB_PORT", 5432))
    )


# Создание таблиц
async def initialize_database():
    conn = await get_connection()

    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,

                skills TEXT[] NOT NULL DEFAULT '{}',
                desired_position TEXT,
                area_id INTEGER,
                area_name TEXT,
                experience TEXT,
                remote BOOLEAN DEFAULT FALSE,
                min_salary INTEGER,

                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vacancies (
                id BIGSERIAL PRIMARY KEY,
                hh_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                employer_name TEXT,
                description TEXT,
                key_skills TEXT[] NOT NULL DEFAULT '{}',
                salary_from INTEGER,
                salary_to INTEGER,
                currency TEXT,
                area_id INTEGER,
                area_name TEXT,
                experience TEXT,
                url TEXT,
                published_at TIMESTAMPTZ,
                archived BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id BIGSERIAL PRIMARY KEY,

                user_id BIGINT NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,

                vacancy_id BIGINT NOT NULL
                    REFERENCES vacancies(id) ON DELETE CASCADE,

                skill_score NUMERIC(5, 2) DEFAULT 0,
                position_score NUMERIC(5, 2) DEFAULT 0,
                semantic_score NUMERIC(5, 2) DEFAULT 0,
                final_score NUMERIC(5, 2) DEFAULT 0,

                matched_skills TEXT[] NOT NULL DEFAULT '{}',
                missing_skills TEXT[] NOT NULL DEFAULT '{}',

                shown BOOLEAN DEFAULT FALSE,
                saved BOOLEAN DEFAULT FALSE,

                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(user_id, vacancy_id)
            );
        """)

    finally:
        await conn.close()


# Получить или создать пользователя
async def get_or_create_user(
    telegram_id: int,
    username: str | None
):
    conn = await get_connection()

    try:
        async with conn.transaction():
            user_id = await conn.fetchval("""
                INSERT INTO users (telegram_id, username)
                VALUES ($1, $2)

                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    updated_at = CURRENT_TIMESTAMP

                RETURNING id;
            """, telegram_id, username)

            # Создаём профиль, если его ещё нет
            await conn.execute("""
                INSERT INTO profiles (user_id)
                VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING;
            """, user_id)

            return user_id

    finally:
        await conn.close()


# Сохранение навыков
async def update_user_skills(telegram_id: int, skills: list[str]):
    conn = await get_connection()

    try:
        await conn.execute("""
            UPDATE profiles
            SET skills = $1,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = (
                SELECT id FROM users WHERE telegram_id = $2
            );
        """, skills, telegram_id)

    finally:
        await conn.close()


# Получение навыков
async def get_user_skills(telegram_id: int):
    conn = await get_connection()

    try:
        return await conn.fetchval("""
            SELECT profiles.skills
            FROM profiles
            JOIN users ON profiles.user_id = users.id
            WHERE users.telegram_id = $1;
        """, telegram_id)

    finally:
        await conn.close()


# Сохранение должности и опыта
async def update_search_preferences(
    telegram_id: int,
    position: str,
    experience: str
):
    conn = await get_connection()

    try:
        await conn.execute("""
            UPDATE profiles
            SET desired_position = $1,
                experience = $2,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = (
                SELECT id FROM users WHERE telegram_id = $3
            );
        """, position, experience, telegram_id)

    finally:
        await conn.close()


# Получение должности и опыта
async def get_search_preferences(telegram_id: int):
    conn = await get_connection()

    try:
        profile = await conn.fetchrow("""
            SELECT desired_position, experience
            FROM profiles
            JOIN users ON profiles.user_id = users.id
            WHERE users.telegram_id = $1;
        """, telegram_id)

        return dict(profile) if profile else None

    finally:
        await conn.close()