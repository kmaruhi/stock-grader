"""Mise en forme des résultats (texte en français et JSON)."""

from __future__ import annotations

from datetime import date
from typing import Any

from .grading import GRADE_LABELS, Answer, GradeResult, Operand, QuestionResult
from .models import FinancialData, MetricHistory

# Titres courts des questions, pour l'affichage en liste.
SHORT_TITLES = {
    1: "Chiffre d'affaires en hausse (global)",
    2: "Chiffre d'affaires en hausse (récent)",
    3: "Free Cash Flow positif",
    4: "Free Cash Flow en hausse (global)",
    5: "Free Cash Flow en hausse (récent)",
}
_OLDEST_QUESTIONS = {1, 4}
_LATEST_QUESTIONS = {2, 5}

_JOURS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
_MOIS = ("janv.", "févr.", "mars", "avr.", "mai", "juin",
         "juil.", "août", "sept.", "oct.", "nov.", "déc.")

ICONS = {Answer.YES: "✅", Answer.NO: "❌", Answer.NA: "⚪"}


def format_amount(value: float, currency: str | None = None) -> str:
    sign = "-" if value < 0 else ""
    v = abs(value)
    for threshold, suffix in ((1e9, "Md"), (1e6, "M"), (1e3, "k")):
        if v >= threshold:
            text = f"{v / threshold:,.2f}".replace(",", " ").replace(".", ",") + f" {suffix}"
            break
    else:
        text = f"{v:,.0f}".replace(",", " ")
    return f"{sign}{text}" + (f" {currency}" if currency else "")


def describe_period(op: Operand) -> str:
    if op.kind == "constant":
        return "seuil"
    if op.period is None:
        return "TTM" if op.kind == "ttm" else "exercice annuel"
    end = op.period.period_end.strftime("%d/%m/%Y")
    if op.kind == "ttm":
        return f"TTM, 12 mois au {end}"
    return f"exercice {op.period.fiscal_year}, clos le {end}"


def describe_operand(op: Operand, currency: str | None) -> str:
    value = "indisponible" if op.value is None else format_amount(op.value, None if op.kind == "constant" else currency)
    return f"{value} ({describe_period(op)})"


def grade_title(result: GradeResult) -> str:
    if result.letter is None:
        return "Non évaluable (aucune donnée exploitable)"
    title = result.letter
    if result.letter in GRADE_LABELS:
        title += f" ({GRADE_LABELS[result.letter]})"
    if result.incomplete:
        title += " — INCOMPLÈTE"
    return title


def format_date_fr(d: date, weekday: bool = True) -> str:
    text = f"{d.day} {_MOIS[d.month - 1]} {d.year}"
    return f"{_JOURS[d.weekday()]} {text}" if weekday else text


def describe_earnings(dates: tuple[date, ...], today: date) -> tuple[str, int] | None:
    """Texte de la prochaine publication et nombre de jours restants.

    None si aucune date à venir n'est connue (date passée = information périmée).
    """
    upcoming = [d for d in dates if d >= today]
    if not upcoming:
        return None
    if len(dates) >= 2 and dates[0] != dates[-1] and dates[-1] >= today:
        start, end = max(dates[0], today), dates[-1]
        text = f"entre le {format_date_fr(start)} et le {format_date_fr(end)} (date estimée)"
        return text, (dates[0] - today).days if dates[0] >= today else 0
    return format_date_fr(upcoming[0]), (upcoming[0] - today).days


def metric_for(q: QuestionResult, data: FinancialData) -> MetricHistory:
    return data.revenue if q.number <= 2 else data.free_cash_flow


def compared_periods(q: QuestionResult, data: FinancialData) -> str:
    """Ex. « TTM au 30/06/2025 vs exercice 2023 · 2024 sans données »."""
    left = f"TTM au {q.left.period.period_end:%d/%m/%Y}" if q.left.period else "TTM indisponible"
    if q.right.kind == "constant":
        return left.replace("TTM", "FCF TTM", 1)
    if q.right.period is None:
        return f"{left} vs aucun exercice disponible"
    text = f"{left} vs exercice {q.right.period.fiscal_year}"
    metric = metric_for(q, data)
    if q.number in _OLDEST_QUESTIONS:
        skipped = metric.blank_years_before(q.right.period)
    elif q.number in _LATEST_QUESTIONS:
        skipped = metric.blank_years_after(q.right.period)
    else:
        skipped = []
    if skipped:
        years = ", ".join(str(p.fiscal_year) for p in skipped)
        text += f" · {years} sans données"
    return text


def format_question(q: QuestionResult, currency: str | None) -> list[str]:
    lines = [
        f"{ICONS[q.answer]} Q{q.number}. {q.label} : {q.answer.value}",
        f"     {describe_operand(q.left, currency)}  >  {describe_operand(q.right, currency)} ?",
    ]
    lines += [f"     ℹ️  {note}" for note in q.notes]
    return lines


def format_text(result: GradeResult) -> str:
    data = result.data
    header = data.ticker + (f" — {data.company_name}" if data.company_name else "")
    lines = [header, "=" * len(header)]
    for q in result.questions:
        lines += format_question(q, data.currency)
    lines.append("")
    lines.append(f"Note : {grade_title(result)}")
    earnings = describe_earnings(data.next_earnings, date.today())
    summary = f"{result.yes_count} Oui sur {result.answered_count} question(s) évaluée(s)"
    if result.incomplete:
        summary += (
            f" ; {result.na_count} question(s) N/A, non comptée(s) comme Non. "
            "La note porte uniquement sur les questions évaluées."
        )
    lines.append(summary)
    if earnings:
        lines.append(f"Prochains résultats : {earnings[0]} (dans {earnings[1]} j)")
    return "\n".join(lines)


def _operand_dict(op: Operand) -> dict[str, Any]:
    return {
        "type": op.kind,
        "valeur": op.value,
        "fin_periode": op.period.period_end.isoformat() if op.period else None,
        "exercice": op.period.fiscal_year if op.period and op.kind == "annual" else None,
    }


def to_dict(result: GradeResult) -> dict[str, Any]:
    return {
        "ticker": result.ticker,
        "societe": result.data.company_name,
        "devise": result.data.currency,
        "note": result.letter,
        "libelle_note": grade_title(result),
        "incomplete": result.incomplete,
        "nombre_oui": result.yes_count,
        "nombre_na": result.na_count,
        "prochains_resultats": [d.isoformat() for d in result.data.next_earnings],
        "questions": [
            {
                "numero": q.number,
                "question": q.label,
                "reponse": q.answer.value,
                "gauche": _operand_dict(q.left),
                "droite": _operand_dict(q.right),
                "notes": list(q.notes),
            }
            for q in result.questions
        ],
    }
