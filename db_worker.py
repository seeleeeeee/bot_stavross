import asyncpg
from config import config
import logging

logger = logging.getLogger(__name__)

async def init_db():
    """Создает таблицы, если их нет"""
    try:
        conn = await asyncpg.connect(**config.get_db_config())
        
        # Таблица подписчиков
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS report_subscribers (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                chat_id BIGINT NOT NULL,
                username VARCHAR(100),
                first_name VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Таблица цен
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS price_snapshots (
                id SERIAL PRIMARY KEY,
                analog_les_name VARCHAR(255) NOT NULL,
                analog_stavros_name VARCHAR(255),
                stavros_url TEXT,
                price INTEGER,
                max_price INTEGER,
                in_stock BOOLEAN DEFAULT FALSE,
                parsed_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Таблица истории изменений
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS price_change_history (
                id SERIAL PRIMARY KEY,
                analog_les_name VARCHAR(255) NOT NULL,
                old_price INTEGER,
                new_price INTEGER,
                old_max_price INTEGER,
                new_max_price INTEGER,
                change_details TEXT,
                changed_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Индексы
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_snapshots_analog ON price_snapshots(analog_les_name)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_snapshots_date ON price_snapshots(parsed_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_change_analog ON price_change_history(analog_les_name)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_subscribers_telegram ON report_subscribers(telegram_id)
        """)
        
        await conn.close()
        logger.info("✅ База данных инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        return False

async def get_subscribers():
    """Возвращает список активных подписчиков"""
    try:
        conn = await asyncpg.connect(**config.get_db_config())
        rows = await conn.fetch(
            "SELECT telegram_id, chat_id FROM report_subscribers WHERE is_active = TRUE"
        )
        await conn.close()
        return rows
    except Exception as e:
        logger.error(f"Ошибка получения подписчиков: {e}")
        return []

async def add_subscriber(telegram_id: int, chat_id: int, username: str = None, first_name: str = None):
    """Добавляет подписчика"""
    try:
        conn = await asyncpg.connect(**config.get_db_config())
        await conn.execute(
            """
            INSERT INTO report_subscribers (telegram_id, chat_id, username, first_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_id) DO UPDATE SET is_active = TRUE
            """,
            telegram_id, chat_id, username, first_name
        )
        await conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления подписчика: {e}")
        return False

async def remove_subscriber(telegram_id: int):
    """Отписывает пользователя"""
    try:
        conn = await asyncpg.connect(**config.get_db_config())
        await conn.execute(
            "UPDATE report_subscribers SET is_active = FALSE WHERE telegram_id = $1",
            telegram_id
        )
        await conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления подписчика: {e}")
        return False