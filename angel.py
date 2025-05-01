import os
import re
import asyncio
import threading
from flask import Flask
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from settings import (
    setup_extra_handlers, load_initial_settings, is_admin,
    get_all_target_channels, add_target_channel, remove_target_channel, DEFAULT_ADMINS
)
from angel_db import is_forwarded_for_target, mark_as_forwarded_for_target, collection
from angel_db import db  # Add this line to access MongoDB directly

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
STATUS_URL = os.getenv("STATUS_URL")
SOURCE_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID"))
PORT = int(os.getenv("PORT", 8080))

woodcraft = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
woodcraft.delay_seconds = 5
woodcraft.skip_next_message = False
app = Flask(__name__)
forwarding_enabled = True

# MongoDB collection for replacements
replace_collection = db["replacements"]

def apply_replacements(text):
    if not text:
        return text
    all_rules = list(replace_collection.find({}))
    for rule in all_rules:
        try:
            text = re.sub(rule["pattern"], rule["replacement"], text)
        except Exception as e:
            print(f"Regex error: {e}")
    return text

async def send_without_tag(original_msg):
    try:
        targets = await get_all_target_channels()
        if not targets:
            print("⚠️ There is no target channel!")
            return False

        forwarded = False
        for target in targets:
            if await is_forwarded_for_target(original_msg.id, target):
                print(f"⏩ Skip: {original_msg.id} (Target: {target})")
                continue

            print(f"➡️ Forwarding: {original_msg.id} to {target}")
            caption = apply_replacements(original_msg.text)

            if original_msg.media:
                await woodcraft.send_file(
                    entity=target,
                    file=original_msg.media,
                    caption=caption,
                    silent=True
                )
            else:
                await woodcraft.send_message(
                    entity=target,
                    message=caption,
                    formatting_entities=original_msg.entities,
                    silent=True
                )

            await mark_as_forwarded_for_target(original_msg.id, target)
            forwarded = True
            await asyncio.sleep(woodcraft.delay_seconds)

        return forwarded
    except FloodWaitError as e:
        print(f"⏳ FloodWait: {e.seconds} সেকেন্ড অপেক্ষা করুন")
        await asyncio.sleep(e.seconds + 5)
        return await send_without_tag(original_msg)
    except Exception as e:
        print(f"🚨 Error: {str(e)}")
        return False

async def forward_old_messages():
    print("⏪ Start forwarding old messages...")
    async for message in woodcraft.iter_messages(SOURCE_CHAT_ID, reverse=True):
        if forwarding_enabled:
            await send_without_tag(message)
            await asyncio.sleep(woodcraft.delay_seconds)

async def forward_old_messages_to_new_target(new_target_id):
    print(f"🔄 Forward to new target: {new_target_id}")
    async for message in woodcraft.iter_messages(SOURCE_CHAT_ID, reverse=True):
        if await is_forwarded_for_target(message.id, new_target_id):
            continue
        try:
            caption = apply_replacements(message.text)
            if message.media:
                await woodcraft.send_file(
                    new_target_id,
                    file=message.media,
                    caption=caption,
                    silent=True
                )
            else:
                await woodcraft.send_message(
                    new_target_id,
                    caption,
                    formatting_entities=message.entities,
                    silent=True
                )
            await mark_as_forwarded_for_target(message.id, new_target_id)
            print(f"✅ {message.id} -> {new_target_id}")
            await asyncio.sleep(woodcraft.delay_seconds)
        except FloodWaitError as e:
            print(f"⏳ FloodWait: {e.seconds}s অপেক্ষা")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            print(f"🚨 Error: {str(e)}")
            break

# ========= Replacement Management ========= #
@woodcraft.on(events.NewMessage(pattern=r"^/setreplace\s+(.+?)\s*=>\s*(.+)$"))
async def set_replace_handler(event):
    if not is_admin(event.sender_id):
        return
    pattern, replacement = event.pattern_match.group(1).strip(), event.pattern_match.group(2).strip()
    replace_collection.update_one(
        {"pattern": pattern},
        {"$set": {"replacement": replacement}},
        upsert=True
    )
    await event.reply(f"✅ Regex Replacement Added:\n`{pattern}` => `{replacement}`")

@woodcraft.on(events.NewMessage(pattern=r"^/delreplace\s+(.+)$"))
async def del_replace_handler(event):
    if not is_admin(event.sender_id):
        return
    pattern = event.pattern_match.group(1).strip()
    result = replace_collection.delete_one({"pattern": pattern})
    if result.deleted_count:
        await event.reply(f"🗑️ Deleted replacement for pattern `{pattern}`")
    else:
        await event.reply(f"⚠️ No such replacement pattern found: `{pattern}`")

@woodcraft.on(events.NewMessage(pattern=r"^/replacelist$"))
async def list_replace_handler(event):
    if not is_admin(event.sender_id):
        return
    rules = list(replace_collection.find({}))
    if not rules:
        await event.reply("⚠️ No replacement rules found.")
    else:
        msg = "**🔁 Replacement Rules:**\n" + "\n".join(f"`{r['pattern']}` => `{r['replacement']}`" for r in rules)
        await event.reply(msg)

# ========= Bot Control & Utility ========= #
@woodcraft.on(events.NewMessage(pattern=r'^/status$'))
async def status(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ No permission!")
        return

    status = "Active ✅" if forwarding_enabled else "Inactive ❌"
    total_forwarded_files = collection.count_documents({})

    caption = (
        f"◉ Total Forwarded Files: `{total_forwarded_files}`\n"
        f"◉ Status: {status}\n"
        f"◉ Delay: {woodcraft.delay_seconds}s\n"
        f"◉ Skip: {woodcraft.skip_next_message}\n\n"
        f"❖ 𝐖𝐎𝐎𝐃𝐜𝐫𝐚𝐟𝐭 ❖"
    )

    await woodcraft.send_file(
        event.chat_id,
        file=STATUS_URL,
        caption=caption
    )

@woodcraft.on(events.NewMessage(pattern=r'^/off$'))
async def off_handler(event):
    global forwarding_enabled
    if not is_admin(event.sender_id):
        return
    forwarding_enabled = False
    await event.reply("❌ Forwarding is off")

@woodcraft.on(events.NewMessage(pattern=r'^/on$'))
async def on_handler(event):
    global forwarding_enabled
    if not is_admin(event.sender_id):
        return
    forwarding_enabled = True
    await event.reply("✅ Forwarding is on")

@woodcraft.on(events.NewMessage(pattern=r'^/addtarget\s+(-?\d+)$'))
async def addtarget_handler(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ No permission!")
        return
    chat_id = int(event.pattern_match.group(1))
    await add_target_channel(chat_id)
    await event.reply(f"✅ Add target: `{chat_id}`")
    await forward_old_messages_to_new_target(chat_id)

@woodcraft.on(events.NewMessage(pattern=r'^/removetarget\s+(-?\d+)$'))
async def removetarget_handler(event):
    if not is_admin(event.sender_id):
        return
    chat_id = int(event.pattern_match.group(1))
    await remove_target_channel(chat_id)
    await event.reply(f"❌ Target Remove: `{chat_id}`")

@woodcraft.on(events.NewMessage(pattern=r'^/listtargets$'))
async def list_targets_handler(event):
    targets = await get_all_target_channels()
    msg = "**🎯 Target channel:**\n" + "\n".join(f"`{tid}`" for tid in targets) if targets else "No target!"
    await event.reply(msg)

@woodcraft.on(events.NewMessage(pattern=r'^/count$'))
async def count_handler(event):
    total = collection.count_documents({})
    await event.reply(f"📊 Total Forwarded Files: `{total}`")

@woodcraft.on(events.NewMessage(chats=SOURCE_CHAT_ID))
async def new_message_handler(event):
    global forwarding_enabled
    if forwarding_enabled and not woodcraft.skip_next_message:
        await asyncio.sleep(woodcraft.delay_seconds)
        await send_without_tag(event.message)
    elif woodcraft.skip_next_message:
        print("⏭️ Message skipped.")
        woodcraft.skip_next_message = False

@app.route("/")
def home():
    return "🤖 Activate the Angel bot!", 200

async def main():
    await woodcraft.start()
    print("✅ Successfully Launch the bot!")
    await load_initial_settings(woodcraft)
    setup_extra_handlers(woodcraft)

    targets = await get_all_target_channels()
    if not targets:
        print("⚠️ /addtarget Use")

    asyncio.create_task(forward_old_messages())
    await woodcraft.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": PORT}).start()
    asyncio.run(main())
    
