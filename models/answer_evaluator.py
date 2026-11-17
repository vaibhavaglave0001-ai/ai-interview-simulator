"""Semantic and TF-IDF answer evaluation."""

import logging
import os
import re
from functools import lru_cache
from threading import Lock, Thread

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


logger = logging.getLogger(__name__)
_model = None
_loading_started = False
_load_lock = Lock()
_inference_lock = Lock()


def _load_model():
    global _model
    try:
        if os.environ.get("INTERVIEW_SCORING", "onnx" if os.environ.get("VERCEL") == "1" else "semantic").lower() == "onnx":
            from models.onnx_encoder import MiniLMEncoder
            model = MiniLMEncoder()
        else:
            import torch
            from sentence_transformers import SentenceTransformer
            torch.set_num_threads(min(4, os.cpu_count() or 1))
            model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        model.encode("Model warmup", show_progress_bar=False)
        _model = model
        logger.info("Semantic evaluator ready")
    except Exception:
        logger.warning("Semantic model unavailable; using TF-IDF until restart", exc_info=True)


def start_model_loading():
    """Load the cached model once in the background without delaying requests."""
    global _loading_started
    if os.environ.get("INTERVIEW_SCORING", "semantic").lower() == "tfidf":
        return
    with _load_lock:
        if not _loading_started:
            _loading_started = True
            if os.environ.get("VERCEL") == "1":
                # A serverless instance may freeze background threads between requests.
                _load_model()
            else:
                Thread(target=_load_model, name="semantic-model-loader", daemon=True).start()


def _clean_text(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def _tfidf_score(user_answer, ideal_answer):
    texts = [_clean_text(user_answer), _clean_text(ideal_answer)]
    if not any(texts):
        return 0.0
    try:
        matrix = TfidfVectorizer(stop_words="english").fit_transform(texts)
    except ValueError:
        return 0.0
    return float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])


@lru_cache(maxsize=256)
def _ideal_embedding(ideal_answer):
    return _model.encode(ideal_answer, show_progress_bar=False)


def _semantic_score(user_answer, ideal_answer):
    embedding = _model.encode(user_answer, show_progress_bar=False)
    return float(cosine_similarity([embedding], [_ideal_embedding(ideal_answer)])[0][0])


def evaluate_answer(user_answer, ideal_answer):
    """Evaluate an answer from 0-100, using embeddings with a reliable fallback."""
    user_answer = _clean_text(user_answer)
    ideal_answer = _clean_text(ideal_answer)
    if not user_answer:
        score = 0.0
        method = "empty-answer"
    else:
        start_model_loading()
        similarity = None
        semantic_enabled = os.environ.get("INTERVIEW_SCORING", "semantic").lower() != "tfidf"
        if semantic_enabled and _model is not None and _inference_lock.acquire(blocking=False):
            try:
                similarity = _semantic_score(user_answer, ideal_answer)
            except Exception:
                logger.warning("Semantic scoring failed; using TF-IDF", exc_info=True)
            finally:
                _inference_lock.release()
        method = "sentence-transformers" if similarity is not None else "tfidf-fallback"
        if similarity is None:
            similarity = _tfidf_score(user_answer, ideal_answer)
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
