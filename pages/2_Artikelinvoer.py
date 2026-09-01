"""
Artikelinvoer — Lion Beddenshop
Beheer artikelen in Supabase (als pagina binnen de bestelapp).
"""
import re
import streamlit as st
import requests
import pandas as pd
from urllib.parse import quote

# ── Auth check — alleen beheer (Wouter) mag hier komen ───────────────────────
if not st.session_state.get("ingelogd_als"):
    st.switch_page("app.py")
if st.session_state.get("rol") != "beheer":
    st.error("🔒  Geen toegang. Deze pagina is alleen voor beheerders.")
    st.stop()

# ── Configuratie ──────────────────────────────────────────────────────────────
SUPABASE_URL = "https://vuiidztqrmwoqwergurk.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ1aWlkenRxcm13b3F3ZXJndXJrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc4NDkxNzksImV4cCI6MjEwMzQyNTE3OX0"
    ".ioolw5fVSWpC4KREhrTW0Pcqex4qEAUd8YEukVCtmrY"
)
HDR_GET = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
HDR_WRITE = {
    **HDR_GET,
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# ── Supabase functies ─────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def laad_alle_artikelen():
    alle = []
    offset = 0
    while True:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/articles"
            f"?select=ean,artikel,sectie,pad_code,volgorde&limit=1000&offset={offset}",
            headers=HDR_GET,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        alle.extend(data)
        offset += len(data)
        if len(data) < 1000:
            break
    return alle

def patch_artikelen(filter_str: str, velden: dict):
    return requests.patch(
        f"{SUPABASE_URL}/rest/v1/articles?{filter_str}",
        headers=HDR_WRITE,
        json=velden,
    )

def insert_batch(batch: list):
    return requests.post(
        f"{SUPABASE_URL}/rest/v1/articles",
        headers=HDR_WRITE,
        json=batch,
    )

# ── Hulpfuncties ──────────────────────────────────────────────────────────────
def pad_sort_key(x):
    """Sorteert padnummers numeriek: 1, 2, 2A, 3, 3A, 4, 4A, 12, 13A ipv 1, 12, 13A, 2, 2A..."""
    m = re.match(r'^(\d+)([A-Za-z]*)$', str(x).strip())
    if m:
        return (int(m.group(1)), m.group(2).upper())
    return (9999, str(x))

def volgorde_uit_sectie(sectie: str) -> int:
    try:
        return int(sectie.strip().split()[0].lstrip("0") or "0")
    except Exception:
        return 0

def parse_excel_plak(tekst: str) -> list[dict]:
    """Verwerk tab- of komma-gescheiden tekst geplakt vanuit Excel."""
    rijen = []
    for regel in tekst.strip().splitlines():
        delen = regel.split("\t")
        if len(delen) < 2:
            delen = regel.split(",", 1)
        if len(delen) < 2:
            continue
        ean_raw = delen[0].strip().strip('"')
        artikel = delen[1].strip().strip('"')
        if not ean_raw or not artikel:
            continue
        try:
            ean = str(int(float(ean_raw.replace(",", "."))))
        except Exception:
            ean = ean_raw
        rijen.append({"ean": ean, "artikel": artikel})
    return rijen

# ── Pagina ────────────────────────────────────────────────────────────────────
st.title("🛏  Artikelinvoer")

col_info, col_btn = st.columns([6, 1])
with col_btn:
    if st.button("↻  Herladen", use_container_width=True):
        st.cache_data.clear()
        for k in list(st.session_state.keys()):
            if k.startswith("preview") or k.startswith("te_invoegen"):
                del st.session_state[k]
        st.rerun()

# ── Data laden ────────────────────────────────────────────────────────────────
with st.spinner("Verbinden met Supabase..."):
    try:
        artikelen = laad_alle_artikelen()
    except Exception as e:
        st.error(f"Kon geen verbinding maken met Supabase: {e}")
        st.stop()

bestaande_eans = {a["ean"] for a in artikelen}
secties_dict: dict[str, str] = {}
for a in artikelen:
    s = (a.get("sectie") or "").strip()
    p = (a.get("pad_code") or "").strip()
    if s and s not in secties_dict:
        secties_dict[s] = p

# Numeriek gesorteerde padnummers: 1, 2, 2A, 3, 3A, 4, 4A, 4B, 5, 5A, 7, 12, 13A...
pad_codes = sorted(
    {str(a.get("pad_code") or "").strip() for a in artikelen if a.get("pad_code")},
    key=pad_sort_key,
)

with col_info:
    c1, c2, c3 = st.columns(3)
    c1.metric("Artikelen in database", len(artikelen))
    c2.metric("Secties", len(secties_dict))
    c3.metric("Paden", len(pad_codes))

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["➕  Artikelen invoeren", "✏️  Padnummer wijzigen"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — INVOEREN
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### 1.  Sectie kiezen of aanmaken")
    sectie_opties = ["── Nieuwe sectie aanmaken ──"] + sorted(secties_dict.keys())
    sectie_keuze = st.selectbox("Sectie", sectie_opties, key="inv_sectie_keuze")
    if "Nieuwe sectie" in sectie_keuze:
        sectie = st.text_input("Naam nieuwe sectie", placeholder="bijv. 35 BADMATTEN",
                               key="inv_nieuwe_sectie").strip()
    else:
        sectie = sectie_keuze

    st.markdown("### 2.  Padnummer kiezen of aanmaken")
    pad_opties = ["── Nieuw pad aanmaken ──"] + pad_codes
    default_pad_idx = 0
    if sectie in secties_dict and secties_dict[sectie] in pad_opties:
        default_pad_idx = pad_opties.index(secties_dict[sectie])
    pad_keuze = st.selectbox("Padnummer", pad_opties, index=default_pad_idx, key="inv_pad_keuze")
    if "Nieuw pad" in pad_keuze:
        pad = st.text_input("Nieuw padnummer", placeholder="bijv. 26", key="inv_nieuw_pad").strip()
    else:
        pad = pad_keuze

    if sectie and pad and "Nieuwe" not in str(sectie) and "Nieuw" not in str(pad):
        st.info(f"Artikelen worden geplaatst in sectie **{sectie}** → pad **{pad}**")

    st.markdown("### 3.  Artikelen plakken vanuit Excel")
    st.caption("Selecteer in Excel: **Kolom A = EAN-code**  |  **Kolom B = Artikelnaam**  — Ctrl+C en hieronder plakken")
    plak_tekst = st.text_area(
        "Geplakte artikelen",
        height=160,
        key="inv_plak",
        placeholder="8712345678901\tCLAUDIA SINGLE THERMO\n8712345678902\tCLAUDIA 2-PERSOONS WIT",
        label_visibility="collapsed",
    )
    col_check, col_wis = st.columns([2, 1])
    with col_check:
        controleer = st.button("🔍  Controleer & preview", type="primary", use_container_width=True)
    with col_wis:
        if st.button("🗑  Wis", use_container_width=True):
            st.session_state["inv_plak"] = ""
            if "preview_data" in st.session_state:
                del st.session_state["preview_data"]
                del st.session_state["te_invoegen_data"]
            st.rerun()

    if controleer:
        fout = None
        if not sectie or "Nieuwe sectie" in sectie:
            fout = "Voer een sectienaam in."
        elif not pad or "Nieuw pad" in pad:
            fout = "Voer een padnummer in."
        elif not plak_tekst.strip():
            fout = "Plak eerst artikelen in het tekstvak."
        if fout:
            st.error(fout)
        else:
            rijen = parse_excel_plak(plak_tekst)
            if not rijen:
                st.error("Geen geldige rijen gevonden. Zorg dat EAN en naam gescheiden zijn door een tab.")
            else:
                preview = []
                te_invoegen = []
                for r in rijen:
                    if r["ean"] in bestaande_eans:
                        preview.append({"Status": "⚠️  Al aanwezig", "EAN": r["ean"], "Artikel": r["artikel"]})
                    else:
                        preview.append({"Status": "✅  Nieuw", "EAN": r["ean"], "Artikel": r["artikel"]})
                        te_invoegen.append({
                            "ean":      r["ean"],
                            "artikel":  r["artikel"],
                            "sectie":   sectie,
                            "pad_code": pad,
                            "volgorde": volgorde_uit_sectie(sectie),
                        })
                st.session_state["preview_data"]    = preview
                st.session_state["te_invoegen_data"] = te_invoegen
                st.session_state["inv_sectie_label"] = sectie
                st.session_state["inv_pad_label"]    = pad

    if "preview_data" in st.session_state:
        preview  = st.session_state["preview_data"]
        te_inv   = st.session_state["te_invoegen_data"]
        n_nieuw  = sum(1 for r in preview if "Nieuw" in r["Status"])
        n_dubbel = sum(1 for r in preview if "aanwezig" in r["Status"])
        st.markdown("### 4.  Preview")
        col_n, col_d = st.columns(2)
        col_n.success(f"✅  {n_nieuw} nieuw")
        col_d.warning(f"⚠️  {n_dubbel} overgeslagen (al aanwezig)")
        df = pd.DataFrame(preview)
        def kleur(rij):
            if "Nieuw" in rij["Status"]:
                return ["background-color:#c8f7c5; color:#1a1a1a"] * len(rij)
            return ["background-color:#ffc8c8; color:#1a1a1a"] * len(rij)
        st.dataframe(df.style.apply(kleur, axis=1), use_container_width=True, hide_index=True)
        if n_nieuw > 0:
            sectie_lbl = st.session_state.get("inv_sectie_label", "")
            pad_lbl    = st.session_state.get("inv_pad_label", "")
            if st.button(
                f"⬆️   Voeg {n_nieuw} nieuwe artikelen toe  →  sectie '{sectie_lbl}'  /  pad {pad_lbl}",
                type="primary",
                use_container_width=True,
            ):
                BATCH = 50
                ingevoegd = fouten = 0
                prog = st.progress(0, text="Uploaden...")
                for i in range(0, len(te_inv), BATCH):
                    batch = te_inv[i : i + BATCH]
                    resp = insert_batch(batch)
                    if resp.status_code in (200, 201):
                        ingevoegd += len(batch)
                    else:
                        fouten += len(batch)
                        st.warning(f"Batch fout {resp.status_code}: {resp.text[:200]}")
                    prog.progress(min((i + BATCH) / len(te_inv), 1.0))
                prog.empty()
                if fouten == 0:
                    st.success(f"✅  {ingevoegd} artikelen succesvol toegevoegd aan de database!")
                else:
                    st.warning(f"{ingevoegd} ingevoegd  |  {fouten} mislukt.")
                del st.session_state["preview_data"]
                del st.session_state["te_invoegen_data"]
                st.cache_data.clear()
                st.rerun()
        else:
            st.info("Alle artikelen staan al in de database — niets toe te voegen.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — WIJZIGEN
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Padnummer wijzigen voor een volledige sectie")
    wijk_sectie = st.selectbox("Sectie", sorted(secties_dict.keys()), key="wijk_sectie")
    if wijk_sectie:
        huidig_pad   = secties_dict.get(wijk_sectie, "—")
        aantal_art   = sum(1 for a in artikelen if a.get("sectie") == wijk_sectie)
        col_a, col_b = st.columns(2)
        col_a.info(f"Huidig padnummer: **{huidig_pad}**")
        col_b.info(f"Artikelen in deze sectie: **{aantal_art}**")
    wijk_nieuw_pad = st.text_input("Nieuw padnummer", key="wijk_nieuw_pad",
                                   placeholder="bijv. 14")
    if st.button("✅  Wijzig padnummer voor deze sectie", type="primary"):
        if not wijk_sectie:
            st.error("Selecteer een sectie.")
        elif not wijk_nieuw_pad.strip():
            st.error("Voer een nieuw padnummer in.")
        else:
            with st.spinner("Bijwerken..."):
                resp = patch_artikelen(
                    f"sectie=eq.{quote(wijk_sectie, safe='')}",
                    {"pad_code": wijk_nieuw_pad.strip()},
                )
            if resp.status_code in (200, 204):
                try:
                    count = len(resp.json())
                except Exception:
                    count = aantal_art
                st.success(f"✅  {count} artikelen in '{wijk_sectie}' → pad {wijk_nieuw_pad.strip()}")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"Fout {resp.status_code}: {resp.text[:300]}")

    st.divider()
    st.markdown("### Padnummer wijzigen voor één artikel (op EAN-code)")
    ean_input = st.text_input("EAN-code", key="ean_input", placeholder="bijv. 8712345678901")
    gevonden = None
    if ean_input.strip():
        gevonden = next((a for a in artikelen if a.get("ean") == ean_input.strip()), None)
        if gevonden:
            st.info(
                f"📦  **{gevonden['artikel']}**  \n"
                f"Sectie: {gevonden['sectie']}  |  Huidig pad: **{gevonden['pad_code']}**"
            )
        else:
            st.warning("EAN-code niet gevonden in de database.")
    ean_nieuw_pad = st.text_input("Nieuw padnummer", key="ean_nieuw_pad",
                                   placeholder="bijv. 14")
    if st.button("✅  Wijzig padnummer voor dit artikel", type="primary", key="btn_ean"):
        if not ean_input.strip():
            st.error("Voer een EAN-code in.")
        elif not gevonden:
            st.error("EAN niet gevonden — kan niet wijzigen.")
        elif not ean_nieuw_pad.strip():
            st.error("Voer een nieuw padnummer in.")
        else:
            with st.spinner("Bijwerken..."):
                resp = patch_artikelen(
                    f"ean=eq.{quote(ean_input.strip(), safe='')}",
                    {"pad_code": ean_nieuw_pad.strip()},
                )
            if resp.status_code in (200, 204):
                st.success(f"✅  EAN {ean_input.strip()} → pad {ean_nieuw_pad.strip()}")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"Fout {resp.status_code}: {resp.text[:300]}")
