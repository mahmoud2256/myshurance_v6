-- حسابات المستخدمين: مدير + أدمنز (كل أدمن بمدارس محددة). شغّله بعد v6. آمن للتشغيل أكتر من مرة.
create table if not exists app_users (
  id uuid primary key default gen_random_uuid(),
  username text unique not null,
  full_name text,
  role text not null default 'admin' check (role in ('manager', 'admin')),
  password_hash text not null,                 -- salt$hash (PBKDF2)، الباسورد نفسه مش بيتخزن
  policies jsonb not null default '[]'::jsonb, -- أرقام الوثائق (المدارس) المتاحة للأدمن
  is_active boolean not null default true,
  created_by text,
  created_at timestamptz default now());
create index if not exists idx_app_users_username on app_users(username);

alter table app_users enable row level security;
drop policy if exists "allow_all" on app_users;

notify pgrst, 'reload schema';
