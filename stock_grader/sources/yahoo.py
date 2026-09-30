"""Source de données Yahoo Finance via la bibliothèque yfinance."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Callable

import pandas as pd

from ..models import DataPoint, FinancialData, MetricHistory
from .base import DataSourceError

REVENUE_ROWS = ("Total Revenue", "Operating Revenue")
FCF_ROWS = ("Free Cash Flow",)
OCF_ROWS = ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
CAPEX_ROWS = ("Capital Expenditure",)


def _default_ticker_factory(symbol: str) -> Any:
    import yfinance as yf

    return yf.Ticker(symbol)


def _to_date(label: Any) -> date | None:
    try:
        ts = pd.Timestamp(label)
    except (TypeError, ValueError):
        return None
    if pd.isna(ts):
        return None
    return ts.date()


def _clean(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _find_row(frame: pd.DataFrame | None, candidates: tuple[str, ...]) -> pd.Series | None:
    """Première ligne existante et non entièrement vide parmi ``candidates``."""
    if frame is None or frame.empty:
        return None
    for name in candidates:
        if name in frame.index:
            row = frame.loc[name]
            if isinstance(row, pd.DataFrame):  # libellé dupliqué
                row = row.iloc[0]
            if row.notna().any():
                return row
    return None


def _series_points(row: pd.Series | None, note: str | None = None) -> list[DataPoint]:
    if row is None:
        return []
    points = []
    for label, value in row.items():
        period_end = _to_date(label)
        if period_end is not None:
            v = _clean(value)
            points.append(DataPoint(period_end, v, note if v is not None else None))
    return sorted(points, key=lambda p: p.period_end)


def _fcf_points(frame: pd.DataFrame | None) -> list[DataPoint]:
    """Free Cash Flow ; recalculé (flux opérationnel + capex) si la ligne est absente."""
    direct = _series_points(_find_row(frame, FCF_ROWS))
    ocf = {p.period_end: p.value for p in _series_points(_find_row(frame, OCF_ROWS))}
    capex = {p.period_end: p.value for p in _series_points(_find_row(frame, CAPEX_ROWS))}

    by_date = {p.period_end: p for p in direct}
    for period_end in set(ocf) | set(capex) | set(by_date):
        if by_date.get(period_end) is not None and by_date[period_end].has_value:
            continue
        o, c = ocf.get(period_end), capex.get(period_end)
        if o is not None and c is not None:
            by_date[period_end] = DataPoint(
                period_end, o + c, "FCF recalculé : flux de trésorerie opérationnel + capex"
            )
        elif period_end not in by_date:
            by_date[period_end] = DataPoint(period_end, None)
    return sorted(by_date.values(), key=lambda p: p.period_end)


def _latest(points: list[DataPoint]) -> DataPoint | None:
    with_data = [p for p in points if p.has_value]
    return with_data[-1] if with_data else None


def _ttm_from_quarters(points: list[DataPoint]) -> DataPoint | None:
    """Somme des 4 derniers trimestres, uniquement s'ils sont tous renseignés."""
    last4 = points[-4:]
    if len(last4) < 4 or not all(p.has_value for p in last4):
        return None
    return DataPoint(
        last4[-1].period_end,
        sum(p.value for p in last4),  # type: ignore[misc]
        "TTM calculé : somme des 4 derniers trimestres",
    )


class YFinanceDataSource:
    """Récupère CA et FCF (TTM + annuels) depuis Yahoo Finance."""

    def __init__(self, ticker_factory: Callable[[str], Any] = _default_ticker_factory):
        self._ticker_factory = ticker_factory

    def fetch(self, ticker: str) -> FinancialData:
        symbol = ticker.strip().upper()
        try:
            t = self._ticker_factory(symbol)
            income_annual = self._frame(t, "income_stmt")
            cash_annual = self._frame(t, "cashflow")
            income_ttm = self._frame(t, "ttm_income_stmt", optional=True)
            cash_ttm = self._frame(t, "ttm_cashflow", optional=True)
        except Exception as exc:  # réseau, API modifiée, etc.
            raise DataSourceError(f"Impossible de récupérer les données de {symbol} : {exc}") from exc

        revenue_ttm = _latest(_series_points(_find_row(income_ttm, REVENUE_ROWS)))
        fcf_ttm = _latest(_fcf_points(cash_ttm))

        # Repli : reconstituer le TTM à partir des trimestres.
        if revenue_ttm is None:
            quarters = self._frame(t, "quarterly_income_stmt", optional=True)
            revenue_ttm = _ttm_from_quarters(_series_points(_find_row(quarters, REVENUE_ROWS)))
        if fcf_ttm is None:
            quarters = self._frame(t, "quarterly_cashflow", optional=True)
            fcf_ttm = _ttm_from_quarters(_fcf_points(quarters))

        info = self._info(t)
        return FinancialData(
            ticker=symbol,
            revenue=MetricHistory(
                ttm=revenue_ttm,
                annual=tuple(_series_points(_find_row(income_annual, REVENUE_ROWS))),
            ),
            free_cash_flow=MetricHistory(ttm=fcf_ttm, annual=tuple(_fcf_points(cash_annual))),
            currency=info.get("financialCurrency") or info.get("currency"),
            company_name=info.get("longName") or info.get("shortName"),
        )

    @staticmethod
    def _frame(t: Any, attr: str, optional: bool = False) -> pd.DataFrame | None:
        try:
            frame = getattr(t, attr)
        except AttributeError:
            return None
        except Exception:
            if optional:
                return None
            raise
        return frame if isinstance(frame, pd.DataFrame) else None

    @staticmethod
    def _info(t: Any) -> dict:
        # Les métadonnées sont facultatives : un échec ne doit pas bloquer la notation.
        try:
            info = t.info
        except Exception:
            return {}
        return info if isinstance(info, dict) else {}
