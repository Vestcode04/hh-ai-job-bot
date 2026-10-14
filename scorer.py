import asyncio
import logging
from functools import lru_cache


# Обычное сравнение навыков
def calculate_score(user_skills, vacancy_skills):

    user = {
        skill.casefold()
        for skill in user_skills
    }

    vacancy = {
        skill.casefold(): skill
        for skill in vacancy_skills
    }

    if not vacancy:
        return 0, [], []

    matched = [
        name for key, name in vacancy.items()
        if key in user
    ]

    missing = [
        name for key, name in vacancy.items()
        if key not in user
    ]

    score = round(
        len(matched) / len(vacancy) * 100
    )

    return score, matched, missing


# Загружаем AI-модель только один раз
@lru_cache(maxsize=1)
def get_ai_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )


# Рассчитываем смысловое сходство
def calculate_ai_scores(skills, vacancies):

    model = get_ai_model()

    user_text = "Навыки: " + ", ".join(skills)

    texts = [user_text]

    # Формируем текст каждой вакансии
    for vacancy in vacancies:
        vacancy_text = (
            vacancy["name"] + ". "
            + ", ".join(vacancy["key_skills"]) + ". "
            + vacancy["description"][:1500]
        )

        texts.append(vacancy_text)

    # Превращаем тексты в векторы
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False
    )

    # Сравниваем векторы
    scores = []

    for vector in vectors[1:]:
        similarity = float(vectors[0] @ vector)

        score = max(
            0,
            min(100, round(similarity * 100))
        )

        scores.append(score)

    return scores


# Итоговый рейтинг вакансий
async def rank_vacancies(skills, vacancies):

    if not vacancies:
        return []

    # AI работает в отдельном потоке,
    # чтобы не блокировать Telegram-бота
    try:
        ai_scores = await asyncio.to_thread(
            calculate_ai_scores,
            skills,
            vacancies
        )

    except Exception:
        logging.exception("Ошибка локальной AI-модели")

        # Если AI недоступен, обычный scoring продолжит работать
        ai_scores = [None] * len(vacancies)

    results = []

    for vacancy, ai_score in zip(vacancies, ai_scores):

        skill_score, matched, missing = calculate_score(
            skills,
            vacancy["key_skills"]
        )

        if ai_score is None:
            final_score = skill_score
        else:
            # 75% — навыки, 25% — AI-сходство
            final_score = round(
                skill_score * 0.75
                + ai_score * 0.25
            )

        results.append({
            "vacancy": vacancy,
            "score": final_score,
            "skill_score": skill_score,
            "ai_score": ai_score,
            "matched": matched,
            "missing": missing
        })

    # Сортируем по итоговому рейтингу
    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return results