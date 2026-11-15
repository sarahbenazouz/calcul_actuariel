"""Tâche E – Tests du devis PDF (hors-ligne). Lancement : pytest tests/ -v"""
import io
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devis import eur, make_quote_pdf, numero_devis  # noqa: E402

P = {"CA": 1000, "Cf": 300, "pl_bar": 10, "ville": "Nice", "pays": "FR",
     "date_souscription": date(2026, 12, 1)}


def texte(pdf: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def pages(pdf: bytes) -> int:
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(pdf)).pages)


def test_pdf_valide_une_page():
    pdf = make_quote_pdf(P, 9224.0, n_annees=30, aujourdhui=date(2026, 11, 15))
    assert pdf.startswith(b"%PDF") and pages(pdf) == 1


def test_contenu_obligatoire_du_sujet():
    """Le sujet exige : données client + garantie assurée + tarif."""
    t = texte(make_quote_pdf(P, 9224.0, n_annees=30, aujourdhui=date(2026, 11, 15))).replace(" ", " ")
    for attendu in ["Nice", "1 000 €", "300 €", "10,0 mm", "01/12/2026", "30/11/2027",   # données client + période
                    "7,00 mm", "365 jours", "109 500 €",                                      # garantie
                    "9 224 €", "25,27 €"]:                                                    # tarif
        assert attendu in t, attendu


def test_prime_nulle_cf_zero():
    t = texte(make_quote_pdf({**P, "Cf": 0}, 0.0)).replace(" ", " ")
    assert "0 €" in t and "Aucun risque" in t


def test_prime_tres_elevee_et_decimales():
    assert eur(1234567.891, 2) == "1 234 567,89 €"
    assert pages(make_quote_pdf({**P, "CA": 5e9, "Cf": 3e9}, 987_654_321.0)) == 1


def test_pivot_tres_petit_ne_plante_pas():
    pdf = make_quote_pdf({**P, "pl_bar": 0.1}, 39_900.0)
    assert pdf.startswith(b"%PDF") and pages(pdf) == 1


@pytest.mark.parametrize("ville", ["Saint-Étienne", "L'Haÿ-les-Roses", "A & B <script>", "Ville " * 30])
def test_caracteres_speciaux_et_ville_tres_longue(ville):
    assert pages(make_quote_pdf({**P, "ville": ville}, 5000.0)) >= 1


def test_parametres_invalides_refuses():
    with pytest.raises(ValueError, match="CA > Cf"):
        make_quote_pdf({**P, "CA": 300}, 100.0)
    for prime in (float("nan"), float("inf"), -5.0):
        with pytest.raises(ValueError):
            make_quote_pdf(P, prime)


def test_date_souscription_absente_utilise_aujourdhui():
    p = {k: v for k, v in P.items() if k != "date_souscription"}
    assert "15/11/2026" in texte(make_quote_pdf(p, 100.0, aujourdhui=date(2026, 11, 15)))


def test_numero_devis_stable_et_distinct():
    j = date(2026, 11, 15)
    assert numero_devis(P, 100.0, j) == numero_devis(P, 100.0, j)
    assert numero_devis(P, 100.0, j) != numero_devis(P, 101.0, j)