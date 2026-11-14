"""
Module partagé – calculs actuariels.
Contient toutes les formules du sujet + prime empirique + backtest.
Importé par app.py (partie D).
"""
from __future__ import annotations

from datetime import date
import numpy as np
import pandas as pd

from meteo_data import get_rainfall  # module A

N_ANNEES_HISTO = 30
PREMIERE_ANNEE_ERA5 = 1940


# ─── Vérification & formules de base ────────────────────────────────────────

def verifier(params: dict) -> tuple[float, float, float]:
    CA, Cf, pl_bar = float(params["CA"]), float(params["Cf"]), float(params["pl_bar"])
    if pl_bar <= 0:
        raise ValueError("Le pivot pl_bar doit être strictement positif.")
    if CA <= Cf:
        raise ValueError("Le sujet impose CA > Cf.")
    if Cf < 0:
        raise ValueError("Les coûts fixes doivent être positifs.")
    return CA, Cf, pl_bar


def seuil(params: dict) -> float:
    """Pluie au-delà de laquelle la journée est à perte : s = pl_bar(1 - Cf/CA)."""
    CA, Cf, pl_bar = verifier(params)
    return pl_bar * (1 - Cf / CA)


def resultat_journalier(pl, params: dict) -> np.ndarray:
    CA, Cf, pl_bar = verifier(params)
    pl = np.asarray(pl, dtype=float)
    f = np.clip((pl_bar - pl) / pl_bar, 0.0, 1.0)
    return f * CA - Cf


def indemnite(pl, params: dict) -> np.ndarray:
    return np.maximum(0.0, -resultat_journalier(pl, params))


# ─── Tarification empirique (± 15 j, fenêtre circulaire) ───────────────────

def prime_empirique(params: dict, historique: pd.DataFrame,
                    debut: date | None = None, fenetre: int = 15) -> float:
    histo = historique.dropna(subset=["precip_mm"])
    if histo.empty:
        raise ValueError("Historique vide : impossible de tarifer.")
    debut = pd.Timestamp(debut or params.get("date_souscription") or date.today())
    jours_couverts = pd.date_range(debut, periods=365, freq="D")

    ind = indemnite(histo["precip_mm"].to_numpy(), params)
    doy_histo = histo["date"].dt.day_of_year.clip(upper=365).to_numpy()
    somme = np.bincount(doy_histo - 1, weights=ind, minlength=365)
    compte = np.bincount(doy_histo - 1, minlength=365)
    noyau = np.ones(2 * fenetre + 1)
    somme_f = np.convolve(np.concatenate([somme[-fenetre:], somme, somme[:fenetre]]), noyau, "valid")
    compte_f = np.convolve(np.concatenate([compte[-fenetre:], compte, compte[:fenetre]]), noyau, "valid")
    esperance = somme_f / np.maximum(compte_f, 1)

    doy_couverts = jours_couverts.day_of_year.to_numpy().clip(max=365)
    return float(esperance[doy_couverts - 1].sum())


try:
    from pricing import price  # module B si présent
except ImportError:
    price = prime_empirique


# ─── Backtest (rétrospective d'une année) ───────────────────────────────────

def backtest(params: dict, annee: int, n_annees_histo: int = N_ANNEES_HISTO,
             pluie_annee: pd.DataFrame | None = None,
             historique: pd.DataFrame | None = None,
             price_fn=None) -> dict:
    verifier(params)
    annee = int(annee)
    if annee >= date.today().year:
        raise ValueError("L'année doit être entièrement passée.")
    if annee <= PREMIERE_ANNEE_ERA5:
        raise ValueError(f"Pas d'historique avant {PREMIERE_ANNEE_ERA5}.")
    ville = params["ville"]
    debut_a, fin_a = date(annee, 1, 1), date(annee, 12, 31)

    if historique is None:
        debut_h = date(max(annee - n_annees_histo, PREMIERE_ANNEE_ERA5), 1, 1)
        historique = get_rainfall(ville, debut_h, date(annee - 1, 12, 31))
    historique = historique[historique["date"] < pd.Timestamp(debut_a)]
    params_a = {**params, "date_souscription": debut_a}
    prime = float((price_fn or price)(params_a, historique))

    if pluie_annee is None:
        pluie_annee = get_rainfall(ville, debut_a, fin_a)
    jours = pluie_annee[["date", "precip_mm"]].copy()
    manquants = int(jours["precip_mm"].isna().sum())
    jours["precip_mm"] = jours["precip_mm"].fillna(0.0)
    jours["R_nass"] = resultat_journalier(jours["precip_mm"], params)
    jours["indemnite"] = indemnite(jours["precip_mm"], params)
    jours["R_ass"] = jours["R_nass"] + jours["indemnite"]

    R_nass = float(jours["R_nass"].sum())
    R_ass = float(jours["R_ass"].sum())
    pertes_evitees = R_ass - R_nass
    return {
        "ville": ville, "annee": annee, "params": dict(params),
        "seuil": seuil(params), "P": prime,
        "R_nass": R_nass, "R_ass": R_ass,
        "R_net": R_ass - prime,
        "pertes_evitees": pertes_evitees,
        "gain_assurance": pertes_evitees - prime,
        "favorable": pertes_evitees > prime,
        "jours_a_perte": int((jours["indemnite"] > 0).sum()),
        "jours_manquants": manquants,
        "annees_histo": historique["date"].dt.year.nunique(),
        "jours": jours,
    }


def backtest_periode(params: dict, annee_debut: int, annee_fin: int,
                     n_annees_histo: int = N_ANNEES_HISTO) -> pd.DataFrame:
    """Lance le backtest sur plusieurs années et renvoie un DataFrame résumé."""
    lignes = []
    ville = params["ville"]
    # Télécharger l'historique une seule fois (toute la période + les années avant)
    histo_global = get_rainfall(
        ville,
        date(max(annee_debut - n_annees_histo, PREMIERE_ANNEE_ERA5), 1, 1),
        date(annee_fin, 12, 31)
    )
    for a in range(annee_debut, annee_fin + 1):
        pluie_a = histo_global[histo_global["date"].dt.year == a]
        histo_a = histo_global[histo_global["date"].dt.year < a]
        try:
            r = backtest(params, a, n_annees_histo,
                         pluie_annee=pluie_a, historique=histo_a)
            lignes.append({
                "annee": a, "P": r["P"],
                "pertes_evitees": r["pertes_evitees"],
                "gain_assurance": r["gain_assurance"],
                "R_nass": r["R_nass"], "R_net": r["R_net"],
                "jours_a_perte": r["jours_a_perte"],
                "favorable": r["favorable"],
            })
        except Exception:
            pass
    return pd.DataFrame(lignes)
