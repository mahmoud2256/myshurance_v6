// بوت إشعارات Myshurance: بيقرا الطابور من Supabase ويبعت واتساب لرقم الأدمن.
// تشغيل: npm install && node index.js  (أول مرة هيطلب مسح QR أو كود ربط من الرقم الوهمي)
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const { processQueue } = require('./queue');

const cfg = { url: (process.env.SUPABASE_URL || '').replace(/\/$/, ''), key: process.env.SUPABASE_KEY };
const ADMIN = (process.env.ADMIN_NUMBER || '').replace(/\D/g, '');
const POLL_MS = Math.max(3, Number(process.env.POLL_SECONDS || 10)) * 1000;
const PAIRING_NUMBER = (process.env.PAIRING_NUMBER || '').replace(/\D/g, '');

if (!cfg.url || !cfg.key || !ADMIN) {
  console.error('لازم تحط SUPABASE_URL و SUPABASE_KEY و ADMIN_NUMBER (شوف .env.example)');
  process.exit(1);
}

let timer = null;
let busy = false;

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState('auth');
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({ version, auth: state, logger: pino({ level: 'silent' }), browser: ['Myshurance', 'Chrome', '1.0'] });

  if (!sock.authState.creds.registered && PAIRING_NUMBER) {
    setTimeout(async () => {
      try { console.log('كود الربط:', await sock.requestPairingCode(PAIRING_NUMBER)); } catch (e) { console.error(e.message); }
    }, 3000);
  }

  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
    if (qr && !PAIRING_NUMBER) qrcode.generate(qr, { small: true });
    if (connection === 'open') {
      console.log('✅ البوت متصل. بقرا الطابور كل', POLL_MS / 1000, 'ثانية');
      clearInterval(timer);
      const tick = async () => {
        if (busy) return;
        busy = true;
        try {
          const n = await processQueue(cfg, (text) => sock.sendMessage(`${ADMIN}@s.whatsapp.net`, { text }));
          if (n) console.log(`اتبعت ${n} إشعار`);
        } catch (e) { console.error('خطأ في الطابور:', e.message); }
        busy = false;
      };
      tick();
      timer = setInterval(tick, POLL_MS);
    }
    if (connection === 'close') {
      clearInterval(timer);
      const code = lastDisconnect && lastDisconnect.error && lastDisconnect.error.output && lastDisconnect.error.output.statusCode;
      if (code === DisconnectReason.loggedOut) {
        console.error('الرقم اتفصل (logged out). امسح مجلد auth وشغّل تاني.');
        process.exit(1);
      }
      console.log('الاتصال اتقفل، بعيد المحاولة...');
      setTimeout(start, 5000);
    }
  });
}

start();
