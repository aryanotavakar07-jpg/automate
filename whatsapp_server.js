const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const QRCode = require('qrcode');
const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.WA_PORT || 3000;
const SESSIONS_DIR = path.join(__dirname, 'baileys_sessions');

// Migrate old auth dir if exists
const OLD_AUTH_DIR = path.join(__dirname, 'baileys_auth_info');
if (fs.existsSync(OLD_AUTH_DIR) && !fs.existsSync(SESSIONS_DIR)) {
    try {
        fs.mkdirSync(SESSIONS_DIR, { recursive: true });
        const defaultDir = path.join(SESSIONS_DIR, 'default');
        fs.cpSync(OLD_AUTH_DIR, defaultDir, { recursive: true });
    } catch (e) {}
}

if (!fs.existsSync(SESSIONS_DIR)) {
    fs.mkdirSync(SESSIONS_DIR, { recursive: true });
}

const sessions = {}; // key: sessionId -> { sock, qr, connected, name }

const KNOWN_SESSIONS = [
    { id: '1032334999346283', name: 'Saidham Form (Phone: 9326340479)' },
    { id: '1044971085049692', name: 'Silver 26 August Form (Phone: 9892749953)' },
    { id: 'default', name: 'Default Backup Account' }
];

async function initSession(sessionId) {
    if (sessions[sessionId] && sessions[sessionId].sock) {
        return sessions[sessionId];
    }

    const sessionAuthDir = path.join(SESSIONS_DIR, String(sessionId));
    if (!fs.existsSync(sessionAuthDir)) {
        fs.mkdirSync(sessionAuthDir, { recursive: true });
    }

    const sess = {
        id: String(sessionId),
        sock: null,
        qr: null,
        connected: false
    };
    sessions[sessionId] = sess;

    try {
        const { state, saveCreds } = await useMultiFileAuthState(sessionAuthDir);
        const sock = makeWASocket({
            auth: state,
            browser: [`Lead Automation (${sessionId})`, 'Chrome', '1.0.0'],
            printQRInTerminal: false
        });

        sess.sock = sock;
        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                sess.qr = qr;
                console.log(`[WhatsApp - ${sessionId}] New QR generated for session ${sessionId}`);
            }
            if (connection === 'close') {
                sess.connected = false;
                sess.qr = null;
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const errMsg = String(lastDisconnect?.error || '');
                console.log(`[WhatsApp - ${sessionId}] Connection closed. Code: ${statusCode}, Err: ${errMsg}`);
                
                if (statusCode === DisconnectReason.loggedOut || errMsg.includes('QR refs attempts ended') || statusCode === 401) {
                    console.log(`[WhatsApp - ${sessionId}] Resetting auth folder...`);
                    try { fs.rmSync(sessionAuthDir, { recursive: true, force: true }); } catch (e) {}
                }
                setTimeout(() => initSession(sessionId), 4000);
            } else if (connection === 'open') {
                sess.connected = true;
                sess.qr = null;
                console.log(`\n======================================================`);
                console.log(`[WhatsApp] SESSION ${sessionId} CONNECTED SUCCESSFULLY!`);
                console.log(`======================================================\n`);
            }
        });
    } catch (err) {
        console.error(`[WhatsApp - ${sessionId}] Initialization error:`, err);
        setTimeout(() => initSession(sessionId), 5000);
    }
    return sess;
}

// Start all known sessions at server launch
KNOWN_SESSIONS.forEach(s => initSession(s.id));

// Main Dashboard for QR login links
app.get('/qr', async (req, res) => {
    let htmlCards = KNOWN_SESSIONS.map(item => {
        const s = sessions[item.id] || {};
        const statusBadge = s.connected 
            ? `<span style="background:#2e7d32;color:white;padding:4px 12px;border-radius:20px;font-size:14px;">✅ Connected</span>`
            : `<span style="background:#d32f2f;color:white;padding:4px 12px;border-radius:20px;font-size:14px;">⏳ Scan Required</span>`;

        return `
            <div style="background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.08);margin-bottom:15px;display:flex;justify-content:space-between;align-items:center;">
                <div style="text-align:left;">
                    <h3 style="margin:0 0 5px 0;color:#111;">${item.name}</h3>
                    <p style="margin:0;color:#666;font-size:13px;">Form ID: <code>${item.id}</code></p>
                </div>
                <div>
                    ${statusBadge}
                    <a href="/qr/${item.id}" style="margin-left:15px;background:#0070f3;color:white;padding:8px 16px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;">Open QR Page &rarr;</a>
                </div>
            </div>
        `;
    }).join('');

    res.send(`
        <html>
            <head><title>WhatsApp Multi-Account Dashboard</title></head>
            <body style="font-family:sans-serif;background:#f4f6f9;margin:0;padding:40px 20px;">
                <div style="max-width:700px;margin:0 auto;text-align:center;">
                    <h1 style="color:#111;margin-bottom:10px;">📱 WhatsApp Multi-Account QR Manager</h1>
                    <p style="color:#555;margin-bottom:30px;">Connect separate WhatsApp accounts for each Meta Lead Form campaign.</p>
                    ${htmlCards}
                </div>
                <script>setTimeout(() => location.reload(), 8000);</script>
            </body>
        </html>
    `);
});

// Single Session QR page
app.get('/qr/:sessionId', async (req, res) => {
    const sessionId = req.params.sessionId;
    let sess = sessions[sessionId];
    if (!sess) {
        sess = await initSession(sessionId);
    }

    if (sess.connected) {
        return res.send(`
            <html>
                <head><title>WhatsApp Session Connected</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;">
                    <div style="background:white;padding:35px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;max-width:400px;">
                        <h1 style="color:#2e7d32;margin-top:0;">✅ Connected!</h1>
                        <p style="color:#444;font-size:16px;">WhatsApp Session for <b>${sessionId}</b> is active and sending messages.</p>
                        <a href="/qr" style="display:inline-block;margin-top:15px;color:#0070f3;text-decoration:none;">&larr; Back to Dashboard</a>
                    </div>
                </body>
            </html>
        `);
    }

    if (!sess.qr) {
        return res.send(`
            <html>
                <head><title>Generating WhatsApp QR</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;">
                    <div style="background:white;padding:35px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;">
                        <h2 style="color:#333;margin-top:0;">⚡ Generating QR Code for ${sessionId}...</h2>
                        <p style="color:#666;">Please wait a few seconds, page will auto-refresh.</p>
                    </div>
                    <script>setTimeout(() => location.reload(), 3000);</script>
                </body>
            </html>
        `);
    }

    try {
        const qrImage = await QRCode.toDataURL(sess.qr);
        res.send(`
            <html>
                <head><title>Scan QR for ${sessionId}</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;">
                    <div style="background:white;padding:30px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;">
                        <h2 style="color:#111;margin-top:0;">Scan QR Code (Session: ${sessionId})</h2>
                        <p style="color:#666;">Open WhatsApp &rarr; Settings/Menu &rarr; <b>Linked Devices</b> &rarr; <b>Link a Device</b></p>
                        <img src="${qrImage}" style="width:280px;height:280px;border:1px solid #ddd;border-radius:8px;"/>
                        <p style="color:#888;font-size:12px;margin-top:15px;">Auto-refreshes every 5 seconds</p>
                        <a href="/qr" style="display:inline-block;margin-top:10px;color:#0070f3;text-decoration:none;">&larr; Back to Dashboard</a>
                    </div>
                    <script>setTimeout(() => location.reload(), 5000);</script>
                </body>
            </html>
        `);
    } catch (err) {
        res.status(500).send('Error generating QR image');
    }
});

// Endpoint to check status
app.get('/status', (req, res) => {
    const statusMap = {};
    Object.keys(sessions).forEach(k => {
        statusMap[k] = { connected: sessions[k].connected, hasQr: !!sessions[k].qr };
    });
    res.json({ sessions: statusMap });
});

// Endpoint to send WhatsApp message with session targeting
app.post('/send-message', async (req, res) => {
    const { to, message, session } = req.body;
    if (!to || !message) {
        return res.status(400).json({ error: 'Parameters "to" and "message" are required.' });
    }

    let targetSess = null;
    const sessionKey = session ? String(session).strip() : 'default';

    if (sessions[sessionKey] && sessions[sessionKey].connected) {
        targetSess = sessions[sessionKey];
    } else {
        // Fallback to any connected session if target session isn't connected yet
        const activeKey = Object.keys(sessions).find(k => sessions[k].connected);
        if (activeKey) {
            targetSess = sessions[activeKey];
            console.log(`[WhatsApp] Requested session '${sessionKey}' not active. Using active session '${activeKey}'.`);
        }
    }

    if (!targetSess || !targetSess.sock) {
        return res.status(503).json({ error: `WhatsApp session '${sessionKey}' is not connected yet. Please scan QR.` });
    }

    try {
        let formattedNumber = to.replace(/[^0-9]/g, '');
        if (formattedNumber.length === 10) {
            formattedNumber = '91' + formattedNumber;
        }
        if (!formattedNumber.endsWith('@s.whatsapp.net')) {
            formattedNumber = `${formattedNumber}@s.whatsapp.net`;
        }

        await targetSess.sock.sendMessage(formattedNumber, { text: message });
        console.log(`[WhatsApp - ${targetSess.id}] Message sent successfully to ${to}`);
        res.json({ status: 'success', to, session_used: targetSess.id });
    } catch (error) {
        console.error(`[WhatsApp - ${targetSess.id}] Failed to send message:`, error);
        res.status(500).json({ error: error.message });
    }
});

app.listen(PORT, () => {
    console.log(`[WhatsApp Multi-Account Service] Running on http://localhost:${PORT}`);
});
