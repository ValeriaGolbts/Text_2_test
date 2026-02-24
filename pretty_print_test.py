# pretty_print_test.py
import json

with open('test_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(json.dumps(data, ensure_ascii=False, indent=2))
