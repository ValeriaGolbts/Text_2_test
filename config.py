# должен содержать все поля из .env:
# Конфигурация для GigaChat API
from pydantic_settings import BaseSettings
from typing import Optional

class GigaChatConfig(BaseSettings):
    
    # 1. Поля с префиксом GIGACHAT_
    GIGACHAT_API_KEY: str                    
    GIGACHAT_MODEL: str = "GigaChat-2-Max"     
    GIGACHAT_BASE_URL: str = "https://gigachat.devices.sberbank.ru/api/v1"  
    GIGACHAT_TIMEOUT: int = 60               
    GIGACHAT_MAX_TOKENS: int = 4000          
    GIGACHAT_TEMPERATURE: float = 0.7        
    
    GIGACHAT_SCOPE: str = "GIGACHAT_API_B2B"  
    
    # 2. Поля без префикса GIGACHAT_ (настройки проекта)
    DEFAULT_QUESTIONS_COUNT: int = 10        
    DEFAULT_DIFFICULTY: str = "medium"       
    DEBUG: bool = True                       
    MAX_TEXT_LENGTH: int = 10000             
    OUTPUT_FORMAT: str = "json"              
    
    class Config:
        env_prefix = ""  
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  

config = GigaChatConfig()
