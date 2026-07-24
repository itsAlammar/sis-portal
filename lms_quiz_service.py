"""Simple auto-graded quizzes for training courses (one quiz per course).

Multiple-choice questions, a pass threshold, one recorded attempt per
trainee (retake allowed only while not yet passed). Feeds the configurable
completion rule in the training track.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional

from exceptions import NotFoundError, ValidationError
from models import LMSAttempt, LMSQuestion, LMSQuiz

OPTIONS = ("a", "b", "c", "d")


class LMSQuizService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- quiz --------------------------------------------------------------
    def get_or_create_quiz(self, lms_course_id: int, title: str = "",
                           pass_percent: int = 60) -> LMSQuiz:
        quiz = self.get_quiz_for_course(lms_course_id)
        if quiz:
            return quiz
        cur = self.conn.execute(
            "INSERT INTO lms_quizzes (lms_course_id, title, pass_percent, created_at) "
            "VALUES (?, ?, ?, ?)",
            (lms_course_id, title.strip() or None, self._clean_pct(pass_percent),
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return self.get_quiz(cur.lastrowid)

    def get_quiz(self, lms_quiz_id: int) -> LMSQuiz:
        row = self.conn.execute(
            "SELECT * FROM lms_quizzes WHERE lms_quiz_id = ?", (lms_quiz_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No quiz with id {lms_quiz_id}.")
        return LMSQuiz.from_row(row)

    def get_quiz_for_course(self, lms_course_id: int) -> Optional[LMSQuiz]:
        row = self.conn.execute(
            "SELECT * FROM lms_quizzes WHERE lms_course_id = ?", (lms_course_id,)
        ).fetchone()
        return LMSQuiz.from_row(row) if row else None

    def set_pass_percent(self, lms_course_id: int, pass_percent: int,
                         title: str = "") -> LMSQuiz:
        quiz = self.get_or_create_quiz(lms_course_id, title=title, pass_percent=pass_percent)
        self.conn.execute(
            "UPDATE lms_quizzes SET pass_percent = ?, title = ? WHERE lms_quiz_id = ?",
            (self._clean_pct(pass_percent), title.strip() or quiz.title, quiz.lms_quiz_id),
        )
        self.conn.commit()
        return self.get_quiz(quiz.lms_quiz_id)

    @staticmethod
    def _clean_pct(pct) -> int:
        pct = int(pct)
        if not 0 <= pct <= 100:
            raise ValidationError("Pass percent must be between 0 and 100.")
        return pct

    # -- questions ---------------------------------------------------------
    def add_question(self, lms_quiz_id: int, prompt: str, option_a: str, option_b: str,
                     correct_option: str, option_c: str = "", option_d: str = "") -> LMSQuestion:
        self.get_quiz(lms_quiz_id)
        if not prompt.strip() or not option_a.strip() or not option_b.strip():
            raise ValidationError("Prompt and the first two options are required.")
        opts = {"a": option_a.strip(), "b": option_b.strip(),
                "c": option_c.strip(), "d": option_d.strip()}
        correct_option = (correct_option or "").strip().lower()
        if correct_option not in OPTIONS or not opts.get(correct_option):
            raise ValidationError("The correct option must point to a filled-in choice.")
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM lms_questions WHERE lms_quiz_id = ?",
            (lms_quiz_id,),
        ).fetchone()
        cur = self.conn.execute(
            """INSERT INTO lms_questions (lms_quiz_id, prompt, option_a, option_b,
                    option_c, option_d, correct_option, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (lms_quiz_id, prompt.strip(), opts["a"], opts["b"],
             opts["c"] or None, opts["d"] or None, correct_option, row["n"]),
        )
        self.conn.commit()
        return self.get_question(cur.lastrowid)

    def get_question(self, lms_question_id: int) -> LMSQuestion:
        row = self.conn.execute(
            "SELECT * FROM lms_questions WHERE lms_question_id = ?", (lms_question_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No question with id {lms_question_id}.")
        return LMSQuestion.from_row(row)

    def list_questions(self, lms_quiz_id: int) -> List[LMSQuestion]:
        rows = self.conn.execute(
            "SELECT * FROM lms_questions WHERE lms_quiz_id = ? ORDER BY sort_order, lms_question_id",
            (lms_quiz_id,),
        ).fetchall()
        return [LMSQuestion.from_row(r) for r in rows]

    def delete_question(self, lms_question_id: int) -> None:
        self.get_question(lms_question_id)
        self.conn.execute("DELETE FROM lms_questions WHERE lms_question_id = ?", (lms_question_id,))
        self.conn.commit()

    # -- attempts ----------------------------------------------------------
    def get_attempt(self, lms_quiz_id: int, trainee_id: int) -> Optional[LMSAttempt]:
        row = self.conn.execute(
            "SELECT * FROM lms_attempts WHERE lms_quiz_id = ? AND trainee_id = ?",
            (lms_quiz_id, trainee_id),
        ).fetchone()
        return LMSAttempt.from_row(row) if row else None

    def submit_attempt(self, lms_quiz_id: int, trainee_id: int, answers: dict) -> LMSAttempt:
        """Auto-grade answers ({question_id: 'a'..'d'}). Retake is blocked once
        the trainee has already passed."""
        quiz = self.get_quiz(lms_quiz_id)
        questions = self.list_questions(lms_quiz_id)
        if not questions:
            raise ValidationError("This quiz has no questions yet.")
        prev = self.get_attempt(lms_quiz_id, trainee_id)
        if prev and prev.passed:
            raise ValidationError("You have already passed this quiz.")
        correct = sum(1 for q in questions
                      if answers.get(q.lms_question_id) == q.correct_option)
        score = round(correct * 100 / len(questions))
        passed = 1 if score >= quiz.pass_percent else 0
        self.conn.execute(
            """INSERT INTO lms_attempts (lms_quiz_id, trainee_id, score_percent, passed, attempted_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(lms_quiz_id, trainee_id)
               DO UPDATE SET score_percent = excluded.score_percent,
                             passed = excluded.passed, attempted_at = excluded.attempted_at""",
            (lms_quiz_id, trainee_id, score, passed,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return self.get_attempt(lms_quiz_id, trainee_id)

    def has_passed(self, lms_course_id: int, trainee_id: int) -> bool:
        """True if the course has no quiz, or the trainee passed it."""
        quiz = self.get_quiz_for_course(lms_course_id)
        if not quiz:
            return True
        attempt = self.get_attempt(quiz.lms_quiz_id, trainee_id)
        return bool(attempt and attempt.passed)
