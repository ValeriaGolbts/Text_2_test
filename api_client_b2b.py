# api_client_b2b.py - Полная версия
import httpx
import uuid
import json
import logging
from typing import Dict, Any, Optional
from config import config

logger = logging.getLogger(__name__)

class GigaChatB2BClient:
    """Полноценный клиент для GigaChat API B2B тарифа"""
    
    def __init__(self, api_key: Optional[str] = None, scope: Optional[str] = None):
        self.api_key = api_key or config.GIGACHAT_API_KEY
        self.scope = scope or getattr(config, 'GIGACHAT_SCOPE', 'GIGACHAT_API_B2B')
        self.base_url = config.GIGACHAT_BASE_URL
        self.timeout = config.GIGACHAT_TIMEOUT
        self.chat_url = f"{self.base_url}/chat/completions"
        
        # Генерируем уникальный RqUID
        self.rquid = str(uuid.uuid4())
        logger.info(f"Инициализация B2B клиента с RqUID: {self.rquid}")
        
        # Получаем токен
        self.access_token = self._get_access_token()
    
    def _get_access_token(self) -> str:
        """Получает access token"""
        auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": self.rquid
        }
        
        data = {"scope": self.scope}
        
        try:
            with httpx.Client(verify=False, timeout=self.timeout) as client:
                response = client.post(
                    auth_url,
                    headers=headers,
                    data=data
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    logger.info(f"Токен получен, действует {token_data.get('expires_in', 'N/A')} сек")
                    return token_data["access_token"]
                else:
                    error_text = response.text
                    logger.error(f"Ошибка авторизации {response.status_code}: {error_text[:200]}")
                    raise Exception(f"Auth Error {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Ошибка при получении токена: {str(e)}")
            raise
    
    async def send_request(self, messages: list, **kwargs) -> Dict[str, Any]:
        """Отправляет запрос в GigaChat API"""
        
        payload = {
            "model": kwargs.get("model", config.GIGACHAT_MODEL),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", config.GIGACHAT_MAX_TOKENS),
            "temperature": kwargs.get("temperature", config.GIGACHAT_TEMPERATURE),
        }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "RqUID": self.rquid
        }
        
        logger.info(f"Отправка запроса к GigaChat")
        logger.debug(f"RqUID: {self.rquid}")
        
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=False
            ) as client:
                response = await client.post(
                    self.chat_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info("Запрос успешен")
                    return result
                else:
                    error_text = response.text[:200]
                    logger.error(f"API Error {response.status_code}: {error_text}")
                    raise Exception(f"API Error {response.status_code}")
                    
        except httpx.TimeoutException:
            logger.error(f"Таймаут запроса")
            raise Exception(f"Таймаут запроса")
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса: {str(e)}")
            raise
    
    async def check_availability(self) -> bool:
        """Проверяет доступность API"""
        try:
            test_messages = [{"role": "user", "content": "Тест"}]
            await self.send_request(messages=test_messages, max_tokens=5)
            return True
        except Exception as e:
            logger.error(f"API недоступен: {str(e)}")
            return False
    
    def get_rquid(self) -> str:
        """Возвращает текущий RqUID"""
        return self.rquid
