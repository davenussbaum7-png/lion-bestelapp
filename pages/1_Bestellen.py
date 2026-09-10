"""
Lion Beddenshop — Winkelformulier
Winkels vullen hier hun wekelijkse bestelling in.
"""
import os
import re as _re
import datetime as _dt
import streamlit as st
from PIL import Image

# ─── Weeknummer berekenen ─────────────────────────────────────────────────────
_vandaag    = _dt.date.today()
_bestelweek = _vandaag.isocalendar()[1]
_leverweek  = (_vandaag + _dt.timedelta(weeks=1)).isocalendar()[1]

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

# ─── Verberg Streamlit-branding ───────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stToolbar"] { display: none !important; }
.stDeployButton { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ─── Toegangscontrole ─────────────────────────────────────────────────────────
if st.session_state.get("rol") != "winkel":
    st.warning("Je bent niet ingelogd. Ga terug naar de hoofdpagina.")
    if st.button("← Naar inlogpagina"):
        st.switch_page("app.py")
    st.stop()

winkelnaam = st.session_state.ingelogd_als

from utils.database import (
    laad_artikelen, laad_bestelling, laad_dbo_bestelling,
    sla_bestelling_op, sla_dbo_op, laad_order_status_info,
    laad_buffer, wis_buffer, sla_buffer_op,
)

def _invalideer_winkel_cache(winkelnaam: str):
    """Wis gecachede data na een opslaan, zodat de volgende rerun verse data toont."""
    laad_dbo_bestelling.clear()
    laad_order_status_info.clear()

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
.sectie-header {
    font-weight: 700;
    font-size: 0.95rem;
    color: #374151;
    margin: 12px 0 4px;
    padding-bottom: 4px;
    border-bottom: 1px solid #e5e7eb;
}
</style>
""", unsafe_allow_html=True)

# ─── Natural sort voor sectienamen ────────────────────────────────────────────
def _sectie_sort_key(naam: str):
    """
    Natural sort: splitst tekst en getallen zodat bijv.
    '6 CM' < '8 CM' < '10 CM' in plaats van alfabetisch '10' < '6' < '8'.
    """
    delen = _re.split(r'(\d+)', (naam or "").upper())
    return [int(d) if d.isdigit() else d for d in delen]

# ─── Data laden ───────────────────────────────────────────────────────────────
artikelen_db   = laad_artikelen()
dbo_opgeslagen = laad_dbo_bestelling(winkelnaam)

# ─── Status EERST laden (vóór session state init) ─────────────────────────────
_status_info = laad_order_status_info(winkelnaam)
_status      = _status_info.get("status", "geen_bestelling")
_bijgewerkt  = _status_info.get("bijgewerkt")
vergrendeld  = _status in ("piklijst_klaar", "pakket_onderweg")

# ─── Session state initialiseren (eenmalig vanuit DB bij eerste laad) ─────────
if f"_geladen_{winkelnaam}" not in st.session_state:
    if vergrendeld:
        # Vergrendeld: laad buffer (pre-orders voor de volgende ronde)
        buffer = laad_buffer(winkelnaam)
        for art in artikelen_db:
            ean = art["ean"]
            st.session_state[f"art_{ean}"] = buffer.get(ean, 0) or 0
        if buffer:
            st.session_state["_buffer_actief"] = True
    else:
        # Niet vergrendeld: laad huidige actieve bestelling
        opgeslagen = laad_bestelling(winkelnaam)
        for art in artikelen_db:
            ean = art["ean"]
            st.session_state[f"art_{ean}"] = opgeslagen.get(ean, 0) or 0
        # Buffer check: als er geen lopende bestelling is maar wel een buffer (na reset)
        heeft_lopende = any(st.session_state.get(f"art_{a['ean']}", 0) > 0 for a in artikelen_db)
        if not heeft_lopende:
            buffer = laad_buffer(winkelnaam)
            if buffer:
                for art in artikelen_db:
                    ean = art["ean"]
                    if ean in buffer and buffer[ean] > 0:
                        st.session_state[f"art_{ean}"] = buffer[ean]
                st.session_state["_buffer_geladen"] = True

    # DBO initialiseren
    dbo_secties_init = ["01 1 PERS.DBO", "02 2 PERS.DBO", "03 3 Pers.DBO", "04 260 BR.DBO", "05 Diversen"]
    dbo_bestaand_init = {}
    for r in dbo_opgeslagen:
        dbo_bestaand_init.setdefault(r["sectie"], []).append(r)
    for sectie_dbo in dbo_secties_init:
        bestaande = dbo_bestaand_init.get(sectie_dbo, [])
        n_rijen = max(10, len(bestaande) + 2)
        for i in range(n_rijen):
            b = bestaande[i] if i < len(bestaande) else {}
            if f"dbo_art_{sectie_dbo}_{i}" not in st.session_state:
                st.session_state[f"dbo_art_{sectie_dbo}_{i}"] = b.get("artikel", "")
            if f"dbo_qty_{sectie_dbo}_{i}" not in st.session_state:
                st.session_state[f"dbo_qty_{sectie_dbo}_{i}"] = b.get("quantity", 0) or 0
    st.session_state[f"_geladen_{winkelnaam}"] = True

# ─── Cart items berekenen ─────────────────────────────────────────────────────
_cart_eans = {a["ean"] for a in artikelen_db if st.session_state.get(f"art_{a['ean']}", 0) > 0}
_n_cart    = len(_cart_eans)

# ─── Save-knop label ─────────────────────────────────────────────────────────
_opslaan_label = "💾  Alvast bestellen — volgende ronde" if vergrendeld else "💾  Sla bestelling op"

# ─── Header ───────────────────────────────────────────────────────────────────
col_logo, col_title, col_knoppen = st.columns([1, 5, 2])
with col_logo:
    if _logo_path:
        st.image(_logo_path, width=72)
with col_title:
    st.title(f"Bestelling — {winkelnaam}")
    st.caption(f"📦 Bestelweek {_bestelweek} → Levering week {_leverweek}")
with col_knoppen:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Uitloggen", use_container_width=True):
        st.session_state.rol = None
        st.session_state.ingelogd_als = None
        st.switch_page("app.py")
    opslaan = st.button(
        _opslaan_label,
        type="primary",
        use_container_width=True,
        key="opslaan_header",
    )

# ─── Feedback van vorige opslag tonen ────────────────────────────────────────
if "_save_result" in st.session_state:
    _res = st.session_state.pop("_save_result")
    if _res["ok"]:
        st.success(_res["msg"])
    else:
        st.error(_res["msg"])
        st.info("Ververs de pagina en probeer opnieuw. Als het probleem blijft, neem contact op met Wouter.")

# ─── Statusbalk ───────────────────────────────────────────────────────────────
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

if _bijgewerkt:
    try:
        from datetime import datetime as _datetime
        _ts = _datetime.fromisoformat(_bijgewerkt.replace("Z", "+00:00"))
        _ts_str = _ts.strftime("%-d %b %H:%M")
        _tijdlabel = f" <span style='color:#999;font-size:0.85rem'>· bijgewerkt {_ts_str}</span>"
    except Exception:
        _tijdlabel = ""
else:
    _tijdlabel = ""

st.markdown(f"""
<div class="status-balk">
  <span class="status-stap {_s1}">✅ Bestelling ontvangen</span>
  <span class="status-pijl">›</span>
  <span class="status-stap {_s2}">📋 Piklijst klaar</span>
  <span class="status-pijl">›</span>
  <span class="status-stap {_s3}">🚚 Pakket onderweg</span>
  &nbsp;·&nbsp; <span style="color:#555">{_icoon} {_label}</span>{_tijdlabel}
</div>
""", unsafe_allow_html=True)

# ─── Meldingen ────────────────────────────────────────────────────────────────
if vergrendeld:
    if st.session_state.get("_buffer_actief"):
        st.info(
            f"📦 **Volgende ronde — je bestelling staat al klaar.** "
            "Pas aan waar nodig en sla opnieuw op. "
            "Wouter laadt dit automatisch in zodra hij de nieuwe ronde start."
        )
    else:
        st.info(
            f"📦 **Bestelling week {_bestelweek} is verwerkt door Wouter.** "
            "Je kunt alvast je bestelling voor de **volgende ronde** klaarzetten. "
            "Wouter laadt dit automatisch in zodra hij de nieuwe ronde start."
        )
elif st.session_state.get("_buffer_geladen"):
    st.info(
        f"📦 **Nieuwe bestelronde gestart — Levering week {_leverweek}.** "
        "Je vorige bestelling staat klaar als startpunt. "
        "Pas aan waar nodig en druk daarna op **Sla bestelling op**."
    )
elif _status == "geen_bestelling":
    st.success(
        f"🟢 **Bestelronde open — Levering week {_leverweek}.** "
        "Vul je bestelling in en sla op wanneer je klaar bent."
    )
elif _status == "besteld":
    st.success(
        f"✅ **Bestelling week {_leverweek} is ontvangen door Wouter.** "
        "Je kunt de aantallen nog aanpassen tot de piklijst verwerkt wordt."
    )

st.markdown("---")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
_tab_cart_label = f"🛒 Mijn bestelling ({_n_cart})" if _n_cart > 0 else "🛒 Mijn bestelling"
tab_alle, tab_cart = st.tabs(["📝 Alle artikelen", _tab_cart_label])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Alle artikelen
# ══════════════════════════════════════════════════════════════════════════════
with tab_alle:
    if vergrendeld:
        st.markdown("Zet alvast je bestelling klaar voor de **volgende ronde**. Artikelen die al in je bestelling staan zie je in **Mijn bestelling**.")
    else:
        st.markdown("Vul de aantallen in die je wilt bestellen. Artikelen die al in je bestelling staan zie je in **Mijn bestelling**.")

    # Zoekbalk
    zoekterm = st.text_input("🔍 Zoek op artikelnaam, sectie of EAN",
                             placeholder="bijv. Claudia 140 of Jersey...")

    # Artikelen filteren
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

    # Totaal teller
    totaal_ingevuld = sum(
        st.session_state.get(f"art_{a['ean']}", 0)
        for a in artikelen_db
        if st.session_state.get(f"art_{a['ean']}", 0) > 0
    )
    if _n_cart > 0:
        st.info(f"**{totaal_ingevuld} stuks** ingevuld · **{_n_cart} artikelen** in bestelling")

    if zoekterm.strip() and not gefilterd:
        st.warning(f"Geen artikelen gevonden voor **'{zoekterm.strip()}'**. Controleer de spelling of probeer een andere zoekterm.")

    secties = {}
    for art in gefilterd:
        s = art.get("sectie") or "Overig"
        secties.setdefault(s, []).append(art)

    # Natural sort: getallen in sectienamen numerisch vergelijken (6 CM < 8 CM < 10 CM)
    # Bij actieve zoekterm: secties altijd open (zodat ze niet dichtklappen bij getal invoer)
    _secties_gesorteerd = sorted(secties.items(), key=lambda x: _sectie_sort_key(x[0]))
    _auto_expand = bool(zoekterm.strip()) and len(_secties_gesorteerd) <= 5
    for sectie, artikelen_sectie in _secties_gesorteerd:
        in_cart = sum(1 for a in artikelen_sectie if a["ean"] in _cart_eans)
        sectie_label = f"📦 {sectie} ({len(artikelen_sectie)} artikelen)"
        if in_cart > 0:
            sectie_label += f" · ✅ {in_cart} besteld"

        with st.expander(sectie_label, expanded=_auto_expand):
            for art in artikelen_sectie:
                ean   = art["ean"]
                label = art["artikel"]
                col_art, col_num = st.columns([5, 1])
                with col_art:
                    st.markdown(f"<p class='art-label'>{label}</p>", unsafe_allow_html=True)
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

    # ─── DBO-secties ──────────────────────────────────────────────────────────
    dbo_secties = ["01 1 PERS.DBO", "02 2 PERS.DBO", "03 3 Pers.DBO", "04 260 BR.DBO", "05 Diversen"]
    dbo_bestaand = {}
    for r in dbo_opgeslagen:
        dbo_bestaand.setdefault(r["sectie"], []).append(r)

    st.subheader("DBO — Vrije invoer")
    if vergrendeld:
        st.caption("DBO-bestellingen kun je invullen zodra Wouter de nieuwe ronde start.")
    else:
        st.caption("Artikelen die niet in de lijst staan. Typ de naam en het aantal.")

    for sectie_dbo in dbo_secties:
        with st.expander(f"📝 {sectie_dbo}", expanded=False):
            bestaande_regels = dbo_bestaand.get(sectie_dbo, [])
            n_rijen = max(10, len(bestaande_regels) + 2)
            for i in range(n_rijen):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.text_input(
                        "Artikel",
                        key=f"dbo_art_{sectie_dbo}_{i}",
                        label_visibility="collapsed",
                        placeholder="Artikelnaam...",
                        disabled=vergrendeld,
                    )
                with c2:
                    st.number_input(
                        "Aantal",
                        min_value=0,
                        max_value=999,
                        key=f"dbo_qty_{sectie_dbo}_{i}",
                        label_visibility="collapsed",
                        disabled=vergrendeld,
                    )

    st.markdown("---")

    opslaan_footer = st.button(
        _opslaan_label,
        type="primary",
        use_container_width=True,
        key="opslaan_footer",
    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Mijn bestelling (cart)
# ══════════════════════════════════════════════════════════════════════════════
with tab_cart:
    if not _cart_eans:
        if vergrendeld:
            st.info("🛒 Nog niets klaargezet voor de volgende ronde. Ga naar **Alle artikelen** om te bestellen.")
        else:
            st.info("🛒 Je hebt nog geen artikelen in je bestelling. Ga naar **Alle artikelen** om artikelen toe te voegen.")
    else:
        totaal_cart_stuks = sum(
            st.session_state.get(f"art_{a['ean']}", 0)
            for a in artikelen_db if a["ean"] in _cart_eans
        )
        if vergrendeld:
            st.info(f"**{totaal_cart_stuks} stuks** · **{_n_cart} artikelen** klaargezet voor de volgende ronde")
        else:
            st.info(f"**{totaal_cart_stuks} stuks** · **{_n_cart} artikelen** in bestelling")

        cart_secties: dict = {}
        for art in artikelen_db:
            if art["ean"] in _cart_eans:
                cart_secties.setdefault(art.get("sectie") or "Overig", []).append(art)

        # Natural sort ook in cart-tab
        for sectie, items in sorted(cart_secties.items(), key=lambda x: _sectie_sort_key(x[0])):
            st.markdown(f"<div class='sectie-header'>{sectie}</div>", unsafe_allow_html=True)
            for art in items:
                ean = art["ean"]
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"<p class='art-label'>{art['artikel']}</p>", unsafe_allow_html=True)
                with col2:
                    qty = st.session_state.get(f"art_{ean}", 0)
                    st.markdown(f"<p style='text-align:right;font-weight:700;padding-top:4px'>{qty}</p>", unsafe_allow_html=True)
            st.markdown("")

        # DBO samenvatting — alleen tonen als niet vergrendeld
        if not vergrendeld:
            dbo_gevuld = [
                r for r in dbo_opgeslagen
                if r.get("quantity", 0) > 0 and r.get("artikel", "").strip()
            ]
            if dbo_gevuld:
                st.markdown("---")
                st.markdown("<div class='sectie-header'>DBO — Vrije invoer</div>", unsafe_allow_html=True)
                for r in dbo_gevuld:
                    st.markdown(f"- **{r['artikel']}** ({r['sectie']}): {r['quantity']} st")
                st.caption("Aanpassen? Open 'Alle artikelen' → DBO-sectie hieronder.")

        st.markdown("---")
        opslaan_cart = st.button(
            _opslaan_label,
            type="primary",
            use_container_width=True,
            key="opslaan_cart",
        )

# ─── Opslaan afhandelen ───────────────────────────────────────────────────────
_opslaan = opslaan or opslaan_footer or st.session_state.get("opslaan_cart", False)

if _opslaan:
    dbo_secties = ["01 1 PERS.DBO", "02 2 PERS.DBO", "03 3 Pers.DBO", "04 260 BR.DBO", "05 Diversen"]
    dbo_bestaand = {}
    for r in dbo_opgeslagen:
        dbo_bestaand.setdefault(r["sectie"], []).append(r)

    nieuwe_orders = {}
    for art in artikelen_db:
        ean = art["ean"]
        nieuwe_orders[ean] = st.session_state.get(f"art_{ean}", 0)

    nieuwe_dbo = []
    if not vergrendeld:
        for sectie_dbo in dbo_secties:
            bestaande_regels = dbo_bestaand.get(sectie_dbo, [])
            n_rijen = max(10, len(bestaande_regels) + 2)
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
        if vergrendeld:
            # Sla op in buffer voor de volgende ronde
            sla_buffer_op(winkelnaam, nieuwe_orders)
            _invalideer_winkel_cache(winkelnaam)
            st.session_state["_buffer_actief"] = True
            ingevuld = sum(1 for v in nieuwe_orders.values() if v > 0)
            st.session_state["_save_result"] = {
                "ok": True,
                "msg": f"✅ Bestelling klaargezet voor de volgende ronde! {ingevuld} artikelen. Wouter laadt dit automatisch in.",
            }
        else:
            # Normale opslag als actieve bestelling
            wis_buffer(winkelnaam)
            st.session_state.pop("_buffer_geladen", None)
            sla_bestelling_op(winkelnaam, nieuwe_orders)
            sla_dbo_op(winkelnaam, nieuwe_dbo)
            _invalideer_winkel_cache(winkelnaam)
            ingevuld = sum(1 for v in nieuwe_orders.values() if v > 0) + len(nieuwe_dbo)
            st.session_state["_save_result"] = {
                "ok": True,
                "msg": f"✅ Bestelling week {_leverweek} opgeslagen! {ingevuld} regels ingevuld.",
            }
    except Exception as fout:
        st.session_state["_save_result"] = {
            "ok": False,
            "msg": f"❌ Fout bij opslaan: {fout}",
        }
    st.rerun()
