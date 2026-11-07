"""
Module A : données météo (pluviométrie journalière).

Source : Open-Meteo, sans clé API.
  - Géocodage  : geocoding-api.open-meteo.com
  - Historique : archive-api.open-meteo.com (réanalyse ERA5, depuis 1940, ~5 jours de retard)
  - Temps réel : api.open-meteo.com (paramètre past_days pour les derniers jours)

Installation : pip install requests pandas

Fonctions pour les autres modules :
  get_rainfall(ville, debut, fin=None) -> DataFrame [date, ville, precip_mm, source]
  pluie_actuelle(ville)                -> dict (pluie à l'instant)
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

ARCHIVE_LAG_JOURS = 7   # l'archive ERA5 a quelques jours de retard
TIMEOUT = 30
CACHE_DIR = Path("cache")


def geocoder(ville: str, pays: str | None = "FR") -> dict:
    """Retourne latitude, longitude et nom de la ville (premier résultat du pays demandé)."""
    reponse = requests.get(
        GEOCODE_URL,
        params={"name": ville, "count": 10, "language": "fr", "format": "json"},
        timeout=TIMEOUT,
    )
    reponse.raise_for_status()
    resultats = reponse.json().get("results") or []
    if not resultats:
        raise ValueError(f"Ville introuvable : {ville!r}")
    if pays:
        for res in resultats:
            if res.get("country_code") == pays:
                return res
    return resultats[0]


def _lire_journalier(url: str, lat: float, lon: float, **params) -> pd.DataFrame:
    """Appelle une API Open-Meteo et retourne la pluie journalière (mm)."""
    reponse = requests.get(
        url,
        params={
            "latitude": lat,
            "longitude": lon,
            "daily": "precipitation_sum",
            "timezone": "auto",
            **params,
        },
        timeout=TIMEOUT,
    )
    reponse.raise_for_status()
    jour = reponse.json()["daily"]
    return pd.DataFrame(
        {"date": pd.to_datetime(jour["time"]), "precip_mm": jour["precipitation_sum"]}
    )


def _historique(ville: str, lat: float, lon: float, debut: date, fin: date) -> pd.DataFrame:
    """Historique via l'archive, avec cache local pour éviter de retélécharger."""
    CACHE_DIR.mkdir(exist_ok=True)
    nom = ville.lower().replace(" ", "_")
    fichier = CACHE_DIR / f"{nom}_{debut}_{fin}.csv"
    if fichier.exists():
        return pd.read_csv(fichier, parse_dates=["date"])
    df = _lire_journalier(
        ARCHIVE_URL, lat, lon, start_date=debut.isoformat(), end_date=fin.isoformat()
    )
    df.to_csv(fichier, index=False)
    return df


def _recent(lat: float, lon: float, debut: date, fin: date) -> pd.DataFrame:
    """Derniers jours (jusqu'à aujourd'hui) via l'API temps réel."""
    jours_passes = max((date.today() - debut).days, 0)
    df = _lire_journalier(
        FORECAST_URL, lat, lon, past_days=min(jours_passes, 92), forecast_days=1
    )
    masque = (df["date"] >= pd.Timestamp(debut)) & (df["date"] <= pd.Timestamp(fin))
    return df[masque].reset_index(drop=True)


def get_rainfall(ville: str, debut, fin=None, pays: str | None = "FR") -> pd.DataFrame:
    """
    Pluie journalière (mm) d'une ville entre deux dates.
    debut, fin : 'AAAA-MM-JJ', date ou datetime. fin = aujourd'hui par défaut
    (jamais au-delà d'aujourd'hui : on ne tarife pas sur des prévisions).
    Colonne 'source' : 'historique' (archive ERA5) ou 'temps_reel'.
    """
    aujourdhui = date.today()
    debut = pd.to_datetime(debut).date()
    fin = pd.to_datetime(fin).date() if fin else aujourdhui
    fin = min(fin, aujourdhui)
    if debut > fin:
        raise ValueError("La date de début est postérieure à la date de fin.")

    lieu = geocoder(ville, pays)
    lat, lon = lieu["latitude"], lieu["longitude"]
    limite = aujourdhui - timedelta(days=ARCHIVE_LAG_JOURS)

    morceaux = []
    if debut <= limite:
        hist = _historique(ville, lat, lon, debut, min(fin, limite))
        hist["source"] = "historique"
        morceaux.append(hist)
    if fin > limite:
        recent = _recent(lat, lon, max(debut, limite + timedelta(days=1)), fin)
        recent["source"] = "temps_reel"
        morceaux.append(recent)

    df = pd.concat(morceaux, ignore_index=True)
    df.insert(1, "ville", lieu["name"])
    return df


def pluie_actuelle(ville: str, pays: str | None = "FR") -> dict:
    """Pluie à l'instant (mm, dernier pas de temps du modèle)."""
    lieu = geocoder(ville, pays)
    reponse = requests.get(
        FORECAST_URL,
        params={
            "latitude": lieu["latitude"],
            "longitude": lieu["longitude"],
            "current": "precipitation",
            "timezone": "auto",
        },
        timeout=TIMEOUT,
    )
    reponse.raise_for_status()
    courant = reponse.json()["current"]
    return {
        "ville": lieu["name"],
        "heure": courant["time"],
        "precip_mm": courant["precipitation"],
    }


if __name__ == "__main__":
    print(pluie_actuelle("Nice"))

    trente_jours = get_rainfall("Nice", date.today() - timedelta(days=30))
    print(trente_jours.tail(10))

    nice_1998 = get_rainfall("Nice", "1998-01-01", "1998-12-31")
    print(
        f"Nice 1998 : {len(nice_1998)} jours, "
        f"{nice_1998['precip_mm'].isna().sum()} manquants, "
        f"cumul {nice_1998['precip_mm'].sum():.0f} mm"
    )
    nice_1998.to_csv("nice_1998.csv", index=False)

import pandas as pd
df = pd.read_csv("nice_1998.csv", parse_dates=["date"])
print((df["precip_mm"] >= 10).sum(), "jours >= 10 mm")
print(df.groupby(df["date"].dt.month)["precip_mm"].sum().round(0))