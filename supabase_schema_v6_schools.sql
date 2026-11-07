-- المدارس وشركات التأمين من جوه البرنامج (شغّله بعد v5. آمن للتشغيل أكتر من مرة)
alter table insurance_providers add column if not exists email text;
alter table client_companies add column if not exists is_active boolean default true;

-- إيميل Allianz المعروف (لو لسه فاضي)
update insurance_providers set email = 'Health.Corporate@allianz.com.eg'
  where name = 'Allianz' and (email is null or email = '');

notify pgrst, 'reload schema';
