# pretty_print_test.py
import json

with open('test_result_S1_random_lecture_20260519_191606.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(json.dumps(data, ensure_ascii=False, indent=2))
