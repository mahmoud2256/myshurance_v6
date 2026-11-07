-- ─────────────────────────────────────────────────────────
-- Myshurance - Schema V3 (آمن للتشغيل أكتر من مرة، ومبيمسحش بيانات)
-- شغّله في Supabase > SQL Editor
-- ─────────────────────────────────────────────────────────
create extension if not exists pgcrypto;

-- الجداول الأساسية (لو مش موجودة)
create table if not exists insurance_providers (
  id uuid primary key default gen_random_uuid(),
  name text unique not null, code text unique,
  is_active boolean default true, created_at timestamptz default now());

create table if not exists client_companies (
  id uuid primary key default gen_random_uuid(),
  name text not null, provider_id uuid references insurance_providers(id),
  policy_no text unique, created_at timestamptz default now());

create table if not exists members (
  id uuid primary key default gen_random_uuid(),
  name text not null, policy_no text, status text default 'active',
  created_at timestamptz default now());

create table if not exists requests (
  id uuid primary key default gen_random_uuid(),
  type text, status text default 'draft', created_at timestamptz default now());

create table if not exists policies (
  id uuid primary key default gen_random_uuid(),
  policy_no text unique, type text default 'p_health', start_date date, end_date date,
  premium numeric default 0, status text default 'active', created_at timestamptz default now());

-- أعمدة العضو الجديدة
alter table members add column if not exists staff_no text;
alter table members add column if not exists card_no text;
alter table members add column if not exists national_id text;
alter table members add column if not exists phone text;
alter table members add column if not exists dependency text default 'PRINCIPAL';
alter table members add column if not exists dob date;
alter table members add column if not exists gender text;
alter table members add column if not exists category text;
alter table members add column if not exists source_start date;
alter table members add column if not exists source_end date;
alter table members add column if not exists termination_date date;

-- أعمدة الطلبات الجديدة
alter table requests add column if not exists ref_no text;
alter table requests add column if not exists member_id uuid references members(id) on delete set null;
alter table requests add column if not exists member_name text;
alter table requests add column if not exists staff_no text;
alter table requests add column if not exists policy_no text;
alter table requests add column if not exists effective_date date;
alter table requests add column if not exists details text;
alter table requests add column if not exists payload jsonb default '{}'::jsonb;
alter table requests add column if not exists created_by text;
alter table requests add column if not exists updated_at timestamptz;

alter table requests alter column status set default 'draft';

-- ترحيل البيانات القديمة (مرة واحدة، وآمن لو اتشغل تاني)
-- 1) الرقم الوظيفي كان متخزن في job
do $$ begin
  if exists (select 1 from information_schema.columns where table_name='members' and column_name='job') then
    execute $q$update members set staff_no = job where staff_no is null and job is not null and job <> ''$q$;
  end if;
end $$;
-- 2) رقم الكارت كان متخزن في national_id: أي قيمة مش 14 رقم تتنقل لـ card_no
update members set card_no = national_id, national_id = null
 where card_no is null and national_id is not null and national_id !~ '^[0-9]{14}$';
-- 3) حالات الطلبات القديمة
update requests set status = 'draft' where status = 'new';
update requests set type = 'add'     where type in ('t_add');
update requests set type = 'delete'  where type in ('t_del');
update requests set type = 'replace' where type in ('t_claim');

-- منع تكرار العضو في نفس الوثيقة (بالرقم الوظيفي)
delete from members m using (
  select id, row_number() over (partition by policy_no, staff_no order by created_at, id) rn
  from members where staff_no is not null
) d where m.id = d.id and d.rn > 1;

do $$ begin
  alter table members add constraint members_policy_staff_uq unique (policy_no, staff_no);
exception when duplicate_table or duplicate_object then null; end $$;

-- ref_no فريد
do $$ begin
  alter table requests add constraint requests_ref_no_uq unique (ref_no);
exception when duplicate_table or duplicate_object then null; end $$;

create index if not exists idx_requests_status on requests(status);
create index if not exists idx_members_policy on members(policy_no);

-- طابور الإشعارات (البوت بيقراه ويبعت واتساب)
create table if not exists notifications (
  id uuid primary key default gen_random_uuid(),
  event text, message text not null,
  status text not null default 'pending',     -- pending | sent | failed
  attempts int not null default 0,
  error text, sent_at timestamptz,
  created_at timestamptz default now());
create index if not exists idx_notifications_status on notifications(status, created_at);

-- شركات التأمين + وثائق Allianz
insert into insurance_providers (name, code) values
('Sarwa Life','SARWA_LIFE'),('Sarwa','SARWA'),('Orient','ORIENT'),('AXA','AXA'),('GIG Life','GIG_LIFE'),('Allianz','ALLIANZ')
on conflict (name) do nothing;

insert into policies (policy_no, type, status) values
('90502239912','p_health','active'),('90502239913','p_health','active'),
('90502239934','p_health','active'),('90502239932','p_health','active')
on conflict (policy_no) do nothing;

-- الأمان: RLS مفعّل وبدون أي policy مفتوحة.
-- البرنامج والبوت بيستخدموا service_role key (بيتجاوز RLS)، فأي حد معاه anon key مش هيقدر يقرا حاجة.
alter table insurance_providers enable row level security;
alter table client_companies enable row level security;
alter table members enable row level security;
alter table requests enable row level security;
alter table policies enable row level security;
alter table notifications enable row level security;
drop policy if exists "allow_all" on insurance_providers;
drop policy if exists "allow_all" on client_companies;
drop policy if exists "allow_all" on members;
drop policy if exists "allow_all" on requests;
drop policy if exists "allow_all" on policies;
