"""
Partie D – Interface web & intégration
Logiciel d'assurance de risque météorologique
IMAFA 2026-2027

Lancement : streamlit run app.py
"""
import io
from datetime import date, timedelta

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

from meteo_data import get_rainfall, pluie_actuelle
from actuariat import (
    verifier, seuil, resultat_journalier, indemnite,
    prime_empirique, price, backtest, backtest_periode,
    N_ANNEES_HISTO, PREMIERE_ANNEE_ERA5,
)

# ─── Configuration de la page ────────────────────────────────────────────────
st.set_page_config(
    page_title="AssurMétéo",
    page_icon="🌧️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS personnalisé ────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #f0f4f8;
        border-radius: 10px;
        padding: 16px 20px;
        margin: 6px 0;
    }
    .favorable { color: #1e8449; font-weight: bold; }
    .defavorable { color: #c0392b; font-weight: bold; }
    .section-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #2c3e50;
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ─── Couleurs partagées pour les graphiques ──────────────────────────────────
CL = {"nass": "#c0392b", "ass": "#2e86c1", "net": "#1e8449", "prime": "#7f8c8d"}


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR – saisie des paramètres client
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/1163/1163661.png", width=60)
    st.title("Paramètres client")

    ville = st.text_input("Ville", value="Nice", help="Nom de la ville (France par défaut)")
    pays  = st.text_input("Code pays", value="FR", max_chars=2).upper()

    st.markdown("---")
    CA     = st.number_input("CA journalier max (€)", min_value=1, value=1000, step=100)
    Cf     = st.number_input("Coûts fixes journaliers (€)", min_value=0, value=300, step=50)
    pl_bar = st.number_input("Pivot pluviométrique pl̄ (mm)", min_value=0.1, value=10.0, step=0.5)

    st.markdown("---")
    date_souscription = st.date_input(
        "Date de souscription",
        value=date.today(),
        min_value=date(2000, 1, 1),
        max_value=date.today(),
    )

    params = {
        "CA": CA, "Cf": Cf, "pl_bar": pl_bar,
        "ville": ville, "pays": pays,
        "date_souscription": date_souscription,
    }

    # Validation
    try:
        verifier(params)
        s = seuil(params)
        st.success(f"✅ Seuil de perte : **{s:.2f} mm**")
        params_ok = True
    except ValueError as e:
        st.error(f"⚠️ {e}")
        params_ok = False

# ═══════════════════════════════════════════════════════════════════════════
# ONGLETS PRINCIPAUX
# ═══════════════════════════════════════════════════════════════════════════
tab_prix, tab_retro, tab_multi, tab_meteo = st.tabs([
    "💶 Tarification & Devis",
    "📊 Rétrospective (1 an)",
    "📈 Rétrospective multi-années",
    "🌦️ Météo en temps réel",
])


# ───────────────────────────────────────────────────────────────────────────
# ONGLET 1 – TARIFICATION & DEVIS
# ───────────────────────────────────────────────────────────────────────────
with tab_prix:
    st.header("💶 Tarification & Devis")
    if not params_ok:
        st.warning("Corrigez les paramètres dans la barre latérale.")
        st.stop()

    col_btn, _ = st.columns([1, 3])
    calculer = col_btn.button("🔄 Calculer la prime", type="primary", use_container_width=True)

    if calculer or "prime_result" in st.session_state:
        if calculer:
            with st.spinner("Téléchargement de l'historique…"):
                try:
                    debut_h = date(
                        max(date_souscription.year - N_ANNEES_HISTO, PREMIERE_ANNEE_ERA5), 1, 1
                    )
                    histo = get_rainfall(
                        ville, debut_h,
                        date_souscription - timedelta(days=1),
                        pays=pays,
                    )
                    prime = price(params, histo)
                    st.session_state["prime_result"] = {
                        "prime": prime, "histo": histo,
                        "n_annees": histo["date"].dt.year.nunique(),
                    }
                except Exception as e:
                    st.error(f"Erreur : {e}")
                    st.stop()

        pr = st.session_state["prime_result"]
        prime = pr["prime"]

        # ── KPIs ──
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Prime annuelle", f"{prime:,.0f} €")
        c2.metric("Seuil de perte", f"{seuil(params):.2f} mm/j")
        c3.metric("Prime / jour", f"{prime/365:.1f} €")
        c4.metric("Années d'historique", pr["n_annees"])

        st.markdown("---")

        # ── Graphique : indemnité attendue par jour de l'année ──
        st.subheader("Indemnité moyenne attendue par jour de l'année")
        histo = pr["histo"].dropna(subset=["precip_mm"])
        ind_arr = indemnite(histo["precip_mm"].to_numpy(), params)
        doy = histo["date"].dt.day_of_year.clip(upper=365).to_numpy()
        somme = np.bincount(doy - 1, weights=ind_arr, minlength=365)
        compte = np.bincount(doy - 1, minlength=365)
        esperance = somme / np.maximum(compte, 1)
        fig_ind, ax = plt.subplots(figsize=(10, 3))
        ax.fill_between(range(1, 366), esperance, alpha=0.5, color=CL["ass"])
        ax.set_xlabel("Jour de l'année")
        ax.set_ylabel("Indemnité moy. (€)")
        ax.set_title(f"Indemnité journalière attendue – {ville}")
        ax.grid(alpha=0.3)
        st.pyplot(fig_ind)
        plt.close(fig_ind)

        st.markdown("---")

        # ── DEVIS PDF ──
        st.subheader("📄 Devis client")
        devis_txt = f"""
╔══════════════════════════════════════════════════════╗
║          DEVIS D'ASSURANCE MÉTÉOROLOGIQUE            ║
╚══════════════════════════════════════════════════════╝

Client            : {ville} ({pays})
Date de devis     : {date.today():%d/%m/%Y}
Date de début     : {date_souscription:%d/%m/%Y}
Date de fin       : {(date_souscription + timedelta(days=364)):%d/%m/%Y}

── Paramètres renseignés ──────────────────────────────
  CA journalier maximum  : {CA:>10,.0f} €
  Coûts fixes journaliers: {Cf:>10,.0f} €
  Pivot pluviométrique   : {pl_bar:>10.1f} mm

── Garanties ─────────────────────────────────────────
  Seuil de déclenchement : {seuil(params):.2f} mm/jour
  Couverture             : résultat journalier ≥ 0 €
  Période couverte       : 365 jours consécutifs

── Tarif ─────────────────────────────────────────────
  PRIME ANNUELLE         : {prime:>10,.0f} €
  Soit par jour          : {prime/365:>10.2f} €

Méthode : prime pure empirique sur {pr['n_annees']} ans
         d'historique (ERA5 / Open-Meteo), fenêtre
         saisonnière ± 15 jours.

══════════════════════════════════════════════════════
Devis non contractuel – valable 30 jours.
"""
        st.code(devis_txt, language=None)

        buf = io.BytesIO(devis_txt.encode())
        st.download_button(
            "⬇️ Télécharger le devis (.txt)",
            data=buf,
            file_name=f"devis_assurance_{ville.lower()}_{date.today()}.txt",
            mime="text/plain",
        )


# ───────────────────────────────────────────────────────────────────────────
# ONGLET 2 – RÉTROSPECTIVE 1 AN
# ───────────────────────────────────────────────────────────────────────────
with tab_retro:
    st.header("📊 Rétrospective – une année")
    if not params_ok:
        st.warning("Corrigez les paramètres dans la barre latérale.")
        st.stop()

    annee_retro = st.number_input(
        "Année à analyser",
        min_value=PREMIERE_ANNEE_ERA5 + 1,
        max_value=date.today().year - 1,
        value=min(1998, date.today().year - 1),
        step=1,
    )

    if st.button("🔄 Lancer la rétrospective", type="primary"):
        with st.spinner(f"Téléchargement des données {annee_retro}…"):
            try:
                res = backtest(params, int(annee_retro))
                st.session_state["retro_result"] = res
            except Exception as e:
                st.error(f"Erreur : {e}")
                st.stop()

    if "retro_result" in st.session_state:
        res = st.session_state["retro_result"]
        favorable = res["favorable"]

        # ── Verdict ──
        verdict = "✅ S'assurer aurait été **FAVORABLE**" if favorable \
                  else "❌ S'assurer aurait été **DÉFAVORABLE**"
        st.markdown(f"### {verdict} en {res['annee']}")

        # ── KPIs ──
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("R non assuré", f"{res['R_nass']:,.0f} €",
                  help="Résultat annuel a posteriori, sans assurance")
        c2.metric("Prime P (a priori)", f"{res['P']:,.0f} €",
                  help="Prime calculée au 1er jan avec données AVANT l'année")
        c3.metric("R assuré (avant prime)", f"{res['R_ass']:,.0f} €")
        c4.metric("R net (assuré − prime)", f"{res['R_net']:,.0f} €",
                  delta=f"{res['gain_assurance']:+,.0f} €")
        c5.metric("Jours à perte évités", res["jours_a_perte"])

        st.markdown("---")

        # ── Graphique 1 : résultats cumulés ──
        j = res["jours"]
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5),
                                        gridspec_kw={"width_ratios": [2, 1]})
        ax1.plot(j["date"], j["R_nass"].cumsum(), color=CL["nass"], label="Non assuré")
        ax1.plot(j["date"], j["R_ass"].cumsum(), color=CL["ass"], label="Assuré (avant prime)")
        ax1.plot(j["date"], j["R_ass"].cumsum() - res["P"], color=CL["net"],
                 ls="--", label="Assuré, net de prime")
        idx_perte = j[j["indemnite"] > 0].index
        ax1.scatter(j.loc[idx_perte, "date"], j["R_nass"].cumsum()[idx_perte],
                    s=14, color=CL["nass"], zorder=3, label="Jour à perte")
        ax1.set_title(f"Résultat cumulé – {res['ville']} {res['annee']}")
        ax1.set_ylabel("€"); ax1.grid(alpha=0.3); ax1.legend()

        noms = ["R non assuré", "Prime P", "R assuré", "R net"]
        vals = [res["R_nass"], res["P"], res["R_ass"], res["R_net"]]
        cols = [CL["nass"], CL["prime"], CL["ass"], CL["net"]]
        bars = ax2.bar(noms, vals, color=cols)
        ax2.bar_label(bars, labels=[f"{v:,.0f} €" for v in vals], fontsize=8)
        ax2.set_title("Favorable" if favorable else "Défavorable",
                      color=CL["net"] if favorable else CL["nass"])
        ax2.tick_params(axis="x", rotation=20); ax2.grid(axis="y", alpha=0.3)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        st.markdown("---")

        # ── Tableau détail journalier (filtrable) ──
        with st.expander("📋 Détail journalier (jours à perte uniquement)"):
            jours_perte = j[j["indemnite"] > 0].copy()
            jours_perte["date"] = jours_perte["date"].dt.strftime("%d/%m/%Y")
            jours_perte = jours_perte.rename(columns={
                "precip_mm": "Pluie (mm)", "R_nass": "R non ass. (€)",
                "indemnite": "Indemnité (€)", "R_ass": "R assuré (€)",
            })
            st.dataframe(
                jours_perte[["date", "Pluie (mm)", "R non ass. (€)", "Indemnité (€)", "R assuré (€)"]],
                use_container_width=True, hide_index=True,
            )
            st.caption(f"Total : {res['jours_a_perte']} jours à perte – "
                       f"{res['jours_manquants']} données manquantes (remplacées par 0 mm)")


# ───────────────────────────────────────────────────────────────────────────
# ONGLET 3 – RÉTROSPECTIVE MULTI-ANNÉES
# ───────────────────────────────────────────────────────────────────────────
with tab_multi:
    st.header("📈 Rétrospective multi-années")
    if not params_ok:
        st.warning("Corrigez les paramètres dans la barre latérale.")
        st.stop()

    annee_max = date.today().year - 1
    col1, col2 = st.columns(2)
    a_debut = col1.number_input("Année de début", min_value=PREMIERE_ANNEE_ERA5 + N_ANNEES_HISTO + 1,
                                 max_value=annee_max - 1, value=max(1990, annee_max - 20), step=1)
    a_fin   = col2.number_input("Année de fin",   min_value=a_debut + 1,
                                 max_value=annee_max, value=annee_max, step=1)

    st.caption(f"⚠️ Le calcul télécharge les données ERA5 de {a_debut - N_ANNEES_HISTO} à {a_fin}.")

    if st.button("🔄 Lancer la rétrospective multi-années", type="primary"):
        with st.spinner("Téléchargement et calculs en cours (peut prendre quelques secondes)…"):
            try:
                df = backtest_periode(params, int(a_debut), int(a_fin))
                st.session_state["multi_result"] = df
            except Exception as e:
                st.error(f"Erreur : {e}")
                st.stop()

    if "multi_result" in st.session_state:
        df = st.session_state["multi_result"]
        if df.empty:
            st.warning("Aucun résultat calculé.")
            st.stop()

        n_fav = int(df["favorable"].sum())
        pct_fav = n_fav / len(df) * 100

        # ── KPIs ──
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Années analysées", len(df))
        c2.metric("Années favorables", f"{n_fav} / {len(df)}")
        c3.metric("% favorable", f"{pct_fav:.0f} %")
        c4.metric("Gain moyen/an", f"{df['gain_assurance'].mean():+,.0f} €")

        st.markdown("---")

        # ── Graphique 1 : prime vs pertes évitées ──
        fig1, ax = plt.subplots(figsize=(12, 4))
        x = np.arange(len(df))
        ax.bar(x - 0.2, df["P"], width=0.4, color=CL["prime"], label="Prime (a priori)")
        ax.bar(x + 0.2, df["pertes_evitees"], width=0.4, color=CL["ass"], label="Pertes évitées (a posteriori)")
        ax.set_xticks(x); ax.set_xticklabels(df["annee"], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("€"); ax.legend(); ax.grid(axis="y", alpha=0.3)
        ax.set_title(f"Prime vs pertes évitées – {ville} {int(df['annee'].min())}–{int(df['annee'].max())}")
        st.pyplot(fig1); plt.close(fig1)

        # ── Graphique 2 : R_nass vs R_net ──
        fig2, ax2 = plt.subplots(figsize=(12, 4))
        ax2.plot(df["annee"], df["R_nass"], "o-", color=CL["nass"], label="R non assuré")
        ax2.plot(df["annee"], df["R_net"],  "s--", color=CL["net"], label="R net de prime")
        ax2.fill_between(df["annee"], df["R_nass"], df["R_net"],
                         where=df["favorable"], alpha=0.15, color=CL["net"], label="Favorable")
        ax2.fill_between(df["annee"], df["R_nass"], df["R_net"],
                         where=~df["favorable"], alpha=0.15, color=CL["nass"], label="Défavorable")
        ax2.set_ylabel("€"); ax2.legend(); ax2.grid(alpha=0.3)
        ax2.set_title("Résultat annuel non assuré vs assuré net")
        st.pyplot(fig2); plt.close(fig2)

        # ── Tableau récapitulatif ──
        with st.expander("📋 Tableau récapitulatif par année"):
            df_show = df.copy()
            df_show["favorable"] = df_show["favorable"].map({True: "✅ Oui", False: "❌ Non"})
            st.dataframe(
                df_show.rename(columns={
                    "annee": "Année", "P": "Prime (€)", "pertes_evitees": "Pertes évitées (€)",
                    "gain_assurance": "Gain assurance (€)", "R_nass": "R non ass. (€)",
                    "R_net": "R net (€)", "jours_a_perte": "Jours à perte",
                    "favorable": "Favorable",
                }).set_index("Année"),
                use_container_width=True,
            )

        # ── Statistiques ──
        st.markdown("---")
        st.subheader("📐 Statistiques")
        c1, c2, c3 = st.columns(3)
        c1.metric("Ratio indemnités / primes", f"{df['pertes_evitees'].sum() / df['P'].sum():.1%}")
        c2.metric("Écart-type R non assuré", f"{df['R_nass'].std():,.0f} €")
        c3.metric("Écart-type R net assuré", f"{df['R_net'].std():,.0f} €")
        st.caption("L'intérêt de l'assurance est de **réduire la variabilité** du résultat, même si en moyenne elle est neutre (prime pure).")


# ───────────────────────────────────────────────────────────────────────────
# ONGLET 4 – MÉTÉO EN TEMPS RÉEL
# ───────────────────────────────────────────────────────────────────────────
with tab_meteo:
    st.header("🌦️ Météo en temps réel")

    col_v, col_b = st.columns([2, 1])
    ville_rt = col_v.text_input("Ville", value=ville, key="ville_rt")
    rafraichir = col_b.button("🔄 Rafraîchir", use_container_width=True)

    if rafraichir or "meteo_result" not in st.session_state:
        try:
            with st.spinner("Connexion Open-Meteo…"):
                from meteo_data import pluie_actuelle
                courant = pluie_actuelle(ville_rt, pays)
                trente = get_rainfall(ville_rt, date.today() - timedelta(days=30), pays=pays)
                st.session_state["meteo_result"] = {"courant": courant, "trente": trente}
        except Exception as e:
            st.error(f"Erreur météo : {e}")
            st.stop()

    if "meteo_result" in st.session_state:
        m = st.session_state["meteo_result"]
        courant = m["courant"]
        trente = m["trente"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Pluie actuelle", f"{courant['precip_mm']:.1f} mm")
        c2.metric("Heure de mesure", courant["heure"])
        c3.metric("Ville détectée", courant["ville"])

        st.markdown("---")

        # Résultat du jour selon pluie actuelle
        if params_ok:
            pl_j = courant["precip_mm"]
            r_j = float(resultat_journalier(np.array([pl_j]), params)[0])
            ind_j = float(indemnite(np.array([pl_j]), params)[0])
            st.subheader("Impact sur le résultat du jour")
            c1, c2, c3 = st.columns(3)
            c1.metric("Pluie aujourd'hui", f"{pl_j:.1f} mm",
                      delta="Perte" if pl_j > seuil(params) else "Bénéfice")
            c2.metric("Résultat non assuré", f"{r_j:,.0f} €")
            c3.metric("Indemnité versée", f"{ind_j:,.0f} €")

        st.markdown("---")

        # Courbe des 30 derniers jours
        st.subheader("Pluie des 30 derniers jours")
        fig, ax = plt.subplots(figsize=(12, 3))
        ax.bar(trente["date"], trente["precip_mm"], color=CL["ass"], alpha=0.8, label="Pluie (mm)")
        if params_ok:
            ax.axhline(seuil(params), color=CL["nass"], ls="--", lw=1.5,
                       label=f"Seuil de perte ({seuil(params):.1f} mm)")
            ax.axhline(pl_bar, color=CL["prime"], ls=":", lw=1.5,
                       label=f"Pivot pl̄ ({pl_bar} mm)")
        ax.set_ylabel("mm"); ax.legend(); ax.grid(axis="y", alpha=0.3)
        ax.set_title(f"Pluviométrie – {ville_rt} – 30 derniers jours")
        plt.xticks(rotation=45, ha="right", fontsize=7)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
