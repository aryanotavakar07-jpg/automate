const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');
const express = require('express');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.WA_PORT || 3000;
let sock = null;
let latestQrData = null;
let isConnected = false;

async function connectToWhatsApp() {
    try {
        const { state, saveCreds } = await useMultiFileAuthState('baileys_auth_info');
        
        sock = makeWASocket({
            auth: state,
            printQRInTerminal: true
        });

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (qr) {
                latestQrData = qr;
                qrcode.generate(qr, { small: true });
                console.log('\n[WhatsApp] Scan the QR code above or open http://localhost:' + PORT + '/qr in your browser!\n');
            }

            if (connection === 'close') {
                isConnected = false;
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                console.log('[WhatsApp] Connection closed. Reconnecting:', shouldReconnect);
                if (shouldReconnect) {
                    setTimeout(connectToWhatsApp, 3000);
                }
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
    }
}

// Endpoint to view QR code in browser
app.get('/qr', async (req, res) => {
    if (isConnected) {
        return res.send('<h2 style="color:green;font-family:sans-serif;text-align:center;margin-top:20%;">WhatsApp is already connected and active!</h2>');
    }
    if (!latestQrData) {
        return res.send('<h2 style="font-family:sans-serif;text-align:center;margin-top:20%;">Generating QR Code... Please refresh in a few seconds.</h2><script>setTimeout(() => location.reload(), 3000);</script>');
    }
    try {
        const qrImage = await QRCode.toDataURL(latestQrData);
        res.send(`
            <html>
                <head><title>WhatsApp QR Login</title></head>
                <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#f0f2f5;margin:0;">
                    <div style="background:white;padding:30px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.1);text-align:center;">
                        <h2 style="color:#111;margin-top:0;">Scan with WhatsApp on 9892749953</h2>
                        <p style="color:#666;">Open WhatsApp on phone &rarr; Settings/Menu &rarr; <b>Linked Devices</b> &rarr; <b>Link a Device</b></p>
                        <img src="${qrImage}" style="width:280px;height:280px;border:1px solid #ddd;border-radius:8px;"/>
                        <p style="color:#888;font-size:12px;margin-bottom:0;">Auto-refreshes every 5 seconds</p>
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
    res.json({ connected: isConnected });
});

// Endpoint to send WhatsApp message
app.post('/send-message', async (req, res) => {
    const { to, message } = req.body;
    if (!to || !message) {
        return res.status(400).json({ error: 'Parameters "to" and "message" are required.' });
    }
    if (!isConnected || !sock) {
        return res.status(503).json({ error: 'WhatsApp is not connected yet. Please scan the QR code at /qr.' });
    }

    try {
        let formattedNumber = to.replace(/[^0-9]/g, '');
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
    console.log(`[WhatsApp Service] Server running on http://localhost:${PORT}`);
    connectToWhatsApp();
});
