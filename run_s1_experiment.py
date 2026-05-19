import asyncio
from strategy_random_chunks import StrategyRandomChunks

async def run():
    strategy = StrategyRandomChunks(random_seed=42)
    
    result = await strategy.generate_test(
        json_path="output.json",
        num_questions=5,
        difficulty="hard",
        question_types="closed"
    )
    
    print(f"Сгенерировано {len(result.get('questions', []))} вопросов")

asyncio.run(run())
