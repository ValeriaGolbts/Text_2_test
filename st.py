"""
semantic_metrics.py
Семантические метрики для оценки качества тестов технических дисциплин.

Включает:
- N-граммные метрики (BLEU, ROUGE) для оценки дистракторов
- BERTScore для семантической близости вопрос-ответ
- MoverScore для оценки тематического единства и разнообразия
- Метрики глубины сложности вопросов
"""

import json
import re
import math
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional
from collections import Counter, defaultdict
from datetime import datetime

try:
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer, AutoModel
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("Предупреждение: PyTorch/Transformers не установлены. BERTScore и MoverScore недоступны.")

try:
    from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
    from nltk.util import ngrams
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    print("Предупреждение: NLTK не установлен. N-граммные метрики недоступны.")


class NumpyEncoder(json.JSONEncoder):
    """Кастомный JSON энкодер для numpy типов."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, torch.Tensor):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)


def convert_to_serializable(obj):
    """Рекурсивно конвертирует numpy и torch типы в стандартные Python типы."""
    if isinstance(obj, dict):
        return {key: convert_to_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_to_serializable(item) for item in obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, torch.Tensor):
        return obj.tolist()
    else:
        return obj


class NGramDistractorMetrics:
    """
    Оценка качества дистракторов на основе n-граммных метрик.
    BLEU и ROUGE между правильным ответом и дистракторами.
    """
    
    def __init__(self):
        if not NLTK_AVAILABLE:
            raise ImportError("NLTK требуется для n-граммных метрик")
        self.smoother = SmoothingFunction()
    
    def tokenize(self, text: str) -> List[str]:
        """Токенизация текста на слова."""
        return re.findall(r'\b[а-яё]+\b', text.lower())
    
    def compute_bleu(self, reference: str, candidate: str, weights: Tuple = (0.25, 0.25, 0.25, 0.25)) -> float:
        """Вычисляет BLEU score между эталоном и кандидатом."""
        ref_tokens = [self.tokenize(reference)]
        cand_tokens = self.tokenize(candidate)
        
        if len(cand_tokens) < 2 or len(ref_tokens[0]) < 2:
            return 0.0
        
        return sentence_bleu(
            ref_tokens, 
            cand_tokens, 
            weights=weights, 
            smoothing_function=self.smoother.method1
        )
    
    def compute_rouge_n(self, reference: str, candidate: str, n: int = 1) -> Dict[str, float]:
        """Вычисляет ROUGE-N метрики."""
        ref_tokens = self.tokenize(reference)
        cand_tokens = self.tokenize(candidate)
        
        if len(ref_tokens) < n or len(cand_tokens) < n:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        
        ref_ngrams = set(ngrams(ref_tokens, n))
        cand_ngrams = set(ngrams(cand_tokens, n))
        
        if not ref_ngrams or not cand_ngrams:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        
        overlap = ref_ngrams & cand_ngrams
        
        precision = len(overlap) / len(cand_ngrams)
        recall = len(overlap) / len(ref_ngrams)
        
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0.0
        
        return {"precision": precision, "recall": recall, "f1": f1}
    
    def compute_rouge_l(self, reference: str, candidate: str) -> Dict[str, float]:
        """Вычисляет ROUGE-L на основе наибольшей общей подпоследовательности."""
        ref_tokens = self.tokenize(reference)
        cand_tokens = self.tokenize(candidate)
        
        if not ref_tokens or not cand_tokens:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        
        lcs_length = self._lcs_length(ref_tokens, cand_tokens)
        
        precision = lcs_length / len(cand_tokens) if len(cand_tokens) > 0 else 0.0
        recall = lcs_length / len(ref_tokens) if len(ref_tokens) > 0 else 0.0
        
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0.0
        
        return {"precision": precision, "recall": recall, "f1": f1}
    
    def _lcs_length(self, a: List[str], b: List[str]) -> int:
        """Вычисляет длину наибольшей общей подпоследовательности."""
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(m):
            for j in range(n):
                if a[i] == b[j]:
                    dp[i + 1][j + 1] = dp[i][j] + 1
                else:
                    dp[i + 1][j + 1] = max(dp[i + 1][j], dp[i][j + 1])
        
        return dp[m][n]
    
    def evaluate_distractor(self, correct_answer: str, distractor: str) -> Dict[str, Any]:
        """Комплексная оценка одного дистрактора."""
        bleu_score = self.compute_bleu(correct_answer, distractor)
        rouge1 = self.compute_rouge_n(correct_answer, distractor, n=1)
        rouge2 = self.compute_rouge_n(correct_answer, distractor, n=2)
        rouge_l = self.compute_rouge_l(correct_answer, distractor)
        
        optimal_bleu_range = (0.1, 0.4)
        optimal_rouge1_range = (0.2, 0.5)
        
        if optimal_bleu_range[0] <= bleu_score <= optimal_bleu_range[1]:
            bleu_quality = 1.0
        elif bleu_score < optimal_bleu_range[0]:
            bleu_quality = bleu_score / optimal_bleu_range[0]
        else:
            bleu_quality = max(0.0, 1.0 - (bleu_score - optimal_bleu_range[1]) / 0.3)
        
        rouge1_f1 = rouge1["f1"]
        if optimal_rouge1_range[0] <= rouge1_f1 <= optimal_rouge1_range[1]:
            rouge_quality = 1.0
        elif rouge1_f1 < optimal_rouge1_range[0]:
            rouge_quality = rouge1_f1 / optimal_rouge1_range[0]
        else:
            rouge_quality = max(0.0, 1.0 - (rouge1_f1 - optimal_rouge1_range[1]) / 0.3)
        
        quality_score = 0.4 * bleu_quality + 0.35 * rouge_quality + 0.25 * (1.0 - abs(rouge_l["f1"] - rouge1_f1))
        
        return {
            "bleu": float(bleu_score),
            "rouge_1": rouge1,
            "rouge_2": rouge2,
            "rouge_l": rouge_l,
            "bleu_quality": float(bleu_quality),
            "rouge_quality": float(rouge_quality),
            "overall_quality": float(quality_score),
            "is_plausible": bool(quality_score >= 0.5)
        }


class BERTScoreEvaluator:
    """
    Оценка семантической близости на основе BERTScore.
    Используется для проверки релевантности ответа вопросу.
    """
    
    def __init__(self, model_name: str = "bert-base-multilingual-cased"):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch и Transformers требуются для BERTScore")
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self.model_name = model_name
    
    def get_embeddings(self, texts: List[str], batch_size: int = 8) -> torch.Tensor:
        """Получает эмбеддинги для списка текстов."""
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            encoded = self.tokenizer(
                batch, 
                padding=True, 
                truncation=True, 
                return_tensors="pt",
                max_length=512
            ).to(self.device)
            
            with torch.no_grad():
                outputs = self.model(**encoded)
                attention_mask = encoded["attention_mask"]
                token_embeddings = outputs.last_hidden_state
                
                mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
                sum_embeddings = torch.sum(token_embeddings * mask_expanded, 1)
                sum_mask = torch.clamp(mask_expanded.sum(1), min=1e-9)
                mean_embeddings = sum_embeddings / sum_mask
                
                all_embeddings.append(mean_embeddings.cpu())
        
        return torch.cat(all_embeddings, dim=0)
    
    def cosine_similarity(self, a: torch.Tensor, b: torch.Tensor) -> float:
        """Вычисляет косинусное сходство между двумя тензорами."""
        a_norm = F.normalize(a, p=2, dim=-1)
        b_norm = F.normalize(b, p=2, dim=-1)
        return float((a_norm * b_norm).sum().item())
    
    def compute_bertscore(self, question: str, answer: str) -> Dict[str, float]:
        """Вычисляет BERTScore между вопросом и ответом."""
        embeddings = self.get_embeddings([question, answer])
        
        question_embedding = embeddings[0]
        answer_embedding = embeddings[1]
        
        similarity = self.cosine_similarity(
            question_embedding.unsqueeze(0), 
            answer_embedding.unsqueeze(0)
        )
        
        score = max(0.0, min(1.0, similarity))
        
        return {
            "bertscore": float(score),
            "is_relevant": bool(score >= 0.6),
            "relevance_level": "высокая" if score >= 0.8 else "средняя" if score >= 0.6 else "низкая"
        }
    
    def evaluate_question_answer_pair(self, question: str, answer: str) -> Dict[str, Any]:
        """Оценивает пару вопрос-ответ на релевантность."""
        return self.compute_bertscore(question, answer)
    
    def evaluate_all_questions(self, questions: List[Dict]) -> Dict[str, Any]:
        """Оценивает все пары вопрос-ответ в тесте."""
        results = []
        scores = []
        
        for q in questions:
            question_text = q.get('question', '')
            correct_answer = q.get('correct_answer', '')
            
            if question_text and correct_answer:
                evaluation = self.evaluate_question_answer_pair(question_text, correct_answer)
                results.append({
                    "question_id": q.get('id'),
                    "bertscore": float(evaluation["bertscore"]),
                    "is_relevant": bool(evaluation["is_relevant"])
                })
                scores.append(evaluation["bertscore"])
        
        avg_score = float(np.mean(scores)) if scores else 0.0
        relevant_count = int(sum(1 for r in results if r["is_relevant"]))
        
        return {
            "average_bertscore": avg_score,
            "relevant_questions": relevant_count,
            "total_questions": len(questions),
            "relevance_ratio": float(relevant_count / len(questions)) if questions else 0.0,
            "overall_relevance": "хорошая" if avg_score >= 0.75 else "приемлемая" if avg_score >= 0.6 else "низкая",
            "detailed_results": results
        }


class MoverScoreEvaluator:
    """
    Оценка тематического распределения на основе MoverScore.
    Использует расстояние Вассерштейна между распределениями эмбеддингов вопросов.
    """
    
    def __init__(self, model_name: str = "bert-base-multilingual-cased"):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch и Transformers требуются для MoverScore")
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self.model_name = model_name
    
    def get_token_embeddings(self, text: str) -> torch.Tensor:
        """Получает эмбеддинги токенов для текста."""
        encoded = self.tokenizer(
            text, 
            padding=True, 
            truncation=True, 
            return_tensors="pt",
            max_length=512
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**encoded)
            token_embeddings = outputs.last_hidden_state[0]
            attention_mask = encoded["attention_mask"][0]
            
            mask = attention_mask.bool()
            return token_embeddings[mask].cpu()
    
    def wasserstein_distance(self, embeddings_a: torch.Tensor, embeddings_b: torch.Tensor) -> float:
        """Приближенное расстояние Вассерштейна между двумя наборами эмбеддингов."""
        if embeddings_a.size(0) == 0 or embeddings_b.size(0) == 0:
            return 1.0
        
        a_norm = F.normalize(embeddings_a, p=2, dim=1)
        b_norm = F.normalize(embeddings_b, p=2, dim=1)
        
        similarity_matrix = torch.mm(a_norm, b_norm.t())
        
        cost_matrix = 1.0 - similarity_matrix
        
        total_cost = 0.0
        remaining_b = set(range(embeddings_b.size(0)))
        
        for i in range(embeddings_a.size(0)):
            if not remaining_b:
                break
            
            costs_i = cost_matrix[i, list(remaining_b)]
            min_cost_idx_local = torch.argmin(costs_i).item()
            min_cost_idx_global = list(remaining_b)[min_cost_idx_local]
            
            total_cost += cost_matrix[i, min_cost_idx_global].item()
            remaining_b.remove(min_cost_idx_global)
        
        total_elements = max(embeddings_a.size(0), embeddings_b.size(0))
        return float(total_cost / total_elements) if total_elements > 0 else 1.0
    
    def compute_pairwise_moverscores(self, questions: List[str]) -> np.ndarray:
        """Вычисляет MoverScore между всеми парами вопросов."""
        n = len(questions)
        distance_matrix = np.zeros((n, n))
        
        embeddings_cache = {}
        
        for i in range(n):
            if i not in embeddings_cache:
                embeddings_cache[i] = self.get_token_embeddings(questions[i])
            
            for j in range(i + 1, n):
                if j not in embeddings_cache:
                    embeddings_cache[j] = self.get_token_embeddings(questions[j])
                
                distance = self.wasserstein_distance(
                    embeddings_cache[i], 
                    embeddings_cache[j]
                )
                
                distance_matrix[i][j] = distance
                distance_matrix[j][i] = distance
        
        return distance_matrix
    
    def evaluate_test_cohesion(self, questions: List[Dict]) -> Dict[str, Any]:
        """Оценивает тематическое единство и разнообразие теста."""
        if len(questions) < 2:
            return {
                "average_moverscore": 0.5,
                "thematic_cohesion": "недостаточно вопросов",
                "is_optimal": True,
                "score": 0.5,
                "duplicate_pairs": 0,
                "unrelated_pairs": 0,
                "total_pairs": 0
            }
        
        question_texts = [q.get('question', '') for q in questions]
        distance_matrix = self.compute_pairwise_moverscores(question_texts)
        
        upper_triangle = []
        for i in range(len(questions)):
            for j in range(i + 1, len(questions)):
                upper_triangle.append(distance_matrix[i][j])
        
        avg_distance = float(np.mean(upper_triangle))
        std_distance = float(np.std(upper_triangle))
        
        distances = np.array(upper_triangle)
        duplicate_pairs = int(np.sum(distances < 0.2))
        unrelated_pairs = int(np.sum(distances > 0.8))
        
        if 0.3 <= avg_distance <= 0.6:
            cohesion_score = 1.0
            cohesion_level = "оптимальное"
        elif 0.2 <= avg_distance < 0.3:
            cohesion_score = avg_distance / 0.3
            cohesion_level = "тенденция к дублированию"
        elif 0.6 < avg_distance <= 0.8:
            cohesion_score = 1.0 - (avg_distance - 0.6) / 0.3
            cohesion_level = "тенденция к несвязности"
        elif avg_distance < 0.2:
            cohesion_score = 0.2
            cohesion_level = "сильное дублирование"
        else:
            cohesion_score = 0.1
            cohesion_level = "полная несвязность"
        
        return {
            "average_moverscore": avg_distance,
            "std_moverscore": std_distance,
            "duplicate_pairs": duplicate_pairs,
            "unrelated_pairs": unrelated_pairs,
            "total_pairs": len(upper_triangle),
            "thematic_cohesion": cohesion_level,
            "is_optimal": bool(0.3 <= avg_distance <= 0.6),
            "cohesion_score": float(cohesion_score),
            "distance_matrix": distance_matrix.tolist()
        }


class DifficultyDepthMetrics:
    """
    Метрики глубины сложности вопросов на основе энтропии и лексического разнообразия.
    """
    
    def __init__(self):
        self.stop_words = {
            'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 'она', 'так', 'но',
            'да', 'ты', 'к', 'у', 'же', 'вы', 'за', 'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня',
            'еще', 'нет', 'о', 'из', 'ему', 'теперь', 'когда', 'даже', 'ну', 'вдруг', 'ли', 'если', 'уже', 'или',
            'ни', 'быть', 'был', 'него', 'до', 'вас', 'нибудь', 'опять', 'уж', 'вам', 'ведь', 'там', 'потом', 'себя',
            'ничего', 'ей', 'может', 'они', 'тут', 'где', 'есть', 'надо', 'ней', 'для', 'мы', 'тебя', 'их', 'чем',
            'была', 'сам', 'чтоб', 'без', 'будто', 'чего', 'раз', 'тоже', 'себе', 'под', 'будет', 'ж', 'тогда', 'кто',
            'этот', 'того', 'потому', 'этого', 'какой', 'совсем', 'ним', 'здесь', 'этом', 'один', 'почти', 'мой'
        }
    
    def calculate_lexical_diversity(self, text: str) -> float:
        """Вычисляет лексическое разнообразие (TTR)."""
        words = re.findall(r'\b[а-яё]+\b', text.lower())
        if not words:
            return 0.0
        meaningful = [w for w in words if w not in self.stop_words and len(w) > 2]
        if not meaningful:
            return 0.0
        return len(set(meaningful)) / len(meaningful)
    
    def calculate_text_entropy(self, text: str) -> float:
        """Вычисляет нормализованную энтропию текста."""
        words = re.findall(r'\b[а-яё]+\b', text.lower())
        meaningful = [w for w in words if w not in self.stop_words and len(w) > 2]
        if not meaningful:
            return 0.0
        
        freq = Counter(meaningful)
        total = len(meaningful)
        
        entropy = 0.0
        for count in freq.values():
            prob = count / total
            entropy -= prob * math.log2(prob)
        
        max_entropy = math.log2(len(freq)) if len(freq) > 1 else 0.0
        return entropy / max_entropy if max_entropy > 0 else 0.0
    
    def evaluate_question_difficulty(self, questions: List[Dict]) -> Dict[str, Any]:
        """Оценивает глубину сложности вопросов."""
        if not questions:
            return {
                "average_difficulty": 0.0,
                "std_difficulty": 0.0,
                "difficulty_level": "неизвестно",
                "distribution_variance": 0.0,
                "is_valid": False,
                "detailed_analysis": []
            }
        
        difficulty_scores = []
        analysis = []
        
        technical_patterns = [
            r'\b(формул|закон|теорем|принцип|метод|алгоритм|уравнен|расчет|вычислен)',
            r'\b(определите|вычислите|рассчитайте|проанализируйте|сравните|оцените|докажите)',
            r'\b(если|то|когда|при\s+условии|в\s+случае|следовательно|поэтому)'
        ]
        
        for q in questions:
            text = q.get('question', '')
            
            entropy = self.calculate_text_entropy(text)
            diversity = self.calculate_lexical_diversity(text)
            
            technical_complexity = 0
            for pattern in technical_patterns:
                if re.search(pattern, text.lower()):
                    technical_complexity += 1
            technical_complexity = min(1.0, technical_complexity / 2.0)
            
            word_count = len(re.findall(r'\b[а-яё]+\b', text.lower()))
            length_score = min(1.0, word_count / 25.0)
            
            difficulty = (
                0.35 * entropy +
                0.30 * diversity +
                0.20 * technical_complexity +
                0.15 * length_score
            )
            
            difficulty_scores.append(difficulty)
            analysis.append({
                "question_id": q.get('id'),
                "difficulty_score": float(difficulty),
                "entropy": float(entropy),
                "diversity": float(diversity),
                "technical_complexity": float(technical_complexity),
                "difficulty_level": "высокий" if difficulty > 0.7 else "средний" if difficulty > 0.4 else "низкий"
            })
        
        avg_difficulty = float(np.mean(difficulty_scores)) if difficulty_scores else 0.0
        std_difficulty = float(np.std(difficulty_scores)) if difficulty_scores else 0.0
        
        return {
            "average_difficulty": avg_difficulty,
            "std_difficulty": std_difficulty,
            "difficulty_level": "высокий" if avg_difficulty > 0.7 else "средний" if avg_difficulty > 0.4 else "низкий",
            "distribution_variance": std_difficulty,
            "is_valid": bool(0.4 <= avg_difficulty <= 0.8),
            "detailed_analysis": analysis
        }


class ComprehensiveTestEvaluator:
    """
    Комплексная оценка теста, объединяющая все семантические метрики.
    """
    
    def __init__(self, test_data: Dict, test_path: str = None):
        self.test = test_data
        self.test_path = test_path
        self.questions = test_data.get('questions', [])
        
        self.ngram_metrics = NGramDistractorMetrics() if NLTK_AVAILABLE else None
        self.bertscore_evaluator = BERTScoreEvaluator() if TORCH_AVAILABLE else None
        self.moverscore_evaluator = MoverScoreEvaluator() if TORCH_AVAILABLE else None
        self.difficulty_metrics = DifficultyDepthMetrics()
    
    def evaluate_distractors_with_ngrams(self) -> Dict[str, Any]:
        """Оценка всех дистракторов с помощью n-граммных метрик."""
        if not self.ngram_metrics:
            return {"error": "NLTK не установлен", "score": 0.5, "is_valid": True}
        
        results = []
        total_score = 0.0
        
        for q in self.questions:
            options = q.get('options', [])
            correct = q.get('correct_answer', '')
            distractors = [opt for opt in options if opt != correct]
            
            question_distractor_results = []
            for distractor in distractors:
                evaluation = self.ngram_metrics.evaluate_distractor(correct, distractor)
                question_distractor_results.append(evaluation)
                total_score += evaluation["overall_quality"]
            
            avg_quality = float(np.mean([d["overall_quality"] for d in question_distractor_results])) if question_distractor_results else 0.0
            
            results.append({
                "question_id": q.get('id'),
                "distractor_evaluations": question_distractor_results,
                "average_quality": avg_quality
            })
        
        total_distractors = sum(len(r["distractor_evaluations"]) for r in results)
        avg_score = float(total_score / total_distractors) if total_distractors > 0 else 0.0
        
        plausible_count = int(sum(
            1 for r in results 
            for d in r["distractor_evaluations"] 
            if d["is_plausible"]
        ))
        
        return {
            "metric": "N-граммное качество дистракторов",
            "average_quality_score": avg_score,
            "total_distractors": total_distractors,
            "plausible_distractors": plausible_count,
            "plausible_ratio": float(plausible_count / total_distractors) if total_distractors > 0 else 0.0,
            "is_valid": bool(avg_score >= 0.5),
            "score": avg_score,
            "detailed_results": results
        }
    
    def evaluate_question_answer_relevance(self) -> Dict[str, Any]:
        """Оценка релевантности ответов вопросам через BERTScore."""
        if not self.bertscore_evaluator:
            return {"error": "PyTorch/Transformers не установлены", "score": 0.5, "is_valid": True}
        
        return self.bertscore_evaluator.evaluate_all_questions(self.questions)
    
    def evaluate_thematic_cohesion(self) -> Dict[str, Any]:
        """Оценка тематического единства через MoverScore."""
        if not self.moverscore_evaluator:
            return {"error": "PyTorch/Transformers не установлены", "score": 0.5, "is_valid": True}
        
        if len(self.questions) < 2:
            return {
                "metric": "Тематическое единство",
                "average_moverscore": 0.5,
                "thematic_cohesion": "недостаточно вопросов для анализа",
                "is_valid": True,
                "score": 0.5,
                "duplicate_pairs": 0,
                "unrelated_pairs": 0,
                "total_pairs": 0
            }
        
        result = self.moverscore_evaluator.evaluate_test_cohesion(self.questions)
        result["metric"] = "Тематическое единство"
        result["is_valid"] = result["is_optimal"]
        result["score"] = result["cohesion_score"]
        return result
    
    def evaluate_difficulty(self) -> Dict[str, Any]:
        """Оценка глубины сложности."""
        result = self.difficulty_metrics.evaluate_question_difficulty(self.questions)
        result["metric"] = "Глубина сложности"
        result["score"] = result["average_difficulty"]
        return result
    
    def calculate_all_metrics(self) -> Dict[str, Any]:
        """Комплексный расчет всех метрик."""
        
        metrics = {}
        
        metrics["ngram_distractors"] = self.evaluate_distractors_with_ngrams()
        metrics["bertscore_relevance"] = self.evaluate_question_answer_relevance()
        metrics["moverscore_cohesion"] = self.evaluate_thematic_cohesion()
        metrics["difficulty_depth"] = self.evaluate_difficulty()
        
        weights = {
            "ngram_distractors": 0.30,
            "bertscore_relevance": 0.30,
            "moverscore_cohesion": 0.20,
            "difficulty_depth": 0.20
        }
        
        total_score = sum(
            metrics[key].get("score", 0.5) * weights[key] 
            for key in weights
        )
        
        if total_score >= 0.75:
            suitability = "Рекомендован к использованию"
            can_use = True
        elif total_score >= 0.55:
            suitability = "Можно использовать после доработки"
            can_use = True
        elif total_score >= 0.40:
            suitability = "Требует существенной доработки"
            can_use = False
        else:
            suitability = "Непригоден для использования"
            can_use = False
        
        return {
            "test_title": self.test.get('test_title', 'Неизвестный тест'),
            "total_questions": len(self.questions),
            "evaluation_timestamp": datetime.now().isoformat(),
            "source_file": str(self.test_path) if self.test_path else "unknown",
            "metrics": metrics,
            "overall_score": float(total_score),
            "suitability": suitability,
            "can_be_used": bool(can_use)
        }
    
    def save_results(self, output_path: str = None) -> str:
        """Сохраняет результаты в JSON."""
        results = self.calculate_all_metrics()
        
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            source_name = Path(self.test_path).stem if self.test_path else "test"
            output_path = f"semantic_metrics_{source_name}_{timestamp}.json"
        
        results = convert_to_serializable(results)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)
        
        return output_path
    
    def print_report(self):
        """Выводит отчет о качестве теста."""
        results = self.calculate_all_metrics()
        
        print(f"\n{'='*70}")
        print(f"КОМПЛЕКСНАЯ ОЦЕНКА ТЕСТА: {results['test_title']}")
        print(f"{'='*70}")
        print(f"Количество вопросов: {results['total_questions']}")
        print(f"Общая оценка: {results['overall_score']:.3f}")
        print(f"Статус: {results['suitability']}")
        print()
        
        metrics = results['metrics']
        
        ngram = metrics.get('ngram_distractors', {})
        if 'error' not in ngram:
            print(f"N-граммное качество дистракторов: {ngram.get('score', 0):.3f}")
            print(f"  Правдоподобных дистракторов: {ngram.get('plausible_distractors', 0)}/{ngram.get('total_distractors', 0)}")
        else:
            print(f"N-граммные метрики: {ngram['error']}")
        
        bertscore = metrics.get('bertscore_relevance', {})
        if 'error' not in bertscore:
            print(f"BERTScore релевантность вопрос-ответ: {bertscore.get('average_bertscore', 0):.3f}")
            print(f"  Релевантных вопросов: {bertscore.get('relevant_questions', 0)}/{bertscore.get('total_questions', 0)}")
        else:
            print(f"BERTScore: {bertscore['error']}")
        
        moverscore = metrics.get('moverscore_cohesion', {})
        if 'error' not in moverscore:
            print(f"MoverScore тематическое единство: {moverscore.get('average_moverscore', 0):.3f}")
            print(f"  Состояние: {moverscore.get('thematic_cohesion', 'неизвестно')}")
            if 'duplicate_pairs' in moverscore:
                print(f"  Дублирующихся пар: {moverscore['duplicate_pairs']}/{moverscore.get('total_pairs', 0)}")
        else:
            print(f"MoverScore: {moverscore['error']}")
        
        difficulty = metrics.get('difficulty_depth', {})
        print(f"Глубина сложности: {difficulty.get('average_difficulty', 0):.3f}")
        print(f"  Уровень: {difficulty.get('difficulty_level', 'неизвестно')}")
        print(f"  Стандартное отклонение: {difficulty.get('std_difficulty', 0):.3f}")
        
        print(f"\n{'='*70}")
        print(f"РЕКОМЕНДАЦИЯ: {'Тест можно использовать' if results['can_be_used'] else 'Тест требует переработки'}")
        print(f"{'='*70}\n")


def analyze_test(test_path: str, output_dir: str = None) -> Dict[str, Any]:
    """
    Полный анализ теста из файла.
    """
    with open(test_path, 'r', encoding='utf-8') as f:
        test_data = json.load(f)
    
    evaluator = ComprehensiveTestEvaluator(test_data, test_path=test_path)
    evaluator.print_report()
    
    if output_dir:
        output_path = Path(output_dir) / f"semantic_evaluation_{Path(test_path).stem}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        evaluator.save_results(str(output_path))
        print(f"Результаты сохранены: {output_path}")
    
    return evaluator.calculate_all_metrics()


def compare_strategies(test_files: List[str], output_dir: str = None) -> Dict[str, Any]:
    """
    Сравнивает несколько стратегий генерации тестов.
    """
    results = {}
    
    for test_file in test_files:
        strategy_name = Path(test_file).stem
        metrics = analyze_test(test_file, output_dir)
        results[strategy_name] = {
            "file": test_file,
            "overall_score": float(metrics["overall_score"]),
            "suitability": metrics["suitability"],
            "can_be_used": bool(metrics["can_be_used"]),
            "ngram_distractor_score": float(metrics["metrics"]["ngram_distractors"].get("score", 0)),
            "bertscore_relevance": float(metrics["metrics"]["bertscore_relevance"].get("average_bertscore", 0)),
            "moverscore_cohesion": float(metrics["metrics"]["moverscore_cohesion"].get("average_moverscore", 0)),
            "difficulty_depth": float(metrics["metrics"]["difficulty_depth"].get("average_difficulty", 0))
        }
    
    best_strategy = max(results.items(), key=lambda x: x[1]["overall_score"])
    
    comparison = {
        "strategies": results,
        "best_strategy": best_strategy[0],
        "best_score": float(best_strategy[1]["overall_score"]),
        "comparison_timestamp": datetime.now().isoformat()
    }
    
    if output_dir:
        output_path = Path(output_dir) / "strategy_comparison.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        comparison = convert_to_serializable(comparison)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)
        print(f"\nСравнение стратегий сохранено: {output_path}")
    
    print(f"\n{'='*70}")
    print("РЕЗУЛЬТАТЫ СРАВНЕНИЯ СТРАТЕГИЙ")
    print(f"{'='*70}")
    for strategy, data in results.items():
        print(f"\n{strategy}:")
        print(f"  Общая оценка: {data['overall_score']:.3f}")
        print(f"  Статус: {data['suitability']}")
        print(f"  N-граммные дистракторы: {data['ngram_distractor_score']:.3f}")
        print(f"  BERTScore релевантность: {data['bertscore_relevance']:.3f}")
        print(f"  MoverScore связность: {data['moverscore_cohesion']:.3f}")
        print(f"  Глубина сложности: {data['difficulty_depth']:.3f}")
    
    print(f"\n{'='*70}")
    print(f"Лучшая стратегия: {best_strategy[0]} ({best_strategy[1]['overall_score']:.3f})")
    print(f"{'='*70}\n")
    
    return comparison


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python semantic_metrics.py test.json                 - анализ одного теста")
        print("  python semantic_metrics.py test1.json test2.json     - сравнение стратегий")
        sys.exit(0)
    
    test_files = sys.argv[1:]
    
    if len(test_files) == 1:
        analyze_test(test_files[0], output_dir="semantic_metrics_output")
    else:
        compare_strategies(test_files, output_dir="semantic_metrics_output")
