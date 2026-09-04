"""
Lion Beddenshop — Winkelformulier
Winkels vullen hier hun wekelijkse bestelling in.
"""
import os
import streamlit as st
from PIL import Image
# ─── Page config met logo ─────────────────────────────────────────────────────
_logo_path = None
for _p in ["Lion.nl.jpg", "logo.png", "logo.jpg", "logo.jpeg"]:
    if os.path.exists(_p):
        _logo_path = _p
        break
try:
    _page_icon = Image.open(_logo_path)
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
    sla_bestelling_op, sla_dbo_op, laad_order_status,
)
# ─── Stijl ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.art-label { font-size: 0.92rem; font-weight: 600; margin: 0; line-height: 1.3; }
div[data-testid="stNumberInput"] label { display: none; }
.stExpander div[data-testid="stVerticalBlock"] { gap: 0.2rem; }
[data-testid="stToolbar"] { display: none !important; }
.stDeployButton { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
.status-balk {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.6rem 1rem;
    border-radius: 8px;
    background: #f8f9fa;
    font-size: 0.95rem;
    margin-bottom: 0.5rem;
    flex-wrap: wrap;
}
.status-stap { color: #aaa; }
.status-stap.actief { color: #222; font-weight: 600; }
.status-stap.klaar { color: #2e7d32; font-weight: 600; }
.status-pijl { color: #ccc; }
</style>
""", unsafe_allow_html=True)

# ─── Data laden ───────────────────────────────────────────────────────────────
artikelen_db   = laad_artikelen()
dbo_opgeslagen = laad_dbo_bestelling(winkelnaam)

# ─── Session state initialiseren (eenmalig vanuit DB bij eerste laad) ─────────
if f"_geladen_{winkelnaam}" not in st.session_state:
    opgeslagen = laad_bestelling(winkelnaam)
    for art in artikelen_db:
        ean = art["ean"]
        st.session_state[f"art_{ean}"] = opgeslagen.get(ean, 0) or 0
    dbo_secties_init = ["01 1 PERS.DBO", "02 2 PERS.DBO", "03 3 Pers.DBO", "04 260 BR.DBO"]
    dbo_bestaand_init = {}
    for r in dbo_opgeslagen:
        dbo_bestaand_init.setdefault(r["sectie"], []).append(r)
    for sectie_dbo in dbo_secties_init:
        bestaande = dbo_bestaand_init.get(sectie_dbo, [])
        n_rijen = max(5, len(bestaande) + 2)
        for i in range(n_rijen):
            b = bestaande[i] if i < len(bestaande) else {}
            if f"dbo_art_{sectie_dbo}_{i}" not in st.session_state:
                st.session_state[f"dbo_art_{sectie_dbo}_{i}"] = b.get("artikel", "")
            if f"dbo_qty_{sectie_dbo}_{i}" not in st.session_state:
                st.session_state[f"dbo_qty_{sectie_dbo}_{i}"] = b.get("quantity", 0) or 0
    st.session_state[f"_geladen_{winkelnaam}"] = True

# ─── Header ───────────────────────────────────────────────────────────────────
col_logo, col_title, col_knoppen = st.columns([1, 5, 2])
with col_logo:
    if _logo_path:
        st.image(_logo_path, width=72)
with col_title:
    st.title(f"Bestelling — {winkelnaam}")
with col_knoppen:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Uitloggen", use_container_width=True):
        st.session_state.rol = None
        st.session_state.ingelogd_als = None
        st.switch_page("app.py")
    opslaan = st.button(
        "💾  Sla bestelling op",
        type="primary",
        use_container_width=True,
        key="opslaan_header",
    )

# ─── Statusbalk ───────────────────────────────────────────────────────────────
_status = laad_order_status(winkelnaam)

_STAPPEN = [
    ("geen_bestelling", "besteld"),           # stap 1: bestelling invullen
    ("besteld",),                              # stap 2: ontvangen
    ("piklijst_klaar",),                       # stap 3: piklijst klaar
    ("pakket_onderweg",),                      # stap 4: pakket onderweg
]

def _stap_klasse(stap_statussen: tuple, huidig: str) -> str:
    volgorde = ["geen_bestelling", "besteld", "piklijst_klaar", "pakket_onderweg"]
    huidig_idx = volgorde.index(huidig) if huidig in volgorde else 0
    stap_idx   = max(volgorde.index(s) for s in stap_statussen if s in volgorde)
    if huidig_idx > stap_idx:
        return "klaar"
    if huidig_idx == stap_idx:
        return "actief"
    return ""

_s1 = _stap_klasse(("besteld",), _status)
_s2 = _stap_klasse(("piklijst_klaar",), _status)
_s3 = _stap_klasse(("pakket_onderweg",), _status)

_icoon = {
    "geen_bestelling": "📝",
    "besteld":         "✅",
    "piklijst_klaar":  "📋",
    "pakket_onderweg": "🚚",
}.get(_status, "📝")

_label = {
    "geen_bestelling": "Nog geen bestelling ingediend",
    "besteld":         "Bestelling ontvangen door Wouter",
    "piklijst_klaar":  "Piklijst is klaar — pakket wordt samengesteld",
    "pakket_onderweg": "Pakket is onderweg naar jouw winkel! 🎉",
}.get(_status, "")

st.markdown(f"""
<div class="status-balk">
  <span class="status-stap {_s1}">✅ Bestelling ontvangen</span>
  <span class="status-pijl">›</span>
  <span class="status-stap {_s2}">📋 Piklijst klaar</span>
  <span class="status-pijl">›</span>
  <span class="status-stap {_s3}">🚚 Pakket onderweg</span>
  &nbsp;·&nbsp; <span style="color:#555">{_icoon} {_label}</span>
</div>
""", unsafe_allow_html=True)

st.markdown("Vul de aantallen in die je wilt bestellen. Klik daarna op **Sla bestelling op**.")
st.markdown("---")

# ─── Zoekbalk ─────────────────────────────────────────────────────────────────
zoekterm = st.text_input("🔍 Zoek op artikelnaam, sectie of EAN",
                         placeholder="bijv. Claudia 140 of Jersey...")

# ─── Artikelen filteren ────────────────────────────────────────────────────────
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

# ─── Totaal teller ────────────────────────────────────────────────────────────
totaal_ingevuld = sum(
    st.session_state.get(f"art_{a['ean']}", 0)
    for a in artikelen_db
    if st.session_state.get(f"art_{a['ean']}", 0) > 0
)
st.info(f"**{totaal_ingevuld} stuks** ingevuld in huidige bestelling")

# ─── Artikelen per sectie ─────────────────────────────────────────────────────
secties = {}
for art in gefilterd:
    s = art.get("sectie") or "Overig"
    secties.setdefault(s, []).append(art)

for sectie, artikelen_sectie in secties.items():
    with st.expander(f"📦 {sectie} ({len(artikelen_sectie)} artikelen)", expanded=False):
        for art in artikelen_sectie:
            ean   = art["ean"]
            label = art["artikel"]
            col_art, col_num = st.columns([5, 1])
            with col_art:
                st.markdown(f"<p class='art-label'>{label}</p>",
                            unsafe_allow_html=True)
            with col_num:
                st.number_input(
                    label=f"_{ean}",
                    min_value=0,
                    max_value=999,
                    step=1,
                    label_visibility="collapsed",
                    key=f"art_{ean}",
                )

st.markdown("---")

# ─── DBO-secties ──────────────────────────────────────────────────────────────
dbo_secties = ["01 1 PERS.DBO", "02 2 PERS.DBO", "03 3 Pers.DBO", "04 260 BR.DBO"]
dbo_bestaand = {}
for r in dbo_opgeslagen:
    dbo_bestaand.setdefault(r["sectie"], []).append(r)

st.subheader("DBO — Vrije invoer")
st.caption("Artikelen die niet in de lijst staan. Typ de naam en het aantal.")

for sectie_dbo in dbo_secties:
    with st.expander(f"📝 {sectie_dbo}", expanded=False):
        bestaande_regels = dbo_bestaand.get(sectie_dbo, [])
        n_rijen = max(5, len(bestaande_regels) + 2)
        for i in range(n_rijen):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.text_input(
                    "Artikel",
                    key=f"dbo_art_{sectie_dbo}_{i}",
                    label_visibility="collapsed",
                    placeholder="Artikelnaam...",
                )
            with c2:
                st.number_input(
                    "Aantal",
                    min_value=0,
                    max_value=999,
                    key=f"dbo_qty_{sectie_dbo}_{i}",
                    label_visibility="collapsed",
                )

# ─── Opslaan afhandelen ───────────────────────────────────────────────────────
if opslaan:
    nieuwe_orders = {}
    for art in artikelen_db:
        ean = art["ean"]
        nieuwe_orders[ean] = st.session_state.get(f"art_{ean}", 0)
    nieuwe_dbo = []
    for sectie_dbo in dbo_secties:
        bestaande_regels = dbo_bestaand.get(sectie_dbo, [])
        n_rijen = max(5, len(bestaande_regels) + 2)
        for i in range(n_rijen):
            art_val = st.session_state.get(f"dbo_art_{sectie_dbo}_{i}", "")
            qty_val = st.session_state.get(f"dbo_qty_{sectie_dbo}_{i}", 0)
            if art_val.strip() and qty_val > 0:
                nieuwe_dbo.append({
                    "sectie":   sectie_dbo,
                    "artikel":  art_val.strip(),
                    "quantity": qty_val,
                })
    try:
        sla_bestelling_op(winkelnaam, nieuwe_orders)
        sla_dbo_op(winkelnaam, nieuwe_dbo)
        ingevuld = sum(1 for v in nieuwe_orders.values() if v > 0) + len(nieuwe_dbo)
        st.success(f"✅ Bestelling opgeslagen! {ingevuld} regels ingevuld.")
        st.toast("✅ Opgeslagen!", icon="💾")
    except Exception as fout:
        st.error(f"❌ Fout bij opslaan: {fout}")
        st.info("Ververs de pagina en probeer opnieuw. Als het probleem blijft, neem contact op met Wouter.")
