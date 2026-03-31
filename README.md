# Text_2_test
Разработка системы автоматической генерации тестовых заданий на основе мультимодальных образовательных материалов, интегрированной в Telegram-бот


## Модуль предобработки текста

### Поддерживаемые форматы
- Текстовые: .txt, .pdf, .docx
- Аудио: .mp3 (через Vosk)
- Видео: .mp4 (извлекается аудиодорожка, транскрипция через Vosk)

### Установка
1. Установите Python 3.10 или выше.
2. Установите зависимости:
   pip install -r requirements.txt
3. Установите ffmpeg (необходим для конвертации аудио/видео):
   - Windows: winget install ffmpeg
   - Linux: sudo apt install ffmpeg
   - macOS: brew install ffmpeg
4. Скачайте русскую модель Vosk:
   https://alphacephei.com/vosk/models (vosk-model-small-ru-0.22)
   Распакуйте в папку `src/models/vosk-model-small-ru-0.22`.

### Использование
```python
from src.pipeline import process_file
result = process_file("лекция.mp3", output_path="output.json")
print(f"Обработано чанков: {len(result.chunks)}")
