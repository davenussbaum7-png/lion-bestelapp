"""
Lion Beddenshop — Bestelapp
Startpagina / login voor winkels en Wouter (beheer).
"""
import streamlit as st

st.set_page_config(
    page_title="Lion Beddenshop — Bestellen",
    page_icon="🛏️",
    layout="centered",
)

# ─── Sessie initialiseren ─────────────────────────────────────────────────────
if "ingelogd_als" not in st.session_state:
    st.session_state.ingelogd_als = None   # winkelnaam of "WOUTER"
if "rol" not in st.session_state:
    st.session_state.rol = None            # "winkel" of "beheer"

# ─── Al ingelogd? Doorsturen ──────────────────────────────────────────────────
if st.session_state.rol == "winkel":
    st.switch_page("pages/1_Bestellen.py")
elif st.session_state.rol == "beheer":
    st.switch_page("pages/2_Beheer.py")

# ─── Login-scherm ─────────────────────────────────────────────────────────────
st.image("https://via.placeholder.com/200x60?text=Lion+Beddenshop", width=200)
st.title("Bestelapplicatie")
st.markdown("---")

tab_winkel, tab_beheer = st.tabs(["🏪 Winkel", "🔧 Beheer (Wouter)"])

# ── Winkel-tab ────────────────────────────────────────────────────────────────
with tab_winkel:
    from utils.database import laad_winkels, controleer_pin

    st.subheader("Inloggen als winkel")
    winkels = laad_winkels()
    winkel_namen = [w["name"] for w in winkels]

    keuze = st.selectbox("Kies je winkel", ["— selecteer —"] + winkel_namen)
    pin   = st.text_input("PIN-code", type="password", max_chars=6)

    if st.button("Inloggen", type="primary", use_container_width=True):
        if keuze == "— selecteer —":
            st.error("Selecteer eerst je winkel.")
        elif not pin:
            st.error("Vul je PIN-code in.")
        elif controleer_pin(keuze, pin):
            st.session_state.ingelogd_als = keuze
            st.session_state.rol = "winkel"
            st.rerun()
        else:
            st.error("Verkeerde PIN-code. Probeer het opnieuw.")

# ── Beheer-tab ────────────────────────────────────────────────────────────────
with tab_beheer:
    st.subheader("Inloggen als Wouter")
    wachtwoord = st.text_input("Wachtwoord", type="password", key="beheer_pw")

    if st.button("Inloggen als beheerder", use_container_width=True):
        if wachtwoord == st.secrets.get("wouter_wachtwoord", ""):
            st.session_state.ingelogd_als = "WOUTER"
            st.session_state.rol = "beheer"
            st.rerun()
        else:
            st.error("Verkeerd wachtwoord.")
