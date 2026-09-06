"""
Lion Beddenshop — Hoofdpagina / Login
"""
import streamlit as st
from PIL import Image
import os

# ─── Page config ──────────────────────────────────────────────────────────────
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
    page_title="Lion Beddenshop",
    page_icon=_page_icon,
    layout="centered",
)

# ─── Stijl ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stToolbar"] { display: none !important; }
.stDeployButton { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ─── Session state ────────────────────────────────────────────────────────────
if "rol" not in st.session_state:
    st.session_state.rol = None
if "ingelogd_als" not in st.session_state:
    st.session_state.ingelogd_als = None

# ─── Al ingelogd? Doorsturen ──────────────────────────────────────────────────
if st.session_state.rol == "winkel":
    st.switch_page("pages/1_Bestellen.py")
elif st.session_state.rol == "beheerder":
    st.switch_page("pages/2_Beheer.py")

# ─── Logo ─────────────────────────────────────────────────────────────────────
if _logo_path:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(_logo_path, use_container_width=True)
else:
    st.title("🛏️ Lion Beddenshop")

st.markdown("## Inloggen")

# ─── Login-formulier ──────────────────────────────────────────────────────────
from utils.database import laad_winkels, controleer_pin

BEHEER_WACHTWOORD        = st.secrets["BEHEER_WACHTWOORD"]
WINKEL_WACHTWOORD_FALLBACK = st.secrets["WINKEL_WACHTWOORD_FALLBACK"]

winkels     = laad_winkels()
winkelnamen = [w["name"] for w in winkels]
winkel_pins = {w["name"]: w.get("pin", "") for w in winkels}

keuze      = st.selectbox("Selecteer jouw winkel of kies 'Beheerder'",
                          ["— selecteer —", "Beheerder"] + winkelnamen)
wachtwoord = st.text_input("Wachtwoord / PIN", type="password")

if st.button("Inloggen", type="primary", use_container_width=True):
    if keuze == "— selecteer —":
        st.warning("Selecteer eerst een winkel.")

    elif keuze == "Beheerder":
        if wachtwoord == BEHEER_WACHTWOORD:
            st.session_state.rol          = "beheerder"
            st.session_state.ingelogd_als = "Beheerder"
            st.switch_page("pages/2_Beheer.py")
        else:
            st.error("Verkeerd wachtwoord.")

    else:
        # Per-winkel PIN als die is ingesteld, anders gedeeld fallback-wachtwoord
        pin_ingesteld = winkel_pins.get(keuze, "")
        if pin_ingesteld:
            toegang = controleer_pin(keuze, wachtwoord)
        else:
            toegang = (wachtwoord == WINKEL_WACHTWOORD_FALLBACK)

        if toegang:
            st.session_state.rol          = "winkel"
            st.session_state.ingelogd_als = keuze
            st.switch_page("pages/1_Bestellen.py")
        else:
            st.error("Verkeerde PIN of wachtwoord.")
