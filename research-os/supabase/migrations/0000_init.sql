create extension if not exists vector;
create extension if not exists pg_trgm;

-- papers
create table papers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text, authors jsonb default '[]'::jsonb,
  year int, venue text, abstract text,
  doi text, arxiv_id text, semantic_scholar_id text,
  source_url text, storage_path text, page_count int,
  status text not null default 'processing' check (status in ('processing','ready','failed')),
  reading_status text not null default 'unread' check (reading_status in ('unread','queued','reading','read')),
  summary text, error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index papers_user_id_idx on papers(user_id);
create index papers_status_idx on papers(status);
create index papers_created_at_idx on papers(created_at desc);
create index papers_title_trgm_idx on papers using gin (title gin_trgm_ops);
alter table papers enable row level security;
create policy papers_select_own on papers for select using (auth.uid() = user_id);
create policy papers_insert_own on papers for insert with check (auth.uid() = user_id);
create policy papers_update_own on papers for update using (auth.uid() = user_id);
create policy papers_delete_own on papers for delete using (auth.uid() = user_id);

-- chunks
create table chunks (
  id uuid primary key default gen_random_uuid(),
  paper_id uuid not null references papers(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  chunk_index int not null, content text not null,
  page_number int, char_start int, char_end int, token_count int,
  embedding vector(1536),
  content_tsv tsvector generated always as (to_tsvector('english', content)) stored,
  created_at timestamptz not null default now()
);
create index chunks_paper_id_idx on chunks(paper_id);
create index chunks_user_id_idx on chunks(user_id);
create index chunks_embedding_idx on chunks using hnsw (embedding vector_cosine_ops);
create index chunks_tsv_idx on chunks using gin (content_tsv);
alter table chunks enable row level security;
create policy chunks_select_own on chunks for select using (auth.uid() = user_id);

-- notes
create table notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  paper_id uuid references papers(id) on delete set null,
  title text, content text not null default '',
  linked_chunk_ids uuid[] default array[]::uuid[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index notes_user_id_idx on notes(user_id);
create index notes_paper_id_idx on notes(paper_id);
alter table notes enable row level security;
create policy notes_all_own on notes for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- highlights (Phase 2)
create table highlights (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  paper_id uuid not null references papers(id) on delete cascade,
  chunk_id uuid references chunks(id) on delete set null,
  note_id uuid references notes(id) on delete set null,
  page_number int, text text not null,
  color text default 'yellow', position jsonb,
  created_at timestamptz not null default now()
);
create index highlights_user_id_idx on highlights(user_id);
create index highlights_paper_id_idx on highlights(paper_id);
alter table highlights enable row level security;
create policy highlights_all_own on highlights for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- collections (Phase 2)
create table collections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null, description text,
  created_at timestamptz not null default now()
);
create table collection_papers (
  collection_id uuid not null references collections(id) on delete cascade,
  paper_id uuid not null references papers(id) on delete cascade,
  added_at timestamptz not null default now(),
  primary key (collection_id, paper_id)
);
create index collections_user_id_idx on collections(user_id);
alter table collections enable row level security;
alter table collection_papers enable row level security;
create policy collections_all_own on collections for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy collection_papers_via_collection on collection_papers for all
  using (exists (select 1 from collections c where c.id = collection_id and c.user_id = auth.uid()))
  with check (exists (select 1 from collections c where c.id = collection_id and c.user_id = auth.uid()));

-- tags (Phase 3)
create table tags (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  kind text not null default 'custom' check (kind in ('method','dataset','custom')),
  created_at timestamptz not null default now(),
  unique (user_id, name, kind)
);
create table paper_tags (
  paper_id uuid not null references papers(id) on delete cascade,
  tag_id uuid not null references tags(id) on delete cascade,
  confidence real,
  primary key (paper_id, tag_id)
);
alter table tags enable row level security;
alter table paper_tags enable row level security;
create policy tags_all_own on tags for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy paper_tags_via_tag on paper_tags for all
  using (exists (select 1 from tags t where t.id = tag_id and t.user_id = auth.uid()))
  with check (exists (select 1 from tags t where t.id = tag_id and t.user_id = auth.uid()));

-- tracked_questions (Phase 2)
create table tracked_questions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  question text not null, embedding vector(1536),
  last_checked_at timestamptz,
  created_at timestamptz not null default now()
);
create index tracked_questions_user_id_idx on tracked_questions(user_id);
create index tracked_questions_embedding_idx on tracked_questions using hnsw (embedding vector_cosine_ops);
alter table tracked_questions enable row level security;
create policy tracked_questions_all_own on tracked_questions for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- claims (Phase 3)
create table claims (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  paper_id uuid not null references papers(id) on delete cascade,
  chunk_id uuid references chunks(id) on delete set null,
  text text not null,
  claim_type text, subject text, predicate text, object text,
  confidence real, embedding vector(1536),
  created_at timestamptz not null default now()
);
create index claims_user_id_idx on claims(user_id);
create index claims_paper_id_idx on claims(paper_id);
create index claims_embedding_idx on claims using hnsw (embedding vector_cosine_ops);
alter table claims enable row level security;
create policy claims_select_own on claims for select using (auth.uid() = user_id);

-- contradictions (Phase 3)
create table contradictions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  claim_a_id uuid not null references claims(id) on delete cascade,
  claim_b_id uuid not null references claims(id) on delete cascade,
  rationale text,
  detected_at timestamptz not null default now(),
  dismissed boolean not null default false,
  unique (claim_a_id, claim_b_id)
);
create index contradictions_user_id_idx on contradictions(user_id);
alter table contradictions enable row level security;
create policy contradictions_select_own on contradictions for select using (auth.uid() = user_id);
create policy contradictions_update_own on contradictions for update using (auth.uid() = user_id);

-- assistant threads + messages (Phase 1)
create table assistant_threads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table assistant_messages (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references assistant_threads(id) on delete cascade,
  role text not null check (role in ('user','assistant','system')),
  content text not null,
  citations jsonb default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index assistant_threads_user_id_idx on assistant_threads(user_id);
create index assistant_messages_thread_id_idx on assistant_messages(thread_id);
alter table assistant_threads enable row level security;
alter table assistant_messages enable row level security;
create policy threads_all_own on assistant_threads for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy messages_via_thread on assistant_messages for all
  using (exists (select 1 from assistant_threads t where t.id = thread_id and t.user_id = auth.uid()))
  with check (exists (select 1 from assistant_threads t where t.id = thread_id and t.user_id = auth.uid()));

-- hybrid search RPC
create or replace function search_chunks(
  query_embedding vector(1536),
  query_text text,
  match_count int default 8,
  user_id_input uuid default auth.uid()
) returns table (
  id uuid, paper_id uuid, content text, page_number int, similarity real
) language sql stable as $$
  with dense as (
    select c.id, c.paper_id, c.content, c.page_number,
           1 - (c.embedding <=> query_embedding) as similarity
    from chunks c
    where c.user_id = user_id_input and c.embedding is not null
    order by c.embedding <=> query_embedding limit 40
  ),
  sparse as (
    select c.id, c.paper_id, c.content, c.page_number,
           ts_rank(c.content_tsv, plainto_tsquery('english', query_text))::real as similarity
    from chunks c
    where c.user_id = user_id_input
      and c.content_tsv @@ plainto_tsquery('english', query_text)
    order by similarity desc limit 40
  ),
  combined as (select * from dense union select * from sparse)
  select distinct on (id) id, paper_id, content, page_number, similarity
  from combined order by id, similarity desc limit match_count;
$$;

-- updated_at trigger
create or replace function touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;
create trigger papers_touch before update on papers for each row execute function touch_updated_at();
create trigger notes_touch before update on notes for each row execute function touch_updated_at();
create trigger threads_touch before update on assistant_threads for each row execute function touch_updated_at();
