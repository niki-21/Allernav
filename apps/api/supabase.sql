create table if not exists public.menu_records (
  restaurant_id text primary key,
  restaurant_name text,
  source_url text,
  source_type text not null,
  fetched_at timestamptz,
  status text not null,
  error text,
  raw_text text,
  menu_json jsonb not null,
  updated_at timestamptz not null default now()
);

create index if not exists menu_records_status_idx
  on public.menu_records (status);

create index if not exists menu_records_source_type_idx
  on public.menu_records (source_type);

create table if not exists public.menu_documents (
  id uuid primary key default gen_random_uuid(),
  restaurant_id text not null references public.menu_records (restaurant_id) on delete cascade,
  document_url text not null,
  content_type text,
  extraction_method text,
  page_count integer,
  extraction_confidence numeric,
  raw_text text,
  created_at timestamptz not null default now()
);

create index if not exists menu_documents_restaurant_id_idx
  on public.menu_documents (restaurant_id);

create unique index if not exists menu_documents_restaurant_url_idx
  on public.menu_documents (restaurant_id, document_url);

create table if not exists public.menu_refresh_jobs (
  id uuid primary key,
  restaurant_id text not null,
  status text not null,
  message text not null,
  processed_documents integer not null default 0,
  total_documents integer not null default 0,
  job_json jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);

alter table public.menu_refresh_jobs add column if not exists restaurant_id text;
alter table public.menu_refresh_jobs add column if not exists status text;
alter table public.menu_refresh_jobs add column if not exists message text;
alter table public.menu_refresh_jobs add column if not exists processed_documents integer not null default 0;
alter table public.menu_refresh_jobs add column if not exists total_documents integer not null default 0;
alter table public.menu_refresh_jobs add column if not exists job_json jsonb;
alter table public.menu_refresh_jobs add column if not exists created_at timestamptz not null default now();
alter table public.menu_refresh_jobs add column if not exists updated_at timestamptz not null default now();
alter table public.menu_refresh_jobs add column if not exists completed_at timestamptz;

create index if not exists menu_refresh_jobs_restaurant_idx
  on public.menu_refresh_jobs (restaurant_id, created_at desc);

create index if not exists menu_refresh_jobs_status_idx
  on public.menu_refresh_jobs (status);

create table if not exists public.menu_document_pages (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.menu_refresh_jobs (id) on delete cascade,
  restaurant_id text not null,
  document_url text not null,
  page_number integer not null,
  status text not null,
  raw_text text,
  extraction_confidence numeric,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists menu_document_pages_job_url_idx
  on public.menu_document_pages (job_id, document_url);
