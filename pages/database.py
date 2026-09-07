"""
Lion Beddenshop — Supabase database.
Verbindt met de Supabase PostgreSQL database via supabase-py.
Credentials worden geladen vanuit Streamlit Secrets.
"""
import csv
import io
import json
import datetime
import streamlit as st
from supabase import create_client, Client


# ─── Supabase client ──────────────────────────────────────────────────────────
@st.cache_resource
def _sb() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def _data(response) -> list:
    """Haal data op uit Supabase response; geeft lege lijst bij fouten."""
    return response.data or []


# ─── Winkels ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def laad_winkels() -> list:
    resp = _sb().table("stores").select("name, pin").order("name").execute()
    return _data(resp)


def voeg_winkel_toe(name: str, pin: str = ""):
    _sb().table("stores").upsert({"name": name, "pin": pin}, on_conflict="name").execute()
    laad_winkels.clear()


def verwijder_winkel(name: str):
    sb = _sb()
    sb.table("piklijst_correcties").delete().eq("winkelnaam", name).execute()
    sb.table("order_status").delete().eq("winkelnaam", name).execute()
    sb.table("dbo_orders").delete().eq("store_name", name).execute()
    sb.table("store_orders").delete().eq("store_name", name).execute()
    sb.table("sap_data").delete().eq("store_name", name).execute()
    try:
        sb.table("order_buffer").delete().eq("store_name", name).execute()
    except Exception:
        pass
    sb.table("stores").delete().eq("name", name).execute()
    laad_winkels.clear()


def stel_pin_in(winkelnaam: str, pin: str):
    """Stel een per-winkel PIN in (of wis met lege string voor fallback-wachtwoord)."""
    _sb().table("stores").update({"pin": pin}).eq("name", winkelnaam).execute()
    laad_winkels.clear()


def controleer_pin(winkelnaam: str, pin: str) -> bool:
    for w in laad_winkels():
        if w["name"].lower() == winkelnaam.lower():
            return w["pin"] == pin
    return False


# ─── Artikelen ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def laad_artikelen() -> list:
    # Supabase heeft standaard een limit van 1000 rijen; haal alles op in batches
    alle = []
    offset = 0
    batch = 1000
    while True:
        resp = (
            _sb().table("articles")
            .select("ean, artikel, sectie, volgorde, pad_code")
            .order("volgorde")
            .order("artikel")
            .range(offset, offset + batch - 1)
            .execute()
        )
        rijen = _data(resp)
        alle.extend(rijen)
        if len(rijen) < batch:
            break
        offset += batch
    return alle


def update_pad_codes(pad_codes: dict):
    sb = _sb()
    bijgewerkt = 0
    for ean, pad in pad_codes.items():
        if pad:
            sb.table("articles").update({"pad_code": pad}).eq("ean", ean).execute()
            bijgewerkt += 1
    laad_artikelen.clear()
    return bijgewerkt


def importeer_artikelen_csv(bestandspad: str, scheidingsteken: str = ";"):
    """
    Importeer artikelen vanuit CSV-bestandspad.
    Verwachte kolommen: ean, artikel, sectie, volgorde, pad_code
    """
    with open(bestandspad, newline="", encoding="utf-8-sig") as f:
        lezer = csv.DictReader(f, delimiter=scheidingsteken)
        ingevoerd = _importeer_artikelen_rows(lezer)
    laad_artikelen.clear()
    return ingevoerd


def importeer_artikelen_bytes(bestand_bytes: bytes, scheidingsteken: str = ";") -> int:
    """
    Importeer artikelen vanuit geüploade CSV-bytes (voor Streamlit file_uploader).
    Probeert UTF-8 met BOM, daarna latin-1 als fallback.
    """
    try:
        tekst = bestand_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        tekst = bestand_bytes.decode("latin-1")
    lezer = csv.DictReader(io.StringIO(tekst), delimiter=scheidingsteken)
    ingevoerd = _importeer_artikelen_rows(lezer)
    laad_artikelen.clear()
    return ingevoerd


def _importeer_artikelen_rows(lezer) -> int:
    """Gemeenschappelijke logica voor CSV-import vanuit een DictReader."""
    sb = _sb()
    rijen = []
    for rij in lezer:
        ean = (rij.get("ean") or rij.get("EAN") or "").strip()
        if not ean:
            continue
        vol = (rij.get("volgorde") or "").strip()
        rijen.append({
            "ean":      ean,
            "artikel":  (rij.get("artikel") or rij.get("Artikel") or "").strip(),
            "sectie":   (rij.get("sectie")  or rij.get("Sectie")  or "").strip(),
            "volgorde": int(vol) if vol.isdigit() else 9999,
            "pad_code": (rij.get("pad_code") or rij.get("Pad") or "").strip(),
        })
    if rijen:
        # Upsert in batches van 500
        for i in range(0, len(rijen), 500):
            sb.table("articles").upsert(rijen[i:i+500], on_conflict="ean").execute()
    return len(rijen)


# ─── Bestellingen lezen ───────────────────────────────────────────────────────
def laad_bestelling(winkelnaam: str) -> dict:
    resp = (
        _sb().table("store_orders")
        .select("ean, quantity")
        .eq("store_name", winkelnaam)
        .execute()
    )
    return {r["ean"]: r["quantity"] for r in _data(resp)}


def laad_dbo_bestelling(winkelnaam: str) -> list:
    resp = (
        _sb().table("dbo_orders")
        .select("*")
        .eq("store_name", winkelnaam)
        .order("sectie")
        .execute()
    )
    return _data(resp)


def laad_alle_bestellingen() -> dict:
    resp = _sb().table("store_orders").select("store_name, ean, quantity").execute()
    result = {}
    for r in _data(resp):
        result.setdefault(r["store_name"], {})[r["ean"]] = r["quantity"]
    return result


def laad_alle_dbo_bestellingen() -> dict:
    resp = (
        _sb().table("dbo_orders")
        .select("*")
        .order("store_name")
        .order("sectie")
        .execute()
    )
    result = {}
    for r in _data(resp):
        result.setdefault(r["store_name"], []).append(r)
    return result


def bestelling_status() -> list:
    sb = _sb()
    orders  = _data(sb.table("store_orders").select("store_name, quantity").gt("quantity", 0).execute())
    winkels = _data(sb.table("stores").select("name").order("name").execute())
    counts = {}
    stuks  = {}
    for r in orders:
        counts[r["store_name"]] = counts.get(r["store_name"], 0) + 1
        stuks[r["store_name"]]  = stuks.get(r["store_name"],  0) + (r["quantity"] or 0)
    return [
        {"winkel": w["name"], "regels": counts.get(w["name"], 0), "stuks": stuks.get(w["name"], 0)}
        for w in winkels
    ]


# ─── Bestellingen opslaan ─────────────────────────────────────────────────────
def sla_bestelling_op(winkelnaam: str, orders: dict):
    sb = _sb()
    sb.table("store_orders").delete().eq("store_name", winkelnaam).execute()
    rijen = [
        {"store_name": winkelnaam, "ean": ean, "quantity": qty}
        for ean, qty in orders.items() if qty and qty > 0
    ]
    if rijen:
        sb.table("store_orders").insert(rijen).execute()
    update_order_status(winkelnaam, "besteld")


def sla_dbo_op(winkelnaam: str, dbo_regels: list):
    sb = _sb()
    sb.table("dbo_orders").delete().eq("store_name", winkelnaam).execute()
    rijen = [
        {"store_name": winkelnaam, "sectie": r["sectie"],
         "artikel": r["artikel"], "quantity": r["quantity"]}
        for r in dbo_regels
        if r.get("quantity", 0) > 0 and r.get("artikel", "").strip()
    ]
    if rijen:
        sb.table("dbo_orders").insert(rijen).execute()


# ─── SAP data ─────────────────────────────────────────────────────────────────
def sla_sap_op(winkelnaam: str, sap_data: list):
    # Dedupliceer op EAN (stuks_verkocht optellen bij duplicaten)
    gezien = {}
    for r in sap_data:
        ean = r.get("ean")
        if ean not in gezien:
            gezien[ean] = dict(r)
        else:
            gezien[ean]["stuks_verkocht"] = (
                gezien[ean].get("stuks_verkocht", 0) + r.get("stuks_verkocht", 0)
            )
    sb = _sb()
    sb.table("sap_data").delete().eq("store_name", winkelnaam).execute()
    rijen = [
        {
            "store_name":        winkelnaam,
            "ean":               v["ean"],
            "artikel":           v.get("artikel", ""),
            "stuks_verkocht":    v.get("stuks_verkocht", 0),
            "voorraad_centraal": v.get("voorraad_centraal", 0),
        }
        for v in gezien.values()
        if v.get("ean")
    ]
    if rijen:
        sb.table("sap_data").insert(rijen).execute()


def laad_sap(winkelnaam: str) -> dict:
    resp = _sb().table("sap_data").select("*").eq("store_name", winkelnaam).execute()
    return {r["ean"]: r for r in _data(resp)}


def laad_alle_sap() -> dict:
    resp = _sb().table("sap_data").select("*").execute()
    result = {}
    for r in _data(resp):
        result.setdefault(r["store_name"], {})[r["ean"]] = r
    return result


# ─── Piklijst-correcties ──────────────────────────────────────────────────────
def sla_piklijst_correcties_op(winkelnaam: str, artikelen_lijst: list):
    sb = _sb()
    sb.table("piklijst_correcties").delete().eq("winkelnaam", winkelnaam).execute()
    rijen = []
    for art in artikelen_lijst:
        totaal = (art.get("besteld") or 0) + (art.get("sap") or 0)
        if totaal <= 0:
            continue
        rijen.append({
            "winkelnaam":        winkelnaam,
            "ean":               art.get("ean"),
            "artikel":           art.get("artikel", ""),
            "sectie":            art.get("sectie", ""),
            "pad_code":          art.get("pad_code", ""),
            "piklijst_aantal":   totaal,
            "definitief_aantal": totaal,
        })
    if rijen:
        sb.table("piklijst_correcties").insert(rijen).execute()


def laad_piklijst_correcties(winkelnaam: str) -> list:
    resp = (
        _sb().table("piklijst_correcties")
        .select("*")
        .eq("winkelnaam", winkelnaam)
        .order("pad_code")
        .order("artikel")
        .execute()
    )
    return _data(resp)


def sla_definitief_op(winkelnaam: str, correcties: list):
    sb = _sb()
    for corr in correcties:
        sb.table("piklijst_correcties").update(
            {"definitief_aantal": corr["definitief_aantal"]}
        ).eq("id", corr["id"]).eq("winkelnaam", winkelnaam).execute()


def laad_winkels_met_correcties() -> list:
    resp = (
        _sb().table("piklijst_correcties")
        .select("winkelnaam")
        .order("winkelnaam")
        .execute()
    )
    gezien = []
    for r in _data(resp):
        if r["winkelnaam"] not in gezien:
            gezien.append(r["winkelnaam"])
    return gezien


# ─── Orderhistoriek ───────────────────────────────────────────────────────────
def sla_order_history_op(winkelnaam: str, artikelen: list):
    nu = datetime.datetime.now()
    snapshot = [
        {"ean": a.get("ean"), "artikel": a.get("artikel"), "sectie": a.get("sectie"),
         "pad": a.get("pad_code"), "besteld": a.get("besteld") or 0,
         "sap": a.get("sap") or 0,
         "totaal": (a.get("besteld") or 0) + (a.get("sap") or 0)}
        for a in artikelen if ((a.get("besteld") or 0) + (a.get("sap") or 0)) > 0
    ]
    _sb().table("order_history").insert({
        "winkelnaam":    winkelnaam,
        "datum":         nu.isoformat(),
        "weeknummer":    nu.isocalendar()[1],
        "jaar":          nu.year,
        "totaal_stuks":  sum(s["totaal"] for s in snapshot),
        "totaal_regels": len(snapshot),
        "artikelen":     json.dumps(snapshot),
    }).execute()


def laad_order_history(winkelnaam: str = None, limit: int = 100) -> list:
    q = (
        _sb().table("order_history")
        .select("id, winkelnaam, datum, weeknummer, jaar, totaal_stuks, totaal_regels")
        .order("datum", desc=True)
        .limit(limit)
    )
    if winkelnaam:
        q = q.eq("winkelnaam", winkelnaam)
    return _data(q.execute())


def laad_history_detail(history_id: int) -> dict:
    resp = _sb().table("order_history").select("*").eq("id", history_id).execute()
    rows = _data(resp)
    if not rows:
        return {}
    r = rows[0]
    try:
        r["artikelen"] = json.loads(r.get("artikelen") or "[]")
    except Exception:
        r["artikelen"] = []
    return r


def wis_order_history(winkelnaam: str = None, voor_datum: str = None):
    q = _sb().table("order_history").delete()
    if winkelnaam:
        q = q.eq("winkelnaam", winkelnaam)
    if voor_datum:
        q = q.lt("datum", voor_datum)
    if not winkelnaam and not voor_datum:
        # Verwijder alles — Supabase vereist een filter, gebruik neq op een veld dat altijd gevuld is
        q = q.neq("id", 0)
    q.execute()


# ─── Order-status ─────────────────────────────────────────────────────────────
def update_order_status(winkelnaam: str, status: str):
    nu = datetime.datetime.now().isoformat()
    _sb().table("order_status").upsert(
        {"winkelnaam": winkelnaam, "status": status, "bijgewerkt": nu},
        on_conflict="winkelnaam"
    ).execute()


def laad_order_statussen() -> dict:
    resp = _sb().table("order_status").select("*").execute()
    return {r["winkelnaam"]: r for r in _data(resp)}


def laad_order_status(winkelnaam: str) -> str:
    resp = (
        _sb().table("order_status")
        .select("status")
        .eq("winkelnaam", winkelnaam)
        .execute()
    )
    rows = _data(resp)
    return rows[0]["status"] if rows else "geen_bestelling"


def laad_order_status_info(winkelnaam: str) -> dict:
    resp = (
        _sb().table("order_status")
        .select("status, bijgewerkt")
        .eq("winkelnaam", winkelnaam)
        .execute()
    )
    rows = _data(resp)
    return rows[0] if rows else {"status": "geen_bestelling", "bijgewerkt": None}


# ─── Reset ────────────────────────────────────────────────────────────────────
def reset_winkel_bestellingen(winkel_namen: list):
    sb = _sb()
    for naam in winkel_namen:
        sb.table("store_orders").delete().eq("store_name", naam).execute()
        sb.table("dbo_orders").delete().eq("store_name", naam).execute()
    for naam in winkel_namen:
        update_order_status(naam, "geen_bestelling")


# ─── Reset + buffer automatisch laden ────────────────────────────────────────
def reset_en_laad_buffer(winkel_namen: list):
    """
    Reset bestellingen en laad buffer automatisch als nieuwe actieve bestelling.
    - Als er een buffer is → zet die als actieve bestelling (status: besteld)
    - Als er geen buffer is → zet status op geen_bestelling
    """
    sb = _sb()
    for naam in winkel_namen:
        buffer = laad_buffer(naam)
        sb.table("store_orders").delete().eq("store_name", naam).execute()
        sb.table("dbo_orders").delete().eq("store_name", naam).execute()
        if buffer:
            rijen = [
                {"store_name": naam, "ean": ean, "quantity": qty}
                for ean, qty in buffer.items() if qty and qty > 0
            ]
            if rijen:
                sb.table("store_orders").insert(rijen).execute()
            sb.table("order_buffer").delete().eq("store_name", naam).execute()
            update_order_status(naam, "besteld")
        else:
            update_order_status(naam, "geen_bestelling")


# ─── Order-buffer (vorige bestelling onthouden na wissen) ─────────────────────
def sla_buffer_op(winkelnaam: str, orders: dict):
    """Sla huidige bestellaantallen op als buffer, voordat de bestelling wordt gewist."""
    try:
        sb = _sb()
        sb.table("order_buffer").delete().eq("store_name", winkelnaam).execute()
        rijen = [
            {"store_name": winkelnaam, "ean": ean, "quantity": qty}
            for ean, qty in orders.items() if qty and qty > 0
        ]
        if rijen:
            sb.table("order_buffer").insert(rijen).execute()
    except Exception:
        pass  # order_buffer tabel is optioneel


def laad_buffer(winkelnaam: str) -> dict:
    """Laad gebufferde bestelling voor een winkel (aantallen van vorige ronde)."""
    try:
        resp = (
            _sb().table("order_buffer")
            .select("ean, quantity")
            .eq("store_name", winkelnaam)
            .gt("quantity", 0)
            .execute()
        )
        return {r["ean"]: r["quantity"] for r in _data(resp)}
    except Exception:
        return {}


def wis_buffer(winkelnaam: str):
    """Verwijder de buffer nadat de winkel een nieuwe bestelling heeft opgeslagen."""
    try:
        _sb().table("order_buffer").delete().eq("store_name", winkelnaam).execute()
    except Exception:
        pass
