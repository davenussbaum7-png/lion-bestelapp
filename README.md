# Lion Beddenshop — Bestelapplicatie (Fase 2)

Streamlit-webapp waarmee winkels online bestellingen invullen en Wouter piklijsten + paklijsten genereert.

---

## Eenmalige setup (± 30 minuten)

### 1. Supabase database aanmaken (gratis)

1. Ga naar [supabase.com](https://supabase.com) → **Start your project** → maak een gratis account
2. Maak een nieuw project aan (kies een naam, bijv. `lion-beddenshop`)
3. Ga naar **SQL Editor** en plak de inhoud van `setup/supabase_schema.sql` → klik **Run**
4. Ga naar **Project Settings → API** en kopieer:
   - **Project URL** (bijv. `https://abcdef.supabase.co`)
   - **anon public key** (de lange sleutel)

### 2. Secrets invullen

Open `.streamlit/secrets.toml` en vul in:
```toml
supabase_url = "https://JOUW-PROJECT.supabase.co"
supabase_key = "JOUW-ANON-KEY"
wouter_wachtwoord = "KiesEenSterkWachtwoord"
```

### 3. Catalogus laden

Zet `Winkel_Invoer_voor_winkels_v15.xlsx` in de map `setup/`.  
Open `setup/laad_catalogus.py` en pas aan:
- `SUPABASE_URL` en `SUPABASE_KEY` (zelfde als hierboven)
- `WINKELS` — vul de echte winkelnamen en PIN-codes in

Voer dan uit:
```bash
pip install -r requirements.txt
python setup/laad_catalogus.py
```

**Let op:** de winkelnamen moeten EXACT overeenkomen met:
- Cel I1 in de WinkelInvoer-formulieren van de winkels
- De `Magazijnnaam` in de SAP-exports

### 4. Lokaal testen

```bash
streamlit run app.py
```

Ga naar `http://localhost:8501` — je ziet het inlogscherm.

### 5. Online zetten (gratis via Streamlit Cloud)

1. Zet alle bestanden in een **privé** GitHub repository
2. Ga naar [share.streamlit.io](https://share.streamlit.io) → koppel je GitHub-account
3. Selecteer de repository → klik **Deploy**
4. Ga naar **Advanced settings → Secrets** en plak de inhoud van `.streamlit/secrets.toml`
5. Klaar — de app krijgt een publieke URL die je met de winkels deelt

> ⚠️ Voeg `.streamlit/secrets.toml` toe aan `.gitignore` zodat wachtwoorden nooit op GitHub komen.

---

## Wekelijkse werkwijze

### Winkels
1. Ga naar de app-URL → kies je winkel → vul PIN in
2. Vul de aantallen in via het bestelformulier
3. Klik **Sla bestelling op** — klaar

### Wouter
1. Log in als beheerder
2. Upload de SAP-exports (alle winkels tegelijk)
3. Klik **Genereer alle piklijsten** → download ZIP
4. Open de piklijsten, corrigeer NIET OP VOORRAAD-regels (pas Totaal aan of zet op 0)
5. Upload de gecorrigeerde piklijsten → klik **Genereer paklijsten** → download ZIP
6. Print de paklijsten af
7. Klik **Wis alle bestellingen** → bevestig → klaar voor volgende week

---

## Mapstructuur

```
lion_webapp/
├── app.py                  ← Startpagina / login
├── pages/
│   ├── 1_Bestellen.py      ← Winkelformulier
│   └── 2_Beheer.py         ← Wouter beheerpagina
├── utils/
│   ├── database.py         ← Supabase verbinding en queries
│   └── genereer.py         ← Piklijst/paklijst generatie logica
├── setup/
│   ├── supabase_schema.sql ← Eenmalig uitvoeren in Supabase SQL Editor
│   └── laad_catalogus.py   ← Eenmalig uitvoeren om artikelen te laden
├── .streamlit/
│   ├── secrets.toml        ← Jouw Supabase-sleutels (NIET in Git zetten!)
│   └── config.toml         ← Thema-instellingen
└── requirements.txt
```
