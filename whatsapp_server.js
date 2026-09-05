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

const sessions = {}; // key: sessionId -> { sock, qr, connected, pairingCode, sessionAuthDir }

const KNOWN_CAMPAIGNS = {
    '1032334999346283': { name: 'Saidham Form', defaultPhone: '919326340479' },
    '1044971085049692': { name: 'Silver 26 August Form', defaultPhone: '919892749953' },
    'default': { name: 'Default Backup Account', defaultPhone: '' }
};

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
        pairingCode: null,
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
            keepAliveIntervalMs: 25000
        });

        sess.sock = sock;
        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                sess.qr = qr;
                console.log(`[WhatsApp - ${sessionKey}] QR Code generated`);
            }
            if (connection === 'close') {
                sess.connected = false;
                sess.qr = null;
                sess.pairingCode = null;
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const errMsg = String(lastDisconnect?.error || '');
                console.log(`[WhatsApp - ${sessionKey}] Disconnected (${statusCode}): ${errMsg}`);

                if (statusCode === DisconnectReason.loggedOut || errMsg.includes('QR refs attempts ended') || statusCode === 401) {
                    console.log(`[WhatsApp - ${sessionKey}] Session invalid, resetting directory...`);
                    try { fs.rmSync(sessionAuthDir, { recursive: true, force: true }); } catch (e) {}
                }
                setTimeout(() => initSession(sessionKey), 5000);
            } else if (connection === 'open') {
                sess.connected = true;
                sess.qr = null;
                sess.pairingCode = null;
                console.log(`[WhatsApp - ${sessionKey}] CONNECTED ONLINE!`);
            }
        });
    } catch (err) {
        console.error(`[WhatsApp - ${sessionKey}] Init error:`, err);
        setTimeout(() => initSession(sessionKey), 5000);
    }
    return sess;
}

// Request Phone Number Pairing Code (Alternative to QR scan)
app.get('/pair/:sessionId', async (req, res) => {
    const sessionId = req.params.sessionId;
    let phone = req.query.phone || (KNOWN_CAMPAIGNS[sessionId] ? KNOWN_CAMPAIGNS[sessionId].defaultPhone : '');
    phone = phone.replace(/[^0-9]/g, '');

    if (!phone) {
        return res.status(400).send('Please provide phone parameter e.g. /pair/1032334999346283?phone=919326340479');
    }

    let sess = sessions[sessionId];
    if (!sess || !sess.sock) {
        sess = await initSession(sessionId);
        await new Promise(r => setTimeout(r, 2000));
    }

    try {
        const code = await sess.sock.requestPairingCode(phone);
        sess.pairingCode = code;
        res.json({ status: 'success', sessionId, phone, pairingCode: code });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Dashboard
app.get('/qr', async (req, res) => {
    let htmlCards = Object.keys(KNOWN_CAMPAIGNS).map(id => {
        const item = KNOWN_CAMPAIGNS[id];
        const s = sessions[id] || {};
        const statusBadge = s.connected 
            ? `<span style="background:#2e7d32;color:white;padding:5px 14px;border-radius:20px;font-size:14px;font-weight:bold;">✅ Connected</span>`
            : `<span style="background:#d32f2f;color:white;padding:5px 14px;border-radius:20px;font-size:14px;font-weight:bold;">⏳ Login Required</span>`;

        return `
            <div style="background:white;padding:22px;border-radius:12px;box-shadow:0 3px 12px rgba(0,0,0,0.08);margin-bottom:18px;display:flex;justify-content:space-between;align-items:center;">
                <div style="text-align:left;">
                    <h3 style="margin:0 0 6px 0;color:#111;font-size:18px;">${item.name}</h3>
                    <p style="margin:0;color:#666;font-size:13px;">Form ID: <code>${id}</code> | Target Phone: <b>${item.defaultPhone || 'Default'}</b></p>
                </div>
                <div>
                    ${statusBadge}
                    <a href="/qr/${id}" style="margin-left:15px;background:#0070f3;color:white;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block;">Manage Login &rarr;</a>
                </div>
            </div>
        `;
    }).join('');

    res.send(`
        <html>
            <head><title>WhatsApp Multi-Account Dashboard</title></head>
            <body style="font-family:sans-serif;background:#f4f6f9;margin:0;padding:40px 20px;">
                <div style="max-width:700px;margin:0 auto;text-align:center;">
                    <h1 style="color:#111;margin-bottom:10px;">📱 WhatsApp Multi-Account Manager</h1>
                    <p style="color:#555;margin-bottom:30px;">Connect separate WhatsApp accounts via QR Code or 8-Digit Pairing Code.</p>
                    ${htmlCards}
                </div>
                <script>setTimeout(() => location.reload(), 10000);</script>
            </body>
        </html>
    `);
});

// Single Session Login Page (Supports both QR Code and 8-Digit Pairing Code)
app.get('/qr/:sessionId', async (req, res) => {
    const sessionId = req.params.sessionId;
    let sess = sessions[sessionId];
    if (!sess) {
        sess = await initSession(sessionId);
    }

    const campaign = KNOWN_CAMPAIGNS[sessionId] || { name: `Session ${sessionId}`, defaultPhone: '' };

    if (sess.connected) {
        return res.send(`
            <html>
                <head><title>WhatsApp Connected - ${campaign.name}</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;">
                    <div style="background:white;padding:35px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;max-width:440px;">
                        <h1 style="color:#2e7d32;margin-top:0;">✅ WhatsApp Connected!</h1>
                        <p style="color:#444;font-size:16px;line-height:1.5;">Account for <b>${campaign.name}</b> is active and sending instant lead messages.</p>
                        <div style="margin-top:25px;">
                            <a href="/qr" style="color:#0070f3;text-decoration:none;font-weight:bold;margin-right:20px;">&larr; Back to Dashboard</a>
                            <a href="/qr/${sessionId}/reset" style="color:#d32f2f;text-decoration:none;font-size:13px;" onclick="return confirm('Disconnect and generate new login?')">Disconnect / Reset</a>
                        </div>
                    </div>
                </body>
            </html>
        `);
    }

    let qrImageHtml = `<p style="color:#666;">Generating QR Code, please wait 3 seconds...</p><script>setTimeout(() => location.reload(), 3000);</script>`;
    if (sess.qr) {
        try {
            const qrImage = await QRCode.toDataURL(sess.qr);
            qrImageHtml = `<img src="${qrImage}" style="width:250px;height:250px;border:2px solid #25D366;border-radius:10px;padding:5px;background:white;"/>`;
        } catch (e) {}
    }

    let pairCodeHtml = sess.pairingCode 
        ? `<div style="background:#e8f5e9;border:1px solid #4caf50;padding:15px;border-radius:8px;margin-top:15px;"><span style="font-size:13px;color:#2e7d32;">8-Digit WhatsApp Pairing Code:</span><h2 style="font-family:monospace;font-size:32px;letter-spacing:4px;color:#1b5e20;margin:8px 0;">${sess.pairingCode}</h2><p style="font-size:12px;color:#555;margin:0;">Open WhatsApp &rarr; Linked Devices &rarr; Link with Phone Number &rarr; Enter Code</p></div>`
        : ``;

    res.send(`
        <html>
            <head><title>WhatsApp Login - ${campaign.name}</title></head>
            <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;padding:20px;">
                <div style="background:white;padding:30px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;max-width:420px;width:100%;">
                    <h2 style="color:#111;margin-top:0;margin-bottom:5px;">${campaign.name} Login</h2>
                    <p style="color:#666;font-size:14px;margin-bottom:20px;">Choose Method 1 (QR Scan) or Method 2 (8-Digit Code)</p>

                    <!-- METHOD 1: QR CODE SCAN -->
                    <div style="border:1px solid #eee;padding:15px;border-radius:10px;background:#fafafa;margin-bottom:20px;">
                        <h4 style="margin:0 0 10px 0;color:#333;">Method 1: Scan QR Code</h4>
                        ${qrImageHtml}
                        <p style="color:#888;font-size:12px;margin:10px 0 0 0;">Open WhatsApp &rarr; <b>Linked Devices</b> &rarr; <b>Link a Device</b></p>
                    </div>

                    <!-- METHOD 2: 8-DIGIT PAIRING CODE -->
                    <div style="border:1px solid #eee;padding:15px;border-radius:10px;background:#fafafa;margin-bottom:15px;">
                        <h4 style="margin:0 0 10px 0;color:#333;">Method 2: Link via 8-Digit Code</h4>
                        <form method="GET" action="/pair/${sessionId}" style="margin:0;">
                            <input type="text" name="phone" value="${campaign.defaultPhone}" placeholder="91XXXXXXXXXX" style="width:70%;padding:8px;border:1px solid #ccc;border-radius:6px;font-size:14px;text-align:center;"/>
                            <button type="submit" style="padding:8px 12px;background:#25D366;color:white;border:none;border-radius:6px;font-weight:bold;cursor:pointer;">Get Code</button>
                        </form>
                        ${pairCodeHtml}
                    </div>

                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:15px;">
                        <a href="/qr" style="color:#0070f3;text-decoration:none;font-size:14px;font-weight:bold;">&larr; Dashboard</a>
                        <a href="/qr/${sessionId}/reset" style="background:#ff4d4f;color:white;padding:6px 12px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:bold;">🔄 Reset Login</a>
                    </div>
                </div>
                <script>setTimeout(() => { if(!document.querySelector('input:focus')) location.reload(); }, 5000);</script>
            </body>
        </html>
    `);
});

// Single Session Reset
app.get('/qr/:sessionId/reset', async (req, res) => {
    const sessionId = req.params.sessionId;
    await resetAndCleanSession(sessionId);
    res.redirect(`/qr/${sessionId}`);
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
        return res.status(503).json({ error: `WhatsApp session '${sessionKey}' is not connected yet.` });
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
    console.log(`[WhatsApp Multi-Account Manager] Server running on http://localhost:${PORT}`);
});
