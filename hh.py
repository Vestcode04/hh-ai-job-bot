# Тестовые вакансии, пока HH API недоступен

TEST_VACANCIES = [
    {
        "id": "1",
        "name": "Python Backend Developer",
        "employer": {
            "name": "Test Company"
        },
        "alternate_url": "https://hh.kz/vacancy/1"
    },
    {
        "id": "2",
        "name": "Junior Python Developer",
        "employer": {
            "name": "IT Company"
        },
        "alternate_url": "https://hh.kz/vacancy/2"
    },
    {
        "id": "3",
        "name": "Backend Developer",
        "employer": {
            "name": "Backend Team"
        },
        "alternate_url": "https://hh.kz/vacancy/3"
    }
]


async def search_vacancies(search_text: str):
    # Пока просто возвращаем тестовые вакансии
    return TEST_VACANCIES


async def get_vacancy(vacancy_id: str):
    # Ищем вакансию по id
    for vacancy in TEST_VACANCIES:
        if vacancy["id"] == vacancy_id:
            return vacancy

    return None