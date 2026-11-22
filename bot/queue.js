// منطق طابور الإشعارات (من غير Baileys عشان نقدر نختبره لوحده)
const MAX_ATTEMPTS = 5;

function headers(key) {
  return { apikey: key, Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' };
}

async function fetchPending(cfg, limit = 20) {
  const url = `${cfg.url}/rest/v1/notifications?status=eq.pending&order=created_at.asc&limit=${limit}&select=id,message,attempts`;
  const res = await fetch(url, { headers: headers(cfg.key) });
  if (!res.ok) throw new Error(`fetchPending ${res.status}: ${await res.text()}`);
  return res.json();
}

async function patch(cfg, id, body) {
  const res = await fetch(`${cfg.url}/rest/v1/notifications?id=eq.${id}`, {
    method: 'PATCH', headers: { ...headers(cfg.key), Prefer: 'return=minimal' }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patch ${res.status}: ${await res.text()}`);
}

const markSent = (cfg, id) => patch(cfg, id, { status: 'sent', sent_at: new Date().toISOString(), error: null });

function markFailed(cfg, row, err) {
  const attempts = (row.attempts || 0) + 1;
  return patch(cfg, row.id, { attempts, error: String(err).slice(0, 300), status: attempts >= MAX_ATTEMPTS ? 'failed' : 'pending' });
}

// يبعت كل المعلّق بالترتيب. send(text) بترجع Promise.
async function processQueue(cfg, send, log = console.log) {
  const rows = await fetchPending(cfg);
  let sent = 0;
  for (const row of rows) {
    try {
      await send(row.message);
      await markSent(cfg, row.id);
      sent++;
    } catch (e) {
      log(`فشل إرسال ${row.id}: ${e.message}`);
      try { await markFailed(cfg, row, e.message); } catch (e2) { log(e2.message); }
    }
  }
  return sent;
}

module.exports = { processQueue, fetchPending, markSent, markFailed, MAX_ATTEMPTS };
