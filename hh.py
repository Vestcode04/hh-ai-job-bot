import asyncio
import re
from os import getenv

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.hh.ru"


# Названия технологий
SKILL_ALIASES = {
    "python": "Python",
    "fastapi": "FastAPI",
    "fast api": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "docker": "Docker",
    "git": "Git",
    "linux": "Linux",
    "redis": "Redis",
    "celery": "Celery",
    "rabbitmq": "RabbitMQ",
    "kafka": "Kafka",
    "sqlalchemy": "SQLAlchemy",
    "pytest": "pytest",
    "asyncio": "asyncio",
    "sql": "SQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "kubernetes": "Kubernetes",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "node.js": "Node.js",
    "react": "React",
    "vue": "Vue",
    "java": "Java",
    "spring": "Spring",
    "php": "PHP",
    "laravel": "Laravel",
    "c#": "C#",
    ".net": ".NET",
    "c++": "C++",
    "golang": "Go",
    "rest api": "REST API"
}


# Заголовки HH API
def get_headers():
    token = getenv("HH_ACCESS_TOKEN")
    user_agent = getenv("HH_USER_AGENT")

    if not token or not user_agent:
        raise RuntimeError(
            "Заполни HH_ACCESS_TOKEN и HH_USER_AGENT в .env"
        )

    return {
        "Authorization": f"Bearer {token}",
        "HH-User-Agent": user_agent
    }


# Создаём несколько запросов
def build_queries(skills, position=None):
    queries = []

    if position:
        queries.append(position)

    # Основные языки
    languages = [
        "python", "java", "javascript",
        "typescript", "php", "c#", "c++", "go"
    ]

    # Фреймворки
    frameworks = [
        "fastapi", "django", "flask",
        "spring", "laravel", "react", "vue"
    ]

    for skill in skills:
        if skill.casefold() in languages:
            queries.append(f"{skill} developer")
            break

    for skill in skills:
        if skill.casefold() in frameworks:
            queries.append(skill)
            break

    if not queries:
        queries = skills[:3]

    # Максимум три разных запроса
    return list(dict.fromkeys(queries))[:3]


# Проверка уровня вакансии
def allowed_level(vacancy, experience):
    title = vacancy.get("name", "").lower()

    senior_words = [
        "senior", "lead", "principal",
        "сеньор", "ведущий",
        "тимлид", "руководитель"
    ]

    middle_words = [
        "middle", "mid-level", "мидл"
    ]

    # Для новичков исключаем Middle и Senior
    if experience == "noExperience":
        excluded = senior_words + middle_words

    # Для 1–3 лет исключаем Senior и руководителей
    elif experience == "between1And3":
        excluded = senior_words

    else:
        excluded = []

    for word in excluded:
        pattern = rf"(?<!\w){re.escape(word)}(?!\w)"

        if re.search(pattern, title):
            return False

    return True


# Извлечение навыков из вакансии
def extract_skills(details, user_skills):

    description = BeautifulSoup(
        details.get("description") or "",
        "html.parser"
    ).get_text(" ", strip=True)

    found = set()

    # Навыки, указанные работодателем
    for skill in details.get("key_skills") or []:
        name = skill.get("name", "").strip()

        if name:
            found.add(
                SKILL_ALIASES.get(name.casefold(), name)
            )

    # Анализ текста вакансии
    text = f"{details.get('name', '')} {description}"

    aliases = SKILL_ALIASES.copy()

    # Добавляем навыки пользователя для поиска
    for skill in user_skills:
        aliases[skill.casefold()] = SKILL_ALIASES.get(
            skill.casefold(), skill
        )

    for alias, name in aliases.items():
        pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"

        if re.search(pattern, text, re.IGNORECASE):
            found.add(name)

    return sorted(found), description


# Получение полной вакансии
async def get_vacancy(vacancy_id):

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{BASE_URL}/vacancies/{vacancy_id}",
            headers=get_headers(),
            params={"host": "hh.kz"}
        )

        response.raise_for_status()

        return response.json()


# Поиск вакансий
async def search_vacancies(
    skills,
    position=None,
    experience=None
):
    headers = get_headers()

    # Поисковые запросы
    queries = build_queries(skills, position)

    candidates = {}

    async with httpx.AsyncClient(timeout=20) as client:

        # Ищем вакансии по нескольким запросам
        for query in queries:
            params = {
                "text": query,
                "area": 40,       # Казахстан
                "host": "hh.kz",
                "per_page": 20,
                "page": 0
            }

            # Фильтр опыта
            if experience:
                params["experience"] = experience

            response = await client.get(
                f"{BASE_URL}/vacancies",
                headers=headers,
                params=params
            )

            response.raise_for_status()

            data = response.json()

            # Убираем дубликаты по HH ID
            for item in data.get("items", []):
                candidates[item["id"]] = item

        # Убираем неподходящие уровни
        filtered = [
            item for item in candidates.values()
            if allowed_level(item, experience)
        ]

        # Сначала рассматриваем вакансии,
        # похожие по названию на желаемую должность
        position_words = []

        if position:
            position_words = [
                word.casefold()
                for word in position.split()
                if len(word) > 3
                and word.casefold() not in (
                    "developer", "engineer", "разработчик"
                )
            ]

        def priority(item):
            title = item.get("name", "").casefold()

            position_matches = sum(
                1 for word in position_words
                if word in title
            )

            skill_matches = sum(
                1 for skill in skills
                if skill.casefold() in title
            )

            return position_matches * 2 + skill_matches

        selected = sorted(
            filtered,
            key=priority,
            reverse=True
        )[:15]

        # Ограничиваем количество одновременных запросов
        semaphore = asyncio.Semaphore(3)

        async def load_details(item):

            async with semaphore:
                response = await client.get(
                    f"{BASE_URL}/vacancies/{item['id']}",
                    headers=headers,
                    params={"host": "hh.kz"}
                )

                if response.status_code in (404, 410):
                    return None

                response.raise_for_status()

                details = response.json()

                vacancy_skills, description = extract_skills(
                    details, skills
                )

                return {
                    "id": item["id"],
                    "name": item["name"],
                    "employer": {
                        "name": (
                            (item.get("employer") or {}).get("name")
                            or "Не указана"
                        )
                    },
                    "alternate_url": (
                        item.get("alternate_url")
                        or details.get("alternate_url")
                    ),
                    "key_skills": vacancy_skills,
                    "description": description,
                    "salary": item.get("salary"),
                    "experience": details.get("experience")
                }

        # Загружаем подробности вакансий
        vacancies = await asyncio.gather(
            *(load_details(item) for item in selected)
        )

        return [
            vacancy for vacancy in vacancies
            if vacancy is not None
        ]