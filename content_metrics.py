"""
content_metrics.py

Содержательные метрики качества тестов
для сравнения стратегий выбора чанков.

Вход:
    output.json
    test_result.json

Выход:
    metrics.json
"""

import json
import re
import numpy as np

from pathlib import Path
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sentence_transformers import SentenceTransformer

class TestMetrics:

    def __init__(self,
                 chunks_file,
                 test_file):

        self.chunks_file = chunks_file
        self.test_file = test_file

        self.chunks=[]
        self.questions=[]

        self.model = SentenceTransformer(
            'paraphrase-multilingual-MiniLM-L12-v2',
            device='cpu'
        )

    def load(self):

        with open(
                self.chunks_file,
                encoding='utf8'
        ) as f:

            data=json.load(f)

        self.chunks=data["chunks"]

        with open(
                self.test_file,
                encoding='utf8'
        ) as f:

            data=json.load(f)

        self.questions=data["questions"]

    def all_chunk_text(self):

        texts=[]

        for c in self.chunks:

            txt=c.get(
                "processed_text",
                ""
            )

            texts.append(txt)

        return texts

    def question_texts(self):

        return [
            q["question"]
            for q in self.questions
        ]

    def extract_terms(self):

        terms=[]

        for c in self.chunks:

            metadata=c.get(
                "metadata",
                {}
            )

            terms.extend(
                metadata.get(
                    "key_terms",
                    []
                )
            )

        return list(
            set(
                x.lower()
                for x in terms
            )
        )

    def term_coverage(self):

        terms=self.extract_terms()

        questions=" ".join(
            self.question_texts()
        ).lower()

        found=0

        for t in terms:

            if t in questions:
                found+=1

        if len(terms)==0:
            return 0

        return found/len(terms)

    def formula_coverage(self):

        formulas=[]

        for c in self.chunks:

            for f in c.get(
                    "formulas",
                    []
            ):

                x=f.get(
                    "normalized",
                    ""
                )

                if x:
                    f
                  ormulas.append(x)

        formulas=list(
            set(formulas)
        )

        all_questions=" ".join(
            self.question_texts()
        )

        found=0

        for f in formulas:

            if f in all_questions:

                found+=1

        if len(formulas)==0:
            return 0

        return found/len(formulas)

    def semantic_relevance(self):

        source=" ".join(
            self.all_chunk_text()
        )

        questions=self.question_texts()

        source_emb=self.model.encode(
            [source]
        )

        q_emb=self.model.encode(
            questions
        )

        sim=cosine_similarity(
            source_emb,
            q_emb
        )[0]

        return np.mean(sim)

    def question_diversity(self):

        questions=self.question_texts()

        embeddings=self.model.encode(
            questions
        )

        sim=cosine_similarity(
            embeddings
        )

        n=len(sim)

        values=[]

        for i in range(n):

            for j in range(i+1,n):

                values.append(
                    sim[i][j]
                )

        mean_similarity=np.mean(
            values
        )

        return 1-mean_similarity

    def redundancy(self):

        questions=self.question_texts()

        vectorizer=TfidfVectorizer()

        X=vectorizer.fit_transform(
            questions
        )

        sim=cosine_similarity(
            X
        )

        n=len(sim)

        duplicates=0
        total=0

        for i in range(n):

            for j in range(i+1,n):

                total+=1

                if sim[i][j]>0.8:

                    duplicates+=1

        if total==0:
            return 0

        return duplicates/total

    def cognitive_variety(self):

        categories={

            "определение":[
                "что",
                "определите"
            ],

            "объяснение":[
                "объясните",
                "почему"
            ],

            "вычисление":[
                "вычислите",
                "найдите"
            ],

            "сравнение":[
                "сравните"
            ],

            "анализ":[
                "проанализируйте"
            ]
        }

        found=[]

        for q in self.question_texts():

            q=q.lower()

            for category,words in categories.items():

                for w in words:

                    if w in q:

                        found.append(
                            category
                        )

        if len(found)==0:
            return 0

        return len(
            set(found)
        )/len(
            categories
        )

    def calculate(self):

        result={

            "term_coverage":
                self.term_coverage(),

            "formula_coverage":
                self.formula_coverage(),

            "semantic_relevance":
                self.semantic_relevance(),

            "question_diversity":
                self.question_diversity(),

            "redundancy":
                self.redundancy(),

            "cognitive_variety":
                self.cognitive_variety()
        }

        result["overall_score"]=(
            0.2*
            result["term_coverage"]

            +

            0.2*
            result["formula_coverage"]

            +

            0.25*
            result["semantic_relevance"]

            +

            0.2*
            result["question_diversity"]

            +

            0.1*
            (
                    1-
                    result["redundancy"]
            )

            +

            0.05*
            result["cognitive_variety"]
        )

        return result

def main():

    metrics=TestMetrics(
        "output.json",
        "test_result.json"
    )

    metrics.load()

    result=metrics.calculate()

    print(
        json.dumps(
            result,
            indent=4,
            ensure_ascii=False
        )
  )

    with open(
            "metrics.json",
            "w",
            encoding="utf8"
    ) as f:

        json.dump(
            result,
            f,
            indent=4,
            ensure_ascii=False
        )

if __name__=="__main__":
    main()
