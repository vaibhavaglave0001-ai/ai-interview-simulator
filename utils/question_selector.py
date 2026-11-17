"""Question selection helpers for interview sessions."""

import csv
import random
import re
import unicodedata
from pathlib import Path

from database import fetch_questions


DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "interview_questions.csv"


def load_questions():
    with DATASET_PATH.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def normalize_question(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def select_questions(category, difficulty, count, domain=None, previous_ids=()):
    """Sample without replacement, preferring new concepts and unseen questions.

    Return an empty list rather than pad an insufficient pool with duplicates.
    No external generation API is used by this application.
    """
    questions = list(fetch_questions(category.lower(), difficulty.lower(), domain))
    if count <= 0:
        return []
    random.shuffle(questions)
    previous_ids = set(previous_ids)
    questions.sort(key=lambda question: question["id"] in previous_ids)
    selected, deferred = [], []
    seen_ids, seen_text, seen_topics = set(), set(), set()
    for question in questions:
        text = normalize_question(question["question"])
        if not text or not question["ideal_answer"].strip():
            continue
        if question["id"] in seen_ids or text in seen_text:
            continue
        seen_ids.add(question["id"])
        seen_text.add(text)
        topic = question["topic"]
        if topic and topic in seen_topics:
            deferred.append(question)
        else:
            selected.append(question)
            if topic:
                seen_topics.add(topic)
    selected.extend(deferred)
    return selected[:count] if len(selected) >= count else []
