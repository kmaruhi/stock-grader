"""Tests de l'adaptateur yfinance avec un faux objet Ticker (aucun accès réseau)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from stock_grader.sources import DataSourceError
from stock_grader.sources.yahoo import YFinanceDataSource


def frame(rows: dict, dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=pd.to_datetime(dates)).T


ANNUAL_DATES = ["2024-09-30", "2023-09-30", "2022-09-30", "2021-09-30"]  # ordre yfinance : récent -> ancien


class FakeTicker:
    def __init__(self, **frames):
        self.income_stmt = frames.get("income_stmt", pd.DataFrame())
        self.cashflow = frames.get("cashflow", pd.DataFrame())
        self.ttm_income_stmt = frames.get("ttm_income_stmt", pd.DataFrame())
        self.ttm_cashflow = frames.get("ttm_cashflow", pd.DataFrame())
        self.quarterly_income_stmt = frames.get("quarterly_income_stmt", pd.DataFrame())
        self.quarterly_cashflow = frames.get("quarterly_cashflow", pd.DataFrame())
        self.info = frames.get("info", {"financialCurrency": "USD", "longName": "Fake Inc."})


def source_for(ticker):
    return YFinanceDataSource(ticker_factory=lambda symbol: ticker)


def test_reads_annual_and_ttm():
    t = FakeTicker(
        income_stmt=frame({"Total Revenue": [400, 380, np.nan, 360]}, ANNUAL_DATES),
        cashflow=frame({"Free Cash Flow": [100, 90, 80, np.nan]}, ANNUAL_DATES),
        ttm_income_stmt=frame({"Total Revenue": [410]}, ["2025-06-30"]),
        ttm_cashflow=frame({"Free Cash Flow": [105]}, ["2025-06-30"]),
    )
    d = source_for(t).fetch(" aapl ")
    assert d.ticker == "AAPL" and d.currency == "USD" and d.company_name == "Fake Inc."
    assert d.revenue.ttm.value == 410 and d.revenue.ttm.period_end == date(2025, 6, 30)
    assert [p.fiscal_year for p in d.revenue.annual] == [2021, 2022, 2023, 2024]
    assert d.revenue.annual[1].value is None  # année vide conservée comme vide
    assert d.revenue.oldest_annual().fiscal_year == 2021
    assert d.free_cash_flow.oldest_annual().fiscal_year == 2022
    assert d.free_cash_flow.latest_annual().value == 100


def test_fcf_derived_from_ocf_and_capex_when_missing():
    t = FakeTicker(
        income_stmt=frame({"Total Revenue": [400]}, ["2024-12-31"]),
        cashflow=frame({"Operating Cash Flow": [150], "Capital Expenditure": [-40]}, ["2024-12-31"]),
        ttm_cashflow=frame({"Operating Cash Flow": [160], "Capital Expenditure": [-50]}, ["2025-06-30"]),
    )
    d = source_for(t).fetch("X")
    assert d.free_cash_flow.annual[0].value == 110
    assert d.free_cash_flow.ttm.value == 110
    assert "recalculé" in d.free_cash_flow.ttm.note


def test_ttm_falls_back_to_last_four_quarters():
    q_dates = ["2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30", "2024-06-30"]
    t = FakeTicker(
        income_stmt=frame({"Total Revenue": [400]}, ["2024-12-31"]),
        quarterly_income_stmt=frame({"Total Revenue": [110, 105, 100, 95, 1000]}, q_dates),
        quarterly_cashflow=frame({"Free Cash Flow": [10, np.nan, 10, 10, 10]}, q_dates),
    )
    d = source_for(t).fetch("X")
    assert d.revenue.ttm.value == 410 and d.revenue.ttm.period_end == date(2025, 6, 30)
    assert "4 derniers trimestres" in d.revenue.ttm.note
    assert d.free_cash_flow.ttm is None  # trimestre manquant : pas de TTM inventé


def test_no_data_at_all_raises():
    # Ticker inconnu ou Yahoo injoignable : yfinance renvoie des tableaux vides.
    with pytest.raises(DataSourceError, match="Aucune donnée financière reçue pour ZZZZ"):
        source_for(FakeTicker(info={})).fetch("ZZZZ")


def test_partial_data_is_kept():
    t = FakeTicker(info={}, cashflow=frame({"Free Cash Flow": [10]}, ["2024-12-31"]))
    d = source_for(t).fetch("X")
    assert d.revenue.annual == () and d.free_cash_flow.latest_annual().value == 10
    assert d.currency is None


def test_network_error_becomes_data_source_error():
    class Broken:
        @property
        def income_stmt(self):
            raise ConnectionError("réseau indisponible")

    with pytest.raises(DataSourceError, match="ZZZZ"):
        source_for(Broken()).fetch("ZZZZ")


def test_info_failure_is_not_fatal():
    class NoInfo(FakeTicker):
        @property
        def info(self):
            raise ConnectionError

        @info.setter
        def info(self, _):
            pass

    t = NoInfo(income_stmt=frame({"Total Revenue": [400]}, ["2024-12-31"]))
    assert source_for(t).fetch("X").currency is None
