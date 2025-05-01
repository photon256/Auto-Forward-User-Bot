import os
from dotenv import load_dotenv
import asyncio
import threading
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from settings import (
    setup_extra_handlers, load_initial_settings, is_admin,
    DEFAULT_ADMINS, get_all_target_channels, get_all_source_channels, 
    add_target_channel, remove_target_channel
)
from angel_db import (
    is_forwarded_for_target, mark_as_forwarded_for_target,
    collection, apply_replacements,
    add_replacement, remove_replacement, list_replacements,
    get_all_source_channels, add_source_channel, remove_source_channel
)

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
STATUS_URL = os.getenv("STATUS_URL")
PORT = int(os.getenv("PORT", 8080))

woodcraft = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
woodcraft.delay_seconds = 5
woodcraft.skip_next_message = False
app = Flask(__name__)
forwarding_enabled = True

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

            text = await apply_replacements(original_msg.text or "")

            print(f"➡️ Forwarding: {original_msg.id} to {target}")
            if original_msg.media:
                await woodcraft.send_file(
                    entity=target,
                    file=original_msg.media,
                    caption=text,
                    silent=True
                )
            else:
                await woodcraft.send_message(
                    entity=target,
                    message=text,
                    formatting_entities=original_msg.entities,
                    silent=True
                )

            await mark_as_forwarded_for_target(original_msg.id, target)
            forwarded = True
            await asyncio.sleep(woodcraft.delay_seconds)

        return forwarded
    except FloodWaitError as e:
        print(f"⏳ FloodWait: {e.seconds} seconds")
        await asyncio.sleep(e.seconds + 5)
        return await send_without_tag(original_msg)
    except Exception as e:
        print(f"🚨 Error: {str(e)}")
        return False

@woodcraft.on(events.NewMessage())
async def new_message_handler(event):
    global forwarding_enabled
    if not forwarding_enabled:
        return
    if woodcraft.skip_next_message:
        woodcraft.skip_next_message = False
        print("⏭️ Message skipped.")
        return

    source_channels = await get_all_source_channels()
    if event.is_channel and event.chat.id not in source_channels:
        return

    await asyncio.sleep(woodcraft.delay_seconds)
    await send_without_tag(event.message)

@woodcraft.on(events.NewMessage(pattern=r'^/status$'))
async def status(event):
    if not is_admin(event.sender_id):
        return await event.reply("❌ No permission!")

    status_text = "Active ✅" if forwarding_enabled else "Inactive ❌"
    total = collection.count_documents({})
    caption = (
        f"◉ Total Forwarded Files: `{total}`\n"
        f"◉ Status: {status_text}\n"
        f"◉ Delay: {woodcraft.delay_seconds}s\n"
        f"◉ Skip: {woodcraft.skip_next_message}\n\n"
        f"❖ 𝐖𝐎𝐎𝐃𝐜𝐫𝐚𝐟𝐭 ❖"
    )
    await woodcraft.send_file(event.chat_id, file=STATUS_URL, caption=caption)

@woodcraft.on(events.NewMessage(pattern=r'^/on$'))
async def on_handler(event):
    global forwarding_enabled
    if is_admin(event.sender_id):
        forwarding_enabled = True
        await event.reply("✅ Forwarding is on")

@woodcraft.on(events.NewMessage(pattern=r'^/off$'))
async def off_handler(event):
    global forwarding_enabled
    if is_admin(event.sender_id):
        forwarding_enabled = False
        await event.reply("❌ Forwarding is off")

# Target Channel Management
@woodcraft.on(events.NewMessage(pattern=r'^/addtarget\s+(-?\d+)$'))
async def addtarget_handler(event):
    if not is_admin(event.sender_id):
        return
    chat_id = int(event.pattern_match.group(1))
    await add_target_channel(chat_id)
    await event.reply(f"✅ Add target: `{chat_id}`")

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
    msg = "**🎯 Target channels:**\n" + "\n".join(f"`{tid}`" for tid in targets) if targets else "No targets!"
    await event.reply(msg)

# Source Channel Management
@woodcraft.on(events.NewMessage(pattern=r'^/addsource\s+(-?\d+)$'))
async def add_source_handler(event):
    if not is_admin(event.sender_id):
        return
    chat_id = int(event.pattern_match.group(1))
    await add_source_channel(chat_id)
    await event.reply(f"✅ Added source channel: `{chat_id}`")

@woodcraft.on(events.NewMessage(pattern=r'^/removesource\s+(-?\d+)$'))
async def remove_source_handler(event):
    if not is_admin(event.sender_id):
        return
    chat_id = int(event.pattern_match.group(1))
    await remove_source_channel(chat_id)
    await event.reply(f"❌ Removed source channel: `{chat_id}`")

@woodcraft.on(events.NewMessage(pattern=r'^/listsources$'))
async def list_sources_handler(event):
    sources = await get_all_source_channels()
    msg = "**📡 Source Channels:**\n" + "\n".join(f"`{cid}`" for cid in sources) if sources else "No sources set!"
    await event.reply(msg)

# Regex Replacement Management
@woodcraft.on(events.NewMessage(pattern=r'^/setreplace (.+?)\s*=>\s*(.+)$'))
async def set_replace_handler(event):
    if not is_admin(event.sender_id):
        return
    pattern, replacement = event.pattern_match.group(1), event.pattern_match.group(2)
    await add_replacement(pattern, replacement)
    await event.reply(f"✅ Set replacement:\n`{pattern}` => `{replacement}`")

@woodcraft.on(events.NewMessage(pattern=r'^/delreplace\s+(.+)$'))
async def del_replace_handler(event):
    if not is_admin(event.sender_id):
        return
    pattern = event.pattern_match.group(1)
    await remove_replacement(pattern)
    await event.reply(f"🗑️ Deleted replacement for pattern: `{pattern}`")

@woodcraft.on(events.NewMessage(pattern=r'^/listreplace$'))
async def list_replace_handler(event):
    if not is_admin(event.sender_id):
        return
    replacements = await list_replacements()
    if not replacements:
        return await event.reply("⚠️ No replacements set.")
    msg = "**✏️ Caption Replacements:**\n" + "\n".join(
        f"`{r['pattern']}` => `{r['replacement']}`" for r in replacements
    )
    await event.reply(msg)

@app.route("/")
def home():
    return "🤖 Angel Bot is running!", 200

async def main():
    await woodcraft.start()
    print("✅ Bot started!")
    await load_initial_settings(woodcraft)
    setup_extra_handlers(woodcraft)

    if not await get_all_target_channels():
        print("⚠️ No target channels. Use /addtarget.")
    if not await get_all_source_channels():
        print("⚠️ No source channels. Use /addsource.")

    await woodcraft.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": PORT}).start()
    asyncio.run(main())
