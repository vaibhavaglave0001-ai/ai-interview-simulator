"""Semantic and TF-IDF answer evaluation."""

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _clean_text(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def _tfidf_score(user_answer, ideal_answer):
    texts = [_clean_text(user_answer), _clean_text(ideal_answer)]
    if not any(texts):
        return 0.0
    matrix = TfidfVectorizer(stop_words="english").fit_transform(texts)
    return float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])


def _semantic_score(user_answer, ideal_answer):
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode([_clean_text(user_answer), _clean_text(ideal_answer)])
    return float(cosine_similarity([embeddings[0]], [embeddings[1]])[0][0])


def evaluate_answer(user_answer, ideal_answer):
    """Evaluate an answer from 0-100, using embeddings with a reliable fallback."""
    user_answer = _clean_text(user_answer)
    ideal_answer = _clean_text(ideal_answer)
    if not user_answer:
        score = 0.0
        method = "empty-answer"
    else:
        try:
            similarity = _semantic_score(user_answer, ideal_answer)
            method = "sentence-transformers"
        except Exception:
            similarity = _tfidf_score(user_answer, ideal_answer)
            method = "tfidf-fallback"
        score = max(0.0, min(100.0, similarity * 100))

    rounded_score = round(score, 1)
    if rounded_score >= 80:
        level = "Excellent"
        suggestion = "Strong answer. Keep supporting your points with concise, specific examples."
    elif rounded_score >= 60:
        level = "Good"
        suggestion = "Good foundation. Add a little more detail or a concrete example to strengthen it."
    elif rounded_score >= 40:
        level = "Needs Improvement"
        suggestion = "Cover more of the key ideas in the ideal answer and organize your response clearly."
    else:
        level = "Poor"
        suggestion = "Review the topic and answer with the main concept, reasoning, and a relevant example."

    return {
        "score": rounded_score,
        "level": level,
        "suggestion": suggestion,
        "method": method,
    }
