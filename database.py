import asyncpg
from dotenv import load_dotenv
from os import getenv

load_dotenv()


async def get_connection():
    return await asyncpg.connect(
        user=getenv("DB_USER"),
        password=getenv("DB_PASSWORD"),
        database=getenv("DB_NAME"),
        host=getenv("DB_HOST"),
        port=int(getenv("DB_PORT", 5432))
    )


async def initialize_database():
    conn = await get_connection()

    try:
        # -------------------------
        # USERS
        # -------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,

                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,

                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # -------------------------
        # PROFILES
        # -------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id BIGSERIAL PRIMARY KEY,

                user_id BIGINT UNIQUE NOT NULL
                    REFERENCES users(id)
                    ON DELETE CASCADE,

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

        # -------------------------
        # VACANCIES
        # -------------------------
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

        # -------------------------
        # MATCHES
        # -------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id BIGSERIAL PRIMARY KEY,

                user_id BIGINT NOT NULL
                    REFERENCES users(id)
                    ON DELETE CASCADE,

                vacancy_id BIGINT NOT NULL
                    REFERENCES vacancies(id)
                    ON DELETE CASCADE,

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


async def get_or_create_user(
    telegram_id: int,
    username: str | None
):
    conn = await get_connection()

    try:
        async with conn.transaction():

            user_id = await conn.fetchval("""
                INSERT INTO users (
                    telegram_id,
                    username
                )
                VALUES ($1, $2)

                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    updated_at = CURRENT_TIMESTAMP

                RETURNING id;
            """, telegram_id, username)

            await conn.execute("""
                INSERT INTO profiles (
                    user_id
                )
                VALUES ($1)

                ON CONFLICT (user_id)
                DO NOTHING;
            """, user_id)

            return user_id

    finally:
        await conn.close()

async def update_user_skills(
    telegram_id: int,
    skills: list[str]
):
    conn = await get_connection()

    try:
        await conn.execute("""
            UPDATE profiles
            SET
                skills = $1,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = (
                SELECT id
                FROM users
                WHERE telegram_id = $2
            );
        """, skills, telegram_id)

    finally:
        await conn.close()

async def get_user_skills(telegram_id: int):
    conn = await get_connection()

    try:
        # Получаем навыки пользователя
        skills = await conn.fetchval("""
            SELECT profiles.skills
            FROM profiles
            JOIN users ON users.id = profiles.user_id
            WHERE users.telegram_id = $1;
        """, telegram_id)

        return skills

    finally:
        await conn.close()