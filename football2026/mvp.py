"""
Получает список всех футбольных матчей на сегодня через football-data.org API.

Перед запуском:
1. Зарегистрируйся на https://www.football-data.org/client/register и получи бесплатный токен.
2. Вставь токен в переменную API_TOKEN ниже (или задай через переменную окружения FOOTBALL_DATA_TOKEN).
3. Установи библиотеку requests: pip install requests
"""

import os
import requests

API_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "2b7ff41203e64cde9d052df106d48e51")
URL = "https://api.football-data.org/v4/matches/"


def main():
    headers = {"X-Auth-Token": API_TOKEN}

    response = requests.get(URL, headers=headers)

    if response.status_code != 200:
        print(f"Ошибка запроса: {response.status_code}")
        print(response.text)
        return

    data = response.json()
    matches = data.get("matches", [])

    if not matches:
        print("На сегодня матчей не найдено (или они не входят в бесплатный набор турниров).")
        return

    print(f"Найдено матчей: {len(matches)}\n")

    for match in matches:
        competition = match["competition"]["name"]
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        status = match["status"]
        utc_date = match["utcDate"]

        score = match.get("score", {}).get("fullTime", {})
        home_score = score.get("home")
        away_score = score.get("away")

        if home_score is not None and away_score is not None:
            score_str = f"{home_score}:{away_score}"
        else:
            score_str = "—"

        print(f"[{competition}] {home} {score_str} {away} | статус: {status} | время (UTC): {utc_date}")


if __name__ == "__main__":
    main()