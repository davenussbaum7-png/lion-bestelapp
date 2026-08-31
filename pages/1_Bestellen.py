"""
Lion Beddenshop — Winkelformulier
Winkels vullen hier hun wekelijkse bestelling in.
"""
import streamlit as st
from PIL import Image

# ─── Page config met logo ─────────────────────────────────────────────────────
_logo_path = None
for _p in ["Lion.nl.jpg", "logo.png", "logo.jpg", "logo.jpeg"]:
    import os
    if os.path.exists(_p):
        _logo_path = _p
        break

try:
    _logo_img = Image.open(_logo_path)
    _page_icon = _logo_img
except Exception:
    _page_icon = "🛏️"

st.set_page_config(
    page_title="Bestellen — Lion Beddenshop",
    page_icon=_page_icon,
    layout="wide",
)

# ─── Toegangscontrole ─────────────────────────────────────────────────────────
if st.session_state.get("rol") != "winkel":
    st.warning("Je bent niet ingelogd. Ga terug naar de hoofdpagina.")
    if st.button("← Naar inlogpagina"):
        st.switch_page("app.py")
    st.stop()

winkelnaam = st.session_state.ingelogd_als

from utils.database import (
    laad_artikelen, laad_bestelling, laad_dbo_bestelling,
    sla_bestelling_op, sla_dbo_op,
)

# ─── Stijl ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Compactere artikelrijen */
.art-label { font-size: 0.92rem; font-weight: 600; margin: 0; line-height: 1.3; }
/* Verberg Streamlit's eigen label van number_input */
div[data-testid="stNumberInput"] label { display: none; }
/* Minder ruimte tussen elementen in expanders */
.stExpander div[data-testid="stVerticalBlock"] { gap: 0.2rem; }

/* ── Sticky floating save button ─────────────────────────────────────────── */
div[data-testid="stFormSubmitButton"] {
    position: fixed;
    bottom: 1.5rem;
    right: 1.5rem;
    z-index: 9999;
    width: auto !important;
}
div[data-testid="stFormSubmitButton"] button {
    min-width: 240px !important;
    width: auto !important;
    padding: 0.75rem 2rem !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
    background-color: #CC0000 !important;
    color: #ffffff !important;
    border: none !important;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.45) !important;
    letter-spacing: 0.02em !important;
}
div[data-testid="stFormSubmitButton"] button:hover {
    background-color: #aa0000 !important;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55) !important;
}
/* Extra ruimte onderaan zodat content niet achter de knop verdwijnt */
section.main > div.block-container {
    padding-bottom: 6rem !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Data laden ───────────────────────────────────────────────────────────────
artikelen_db   = laad_artikelen()
opgeslagen     = laad_bestelling(winkelnaam)
dbo_opgeslagen = laad_dbo_bestelling(winkelnaam)

# ─── Header ───────────────────────────────────────────────────────────────────
col_logo, col_title, col_logout = st.columns([1, 6, 2])

with col_logo:
    if _logo_path:
        st.image(_logo_path, width=72)
    else:
        st.markdown("🛏️")

with col_title:
    st.title(f"Bestelling — {winkelnaam}")

with col_logout:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Uitloggen", use_container_width=True):
        st.session_state.rol = None
        st.session_state.ingelogd_als = None
        st.switch_page("app.py")

st.markdown("Vul de aantallen in die je wilt bestellen. Klik daarna op **Sla bestelling op**.")
st.markdown("---")

# ─── Zoekbalk ─────────────────────────────────────────────────────────────────
zoekterm = st.text_input("🔍 Zoek op artikelnaam, sectie of EAN",
                         placeholder="bijv. Claudia 140 of Jersey...")

# ─── Artikelen filteren (meerdere zoekwoorden) ────────────────────────────────
if zoekterm.strip():
    woorden = zoekterm.strip().lower().split()
    gefilterd = [
        a for a in artikelen_db
        if all(
            w in (a.get("artikel") or "").lower()
            or w in (a.get("sectie") or "").lower()
            or w in (a.get("ean") or "").lower()
            for w in woorden
        )
    ]
else:
    gefilterd = artikelen_db

# ─── Bestellingen formulier ───────────────────────────────────────────────────
nieuwe_orders = dict(opgeslagen)

# Groepeer per sectie
secties = {}
for art in gefilterd:
    s = art.get("sectie") or "Overig"
    secties.setdefault(s, []).append(art)

totaal_ingevuld = sum(v for v in nieuwe_orders.values() if v > 0)
st.info(f"**{totaal_ingevuld} stuks** ingevuld in huidige bestelling")

with st.form("bestelformulier"):

    for sectie, artikelen_sectie in secties.items():
        with st.expander(f"📦 {sectie} ({len(artikelen_sectie)} artikelen)", expanded=False):
            for art in artikelen_sectie:
                ean    = art["ean"]
                label  = art["artikel"]
                huidig = opgeslagen.get(ean, 0) or 0

                col_art, col_num = st.columns([5, 1])
                with col_art:
                    st.markdown(f"<p class='art-label'>{label}</p>",
                                unsafe_allow_html=True)
                with col_num:
                    val = st.number_input(
                        label=f"_{ean}",
                        min_value=0,
                        max_value=999,
                        value=huidig,
                        step=1,
                        label_visibility="collapsed",
                        key=f"art_{ean}",
                    )
                    nieuwe_orders[ean] = val

    st.markdown("---")

    # ── DBO-secties (01–04, vrije tekst) ─────────────────────────────────────
    dbo_secties = ["01 1 PERS.DBO", "02 2 PERS.DBO", "03 3 Pers.DBO", "04 260 BR.DBO"]
    dbo_bestaand = {r["sectie"]: [] for r in dbo_opgeslagen}
    for r in dbo_opgeslagen:
        dbo_bestaand[r["sectie"]].append(r)

    st.subheader("DBO — Vrije invoer")
    st.caption("Artikelen die niet in de lijst staan. Typ de naam en het aantal.")

    nieuwe_dbo = []
    for sectie_dbo in dbo_secties:
        with st.expander(f"📝 {sectie_dbo}", expanded=False):
            bestaande_regels = dbo_bestaand.get(sectie_dbo, [])
            n_rijen = max(5, len(bestaande_regels) + 2)
            for i in range(n_rijen):
                bestaand = bestaande_regels[i] if i < len(bestaande_regels) else {}
                c1, c2 = st.columns([4, 1])
                with c1:
                    art_val = st.text_input(
                        "Artikel",
                        value=bestaand.get("artikel", ""),
                        key=f"dbo_art_{sectie_dbo}_{i}",
                        label_visibility="collapsed",
                        placeholder="Artikelnaam...",
                    )
                with c2:
                    qty_val = st.number_input(
                        "Aantal",
                        min_value=0,
                        max_value=999,
                        value=bestaand.get("quantity", 0) or 0,
                        key=f"dbo_qty_{sectie_dbo}_{i}",
                        label_visibility="collapsed",
                    )
                if art_val.strip() and qty_val > 0:
                    nieuwe_dbo.append({
                        "sectie":   sectie_dbo,
                        "artikel":  art_val.strip(),
                        "quantity": qty_val,
                    })

    st.markdown("---")

    # ── Knop onderaan ────────────────────────────────────────────────────────
    opslaan = st.form_submit_button(
        "💾  Sla bestelling op",
        type="primary",
    )

if opslaan:
    sla_bestelling_op(winkelnaam, nieuwe_orders)
    sla_dbo_op(winkelnaam, nieuwe_dbo)
    ingevuld = sum(1 for v in nieuwe_orders.values() if v > 0) + len(nieuwe_dbo)
    st.success(f"✅ Bestelling opgeslagen! {ingevuld} regels ingevuld.")
    st.balloons()
