import aiohttp
import asyncio
import random
from src.utils.constants import DATA_API_URL, PROXIES
from src.utils.proxy_manager import get_headers_for_proxy

CONCURRENCY_LIMIT = len(PROXIES) if PROXIES else 10


async def _check_single_wallet_activity(session, wallet, semaphore):
    """
    Внутренняя функция проверки одного кошелька.
    Использует семафор для ограничения количества одновременных запросов.
    """
    async with semaphore:
        # Выбираем случайный прокси для этого кошелька (Load Balancing)
        proxy = random.choice(PROXIES) if PROXIES else None
        
        headers = get_headers_for_proxy(proxy)

        try:
            # 1. Получаем закрытые позиции
            pos_params = {"user": wallet, "limit": 50}
            
            async with session.get(f"{DATA_API_URL}/closed-positions", params=pos_params, proxy=proxy, headers=headers) as pos_resp:
                if pos_resp.status != 200:
                    print(f"Ошибка получаения закрытых позиций ({pos_resp.status}): {pos_resp.text} ")
                    return None
                positions = await pos_resp.json()
            
            if not positions:
                return None
            
            # 2. Проверяем рынки
            for pos in positions:
                market_id = pos.get('conditionId')
                if not market_id:
                    continue
                
                trades_params = {
                    "user": wallet,
                    "market": market_id,
                    "limit": 31 
                }
                
                async with session.get(f"{DATA_API_URL}/trades", params=trades_params, proxy=proxy, headers=headers) as trades_resp:
                    if trades_resp.status != 200:
                        print(f"Ошибка проверки сделок ({trades_resp.status}): {trades_resp.text} ")
                        continue
                    
                    trades = await trades_resp.json()
                    
                    if len(trades) > 30:
                        print(f"✅ {wallet[:6]}... активен (>{len(trades)} трейдов)")
                        return wallet # Возвращаем кошелек, если подошел
            
            # Если дошли сюда, значит ни один рынок не подошел
            print(f"❌ {wallet[:6]}... пропуск (мало сделок)")
            return None

        except Exception as e:
            print(f"⚠️ Ошибка {wallet[:6]}...: {e}")
            return None


async def filter_wallets_by_activity(session: aiohttp.ClientSession, wallets):
    """
    Параллельная проверка активности кошельков.
    """
    print(f"\n🚀 Запуск проверки активности для {len(wallets)} кошельков.")
    print(f"⚡ Потоков (активных прокси): {CONCURRENCY_LIMIT}")
    
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    tasks = []

    for wallet in wallets:
        # Создаем задачу для каждого кошелька
        task = asyncio.create_task(_check_single_wallet_activity(session, wallet, semaphore))
        tasks.append(task)
    
    # Запускаем все задачи и ждем их выполнения
    results = await asyncio.gather(*tasks)
    
    # Фильтруем None (те, кто не прошел или ошибка)
    active_wallets = [w for w in results if w is not None]
    
    return active_wallets


async def _check_single_wallet_market_count(session, wallet, min_count, semaphore):
    """
    Внутренняя функция проверки количества рынков одного кошелька.
    """
    async with semaphore:
        proxy = random.choice(PROXIES) if PROXIES else None
        
        headers = get_headers_for_proxy(proxy)

        try:
            params = {"user": wallet}
            async with session.get(f"{DATA_API_URL}/traded", params=params, proxy=proxy, headers=headers) as response:
                if response.status != 200:
                    print(f"Ошибка количества рынков ({response.status}): {response.text} ")
                    return None

                data = await response.json()
            
            traded_count = data.get('traded', 0)
            
            if traded_count >= min_count:
                print(f"✅ {wallet[:6]}... проходит (Traded: {traded_count})")
                return {'address': wallet, 'traded': traded_count}
            else:
                print(f"❌ {wallet[:6]}... мало рынков ({traded_count})")
                return None
            
        except Exception as e:
            print(f"⚠️ Ошибка {wallet[:6]}...: {e}")
            return None


async def filter_wallets_by_market_count(session: aiohttp.ClientSession, wallets, min_count=100):
    """
    Параллельная проверка количества рынков.
    """
    print(f"\n🚀 Запуск проверки количества рынков (min {min_count}).")
    print(f"⚡ Потоков (активных прокси): {CONCURRENCY_LIMIT}")

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    tasks = []
    
    for wallet in wallets:
        task = asyncio.create_task(_check_single_wallet_market_count(session, wallet, min_count, semaphore))
        tasks.append(task)
        
    results = await asyncio.gather(*tasks)
    
    valid_wallets_data = [w for w in results if w is not None]
    
    return valid_wallets_data


