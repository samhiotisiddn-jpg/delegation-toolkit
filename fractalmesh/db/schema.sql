-- FractalMesh Supabase Schema
-- Run this in your Supabase SQL editor (project: tzdlozmrqhaocccjrwhv)

-- ─────────────────────────────────────────────
-- TRADES: KuCoin arbitrage execution log
-- ─────────────────────────────────────────────
create table if not exists trades (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  pair          text not null,          -- e.g. "BTC-USDT"
  buy_exchange  text not null default 'kucoin',
  sell_exchange text not null default 'kucoin',
  buy_price     numeric(20,8) not null,
  sell_price    numeric(20,8) not null,
  spread_pct    numeric(8,4) not null,  -- percentage spread
  quantity      numeric(20,8) not null,
  pnl_usdt      numeric(20,8),          -- realised P&L
  status        text not null default 'pending'
                  check (status in ('pending','executed','failed','skipped')),
  error         text,
  raw           jsonb                   -- full exchange response
);

create index on trades (created_at desc);
create index on trades (pair, status);

-- ─────────────────────────────────────────────
-- ALERTS: system-wide event log
-- ─────────────────────────────────────────────
create table if not exists alerts (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  source      text not null,    -- 'trading','stripe','system','make'
  level       text not null default 'info'
                check (level in ('info','warn','error','critical')),
  title       text not null,
  body        text,
  slack_sent  boolean not null default false,
  raw         jsonb
);

create index on alerts (created_at desc);
create index on alerts (level, slack_sent);

-- ─────────────────────────────────────────────
-- PRODUCTS: Stripe product catalogue
-- ─────────────────────────────────────────────
create table if not exists products (
  id               uuid primary key default gen_random_uuid(),
  created_at       timestamptz not null default now(),
  stripe_product_id text unique,
  stripe_price_id   text,
  name             text not null,
  description      text,
  price_aud        numeric(10,2) not null,
  active           boolean not null default true,
  metadata         jsonb
);

-- ─────────────────────────────────────────────
-- ORDERS: Stripe payment records
-- ─────────────────────────────────────────────
create table if not exists orders (
  id                  uuid primary key default gen_random_uuid(),
  created_at          timestamptz not null default now(),
  stripe_session_id   text unique,
  stripe_payment_intent text,
  product_id          uuid references products(id),
  customer_email      text,
  amount_aud          numeric(10,2) not null,
  status              text not null default 'pending'
                        check (status in ('pending','paid','failed','refunded')),
  raw                 jsonb
);

create index on orders (created_at desc);
create index on orders (status);

-- ─────────────────────────────────────────────
-- WEBHOOK_EVENTS: Make.com inbound log
-- ─────────────────────────────────────────────
create table if not exists webhook_events (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  source      text not null,   -- 'make','stripe','kucoin'
  event_type  text,
  payload     jsonb not null,
  processed   boolean not null default false
);

create index on webhook_events (created_at desc);
create index on webhook_events (source, processed);

-- ─────────────────────────────────────────────
-- Row-Level Security (enable after setup)
-- ─────────────────────────────────────────────
alter table trades        enable row level security;
alter table alerts        enable row level security;
alter table products      enable row level security;
alter table orders        enable row level security;
alter table webhook_events enable row level security;

-- Service-role bypass (your backend uses service_role key)
create policy "service_role full access on trades"
  on trades for all using (true);
create policy "service_role full access on alerts"
  on alerts for all using (true);
create policy "service_role full access on products"
  on products for all using (true);
create policy "service_role full access on orders"
  on orders for all using (true);
create policy "service_role full access on webhook_events"
  on webhook_events for all using (true);
