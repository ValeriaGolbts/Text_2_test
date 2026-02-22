"""
Интеграционные тесты для всего пайплайна.
"""

import os
import tempfile
import pytest
from src.pipeline import LectureProcessingPipeline, process_file
from src.models import BlockType


class TestPipeline:
    """Тесты полного пайплайна."""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def create_test_txt(self, content):
        path = os.path.join(self.temp_dir, "test.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path
    
    def test_pipeline_on_simple_text(self):
        content = """
        # Лекция по математике
        
        ## Теорема Пифагора
        
        В прямоугольном треугольнике квадрат гипотенузы равен сумме квадратов катетов.
        
        Формула: $a^2 + b^2 = c^2$
        
        ## Квадратное уравнение
        
        $ax^2 + bx + c = 0$
        
        Дискриминант: D = b^2 - 4ac
        """
        file_path = self.create_test_txt(content)
        
        pipeline = LectureProcessingPipeline()
        result = pipeline.process(file_path)
        
        assert result is not None
        assert len(result.chunks) > 0
        assert result.statistics.total_chunks > 0
        assert result.statistics.total_formulas > 0
        
        # Проверим, что результат можно сериализовать в JSON
        json_dict = result.to_dict()
        assert 'chunks' in json_dict
        assert 'statistics' in json_dict
        assert json_dict['source_file'] == 'test.txt'
    
    def test_process_file_function(self):
        content = "Простой текст без формул."
        file_path = self.create_test_txt(content)
        output_path = os.path.join(self.temp_dir, "output.json")
        
        result = process_file(file_path, output_path=output_path)
        
        assert os.path.exists(output_path)
        assert result is not None

    def test_pipeline_with_code(self):
        """Тест обработки текста с блоком кода."""
        content = """
        # Лекция по Python
        
        Вот пример кода:
        
        ```python
        def hello():
            print("Hello, world!")
        ```
        
        Это функция выводит приветствие.
        """
        file_path = self.create_test_txt(content)
        pipeline = LectureProcessingPipeline()
        result = pipeline.process(file_path)
        
        # Должен быть хотя бы один чанк с типом CODE
        code_chunks = [c for c in result.chunks if c.block_type == BlockType.CODE]
        assert len(code_chunks) >= 1, "Не найден блок кода"
        chunk = code_chunks[0]
        assert "def hello()" in chunk.processed_text
        assert chunk.metadata.get('language') == 'python'
     