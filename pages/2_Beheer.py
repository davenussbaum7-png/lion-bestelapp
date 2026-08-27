"""
Lion Beddenshop — Beheerpagina (Wouter)
SAP uploaden, piklijsten genereren, paklijsten genereren, reset.
"""
import io
import zipfile
import streamlit as st

st.set_page_config(
    page_title="Beheer — Lion Beddenshop",
    page_icon="🔧",
    layout="wide",
)

# ─── Toegangscontrole ─────────────────────────────────────────────────────────
if st.session_state.get("rol") != "beheer":
    st.warning("Toegang geweigerd. Log in als beheerder.")
    if st.button("← Naar inlogpagina"):
        st.switch_page("app.py")
    st.stop()

from utils.database import (
    laad_artikelen, laad_alle_bestellingen, laad_alle_dbo_bestellingen,
    laad_alle_sap, sla_sap_op, bestelling_status, reset_alle_bestellingen,
)
from utils.genereer import bouw_artikellijst, schrijf_piklijst, schrijf_paklijst, lees_sap_xlsx

# ─── Header ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.title("🔧 Beheer — Wouter")
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Uitloggen", use_container_width=True):
        st.session_state.rol = None
        st.session_state.ingelogd_als = None
        st.switch_page("app.py")

st.markdown("---")

# ─── Overzicht bestellingen ───────────────────────────────────────────────────
st.subheader("📊 Status bestellingen")
status = bestelling_status()

cols = st.columns(min(len(status), 5))
for i, s in enumerate(status):
    with cols[i % len(cols)]:
        kleur = "🟢" if s["regels"] > 0 else "⚪"
        st.metric(label=f"{kleur} {s['winkel']}", value=f"{s['regels']} regels")

st.markdown("---")

# ─── SAP uploaden ─────────────────────────────────────────────────────────────
st.subheader("📥 SAP-exports uploaden")
st.caption("Upload de SAP-exports per winkel. Het systeem herkent de winkelnaam automatisch.")

sap_bestanden = st.file_uploader(
    "Selecteer SAP-bestanden (.xlsx)",
    type=["xlsx"],
    accept_multiple_files=True,
    key="sap_upload",
)

if sap_bestanden:
    if st.button("Verwerk SAP-bestanden", type="primary"):
        succes, fouten = 0, []
        for bestand in sap_bestanden:
            winkelnaam_sap, sap_regels = lees_sap_xlsx(bestand.read())
            if winkelnaam_sap and sap_regels:
                sla_sap_op(winkelnaam_sap, sap_regels)
                st.success(f"✅ {bestand.name} → {winkelnaam_sap} ({len(sap_regels)} regels)")
                succes += 1
            else:
                fouten.append(bestand.name)
                st.error(f"❌ {bestand.name}: winkelnaam of data niet herkend")
        if succes:
            st.info(f"{succes} SAP-bestand(en) verwerkt.")

st.markdown("---")

# ─── Piklijsten genereren ────────────────────────────────────────────────────
st.subheader("📋 Stap 1 — Piklijsten genereren")
st.caption("Genereert piklijsten voor alle winkels met ingevulde bestellingen.")

if st.button("🖨️ Genereer alle piklijsten (download ZIP)", type="primary", use_container_width=True):
    artikelen_db = laad_artikelen()
    alle_orders  = laad_alle_bestellingen()
    alle_dbo     = laad_alle_dbo_bestellingen()
    alle_sap     = laad_alle_sap()

    zip_buf = io.BytesIO()
    n_gemaakt = 0

    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for winkelnaam, orders in alle_orders.items():
            if not any(v > 0 for v in orders.values()):
                continue
            dbo    = alle_dbo.get(winkelnaam, [])
            sap    = alle_sap.get(winkelnaam, {})
            artikelen = bouw_artikellijst(winkelnaam, orders, dbo, sap, artikelen_db)
            pik_bytes = schrijf_piklijst(winkelnaam, artikelen)
            zf.writestr(f"{winkelnaam}_PIKLIJST.xlsx", pik_bytes)
            n_gemaakt += 1

    if n_gemaakt == 0:
        st.warning("Geen bestellingen gevonden. Winkels moeten eerst hun bestelling invullen.")
    else:
        st.session_state["piklijsten_zip"] = zip_buf.getvalue()
        st.session_state["piklijsten_n"]   = n_gemaakt
        st.success(f"✅ {n_gemaakt} piklijst(en) gegenereerd. Download hieronder.")

if "piklijsten_zip" in st.session_state:
    st.download_button(
        label=f"⬇️ Download piklijsten ZIP ({st.session_state['piklijsten_n']} bestanden)",
        data=st.session_state["piklijsten_zip"],
        file_name="Lion_Piklijsten.zip",
        mime="application/zip",
        use_container_width=True,
    )

st.markdown("---")

# ─── Paklijsten genereren ────────────────────────────────────────────────────
st.subheader("📦 Stap 2 — Paklijsten genereren")
st.caption(
    "Upload de **gecorrigeerde** piklijsten (na je NIET OP VOORRAAD correcties) "
    "en genereer de paklijsten."
)

gecorrigeerde = st.file_uploader(
    "Upload gecorrigeerde piklijsten (.xlsx)",
    type=["xlsx"],
    accept_multiple_files=True,
    key="piklijst_upload",
)

if gecorrigeerde:
    if st.button("📦 Genereer paklijsten", type="primary", use_container_width=True):
        zip_buf  = io.BytesIO()
        n_gemaakt = 0

        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for bestand in gecorrigeerde:
                naam = bestand.name.replace("_PIKLIJST.xlsx", "").replace(".xlsx", "")
                pak_bytes = schrijf_paklijst(naam, bestand.read())
                zf.writestr(f"{naam}_PAKLIJST.xlsx", pak_bytes)
                n_gemaakt += 1
                st.success(f"✅ {naam}_PAKLIJST.xlsx gegenereerd")

        st.session_state["paklijsten_zip"] = zip_buf.getvalue()
        st.session_state["paklijsten_n"]   = n_gemaakt

if "paklijsten_zip" in st.session_state:
    st.download_button(
        label=f"⬇️ Download paklijsten ZIP ({st.session_state.get('paklijsten_n', 0)} bestanden)",
        data=st.session_state["paklijsten_zip"],
        file_name="Lion_Paklijsten.zip",
        mime="application/zip",
        use_container_width=True,
    )

st.markdown("---")

# ─── Reset bestellingen ───────────────────────────────────────────────────────
st.subheader("🗑️ Bestellingen wissen")


@st.dialog("⚠️ Bestellingen wissen")
def bevestig_reset():
    st.warning(
        "Je staat op het punt **alle bestellingen van alle winkels** te wissen. "
        "Dit kan niet ongedaan worden gemaakt.\n\n"
        "✅ Gebruik deze knop **alleen** nadat je de paklijsten hebt afgedrukt "
        "en alles verwerkt is."
    )
    col_ja, col_nee = st.columns(2)
    with col_ja:
        if st.button("Ja, wis alle bestellingen", type="primary", use_container_width=True):
            reset_alle_bestellingen()
            # Cache leegmaken zodat de statuspagina meteen klopt
            st.cache_data.clear()
            # Piklijsten/paklijsten uit sessie verwijderen
            for k in ["piklijsten_zip", "piklijsten_n", "paklijsten_zip", "paklijsten_n"]:
                st.session_state.pop(k, None)
            st.success("✅ Alle bestellingen zijn gewist. Klaar voor volgende week!")
            st.rerun()
    with col_nee:
        if st.button("Annuleren", use_container_width=True):
            st.rerun()


if st.button(
    "🗑️ Wis alle bestellingen (na afdrukken paklijsten)",
    use_container_width=True,
):
    bevestig_reset()
