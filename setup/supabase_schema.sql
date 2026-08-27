-- Lion Beddenshop — Supabase database schema
-- Voer dit uit in de Supabase SQL Editor (één keer)

-- ─── Winkels ────────────────────────────────────────────────────────────────
create table if not exists stores (
  id   bigint generated always as identity primary key,
  name text unique not null,
  pin  text not null
);

-- ─── Artikelcatalogus ────────────────────────────────────────────────────────
create table if not exists articles (
  id       bigint generated always as identity primary key,
  ean      text unique,
  artikel  text not null,
  sectie   text not null,
  pad_code text default '',
  volgorde integer default 9999
);
create index if not exists idx_articles_ean on articles(ean);
create index if not exists idx_articles_sectie on articles(sectie);

-- ─── Bestellingen (winkels) ──────────────────────────────────────────────────
create table if not exists store_orders (
  id         bigint generated always as identity primary key,
  store_name text not null,
  ean        text not null,
  quantity   integer not null default 0,
  updated_at timestamptz default now(),
  constraint store_orders_unique unique (store_name, ean)
);
create index if not exists idx_orders_store on store_orders(store_name);

-- ─── DBO vrije regels ────────────────────────────────────────────────────────
create table if not exists dbo_orders (
  id         bigint generated always as identity primary key,
  store_name text not null,
  sectie     text not null,
  artikel    text not null,
  quantity   integer not null default 0,
  updated_at timestamptz default now()
);
create index if not exists idx_dbo_store on dbo_orders(store_name);

-- ─── SAP data (wekelijks geüpload door Wouter) ───────────────────────────────
create table if not exists sap_data (
  id                 bigint generated always as identity primary key,
  store_name         text not null,
  ean                text not null,
  artikel            text default '',
  stuks_verkocht     integer not null default 0,
  voorraad_centraal  integer not null default 999,
  groepsnaam         text default '',
  updated_at         timestamptz default now(),
  constraint sap_data_unique unique (store_name, ean)
);
create index if not exists idx_sap_store on sap_data(store_name);

-- ─── Row Level Security (aanbevolen voor productie) ──────────────────────────
-- Zet RLS aan en gebruik service_role key in het setup-script,
-- anon key in de app (read-only voor stores, write via RLS policies).
-- Voor een snelle start kun je RLS uitgeschakeld laten en de anon key gebruiken.
-- Bespreek met Dave welke beveiligingslaag gewenst is.
