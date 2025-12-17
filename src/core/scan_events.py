import aiohttp
from src.utils.constants import GAMMA_API_URL, TARGET_SLUGS


REQUIRED_COUNT = 800


async def fetch_target_events(session: aiohttp.ClientSession):
    """
    Асинхронно собирает события с использованием переданной сессии aiohttp.
    """
    collected_events = []
    offset = 0
    limit = 500

    print(f"Цель: {REQUIRED_COUNT} событий типов: {TARGET_SLUGS}")

    while len(collected_events) < REQUIRED_COUNT:
        try:
            params = {
                "limit": limit,
                "offset": offset,
                "closed": "true",
                "order": "endDate",
                "ascending": "false"
            }

            # Асинхронный запрос
            async with session.get(f"{GAMMA_API_URL}/events", params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    print(f"Ошибка API {response.status}: {text}")
                    break

                # Асинхронное получение JSON
                data = await response.json()
            
            if not data:
                break

            page_matches = []
            for event in data:
                slug = event.get('slug', '')
                
                if any(target in slug for target in TARGET_SLUGS):
                    page_matches.append(event)

            collected_events.extend(page_matches)

            offset += limit

        except Exception as e:
            print(f"Произошла ошибка: {e}")
            break

    return collected_events[:REQUIRED_COUNT]