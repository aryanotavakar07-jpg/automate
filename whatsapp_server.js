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
const AUTH_DIR = path.join(__dirname, 'baileys_auth_info');

if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
}

let sock = null;
let latestQrData = null;
let isConnected = false;

async function connectToWhatsApp() {
    try {
        const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

        sock = makeWASocket({
            auth: state,
            browser: Browsers.ubuntu('Chrome'),
            printQRInTerminal: false,
            connectTimeoutMs: 60000,
            defaultQueryTimeoutMs: 60000
        });

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                latestQrData = qr;
                console.log('\n[WhatsApp] New QR Code generated! Scan at /qr\n');
            }

            if (connection === 'close') {
                isConnected = false;
                latestQrData = null;
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const errMsg = String(lastDisconnect?.error || '');
                console.log('[WhatsApp] Connection closed. Code:', statusCode, 'Error:', errMsg);

                if (statusCode === DisconnectReason.loggedOut || errMsg.includes('QR refs attempts ended') || statusCode === 401) {
                    console.log('[WhatsApp] Resetting auth session to generate fresh QR code...');
                    try {
                        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
                    } catch (e) {}
                }

                setTimeout(connectToWhatsApp, 3000);
            } else if (connection === 'open') {
                isConnected = true;
                latestQrData = null;
                console.log('\n======================================================');
                console.log('[WhatsApp] SUCCESSFULLY CONNECTED TO WHATSAPP!');
                console.log('======================================================\n');
            }
        });
    } catch (err) {
        console.error('[WhatsApp] Initialization error:', err);
        setTimeout(connectToWhatsApp, 5000);
    }
}

// Single QR Login Page
app.get('/qr', async (req, res) => {
    if (isConnected) {
        return res.send(`
            <html>
                <head><title>WhatsApp Status</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;">
                    <div style="background:white;padding:35px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;max-width:420px;">
                        <h1 style="color:#2e7d32;margin-top:0;">✅ WhatsApp Connected!</h1>
                        <p style="color:#444;font-size:16px;">Lead Automation is active and sending instant messages.</p>
                    </div>
                </body>
            </html>
        `);
    }

    if (!latestQrData) {
        return res.send(`
            <html>
                <head><title>Generating WhatsApp QR</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;">
                    <div style="background:white;padding:35px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;">
                        <h2 style="color:#333;margin-top:0;">⚡ Generating WhatsApp QR Code...</h2>
                        <p style="color:#666;">Please wait a few seconds, page will auto-refresh.</p>
                    </div>
                    <script>setTimeout(() => location.reload(), 3000);</script>
                </body>
            </html>
        `);
    }

    try {
        const qrImage = await QRCode.toDataURL(latestQrData);
        res.send(`
            <html>
                <head><title>WhatsApp QR Login</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;">
                    <div style="background:white;padding:30px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;">
                        <h2 style="color:#111;margin-top:0;margin-bottom:10px;">Scan with WhatsApp</h2>
                        <p style="color:#666;margin-bottom:20px;">Open WhatsApp &rarr; Settings/Menu &rarr; <b>Linked Devices</b> &rarr; <b>Link a Device</b></p>
                        <img src="${qrImage}" style="width:280px;height:280px;border:2px solid #25D366;border-radius:10px;padding:5px;background:white;"/>
                        <p style="color:#888;font-size:12px;margin-top:15px;">Auto-refreshes every 4 seconds</p>
                    </div>
                    <script>setTimeout(() => location.reload(), 4000);</script>
                </body>
            </html>
        `);
    } catch (err) {
        res.status(500).send('Error generating QR image');
    }
});

// Status check
app.get('/status', (req, res) => {
    res.json({ connected: isConnected, hasQr: !!latestQrData });
});

// Send WhatsApp message
app.post('/send-message', async (req, res) => {
    const { to, message } = req.body;
    if (!to || !message) {
        return res.status(400).json({ error: 'Parameters "to" and "message" are required.' });
    }
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp is not connected yet. Please scan QR code at /qr.' });
    }

    try {
        let formattedNumber = to.replace(/[^0-9]/g, '');
        if (formattedNumber.length === 10) {
            formattedNumber = '91' + formattedNumber;
        }
        if (!formattedNumber.endsWith('@s.whatsapp.net')) {
            formattedNumber = `${formattedNumber}@s.whatsapp.net`;
        }

        await sock.sendMessage(formattedNumber, { text: message });
        console.log(`[WhatsApp] Message sent successfully to ${to}`);
        res.json({ status: 'success', to });
    } catch (error) {
        console.error('[WhatsApp] Failed to send message:', error);
        res.status(500).json({ error: error.message });
    }
});

app.listen(PORT, () => {
    console.log(`[WhatsApp QR Service] Server running on http://localhost:${PORT}`);
    connectToWhatsApp();
});
