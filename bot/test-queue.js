// اختبار محلي للطابور بسيرفر وهمي بيقلّد Supabase (من غير واتساب)
const http = require('http');
const assert = require('assert');
const { processQueue } = require('./queue');

const rows = [
  { id: 'a1', message: 'رسالة 1', attempts: 0, status: 'pending' },
  { id: 'a2', message: 'رسالة 2', attempts: 4, status: 'pending' },
  { id: 'a3', message: 'رسالة 3', attempts: 0, status: 'sent' },
];

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  const id = (u.searchParams.get('id') || '').replace('eq.', '');
  if (req.method === 'GET') {
    res.end(JSON.stringify(rows.filter((r) => r.status === 'pending')));
  } else {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => { Object.assign(rows.find((r) => r.id === id), JSON.parse(body)); res.statusCode = 204; res.end(); });
  }
});

server.listen(0, async () => {
  const cfg = { url: `http://127.0.0.1:${server.address().port}`, key: 'k' };
  const sentTexts = [];
  // المرة الأولى: الإرسال ينجح للرسالة 1 ويفشل للرسالة 2 (وهي على آخر محاولة)
  let n = await processQueue(cfg, async (t) => { if (t === 'رسالة 2') throw new Error('boom'); sentTexts.push(t); }, () => {});
  assert.strictEqual(n, 1);
  assert.strictEqual(rows[0].status, 'sent');
  assert.strictEqual(rows[1].status, 'failed');        // وصلت 5 محاولات
  assert.strictEqual(rows[1].attempts, 5);
  assert.strictEqual(rows[2].status, 'sent');           // مالمسهاش
  // تاني مرة: مفيش حاجة معلّقة
  n = await processQueue(cfg, async () => { throw new Error('مفروض مايتندهش'); }, () => {});
  assert.strictEqual(n, 0);
  console.log('✅ اختبار الطابور نجح');
  server.close();
});
