"""
Lion Beddenshop — Hoofdpagina / Login
DEBUG VERSION — verwijder na gebruik
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

# ─── DEBUG: Secrets diagnostics ───────────────────────────────────────────────
with st.expander("🔍 DEBUG — Secrets info (verwijder na gebruik)", expanded=True):
    try:
        alle_keys = list(st.secrets.keys())
        st.write("**Beschikbare secret keys:**", alle_keys)
    except Exception as e:
        st.error(f"Kan secrets.keys() niet lezen: {e}")
        alle_keys = []

    # Check specifiek op BEHEER_WACHTWOORD
    if "BEHEER_WACHTWOORD" in alle_keys:
        val = st.secrets["BEHEER_WACHTWOORD"]
        st.success(f"✅ BEHEER_WACHTWOORD gevonden — waarde: '{val}' (len={len(str(val))})")
    else:
        st.error("❌ BEHEER_WACHTWOORD NIET gevonden in secrets!")
        # Zoek naar vergelijkbare namen (typfout / spatie / hoofdletters)
        vergelijkbaar = [k for k in alle_keys if "beheer" in k.lower() or "wacht" in k.lower()]
        if vergelijkbaar:
            st.warning(f"Vergelijkbare keys gevonden: {vergelijkbaar}")
        else:
            st.info("Geen vergelijkbare keys gevonden.")

    # Laat ook zien of er een lokaal secrets.toml is
    import pathlib
    lokaal_toml = pathlib.Path(".streamlit/secrets.toml")
    if lokaal_toml.exists():
        st.error("⚠️ .streamlit/secrets.toml GEVONDEN IN REPO — dit overschrijft de cloud secrets!")
        st.code(lokaal_toml.read_text(), language="toml")
    else:
        st.success("✅ Geen lokaal .streamlit/secrets.toml — cloud secrets worden gebruikt")

# ─── Login-formulier ──────────────────────────────────────────────────────────
from utils.database import laad_winkels, controleer_pin

try:
    BEHEER_WACHTWOORD = st.secrets["BEHEER_WACHTWOORD"]
except KeyError:
    st.error("❌ BEHEER_WACHTWOORD niet gevonden — login niet mogelijk. Zie debug info hierboven.")
    st.stop()

try:
    WINKEL_WACHTWOORD_FALLBACK = st.secrets["WINKEL_WACHTWOORD_FALLBACK"]
except KeyError:
    st.error("❌ WINKEL_WACHTWOORD_FALLBACK niet gevonden — login niet mogelijk. Zie debug info hierboven.")
    st.stop()

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
