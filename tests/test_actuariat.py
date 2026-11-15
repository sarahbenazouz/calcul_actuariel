"""
Tâche E – Tests des cas limites du moteur actuariel (actuariat.py).

Tous les tests sont HORS-LIGNE : aucune requête réseau, les pluies sont
injectées (fichier nice_1998.csv du dépôt ou séries synthétiques).

Lancement (depuis la racine du dépôt) :
    pip install pytest
    pytest tests/ -v
"""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from actuariat import (  # noqa: E402
    backtest, indemnite, prime_empirique, resultat_journalier, seuil, verifier,
)

BASE = {"CA": 1000, "Cf": 300, "pl_bar": 10, "ville": "Nice"}


# ─── Données de test ─────────────────────────────────────────────────────────
def serie(pluie, debut="1990-01-01", fin="1997-12-31"):
    """Historique synthétique : pluie constante (ou fonction de la date)."""
    dates = pd.date_range(debut, fin, freq="D")
    valeurs = pluie(dates) if callable(pluie) else np.full(len(dates), float(pluie))
    return pd.DataFrame({"date": dates, "precip_mm": valeurs})


@pytest.fixture(scope="module")
def nice_1998():
    return pd.read_csv(RACINE / "nice_1998.csv", parse_dates=["date"])


@pytest.fixture(scope="module")
def histo_alea():
    """30 ans de pluie pseudo-aléatoire (60 % de jours secs, queue exponentielle)."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("1968-01-01", "1997-12-31", freq="D")
    pluie = np.where(rng.random(len(dates)) < 0.6, 0.0, rng.exponential(6, len(dates)).round(1))
    return pd.DataFrame({"date": dates, "precip_mm": pluie})


def prime(params, histo, debut=date(1998, 1, 1)):
    return prime_empirique({**params, "date_souscription": debut}, histo, debut=debut)


# ═══ 1. Formules du sujet : résultat journalier ═════════════════════════════
class TestFormulesDuSujet:
    def test_pas_de_pluie_resultat_maximal(self):
        assert resultat_journalier(0.0, BASE) == pytest.approx(700)       # CA - Cf

    def test_pluie_au_pivot_ou_au_dela_resultat_moins_cf(self):
        assert resultat_journalier(10.0, BASE) == pytest.approx(-300)     # pl = pivot
        assert resultat_journalier(250.0, BASE) == pytest.approx(-300)    # pluie extrême

    def test_pluie_intermediaire(self):
        # f = (10 - 5)/10 = 0.5  ->  R = 0.5*1000 - 300 = 200
        assert resultat_journalier(5.0, BASE) == pytest.approx(200)

    def test_seuil_de_perte(self):
        assert seuil(BASE) == pytest.approx(7.0)                          # 10*(1-0.3)

    def test_resultat_nul_exactement_au_seuil(self):
        assert resultat_journalier(seuil(BASE), BASE) == pytest.approx(0, abs=1e-9)

    def test_indemnite_nulle_avant_seuil_et_egale_cf_au_pivot(self):
        assert indemnite(6.9, BASE) == 0
        assert indemnite(7.0, BASE) == pytest.approx(0, abs=1e-9)
        assert indemnite(10.0, BASE) == pytest.approx(300)
        assert indemnite(80.0, BASE) == pytest.approx(300)                # plafonnée à Cf

    def test_garantie_resultat_assure_positif_chaque_jour(self):
        pl = np.linspace(0, 200, 4001)
        assert ((resultat_journalier(pl, BASE) + indemnite(pl, BASE)) >= -1e-9).all()

    def test_vectorisation(self):
        out = indemnite([0, 5, 8.5, 10, 30], BASE)
        assert out.shape == (5,)
        assert out == pytest.approx([0, 0, 150, 300, 300])


# ═══ 2. Cas limite : CA = Cf ════════════════════════════════════════════════
class TestCasCAegalCf:
    def test_ca_egal_cf_est_refuse_avec_message_clair(self):
        with pytest.raises(ValueError, match="CA > Cf"):
            verifier({**BASE, "CA": 300, "Cf": 300})

    def test_ca_inferieur_cf_est_refuse(self):
        with pytest.raises(ValueError, match="CA > Cf"):
            verifier({**BASE, "CA": 200, "Cf": 300})

    def test_ca_juste_au_dessus_de_cf_seuil_quasi_nul(self):
        p = {**BASE, "CA": 300.01, "Cf": 300}
        assert 0 < seuil(p) < 1e-3                       # la moindre pluie déclenche une indemnité
        assert indemnite(0.0, p) == 0
        assert indemnite(0.1, p) > 0
        assert indemnite(10.0, p) == pytest.approx(300)   # au pivot : indemnité maximale = Cf

    def test_ca_juste_au_dessus_de_cf_prime_calculable(self):
        p = {**BASE, "CA": 300.01, "Cf": 300}
        histo = serie(lambda d: np.where(d.day % 2 == 0, 1.0, 0.0))   # 1 jour sur 2 pluvieux (1 mm)
        # 1 mm -> f = 0,9 -> R = 0,9*300,01 - 300 = -29,99 -> indemnité ~ 30 € un jour sur deux
        assert prime(p, histo) == pytest.approx(float(indemnite(1.0, p)) * 365 / 2, rel=0.03)


# ═══ 3. Cas limite : pivot p̄l très petit ═══════════════════════════════════
class TestPivotTresPetit:
    @pytest.mark.parametrize("pivot", [1e-9, 1e-6, 0.01, 0.1])
    def test_calcul_stable_sans_nan_ni_inf(self, pivot):
        p = {**BASE, "pl_bar": pivot}
        pl = np.array([0.0, 0.05, 0.1, 5.0, 100.0])
        for arr in (resultat_journalier(pl, p), indemnite(pl, p)):
            assert np.isfinite(arr).all()
        assert np.isfinite(seuil(p))

    def test_pivot_infime_toute_pluie_mesurable_coute_cf(self):
        p = {**BASE, "pl_bar": 1e-9}
        assert indemnite(0.0, p) == 0                     # jour sec : jamais d'indemnité
        assert indemnite(0.1, p) == pytest.approx(300)    # 0,1 mm -> perte maximale

    def test_pivot_infime_prime_egale_cf_x_nb_jours_pluvieux(self):
        p = {**BASE, "pl_bar": 1e-9}
        histo = serie(lambda d: np.where(d.day <= 10, 2.0, 0.0))      # ~1/3 des jours pluvieux
        attendu = 300 * (histo["precip_mm"] > 0).mean() * 365
        assert prime(p, histo) == pytest.approx(attendu, rel=0.03)

    def test_prime_plafonnee_par_365_cf(self):
        p = {**BASE, "pl_bar": 1e-9}
        assert prime(p, serie(50.0)) == pytest.approx(365 * 300)

    def test_pivot_nul_ou_negatif_refuse(self):
        for pivot in (0, -5):
            with pytest.raises(ValueError, match="strictement positif"):
                verifier({**BASE, "pl_bar": pivot})

    def test_la_prime_decroit_quand_le_pivot_augmente(self, histo_alea):
        primes = [prime({**BASE, "pl_bar": pv}, histo_alea) for pv in (0.5, 2, 5, 10, 20, 50)]
        assert all(a >= b - 1e-6 for a, b in zip(primes, primes[1:]))


# ═══ 4. Valeurs d'entrée invalides ══════════════════════════════════════════
class TestEntreesInvalides:
    @pytest.mark.parametrize("cle,val", [("CA", -100), ("CA", 0), ("Cf", -1)])
    def test_valeurs_negatives_ou_nulles_refusees(self, cle, val):
        with pytest.raises(ValueError):
            verifier({**BASE, cle: val})

    @pytest.mark.parametrize("cle", ["CA", "Cf", "pl_bar"])
    @pytest.mark.parametrize("val", [float("nan"), float("inf"), float("-inf")])
    def test_nan_et_infini_refuses(self, cle, val):
        # Sans contrôle, NaN donnait une prime NaN affichée "nan €" dans le devis.
        with pytest.raises(ValueError):
            verifier({**BASE, cle: val})

    def test_parametre_manquant(self):
        with pytest.raises(KeyError):
            verifier({"CA": 1000, "Cf": 300})

    def test_parametre_texte_non_numerique(self):
        with pytest.raises(ValueError):
            verifier({**BASE, "CA": "abc"})

    def test_cf_zero_prime_nulle(self, histo_alea):
        assert prime({**BASE, "Cf": 0}, histo_alea) == 0       # rien à assurer


# ═══ 5. Historique pathologique ═════════════════════════════════════════════
class TestHistorique:
    def test_historique_vide(self):
        with pytest.raises(ValueError, match="Historique vide"):
            prime(BASE, pd.DataFrame({"date": pd.to_datetime([]), "precip_mm": []}))

    def test_historique_entierement_nan(self):
        histo = serie(np.nan)
        with pytest.raises(ValueError, match="Historique vide"):
            prime(BASE, histo)

    def test_historique_toujours_sec_prime_nulle(self):
        assert prime(BASE, serie(0.0)) == 0

    def test_historique_toujours_dilluvien_prime_maximale(self):
        assert prime(BASE, serie(120.0)) == pytest.approx(365 * 300)

    def test_nan_ignores_dans_l_historique(self, histo_alea):
        h = histo_alea.copy()
        h.loc[h.sample(frac=0.05, random_state=1).index, "precip_mm"] = np.nan
        p_ref, p_nan = prime(BASE, histo_alea), prime(BASE, h)
        assert np.isfinite(p_nan)
        assert p_nan == pytest.approx(p_ref, rel=0.10)         # 5 % de trous : écart limité

    def test_historique_court_un_seul_mois(self):
        histo = serie(5.0, "1997-12-01", "1997-12-31")
        assert np.isfinite(prime(BASE, histo))                 # pas de plantage (jours sans donnée -> 0)

    def test_annees_bissextiles_et_29_fevrier(self, histo_alea):
        # 1996 est bissextile : la souscription le 29/02 couvre quand même 365 jours
        p = prime(BASE, histo_alea, debut=date(1996, 2, 29))
        assert np.isfinite(p) and 0 <= p <= 365 * 300

    def test_souscription_un_31_decembre(self, histo_alea):
        p = prime(BASE, histo_alea, debut=date(1997, 12, 31))
        assert np.isfinite(p) and 0 <= p <= 365 * 300

    def test_prime_toujours_entre_0_et_365_cf(self, histo_alea):
        for pv in (0.1, 1, 10, 100):
            for ca in (301, 1000, 1e6):
                p = prime({**BASE, "pl_bar": pv, "CA": ca}, histo_alea)
                assert 0 <= p <= 365 * 300 + 1e-6

    def test_prime_decroit_avec_ca_et_croit_avec_cf(self, histo_alea):
        assert prime({**BASE, "CA": 2000}, histo_alea) <= prime({**BASE, "CA": 1000}, histo_alea)
        assert prime({**BASE, "Cf": 500}, histo_alea) >= prime({**BASE, "Cf": 300}, histo_alea)


# ═══ 6. Rétrospective (backtest) ════════════════════════════════════════════
class TestBacktest:
    def _histo_avant(self, histo_alea):
        return histo_alea[histo_alea["date"] < "1998-01-01"]

    def test_nice_1998_resultats_attendus(self, nice_1998, histo_alea):
        """Reproduit le graphique retro_nice_1998.png du dépôt (R_nass = 214 510 €)."""
        res = backtest(BASE, 1998, pluie_annee=nice_1998, historique=histo_alea)
        assert res["R_nass"] == pytest.approx(214_510)
        assert res["R_ass"] == pytest.approx(220_490)
        assert res["pertes_evitees"] == pytest.approx(5_980)
        assert res["jours_a_perte"] == 23
        assert res["R_net"] == pytest.approx(res["R_ass"] - res["P"])
        assert res["seuil"] == pytest.approx(7.0)

    def test_identites_comptables(self, nice_1998, histo_alea):
        r = backtest(BASE, 1998, pluie_annee=nice_1998, historique=histo_alea)
        assert r["pertes_evitees"] == pytest.approx(r["R_ass"] - r["R_nass"])
        assert r["gain_assurance"] == pytest.approx(r["pertes_evitees"] - r["P"])
        assert r["favorable"] == (r["pertes_evitees"] > r["P"])
        assert (r["jours"]["R_ass"] >= -1e-9).all()

    def test_pas_de_biais_la_prime_ignore_l_annee_analysee(self, nice_1998, histo_alea):
        """Rajouter dans l'historique des pluies de 1998 ou après ne doit rien changer."""
        futur = nice_1998.copy()
        histo_pollue = pd.concat([histo_alea, futur.assign(precip_mm=500.0)], ignore_index=True)
        r1 = backtest(BASE, 1998, pluie_annee=nice_1998, historique=histo_alea)
        r2 = backtest(BASE, 1998, pluie_annee=nice_1998, historique=histo_pollue)
        assert r1["P"] == pytest.approx(r2["P"])

    def test_donnees_manquantes_comptees_et_remplacees_par_zero(self, nice_1998, histo_alea):
        trous = nice_1998.copy()
        trous.loc[:9, "precip_mm"] = np.nan
        r = backtest(BASE, 1998, pluie_annee=trous, historique=histo_alea)
        assert r["jours_manquants"] == 10
        assert np.isfinite(r["R_nass"])

    def test_annee_non_revolue_refusee(self):
        with pytest.raises(ValueError, match="entièrement passée"):
            backtest(BASE, date.today().year)
        with pytest.raises(ValueError, match="entièrement passée"):
            backtest(BASE, date.today().year + 3)

    def test_annee_avant_debut_era5_refusee(self):
        with pytest.raises(ValueError, match="1940"):
            backtest(BASE, 1940)

    def test_annee_seche_defavorable_annee_pluvieuse_favorable(self, histo_alea):
        sec = pd.DataFrame({"date": pd.date_range("1998-01-01", "1998-12-31"), "precip_mm": 0.0})
        pluie = sec.assign(precip_mm=40.0)
        r_sec = backtest(BASE, 1998, pluie_annee=sec, historique=histo_alea)
        r_pluie = backtest(BASE, 1998, pluie_annee=pluie, historique=histo_alea)
        assert r_sec["favorable"] is False and r_sec["pertes_evitees"] == 0
        assert r_pluie["favorable"] is True
        assert r_pluie["pertes_evitees"] == pytest.approx(365 * 300)
        assert r_pluie["R_nass"] == pytest.approx(-365 * 300)
        assert r_pluie["R_net"] == pytest.approx(-r_pluie["P"])    # assuré : on ne perd que la prime

    def test_ca_egal_cf_refuse_dans_backtest(self, nice_1998, histo_alea):
        with pytest.raises(ValueError, match="CA > Cf"):
            backtest({**BASE, "CA": 300}, 1998, pluie_annee=nice_1998, historique=histo_alea)