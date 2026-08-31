"""
Supabase database verbinding en helpers.
"""
import time
import streamlit as st
from supabase import create_client, Client


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
        resultaat = db.table("articles").select("*").order("volgorde").range(offset, offset + 999).execute()
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
    rows = db.table("store_orders") \
             .select("ean, quantity") \
             .eq("store_name", winkelnaam) \
             .execute()
    return {r["ean"]: r["quantity"] for r in rows.data}


def laad_dbo_bestelling(winkelnaam: str) -> list:
    """Geeft lijst van DBO-regels voor de winkel."""
    db = get_client()
    rows = db.table("dbo_orders") \
             .select("*") \
             .eq("store_name", winkelnaam) \
             .execute()
    return rows.data


def laad_alle_bestellingen() -> dict:
    """Geeft {winkelnaam: {ean: quantity}} voor alle winkels."""
    db = get_client()
    rows = db.table("store_orders").select("store_name, ean, quantity").execute()
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
    """Geeft per winkel het aantal ingevulde regels."""
    db = get_client()
    rows = db.table("store_orders") \
             .select("store_name, quantity") \
             .gt("quantity", 0) \
             .execute()
    counts = {}
    for r in rows.data:
        counts[r["store_name"]] = counts.get(r["store_name"], 0) + 1
    winkels = db.table("stores").select("name").order("name").execute()
    return [
        {"winkel": w["name"], "regels": counts.get(w["name"], 0)}
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
            # Stuks optellen bij duplicaat EAN
            gezien[ean]["stuks_verkocht"] = (
                gezien[ean].get("stuks_verkocht", 0) + r.get("stuks_verkocht", 0)
            )
    rijen = list(gezien.values())
    if rijen:
        # Upsert: insert of update als (store_name, ean) al bestaat
        db.table("sap_data").upsert(
            rijen, on_conflict="store_name,ean"
        ).execute()
        # Verwijder daarna regels die niet meer in de nieuwe upload zitten
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


# ─── Reset ───────────────────────────────────────────────────────────────────

def reset_alle_bestellingen():
    """Verwijder alle bestellingen van alle winkels."""
    db = get_client()
    db.table("store_orders").delete().neq("id", 0).execute()
    db.table("dbo_orders").delete().neq("id", 0).execute()


def reset_winkel_bestellingen(winkel_namen: list):
    """Verwijder bestellingen van geselecteerde winkels."""
    db = get_client()
    for naam in winkel_namen:
        db.table("store_orders").delete().eq("store_name", naam).execute()
        db.table("dbo_orders").delete().eq("store_name", naam).execute()


# ─── Winkels ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def laad_winkels() -> list:
    db = get_client()
    rows = db.table("stores").select("name, pin").order("name").execute()
    return rows.data


def controleer_pin(winkelnaam: str, pin: str) -> bool:
    try:
        winkels = laad_winkels()
    except Exception:
        # Verbindingsfout: cache leegmaken zodat de volgende poging opnieuw probeert
        st.cache_resource.clear()
        st.cache_data.clear()
        st.error("⚠️ Verbindingsprobleem. Ververs de pagina en probeer opnieuw.")
        return False
    for w in winkels:
        if w["name"].lower() == winkelnaam.lower():
            return w["pin"] == pin
    return False
