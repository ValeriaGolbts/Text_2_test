"""
Модуль для загрузки файлов различных форматов.

Предоставляет абстрактный интерфейс для загрузчиков и конкретные реализации
для поддерживаемых форматов (TXT, PDF, DOCX).
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path
from docx import Document
import pymupdf4llm
from faster_whisper import WhisperModel


import time
from PIL import Image
import io
import re
from .data_models import ProcessingResult 
import fitz  

import json
import wave
import tempfile
import subprocess
import numpy as np

import shutil

# Настройка логирования
logger = logging.getLogger(__name__)


class FileLoader(ABC):
    """Абстрактный базовый класс для загрузчиков файлов."""
    
    @abstractmethod
    def load(self, file_path: str) -> str:
        """
        Загружает содержимое файла.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Текст содержимого файла
            
        Raises:
            FileNotFoundError: Если файл не существует
            ValueError: Если файл пустой или поврежден
        """
        pass
    
    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """
        Возвращает метаданные о загруженном файле.
        
        Returns:
            Словарь с метаданными
        """
        pass
    
    def _validate_file(self, file_path: str) -> None:
        """
        Проверяет существование и доступность файла.
        
        Args:
            file_path: Путь к файлу
            
        Raises:
            FileNotFoundError: Если файл не существует
            ValueError: Если путь указывает на директорию
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        if not os.path.isfile(file_path):
            raise ValueError(f"Указанный путь не является файлом: {file_path}")
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise ValueError(f"Файл пуст: {file_path}")
        
        logger.debug(f"Файл проверен: {file_path}, размер: {file_size} байт") 


class TxtLoader(FileLoader):
    """Загрузчик для текстовых файлов (.txt)."""
    
    def __init__(self):
        self._metadata: Dict[str, Any] = {}
    
    def load(self, file_path: str) -> str:
        """
        Загружает текстовый файл.
        
        Args:
            file_path: Путь к .txt файлу
            
        Returns:
            Содержимое файла как строка
        """
        # Проверяем файл
        self._validate_file(file_path)
        
        # Определяем кодировку
        encoding = self._detect_encoding(file_path)
        
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                content = file.read()
            
            # Сохраняем метаданные
            self._metadata = {
                "file_type": "txt",
                "encoding": encoding,
                "file_size": os.path.getsize(file_path),
                "line_count": content.count('\n') + 1,
                "character_count": len(content)
            }
            
            logger.info(f"Загружен TXT файл: {file_path}, символов: {len(content)}")
            return content
            
        except UnicodeDecodeError as e:
            logger.error(f"Ошибка декодирования файла {file_path}: {e}")
            raise ValueError(f"Не удалось декодировать файл {file_path}. Попробуйте другую кодировку.")
    
    def get_metadata(self) -> Dict[str, Any]:
        return self._metadata.copy()
    
    def _detect_encoding(self, file_path: str) -> str:
        """
        Определяет кодировку текстового файла.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Название кодировки
        """
        # Сначала проверяем BOM (Byte Order Mark) для UTF-8
        try:
            with open(file_path, 'rb') as f:
                raw = f.read(4)
                if raw.startswith(b'\xef\xbb\xbf'):
                    return 'utf-8-sig'  # UTF-8 с BOM
                elif raw.startswith(b'\xff\xfe'):
                    return 'utf-16-le'
                elif raw.startswith(b'\xfe\xff'):
                    return 'utf-16-be'
        except:
            pass
        
        # Пробуем определить по содержимому
        encodings = ['utf-8', 'cp1251', 'koi8-r', 'iso-8859-1', 'cp866']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    # Пробуем прочитать достаточно для определения
                    content = file.read(10000)
                    # Проверяем, нет ли символов замены 
                    if any(ord(char) == 65533 for char in content):
                        continue
                    return encoding
            except UnicodeDecodeError:
                continue
        
        # Если ни одна не подошла, используем utf-8 с игнорированием ошибок
        logger.warning(f"Не удалось определить кодировку для {file_path}, используем utf-8 с игнорированием ошибок")
        return 'utf-8'


class PdfLoader(FileLoader):
    """Загрузчик для PDF файлов (.pdf) с использованием pymupdf4llm."""
    UNICODE_FIX_MAP = {
                # Греческие буквы (строчные)
                '\uf061': 'α', '\uf062': 'β', '\uf063': 'γ', '\uf064': 'δ',
                '\uf065': 'ε', '\uf066': 'ζ', '\uf067': 'η', '\uf068': 'θ',
                '\uf069': 'ι', '\uf06a': 'κ', '\uf06b': 'μ', '\uf06c': 'λ',
                '\uf06d': 'ν', '\uf06e': 'ξ', '\uf06f': 'ο', '\uf070': 'π',
                '\uf071': 'ρ', '\uf072': 'σ', '\uf073': 'σ', '\uf074': 'τ',
                '\uf075': 'υ', '\uf076': 'φ', '\uf077': 'χ', '\uf078': 'ψ',
                '\uf079': 'ω',
                # Греческие буквы (заглавные)
                '\uf041': 'Α', '\uf042': 'Β', '\uf043': 'Γ', '\uf044': 'Δ',
                '\uf045': 'Ε', '\uf046': 'Ζ', '\uf047': 'Η', '\uf048': 'Θ',
                '\uf049': 'Ι', '\uf04a': 'Κ', '\uf04b': 'Λ', '\uf04c': 'Μ',
                '\uf04d': 'Ν', '\uf04e': 'Ξ', '\uf04f': 'Ο', '\uf050': 'Π',
                '\uf051': 'Ρ', '\uf052': 'Σ', '\uf053': 'Τ', '\uf054': 'Υ',
                '\uf055': 'Φ', '\uf056': 'Χ', '\uf057': 'Ψ', '\uf058': 'Ω',
                # Математические операторы и символы
                '\uf03d': '=', '\uf02d': '-', '\uf02b': '+', '\uf02f': '/',
                '\uf027': '*', '\uf03c': '<', '\uf03e': '>', '\uf0b3': '≥',
                '\uf0b4': '≤', '\uf0b5': '≠', '\uf0b6': '≈', '\uf0b7': '∼',
                '\uf0b8': '∝', '\uf0b9': '∞', '\uf0ba': '∂', '\uf0bb': '∇',
                '\uf0bc': '∫', '\uf0bd': '∑', '\uf0be': '∏', '\uf0bf': '√',
                '\uf0c0': '∛', '\uf0c1': '∜',
                # Скобки и пунктуация
                '\uf028': '(', '\uf029': ')', '\uf05b': '[', '\uf05d': ']',
                '\uf07b': '{', '\uf07d': '}', '\uf03a': ':', '\uf03b': ';',
                '\uf02c': ',', '\uf02e': '.', '\uf020': ' ',  # пробел иногда нужен
            }
    
    
    def __init__(self):
        self._metadata: Dict[str, Any] = {}

    
    def load(self, file_path: str) -> str:
        # Проверяем файл (метод из базового класса)
        self._validate_file(file_path)
        
        try:
            # Извлекаем Markdown-текст (формулы будут в LaTeX-обёртках)
            # Отключаем обработку изображений и OCR
            md_text = pymupdf4llm.to_markdown(
                file_path,
                ignore_images=False,
                ignore_graphics=True,    # игнорировать векторную графику
                use_ocr=True,
                force_text=True,
                write_images=False,      # не сохранять изображения в файлы
                embed_images=False       # не встраивать изображения в Markdown
            )
            
            # Применяем замену битых символов
            for bad, good in self.UNICODE_FIX_MAP.items():
                md_text = md_text.replace(bad, good)
            
            # Метаданные
            file_stats = os.stat(file_path)
            self._metadata = {
                "file_type": "pdf",
                "file_size": file_stats.st_size,
                "total_characters": len(md_text),
                "extraction_tool": "pymupdf4llm"
            }
            
            logger.info(f"Загружен PDF файл: {file_path}, символов: {len(md_text)}")
            return md_text
            
        except Exception as e:
            logger.error(f"Ошибка при чтении PDF {file_path}: {e}")
            raise ValueError(f"Не удалось прочитать PDF файл {file_path}: {str(e)}")

    
    def get_metadata(self) -> Dict[str, Any]:
        return self._metadata.copy()
    
import pypandoc

class DocxLoader(FileLoader):
    """Загрузчик для DOCX‑файлов. Конвертирует в Markdown с помощью Pandoc,
    что позволяет извлечь формулы в формате LaTeX ($...$ или $$...$$)."""

    def __init__(self):
        self._metadata = {}

    def load(self, file_path: str) -> str:
        # Проверка, что файл существует и не пуст
        self._validate_file(file_path)

        try:
            md_text = pypandoc.convert_file(
                file_path,
                'markdown',
                format='docx',
                extra_args=['--wrap=none']
            )

            # Сохраняем метаданные
            self._metadata = {
                "file_type": "docx",
                "file_size": os.path.getsize(file_path),
                "total_characters": len(md_text),
                "extraction_tool": "pandoc (via pypandoc)",
                "page_count": None,   # DOCX не хранит точное число страниц
                "character_count": len(md_text)
            }

            logger.info(f"Загружен DOCX файл через Pandoc: {file_path}, символов: {len(md_text)}")
            return md_text

        except Exception as e:
            logger.error(f"Ошибка при конвертации DOCX в Markdown: {e}")
            raise ValueError(f"Не удалось прочитать DOCX файл {file_path}: {str(e)}")

    def get_metadata(self) -> Dict[str, Any]:
        return self._metadata.copy()
        
    
def transcribe_audio_whisper(audio_path: str, model_size: str = "small", device: str = "cpu", compute_type: str = "int8") -> str:
    """
    Транскрибирует аудиофайл (mp3, wav) с помощью faster-whisper.
    model_size: "tiny", "base", "small", "medium", "large-v3-turbo"
    device: "cpu" или "cuda" (если есть GPU)
    compute_type: "int8" (для CPU), "float16" (для GPU)
    """
    # Если файл не wav, конвертируем во временный wav (частота 16 кГц, моно)
    if not audio_path.endswith('.wav'):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name
        FFMPEG_PATH = r"C:\Users\tvn4175\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
        cmd = [FFMPEG_PATH, '-i', audio_path, '-ar', '16000', '-ac', '1', '-y', tmp_wav]
        subprocess.run(cmd, capture_output=True, check=True)
    else:
        tmp_wav = audio_path

    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        # Транскрипция с русским языком, жадный поиск, фильтр VAD
        segments, info = model.transcribe(tmp_wav, beam_size=1, language="ru", vad_filter=True)
        # Собираем текст
        full_text = " ".join(seg.text for seg in segments)
        return full_text
    finally:
        # Удаляем временный wav, если он был создан
        if tmp_wav != audio_path:
            try:
                os.remove(tmp_wav)
            except PermissionError:
                import time
                time.sleep(0.5)
                os.remove(tmp_wav)


class AudioLoader(FileLoader):
    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8"):
        self._metadata = {}
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    def load(self, file_path: str) -> str:
        self._validate_file(file_path)
        # Транскрибируем с помощью Whisper
        text = transcribe_audio_whisper(file_path, self.model_size, self.device, self.compute_type)
        self._metadata = {
            "file_type": "audio",
            "file_size": os.path.getsize(file_path),
            "model": f"whisper_{self.model_size}",
            "device": self.device,
            "character_count": len(text)
        }
        return text

    def get_metadata(self):
        return self._metadata.copy()
    

class VideoLoader(FileLoader):
    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8"):
        self._metadata = {}
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    def load(self, file_path: str) -> str:
        self._validate_file(file_path)
        # Извлекаем аудио во временный mp3
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_audio = tmp.name
        FFMPEG_PATH = r"C:\Users\tvn4175\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
        cmd = [FFMPEG_PATH, '-i', audio_path, '-ar', '16000', '-ac', '1', '-y', tmp_wav]
        subprocess.run(cmd, capture_output=True, check=True)
        try:
            text = transcribe_audio_whisper(tmp_audio, self.model_size, self.device, self.compute_type)
            self._metadata = {
                "file_type": "video",
                "file_size": os.path.getsize(file_path),
                "model": f"whisper_{self.model_size}",
                "device": self.device,
                "character_count": len(text)
            }
            return text
        finally:
            if os.path.exists(tmp_audio):
                os.remove(tmp_audio)

    def get_metadata(self):
        return self._metadata.copy()

class FileLoaderFactory:
    """Фабрика для создания загрузчиков файлов по расширению."""
    
    # Регистр загрузчиков: расширение -> класс загрузчика
    _loaders = {
        '.txt': TxtLoader,
        '.pdf': PdfLoader,
        '.docx': DocxLoader,
        '.mp3': AudioLoader,
        '.mp4': VideoLoader
    }
    
    @classmethod
    def register_loader(cls, extension: str, loader_class: type) -> None:
        """
        Регистрирует новый загрузчик для расширения.
        
        Args:
            extension: Расширение файла (с точкой, например '.docx')
            loader_class: Класс загрузчика
        """
        if not extension.startswith('.'):
            extension = '.' + extension
        
        cls._loaders[extension.lower()] = loader_class
        logger.debug(f"Зарегистрирован загрузчик {loader_class.__name__} для {extension}")
    
    @classmethod
    def get_loader(cls, file_path: str) -> FileLoader:
        """
        Возвращает подходящий загрузчик для файла.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Экземпляр загрузчика
            
        Raises:
            ValueError: Если формат не поддерживается
        """
        path = Path(file_path)
        
        # Проверяем существование файла
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
        
        # Получаем расширение
        extension = path.suffix.lower()
        
        # Ищем подходящий загрузчик
        if extension in cls._loaders:
            loader_class = cls._loaders[extension]
            logger.debug(f"Создан загрузчик {loader_class.__name__} для {file_path}")
            return loader_class()
        
        # Если формат не поддерживается
        supported = list(cls._loaders.keys())
        raise ValueError(
            f"Формат файла {extension} не поддерживается. "
            f"Поддерживаемые форматы: {', '.join(supported)}"
        )
    
    @classmethod
    def get_supported_extensions(cls) -> list:
        """Возвращает список поддерживаемых расширений."""
        return list(cls._loaders.keys())
    

def load_file(file_path: str) -> tuple[str, Dict[str, Any]]:
    """
    Функция для загрузки файла.
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Кортеж (текст, метаданные)
    """
    loader = FileLoaderFactory.get_loader(file_path)
    content = loader.load(file_path)
    metadata = loader.get_metadata()
    return content, metadata


# Пример регистрации дополнительных загрузчиков (для будущего расширения)
def register_default_loaders():
    """Регистрирует все загрузчики по умолчанию."""
    # Уже зарегистрированы через объявление в классе
    pass