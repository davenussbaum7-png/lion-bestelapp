"""
Supabase database verbinding en helpers.
"""
import datetime
import time
import streamlit as st
from supabase import create_client, Client


def _retry(func, max_pogingen=3):
    """
    Voer een callable uit met retry bij netwerk- of verbindingsfouten.
    Gebruik: _retry(lambda: db.table(...).execute())
    """
    laatste_fout = None
    for poging in range(max_pogingen):
        try:
            return func()
        except Exception as fout:
            laatste_fout = fout
            if poging < max_pogingen - 1:
                time.sleep(2 ** poging)   # 1s, dan 2s
    raise laatste_fout


@st.cache_resource(ttl=3600)
def get_client() -> Client:
    """
    Verbinding met Supabase. Probeert 3 keer bij opstartproblemen.
    TTL van 1 uur zorgt dat een slechte verbinding zichzelf herstelt.
    """
    laatste_fout = None
    for poging in range(3):
        try:
            url = st.secrets["supabase_url"]
            key = st.secrets["supabase_key"]
            client = create_client(url, key)
            return client
        except Exception as fout:
            laatste_fout = fout
            if poging < 2:
                time.sleep(2 ** poging)   # wacht 1s, daarna 2s
    raise laatste_fout


# ─── Artikelen ────────────────────────────────────────────────────────────────
def update_pad_codes(pad_codes: dict):
    """
    Update pad_code voor bestaande artikelen.
    pad_codes = {ean: pad_code}
    """
    db = get_client()
    bijgewerkt = 0
    for ean, pad in pad_codes.items():
        if pad:
            db.table("articles").update({"pad_code": pad}).eq("ean", ean).execute()
            bijgewerkt += 1
    laad_artikelen.clear()
    return bijgewerkt


@st.cache_data(ttl=3600)
def laad_artikelen():
    """Laad alle artikelen uit de catalogus (gecached, 1 uur geldig)."""
    db = get_client()
    alle = []
    offset = 0
    while True:
        resultaat = _retry(lambda o=offset: db.table("articles").select("*").order("volgorde").range(o, o + 999).execute())
        data = resultaat.data
        if not data:
            break
        alle.extend(data)
        offset += len(data)
        if len(data) < 1000:
            break
    return alle


# ─── Bestellingen lezen ───────────────────────────────────────────────────────
def laad_bestelling(winkelnaam: str) -> dict:
    """Geeft {ean: quantity} dict voor de winkel."""
    db = get_client()
    rows = _retry(lambda: db.table("store_orders")
                             .select("ean, quantity")
                             .eq("store_name", winkelnaam)
                             .execute())
    return {r["ean"]: r["quantity"] for r in rows.data}


def laad_dbo_bestelling(winkelnaam: str) -> list:
    """Geeft lijst van DBO-regels voor de winkel."""
    db = get_client()
    rows = _retry(lambda: db.table("dbo_orders")
                             .select("*")
                             .eq("store_name", winkelnaam)
                             .execute())
    return rows.data


def laad_alle_bestellingen() -> dict:
    """Geeft {winkelnaam: {ean: quantity}} voor alle winkels."""
    db = get_client()
    rows = _retry(lambda: db.table("store_orders").select("store_name, ean, quantity").execute())
    result = {}
    for r in rows.data:
        result.setdefault(r["store_name"], {})[r["ean"]] = r["quantity"]
    return result


def laad_alle_dbo_bestellingen() -> dict:
    """Geeft {winkelnaam: [dbo_regels]} voor alle winkels."""
    db = get_client()
    rows = db.table("dbo_orders").select("*").execute()
    result = {}
    for r in rows.data:
        result.setdefault(r["store_name"], []).append(r)
    return result


def bestelling_status() -> list:
    """Geeft per winkel het aantal ingevulde regels én totaal aantal stuks."""
    db = get_client()
    rows = db.table("store_orders") \
             .select("store_name, quantity") \
             .gt("quantity", 0) \
             .execute()
    counts = {}
    stuks = {}
    for r in rows.data:
        counts[r["store_name"]] = counts.get(r["store_name"], 0) + 1
        stuks[r["store_name"]]  = stuks.get(r["store_name"], 0) + (r["quantity"] or 0)
    winkels = db.table("stores").select("name").order("name").execute()
    return [
        {
            "winkel": w["name"],
            "regels": counts.get(w["name"], 0),
            "stuks":  stuks.get(w["name"], 0),
        }
        for w in winkels.data
    ]


# ─── Bestellingen opslaan ─────────────────────────────────────────────────────
def sla_bestelling_op(winkelnaam: str, orders: dict):
    """
    Sla bestellingen op. orders = {ean: quantity}
    Nul-regels worden verwijderd.
    """
    db = get_client()
    db.table("store_orders").delete().eq("store_name", winkelnaam).execute()
    rijen = [
        {"store_name": winkelnaam, "ean": ean, "quantity": qty}
        for ean, qty in orders.items()
        if qty and qty > 0
    ]
    if rijen:
        db.table("store_orders").insert(rijen).execute()
    # Status bijwerken: winkel heeft besteld
    update_order_status(winkelnaam, "besteld")


def sla_dbo_op(winkelnaam: str, dbo_regels: list):
    """
    Sla DBO-regels op. dbo_regels = [{sectie, artikel, quantity}]
    """
    db = get_client()
    db.table("dbo_orders").delete().eq("store_name", winkelnaam).execute()
    rijen = [
        {"store_name": winkelnaam, "sectie": r["sectie"],
         "artikel": r["artikel"], "quantity": r["quantity"]}
        for r in dbo_regels
        if r.get("quantity", 0) > 0 and r.get("artikel", "").strip()
    ]
    if rijen:
        db.table("dbo_orders").insert(rijen).execute()


# ─── SAP data ─────────────────────────────────────────────────────────────────
def sla_sap_op(winkelnaam: str, sap_data: list):
    """sap_data = [{ean, artikel, stuks_verkocht, voorraad_centraal}]"""
    db = get_client()
    # Dedupleer op EAN (zelfde EAN in meerdere secties samenvoegen)
    gezien = {}
    for r in sap_data:
        ean = r.get("ean")
        if ean not in gezien:
            gezien[ean] = {"store_name": winkelnaam, **r}
        else:
            gezien[ean]["stuks_verkocht"] = (
                gezien[ean].get("stuks_verkocht", 0) + r.get("stuks_verkocht", 0)
            )
    rijen = list(gezien.values())
    if rijen:
        db.table("sap_data").upsert(
            rijen, on_conflict="store_name,ean"
        ).execute()
        nieuwe_eans = [r["ean"] for r in rijen]
        db.table("sap_data") \
          .delete() \
          .eq("store_name", winkelnaam) \
          .not_.in_("ean", nieuwe_eans) \
          .execute()
    else:
        db.table("sap_data").delete().eq("store_name", winkelnaam).execute()


def laad_sap(winkelnaam: str) -> dict:
    """Geeft {ean: {stuks_verkocht, voorraad_centraal, artikel}} voor een winkel."""
    db = get_client()
    rows = db.table("sap_data").select("*").eq("store_name", winkelnaam).execute()
    return {r["ean"]: r for r in rows.data}


def laad_alle_sap() -> dict:
    """Geeft {winkelnaam: {ean: sap_dict}} voor alle winkels."""
    db = get_client()
    rows = db.table("sap_data").select("*").execute()
    result = {}
    for r in rows.data:
        result.setdefault(r["store_name"], {})[r["ean"]] = r
    return result


# ─── Piklijst-correcties ──────────────────────────────────────────────────────
def sla_piklijst_correcties_op(winkelnaam: str, artikelen_lijst: list):
    """
    Sla piklijst-data op als startpunt voor correcties.
    artikelen_lijst = output van bouw_artikellijst()
    Overschrijft bestaande correcties voor deze winkel.
    """
    db = get_client()
    db.table("piklijst_correcties").delete().eq("winkelnaam", winkelnaam).execute()
    rijen = []
    for art in artikelen_lijst:
        totaal = (art.get("besteld") or 0) + (art.get("sap") or 0)
        if totaal <= 0:
            continue
        rijen.append({
            "winkelnaam":        winkelnaam,
            "ean":               art.get("ean") or None,
            "artikel":           art.get("artikel") or "",
            "sectie":            art.get("sectie") or "",
            "pad_code":          art.get("pad_code") or "",
            "piklijst_aantal":   totaal,
            "definitief_aantal": totaal,
        })
    if rijen:
        db.table("piklijst_correcties").insert(rijen).execute()


def laad_piklijst_correcties(winkelnaam: str) -> list:
    """Geeft correctie-regels voor een winkel."""
    db = get_client()
    rows = _retry(lambda: db.table("piklijst_correcties")
                             .select("*")
                             .eq("winkelnaam", winkelnaam)
                             .order("pad_code")
                             .order("artikel")
                             .execute())
    return rows.data


def sla_definitief_op(winkelnaam: str, correcties: list):
    """
    Sla definitieve aantallen op.
    correcties = [{id, definitief_aantal}]
    """
    db = get_client()
    for c in correcties:
        db.table("piklijst_correcties") \
          .update({"definitief_aantal": c["definitief_aantal"]}) \
          .eq("id", c["id"]) \
          .eq("winkelnaam", winkelnaam) \
          .execute()


def laad_winkels_met_correcties() -> list:
    """Geeft lijst van winkelnamen die correctie-regels hebben."""
    db = get_client()
    rows = _retry(lambda: db.table("piklijst_correcties")
                             .select("winkelnaam")
                             .execute())
    namen = sorted({r["winkelnaam"] for r in rows.data})
    return namen


# ─── Orderhistoriek ───────────────────────────────────────────────────────────
def sla_order_history_op(winkelnaam: str, artikelen: list):
    """
    Sla een snapshot op van de gegenereerde piklijst.
    Wordt aangeroepen vanuit 2_Beheer.py bij het genereren van piklijsten.
    artikelen = output van bouw_artikellijst()
    """
    db = get_client()
    nu = datetime.datetime.now()
    weeknummer = nu.isocalendar()[1]
    jaar = nu.year
    totaal_stuks  = sum((a.get("besteld") or 0) + (a.get("sap") or 0) for a in artikelen)
    totaal_regels = len([a for a in artikelen if ((a.get("besteld") or 0) + (a.get("sap") or 0)) > 0])
    # Compacte snapshot — alleen noodzakelijke velden
    snapshot = [
        {
            "ean":     a.get("ean"),
            "artikel": a.get("artikel"),
            "sectie":  a.get("sectie"),
            "pad":     a.get("pad_code"),
            "besteld": a.get("besteld") or 0,
            "sap":     a.get("sap") or 0,
            "totaal":  (a.get("besteld") or 0) + (a.get("sap") or 0),
        }
        for a in artikelen
        if ((a.get("besteld") or 0) + (a.get("sap") or 0)) > 0
    ]
    db.table("order_history").insert({
        "winkelnaam":    winkelnaam,
        "datum":         nu.isoformat(),
        "weeknummer":    weeknummer,
        "jaar":          jaar,
        "totaal_stuks":  totaal_stuks,
        "totaal_regels": totaal_regels,
        "artikelen":     snapshot,
    }).execute()


def laad_order_history(winkelnaam: str = None, limit: int = 100) -> list:
    """
    Laad orderhistoriek (zonder artikelen-detail, voor overzicht).
    Optioneel gefilterd op winkel.
    """
    db = get_client()
    query = (
        db.table("order_history")
          .select("id, winkelnaam, datum, weeknummer, jaar, totaal_stuks, totaal_regels")
          .order("datum", desc=True)
          .limit(limit)
    )
    if winkelnaam:
        query = query.eq("winkelnaam", winkelnaam)
    rows = _retry(lambda: query.execute())
    return rows.data


def laad_history_detail(history_id: int) -> dict:
    """Laad de volledige snapshot (inclusief artikelen) voor één historiek-regel."""
    db = get_client()
    rows = _retry(lambda: db.table("order_history")
                             .select("*")
                             .eq("id", history_id)
                             .execute())
    return rows.data[0] if rows.data else {}


def wis_order_history(winkelnaam: str = None, voor_datum: str = None):
    """
    Wis historiek-regels.
    - winkelnaam: alleen voor deze winkel (None = alle winkels)
    - voor_datum: alleen regels vóór deze datum (ISO-string, bijv. '2026-09-01')
    Beide filters tegelijk zijn mogelijk.
    """
    db = get_client()
    query = db.table("order_history").delete()
    if winkelnaam:
        query = query.eq("winkelnaam", winkelnaam)
    if voor_datum:
        query = query.lt("datum", voor_datum)
    if not winkelnaam and not voor_datum:
        # Veiligheidscheck: voorkom dat je per ongeluk alles wist zonder filter
        query = query.neq("id", 0)
    query.execute()


# ─── Order-status (terugkoppeling aan winkels) ────────────────────────────────
def update_order_status(winkelnaam: str, status: str):
    """
    Zet de status voor een winkel.
    Waarden: 'geen_bestelling' | 'besteld' | 'piklijst_klaar' | 'pakket_onderweg'
    """
    db = get_client()
    db.table("order_status").upsert({
        "winkelnaam": winkelnaam,
        "status":     status,
        "bijgewerkt": datetime.datetime.now().isoformat(),
    }, on_conflict="winkelnaam").execute()


def laad_order_statussen() -> dict:
    """Geeft {winkelnaam: {status, bijgewerkt}} voor alle winkels."""
    db = get_client()
    rows = _retry(lambda: db.table("order_status").select("*").execute())
    return {r["winkelnaam"]: r for r in rows.data}


def laad_order_status(winkelnaam: str) -> str:
    """Geeft de huidige status voor één winkel."""
    db = get_client()
    rows = _retry(lambda: db.table("order_status")
                             .select("status")
                             .eq("winkelnaam", winkelnaam)
                             .execute())
    if rows.data:
        return rows.data[0]["status"]
    return "geen_bestelling"


# ─── Reset ───────────────────────────────────────────────────────────────────
def reset_alle_bestellingen():
    """Verwijder alle bestellingen van alle winkels."""
    db = get_client()
    db.table("store_orders").delete().neq("id", 0).execute()
    db.table("dbo_orders").delete().neq("id", 0).execute()


def reset_winkel_bestellingen(winkel_namen: list):
    """Verwijder bestellingen van geselecteerde winkels en reset hun status."""
    db = get_client()
    for naam in winkel_namen:
        db.table("store_orders").delete().eq("store_name", naam).execute()
        db.table("dbo_orders").delete().eq("store_name", naam).execute()
        update_order_status(naam, "geen_bestelling")


# ─── Winkels ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def laad_winkels() -> list:
    db = get_client()
    rows = _retry(lambda: db.table("stores").select("name, pin").order("name").execute())
    return rows.data


def controleer_pin(winkelnaam: str, pin: str) -> bool:
    try:
        winkels = laad_winkels()
    except Exception:
        st.cache_resource.clear()
        st.cache_data.clear()
        st.error("⚠️ Verbindingsprobleem. Ververs de pagina en probeer opnieuw.")
        return False
    for w in winkels:
        if w["name"].lower() == winkelnaam.lower():
            return w["pin"] == pin
    return False
