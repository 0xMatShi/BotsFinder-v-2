import asyncio
import aiohttp

from src.core.scan_events import fetch_target_events
from src.core.scan_trades import fetch_and_extract_wallets
from src.core.scan_wallets import filter_wallets_by_activity, filter_wallets_by_market_count
from src.utils.exporter import save_wallets_to_xlsx
from src.utils.constants import PROXIES
from src.utils.proxy_manager import load_and_assign_uas


async def main():
    # 0. Инициализация прокси и UA
    print("--- Настройка сети ---")
    if PROXIES:
        load_and_assign_uas(PROXIES)
    else:
        print("⚠️ Прокси не заданы, будут использоваться дефолтные заголовки.")

    # Настройка коннектора
    connector = aiohttp.TCPConnector(limit=200, ttl_dns_cache=300)

    async with aiohttp.ClientSession(connector=connector) as session:

        # 1. Сбор событий
        print("\n--- Начинаем сбор событий ---")
        events = await fetch_target_events(session)
        if not events:
            print("Нет событий для сбора сделок.")
            return
        print(f"\n✅ Готово! Собрано событий: {len(events)}")

        # 2. Сбор трейдов
        print("\n--- Начинаем сбор сделок и кошельков ---")
        unique_wallets = await fetch_and_extract_wallets(session, events)
        if not unique_wallets:
            print("Нет сделок, собранных по событиям.")
            return
        print(f"\n✅ Всего найдено уникальных кошельков: {len(unique_wallets)}")

        # 3. Анализ
        print("\n--- Начинаем анализ кошельков ---")
        test_batch = unique_wallets
        
        active_wallets = await filter_wallets_by_activity(session, test_batch)
        if not active_wallets:
            print("Нет активных кошельков после фильтрации.")
            return 
        print(f"\n✅ Активных кошельков после фильтрации: {len(active_wallets)}")

        old_wallets = await filter_wallets_by_market_count(session, active_wallets, min_count=100)
        if not old_wallets:
            print("Нет кошельков, подходящих по количеству рынков.")
            return
        print(f"\n✅ Кошельков с количеством рынков > 100: {len(old_wallets)}")

        # 5. Выгрузка в Excel
        print("\n--- Сохранение результатов ---")
        save_wallets_to_xlsx(old_wallets)  # <--- Вызов новой функции


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
