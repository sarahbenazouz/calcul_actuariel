# 🌧️ AssurMétéo – Logiciel d'assurance de risque météorologique
**IMAFA 2026-2027 – Projet d'actuariat**

> Logiciel de tarification d'assurance météorologique pour commerçants, avec devis client et analyse rétrospective. Développé en Python + Streamlit.

---

## Description

Un commerçant perd de l'argent les jours de forte pluie (moins de clients). Ce logiciel lui permet de souscrire une assurance qui lui verse une indemnité chaque jour de pluie excessive, garantissant que son résultat journalier reste ≥ 0 €.

Le logiciel permet de :
- **Tarifer** l'assurance en fonction des paramètres du client
- **Générer un devis** imprimable (approche prospective)
- **Analyser rétrospectivement** l'impact de l'assurance sur des années passées (approche rétrospective)

---

## Structure du projet

assurance_meteo/
├── app.py # Partie D – Interface Streamlit (point d’entrée)
├── actuariat.py # Partie D – Calculs actuariels partagés
├── meteo_data.py # Partie A – Données météo Open-Meteo (pluie journalière)
├── pricing.py # Partie B – Tarification (prime annuelle)
├── retrospective.py # Partie C – Analyse rétrospective
├── requirements.txt # Dépendances Python
└── cache/ # Créé automatiquement – cache local des appels API

---

##  Répartition des rôles

| Module | Rôle | Mission |
|---|---|---|
| **A – Données météo** | `meteo_data.py` | Géocodage, API temps réel, historique ERA5, cache local |
| **B – Pricing** | `pricing.py` | Calcul du seuil `s`, de l'indemnité `I_t` et de la prime annuelle |
| **C – Rétrospective** | `retrospective.py` | Analyse R_nass / R_ass / P pour une année passée, graphiques |
| **D – Interface** | `app.py` | Application web Streamlit, assemblage des modules, devis |
| **E – Devis & qualité** | — | Devis PDF, guide utilisateur, tests des cas limites |

---

##  Installation

### Prérequis

- Python 3.10+
- pip

### Installer les dépendances

```bash
pip install streamlit matplotlib numpy pandas requests
```

Ou via le fichier requirements :

```bash
pip install -r requirements.txt
```

### Lancer l'application

```bash
streamlit run app.py
```

L'application s'ouvre automatiquement sur `http://localhost:8501`.  
Accessible sur mobile via l'IP locale : `http://<IP_machine>:8501`.

---

##  Utilisation

### Paramètres à saisir (barre latérale)

| Paramètre | Description | Exemple |
|---|---|---|
| Ville | Localisation du commerce | Nice |
| Code pays | Code ISO 2 lettres | FR |
| CA journalier max | Chiffre d'affaires max par jour (€) | 1 000 € |
| Coûts fixes journaliers | Charges fixes par jour (€) | 300 € |
| Pivot pluviométrique p̄l | Pluie (mm) au-delà de laquelle CA = 0 | 10 mm |
| Date de souscription | Début de la couverture | 01/01/2025 |

### Onglets de l'application

####  Tarification & Devis
- Calcule la prime annuelle à partir de 30 ans d'historique ERA5
- Affiche prime, seuil de perte, prime/jour, nombre d'années d'historique
- Graphique de l'indemnité journalière attendue (saisonnalité)
- Génère un devis téléchargeable

####  Rétrospective – une année
- Choisir une année passée (ex. 1998)
- Prime calculée **a priori** (données strictement antérieures à l'année)
- Résultat simulé **a posteriori** avec les vraies pluies
- Graphique cumulé + tableau des jours à perte

####  Rétrospective multi-années
- Backtest sur une plage d'années (ex. 1990–2024)
- Prime a priori vs pertes évitées a posteriori par année
- Statistiques : % années favorables, ratio indemnités/primes, réduction de variabilité

####  Météo en temps réel
- Pluie à l'instant via Open-Meteo
- Impact sur le résultat du jour selon les paramètres saisis
- Courbe des 30 derniers jours avec seuil et pivot visualisés

---

##  Modèle mathématique

### Résultat journalier sans assurance

$$R_t = f_t \times CA - Cf$$

avec :

$$f_t = \frac{\overline{pl} - pl_t}{\overline{pl}} \quad \text{si } 0 < pl_t < \overline{pl}, \quad f_t = 1 \text{ si } pl_t = 0, \quad f_t = 0 \text{ si } pl_t \geq \overline{pl}$$

### Seuil de perte

$$s = \overline{pl} \times \left(1 - \frac{Cf}{CA}\right)$$

Le client est à perte chaque jour où `pl_t > s`.

### Indemnité versée par l'assurance

$$I_t = \min\left(Cf,\ \frac{CA}{\overline{pl}}\,(pl_t - s)^+\right) = \max(0,\ -R_t)$$

Garantit `R_t + I_t ≥ 0` chaque jour.

### Prime annuelle

Somme sur 365 jours de l'espérance de l'indemnité, estimée sur l'historique avec une fenêtre saisonnière de ±15 jours :

$$P = \sum_{t=1}^{365} \mathbb{E}[I_t]$$

---

##  Source des données météo

| Source | Usage |
|---|---|
| [Open-Meteo Archive API](https://open-meteo.com) | Historique ERA5 depuis 1940, sans clé API |
| Open-Meteo Forecast API | Données temps réel (derniers jours) |
| Open-Meteo Geocoding API | Coordonnées GPS d'une ville |

Les données sont mises en **cache local** dans `cache/` pour éviter de re-télécharger à chaque calcul.

---

##  Intégration entre modules

Les quatre fonctions contractuelles qui permettent à chaque module d'avancer indépendamment :

```python
# Module A
get_rainfall(ville, debut, fin) -> DataFrame  # [date, ville, precip_mm, source]

# Module B
price(params, historique) -> float  # prime annuelle en euros

# Module C
backtest(params, annee) -> dict  # R_nass, R_ass, P, R_net, favorable, ...

# Module D
make_quote(params, prime) -> None  # génère et affiche le devis
```

Le module `actuariat.py` utilise automatiquement `pricing.py` (module B) s'il est présent :

```python
try:
    from pricing import price   # Module B – remplace la prime empirique si présent
except ImportError:
    price = prime_empirique     # Fallback : méthode empirique ±15 jours
```

---

##  Calendrier

| Période | Objectif |
|---|---|
| 6–9 nov | Réunion de lancement, signatures des fonctions, dépôt Git |
| 10–14 nov | Développement de chaque module en parallèle |
| 15–16 nov | Intégration et répétition |
| **16 nov** | **Draft** – démonstration (10 min) |
| 18–30 nov | Temps réel, loi ajustée, rétrospective multi-années |
| 1–8 déc | Devis PDF, tests, comparaison de villes |
| 9–12 déc | Gel des fonctionnalités, guide utilisateur, correction de bugs |
| **15 déc** | **Envoi de la version finale** (logiciel + user guide) |

---

##  requirements.txt

streamlit>=1.30.0
matplotlib>=3.7.0
numpy>=1.24.0
pandas>=2.0.0
requests>=2.28.0

---

## 📝 Exemple numérique (sujet)

> En 1998, un client niçois avec p̄l = 10 mm, CA = 1 000 €/j, Cf = 300 €/j :
> - **R non assuré** (a posteriori) : 90 000 €
> - **Prime P** (calculée a priori au 01/01/1998) : 3 000 €
> - **R assuré** (a posteriori, avant prime) : 95 000 €
> - **R net** (assuré − prime) : **92 000 €**
>
> → S'assurer aurait été **favorable** : la prime (3 000 €) était inférieure aux pertes évitées (5 000 €).

---

## Auteur

Projet IMAFA 2026-2027 – Logiciel d'assurance de risque météorologique  
Encadrant : Marius AKRE
