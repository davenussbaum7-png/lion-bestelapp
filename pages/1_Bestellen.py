"""
Lion Beddenshop — Winkelformulier
Winkels vullen hier hun wekelijkse bestelling in.
"""
import streamlit as st

st.set_page_config(
    page_title="Bestellen — Lion Beddenshop",
    page_icon="🛏️",
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

# ─── Data laden ───────────────────────────────────────────────────────────────
artikelen_db  = laad_artikelen()
opgeslagen    = laad_bestelling(winkelnaam)
dbo_opgeslagen = laad_dbo_bestelling(winkelnaam)

# ─── Header ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.title(f"🛏️ Bestelling — {winkelnaam}")
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Uitloggen", use_container_width=True):
        st.session_state.rol = None
        st.session_state.ingelogd_als = None
        st.switch_page("app.py")

st.markdown("Vul de aantallen in die je wilt bestellen. Klik daarna op **Sla bestelling op**.")
st.markdown("---")

# ─── Zoekbalk ─────────────────────────────────────────────────────────────────
zoekterm = st.text_input("🔍 Zoek op artikelnaam, sectie of EAN", placeholder="bijv. Jersey of 872...")

# ─── Artikelen filteren ───────────────────────────────────────────────────────
if zoekterm.strip():
    z = zoekterm.strip().lower()
    gefilterd = [
        a for a in artikelen_db
        if z in (a.get("artikel") or "").lower()
        or z in (a.get("sectie") or "").lower()
        or z in (a.get("ean") or "").lower()
    ]
else:
    gefilterd = artikelen_db

# ─── Bestellingen formulier ───────────────────────────────────────────────────
# Verzamel nieuwe aantallen in een dict
nieuwe_orders = dict(opgeslagen)  # begin met wat al opgeslagen is

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
                ean     = art["ean"]
                label   = art["artikel"]
                huidig  = opgeslagen.get(ean, 0) or 0

                col_art, col_num = st.columns([4, 1])
                with col_art:
                    st.markdown(f"**{label}**  \n<small style='color:gray'>{ean}</small>",
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
            # Altijd minstens 5 lege rijen tonen, plus bestaande
            n_rijen = max(5, len(bestaande_regels) + 2)
            for i in range(n_rijen):
                bestaand = bestaande_regels[i] if i < len(bestaande_regels) else {}
                c1, c2 = st.columns([4, 1])
                with c1:
                    art_val = st.text_input(
                        f"Artikel",
                        value=bestaand.get("artikel", ""),
                        key=f"dbo_art_{sectie_dbo}_{i}",
                        label_visibility="collapsed",
                        placeholder="Artikelnaam...",
                    )
                with c2:
                    qty_val = st.number_input(
                        f"Aantal",
                        min_value=0,
                        max_value=999,
                        value=bestaand.get("quantity", 0) or 0,
                        key=f"dbo_qty_{sectie_dbo}_{i}",
                        label_visibility="collapsed",
                    )
                if art_val.strip() and qty_val > 0:
                    nieuwe_dbo.append({
                        "sectie": sectie_dbo,
                        "artikel": art_val.strip(),
                        "quantity": qty_val,
                    })

    st.markdown("---")
    opslaan = st.form_submit_button(
        "💾 Sla bestelling op",
        type="primary",
        use_container_width=True,
    )

if opslaan:
    sla_bestelling_op(winkelnaam, nieuwe_orders)
    sla_dbo_op(winkelnaam, nieuwe_dbo)
    ingevuld = sum(1 for v in nieuwe_orders.values() if v > 0) + len(nieuwe_dbo)
    st.success(f"✅ Bestelling opgeslagen! {ingevuld} regels ingevuld.")
    st.balloons()
