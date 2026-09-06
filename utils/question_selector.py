"""Question selection helpers for interview sessions."""

import csv
import random
from pathlib import Path


DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "interview_questions.csv"


def load_questions():
    with DATASET_PATH.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def select_questions(category, difficulty, count):
    """Return a random selection, falling back to the available pool size."""
    questions = [
        question for question in load_questions()
        if question["category"].lower() == category.lower()
        and question["difficulty"].lower() == difficulty.lower()
    ]
    random.shuffle(questions)
    return questions[: min(int(count), len(questions))]
