"""Non-answer rejection and exact preservation of the existing scoring path."""

import os
import unittest
from unittest.mock import Mock, patch

from models import answer_evaluator as evaluator


IDEAL = (
    "Python is a high-level, interpreted programming language known for readable "
    "syntax and a large standard library."
)
VALID_ANSWERS = {
    "meaningful but incorrect": "Python is a compiled database engine that stores rows.",
    "partially correct": "Python is a language used to write programs.",
    "fully correct": "Python is a programming language used for software development and automation.",
    "detailed technical": (
        "Python is a high-level, dynamically typed, interpreted programming language. "
        "It supports functions, classes, generators and exception handling. Its standard "
        "library supports automation, file processing and networking."
    ),
    "short but correct": "Programming language.",
    "short partial": "It is interpreted.",
    "paraphrase": "A tool for writing scripts.",
    "uncertainty with substance": "I don't know all the details, but Python is a programming language.",
}
INVALID_ANSWERS = (
    "asdfgh jklqwe zxcvbn",
    "qwertyuiop",
    "aaaaaaa bbbbbbb ccccccc",
    "banana car table running xyz",
    "I don't know",
    "I don’t know.",
    "I do not know",
    "No idea!",
    "I'm not sure",
    "!!! ???",
    # Repetition and technical keywords must not rescue obvious gibberish.
    "asdfgh jklqwe zxcvbn Python programming",
    "asdfgh jklqwe zxcvbn " * 100,
)


class AnswerValidationTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.dict(os.environ, {"INTERVIEW_SCORING": "tfidf"})
        self.settings.start()
        self.model = patch.object(evaluator, "_model", None)
        self.model.start()
        self.loading = patch.object(evaluator, "_loading_started", True)
        self.loading.start()
        evaluator._ideal_embedding.cache_clear()

    def tearDown(self):
        evaluator._ideal_embedding.cache_clear()
        self.loading.stop()
        self.model.stop()
        self.settings.stop()

    def assert_original_result(self, answer, ideal=IDEAL):
        # Bypassing only the guard executes the untouched original scoring path.
        with patch.object(evaluator, "_is_non_answer", return_value=False):
            original = evaluator.evaluate_answer(answer, ideal)
        self.assertEqual(evaluator.evaluate_answer(answer, ideal), original)

    def test_invalid_answers_zero_in_fallback_and_positive_semantic_scoring(self):
        for mode in ("tfidf", "semantic"):
            with patch.dict(os.environ, {"INTERVIEW_SCORING": mode}), patch.object(
                evaluator, "_semantic_score", return_value=0.73
            ):
                # Even a scorer willing to award 73 cannot rescue a non-answer.
                evaluator._model = Mock() if mode == "semantic" else None
                for answer in INVALID_ANSWERS:
                    if mode == "semantic" and answer == "banana car table running xyz":
                        # This requires real semantic validation, tested below;
                        # a constant similarity stub cannot assess relevance.
                        continue
                    with self.subTest(mode=mode, answer=answer[:60]):
                        self.assertEqual(evaluator.evaluate_answer(answer, IDEAL)["score"], 0)

    def test_empty_answer(self):
        for answer in (None, "", "  \n\t"):
            with self.subTest(answer=answer):
                result = evaluator.evaluate_answer(answer, IDEAL)
                self.assertEqual(result["score"], 0)
                self.assertEqual(result["method"], "empty-answer")

    def test_valid_fallback_results_are_identical(self):
        for name, answer in VALID_ANSWERS.items():
            with self.subTest(case=name):
                self.assert_original_result(answer)

    def test_all_existing_reference_answers_pass_validation(self):
        from data.question_bank import bank_rows

        for question, category, difficulty, ideal, domain, topic in bank_rows():
            with self.subTest(question=question):
                self.assertFalse(evaluator._is_non_answer(ideal, ideal))

    def test_short_technical_and_hr_answers_remain_unchanged(self):
        for answer, ideal in (
            ("with", "Use with to acquire and release resources safely."),
            ("ACID", "ACID means atomicity, consistency, isolation and durability."),
            ("42", "The result is 42."),
            ("==", "Use == to compare values."),
            ("Atomicity consistency isolation durability", "ACID means atomicity, consistency, isolation and durability."),
            ("I coached two interns through weekly code reviews.", "Explain your actions and the measurable outcome."),
        ):
            with self.subTest(answer=answer):
                self.assert_original_result(answer, ideal)

    def test_busy_unavailable_and_failed_validation_preserve_scoring(self):
        answer = VALID_ANSWERS["paraphrase"]
        with patch.dict(os.environ, {"INTERVIEW_SCORING": "semantic"}):
            self.assert_original_result(answer)
            evaluator._model = Mock()
            evaluator._inference_lock.acquire()
            try:
                self.assert_original_result(answer)
            finally:
                evaluator._inference_lock.release()
            evaluator._model.encode.side_effect = RuntimeError("unavailable")
            with self.assertLogs(evaluator.logger, level="WARNING"):
                self.assert_original_result(answer)
            self.assertFalse(evaluator._inference_lock.locked())


class LocalSemanticValidationTests(AnswerValidationTests):
    @classmethod
    def setUpClass(cls):
        from models.onnx_encoder import MiniLMEncoder

        cls.encoder = MiniLMEncoder()

    def test_real_semantic_invalid_answers(self):
        with patch.dict(os.environ, {"INTERVIEW_SCORING": "onnx"}):
            evaluator._model = self.encoder
            for answer in (
                *INVALID_ANSWERS, "I ate a banana for breakfast.", "banana car table running",
                "qazwsxedcrfvtgb", "Python banana car table running",
                "network database algorithm compiler banana car",
            ):
                with self.subTest(answer=answer[:60]):
                    self.assertEqual(evaluator.evaluate_answer(answer, IDEAL)["score"], 0)

    def test_small_positive_similarity_does_not_award_marks_to_gibberish(self):
        with patch.dict(os.environ, {"INTERVIEW_SCORING": "onnx"}):
            evaluator._model = self.encoder
            answer = "qazwsxedcrfvtgb"
            with patch.object(evaluator, "_is_non_answer", return_value=False):
                self.assertGreater(evaluator.evaluate_answer(answer, IDEAL)["score"], 0)
            self.assertEqual(evaluator.evaluate_answer(answer, IDEAL)["score"], 0)

    def test_real_semantic_valid_scores_and_feedback_are_identical(self):
        with patch.dict(os.environ, {"INTERVIEW_SCORING": "onnx"}):
            evaluator._model = self.encoder
            for name, answer in VALID_ANSWERS.items():
                with self.subTest(case=name):
                    self.assert_original_result(answer)
            self.assert_original_result(
                "I coached two interns through weekly code reviews and they shipped their first feature.",
                "Explain how you established trust, aligned people, handled resistance and measured the outcome.",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
