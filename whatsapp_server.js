const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, Browsers } = require('@whiskeysockets/baileys');
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

if (!fs.existsSync(SESSIONS_DIR)) {
    fs.mkdirSync(SESSIONS_DIR, { recursive: true });
}

const sessions = {}; // key: sessionId -> { sock, qr, connected, name, sessionAuthDir }

const KNOWN_SESSIONS = [
    { id: '1032334999346283', name: 'Saidham Form (Phone: 9326340479)' },
    { id: '1044971085049692', name: 'Silver 26 August Form (Phone: 9892749953)' },
    { id: 'default', name: 'Default Backup Account' }
];

async function resetAndCleanSession(sessionId) {
    const sessionKey = String(sessionId).trim();
    if (sessions[sessionKey]) {
        try {
            if (sessions[sessionKey].sock) {
                sessions[sessionKey].sock.ev.removeAllListeners();
                sessions[sessionKey].sock.end(undefined);
            }
        } catch (e) {}
        delete sessions[sessionKey];
    }

    const sessionAuthDir = path.join(SESSIONS_DIR, sessionKey);
    try {
        fs.rmSync(sessionAuthDir, { recursive: true, force: true });
    } catch (e) {}

    return await initSession(sessionKey);
}

async function initSession(sessionId) {
    const sessionKey = String(sessionId).trim();
    if (sessions[sessionKey] && sessions[sessionKey].sock) {
        return sessions[sessionKey];
    }

    const sessionAuthDir = path.join(SESSIONS_DIR, sessionKey);
    if (!fs.existsSync(sessionAuthDir)) {
        fs.mkdirSync(sessionAuthDir, { recursive: true });
    }

    const sess = {
        id: sessionKey,
        sock: null,
        qr: null,
        connected: false,
        sessionAuthDir: sessionAuthDir
    };
    sessions[sessionKey] = sess;

    try {
        const { state, saveCreds } = await useMultiFileAuthState(sessionAuthDir);
        const sock = makeWASocket({
            auth: state,
            browser: Browsers.ubuntu('Chrome'),
            printQRInTerminal: false,
            connectTimeoutMs: 60000,
            defaultQueryTimeoutMs: 60000,
            retryRequestDelayMs: 2000
        });

        sess.sock = sock;
        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                sess.qr = qr;
                console.log(`[WhatsApp - ${sessionKey}] New QR code generated successfully!`);
            }
            if (connection === 'close') {
                sess.connected = false;
                sess.qr = null;
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const errMsg = String(lastDisconnect?.error || '');
                console.log(`[WhatsApp - ${sessionKey}] Connection closed. Code: ${statusCode}, Err: ${errMsg}`);

                if (statusCode === DisconnectReason.loggedOut || errMsg.includes('QR refs attempts ended') || statusCode === 401) {
                    console.log(`[WhatsApp - ${sessionKey}] Resetting auth directory...`);
                    try { fs.rmSync(sessionAuthDir, { recursive: true, force: true }); } catch (e) {}
                }
                setTimeout(() => initSession(sessionKey), 4000);
            } else if (connection === 'open') {
                sess.connected = true;
                sess.qr = null;
                console.log(`\n======================================================`);
                console.log(`[WhatsApp] SESSION ${sessionKey} CONNECTED SUCCESSFULLY!`);
                console.log(`======================================================\n`);
            }
        });
    } catch (err) {
        console.error(`[WhatsApp - ${sessionKey}] Initialization error:`, err);
        setTimeout(() => initSession(sessionKey), 5000);
    }
    return sess;
}

// Start all known sessions at launch
KNOWN_SESSIONS.forEach(s => initSession(s.id));

// Main Dashboard
app.get('/qr', async (req, res) => {
    let htmlCards = KNOWN_SESSIONS.map(item => {
        const s = sessions[item.id] || {};
        const statusBadge = s.connected 
            ? `<span style="background:#2e7d32;color:white;padding:5px 14px;border-radius:20px;font-size:14px;font-weight:bold;">✅ Connected</span>`
            : `<span style="background:#d32f2f;color:white;padding:5px 14px;border-radius:20px;font-size:14px;font-weight:bold;">⏳ Scan Required</span>`;

        return `
            <div style="background:white;padding:22px;border-radius:12px;box-shadow:0 3px 12px rgba(0,0,0,0.08);margin-bottom:18px;display:flex;justify-content:space-between;align-items:center;">
                <div style="text-align:left;">
                    <h3 style="margin:0 0 6px 0;color:#111;font-size:18px;">${item.name}</h3>
                    <p style="margin:0;color:#666;font-size:13px;">Form ID: <code>${item.id}</code></p>
                </div>
                <div>
                    ${statusBadge}
                    <a href="/qr/${item.id}" style="margin-left:15px;background:#0070f3;color:white;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block;">Open QR Page &rarr;</a>
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

// Clean Reset Endpoint
app.get('/qr/:sessionId/reset', async (req, res) => {
    const sessionId = req.params.sessionId;
    await resetAndCleanSession(sessionId);
    res.redirect(`/qr/${sessionId}`);
});

// Single Session QR Page
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
                    <div style="background:white;padding:35px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;max-width:420px;">
                        <h1 style="color:#2e7d32;margin-top:0;">✅ Connected!</h1>
                        <p style="color:#444;font-size:16px;line-height:1.5;">WhatsApp Session for <b>${sessionId}</b> is active and sending messages.</p>
                        <div style="margin-top:20px;">
                            <a href="/qr" style="color:#0070f3;text-decoration:none;font-weight:bold;margin-right:15px;">&larr; Back to Dashboard</a>
                            <a href="/qr/${sessionId}/reset" style="color:#d32f2f;text-decoration:none;font-size:13px;" onclick="return confirm('Disconnect and generate new QR?')">Logout / Reset</a>
                        </div>
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
                    <div style="background:white;padding:35px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;max-width:400px;">
                        <h2 style="color:#333;margin-top:0;">⚡ Generating QR Code...</h2>
                        <p style="color:#666;">Initializing fresh WhatsApp session for <code>${sessionId}</code>.</p>
                        <a href="/qr/${sessionId}/reset" style="display:inline-block;margin-top:15px;background:#e0e0e0;color:#333;padding:8px 16px;border-radius:6px;text-decoration:none;font-size:13px;">🔄 Click to Reset Session</a>
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
                    <div style="background:white;padding:30px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;max-width:380px;">
                        <h2 style="color:#111;margin-top:0;margin-bottom:10px;">Scan with WhatsApp</h2>
                        <p style="color:#555;font-size:14px;margin-bottom:20px;">Open WhatsApp &rarr; <b>Linked Devices</b> &rarr; <b>Link a Device</b></p>
                        
                        <img src="${qrImage}" style="width:260px;height:260px;border:2px solid #25D366;border-radius:10px;padding:5px;background:white;"/>
                        
                        <div style="margin-top:20px;display:flex;justify-content:space-between;align-items:center;">
                            <a href="/qr" style="color:#0070f3;text-decoration:none;font-size:14px;font-weight:bold;">&larr; Dashboard</a>
                            <a href="/qr/${sessionId}/reset" style="background:#ff4d4f;color:white;padding:6px 12px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:bold;">🔄 Reset QR</a>
                        </div>
                    </div>
                    <script>setTimeout(() => location.reload(), 4000);</script>
                </body>
            </html>
        `);
    } catch (err) {
        res.status(500).send('Error generating QR image');
    }
});

// Check status
app.get('/status', (req, res) => {
    const statusMap = {};
    Object.keys(sessions).forEach(k => {
        statusMap[k] = { connected: sessions[k].connected, hasQr: !!sessions[k].qr };
    });
    res.json({ sessions: statusMap });
});

// Send WhatsApp message
app.post('/send-message', async (req, res) => {
    const { to, message, session } = req.body;
    if (!to || !message) {
        return res.status(400).json({ error: 'Parameters "to" and "message" are required.' });
    }

    let targetSess = null;
    const sessionKey = session ? String(session).trim() : 'default';

    if (sessions[sessionKey] && sessions[sessionKey].connected) {
        targetSess = sessions[sessionKey];
    } else {
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
