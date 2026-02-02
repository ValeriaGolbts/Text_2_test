# Только отправка запросов и получение сырых ответов.
import httpx
import logging
from typing import Dict, Any, Optional
from config import config

logger = logging.getLogger(__name__)

class GigaChatAPIClient:
    """Минималистичный клиент для GigaChat API"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.GIGACHAT_API_KEY
        self.base_url = config.GIGACHAT_BASE_URL
        self.timeout = config.GIGACHAT_TIMEOUT
        self.chat_url = f"{self.base_url}/chat/completions"
        
    async def send_request(self, messages: list, **kwargs) -> Dict[str, Any]:
        """
        Отправляет запрос в GigaChat API и возвращает сырой JSON ответ.
        
        Args:
            messages: Список сообщений в формате GigaChat API
            **kwargs: Дополнительные параметры (max_tokens, temperature и т.д.)
            
        Returns:
            Сырой JSON ответ от API
            
        Raises:
            Exception: При ошибках сети или API
        """
        
        # Формируем тело запроса
        payload = {
            "model": kwargs.get("model", config.GIGACHAT_MODEL),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", config.GIGACHAT_MAX_TOKENS),
            "temperature": kwargs.get("temperature", config.GIGACHAT_TEMPERATURE),
        }
        
        # Заголовки
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        logger.debug(f"Отправка запроса к {self.chat_url}")
        logger.debug(f"Параметры: model={payload['model']}, tokens={payload['max_tokens']}")
        
        try:
            # Ключевое изменение: verify=False отключает проверку SSL
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=False  # ← ОТКЛЮЧАЕМ ПРОВЕРКУ SSL
            ) as client:
                response = await client.post(
                    self.chat_url,
                    json=payload,
                    headers=headers
                )
                
                # Логируем статус
                logger.debug(f"Статус ответа: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text[:200]  # Первые 200 символов ошибки
                    logger.error(f"API Error {response.status_code}: {error_text}")
                    raise Exception(f"API Error {response.status_code}: {error_text}")
                
                # Возвращаем сырой JSON
                return response.json()
                
        except httpx.TimeoutException:
            logger.error(f"Timeout после {self.timeout} секунд")
            raise Exception(f"Timeout после {self.timeout} секунд")
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса: {str(e)}")
            raise
    
    async def check_availability(self) -> bool:
        """Проверяет доступность API и валидность ключа"""
        try:
            # Важно: правильный формат вызова
            test_messages = [{"role": "user", "content": "test"}]
            await self.send_request(messages=test_messages, max_tokens=5)
            return True
        except Exception as e:
            logger.error(f"Ошибка при проверке доступности: {str(e)}")
            return False
