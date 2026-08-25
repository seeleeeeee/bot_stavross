import os
import re
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    DATABASE_URL = "postgresql://postgre:3vnGJeGrXy6CChThJYBrdFBXNRj4n8Sa@dpg-da6jm9m1egvs739141t0-a/les_analog"
    
    # Парсим URL прямо в конструкторе класса
    match = re.match(r'postgresql://(.+):(.+)@(.+):(\d+)/(.+)', DATABASE_URL)
    if match:
        DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME = match.groups()
    else:
        DB_HOST = "localhost"
        DB_PORT = "5432"
        DB_USER = "postgres"
        DB_PASSWORD = ""
        DB_NAME = "les_analog"
    
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
    
    @classmethod
    def get_db_url(cls):
        return cls.DATABASE_URL

config = Config()

print(f"🔍 DB_HOST: {config.DB_HOST}")
print(f"🔍 DB_PORT: {config.DB_PORT}")
print(f"🔍 DB_USER: {config.DB_USER}")
print(f"🔍 DB_NAME: {config.DB_NAME}")
print(f"🔍 DATABASE_URL: {config.DATABASE_URL}")