def calculate_score(user_skills, vacancy_skills):
    # Переводим навыки в нижний регистр
    user_skills = {
        skill.lower()
        for skill in user_skills
    }

    vacancy_skills = {
        skill.lower()
        for skill in vacancy_skills
    }

    if not vacancy_skills:
        return 0, [], []

    # Совпавшие навыки
    matched = user_skills & vacancy_skills

    # Навыки, которых нет у пользователя
    missing = vacancy_skills - user_skills

    # Считаем процент
    score = len(matched) / len(vacancy_skills) * 100

    return round(score), list(matched), list(missing)