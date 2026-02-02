# config.py должен содержать ВСЕ поля из .env:

from pydantic_settings import BaseSettings
from typing import Optional

class GigaChatConfig(BaseSettings):
    """Конфигурация для GigaChat API"""
    
    # 1. Поля с префиксом GIGACHAT_
    GIGACHAT_API_KEY: str                    # ← ЕСТЬ в .env
    GIGACHAT_MODEL: str = "GigaChat-2-Max"   # ← ЕСТЬ в .env  
    GIGACHAT_BASE_URL: str = "https://gigachat.devices.sberbank.ru/api/v1"  # ← ЕСТЬ
    GIGACHAT_TIMEOUT: int = 60               # ← ЕСТЬ в .env
    GIGACHAT_MAX_TOKENS: int = 4000          # ← ЕСТЬ в .env
    GIGACHAT_TEMPERATURE: float = 0.7        # ← ЕСТЬ в .env
    
    # 2. Поля без префикса GIGACHAT_ (настройки проекта)
    DEFAULT_QUESTIONS_COUNT: int = 10        # ← ЕСТЬ в .env
    DEFAULT_DIFFICULTY: str = "medium"       # ← ЕСТЬ в .env
    DEBUG: bool = True                       # ← ЕСТЬ в .env
    MAX_TEXT_LENGTH: int = 10000             # ← ЕСТЬ в .env
    OUTPUT_FORMAT: str = "json"              # ← ЕСТЬ в .env
    
    class Config:
        env_prefix = ""  # Без префикса, так как имена полей уже полные
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Важно для отладки:
        extra = "ignore"  # Игнорирует лишние поля в .env

config = GigaChatConfig()
