# api_client_b2b.py - Специальный клиент для B2B тарифа
import httpx
import uuid  # ← ДОБАВИТЬ ЭТОТ ИМПОРТ
import logging
from typing import Dict, Any, Optional
from config import config

logger = logging.getLogger(__name__)

class GigaChatB2BClient:
    """Клиент для GigaChat API B2B тарифа"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GIGACHAT_API_KEY
        self.scope = config.GIGACHAT_SCOPE
        self.base_url = config.GIGACHAT_BASE_URL
        self.timeout = config.GIGACHAT_TIMEOUT
        self.chat_url = f"{self.base_url}/chat/completions"
        
        # Генерируем RqUID (ОБЯЗАТЕЛЬНО для B2B!)
        self.rquid = str(uuid.uuid4())
        logger.debug(f"Сгенерирован RqUID: {self.rquid}")
        
        # Авторизуемся и получаем access token
        self.access_token = self._get_access_token()
        
    def _get_access_token(self) -> str:
        """Получаем access token для B2B тарифа"""
        auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": self.rquid  # ← ДОБАВИТЬ ЭТОТ ЗАГОЛОВОК!
        }
        
        data = {
            "scope": self.scope
        }
        
        try:
            # Отключаем SSL проверку для тестирования
            with httpx.Client(verify=False) as client:
                response = client.post(
                    auth_url,
                    headers=headers,
                    data=data,
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    error_text = response.text[:200]
                    logger.error(f"Auth Error {response.status_code}: {error_text}")
                    raise Exception(f"Auth Error {response.status_code}: {error_text}")
                
                token_data = response.json()
                logger.debug(f"Токен получен, действует {token_data.get('expires_in', 'N/A')} сек")
                return token_data["access_token"]
                
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
            "RqUID": self.rquid  # ← ДОБАВИТЬ И ЗДЕСЬ!
        }
        
        logger.debug(f"Отправка запроса к {self.chat_url}")
        logger.debug(f"Параметры: model={payload['model']}, tokens={payload['max_tokens']}")
        logger.debug(f"RqUID: {self.rquid}")
        
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=False  # Отключаем SSL для тестирования
            ) as client:
                response = await client.post(
                    self.chat_url,
                    json=payload,
                    headers=headers
                )
                
                logger.debug(f"Статус ответа: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text[:200]
                    logger.error(f"API Error {response.status_code}: {error_text}")
                    raise Exception(f"API Error {response.status_code}: {error_text}")
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса: {str(e)}")
            raise
    
    async def check_availability(self) -> bool:
        """Проверяет доступность API"""
        try:
            test_messages = [{"role": "user", "content": "Привет"}]
            await self.send_request(messages=test_messages, max_tokens=5)
            return True
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности: {str(e)}")
            return False
