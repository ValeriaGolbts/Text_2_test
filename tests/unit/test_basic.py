"""
Базовый тест для проверки инфраструктуры.
"""

def test_environment():
    """Проверяем, что тестовая среда работает."""
    assert 1 + 1 == 2

def test_import():
    """Проверяем, что можем импортировать наши модули."""
    try:
        from src.data_models import Formula, TextChunk
        from src.file_loader import FileLoaderFactory
        assert True
    except ImportError as e:
        print(f"Import error: {e}")
        assert False, f"Failed to import: {e}"

def test_fixture_exists():
    """Проверяем, что тестовый файл существует."""
    import os
    fixture_path = os.path.join("tests", "fixtures", "test_lecture.txt")
    assert os.path.exists(fixture_path), f"Fixture not found: {fixture_path}"
    assert os.path.getsize(fixture_path) > 0, "Fixture file is empty"