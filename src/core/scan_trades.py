import aiohttp
import asyncio

from src.utils.constants import DATA_API_URL, PROXIES
from src.utils.proxy_manager import get_headers_for_proxy


if not PROXIES:
    print("⚠️ Внимание: Список PROXIES пуст. Работа будет идти без прокси в один поток.")
    PROXIES = [None] 


async def fetch_trade_page(session, url, params, proxy, retries=3):
    
    # ТЕПЕРЬ БЕРЕМ ЗАКРЕПЛЕННЫЙ HEADER
    request_headers = get_headers_for_proxy(proxy)
    
    request_kwargs = {
        "params": params, 
        "timeout": 10,
        "headers": request_headers,
        "proxy": proxy if proxy else None
    }
    
    for attempt in range(retries):
        try:
            async with session.get(url, **request_kwargs) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        return data
                    except:
                        return []
                elif response.status in [403, 429]:
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    await asyncio.sleep(1)

        except Exception as e:
            await asyncio.sleep(1)
    
    return []


async def fetch_and_extract_wallets(session: aiohttp.ClientSession, events):
    """
    Параллельный сбор трейдов.
    Итерируется по КАЖДОМУ рынку отдельно, применяя к нему "волну" прокси.
    Это гарантирует, что мы выкачаем максимум сделок (до лимита) из каждого события.
    """
    LIMIT = 500      
    MAX_TRADES_PER_MARKET = 100_000 # Лимит сделок на ОДИН рынок
    
    # 1. Извлекаем ID рынков
    condition_ids = []
    for event in events:
        markets = event.get('markets', [])
        for market in markets:
            c_id = market.get('conditionId')
            if c_id:
                condition_ids.append(c_id)
    
    print(f"Из {len(events)} событий извлечено {len(condition_ids)} рынков.")
    
    unique_wallets_set = set()
    
    # 2. Обработка рынков ПО ОДНОМУ
    # Раньше тут был шаг BATCH_SIZE, теперь идем по каждому
    for i, market_id in enumerate(condition_ids):
        
        print(f"\n🚀 Обработка рынка {i+1}/{len(condition_ids)} (ID: {market_id})...")

        base_offset = 0
        market_finished = False
        
        while not market_finished:
            tasks = []
            
            # Формируем волну запросов для ТЕКУЩЕГО рынка
            active_proxies = PROXIES if PROXIES else [None]
            
            for p_index, proxy in enumerate(active_proxies):
                # Сдвиг оффсета
                current_offset = base_offset + (p_index * LIMIT)
                
                # Если мы уже вышли за пределы желаемого миллиона ВНУТРИ волны, 
                # можно не создавать лишние задачи, но для простоты оставим как есть,
                # прерывание сработает ниже.
                
                params = {
                    "market": market_id, # Запрашиваем только один рынок
                    "limit": LIMIT,
                    "offset": current_offset,
                    "takerOnly": "false" 
                }
                
                task = asyncio.create_task(fetch_trade_page(session, f"{DATA_API_URL}/trades", params, proxy))
                tasks.append((task, current_offset))

            print(f"🌊 Запуск волны: Offset {base_offset} ...")
            
            task_objects = [t[0] for t in tasks]
            results = await asyncio.gather(*task_objects)
            
            cnt_in_wave = 0
            
            for idx, data in enumerate(results):
                task_offset = tasks[idx][1]
                
                if not data:
                    # Если первый запрос в волне пустой — значит точно конец
                    if idx == 0 and len(results) > 1:
                        market_finished = True
                else:
                    count = len(data)
                    cnt_in_wave += count
                    
                    # Сразу достаем кошельки
                    for trade in data:
                        w = trade.get('proxyWallet')
                        if w:
                            unique_wallets_set.add(w)
                    
                    if count < LIMIT:
                        market_finished = True
                        # print(f"🏁 Конец данных на offset {task_offset}")
            
            print(f"   -> Волна завершена. Скачано: {cnt_in_wave}. Всего кошельков: {len(unique_wallets_set)}")

            if not market_finished:
                base_offset += (len(active_proxies) * LIMIT)
                
                # Защита: если с ОДНОГО рынка скачали больше миллиона сделок - хватит
                if base_offset >= MAX_TRADES_PER_MARKET: 
                    print(f"🛑 Достигнут лимит {MAX_TRADES_PER_MARKET} сделок для этого рынка.")
                    break

    return list(unique_wallets_set)