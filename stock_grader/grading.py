"""Logique de notation — pure, sans accès réseau ni dépendance à la source."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import DataPoint, FinancialData, MetricHistory


class Answer(str, Enum):
    YES = "Oui"
    NO = "Non"
    NA = "N/A"


@dataclass(frozen=True)
class Operand:
    """Un des deux termes d'une comparaison."""

    kind: str  # "ttm", "annual" ou "constant"
    value: float | None
    period: DataPoint | None = None

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class QuestionResult:
    number: int
    label: str
    answer: Answer
    left: Operand
    right: Operand
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class GradeResult:
    ticker: str
    questions: tuple[QuestionResult, ...]
    letter: str | None  # None si aucune question n'a pu être évaluée
    yes_count: int
    na_count: int
    data: FinancialData = field(repr=False, compare=False)

    @property
    def incomplete(self) -> bool:
        return self.na_count > 0

    @property
    def answered_count(self) -> int:
        return len(self.questions) - self.na_count


GRADE_BY_YES = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F", 0: "F"}
GRADE_LABELS = {"D": "sous-performance"}


def letter_for(yes_count: int) -> str:
    return GRADE_BY_YES[yes_count]


def _ttm(metric: MetricHistory) -> Operand:
    point = metric.ttm if metric.ttm is not None and metric.ttm.has_value else None
    return Operand("ttm", point.value if point else None, point)


def _annual(point: DataPoint | None) -> Operand:
    return Operand("annual", point.value if point else None, point)


def _compare(number: int, label: str, left: Operand, right: Operand, notes: list[str]) -> QuestionResult:
    if not (left.available and right.available):
        missing = []
        if not left.available:
            missing.append("valeur TTM indisponible")
        if not right.available:
            missing.append(
                "aucun exercice annuel avec données" if right.kind == "annual" else "valeur de référence indisponible"
            )
        notes = [f"Comparaison impossible : {', '.join(missing)}."] + notes
        return QuestionResult(number, label, Answer.NA, left, right, tuple(notes))
    # Comparaison strictement numérique : l'égalité compte comme Non,
    # et -50 M > -100 M compte comme une amélioration.
    answer = Answer.YES if left.value > right.value else Answer.NO  # type: ignore[operator]
    return QuestionResult(number, label, answer, left, right, tuple(notes))


def _source_notes(*operands: Operand) -> list[str]:
    return [op.period.note for op in operands if op.period is not None and op.period.note]


def _vs_oldest(number: int, label: str, metric: MetricHistory) -> QuestionResult:
    left, right = _ttm(metric), _annual(metric.oldest_annual())
    notes = _source_notes(left, right)
    if right.available and len(metric.annual_with_data()) == 1:
        notes.append("Un seul exercice annuel disponible : il sert à la fois de plus ancien et de plus récent.")
    return _compare(number, label, left, right, notes)


def _vs_latest(number: int, label: str, metric: MetricHistory) -> QuestionResult:
    latest = metric.latest_annual()
    left, right = _ttm(metric), _annual(latest)
    notes = _source_notes(left, right)
    if latest is not None:
        skipped = metric.blank_years_after(latest)
        if skipped:
            years = ", ".join(str(p.fiscal_year) for p in skipped)
            notes.append(f"Exercice(s) {years} sans données ignoré(s) ; comparaison avec {latest.fiscal_year}.")
    if left.available and right.available and left.value == right.value:
        same_period = left.period is not None and left.period.period_end == latest.period_end  # type: ignore[union-attr]
        detail = (
            "les 12 derniers mois se terminent à la même date que l'exercice"
            if same_period
            else "les chiffres sont identiques à ceux de l'exercice"
        )
        notes.append(
            f"TTM égal au dernier exercice annuel ({latest.fiscal_year}) : {detail}, "  # type: ignore[union-attr]
            "ce qui arrive typiquement juste après la publication du rapport annuel. "
            "Égalité = Non, sans que cela signale une baisse ; la question redeviendra "
            "discriminante après le prochain rapport trimestriel."
        )
    return _compare(number, label, left, right, notes)


def _positive(number: int, label: str, metric: MetricHistory) -> QuestionResult:
    left = _ttm(metric)
    return _compare(number, label, left, Operand("constant", 0.0), _source_notes(left))


def grade(data: FinancialData) -> GradeResult:
    rev, fcf = data.revenue, data.free_cash_flow
    questions = (
        _vs_oldest(1, "Chiffre d'affaires TTM > plus ancien CA annuel disponible", rev),
        _vs_latest(2, "Chiffre d'affaires TTM > CA annuel le plus récent", rev),
        _positive(3, "Free Cash Flow TTM > 0", fcf),
        _vs_oldest(4, "FCF TTM > plus ancien FCF annuel disponible", fcf),
        _vs_latest(5, "FCF TTM > FCF annuel le plus récent", fcf),
    )
    yes = sum(q.answer is Answer.YES for q in questions)
    na = sum(q.answer is Answer.NA for q in questions)
    letter = letter_for(yes) if na < len(questions) else None
    return GradeResult(data.ticker, questions, letter, yes, na, data)
