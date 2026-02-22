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
    """Загрузчик для PDF файлов (.pdf)."""
    
    def __init__(self):
        self._metadata: Dict[str, Any] = {}
    
    def load(self, file_path: str) -> str:
        """
        Загружает PDF файл и извлекает текст.
        
        Args:
            file_path: Путь к .pdf файлу
            
        Returns:
            Извлеченный текст из PDF
        """
        # Проверяем файл
        self._validate_file(file_path)
        
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF (fitz) не установлен. Установите: pip install PyMuPDF")
            raise ImportError("Для работы с PDF файлами требуется PyMuPDF. Установите: pip install PyMuPDF")
        
        try:
            text_parts = []
            page_count = 0
            total_chars = 0
            
            # Открываем PDF документ
            with fitz.open(file_path) as doc:
                page_count = len(doc)
                
                for page_num, page in enumerate(doc, start=1):
                    # Извлекаем текст со страницы
                    page_text = page.get_text()
                    text_parts.append(page_text)
                    total_chars += len(page_text)
                    
                    # Добавляем разделитель между страницами (но не после последней)
                    if page_num < page_count:
                        text_parts.append(f"\n\n--- Страница {page_num} ---\n\n")
            
            # Объединяем весь текст
            full_text = "".join(text_parts)
            
            # Сохраняем метаданные
            self._metadata = {
                "file_type": "pdf",
                "page_count": page_count,
                "file_size": os.path.getsize(file_path),
                "total_characters": total_chars,
                "contains_images": self._check_for_images(file_path) if page_count > 0 else False
            }
            
            logger.info(f"Загружен PDF файл: {file_path}, страниц: {page_count}, символов: {total_chars}")
            return full_text
            
        except Exception as e:
            logger.error(f"Ошибка при чтении PDF {file_path}: {e}")
            raise ValueError(f"Не удалось прочитать PDF файл {file_path}: {str(e)}")
    
    def get_metadata(self) -> Dict[str, Any]:
        return self._metadata.copy()
    
    def _check_for_images(self, file_path: str) -> bool:
        """
        Проверяет, содержит ли PDF изображения.
        
        Args:
            file_path: Путь к PDF файлу
            
        Returns:
            True если есть изображения
        """
        try:
            import fitz
            with fitz.open(file_path) as doc:
                for page in doc:
                    if page.get_images():
                        return True
            return False
        except:
            # Если не удалось проверить, возвращаем False
            return False
        
class DocxLoader(FileLoader):
    """Загрузчик для DOCX файлов."""
    
    def __init__(self):
        self._metadata = {}
        if Document is None:
            raise ImportError("Для работы с DOCX требуется python-docx. Установите: pip install python-docx")
    
    def load(self, file_path: str) -> str:
        self._validate_file(file_path)
        
        try:
            doc = Document(file_path)
            paragraphs = []
            for para in doc.paragraphs:
                if para.text.strip():
                    paragraphs.append(para.text)
            
            # Также можно извлечь текст из таблиц, если нужно
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        cell_text = cell.text.strip()
                        if cell_text:
                            paragraphs.append(cell_text)
            
            full_text = "\n\n".join(paragraphs)
            
            self._metadata = {
                "file_type": "docx",
                "file_size": os.path.getsize(file_path),
                "paragraph_count": len(paragraphs),
                "character_count": len(full_text)
            }
            
            logger.info(f"Загружен DOCX файл: {file_path}, параграфов: {len(paragraphs)}")
            return full_text
            
        except Exception as e:
            logger.error(f"Ошибка при чтении DOCX {file_path}: {e}")
            raise ValueError(f"Не удалось прочитать DOCX файл {file_path}: {str(e)}")
    
    def get_metadata(self) -> dict:
        return self._metadata.copy()
    
        
class FileLoaderFactory:
    """Фабрика для создания загрузчиков файлов по расширению."""
    
    # Регистр загрузчиков: расширение -> класс загрузчика
    _loaders = {
        '.txt': TxtLoader,
        '.pdf': PdfLoader,
        '.docx': DocxLoader
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