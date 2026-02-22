"""
Командный интерфейс для системы обработки текста.
"""

import argparse
import sys
import os
import logging
from pathlib import Path

# Добавляем путь к src в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import LectureProcessingPipeline, save_result_to_json

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_command(args):
    """Обработка команды process."""
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"Ошибка: файл не найден: {args.input}")
        return 1
    
    print(f"Обработка файла: {args.input}")
    print(f"Выходной файл: {args.output}")
    print("-" * 50)
    
    try:
        # Создаем конвейер
        pipeline = LectureProcessingPipeline(
            detect_plain_text_formulas=not args.no_plain_text_formulas,
            splitter_type=args.splitter,
            min_chunk_size=args.min_chunk,
            max_chunk_size=args.max_chunk
        )
        
        # Обрабатываем файл
        result = pipeline.process(str(input_path))
        
        # Сохраняем результат
        save_result_to_json(result, args.output)
        
        print(f"Обработка завершена успешно!")
        print(f"Результат сохранен в: {args.output}")
        print()
        print("Статистика:")
        print(f"   Файл: {result.source_file}")
        print(f"   Блоков: {result.statistics.total_chunks}")
        print(f"   Формул: {result.statistics.total_formulas}")
        print(f"   Время обработки: {result.statistics.processing_time_seconds:.2f} сек")
        print(f"   Размер файла: {result.statistics.input_file_size_bytes} байт")
        
        return 0
        
    except Exception as e:
        print(f"Ошибка при обработке: {e}")
        logger.exception("Детали ошибки:")
        return 1


def info_command():
    """Информация о системе."""
    print("=" * 50)
    print("Система обработки учебных материалов")
    print("=" * 50)
    print()
    print("Поддерживаемые форматы: TXT, PDF")
    print("Использование: python -m src.cli process -i файл.pdf -o результат.json")
    print("=" * 50)


def main():
    """Основная функция CLI."""
    parser = argparse.ArgumentParser(
        description='Обработка учебных материалов для генерации тестов'
    )
    
    subparsers = parser.add_subparsers(dest='command', title='команды', help='доступные команды')
    
    # Команда process
    process_parser = subparsers.add_parser('process', help='обработка файла')
    process_parser.add_argument('-i', '--input', required=True, help='входной файл (PDF/TXT)')
    process_parser.add_argument('-o', '--output', default='output.json', help='выходной JSON файл')
    process_parser.add_argument('-s', '--splitter', default='paragraph', 
                               choices=['paragraph', 'semantic', 'fixed_size', 'mixed'],
                               help='стратегия разбиения текста')
    process_parser.add_argument('--min-chunk', type=int, default=100, 
                               help='минимальный размер блока')
    process_parser.add_argument('--max-chunk', type=int, default=2000, 
                               help='максимальный размер блока')
    process_parser.add_argument('--no-plain-text-formulas', action='store_true',
                               help='не искать plain-text формулы')
    process_parser.add_argument('-v', '--verbose', action='store_true',
                               help='подробный вывод')
    
    # Команда info
    subparsers.add_parser('info', help='информация о системе')
    
    # Если не переданы аргументы, показываем помощь
    if len(sys.argv) == 1:
        parser.print_help()
        return 0
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.command == 'process':
        return process_command(args)
    elif args.command == 'info':
        info_command()
        return 0
    else:
        parser.print_help()
        return 0
