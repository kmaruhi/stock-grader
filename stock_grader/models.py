"""Structures de données neutres, indépendantes de la source (yfinance ou autre)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class DataPoint:
    """Une valeur financière pour une période donnée.

    ``value`` vaut None quand la source a une colonne pour cette période mais
    aucune donnée (année « vide »).
    """

    period_end: date
    value: float | None
    note: str | None = None  # ex. valeur recalculée plutôt que lue directement

    @property
    def has_value(self) -> bool:
        return self.value is not None

    @property
    def fiscal_year(self) -> int:
        return self.period_end.year


@dataclass(frozen=True)
class MetricHistory:
    """Historique d'un indicateur : TTM + exercices annuels."""

    ttm: DataPoint | None = None
    annual: tuple[DataPoint, ...] = field(default_factory=tuple)

    def annual_with_data(self) -> list[DataPoint]:
        """Exercices ayant une valeur, du plus ancien au plus récent."""
        return sorted((p for p in self.annual if p.has_value), key=lambda p: p.period_end)

    def oldest_annual(self) -> DataPoint | None:
        points = self.annual_with_data()
        return points[0] if points else None

    def latest_annual(self) -> DataPoint | None:
        points = self.annual_with_data()
        return points[-1] if points else None

    def blank_years_after(self, point: DataPoint) -> list[DataPoint]:
        """Exercices vides plus récents que ``point`` (ignorés lors du choix)."""
        return sorted(
            (p for p in self.annual if not p.has_value and p.period_end > point.period_end),
            key=lambda p: p.period_end,
        )


@dataclass(frozen=True)
class FinancialData:
    ticker: str
    revenue: MetricHistory
    free_cash_flow: MetricHistory
    currency: str | None = None
    company_name: str | None = None
