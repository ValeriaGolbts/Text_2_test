test_files = [
    "test_result_s2.json",
    "test_result_s3.json",
    "test_result_s4.json",
    "test_result_s5.json",
]

results = await evaluator.evaluate_multiple("output.json", test_files)
evaluator.print_comparison_table(results)
