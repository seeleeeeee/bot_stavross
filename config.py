import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
    
    @classmethod
    def get_db_config(cls):
        return {
            "host": cls.DB_HOST,
            "port": cls.DB_PORT,
            "user": cls.DB_USER,
            "password": cls.DB_PASSWORD,
            "database": cls.DB_NAME
        }

config = Config()

print(f"🔍 DB_HOST: {config.DB_HOST}")
print(f"🔍 DB_PORT: {config.DB_PORT}")
print(f"🔍 DB_USER: {config.DB_USER}")
print(f"🔍 DB_NAME: {config.DB_NAME}")
print(f"🔍 BOT_TOKEN: {config.BOT_TOKEN[:10]}..." if config.BOT_TOKEN else "❌ BOT_TOKEN не найден!")