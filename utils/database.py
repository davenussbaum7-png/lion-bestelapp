"""
Lion Beddenshop — Lokale SQLite database.
Alle data wordt opgeslagen in lion_app.db naast app.py.
Geen Supabase of internetverbinding nodig voor de data.
"""
import json
import os
import sqlite3
import datetime
import streamlit as st


# ─── Pad naar de database ─────────────────────────────────────────────────────
def _db_pad() -> str:
    basis = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(basis, "lion_app.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_db_pad(), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]


# ─── Database aanmaken ────────────────────────────────────────────────────────
def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS stores (
            name TEXT PRIMARY KEY,
            pin  TEXT
        );
        CREATE TABLE IF NOT EXISTS articles (
            ean      TEXT PRIMARY KEY,
            artikel  TEXT,
            sectie   TEXT,
            volgorde INTEGER DEFAULT 9999,
            pad_code TEXT
        );
        CREATE TABLE IF NOT EXISTS store_orders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            store_name TEXT NOT NULL,
            ean        TEXT NOT NULL,
            quantity   INTEGER DEFAULT 0,
            UNIQUE(store_name, ean)
        );
        CREATE TABLE IF NOT EXISTS dbo_orders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            store_name TEXT NOT NULL,
            sectie     TEXT,
            artikel    TEXT,
            quantity   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sap_data (
            store_name        TEXT NOT NULL,
            ean               TEXT NOT NULL,
            artikel           TEXT,
            stuks_verkocht    INTEGER DEFAULT 0,
            voorraad_centraal INTEGER DEFAULT 0,
            PRIMARY KEY (store_name, ean)
        );
        CREATE TABLE IF NOT EXISTS piklijst_correcties (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            winkelnaam        TEXT NOT NULL,
            ean               TEXT,
            artikel           TEXT,
            sectie            TEXT,
            pad_code          TEXT,
            piklijst_aantal   INTEGER DEFAULT 0,
            definitief_aantal INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS order_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            winkelnaam    TEXT NOT NULL,
            datum         TEXT NOT NULL,
            weeknummer    INTEGER,
            jaar          INTEGER,
            totaal_stuks  INTEGER DEFAULT 0,
            totaal_regels INTEGER DEFAULT 0,
            artikelen     TEXT DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS order_status (
            winkelnaam TEXT PRIMARY KEY,
            status     TEXT DEFAULT 'geen_bestelling',
            bijgewerkt TEXT
        );
        CREATE TABLE IF NOT EXISTS order_buffer (
            store_name TEXT NOT NULL,
            ean        TEXT NOT NULL,
            quantity   INTEGER DEFAULT 0,
            PRIMARY KEY (store_name, ean)
        );
        """)

init_db()


# ─── Winkels ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def laad_winkels() -> list:
    with _conn() as c:
        return _rows(c.execute("SELECT name, pin FROM stores ORDER BY name"))


def voeg_winkel_toe(name: str, pin: str = ""):
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO stores (name, pin) VALUES (?, ?)", (name, pin))
    laad_winkels.clear()


def verwijder_winkel(name: str):
    with _conn() as c:
        c.execute("DELETE FROM stores WHERE name = ?", (name,))
        c.execute("DELETE FROM store_orders WHERE store_name = ?", (name,))
        c.execute("DELETE FROM dbo_orders WHERE store_name = ?", (name,))
        c.execute("DELETE FROM order_status WHERE winkelnaam = ?", (name,))
    laad_winkels.clear()


def controleer_pin(winkelnaam: str, pin: str) -> bool:
    for w in laad_winkels():
        if w["name"].lower() == winkelnaam.lower():
            return w["pin"] == pin
    return False


# ─── Artikelen ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def laad_artikelen() -> list:
    with _conn() as c:
        return _rows(c.execute(
            "SELECT ean, artikel, sectie, volgorde, pad_code "
            "FROM articles ORDER BY volgorde, artikel"
        ))


def update_pad_codes(pad_codes: dict):
    with _conn() as c:
        for ean, pad in pad_codes.items():
            if pad:
                c.execute("UPDATE articles SET pad_code = ? WHERE ean = ?", (pad, ean))
    laad_artikelen.clear()
    return len([p for p in pad_codes.values() if p])


def importeer_artikelen_csv(bestandspad: str, scheidingsteken: str = ";"):
    """
    Importeer artikelen vanuit CSV. Verwachte kolommen: ean, artikel, sectie, volgorde, pad_code
    Geeft het aantal geimporteerde regels terug.
    """
    import csv
    ingevoerd = 0
    with open(bestandspad, newline="", encoding="utf-8-sig") as f:
        lezer = csv.DictReader(f, delimiter=scheidingsteken)
        with _conn() as c:
            for rij in lezer:
                ean = (rij.get("ean") or rij.get("EAN") or "").strip()
                if not ean:
                    continue
                vol = rij.get("volgorde", "").strip()
                c.execute("""
                    INSERT INTO articles (ean, artikel, sectie, volgorde, pad_code)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(ean) DO UPDATE SET
                        artikel  = excluded.artikel,
                        sectie   = excluded.sectie,
                        volgorde = excluded.volgorde,
                        pad_code = excluded.pad_code
                """, (
                    ean,
                    (rij.get("artikel") or rij.get("Artikel") or "").strip(),
                    (rij.get("sectie")  or rij.get("Sectie")  or "").strip(),
                    int(vol) if vol.isdigit() else 9999,
                    (rij.get("pad_code") or rij.get("Pad") or "").strip(),
                ))
                ingevoerd += 1
    laad_artikelen.clear()
    return ingevoerd


# ─── Bestellingen lezen ───────────────────────────────────────────────────────
def laad_bestelling(winkelnaam: str) -> dict:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT ean, quantity FROM store_orders WHERE store_name = ?", (winkelnaam,)
        ))
    return {r["ean"]: r["quantity"] for r in rows}


def laad_dbo_bestelling(winkelnaam: str) -> list:
    with _conn() as c:
        return _rows(c.execute(
            "SELECT * FROM dbo_orders WHERE store_name = ? ORDER BY sectie", (winkelnaam,)
        ))


def laad_alle_bestellingen() -> dict:
    with _conn() as c:
        rows = _rows(c.execute("SELECT store_name, ean, quantity FROM store_orders"))
    result = {}
    for r in rows:
        result.setdefault(r["store_name"], {})[r["ean"]] = r["quantity"]
    return result


def laad_alle_dbo_bestellingen() -> dict:
    with _conn() as c:
        rows = _rows(c.execute("SELECT * FROM dbo_orders ORDER BY store_name, sectie"))
    result = {}
    for r in rows:
        result.setdefault(r["store_name"], []).append(r)
    return result


def bestelling_status() -> list:
    with _conn() as c:
        orders  = _rows(c.execute("SELECT store_name, quantity FROM store_orders WHERE quantity > 0"))
        winkels = _rows(c.execute("SELECT name FROM stores ORDER BY name"))
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
    with _conn() as c:
        c.execute("DELETE FROM store_orders WHERE store_name = ?", (winkelnaam,))
        rijen = [(winkelnaam, ean, qty) for ean, qty in orders.items() if qty and qty > 0]
        if rijen:
            c.executemany(
                "INSERT INTO store_orders (store_name, ean, quantity) VALUES (?, ?, ?)", rijen
            )
    update_order_status(winkelnaam, "besteld")


def sla_dbo_op(winkelnaam: str, dbo_regels: list):
    with _conn() as c:
        c.execute("DELETE FROM dbo_orders WHERE store_name = ?", (winkelnaam,))
        rijen = [
            (winkelnaam, r["sectie"], r["artikel"], r["quantity"])
            for r in dbo_regels
            if r.get("quantity", 0) > 0 and r.get("artikel", "").strip()
        ]
        if rijen:
            c.executemany(
                "INSERT INTO dbo_orders (store_name, sectie, artikel, quantity) VALUES (?, ?, ?, ?)",
                rijen
            )


# ─── SAP data ─────────────────────────────────────────────────────────────────
def sla_sap_op(winkelnaam: str, sap_data: list):
    gezien = {}
    for r in sap_data:
        ean = r.get("ean")
        if ean not in gezien:
            gezien[ean] = dict(r)
        else:
            gezien[ean]["stuks_verkocht"] = (
                gezien[ean].get("stuks_verkocht", 0) + r.get("stuks_verkocht", 0)
            )
    with _conn() as c:
        c.execute("DELETE FROM sap_data WHERE store_name = ?", (winkelnaam,))
        rijen = [
            (winkelnaam, v["ean"], v.get("artikel", ""),
             v.get("stuks_verkocht", 0), v.get("voorraad_centraal", 0))
            for v in gezien.values()
        ]
        if rijen:
            c.executemany(
                "INSERT OR REPLACE INTO sap_data "
                "(store_name, ean, artikel, stuks_verkocht, voorraad_centraal) VALUES (?, ?, ?, ?, ?)",
                rijen
            )


def laad_sap(winkelnaam: str) -> dict:
    with _conn() as c:
        rows = _rows(c.execute("SELECT * FROM sap_data WHERE store_name = ?", (winkelnaam,)))
    return {r["ean"]: r for r in rows}


def laad_alle_sap() -> dict:
    with _conn() as c:
        rows = _rows(c.execute("SELECT * FROM sap_data"))
    result = {}
    for r in rows:
        result.setdefault(r["store_name"], {})[r["ean"]] = r
    return result


# ─── Piklijst-correcties ──────────────────────────────────────────────────────
def sla_piklijst_correcties_op(winkelnaam: str, artikelen_lijst: list):
    with _conn() as c:
        c.execute("DELETE FROM piklijst_correcties WHERE winkelnaam = ?", (winkelnaam,))
        rijen = []
        for art in artikelen_lijst:
            totaal = (art.get("besteld") or 0) + (art.get("sap") or 0)
            if totaal <= 0:
                continue
            rijen.append((
                winkelnaam, art.get("ean"), art.get("artikel", ""),
                art.get("sectie", ""), art.get("pad_code", ""), totaal, totaal,
            ))
        if rijen:
            c.executemany(
                "INSERT INTO piklijst_correcties "
                "(winkelnaam, ean, artikel, sectie, pad_code, piklijst_aantal, definitief_aantal) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rijen
            )


def laad_piklijst_correcties(winkelnaam: str) -> list:
    with _conn() as c:
        return _rows(c.execute(
            "SELECT * FROM piklijst_correcties WHERE winkelnaam = ? ORDER BY pad_code, artikel",
            (winkelnaam,)
        ))


def sla_definitief_op(winkelnaam: str, correcties: list):
    with _conn() as c:
        for corr in correcties:
            c.execute(
                "UPDATE piklijst_correcties SET definitief_aantal = ? WHERE id = ? AND winkelnaam = ?",
                (corr["definitief_aantal"], corr["id"], winkelnaam)
            )


def laad_winkels_met_correcties() -> list:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT DISTINCT winkelnaam FROM piklijst_correcties ORDER BY winkelnaam"
        ))
    return [r["winkelnaam"] for r in rows]


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
    totaal_stuks  = sum(s["totaal"] for s in snapshot)
    totaal_regels = len(snapshot)
    with _conn() as c:
        c.execute(
            "INSERT INTO order_history "
            "(winkelnaam, datum, weeknummer, jaar, totaal_stuks, totaal_regels, artikelen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (winkelnaam, nu.isoformat(), nu.isocalendar()[1], nu.year,
             totaal_stuks, totaal_regels, json.dumps(snapshot))
        )


def laad_order_history(winkelnaam: str = None, limit: int = 100) -> list:
    sql = ("SELECT id, winkelnaam, datum, weeknummer, jaar, totaal_stuks, totaal_regels "
           "FROM order_history")
    params = []
    if winkelnaam:
        sql += " WHERE winkelnaam = ?"
        params.append(winkelnaam)
    sql += " ORDER BY datum DESC LIMIT ?"
    params.append(limit)
    with _conn() as c:
        return _rows(c.execute(sql, params))


def laad_history_detail(history_id: int) -> dict:
    with _conn() as c:
        rows = _rows(c.execute("SELECT * FROM order_history WHERE id = ?", (history_id,)))
    if not rows:
        return {}
    r = rows[0]
    try:
        r["artikelen"] = json.loads(r.get("artikelen") or "[]")
    except Exception:
        r["artikelen"] = []
    return r


def wis_order_history(winkelnaam: str = None, voor_datum: str = None):
    sql = "DELETE FROM order_history WHERE 1=1"
    params = []
    if winkelnaam:
        sql += " AND winkelnaam = ?"
        params.append(winkelnaam)
    if voor_datum:
        sql += " AND datum < ?"
        params.append(voor_datum)
    with _conn() as c:
        c.execute(sql, params)


# ─── Order-status ─────────────────────────────────────────────────────────────
def update_order_status(winkelnaam: str, status: str):
    nu = datetime.datetime.now().isoformat()
    with _conn() as c:
        c.execute(
            "INSERT INTO order_status (winkelnaam, status, bijgewerkt) VALUES (?, ?, ?) "
            "ON CONFLICT(winkelnaam) DO UPDATE SET status = excluded.status, bijgewerkt = excluded.bijgewerkt",
            (winkelnaam, status, nu)
        )


def laad_order_statussen() -> dict:
    with _conn() as c:
        rows = _rows(c.execute("SELECT * FROM order_status"))
    return {r["winkelnaam"]: r for r in rows}


def laad_order_status(winkelnaam: str) -> str:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT status FROM order_status WHERE winkelnaam = ?", (winkelnaam,)
        ))
    return rows[0]["status"] if rows else "geen_bestelling"


def laad_order_status_info(winkelnaam: str) -> dict:
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT status, bijgewerkt FROM order_status WHERE winkelnaam = ?", (winkelnaam,)
        ))
    return rows[0] if rows else {"status": "geen_bestelling", "bijgewerkt": None}


# ─── Reset ────────────────────────────────────────────────────────────────────
def reset_alle_bestellingen():
    with _conn() as c:
        c.execute("DELETE FROM store_orders")
        c.execute("DELETE FROM dbo_orders")


def reset_winkel_bestellingen(winkel_namen: list):
    with _conn() as c:
        for naam in winkel_namen:
            c.execute("DELETE FROM store_orders WHERE store_name = ?", (naam,))
            c.execute("DELETE FROM dbo_orders WHERE store_name = ?", (naam,))
    for naam in winkel_namen:
        update_order_status(naam, "geen_bestelling")


# ─── Order-buffer (vorige bestelling onthouden na wissen) ────────────────────
def sla_buffer_op(winkelnaam: str, orders: dict):
    """Sla huidige bestellaantallen op als buffer, voordat de bestelling wordt gewist."""
    with _conn() as c:
        c.execute("DELETE FROM order_buffer WHERE store_name = ?", (winkelnaam,))
        rijen = [(winkelnaam, ean, qty) for ean, qty in orders.items() if qty and qty > 0]
        if rijen:
            c.executemany(
                "INSERT INTO order_buffer (store_name, ean, quantity) VALUES (?, ?, ?)", rijen
            )


def laad_buffer(winkelnaam: str) -> dict:
    """Laad gebufferde bestelling voor een winkel (aantallen van vorige ronde)."""
    with _conn() as c:
        rows = _rows(c.execute(
            "SELECT ean, quantity FROM order_buffer WHERE store_name = ? AND quantity > 0",
            (winkelnaam,)
        ))
    return {r["ean"]: r["quantity"] for r in rows}


def wis_buffer(winkelnaam: str):
    """Verwijder de buffer nadat de winkel een nieuwe bestelling heeft opgeslagen."""
    with _conn() as c:
        c.execute("DELETE FROM order_buffer WHERE store_name = ?", (winkelnaam,))
