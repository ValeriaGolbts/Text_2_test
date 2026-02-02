from pydantic_settings import BaseSettings
from typing import Optional

class GigaChatConfig(BaseSettings):
    """Конфигурация GigaChat API (B2B тариф)"""
    
    # Обязательные параметры
    api_key: str                      # Ключ API
    
    # Настройки подключения
    base_url: str = "https://gigachat.devices.sberbank.ru/api/v1"
    model: str = "GigaChat-2-Max"    # Модель для B2B
    timeout: int = 60                 # Таймаут в секундах
    
    # Параметры генерации
    max_tokens: int = 4000            # Максимум токенов в ответе
    temperature: float = 0.7          # Креативность (0-2)
    top_p: Optional[float] = 0.9      # Альтернативный параметр креативности
    
    class Config:
        env_prefix = "GIGACHAT_"      # GIGACHAT_API_KEY, GIGACHAT_MODEL и т.д.
        env_file = ".env"             # Берем из .env файла
        env_file_encoding = "utf-8"

config = GigaChatConfig()  # Экземпляр конфигурации
