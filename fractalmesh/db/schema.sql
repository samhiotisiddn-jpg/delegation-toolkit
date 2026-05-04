-- FractalMesh Supabase Schema v2
-- Run in Supabase SQL editor (project: trvjsivktildvbwpljsb)

-- ─────────────────────────────────────────────
-- LEADS: RSS-ingested items with intent scoring
-- ─────────────────────────────────────────────
create table if not exists leads (
  id           uuid primary key default gen_random_uuid(),
  created_at   timestamptz not null default now(),
  title        text not null,
  url          text,
  source_feed  text,
  summary      text,
  intent_score numeric(6,2) not null default 0,
  tier         text not null default 'basic'
                 check (tier in ('basic','standard','premium')),
  tags         text[],
  synced       boolean not null default false,
  raw          jsonb
);
create index on leads (created_at desc);
create index on leads (intent_score desc);
create index on leads (tier, synced);

-- ─────────────────────────────────────────────
-- AFFILIATES
-- ─────────────────────────────────────────────
create table if not exists affiliates (
  id              uuid primary key default gen_random_uuid(),
  created_at      timestamptz not null default now(),
  name            text not null,
  email           text unique not null,
  affiliate_code  text unique not null,
  api_token       text unique not null,
  commission_rate numeric(4,2) not null default 0.20,
  total_referrals int not null default 0,
  total_revenue   numeric(12,2) not null default 0,
  is_active       boolean not null default true
);
create index on affiliates (affiliate_code);
create index on affiliates (api_token);

-- ─────────────────────────────────────────────
-- CUSTOMERS: paying subscribers
-- ─────────────────────────────────────────────
create table if not exists customers (
  id                    uuid primary key default gen_random_uuid(),
  created_at            timestamptz not null default now(),
  email                 text unique not null,
  stripe_customer_id    text unique,
  stripe_subscription_id text,
  subscription_tier     text not null default 'basic'
                          check (subscription_tier in ('basic','standard','premium')),
  access_token          text unique not null,
  token_expires_at      timestamptz,
  referred_by           uuid references affiliates(id),
  is_active             boolean not null default true
);
create index on customers (access_token);
create index on customers (email);

-- ─────────────────────────────────────────────
-- AFFILIATE_REFERRALS
-- ─────────────────────────────────────────────
create table if not exists affiliate_referrals (
  id              uuid primary key default gen_random_uuid(),
  created_at      timestamptz not null default now(),
  affiliate_id    uuid references affiliates(id),
  customer_id     uuid references customers(id),
  conversion_aud  numeric(10,2) not null default 0,
  commission_aud  numeric(10,2) not null default 0,
  paid_out        boolean not null default false
);
create index on affiliate_referrals (affiliate_id, paid_out);

-- ─────────────────────────────────────────────
-- EMAIL_CAMPAIGNS
-- ─────────────────────────────────────────────
create table if not exists email_campaigns (
  id           uuid primary key default gen_random_uuid(),
  created_at   timestamptz not null default now(),
  name         text not null,
  subject      text not null,
  body_text    text not null,
  body_html    text,
  status       text not null default 'draft'
                 check (status in ('draft','sending','sent','failed')),
  total_sent   int not null default 0,
  total_opened int not null default 0
);

-- ─────────────────────────────────────────────
-- EMAIL_CONTACTS (outreach targets)
-- ─────────────────────────────────────────────
create table if not exists email_contacts (
  id           uuid primary key default gen_random_uuid(),
  created_at   timestamptz not null default now(),
  email        text unique not null,
  name         text,
  source       text,
  tags         text[],
  last_emailed timestamptz,
  is_opted_out boolean not null default false
);
create index on email_contacts (is_opted_out, last_emailed);

-- ─────────────────────────────────────────────
-- ALERTS, ORDERS, PRODUCTS, WEBHOOK_EVENTS (from v1)
-- ─────────────────────────────────────────────
create table if not exists alerts (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  source      text not null,
  level       text not null default 'info'
                check (level in ('info','warn','error','critical')),
  title       text not null,
  body        text,
  slack_sent  boolean not null default false,
  raw         jsonb
);
create index on alerts (created_at desc);

create table if not exists products (
  id                uuid primary key default gen_random_uuid(),
  created_at        timestamptz not null default now(),
  stripe_product_id text unique,
  stripe_price_id   text,
  name              text not null,
  description       text,
  price_aud         numeric(10,2) not null,
  active            boolean not null default true,
  metadata          jsonb
);

create table if not exists orders (
  id                    uuid primary key default gen_random_uuid(),
  created_at            timestamptz not null default now(),
  stripe_session_id     text unique,
  stripe_payment_intent text,
  product_id            uuid references products(id),
  customer_email        text,
  amount_aud            numeric(10,2) not null,
  status                text not null default 'pending'
                          check (status in ('pending','paid','failed','refunded')),
  raw                   jsonb
);
create index on orders (status, created_at desc);

create table if not exists webhook_events (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  source      text not null,
  event_type  text,
  payload     jsonb not null,
  processed   boolean not null default false
);

-- ─────────────────────────────────────────────
-- RLS (service_role bypass for backend)
-- ─────────────────────────────────────────────
do $$ declare t text; begin
  for t in select unnest(array['leads','affiliates','customers','affiliate_referrals',
    'email_campaigns','email_contacts','alerts','products','orders','webhook_events'])
  loop
    execute format('alter table %I enable row level security', t);
    execute format(
      'create policy if not exists "service_role_%s" on %I for all using (true)', t, t);
  end loop;
end $$;
