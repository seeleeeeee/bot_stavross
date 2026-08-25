import asyncio
import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Any

from playwright.async_api import async_playwright
import asyncpg

from config import config

# =====================================================
# НАСТРОЙКИ
# =====================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_CONFIG = config.get_db_config()
ANALOGIES_FILE = "analogies.json"


# =====================================================
# 1. ПАРСЕР ЦЕН
# =====================================================

async def parse_stavros_prices(url: str, max_retries: int = 3) -> List[int]:
    """
    Парсит цены из таблицы #priceTable на сайте Stavros.
    Возвращает список всех уникальных цен.
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                logger.info(f"🔄 Загружаю: {url} (попытка {attempt + 1}/{max_retries})")
                await page.goto(url, wait_until='domcontentloaded', timeout=20000)
                await asyncio.sleep(3)
                
                prices = await page.evaluate('''
                    () => {
                        const prices = [];
                        const table = document.querySelector('#priceTable');
                        if (!table) return prices;
                        
                        const rows = table.querySelectorAll('tbody tr');
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('td');
                            cells.forEach(cell => {
                                const text = cell.textContent.trim();
                                const match = text.match(/(\\d[\\d\\s]*?)\\s*р\\./);
                                if (match) {
                                    const price = parseInt(match[1].replace(/\\s/g, ''));
                                    if (price > 100 && price < 50000) {
                                        prices.push(price);
                                    }
                                }
                            });
                        });
                        
                        return [...new Set(prices)].sort((a, b) => a - b);
                    }
                ''')
                
                await browser.close()
                
                if prices:
                    return prices
                else:
                    logger.warning(f"⚠️ Цены не найдены на {url}")
                    return []
                
        except Exception as e:
            last_error = str(e)
            logger.warning(f"⚠️ Попытка {attempt + 1} провалилась: {e}")
            
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.info(f"⏳ Ждём {wait_time} секунд...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Все попытки провалились: {url}")
    
    return []


# =====================================================
# 2. ЗАГРУЗКА АНАЛОГОВ
# =====================================================

def load_analogies() -> Dict[str, List[Dict]]:
    """Загружает analogies.json"""
    if not os.path.exists(ANALOGIES_FILE):
        logger.error(f"Файл {ANALOGIES_FILE} не найден!")
        return {}
    
    with open(ANALOGIES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    total = sum(len(items) for items in data.values())
    logger.info(f"📦 Загружено {total} аналогов в {len(data)} категориях")
    return data


# =====================================================
# 3. РАБОТА С БАЗОЙ ДАННЫХ
# =====================================================

async def get_db_pool():
    """Создает пул подключений к PostgreSQL"""
    return await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)

async def save_price_snapshot(
    les_name: str,
    stavros_name: str,
    stavros_url: str,
    prices: List[int]
) -> Dict[str, Any]:
    """
    Сохраняет результат парсинга в БД.
    - Если БД пустая — просто сохраняет
    - Если цены не изменились — пропускает
    - Если изменились — пишет новую запись и логирует
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Вычисляем min/max
        min_price = min(prices) if prices else None
        max_price = max(prices) if prices else None
        in_stock = len(prices) > 0
        
        # Проверяем ПОСЛЕДНЮЮ запись для этого товара
        existing = await conn.fetchrow(
            """
            SELECT id, price, max_price, in_stock FROM price_snapshots 
            WHERE analog_les_name = $1 AND analog_stavros_name = $2
            ORDER BY parsed_at DESC LIMIT 1
            """,
            les_name, stavros_name
        )
        
        # Если запись есть — сравниваем
        if existing:
            old_min = existing['price']
            old_max = existing['max_price']
            old_stock = existing['in_stock']
            
            # Проверяем, изменилось ли что-то
            min_changed = (old_min != min_price)
            max_changed = (old_max != max_price)
            stock_changed = (old_stock != in_stock)
            
            # Если ничего не изменилось — пропускаем
            if not min_changed and not max_changed and not stock_changed:
                logger.info(f"⏭️ {les_name}: цены не изменились ({min_price}₽ / {max_price}₽)")
                return {
                    "status": "skipped",
                    "old_price": old_min,
                    "new_price": min_price,
                    "old_max_price": old_max,
                    "new_max_price": max_price,
                    "changed": False,
                    "in_stock": in_stock,
                    "min_price": min_price,
                    "max_price": max_price,
                    "prices": prices
                }
            
            # Если что-то изменилось — пишем новую запись
            await conn.execute(
                """
                INSERT INTO price_snapshots 
                (analog_les_name, analog_stavros_name, stavros_url, 
                 price, max_price, in_stock, parsed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                les_name,
                stavros_name,
                stavros_url,
                min_price,
                max_price,
                in_stock,
                datetime.now()
            )
            
            # Логируем изменения
            if min_changed or max_changed:
                if min_changed and max_changed:
                    change_msg = f"min: {old_min}₽ → {min_price}₽, max: {old_max}₽ → {max_price}₽"
                elif min_changed:
                    change_msg = f"min: {old_min}₽ → {min_price}₽, max: {old_max}₽"
                else:  # max_changed
                    change_msg = f"min: {old_min}₽, max: {old_max}₽ → {max_price}₽"
                
                await conn.execute(
                    """
                    INSERT INTO price_change_history 
                    (analog_les_name, old_price, new_price, old_max_price, new_max_price, change_details)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    les_name, 
                    old_min, min_price, 
                    old_max, max_price,
                    change_msg
                )
                logger.info(f"🔄 {les_name}: {change_msg}")
            elif stock_changed:
                stock_msg = f"был {'в наличии' if old_stock else 'под заказ'} → {'в наличии' if in_stock else 'под заказ'}"
                await conn.execute(
                    """
                    INSERT INTO price_change_history 
                    (analog_les_name, old_price, new_price, old_max_price, new_max_price, change_details)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    les_name, 
                    old_min, min_price, 
                    old_max, max_price,
                    stock_msg
                )
                logger.info(f"🔄 {les_name}: {stock_msg}")
            
            return {
                "status": "ok",
                "old_price": old_min,
                "new_price": min_price,
                "old_max_price": old_max,
                "new_max_price": max_price,
                "changed": True,
                "in_stock": in_stock,
                "min_price": min_price,
                "max_price": max_price,
                "prices": prices
            }
        
        # Если записи нет — просто сохраняем
        else:
            await conn.execute(
                """
                INSERT INTO price_snapshots 
                (analog_les_name, analog_stavros_name, stavros_url, 
                 price, max_price, in_stock, parsed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                les_name,
                stavros_name,
                stavros_url,
                min_price,
                max_price,
                in_stock,
                datetime.now()
            )
            logger.info(f"✅ {les_name}: первая запись ({min_price}₽ / {max_price}₽)")
            
            return {
                "status": "first",
                "old_price": None,
                "new_price": min_price,
                "old_max_price": None,
                "new_max_price": max_price,
                "changed": False,
                "in_stock": in_stock,
                "min_price": min_price,
                "max_price": max_price,
                "prices": prices
            }


# =====================================================
# 4. ОБХОД ВСЕХ АНАЛОГОВ
# =====================================================

async def parse_all_analogs() -> Dict[str, Any]:
    """
    Проходит по всем аналогам из JSON, парсит и сохраняет в БД.
    """
    analogies = load_analogies()
    if not analogies:
        return {"error": "Не удалось загрузить analogies.json"}
    
    results = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "first": 0,
        "changes": [],
        "errors": [],
        "by_category": {},
        "price_details": []
    }
    
    for category, items in analogies.items():
        category_result = {"total": len(items), "success": 0, "failed": 0, "skipped": 0}
        
        for idx, item in enumerate(items):
            results["total"] += 1
            les_name = item.get('les_name', 'Неизвестно')
            stavros_name = item.get('stavros_name', 'Неизвестно')
            stavros_url = item.get('stavros_link')
            
            logger.info(f"📌 [{idx + 1}/{len(items)}] {les_name} → {stavros_name}")
            
            if not stavros_url:
                results["failed"] += 1
                category_result["failed"] += 1
                results["errors"].append(f"{les_name}: нет ссылки на Stavros")
                continue
            
            try:
                prices = await parse_stavros_prices(stavros_url)
                
                if not prices:
                    results["failed"] += 1
                    category_result["failed"] += 1
                    results["errors"].append(f"{les_name}: цены не найдены")
                    continue
                
                save_result = await save_price_snapshot(
                    les_name, stavros_name, stavros_url, prices
                )
                
                # Сохраняем детали для отчета
                results["price_details"].append({
                    "les_name": les_name,
                    "stavros_name": stavros_name,
                    "min_price": min(prices),
                    "max_price": max(prices),
                    "all_prices": prices,
                    "in_stock": True
                })
                
                if save_result.get('status') == 'ok':
                    results["success"] += 1
                    category_result["success"] += 1
                    
                    if save_result.get('changed'):
                        results["changes"].append({
                            "les_name": les_name,
                            "old_price": save_result['old_price'],
                            "new_price": save_result['new_price'],
                            "old_max_price": save_result.get('old_max_price'),
                            "new_max_price": save_result.get('new_max_price'),
                            "in_stock": save_result['in_stock'],
                            "url": stavros_url
                        })
                
                elif save_result.get('status') == 'first':
                    results["success"] += 1
                    results["first"] += 1
                    category_result["success"] += 1
                
                elif save_result.get('status') == 'skipped':
                    results["skipped"] += 1
                    category_result["skipped"] += 1
                    results["success"] += 1
                
                else:
                    results["failed"] += 1
                    category_result["failed"] += 1
                    results["errors"].append(f"{les_name}: {save_result.get('message', 'Ошибка сохранения')}")
                
            except Exception as e:
                results["failed"] += 1
                category_result["failed"] += 1
                results["errors"].append(f"{les_name}: {str(e)}")
            
            await asyncio.sleep(0.5)
        
        results["by_category"][category] = category_result
    
    return results


# =====================================================
# 5. ФОРМИРОВАНИЕ ОТЧЕТА
# =====================================================

def format_report(results: Dict[str, Any]) -> str:
    """Форматирует результаты парсинга в читаемый отчет"""
    if results.get('error'):
        return f"❌ {results['error']}"
    
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    
    lines = [
        f"📊 <b>ОТЧЕТ ПО ПАРСИНГУ ЦЕН</b>",
        f"📅 {now}",
        f"",
        f"📦 <b>ИТОГО:</b> {results['total']} позиций",
        f"   ✅ Успешно: {results['success']}",
        f"   ❌ Ошибок: {results['failed']}",
        f"   🆕 Первых записей: {results.get('first', 0)}",
        f"   ⏭️ Без изменений: {results.get('skipped', 0)}",
        f"   🔄 Изменений: {len(results['changes'])}",
        f"",
        f"📂 <b>ПО КАТЕГОРИЯМ:</b>"
    ]
    
    for category, stats in results.get('by_category', {}).items():
        lines.append(f"   • {category}: {stats['success']}/{stats['total']} ✅")
    
    # Добавляем детали по ценам
    if results.get('price_details'):
        lines.append(f"")
        lines.append(f"💰 <b>ТЕКУЩИЕ ЦЕНЫ (min/max):</b>")
        for detail in results['price_details'][:15]:
            min_p = detail.get('min_price', '❌')
            max_p = detail.get('max_price', '❌')
            stock = '✅' if detail.get('in_stock') else '⏳'
            
            if min_p == max_p:
                lines.append(f"   • {detail['les_name']}: {min_p}₽ {stock}")
            else:
                lines.append(f"   • {detail['les_name']}: {min_p}₽ – {max_p}₽ {stock}")
        
        if len(results['price_details']) > 15:
            lines.append(f"   ... и ещё {len(results['price_details']) - 15} позиций")
    
    if results['changes']:
        lines.append(f"")
        lines.append(f"🔄 <b>ИЗМЕНЕНИЯ ЦЕН:</b>")
        for change in results['changes'][:10]:
            old_min = change.get('old_price', '?')
            new_min = change.get('new_price', '?')
            old_max = change.get('old_max_price')
            new_max = change.get('new_max_price')
            
            if old_max is not None and new_max is not None and old_max != new_max:
                lines.append(
                    f"   • {change['les_name']}: "
                    f"min {old_min}₽ → {new_min}₽, "
                    f"max {old_max}₽ → {new_max}₽ "
                    f"({'В наличии ✅' if change['in_stock'] else 'Под заказ ⏳'})"
                )
            else:
                lines.append(
                    f"   • {change['les_name']}: "
                    f"{old_min}₽ → {new_min}₽ "
                    f"({'В наличии ✅' if change['in_stock'] else 'Под заказ ⏳'})"
                )
        if len(results['changes']) > 10:
            lines.append(f"   ... и ещё {len(results['changes']) - 10} изменений")
    
    if results['errors']:
        lines.append(f"")
        lines.append(f"⚠️ <b>ОШИБКИ:</b>")
        for err in results['errors'][:5]:
            lines.append(f"   • {err}")
        if len(results['errors']) > 5:
            lines.append(f"   ... и ещё {len(results['errors']) - 5} ошибок")
    
    return "\n".join(lines)


# =====================================================
# 6. ТОЧКА ВХОДА
# =====================================================

async def main():
    """Тестовый запуск парсера"""
    print("🚀 Запуск парсера всех аналогов...")
    print(f"📁 Файл: {ANALOGIES_FILE}")
    print(f"📊 БД: {DB_CONFIG['database']} на {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print("-" * 50)
    
    results = await parse_all_analogs()
    
    print("\n" + "=" * 50)
    print(format_report(results))
    print("=" * 50)
    
    with open("parse_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 Полный отчет сохранен в parse_report.json")

if __name__ == "__main__":
    asyncio.run(main())