import os
from typing import List, Dict
from datetime import datetime
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler
from telegram.constants import ParseMode

# MongoDB Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://0")
DB_NAME = "file_sharing_bot"

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "0")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Set your Telegram user ID
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "0"))  # Private channel ID for file storage

# Conversation states
GEN_WAITING_FILES, GEN_WAITING_TITLE, SEARCH_WAITING_INPUT, BROADCAST_WAITING_MESSAGE = range(4)

# Database setup
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
fsub_channels = db["fsub_channels"]
admins = db["admins"]
batches = db["batches"]
users = db["users"]

# Initialize owner as admin
admins.update_one({"user_id": OWNER_ID}, {"$set": {"user_id": OWNER_ID, "is_owner": True}}, upsert=True)


# Helper Functions
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    return admins.find_one({"user_id": user_id}) is not None


def get_fsub_channels() -> List[int]:
    return [channel["channel_id"] for channel in fsub_channels.find()]


async def check_fsub(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    channels = get_fsub_channels()
    for channel_id in channels:
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            continue
    return True


def generate_batch_link(batch_id: str) -> str:
    bot_username = "YourBotUsername"  # 🔴 CHANGE THIS to your bot username (without @)
    return f"https://t.me/{bot_username}?start=batch_{batch_id}"


def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📂 Browse"), KeyboardButton("🔍 Search")],
        [KeyboardButton("ℹ️ Info")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# Admin Commands
async def add_fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addfsub <channel_id>\nExample: /addfsub -1001234567890")
        return

    try:
        channel_id = int(context.args[0])
        fsub_channels.update_one({"channel_id": channel_id}, {"$set": {"channel_id": channel_id}}, upsert=True)
        await update.message.reply_text(f"✅ Force subscribe channel {channel_id} added successfully!")
    except ValueError:
        await update.message.reply_text("❌ Invalid channel ID. Please provide a valid integer.")


async def remove_fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removefsub <channel_id>")
        return

    try:
        channel_id = int(context.args[0])
        result = fsub_channels.delete_one({"channel_id": channel_id})
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ Force subscribe channel {channel_id} removed successfully!")
        else:
            await update.message.reply_text("❌ Channel not found in the list.")
    except ValueError:
        await update.message.reply_text("❌ Invalid channel ID.")


async def list_fsub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    channels = list(fsub_channels.find())
    if not channels:
        await update.message.reply_text("📋 No force subscribe channels configured.")
        return

    text = "📋 <b>Force Subscribe Channels:</b>\n\n"
    for ch in channels:
        text += f"• <code>{ch['channel_id']}</code>\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Only the owner can add admins.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return

    try:
        user_id = int(context.args[0])
        admins.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "is_owner": False}}, upsert=True)
        await update.message.reply_text(f"✅ User {user_id} added as admin!")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")


async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Only the owner can remove admins.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return

    try:
        user_id = int(context.args[0])
        if user_id == OWNER_ID:
            await update.message.reply_text("❌ Cannot remove the owner!")
            return
        result = admins.delete_one({"user_id": user_id})
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ User {user_id} removed from admins!")
        else:
            await update.message.reply_text("❌ User not found in admin list.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")


async def list_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    admin_list = list(admins.find())
    if not admin_list:
        await update.message.reply_text("📋 No admins found.")
        return

    text = "📋 <b>Admin List:</b>\n\n"
    for admin in admin_list:
        role = "👑 Owner" if admin.get("is_owner") else "🛡️ Admin"
        text += f"• {role}: <code>{admin['user_id']}</code>\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# Generate Batch
async def gen_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    context.user_data["batch_files"] = []
    context.user_data["file_counts"] = {"audio": 0, "video": 0, "document": 0, "photo": 0}
    
    keyboard = [[InlineKeyboardButton("✅ Done", callback_data="gen_done")]]
    await update.message.reply_text(
        "📤 <b>Send me the files you want to add to this batch.</b>\n\n"
        "When you're done, click the Done button below.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return GEN_WAITING_FILES


async def gen_receive_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    # Forward file to storage channel
    forwarded = await message.forward(STORAGE_CHANNEL_ID)
    
    file_type = None
    if message.audio:
        file_type = "audio"
        context.user_data["file_counts"]["audio"] += 1
    elif message.video:
        file_type = "video"
        context.user_data["file_counts"]["video"] += 1
    elif message.document:
        file_type = "document"
        context.user_data["file_counts"]["document"] += 1
    elif message.photo:
        file_type = "photo"
        context.user_data["file_counts"]["photo"] += 1
    
    context.user_data["batch_files"].append({
        "message_id": forwarded.message_id,
        "type": file_type
    })
    
    return GEN_WAITING_FILES


async def gen_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    files = context.user_data.get("batch_files", [])
    counts = context.user_data.get("file_counts", {})
    
    if not files:
        await query.edit_message_text("❌ No files received. Operation cancelled.")
        return ConversationHandler.END
    
    count_text = "\n".join([f"• {k.title()}: {v}" for k, v in counts.items() if v > 0])
    
    await query.edit_message_text(
        f"📊 <b>Files Received:</b>\n\n{count_text}\n\n"
        f"Total files: {len(files)}\n\n"
        "📝 Now send me the title for this batch:",
        parse_mode=ParseMode.HTML
    )
    return GEN_WAITING_TITLE


async def gen_receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    files = context.user_data.get("batch_files", [])
    
    # Create batch in database
    batch_data = {
        "title": title,
        "files": files,
        "created_by": update.effective_user.id,
        "created_at": datetime.now(),
        "views": 0
    }
    
    result = batches.insert_one(batch_data)
    batch_id = str(result.inserted_id)
    link = generate_batch_link(batch_id)
    
    await update.message.reply_text(
        f"✅ <b>Batch created successfully!</b>\n\n"
        f"📝 Title: {title}\n"
        f"📁 Files: {len(files)}\n\n"
        f"🔗 Share Link:\n<code>{link}</code>",
        parse_mode=ParseMode.HTML
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def list_batches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    
    batch_list = list(batches.find().sort("created_at", -1).limit(20))
    
    if not batch_list:
        await update.message.reply_text("📋 No batches found.")
        return
    
    keyboard = []
    for batch in batch_list:
        batch_id = str(batch["_id"])
        keyboard.append([InlineKeyboardButton(
            f"📦 {batch['title']}", 
            callback_data=f"batch_view_{batch_id}"
        )])
    
    await update.message.reply_text(
        "📋 <b>All Batches:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )


async def batch_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    batch_id = query.data.split("_")[2]
    
    try:
        from bson import ObjectId
        batch = batches.find_one({"_id": ObjectId(batch_id)})
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")
        return
    
    if not batch:
        await query.edit_message_text("❌ Batch not found.")
        return
    
    link = generate_batch_link(batch_id)
    
    keyboard = [
        [
            InlineKeyboardButton("✏️ Edit Title", callback_data=f"batch_edit_{batch_id}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"batch_delete_{batch_id}")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="batch_list")]
    ]
    
    await query.edit_message_text(
        f"📦 <b>Batch Details:</b>\n\n"
        f"📝 Title: {batch['title']}\n"
        f"📁 Files: {len(batch['files'])}\n"
        f"👁️ Views: {batch.get('views', 0)}\n\n"
        f"🔗 Link: <code>{link}</code>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )


async def batch_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    batch_id = query.data.split("_")[2]
    
    await query.edit_message_text(
        "✏️ Send me the new title for this batch:",
        parse_mode=ParseMode.HTML
    )
    
    # Store batch_id in user_data for the next message
    context.user_data["editing_batch_id"] = batch_id


async def batch_edit_receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is editing a batch
    batch_id = context.user_data.get("editing_batch_id")
    
    if not batch_id:
        return
    
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized.")
        return
    
    new_title = update.message.text.strip()
    
    try:
        from bson import ObjectId
        result = batches.update_one(
            {"_id": ObjectId(batch_id)},
            {"$set": {"title": new_title}}
        )
        
        if result.modified_count > 0:
            await update.message.reply_text(
                f"✅ Batch title updated to: <b>{new_title}</b>",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text("❌ Batch not found or title unchanged.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    
    # Clear the editing state
    context.user_data.pop("editing_batch_id", None)


async def batch_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    batch_id = query.data.split("_")[2]
    
    try:
        from bson import ObjectId
        result = batches.delete_one({"_id": ObjectId(batch_id)})
        if result.deleted_count > 0:
            await query.edit_message_text("✅ Batch deleted successfully!")
        else:
            await query.edit_message_text("❌ Batch not found.")
    except Exception as e:
        await query.edit_message_text(f"❌ Error deleting batch: {str(e)}")


async def batch_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    batch_list = list(batches.find().sort("created_at", -1).limit(20))
    
    if not batch_list:
        await query.edit_message_text("📋 No batches found.")
        return
    
    keyboard = []
    for batch in batch_list:
        batch_id = str(batch["_id"])
        keyboard.append([InlineKeyboardButton(
            f"📦 {batch['title']}", 
            callback_data=f"batch_view_{batch_id}"
        )])
    
    await query.edit_message_text(
        "📋 <b>All Batches:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )


# User Side
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Check if user is new
    existing_user = users.find_one({"user_id": user.id})
    is_new_user = existing_user is None
    
    users.update_one(
        {"user_id": user.id},
        {"$set": {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "last_active": datetime.now()
        }},
        upsert=True
    )
    
    # Notify admins about new user
    if is_new_user:
        total_users = users.count_documents({})
        admin_list = list(admins.find())
        
        notification = (
            f"👤 <b>New User Joined!</b>\n\n"
            f"📊 User Count: <b>{total_users}</b>\n"
            f"👤 Name: {user.first_name} {user.last_name or ''}\n"
            f"🆔 Username: @{user.username or 'N/A'}\n"
            f"💬 Chat ID: <code>{user.id}</code>"
        )
        
        for admin in admin_list:
            try:
                await context.bot.send_message(
                    chat_id=admin["user_id"],
                    text=notification,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print(f"Error notifying admin {admin['user_id']}: {e}")
    
    # Check if starting with batch link
    if context.args and context.args[0].startswith("batch_"):
        batch_id = context.args[0][6:]
        await send_batch_files(update, context, batch_id)
        return
    
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        "Use the buttons below to browse or search for files.",
        reply_markup=get_main_keyboard()
    )


async def send_batch_files(update: Update, context: ContextTypes.DEFAULT_TYPE, batch_id: str):
    user_id = update.effective_user.id
    
    # Check force subscribe - check each channel individually
    channels = get_fsub_channels()
    not_joined = []
    
    for ch_id in channels:
        try:
            member = await context.bot.get_chat_member(ch_id, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_joined.append(ch_id)
        except Exception:
            not_joined.append(ch_id)
    
    if not_joined:
        keyboard = []
        for ch_id in not_joined:
            try:
                chat = await context.bot.get_chat(ch_id)
                invite_link = f"https://t.me/{chat.username}" if chat.username else await context.bot.export_chat_invite_link(ch_id)
                keyboard.append([InlineKeyboardButton(f"Join {chat.title}", url=invite_link)])
            except Exception as e:
                print(f"Error getting channel info: {e}")
        
        keyboard.append([InlineKeyboardButton("✅ I Joined All", callback_data=f"check_fsub_{batch_id}")])
        
        await update.message.reply_text(
            "⚠️ You must join the following channels to access files:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        from bson import ObjectId
        batch = batches.find_one({"_id": ObjectId(batch_id)})
    except:
        await update.message.reply_text("❌ Invalid batch link.")
        return
    
    if not batch:
        await update.message.reply_text("❌ Batch not found.")
        return
    
    # Update views
    batches.update_one({"_id": batch["_id"]}, {"$inc": {"views": 1}})
    
    await update.message.reply_text(f"📦 <b>{batch['title']}</b>\n\nSending files...", parse_mode=ParseMode.HTML)
    
    for file_data in batch["files"]:
        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=STORAGE_CHANNEL_ID,
                message_id=file_data["message_id"]
            )
        except Exception as e:
            print(f"Error sending file: {e}")


async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check force subscribe
    channels = get_fsub_channels()
    not_joined = []
    
    for ch_id in channels:
        try:
            member = await context.bot.get_chat_member(ch_id, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_joined.append(ch_id)
        except Exception:
            not_joined.append(ch_id)
    
    if not_joined:
        keyboard = []
        for ch_id in not_joined:
            try:
                chat = await context.bot.get_chat(ch_id)
                invite_link = f"https://t.me/{chat.username}" if chat.username else await context.bot.export_chat_invite_link(ch_id)
                keyboard.append([InlineKeyboardButton(f"Join {chat.title}", url=invite_link)])
            except Exception as e:
                print(f"Error getting channel info: {e}")
        
        keyboard.append([InlineKeyboardButton("✅ I Joined All", callback_data="check_browse")])
        
        await update.message.reply_text(
            "⚠️ You must join the following channels to browse files:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    batch_list = list(batches.find().sort("created_at", -1).limit(20))
    
    if not batch_list:
        await update.message.reply_text("📋 No files available yet.")
        return
    
    keyboard = []
    for batch in batch_list:
        batch_id = str(batch["_id"])
        keyboard.append([InlineKeyboardButton(
            f"📦 {batch['title']}", 
            callback_data=f"user_batch_{batch_id}"
        )])
    
    await update.message.reply_text(
        "📂 <b>Browse Files:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )


async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Send me a search query:")
    return SEARCH_WAITING_INPUT


async def search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()
    
    # Search in titles
    results = list(batches.find({"title": {"$regex": query_text, "$options": "i"}}).limit(20))
    
    if not results:
        await update.message.reply_text("❌ No results found.")
        return ConversationHandler.END
    
    keyboard = []
    for batch in results:
        batch_id = str(batch["_id"])
        keyboard.append([InlineKeyboardButton(
            f"📦 {batch['title']}", 
            callback_data=f"user_batch_{batch_id}"
        )])
    
    await update.message.reply_text(
        f"🔍 <b>Search Results for '{query_text}':</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


async def check_browse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Check if user joined all channels
    channels = get_fsub_channels()
    not_joined = []
    
    for ch_id in channels:
        try:
            member = await context.bot.get_chat_member(ch_id, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_joined.append(ch_id)
        except Exception:
            not_joined.append(ch_id)
    
    if not_joined:
        await query.answer("❌ Please join all channels first!", show_alert=True)
        return
    
    # User joined, show browse list
    batch_list = list(batches.find().sort("created_at", -1).limit(20))
    
    if not batch_list:
        await query.edit_message_text("📋 No files available yet.")
        return
    
    keyboard = []
    for batch in batch_list:
        batch_id = str(batch["_id"])
        keyboard.append([InlineKeyboardButton(
            f"📦 {batch['title']}", 
            callback_data=f"user_batch_{batch_id}"
        )])
    
    await query.edit_message_text(
        "📂 <b>Browse Files:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )


async def user_batch_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    batch_id = query.data.split("_")[2]
    link = generate_batch_link(batch_id)
    
    keyboard = [[InlineKeyboardButton("📥 Get Files", url=link)]]
    
    try:
        from bson import ObjectId
        batch = batches.find_one({"_id": ObjectId(batch_id)})
        
        if batch:
            await query.message.reply_text(
                f"📦 <b>{batch['title']}</b>\n\n"
                f"📁 Files: {len(batch['files'])}\n\n"
                f"Click the button below to get files:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        else:
            await query.message.reply_text("❌ Batch not found.")
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {str(e)}")


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ <b>Bot Information:</b>\n\n"
        "👨‍💻 Bot Made By: <b>Rehan</b>\n"
        "📢 Channel: @DrSudo",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    
    commands_text = """
🤖 <b>Admin Commands:</b>

<b>Force Subscribe Management:</b>
/addfsub &lt;channel_id&gt; - Add force subscribe channel
/removefsub &lt;channel_id&gt; - Remove force subscribe channel
/listfsub - List all force subscribe channels

<b>Admin Management:</b>
/addadmin &lt;user_id&gt; - Add new admin (Owner only)
/removeadmin &lt;user_id&gt; - Remove admin (Owner only)
/listadmin - Show all admins

<b>Batch Management:</b>
/gen - Generate new file batch
/list - View all batches

<b>Bot Stats & Management:</b>
/dashboard - View bot statistics
/broadcast - Broadcast message to all users
/cmd - Show this command list
"""
    
    await update.message.reply_text(commands_text, parse_mode=ParseMode.HTML)


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    
    # Get statistics
    total_users = users.count_documents({})
    total_batches = batches.count_documents({})
    total_files = sum([len(batch.get("files", [])) for batch in batches.find()])
    total_fsub = fsub_channels.count_documents({})
    total_admins = admins.count_documents({})
    
    dashboard_text = f"""
📊 <b>Bot Dashboard</b>

👥 Total Users: <b>{total_users}</b>
📦 Total Batches: <b>{total_batches}</b>
📁 Total Files: <b>{total_files}</b>
📢 Force Subscribe Channels: <b>{total_fsub}</b>
🛡️ Total Admins: <b>{total_admins}</b>
"""
    
    await update.message.reply_text(dashboard_text, parse_mode=ParseMode.HTML)


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📢 <b>Broadcast Message</b>\n\n"
        "Send me the message you want to broadcast to all users.\n"
        "You can send text, photos, videos, or any media.\n\n"
        "Use /cancel to cancel the broadcast.",
        parse_mode=ParseMode.HTML
    )
    return BROADCAST_WAITING_MESSAGE


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    all_users = list(users.find())
    
    status_msg = await update.message.reply_text("📤 Broadcasting message...")
    
    success = 0
    failed = 0
    blocked = 0
    
    for user in all_users:
        try:
            await message.copy(chat_id=user["user_id"])
            success += 1
        except Exception as e:
            if "blocked" in str(e).lower():
                blocked += 1
            else:
                failed += 1
    
    await status_msg.edit_text(
        f"✅ <b>Broadcast Completed!</b>\n\n"
        f"✅ Success: {success}\n"
        f"🚫 Blocked: {blocked}\n"
        f"❌ Failed: {failed}\n"
        f"📊 Total: {len(all_users)}",
        parse_mode=ParseMode.HTML
    )
    
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Broadcast cancelled.")
    return ConversationHandler.END


async def check_fsub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    batch_id = query.data.split("_")[2]
    user_id = query.from_user.id
    
    # Check if user joined all channels
    channels = get_fsub_channels()
    not_joined = []
    
    for ch_id in channels:
        try:
            member = await context.bot.get_chat_member(ch_id, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                not_joined.append(ch_id)
        except Exception:
            not_joined.append(ch_id)
    
    if not_joined:
        await query.answer("❌ Please join all channels first!", show_alert=True)
        return
    
    # User joined all channels, send files
    try:
        from bson import ObjectId
        batch = batches.find_one({"_id": ObjectId(batch_id)})
    except:
        await query.edit_message_text("❌ Invalid batch link.")
        return
    
    if not batch:
        await query.edit_message_text("❌ Batch not found.")
        return
    
    # Update views
    batches.update_one({"_id": batch["_id"]}, {"$inc": {"views": 1}})
    
    await query.edit_message_text(f"📦 <b>{batch['title']}</b>\n\nSending files...", parse_mode=ParseMode.HTML)
    
    for file_data in batch["files"]:
        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=STORAGE_CHANNEL_ID,
                message_id=file_data["message_id"]
            )
        except Exception as e:
            print(f"Error sending file: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Check if editing batch title
    if context.user_data.get("editing_batch_id"):
        await batch_edit_receive_title(update, context)
        return
    
    if text == "📂 Browse":
        await browse(update, context)
    elif text == "🔍 Search":
        await search_start(update, context)
    elif text == "ℹ️ Info":
        await info(update, context)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Admin handlers
    app.add_handler(CommandHandler("addfsub", add_fsub))
    app.add_handler(CommandHandler("removefsub", remove_fsub))
    app.add_handler(CommandHandler("listfsub", list_fsub))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("listadmin", list_admin))
    app.add_handler(CommandHandler("list", list_batches))
    app.add_handler(CommandHandler("cmd", cmd_list))
    app.add_handler(CommandHandler("dashboard", dashboard))
    
    # Gen conversation handler
    gen_handler = ConversationHandler(
        entry_points=[CommandHandler("gen", gen_start)],
        states={
            GEN_WAITING_FILES: [
                MessageHandler(filters.ALL & ~filters.COMMAND, gen_receive_files),
                CallbackQueryHandler(gen_done, pattern="^gen_done$")
            ],
            GEN_WAITING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, gen_receive_title)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    app.add_handler(gen_handler)
    
    # Broadcast conversation handler
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_WAITING_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_send)]
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    app.add_handler(broadcast_handler)
    
    # Search conversation handler
    search_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔍 Search$"), search_start)],
        states={
            SEARCH_WAITING_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_query)]
        },
        fallbacks=[],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    app.add_handler(search_handler)
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(batch_view, pattern="^batch_view_"))
    app.add_handler(CallbackQueryHandler(batch_edit, pattern="^batch_edit_"))
    app.add_handler(CallbackQueryHandler(batch_delete, pattern="^batch_delete_"))
    app.add_handler(CallbackQueryHandler(batch_list_callback, pattern="^batch_list$"))
    app.add_handler(CallbackQueryHandler(user_batch_view, pattern="^user_batch_"))
    app.add_handler(CallbackQueryHandler(check_fsub_callback, pattern="^check_fsub_"))
    app.add_handler(CallbackQueryHandler(check_browse_callback, pattern="^check_browse$"))
    
    # User handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()