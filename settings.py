import os
import sys
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telethon import events

from angel_db import settings_col, admin_col, extra_targets_col

load_dotenv()

WOODCRAFT_URL = os.getenv("WOODCRAFT_URL")
NOOR_URL = os.getenv("NOOR_URL")
DEFAULT_ADMINS = [int(x) for x in os.getenv("DEFAULT_ADMINS", "").split(",") if x.strip()]

# Target Channel Management
async def add_target_channel(chat_id):
    if not extra_targets_col.find_one({"chat_id": chat_id}):
        extra_targets_col.insert_one({"chat_id": chat_id})

async def remove_target_channel(chat_id):
    extra_targets_col.delete_one({"chat_id": chat_id})

async def get_all_target_channels():
    return [doc["chat_id"] for doc in extra_targets_col.find()]

# Admin Management
def is_admin(user_id):
    try:
        user_id = int(user_id)
        return user_id in DEFAULT_ADMINS or admin_col.find_one({"user_id": user_id})
    except:
        return False

def add_admin(user_id):
    user_id = int(user_id)
    admin_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

def remove_admin(user_id):
    user_id = int(user_id)
    admin_col.delete_one({"user_id": user_id})

# Event Command Handlers
def setup_extra_handlers(bot):
    @bot.on(events.NewMessage(pattern=r'^/setdelay (\d+)$'))
    async def set_delay(event):
        if not is_admin(event.sender_id): return
        seconds = int(event.pattern_match.group(1))
        settings_col.update_one({"key": "delay"}, {"$set": {"value": seconds}}, upsert=True)
        bot.delay_seconds = seconds
        await event.reply(f"⏱️ Delay set: {seconds}s")

    @bot.on(events.NewMessage(pattern=r'^/skip$'))
    async def skip_msg(event):
        if not is_admin(event.sender_id): return
        settings_col.update_one({"key": "skip_next"}, {"$set": {"value": True}}, upsert=True)
        bot.skip_next_message = True
        await event.reply("⏭️ Next message will be skipped")

    @bot.on(events.NewMessage(pattern=r'^/resume$'))
    async def resume(event):
        if not is_admin(event.sender_id): return
        settings_col.update_one({"key": "skip_next"}, {"$set": {"value": False}}, upsert=True)
        bot.skip_next_message = False
        await event.reply("▶️ Resumed forwarding")

    @bot.on(events.NewMessage(pattern=r'^/woodcraft$'))
    async def help_handler(event):
        if not is_admin(event.sender_id): return await event.reply("❌ Not allowed!")
        caption = "📋 Help text with all commands here..."
        await bot.send_file(event.chat_id, file=WOODCRAFT_URL, caption=caption, parse_mode='md')

    # AddAdmin, RemoveAdmin, ListAdmins, Restart, Noor handlers remain unchanged...

# Load Settings on Startup
async def load_initial_settings(bot):
    delay = settings_col.find_one({"key": "delay"})
    bot.delay_seconds = delay["value"] if delay else 5
    skip_next = settings_col.find_one({"key": "skip_next"})
    bot.skip_next_message = skip_next["value"] if skip_next else False
    
