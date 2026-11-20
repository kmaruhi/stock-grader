"""Comparaison des notes calculées avec des notes de référence attribuées à la main.

Fichier CSV attendu (une ligne par action) :

    ticker,note_attendue,commentaire
    AAPL,B,noté à la main le 20/11/2026
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .grading import GradeResult, grade
from .report import grade_title
from .sources import DataSourceError, FinancialDataSource

VALID_GRADES = {"A", "B", "C", "D", "F"}


@dataclass(frozen=True)
class Reference:
    ticker: str
    expected: str
    comment: str = ""


@dataclass(frozen=True)
class Comparison:
    reference: Reference
    status: str  # "OK", "ÉCART" ou "ERREUR"
    obtained: str  # note obtenue (ex. « B — INCOMPLÈTE ») ou message d'erreur
    result: GradeResult | None = None


class ReferenceFileError(ValueError):
    """Fichier de références illisible ou mal rempli."""


def load_references(path: str | Path) -> list[Reference]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise ReferenceFileError(f"Impossible de lire {path} : {exc}") from exc
    references = []
    for line, row in enumerate(rows, start=2):
        ticker = (row.get("ticker") or "").strip().upper()
        expected = (row.get("note_attendue") or "").strip().upper()
        if not ticker and not expected:
            continue  # ligne vide
        if not ticker or expected not in VALID_GRADES:
            raise ReferenceFileError(
                f"{path}, ligne {line} : il faut un ticker et une note A, B, C, D ou F "
                f"(trouvé : « {row.get('ticker', '')} », « {row.get('note_attendue', '')} »)."
            )
        references.append(Reference(ticker, expected, (row.get("commentaire") or "").strip()))
    return references


def compare(references: list[Reference], source: FinancialDataSource) -> list[Comparison]:
    comparisons = []
    for ref in references:
        try:
            result = grade(source.fetch(ref.ticker))
        except DataSourceError as exc:
            comparisons.append(Comparison(ref, "ERREUR", str(exc)))
            continue
        status = "OK" if result.letter == ref.expected else "ÉCART"
        comparisons.append(Comparison(ref, status, grade_title(result), result))
    return comparisons


def format_comparisons(comparisons: list[Comparison]) -> str:
    lines = ["Vérification des notes de référence", "=" * 35]
    for c in comparisons:
        icon = {"OK": "✅", "ÉCART": "❌", "ERREUR": "⚠️"}[c.status]
        lines.append(f"{icon} {c.reference.ticker} : attendu {c.reference.expected}, obtenu {c.obtained}")
        if c.reference.comment:
            lines.append(f"     ({c.reference.comment})")
        if c.status == "ÉCART" and c.result is not None:
            answers = ", ".join(f"Q{q.number} {q.answer.value}" for q in c.result.questions)
            lines.append(f"     Réponses : {answers}")
    ok = sum(c.status == "OK" for c in comparisons)
    lines.append("")
    lines.append(f"{ok} / {len(comparisons)} note(s) identique(s) à la référence.")
    return "\n".join(lines)
