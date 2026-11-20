from pathlib import Path

import pytest

from stock_grader.cli import main
from stock_grader.reference import ReferenceFileError, load_references
from stock_grader.sources import DataSourceError

from helpers import data, metric

GOOD = data(metric(140.0, {2021: 100.0, 2024: 130.0}), metric(20.0, {2021: 5.0, 2024: 15.0}), ticker="GOOD")  # A
BAD = data(metric(90.0, {2021: 100.0, 2024: 130.0}), metric(-5.0, {2021: 5.0, 2024: 15.0}), ticker="BAD")  # F


class FakeSource:
    def fetch(self, ticker):
        if ticker == "GOOD":
            return GOOD
        if ticker == "BAD":
            return BAD
        raise DataSourceError(f"Aucune donnée financière reçue pour {ticker}")


def write(tmp_path, text):
    path = tmp_path / "references.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_all_match(tmp_path, capsys):
    path = write(tmp_path, "ticker,note_attendue,commentaire\ngood,a,noté en classe\nBAD,F,\n")
    assert main(["--verifier", path], source=FakeSource()) == 0
    out = capsys.readouterr().out
    assert "✅ GOOD : attendu A, obtenu A" in out and "(noté en classe)" in out
    assert "2 / 2 note(s) identique(s)" in out


def test_difference_and_error_are_reported(tmp_path, capsys):
    path = write(tmp_path, "ticker,note_attendue,commentaire\nGOOD,B,\nZZZZ,C,\n")
    assert main(["--verifier", path], source=FakeSource()) == 1
    out = capsys.readouterr().out
    assert "❌ GOOD : attendu B, obtenu A" in out
    assert "Réponses : Q1 Oui, Q2 Oui, Q3 Oui, Q4 Oui, Q5 Oui" in out
    assert "⚠️ ZZZZ : attendu C, obtenu Aucune donnée" in out
    assert "0 / 2" in out


def test_invalid_grade_in_file(tmp_path):
    path = write(tmp_path, "ticker,note_attendue,commentaire\nAAPL,E,\n")
    with pytest.raises(ReferenceFileError, match="ligne 2"):
        load_references(path)


def test_empty_file_is_explained(tmp_path, capsys):
    assert main(["--verifier", write(tmp_path, "ticker,note_attendue,commentaire\n")], source=FakeSource()) == 2
    assert "Aucune note de référence" in capsys.readouterr().err


def test_no_argument_is_an_error(capsys):
    with pytest.raises(SystemExit):
        main([], source=FakeSource())


def test_repository_reference_file_is_valid():
    # Le fichier rempli par l'enseignante doit rester lisible (tickers + notes valides).
    references = load_references(Path(__file__).parent.parent / "references.csv")
    assert references and all(r.expected in "ABCDF" for r in references)
