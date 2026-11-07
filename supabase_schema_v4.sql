-- ─────────────────────────────────────────────────────────
-- Myshurance - Schema V4 (شغّله بعد v3. آمن للتشغيل أكتر من مرة، ومبيمسحش بيانات)
-- يضيف: جدول الموافقات الطبية + كود دخول الموظف (هاش بس، مش الكود نفسه)
-- ─────────────────────────────────────────────────────────

-- كود دخول الموظف: salt$hash (PBKDF2)، الكود الأصلي مش بيتخزن
alter table members add column if not exists portal_pw text;

-- الموافقات الطبية
create table if not exists approvals (
  id uuid primary key default gen_random_uuid(),
  ref_no text unique,
  member_id uuid references members(id) on delete set null,
  member_name text, staff_no text, policy_no text,
  approval_type text,                      -- hospital | lab | pharmacy | surgery | checkup
  provider text, hospital text,
  amount numeric default 0,
  details text,
  status text not null default 'pending',  -- pending | approved | rejected
  created_by text, decided_by text,
  updated_at timestamptz,
  created_at timestamptz default now());
create index if not exists idx_approvals_status on approvals(status);
create index if not exists idx_approvals_member on approvals(member_id);

-- رقم قومي سريع البحث (بوابة الموظف)
create index if not exists idx_members_national_id on members(national_id);

-- الأمان: نفس نظام v3 (RLS مفعّل وبدون policy مفتوحة، والبرنامج بيستخدم service_role key)
alter table approvals enable row level security;
drop policy if exists "allow_all" on approvals;
