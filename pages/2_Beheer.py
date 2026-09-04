"""
Lion Beddenshop — Beheerpagina (Wouter)
SAP uploaden, piklijsten genereren (PDF), correcties invoeren, paklijsten genereren (PDF), reset, historiek.
"""
import io
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
    laad_alle_sap, sla_sap_op, bestelling_status,
    reset_alle_bestellingen, reset_winkel_bestellingen, update_pad_codes,
    sla_piklijst_correcties_op, laad_piklijst_correcties,
    sla_definitief_op, laad_winkels_met_correcties,
    sla_order_history_op, update_order_status, laad_order_history,
    laad_order_statussen, laad_winkels, wis_order_history,
)
from utils.genereer import (
    bouw_artikellijst, schrijf_piklijst_pdf, schrijf_paklijst_pdf,
    lees_sap_xlsx, lees_padcodes_xlsx, maak_zip,
)

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
statussen = laad_order_statussen()

STATUS_LABELS = {
    "geen_bestelling": ("⚪", "Geen bestelling"),
    "besteld":         ("🟡", "Besteld"),
    "piklijst_klaar":  ("🟢", "Piklijst klaar"),
    "pakket_onderweg": ("🚚", "Pakket onderweg"),
}

cols = st.columns(min(len(status), 5))
for i, s in enumerate(status):
    with cols[i % len(cols)]:
        winkel_status = statussen.get(s["winkel"], {}).get("status", "geen_bestelling")
        icoon, label = STATUS_LABELS.get(winkel_status, ("⚪", winkel_status))
        stuks_str = f"{s['stuks']} st" if s["stuks"] > 0 else "—"
        regels_str = f"{s['regels']} regels"
        st.metric(
            label=f"{icoon} {s['winkel']}",
            value=stuks_str,
            delta=regels_str,
            delta_color="off",
            help=f"Status: {label}",
        )

# Pakket-onderweg knoppen per winkel die de status 'piklijst_klaar' hebben
winkels_pikklaar = [
    s["winkel"] for s in status
    if statussen.get(s["winkel"], {}).get("status") == "piklijst_klaar"
]
if winkels_pikklaar:
    st.caption("Markeer als 'Pakket onderweg' voor:")
    pak_cols = st.columns(min(len(winkels_pikklaar), 5))
    for i, winkelnaam in enumerate(winkels_pikklaar):
        with pak_cols[i % len(pak_cols)]:
            if st.button(f"🚚 {winkelnaam}", key=f"onderweg_{winkelnaam}", use_container_width=True):
                update_order_status(winkelnaam, "pakket_onderweg")
                st.success(f"✅ {winkelnaam} — pakket onderweg!")
                st.rerun()

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

# ─── Padcodes uploaden ────────────────────────────────────────────────────────
st.subheader("🗺️ Padcodes uploaden")
st.caption(
    "Upload een Excel met kolommen **EAN** en **Pad_code** om de padnummers in de catalogus bij te werken. "
    "Na het uploaden worden de piklijsten automatisch per pad gegroepeerd."
)
with st.expander("📋 Vereist Excel-formaat", expanded=False):
    st.markdown("""
Minimaal twee kolommen (kolomnamen worden automatisch herkend):

| EAN | Pad_code |
|-----|----------|
| 121201532 | A1 |
| 121201534 | A1 |
| 8719727167355 | B3 |

Kolomnamen die worden herkend: `EAN`, `Artikelnummer`, `Barcode` voor EAN
en `Pad_code`, `Padcode`, `Pad`, `Pad_nr` voor het padnummer.
""")
padcode_bestand = st.file_uploader(
    "Selecteer padcodes-bestand (.xlsx)",
    type=["xlsx"],
    key="padcode_upload",
)
if padcode_bestand:
    if st.button("🗺️ Verwerk padcodes", type="primary"):
        pad_codes = lees_padcodes_xlsx(padcode_bestand.read())
        if not pad_codes:
            st.error("❌ Geen padcodes gevonden. Controleer of de Excel kolommen 'EAN' en 'Pad_code' bevat.")
        else:
            bijgewerkt = update_pad_codes(pad_codes)
            st.success(f"✅ {bijgewerkt} artikelen bijgewerkt met padcodes.")
            st.info("De artikelcache is geleegd — nieuwe piklijsten gebruiken meteen de nieuwe padcodes.")
st.markdown("---")

# ─── Stap 1 — Piklijsten genereren (PDF) ─────────────────────────────────────
st.subheader("📋 Stap 1 — Piklijsten genereren")
st.caption(
    "Genereert piklijsten als PDF voor alle winkels met ingevulde bestellingen. "
    "De aantallen worden automatisch opgeslagen zodat je ze in Stap 2 kunt corrigeren."
)

# ── Pad-groepen instellen ─────────────────────────────────────────────────────
with st.expander("⚙️ Pad-groepen instellen (optioneel)", expanded=False):
    st.caption(
        "Typ per regel de padnummers die **samen op één blad** moeten worden afgedrukt, "
        "gescheiden door komma's. Paden die je hier niet noemt, krijgen elk een eigen blad. "
        "De padnummers moeten exact overeenkomen met de waarden in de piklijst (bijv. **15**, **15A**, **7**)."
    )
    bekende_pads = st.session_state.get("bekende_pads", [])
    if bekende_pads:
        st.info(f"Bekende pads uit vorige generatie: **{', '.join(bekende_pads)}**")
    groepen_tekst = st.text_area(
        "Pad-groepen (één groep per regel):",
        value=st.session_state.get("pad_groepen_tekst", ""),
        placeholder="Voorbeeld:\n15, 15A\n7, 12",
        height=120,
        key="pad_groepen_input",
    )
    st.session_state["pad_groepen_tekst"] = groepen_tekst


def _parse_pad_groepen(tekst: str) -> list:
    """Zet tekstveld om naar lijst van lijsten: '15, 15A\\n7, 12' → [['15','15A'],['7','12']]"""
    groepen = []
    for regel in (tekst or "").strip().splitlines():
        pads = [p.strip() for p in regel.split(",") if p.strip()]
        if len(pads) > 1:
            groepen.append(pads)
    return groepen


if st.button("🖨️ Genereer alle piklijsten", type="primary", use_container_width=True):
    pad_groepen = _parse_pad_groepen(st.session_state.get("pad_groepen_tekst", ""))

    artikelen_db = laad_artikelen()
    alle_orders  = laad_alle_bestellingen()
    alle_dbo     = laad_alle_dbo_bestellingen()
    alle_sap     = laad_alle_sap()

    piklijsten = {}   # {winkelnaam: pdf_bytes}
    n_gemaakt = 0
    alle_pads = set()

    progressie = st.progress(0, text="Bezig met genereren…")
    winkels_met_orders = [(w, o) for w, o in alle_orders.items() if any(v > 0 for v in o.values())]
    totaal = len(winkels_met_orders)

    for idx, (winkelnaam, orders) in enumerate(winkels_met_orders):
        progressie.progress((idx) / max(totaal, 1), text=f"Verwerken: {winkelnaam}…")
        dbo      = alle_dbo.get(winkelnaam, [])
        sap      = alle_sap.get(winkelnaam, {})
        artikelen = bouw_artikellijst(winkelnaam, orders, dbo, sap, artikelen_db)

        # Verzamel unieke pads (voor de hint in het pad-groepen veld)
        alle_pads.update(a["pad_code"] for a in artikelen if a.get("pad_code"))

        # PDF genereren met pad-groepen
        pdf_bytes = schrijf_piklijst_pdf(winkelnaam, artikelen, pad_groepen=pad_groepen)
        piklijsten[winkelnaam] = pdf_bytes

        # Correcties opslaan in database (startpunt voor Stap 2)
        sla_piklijst_correcties_op(winkelnaam, artikelen)

        # ✨ Orderhistorie opslaan (snapshot vóór reset)
        sla_order_history_op(winkelnaam, artikelen)

        # ✨ Status bijwerken naar 'piklijst_klaar'
        update_order_status(winkelnaam, "piklijst_klaar")

        n_gemaakt += 1

    progressie.progress(1.0, text="Klaar!")

    # Bewaar bekende pads voor de hint (gesorteerd)
    import re as _re
    def _pad_sort(p):
        m = _re.match(r'^(\d+)([A-Za-z]*)$', str(p))
        return (int(m.group(1)), m.group(2).upper()) if m else (9999, str(p))
    st.session_state["bekende_pads"] = sorted(alle_pads, key=_pad_sort)

    if n_gemaakt == 0:
        st.warning("Geen bestellingen gevonden. Winkels moeten eerst hun bestelling invullen.")
    else:
        st.session_state["piklijsten_pdf"] = piklijsten
        if pad_groepen:
            groep_labels = " | ".join(", ".join(g) for g in pad_groepen)
            st.info(f"Pad-groepen toegepast: {groep_labels}")
        st.success(f"✅ {n_gemaakt} piklijst(en) gegenereerd. Download hieronder per winkel of allemaal tegelijk.")

# Download-knoppen per winkel + zip
if "piklijsten_pdf" in st.session_state:
    piklijsten = st.session_state["piklijsten_pdf"]
    st.caption(f"**{len(piklijsten)} piklijst(en) beschikbaar:**")
    cols = st.columns(min(len(piklijsten), 4))
    for i, (winkelnaam, pdf_bytes) in enumerate(sorted(piklijsten.items())):
        with cols[i % len(cols)]:
            st.download_button(
                label=f"⬇️ {winkelnaam}",
                data=pdf_bytes,
                file_name=f"{winkelnaam}_PIKLIJST.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"dl_pik_{winkelnaam}",
            )
    # ✨ Zip-download alle piklijsten
    if len(piklijsten) > 1:
        zip_bytes = maak_zip(piklijsten, "_PIKLIJST")
        st.download_button(
            label=f"📦 Download ALLE piklijsten als zip ({len(piklijsten)} bestanden)",
            data=zip_bytes,
            file_name="alle_piklijsten.zip",
            mime="application/zip",
            use_container_width=True,
            key="dl_pik_zip",
        )

st.markdown("---")

# ─── Stap 2 — Correcties invoeren ────────────────────────────────────────────
st.subheader("✏️ Stap 2 — Correcties invoeren")
st.caption(
    "Pas hier de aantallen aan na het pakken (bijv. NIET OP VOORRAAD artikelen). "
    "Sla op per winkel. De gecorrigeerde aantallen worden gebruikt voor de paklijst in Stap 3."
)

winkels_met_corr = laad_winkels_met_correcties()

if not winkels_met_corr:
    st.info("Nog geen piklijsten gegenereerd. Voer eerst Stap 1 uit.")
else:
    gekozen_winkel = st.selectbox(
        "Kies winkel (typ om te zoeken):",
        options=winkels_met_corr,
        key="correctie_winkel",
    )

    if gekozen_winkel:
        correcties = laad_piklijst_correcties(gekozen_winkel)

        if not correcties:
            st.info(f"Geen correctie-regels gevonden voor {gekozen_winkel}.")
        else:
            key_prefix = f"corr_{gekozen_winkel}"

            # Initialiseer session_state voor ALLE regels vóór het filteren
            for c in correcties:
                sk = f"{key_prefix}_{c['id']}"
                if sk not in st.session_state:
                    st.session_state[sk] = c["definitief_aantal"]

            zoekterm = st.text_input(
                "🔍 Zoek op artikel, sectie of pad:",
                key=f"zoek_{gekozen_winkel}",
                placeholder="Typ om te filteren…",
            )

            if zoekterm.strip():
                term = zoekterm.strip().lower()
                gefilterd = [
                    c for c in correcties
                    if term in (c.get("artikel") or "").lower()
                    or term in (c.get("sectie") or "").lower()
                    or term in (c.get("pad_code") or "").lower()
                ]
                st.caption(
                    f"**{len(gefilterd)} van {len(correcties)} regels** zichtbaar "
                    f"— wijzigingen in verborgen regels blijven bewaard."
                )
            else:
                gefilterd = correcties
                st.caption(f"**{len(correcties)} regels** — pas de 'Definitief' kolom aan waar nodig.")

            if not gefilterd:
                st.warning("Geen artikelen gevonden voor deze zoekterm.")
            else:
                hdr = st.columns([1, 3, 7, 3, 3])
                hdr[0].markdown("**Pad**")
                hdr[1].markdown("**Sectie**")
                hdr[2].markdown("**Artikel**")
                hdr[3].markdown("**Piklijst**")
                hdr[4].markdown("**Definitief**")
                st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

                for c in gefilterd:
                    sk = f"{key_prefix}_{c['id']}"
                    col = st.columns([1, 3, 7, 3, 3])
                    col[0].write(c.get("pad_code") or "—")
                    col[1].write(c.get("sectie") or "")
                    col[2].write(c.get("artikel") or "")
                    col[3].write(str(c.get("piklijst_aantal") or 0))
                    col[4].number_input(
                        label="",
                        min_value=0,
                        value=st.session_state[sk],
                        step=1,
                        key=sk,
                        label_visibility="collapsed",
                    )

            if st.button(f"💾 Sla correcties op voor {gekozen_winkel}", type="primary"):
                gewijzigd = [
                    {"id": c["id"], "definitief_aantal": st.session_state[f"{key_prefix}_{c['id']}"]}
                    for c in correcties
                ]
                sla_definitief_op(gekozen_winkel, gewijzigd)
                st.success(f"✅ Correcties opgeslagen voor {gekozen_winkel}.")

st.markdown("---")

# ─── Stap 3 — Paklijsten genereren (PDF) ─────────────────────────────────────
st.subheader("📦 Stap 3 — Paklijsten genereren")
st.caption(
    "Genereert paklijsten als PDF op basis van de gecorrigeerde aantallen uit Stap 2. "
    "Sla eerst de correcties op in Stap 2 voordat je hier genereert."
)

winkels_paklijst = laad_winkels_met_correcties()

if not winkels_paklijst:
    st.info("Nog geen piklijsten gegenereerd. Voer eerst Stap 1 uit.")
else:
    col_pak1, col_pak2 = st.columns([2, 1])
    with col_pak1:
        gekozen_pak = st.multiselect(
            "Kies winkels voor paklijst:",
            options=winkels_paklijst,
            default=winkels_paklijst,
            key="paklijst_winkels",
        )
    with col_pak2:
        st.markdown("<br>", unsafe_allow_html=True)
        genereer_pak = st.button(
            "📦 Genereer paklijsten",
            type="primary",
            use_container_width=True,
            disabled=not gekozen_pak,
        )

    if genereer_pak and gekozen_pak:
        paklijsten = {}
        for winkelnaam in gekozen_pak:
            correcties = laad_piklijst_correcties(winkelnaam)
            if not correcties:
                st.warning(f"⚠️ Geen correcties gevonden voor {winkelnaam}, overgeslagen.")
                continue
            pdf_bytes = schrijf_paklijst_pdf(winkelnaam, correcties)
            paklijsten[winkelnaam] = pdf_bytes
            st.success(f"✅ Paklijst gegenereerd voor {winkelnaam}")
        if paklijsten:
            st.session_state["paklijsten_pdf"] = paklijsten

    # Download-knoppen + zip
    if "paklijsten_pdf" in st.session_state:
        paklijsten = st.session_state["paklijsten_pdf"]
        st.caption(f"**{len(paklijsten)} paklijst(en) beschikbaar:**")
        cols = st.columns(min(len(paklijsten), 4))
        for i, (winkelnaam, pdf_bytes) in enumerate(sorted(paklijsten.items())):
            with cols[i % len(cols)]:
                st.download_button(
                    label=f"⬇️ {winkelnaam}",
                    data=pdf_bytes,
                    file_name=f"{winkelnaam}_PAKLIJST.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_pak_{winkelnaam}",
                )
        # ✨ Zip-download alle paklijsten
        if len(paklijsten) > 1:
            zip_bytes = maak_zip(paklijsten, "_PAKLIJST")
            st.download_button(
                label=f"📦 Download ALLE paklijsten als zip ({len(paklijsten)} bestanden)",
                data=zip_bytes,
                file_name="alle_paklijsten.zip",
                mime="application/zip",
                use_container_width=True,
                key="dl_pak_zip",
            )

st.markdown("---")

# ─── Reset bestellingen ───────────────────────────────────────────────────────
st.subheader("🗑️ Bestellingen wissen")

status_reset = bestelling_status()
winkels_met_orders = [s["winkel"] for s in status_reset if s["regels"] > 0]

if not winkels_met_orders:
    st.info("Geen openstaande bestellingen om te wissen.")
else:
    geselecteerd = st.multiselect(
        "Kies welke winkels je wilt wissen:",
        options=winkels_met_orders,
        default=winkels_met_orders,
    )

    @st.dialog("⚠️ Bestellingen wissen")
    def bevestig_reset():
        te_wissen = st.session_state.get("_te_wissen", [])
        if len(te_wissen) == len(winkels_met_orders):
            omschrijving = "**alle winkels**"
        else:
            omschrijving = ", ".join(f"**{w}**" for w in te_wissen)
        st.warning(
            f"Je staat op het punt de bestellingen van {omschrijving} te wissen. "
            "Dit kan niet ongedaan worden gemaakt."
        )
        col_ja, col_nee = st.columns(2)
        with col_ja:
            if st.button("Ja, wis bestellingen", type="primary", use_container_width=True):
                reset_winkel_bestellingen(te_wissen)
                st.cache_data.clear()
                for k in ["piklijsten_pdf", "paklijsten_pdf", "_te_wissen"]:
                    st.session_state.pop(k, None)
                st.success(f"✅ Gewist: {', '.join(te_wissen)}")
                st.rerun()
        with col_nee:
            if st.button("Annuleren", use_container_width=True):
                st.rerun()

    if geselecteerd:
        if st.button(
            f"🗑️ Wis bestellingen ({len(geselecteerd)} winkel(s))",
            use_container_width=True,
        ):
            st.session_state["_te_wissen"] = geselecteerd
            bevestig_reset()
    else:
        st.caption("Selecteer minimaal één winkel.")

st.markdown("---")

# ─── Orderhistoriek ───────────────────────────────────────────────────────────
st.subheader("📜 Orderhistoriek")
st.caption(
    "Overzicht van alle gegenereerde piklijsten. "
    "De data blijft bewaard na een reset, zodat je altijd kunt terugkijken."
)

import pandas as pd
import datetime as _dt

alle_winkels = [w["name"] for w in laad_winkels()]

# ── Filters ───────────────────────────────────────────────────────────────────
fc1, fc2 = st.columns(2)
with fc1:
    hist_filter = st.selectbox(
        "Filter op winkel:",
        options=["Alle winkels"] + alle_winkels,
        key="hist_winkel_filter",
    )
with fc2:
    hist_jaar = st.selectbox(
        "Filter op jaar:",
        options=["Alle jaren"] + list(range(_dt.date.today().year, 2024, -1)),
        key="hist_jaar_filter",
    )

winkel_filter = None if hist_filter == "Alle winkels" else hist_filter
history = laad_order_history(winkelnaam=winkel_filter, limit=500)

# Jaar-filter client-side (sneller dan extra DB-call)
if hist_jaar != "Alle jaren":
    history = [h for h in history if h.get("jaar") == int(hist_jaar)]

if not history:
    st.info("Geen historiek gevonden voor deze filters.")
else:
    df = pd.DataFrame(history)
    df["datum"] = pd.to_datetime(df["datum"]).dt.strftime("%d-%m-%Y %H:%M")
    df = df.rename(columns={
        "winkelnaam":    "Winkel",
        "datum":         "Datum",
        "weeknummer":    "Week",
        "jaar":          "Jaar",
        "totaal_stuks":  "Stuks",
        "totaal_regels": "Regels",
    })
    df = df[["Winkel", "Datum", "Week", "Jaar", "Stuks", "Regels"]]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(history)} piklijst-generaties weergegeven.")

# ── Historiek wissen ──────────────────────────────────────────────────────────
with st.expander("🗑️ Historiek wissen", expanded=False):
    st.caption("Verwijder historiek-regels per winkel en/of vóór een bepaalde datum. Beide filters tegelijk zijn mogelijk.")

    wc1, wc2 = st.columns(2)
    with wc1:
        wis_winkel = st.selectbox(
            "Winkel (leeg = alle winkels):",
            options=["Alle winkels"] + alle_winkels,
            key="wis_hist_winkel",
        )
    with wc2:
        wis_voor = st.date_input(
            "Wis alles vóór datum (leeg = geen datumfilter):",
            value=None,
            key="wis_hist_datum",
        )

    wis_winkel_val = None if wis_winkel == "Alle winkels" else wis_winkel
    wis_datum_val  = wis_voor.isoformat() if wis_voor else None

    # Omschrijving wat er gewist wordt
    omschr_delen = []
    if wis_winkel_val:
        omschr_delen.append(f"winkel **{wis_winkel_val}**")
    else:
        omschr_delen.append("**alle winkels**")
    if wis_datum_val:
        omschr_delen.append(f"vóór **{wis_voor.strftime('%d-%m-%Y')}**")
    omschr = " · ".join(omschr_delen)

    st.warning(f"Dit verwijdert historiek voor {omschr}. Dit kan niet ongedaan worden gemaakt.")

    @st.dialog("⚠️ Historiek wissen")
    def bevestig_wis_history():
        params = st.session_state.get("_wis_hist_params", {})
        st.warning(
            f"Je staat op het punt historiek te wissen voor "
            f"{params.get('omschr', '?')}. Definitief verwijderd."
        )
        col_ja, col_nee = st.columns(2)
        with col_ja:
            if st.button("Ja, verwijder", type="primary", use_container_width=True):
                wis_order_history(
                    winkelnaam=params.get("winkel"),
                    voor_datum=params.get("datum"),
                )
                st.session_state.pop("_wis_hist_params", None)
                st.success("✅ Historiek gewist.")
                st.rerun()
        with col_nee:
            if st.button("Annuleren", use_container_width=True):
                st.rerun()

    if st.button("🗑️ Wis geselecteerde historiek", use_container_width=True):
        st.session_state["_wis_hist_params"] = {
            "winkel": wis_winkel_val,
            "datum":  wis_datum_val,
            "omschr": omschr,
        }
        bevestig_wis_history()
