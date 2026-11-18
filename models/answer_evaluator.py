"""Semantic and TF-IDF answer evaluation."""

import logging
import os
import re
from functools import lru_cache
from threading import Lock, Thread

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
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


def _is_non_answer(user_answer, ideal_answer, similarity=None):
    """Reject clear non-answers; leave uncertain/partially correct answers alone.

    The ideal answer supplies the question's topic. A low embedding similarity
    alone is not sufficient: relevant words protect even an incorrect answer.
    This is deliberately conservative, not a general language-understanding model.
    """
    normalized = re.sub(r"[^\w\s]", "", user_answer.lower().replace("\u2019", "'"))
    if re.fullmatch(
        r"(?:sorry\s+)?(?:i\s+)?(?:dont know|do not know|dont understand|"
        r"do not understand|have no idea|no idea|not sure|am not sure|im not sure|"
        r"cannot answer|cant answer|idk|i dunno|dunno)(?:\s+(?:the answer|this|sorry))?",
        normalized,
    ):
        return True

    words = re.findall(r"[^\W\d_]+", user_answer.lower())
    reference = set(re.findall(r"[^\W\d_]+", ideal_answer.lower()))
    # Do not penalize identifiers/acronyms that occur in the reference answer.
    garbage = [word for word in words if word not in reference and (
        re.search(r"(.)\1{3,}|[b-df-hj-np-tv-xz]{6,}", word)
        or re.fullmatch(r"(?:asdf\w*|qwer\w*|zxcv\w*|jkl\w*|xyz)", word)
    )]
    if garbage and len(garbage) * 2 >= len(words):
        return True
    if not words:
        # Numbers and symbolic/code answers may be legitimate short answers.
        return not any(character.isdigit() for character in user_answer) and not (
            user_answer in {"==", "!=", "<=", ">=", "++", "--", "&&", "||"}
            and user_answer in ideal_answer
        )

    content = set(words) - ENGLISH_STOP_WORDS
    if not content:
        return not set(words) <= reference
    # A few topic words must not rescue a clearly unrelated bare word list.
    word_list = len(words) >= 4 and not (set(words) & ENGLISH_STOP_WORDS)
    if word_list and similarity is not None and similarity < 0.25:
        return True
    if content & (reference - ENGLISH_STOP_WORDS):
        return False

    # Only a semantic result can reject an unanchored paraphrase. Reuse the
    # original scorer's inference, before assigning marks, without another model
    # call or waiting for a busy/unavailable model. TF-IDF alone cannot judge it.
    return similarity is not None and similarity < 0.1


def evaluate_answer(user_answer, ideal_answer):
    """Evaluate an answer from 0-100, using embeddings with a reliable fallback."""
    user_answer = _clean_text(user_answer)
    ideal_answer = _clean_text(ideal_answer)
    if not user_answer:
        score = 0.0
        method = "empty-answer"
    elif _is_non_answer(user_answer, ideal_answer):
        score = 0.0
        method = "invalid-answer"
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
        if method == "sentence-transformers" and _is_non_answer(user_answer, ideal_answer, similarity):
            score = 0.0
            method = "invalid-answer"
        else:
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
