"""Mise en forme des résultats (texte en français et JSON)."""

from __future__ import annotations

from typing import Any

from .grading import GRADE_LABELS, Answer, GradeResult, Operand, QuestionResult

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
    summary = f"{result.yes_count} Oui sur {result.answered_count} question(s) évaluée(s)"
    if result.incomplete:
        summary += (
            f" ; {result.na_count} question(s) N/A, non comptée(s) comme Non. "
            "La note porte uniquement sur les questions évaluées."
        )
    lines.append(summary)
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
