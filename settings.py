import os
import sys
import asyncio
import aiohttp
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import events
from angel_db import collection
from angel_db import settings_col, admin_col, extra_targets_col

load_dotenv()

# ================= Configuration =================
WOODCRAFT_URL = os.getenv("WOODCRAFT_URL")
NOOR_URL = os.getenv("NOOR_URL")
DEFAULT_ADMINS = [int(x) for x in os.getenv("DEFAULT_ADMINS", "").split(",") if x.strip()]

# ================== Functions ====================
async def get_source_chat_ids():
    ids = os.getenv("SOURCE_CHAT_IDS", "")
    return [int(x.strip()) for x in ids.split(",") if x.strip()]

async def add_target_channel(chat_id):
    if not extra_targets_col.find_one({"chat_id": chat_id}):
        extra_targets_col.insert_one({"chat_id": chat_id})

async def remove_target_channel(chat_id):
    extra_targets_col.delete_one({"chat_id": chat_id})

async def get_all_target_channels():
    return [doc["chat_id"] for doc in extra_targets_col.find()]

def is_admin(user_id):
    try:
        user_id = int(user_id)
        return user_id in DEFAULT_ADMINS or admin_col.find_one({"user_id": user_id})
    except:
        return False

def add_admin(user_id):
    try:
        user_id = int(user_id)
        admin_col.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id}},
            upsert=True
        )
    except Exception as e:
        print(f"Add admin error: {e}")

def remove_admin(user_id):
    try:
        user_id = int(user_id)
        admin_col.delete_one({"user_id": user_id})
    except Exception as e:
        print(f"Remove admin error: {e}")

# ================= Word Replacement Functions =================
async def set_caption_replacement(event, new_word, replacement_word):
    """ Set a word replacement for captions """
    if not is_admin(event.sender_id):
        return await event.reply("❌ You are not an admin.")
    
    # Add the replacement to the database
    settings_col.update_one(
        {"key": "caption_replacements"},
        {"$push": {"value": {"pattern": new_word, "replacement": replacement_word}}},
        upsert=True
    )
    await event.reply(f"✅ Set replacement for `{new_word}` to `{replacement_word}`.")

async def get_caption_replacements():
    """ Fetch all word replacements from the database """
    replacement_data = settings_col.find_one({"key": "caption_replacements"})
    return replacement_data["value"] if replacement_data else []

def apply_caption_replacements(caption_text):
    """ Apply all replacements to the given caption text """
    replacements = await get_caption_replacements()
    for repl in replacements:
        pattern = repl["pattern"]
        replacement = repl["replacement"]
        caption_text = re.sub(pattern, replacement, caption_text)
    return caption_text

# ================= Event Handlers =================
def setup_extra_handlers(woodcraft):
    @woodcraft.on(events.NewMessage(pattern=r'^/setdelay (\d+)$'))
    async def set_delay(event):
        if not is_admin(event.sender_id):
            return
        seconds = int(event.pattern_match.group(1))
        settings_col.update_one(
            {"key": "delay"},
            {"$set": {"value": seconds}},
            upsert=True
        )
        woodcraft.delay_seconds = seconds
        await event.reply(f"⏱️ Delay set: {seconds}s")

    @woodcraft.on(events.NewMessage(pattern=r'^/skip$'))
    async def skip_msg(event):
        if not is_admin(event.sender_id):
            return
        settings_col.update_one(
            {"key": "skip_next"},
            {"$set": {"value": True}},
            upsert=True
        )
        woodcraft.skip_next_message = True
        await event.reply("⏭️ The next message will be skipped")

    @woodcraft.on(events.NewMessage(pattern=r'^/resume$'))
    async def resume(event):
        if not is_admin(event.sender_id):
            return
        settings_col.update_one(
            {"key": "skip_next"},
            {"$set": {"value": False}},
            upsert=True
        )
        woodcraft.skip_next_message = False
        await event.reply("▶️ Forwarding is on")

    @woodcraft.on(events.NewMessage(pattern=r'^/setreplace (.+) to (.+)$'))
    async def handle_caption_replace(event):
        if not is_admin(event.sender_id):
            return await event.reply("❌ You are not an admin.")
        
        old_word = event.pattern_match.group(1)
        new_word = event.pattern_match.group(2)
        await set_caption_replacement(event, old_word, new_word)

    @woodcraft.on(events.NewMessage(pattern=r'^/woodcraft$'))
    async def woodcraft_handler(event):
        if not is_admin(event.sender_id):
            await event.reply("❌ Not allowed!")
            return

        caption = """
        **🔧 All commands list 🌟**

        ```👉 Click to copy command```

        /status `/status`
        ```⚡ View bot status```

        /setdelay [Sec] `/setdelay`
        ```⏱️ Set the delay time.```

        /skip `/skip`
        ```🛹 Skip to next message```

        /resume `/resume`
        ```🏹 Start forwarding```

        /on `/on`
        ```✅ Launch the bot```

        /off `/off`
        ```📴 Close the bot```

        /addtarget [ID] `/addtarget`
        ```✅ Add target```

        /removetarget [ID] `/removetarget`
        ```😡 Remove target```

        /listtargets `/listtargets`
        ```🆔 View Target ID```

        ```✅ How to Use:
        Reply to a user’s message and send the command:   
        /addadmin```

        /addadmin `/addadmin`
        ```➕ Promote a user to admin (non-permanent).```

        /removeadmin `/removeadmin`
        ```➖ Remove a user from admin who was added using /addadmin.```

        /listadmins `/listadmins`
        ```📋 View the list of all current admins (both from .env and database).```

        /noor `/noor`
        ```👀 Shows a detailed status report including:```

        /count `/count`
        ```📊 Total Forwarded Files```

        /restart `/restart`
        ```♻️ Restarts the bot safely.```

        🖤⃝💔 𝐖𝐎𝐎𝐃𝐂𝐫𝐚𝐟𝐭 🖤⃝💔
        """

        await woodcraft.send_file(
            event.chat_id,
            file=WOODCRAFT_URL,
            caption=caption,
            parse_mode='md'
        )

    @woodcraft.on(events.NewMessage(pattern=r'^/restart$'))
    async def restart_bot(event):
        if not is_admin(event.sender_id):
            return await event.reply("❌ You are not an admin.")
        await event.reply("♻️ Successfully restarting bot ✅")
        await asyncio.sleep(2)
        sys.exit(0)

# ============ Initial Settings Loader ============
async def load_initial_settings(woodcraft):
    delay = settings_col.find_one({"key": "delay"})
    woodcraft.delay_seconds = delay["value"] if delay else 5

    skip_next = settings_col.find_one({"key": "skip_next"})
    woodcraft.skip_next_message = skip_next["value"] if skip_next else False
    
