# scripts/test_b2b_correct.py
import httpx
import uuid
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import config

class GigaChatB2BCorrect:
    """Правильная реализация для B2B тарифа"""
    
    def __init__(self):
        self.api_key = config.GIGACHAT_API_KEY
        self.auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        
        # Генерируем RqUID (ОБЯЗАТЕЛЬНО для B2B!)
        self.rquid = str(uuid.uuid4())
        print(f"🔑 Сгенерирован RqUID: {self.rquid}")
        
        # Получаем токен
        self.access_token = self._get_access_token()
    
    def _get_access_token(self) -> str:
        """Получаем access token с ВСЕМИ необходимыми заголовками"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": self.rquid  # ← ОБЯЗАТЕЛЬНО ДЛЯ B2B!
        }
        
        # Для B2B нужно указывать ВСЕ scope через запятую
        data = {
            "scope": "GIGACHAT_API_PERS,GIGACHAT_API_CORP,GIGACHAT_API_B2B"
        }
        
        print(f"\n🔑 Получение токена...")
        print(f"   Scope: {data['scope']}")
        print(f"   RqUID: {self.rquid}")
        
        try:
            with httpx.Client(verify=False, timeout=30) as client:
                response = client.post(
                    self.auth_url,
                    headers=headers,
                    data=data
                )
                
                print(f"   📡 Статус: {response.status_code}")
                
                if response.status_code == 200:
                    token_data = response.json()
                    print(f"   ✅ Токен получен!")
                    print(f"   ⏱️  Действует: {token_data.get('expires_in', 'N/A')} сек")
                    return token_data["access_token"]
                else:
                    error_text = response.text
                    print(f"   ❌ Ошибка: {response.status_code}")
                    print(f"   📝 Ответ: {error_text}")
                    
                    # Пробуем разобрать JSON ошибки
                    try:
                        error_json = json.loads(error_text)
                        print(f"   🔍 Код ошибки: {error_json.get('code', 'N/A')}")
                        print(f"   📖 Сообщение: {error_json.get('message', 'N/A')}")
                    except:
                        pass
                    
                    raise Exception(f"Auth failed: {response.status_code}")
                    
        except Exception as e:
            print(f"   ❌ Исключение: {str(e)}")
            raise
    
    def send_test_request(self) -> Dict[str, Any]:
        """Отправляем тестовый запрос"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "RqUID": self.rquid  # ← ОБЯЗАТЕЛЬНО И ДЛЯ API ЗАПРОСА!
        }
        
        payload = {
            "model": "GigaChat-2-Max",
            "messages": [
                {
                    "role": "user",
                    "content": "Привет! Это тест B2B тарифа. Ответь 'B2B работает'"
                }
            ],
            "max_tokens": 20,
            "temperature": 0.7
        }
        
        print(f"\n📨 Отправка запроса к API...")
        print(f"   Модель: {payload['model']}")
        print(f"   RqUID: {self.rquid}")
        
        try:
            with httpx.Client(verify=False, timeout=30) as client:
                response = client.post(
                    self.api_url,
                    json=payload,
                    headers=headers
                )
                
                print(f"   📡 API статус: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"   ✅ УСПЕХ!")
                    return result
                else:
                    print(f"   ❌ API ошибка: {response.text[:200]}")
                    return None
                    
        except Exception as e:
            print(f"   ❌ Ошибка: {str(e)}")
            return None

def test_with_different_approaches():
    """Тестируем разные подходы"""
    print("🚀 ТЕСТ РАЗНЫХ ПОДХОДОВ ДЛЯ B2B")
    print("=" * 60)
    
    # Подход 1: Все scope сразу (часто работает для B2B)
    print("\n1️⃣ ПОДХОД 1: Все scope через запятую")
    try:
        client = GigaChatB2BCorrect()
        response = client.send_test_request()
        if response:
            print(f"   🎉 Ответ: {response['choices'][0]['message']['content']}")
            return True
    except Exception as e:
        print(f"   ❌ Не сработало: {str(e)[:100]}")
    
    # Подход 2: Только B2B scope с другим RqUID
    print("\n2️⃣ ПОДХОД 2: Только B2B scope")
    try:
        rquid = str(uuid.uuid4())
        headers = {
            "Authorization": f"Bearer {config.GIGACHAT_API_KEY}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": rquid
        }
        
        data = {"scope": "GIGACHAT_API_B2B"}
        
        with httpx.Client(verify=False) as client:
            # Получаем токен
            auth_resp = client.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers=headers,
                data=data
            )
            
            if auth_resp.status_code == 200:
                token = auth_resp.json()["access_token"]
                print(f"   ✅ Токен получен")
                
                # Отправляем запрос
                api_headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "RqUID": rquid
                }
                
                api_payload = {
                    "model": "GigaChat-2-Max",
                    "messages": [{"role": "user", "content": "Тест"}],
                    "max_tokens": 10
                }
                
                api_resp = client.post(
                    "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                    json=api_payload,
                    headers=api_headers
                )
                
                if api_resp.status_code == 200:
                    result = api_resp.json()
                    print(f"   🎉 Ответ: {result['choices'][0]['message']['content']}")
                    return True
            else:
                print(f"   ❌ Ошибка auth: {auth_resp.text[:100]}")
    except Exception as e:
        print(f"   ❌ Ошибка: {str(e)[:100]}")
    
    return False

def main():
    print("🔧 КОНФИГУРАЦИЯ:")
    print(f"   • Модель: GigaChat-2-Max")
    print(f"   • Ключ: {config.GIGACHAT_API_KEY[:30]}...")
    print(f"   • Тариф: B2B")
    print()
    
    # Тестируем разные подходы
    success = test_with_different_approaches()
    
    print("\n" + "=" * 60)
    
    if success:
        print("🎉 B2B ТАРИФ РАБОТАЕТ!")
        print("\n💡 ИСПОЛЬЗУЙТЕ КЛАСС GigaChatB2BCorrect")
    else:
        print("❌ ПРОБЛЕМА С B2B ТАРИФОМ")
        print("\n🔧 ВОЗМОЖНЫЕ ПРИЧИНЫ И РЕШЕНИЯ:")
        print("1. 🔑 НЕВЕРНЫЙ SCOPE В КЛЮЧЕ")
        print("   • Обратитесь к администратору")
        print("   • Попросите проверить scope ключа в панели администратора B2B")
        print()
        print("2. 🚫 КЛЮЧ НЕ АКТИВИРОВАН ДЛЯ B2B")
        print("   • Возможно, ключ создан, но не активирован в B2B системе")
        print("   • Нужна активация администратором")
        print()
        print("3. 📋 ОШИБКА В КОНФИГУРАЦИИ B2B")
        print("   • Проверьте настройки проекта в B2B кабинете")
        print("   • Убедитесь, что модель GigaChat-2-Max доступна")
        print()
        print("4. ⚠️  ТЕХНИЧЕСКАЯ ПРОБЛЕМА")
        print("   • Временные проблемы с API")
        print("   • Попробуйте позже")
        print()
        print("📞 СВЯЖИТЕСЬ С АДМИНИСТРАТОРОМ И ПРЕДОСТАВЬТЕ:")
        print("   • Код ошибки 400")
        print("   • Сообщение 'scope from db not fully includes consumed scope'")
        print("   • Ваш API ключ (первые 10 символов)")
    
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
