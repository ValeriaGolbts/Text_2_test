"""
Тесты для модуля загрузки файлов.
Упрощенная версия - тестируем только TXT, PDF тесты пропускаем если нет PyMuPDF.
"""

import os
import tempfile
import pytest
from pathlib import Path

# Импортируем только то, что точно есть
from src.file_loader import TxtLoader, FileLoaderFactory, load_file


class TestTxtLoader:
    """Тесты для TxtLoader."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        # Создаем временную директорию для тестовых файлов
        self.temp_dir = tempfile.mkdtemp()
        self.loader = TxtLoader()
        print(f"Создана временная директория: {self.temp_dir}")
    
    def teardown_method(self):
        """Очистка после каждого теста."""
        # Удаляем временную директорию
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"Удалена временная директория: {self.temp_dir}")
    
    def create_test_file(self, content: str, filename: str = "test.txt", 
                        encoding: str = 'utf-8') -> str:
        """
        Создает тестовый файл и возвращает путь к нему.
        
        Args:
            content: Содержимое файла
            filename: Имя файла
            encoding: Кодировка
            
        Returns:
            Полный путь к созданному файлу
        """
        file_path = os.path.join(self.temp_dir, filename)
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)
        
        print(f"Создан тестовый файл: {file_path}, размер: {len(content)} символов")
        return file_path
    
    def test_load_valid_txt_file(self):
        """Тест загрузки корректного TXT файла."""
        content = "Это тестовый файл.\nСодержит несколько строк.\nИ даже формулы: E=mc^2"
        file_path = self.create_test_file(content)
        
        loaded_content = self.loader.load(file_path)
        
        # Проверяем, что содержимое совпадает
        assert loaded_content == content
        assert "тестовый файл" in loaded_content
        assert "E=mc^2" in loaded_content
        print("✓ test_load_valid_txt_file прошел успешно")
    
    def test_load_txt_with_utf8(self):
        """Тест загрузки UTF-8 файла."""
        content = "Русский текст: привет мир\nEnglish text: hello world\nMath: α + β = γ"
        file_path = self.create_test_file(content, encoding='utf-8')
        
        loaded_content = self.loader.load(file_path)
        
        assert loaded_content == content
        assert "привет мир" in loaded_content
        assert "α + β = γ" in loaded_content
        print("✓ test_load_txt_with_utf8 прошел успешно")
    
    def test_load_empty_file_raises_error(self):
        """Тест что загрузка пустого файла вызывает ошибку."""
        file_path = self.create_test_file("")  # Создаем пустой файл
        
        # Ожидаем ошибку ValueError с сообщением "Файл пуст"
        with pytest.raises(ValueError, match="Файл пуст"):
            self.loader.load(file_path)
        print("✓ test_load_empty_file_raises_error прошел успешно")
    
    def test_load_nonexistent_file_raises_error(self):
        """Тест что попытка загрузки несуществующего файла вызывает ошибку."""
        non_existent_path = os.path.join(self.temp_dir, "nonexistent.txt")
        
        # Проверяем что файла действительно нет
        assert not os.path.exists(non_existent_path)
        
        # Ожидаем ошибку FileNotFoundError
        with pytest.raises(FileNotFoundError):
            self.loader.load(non_existent_path)
        print("✓ test_load_nonexistent_file_raises_error прошел успешно")
    
    def test_load_directory_instead_of_file_raises_error(self):
        """Тест что попытка загрузки директории вызывает ошибку."""
        # Пытаемся загрузить директорию вместо файла
        with pytest.raises(ValueError, match="не является файлом"):
            self.loader.load(self.temp_dir)
        print("✓ test_load_directory_instead_of_file_raises_error прошел успешно")
    
    def test_get_metadata_after_load(self):
        """Тест получения метаданных после загрузки файла."""
        content = "Первая строка\nВторая строка\nТретья строка"
        file_path = self.create_test_file(content)
        
        # Загружаем файл
        self.loader.load(file_path)
        
        # Получаем метаданные
        metadata = self.loader.get_metadata()
        
        # Проверяем метаданные
        assert metadata["file_type"] == "txt"
        assert metadata["encoding"] == "utf-8"  # По умолчанию UTF-8
        
        # Проверяем размер файла (в байтах)
        file_size_bytes = os.path.getsize(file_path)
        assert metadata["file_size"] == file_size_bytes
        
        # Проверяем количество строк
        assert metadata["line_count"] == 3
        
        # Проверяем количество символов
        assert metadata["character_count"] == len(content)
        
        print(f"✓ test_get_metadata_after_load прошел успешно. Метаданные: {metadata}")
    
    def test_get_metadata_before_load_returns_empty_dict(self):
        """Тест что метаданные до загрузки файла - пустой словарь."""
        metadata = self.loader.get_metadata()
        assert metadata == {}
        print("✓ test_get_metadata_before_load_returns_empty_dict прошел успешно")
    
    def test_load_file_with_special_characters(self):
        """Тест загрузки файла со специальными символами."""
        content = "Спецсимволы: © ® ™ € £ ¥ \nМатематика: ∫ ∑ ∏ √ ∞ ≠ ≈"
        file_path = self.create_test_file(content)
        
        loaded_content = self.loader.load(file_path)
        
        assert "© ® ™ € £ ¥" in loaded_content
        assert "∫ ∑ ∏ √ ∞ ≠ ≈" in loaded_content
        print("✓ test_load_file_with_special_characters прошел успешно")


class TestFileLoaderFactory:
    """Тесты для фабрики загрузчиков."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.temp_dir = tempfile.mkdtemp()
        print(f"Создана временная директория для фабрики: {self.temp_dir}")
    
    def teardown_method(self):
        """Очистка после каждого теста."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def create_test_file(self, extension: str, content: str = "test content") -> str:
        """Создает тестовый файл с заданным расширением."""
        file_path = os.path.join(self.temp_dir, f"test{extension}")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return file_path
    
    def test_get_loader_for_txt(self):
        """Тест получения загрузчика для TXT файлов."""
        txt_file = self.create_test_file('.txt')
        loader = FileLoaderFactory.get_loader(txt_file)
        
        assert isinstance(loader, TxtLoader)
        print("✓ test_get_loader_for_txt прошел успешно")
    
    def test_get_loader_for_txt_uppercase(self):
        """Тест получения загрузчика для TXT файлов с расширением в верхнем регистре."""
        txt_file = self.create_test_file('.TXT')
        loader = FileLoaderFactory.get_loader(txt_file)
        
        assert isinstance(loader, TxtLoader)
        print("✓ test_get_loader_for_txt_uppercase прошел успешно")
    
    def test_get_loader_for_txt_no_dot(self):
        """Тест получения загрузчика для файла без точки в расширении."""
        # Создаем файл без расширения
        file_path = os.path.join(self.temp_dir, "testfile")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("content")
        
        # Фабрика должна определить что это не поддерживаемый формат
        with pytest.raises(ValueError, match="не поддерживается"):
            FileLoaderFactory.get_loader(file_path)
        print("✓ test_get_loader_for_txt_no_dot прошел успешно")
    
    def test_get_loader_unsupported_format(self):
        """Тест получения загрузчика для неподдерживаемого формата."""
        unsupported_file = self.create_test_file('.xyz')
        
        with pytest.raises(ValueError, match="не поддерживается"):
            FileLoaderFactory.get_loader(unsupported_file)
        print("✓ test_get_loader_unsupported_format прошел успешно")
    
    def test_get_loader_nonexistent_file(self):
        """Тест получения загрузчика для несуществующего файла."""
        with pytest.raises(FileNotFoundError):
            FileLoaderFactory.get_loader("/nonexistent/path/file.txt")
        print("✓ test_get_loader_nonexistent_file прошел успешно")
    
    def test_get_supported_extensions(self):
        """Тест получения списка поддерживаемых расширений."""
        extensions = FileLoaderFactory.get_supported_extensions()
        
        assert isinstance(extensions, list)
        assert '.txt' in extensions
        print(f"✓ test_get_supported_extensions прошел успешно. Поддерживаемые: {extensions}")


class TestLoadFileFunction:
    """Тесты для функции-обертки load_file()."""
    
    def setup_method(self):
        """Настройка перед каждым тестом."""
        self.temp_dir = tempfile.mkdtemp()
        print(f"Создана временная директория для load_file: {self.temp_dir}")
    
    def teardown_method(self):
        """Очистка после каждого теста."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_load_file_success(self):
        """Тест успешной загрузки файла через функцию load_file()."""
        file_path = os.path.join(self.temp_dir, "lecture.txt")
        content = "# Лекция по математике\n\nТеорема Пифагора: a² + b² = c²"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Используем функцию load_file()
        loaded_content, metadata = load_file(file_path)
        
        # Проверяем содержимое
        assert loaded_content == content
        assert "Теорема Пифагора" in loaded_content
        
        # Проверяем метаданные
        assert metadata["file_type"] == "txt"
        assert "file_size" in metadata
        assert metadata["character_count"] == len(content)
        
        print(f"✓ test_load_file_success прошел успешно. Загружено {len(loaded_content)} символов")
    
    def test_load_file_error_propagation(self):
        """Тест что ошибки из загрузчика передаются через load_file()."""
        with pytest.raises(FileNotFoundError):
            load_file("/nonexistent/file.txt")
        print("✓ test_load_file_error_propagation прошел успешно")


class TestDocxLoader:
    """Тесты для DocxLoader """
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def create_test_docx(self, paragraphs):
        """Создаёт простой DOCX файл с указанными параграфами."""
        from docx import Document
        doc = Document()
        for p in paragraphs:
            doc.add_paragraph(p)
        file_path = os.path.join(self.temp_dir, "test.docx")
        doc.save(file_path)
        return file_path
    
    @pytest.mark.skipif(not pytest.importorskip("docx", reason="python-docx не установлен"),
                        reason="Требуется python-docx")
    def test_load_docx(self):
        from src.file_loader import DocxLoader
        
        paras = ["Первый параграф", "Второй параграф", "Третий параграф"]
        file_path = self.create_test_docx(paras)
        
        loader = DocxLoader()
        content = loader.load(file_path)
        metadata = loader.get_metadata()
        
        assert "Первый параграф" in content
        assert "Второй параграф" in content
        assert "Третий параграф" in content
        assert metadata["paragraph_count"] == 3
        assert metadata["file_type"] == "docx"
    
    @pytest.mark.skipif(not pytest.importorskip("docx", reason="python-docx не установлен"),
                        reason="Требуется python-docx")
    def test_factory_returns_docx_loader(self):
        from src.file_loader import FileLoaderFactory
        file_path = self.create_test_docx(["test"])
        loader = FileLoaderFactory.get_loader(file_path)
        from src.file_loader import DocxLoader
        assert isinstance(loader, DocxLoader)