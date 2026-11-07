-- سجل التدقيق (شغّله بعد v4. آمن للتشغيل أكتر من مرة)
create table if not exists audit_log (
  id uuid primary key default gen_random_uuid(),
  actor text, role text,
  action text not null,      -- login | login_failed | request_created | status_changed | approval_created | approval_decided | member_import | policy_dates | portal_code
  entity text, ref text, details text,
  created_at timestamptz default now());
create index if not exists idx_audit_created on audit_log(created_at desc);
create index if not exists idx_audit_action on audit_log(action);

-- RLS مفعّل وبدون policy: البرنامج بس (service key) هو اللي يكتب ويقرا.
alter table audit_log enable row level security;
drop policy if exists "allow_all" on audit_log;

-- يمنع تعديل أو مسح أي سطر حتى بالمفتاح السري من غير ما تشيل التريجر بنفسك من SQL Editor
create or replace function audit_log_immutable() returns trigger language plpgsql as $$
begin raise exception 'audit_log is append-only'; end $$;
drop trigger if exists audit_log_no_change on audit_log;
create trigger audit_log_no_change before update or delete on audit_log
  for each row execute function audit_log_immutable();

notify pgrst, 'reload schema';
