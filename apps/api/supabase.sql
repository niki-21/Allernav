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
