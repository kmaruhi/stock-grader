import json
from datetime import date

from stock_grader.cli import main
from stock_grader.report import format_amount
from stock_grader.sources import DataSourceError

from helpers import data, metric


class FakeSource:
    def __init__(self, by_ticker):
        self.by_ticker = by_ticker

    def fetch(self, ticker):
        if ticker not in self.by_ticker:
            raise DataSourceError(f"Impossible de récupérer les données de {ticker}")
        return self.by_ticker[ticker]


SAMPLE = data(
    metric(391.035e9, {2021: 365.817e9, 2024: 391.035e9}, ttm_end=date(2024, 9, 28)),
    metric(None, {2021: 92.953e9, 2024: 108.807e9}),
    ticker="AAPL",
)


def test_text_output_in_french(capsys):
    assert main(["AAPL"], source=FakeSource({"AAPL": SAMPLE})) == 0
    out = capsys.readouterr().out
    assert "Q1. Chiffre d'affaires TTM > plus ancien CA annuel disponible : Oui" in out
    assert "391,04 Md USD (TTM, 12 mois au 28/09/2024)" in out
    assert "365,82 Md USD (exercice 2021, clos le 31/12/2021)" in out
    assert "TTM égal au dernier exercice annuel" in out
    assert "Note : F — INCOMPLÈTE" in out
    assert "non comptée(s) comme Non" in out


def test_json_output(capsys):
    main(["AAPL", "--json"], source=FakeSource({"AAPL": SAMPLE}))
    [result] = json.loads(capsys.readouterr().out)
    assert result["note"] == "F" and result["incomplete"] is True
    q1 = result["questions"][0]
    assert q1["reponse"] == "Oui" and q1["droite"]["exercice"] == 2021


def test_error_exit_code(capsys):
    assert main(["NOPE"], source=FakeSource({})) == 1
    assert "Erreur" in capsys.readouterr().err


def test_format_amount():
    assert format_amount(-1_234_567_890, "EUR") == "-1,23 Md EUR"
    assert format_amount(5_500_000) == "5,50 M"
    assert format_amount(0) == "0"
