"""
Tâche E – Devis imprimable en PDF.

    from devis_pdf import make_quote_pdf
    pdf_bytes = make_quote_pdf(params, prime, n_annees=30)

`params` est le dictionnaire de l'application : CA, Cf, pl_bar, ville, pays,
date_souscription (+ client, optionnel). Dépendance : pip install reportlab
"""
from __future__ import annotations

import hashlib
import io
import math
from datetime import date, timedelta
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from actuariat import seuil, verifier, indemnite

MARQUE = "AssurMétéo"
VALIDITE_JOURS = 30
BLEU, BLEU_CLAIR, GRIS = colors.HexColor("#1F3A5F"), colors.HexColor("#EAF2FA"), colors.HexColor("#6B7785")
VERT = colors.HexColor("#1E8449")


# ─── Formatage à la française ────────────────────────────────────────────────
def eur(x: float, decimales: int = 0) -> str:
    s = f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return f"{s} €"


def nombre(x: float, decimales: int = 1) -> str:
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


def numero_devis(params: dict, prime: float, aujourdhui: date) -> str:
    """Numéro stable : même dossier + même jour -> même numéro."""
    cle = f"{params['ville']}|{params['CA']}|{params['Cf']}|{params['pl_bar']}|{prime:.2f}|{aujourdhui}"
    return f"DEV-{aujourdhui:%Y%m%d}-{hashlib.sha1(cle.encode()).hexdigest()[:5].upper()}"


# ─── Styles ──────────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle("titre", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=20, textColor=BLEU, alignment=0, spaceAfter=0, leading=24),
        "sous": ParagraphStyle("sous", parent=base["Normal"], fontSize=10, textColor=GRIS),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12, textColor=BLEU, spaceBefore=6, spaceAfter=2),
        "txt": ParagraphStyle("txt", parent=base["Normal"], fontSize=9.5, leading=13),
        "petit": ParagraphStyle("petit", parent=base["Normal"], fontSize=8, leading=10.5, textColor=GRIS),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=9.5, leading=12),
        "prime_lbl": ParagraphStyle("pl", parent=base["Normal"], fontSize=10, textColor=colors.white,
                                    alignment=TA_CENTER),
        "prime_val": ParagraphStyle("pv", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=22,
                                    textColor=colors.white, alignment=TA_CENTER, leading=26),
    }


def _tableau(lignes, largeurs, S):
    t = Table([[Paragraph(a, S["cell"]), Paragraph(f"<b>{b}</b>", S["cell"])] for a, b in lignes],
              colWidths=largeurs)
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BLEU_CLAIR]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D6E2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _pied_de_page(numero):
    def dessiner(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(18 * mm, 10 * mm, f"{MARQUE} – Devis {numero} – Projet d'actuariat IMAFA 2026-2027 (document pédagogique)")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return dessiner


# ─── Fonction principale ─────────────────────────────────────────────────────
def make_quote_pdf(params: dict, prime: float, n_annees: int | None = None,
                   aujourdhui: date | None = None, source: str = "Open-Meteo, réanalyse ERA5",
                   methode: str = "moyenne empirique des indemnités, fenêtre saisonnière de ± 15 jours") -> bytes:
    """Génère le devis et renvoie le contenu du PDF (bytes), prêt pour st.download_button."""
    CA, Cf, pl_bar = verifier(params)          # lève ValueError si paramètres invalides
    if not math.isfinite(prime) or prime < 0:
        raise ValueError("La prime doit être un nombre positif ou nul.")
    aujourdhui = aujourdhui or date.today()
    debut = params.get("date_souscription") or aujourdhui
    fin = debut + timedelta(days=364)
    s = seuil(params)
    numero = numero_devis(params, prime, aujourdhui)
    S = _styles()
    ville = escape(str(params["ville"]))
    pays = escape(str(params.get("pays") or ""))
    lieu = f"{ville} ({pays})" if pays else ville
    client = escape(str(params.get("client") or "Non renseigné"))
    story = []

    # En-tête
    entete = Table([[Paragraph("Devis d'assurance<br/>météorologique", S["titre"]),
                     Paragraph(f"<b>{MARQUE}</b><br/>Devis n° <b>{numero}</b><br/>"
                               f"Émis le {aujourdhui:%d/%m/%Y}<br/>Valable {VALIDITE_JOURS} jours "
                               f"(jusqu'au {aujourdhui + timedelta(days=VALIDITE_JOURS):%d/%m/%Y})", S["sous"])]],
                   colWidths=[100 * mm, 74 * mm])
    entete.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story += [entete, Spacer(1, 3 * mm), HRFlowable(width="100%", thickness=1.5, color=BLEU)]

    # 1. Données client
    story.append(Paragraph("1. Données du client", S["h2"]))
    story.append(_tableau([
        ("Client", client),
        ("Ville du commerce", lieu),
        ("Chiffre d'affaires journalier maximum (CA)", eur(CA)),
        ("Coûts fixes journaliers (Cf)", eur(Cf)),
        ("Niveau de pluie journalier pivot (pl)", f"{nombre(pl_bar)} mm"),
        ("Date de souscription", f"{debut:%d/%m/%Y}"),
    ], [100 * mm, 74 * mm], S))

    # 2. Garantie
    story.append(Paragraph("2. Garantie assurée", S["h2"]))
    story.append(Paragraph(
        f"Pendant <b>365 jours consécutifs</b>, du <b>{debut:%d/%m/%Y}</b> au <b>{fin:%d/%m/%Y}</b>, "
        f"{MARQUE} garantit que le <b>résultat journalier du client reste positif ou nul</b>. "
        f"Chaque jour où la pluie dépasse le seuil de <b>{nombre(s, 2)} mm</b>, "
        f"une indemnité ramène le résultat du jour à 0 €.", S["txt"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_tableau([
        ("Seuil de déclenchement (pluie au-delà de laquelle la journée est à perte)", f"{nombre(s, 2)} mm / jour"),
        ("Indemnité maximale par jour (atteinte dès que la pluie atteint le pivot)", eur(Cf)),
        ("Indemnité maximale sur la période", eur(365 * Cf)),
    ], [118 * mm, 56 * mm], S))

    # Exemples d'indemnisation
    pluies = [0.0, round(s, 1), round((s + pl_bar) / 2, 1), pl_bar, pl_bar * 2]
    pluies = sorted(set(p for p in pluies if p >= 0))
    lignes = [["Pluie du jour", "Résultat sans assurance", "Indemnité versée", "Résultat avec assurance"]]
    for p in pluies:
        r = float(CA * max(0.0, min(1.0, (pl_bar - p) / pl_bar)) - Cf)
        i = float(indemnite(p, params))
        r, i = round(r, 2) + 0.0, round(i, 2) + 0.0      # évite l'affichage « -0 € »
        lignes.append([f"{nombre(p)} mm", eur(r), eur(i), eur(r + i + 0.0)])
    ex = Table(lignes, colWidths=[34 * mm, 46 * mm, 46 * mm, 48 * mm])
    ex.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLEU), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D6E2")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BLEU_CLAIR]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [Spacer(1, 3 * mm), Paragraph("<b>Exemples de fonctionnement de la garantie</b>", S["txt"]),
              Spacer(1, 1 * mm), ex]

    # 3. Tarif
    if prime > 0:
        bloc_prime = Table([[Paragraph("PRIME ANNUELLE À PAYER À LA SOUSCRIPTION", S["prime_lbl"])],
                            [Paragraph(eur(prime), S["prime_val"])],
                            [Paragraph(f"soit {eur(prime / 365, 2)} par jour de garantie "
                                       f"({prime / (365 * Cf):.1%} de l'indemnité maximale)".replace(".", ","),
                                       S["prime_lbl"])]],
                           colWidths=[174 * mm])
    else:
        bloc_prime = Table([[Paragraph("PRIME ANNUELLE", S["prime_lbl"])],
                            [Paragraph(eur(0), S["prime_val"])],
                            [Paragraph("Aucun risque à garantir pour ces paramètres (coûts fixes nuls).", S["prime_lbl"])]],
                           colWidths=[174 * mm])
    bloc_prime.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), VERT),
                                    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    histo_txt = f"{n_annees} ans d'historique" if n_annees else "l'historique disponible"
    story.append(KeepTogether([
        Paragraph("3. Tarif", S["h2"]), bloc_prime, Spacer(1, 2 * mm),
        Paragraph(f"<b>Méthode de calcul.</b> Prime pure = somme, sur les 365 jours couverts, de l'indemnité "
                  f"journalière attendue, estimée sur {histo_txt} de pluviométrie à {ville} ({escape(source)}) : "
                  f"{escape(methode)}. La prime ne comprend ni chargement de sécurité, ni frais de gestion, ni taxes.",
                  S["txt"])]))

    # 4. Conditions et signature
    story.append(Paragraph("4. Conditions", S["h2"]))
    for ligne in [
        f"Devis non contractuel, valable {VALIDITE_JOURS} jours à compter de sa date d'émission.",
        "La prime est payable en une seule fois à la date de souscription.",
        "L'indemnité est calculée sur le cumul de pluie de la journée (en mm) fourni par la source de données indiquée pour la ville du commerce.",
        "Une prime est une estimation fondée sur le passé : elle ne préjuge pas de la pluviométrie future.",
        "Document produit dans le cadre d'un projet pédagogique ; il ne constitue pas une offre commerciale réelle.",
    ]:
        story.append(Paragraph("•&nbsp;&nbsp;" + ligne, S["petit"]))
    signature = Table([["Fait à ____________________, le ____ / ____ / ________",
                        "Bon pour accord – signature du client :"]],
                      colWidths=[87 * mm, 87 * mm], rowHeights=[14 * mm])
    signature.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("BOX", (1, 0), (1, 0), 0.5, GRIS)]))
    story += [Spacer(1, 3 * mm), KeepTogether([signature])]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=10 * mm,
                      bottomMargin=14 * mm, title=f"Devis {numero}", author=MARQUE,
                      subject="Devis d'assurance météorologique").build(
        story, onFirstPage=_pied_de_page(numero), onLaterPages=_pied_de_page(numero))
    return buf.getvalue()


if __name__ == "__main__":  # démonstration : python devis_pdf.py -> exemple_devis.pdf
    demo = {"CA": 1000, "Cf": 300, "pl_bar": 10, "ville": "Nice", "pays": "FR",
            "date_souscription": date(2026, 12, 1), "client": "Boulangerie Exemple"}
    with open("exemple_devis.pdf", "wb") as f:
        f.write(make_quote_pdf(demo, prime=9224.0, n_annees=30))
    print("exemple_devis.pdf écrit")