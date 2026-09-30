from datetime import date

from stock_grader.models import DataPoint, FinancialData, MetricHistory


def metric(ttm, annual, ttm_end=date(2025, 6, 30)):
    """annual : dict {année: valeur ou None}, exercices clos le 31/12."""
    return MetricHistory(
        ttm=None if ttm is None else DataPoint(ttm_end, ttm),
        annual=tuple(DataPoint(date(y, 12, 31), v) for y, v in sorted(annual.items())),
    )


def data(revenue, fcf, ticker="TEST"):
    return FinancialData(ticker=ticker, revenue=revenue, free_cash_flow=fcf, currency="USD")
