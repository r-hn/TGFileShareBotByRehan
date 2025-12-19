
# 🚀 Telegram FileShare Bot By Rehan

A powerful **Telegram File Sharing Bot** using Python + MongoDB that allows admins to create **batch-based share links** and distribute files securely via Telegram.

---

## ⚠️ IMPORTANT CONFIG (READ THIS)

Inside `FileShareMongoDB.py`, you **MUST** change:

```python
bot_username = "YourBotUsername"
```

➡ Replace it with your actual bot username (without `@`)  
This is required to generate **correct shareable batch links**.

---

## ✨ Features
- Batch-based file sharing
- Auto-generated Telegram links
- MongoDB powered
- Force Subscribe (FSUB)
- Admin & Owner system
- Browse & Search
- Broadcast messages
- Dashboard & statistics

---

## 📦 Installation

```bash
pip install python-telegram-bot pymongo dnspython
```

---

## ⚙️ Environment Variables

```env
BOT_TOKEN=YOUR_BOT_TOKEN
OWNER_ID=YOUR_TELEGRAM_USER_ID
MONGO_URI=YOUR_MONGODB_URI
STORAGE_CHANNEL_ID=PRIVATE_CHANNEL_ID
```

---

## ▶️ Run the Bot

```bash
python FileShareMongoDB.py
```

---

## 👮 Admin Commands

### Batch
/gen → Create new file batch  
/list → List batches  

### Force Subscribe
/addfsub <channel_id>  
/removefsub <channel_id>  
/listfsub  

### Admin Control
/addadmin <user_id>  
/removeadmin <user_id>  
/listadmin  

### Management
/dashboard  
/broadcast  
/cmd  

---

## 👤 User Commands
/start  
📂 Browse  
🔍 Search  
ℹ️ Info  

---

## 🔐 Security
- Files stored only on Telegram
- MongoDB stores metadata only
- Force Subscribe prevents leeching

---

## 👨‍💻 Author
**Rehan**  
Telegram: @DrSudo
