import os
import asyncio
import threading
from dotenv import load_dotenv
from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

from settings import (
    setup_extra_handlers, load_initial_settings, is_admin,
    get_all_target_channels, add_target_channel, remove_target_channel,
    get_all_source_channels, add_source_channel, remove_source_channel
)
from angel_db import (
    is_forwarded_for_target, mark_as_forwarded_for_target,
    collection, apply_replacements,
    add_replacement, remove_replacement, list_replacements
)

# Load .env values
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
STATUS_URL = os.getenv("STATUS_URL")
PORT = int(os.getenv("PORT", 8080))

# Initialize bot and web server
woodcraft = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
woodcraft.delay_seconds = 5
woodcraft.skip_next_message = False
app = Flask(__name__)
forwarding_enabled = True

# Forwarding logic
async def send_without_tag(original_msg):
    try:
        targets = await get_all_target_channels()
        if not targets:
            print("⚠️ No target channels!")
            return False

        forwarded = False
        for target in targets:
            if await is_forwarded_for_target(original_msg.id, target):
                print(f"⏩ Skipped: {original_msg.id} (Target: {target})")
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
        print(f"⏳ FloodWait: {e.seconds}s")
        await asyncio.sleep(e.seconds + 5)
        return await send_without_tag(original_msg)

    except Exception as e:
        print(f"🚨 Error: {str(e)}")
        return False

# Message event
@woodcraft.on(events.NewMessage())
async def new_message_handler(event):
    global forwarding_enabled
    if not forwarding_enabled or woodcraft.skip_next_message:
        woodcraft.skip_next_message = False
        print("⏭️ Message skipped.")
        return

    source_channels = await get_all_source_channels()
    if event.is_channel and event.chat.id not in source_channels:
        return

    await asyncio.sleep(woodcraft.delay_seconds)
    await send_without_tag(event.message)

# Bot commands
@woodcraft.on(events.NewMessage(pattern=r'^/status$'))
async def status_handler(event):
    if not is_admin(event.sender_id):
        return await event.reply("❌ No permission!")
    status_text = "✅ Active" if forwarding_enabled else "❌ Inactive"
    total = collection.count_documents({})
    caption = (
        f"◉ Total Forwarded: `{total}`\n"
        f"◉ Status: {status_text}\n"
        f"◉ Delay: {woodcraft.delay_seconds}s\n"
        f"◉ Skip Next: {woodcraft.skip_next_message}\n\n"
        f"❖ 𝐖𝐎𝐎𝐃𝐜𝐫𝐚𝐟𝐭 ❖"
    )
    await woodcraft.send_file(event.chat_id, file=STATUS_URL, caption=caption)

@woodcraft.on(events.NewMessage(pattern=r'^/on$'))
async def on_handler(event):
    global forwarding_enabled
    if is_admin(event.sender_id):
        forwarding_enabled = True
        await event.reply("✅ Forwarding turned ON")

@woodcraft.on(events.NewMessage(pattern=r'^/off$'))
async def off_handler(event):
    global forwarding_enabled
    if is_admin(event.sender_id):
        forwarding_enabled = False
        await event.reply("❌ Forwarding turned OFF")

@woodcraft.on(events.NewMessage(pattern=r'^/skip$'))
async def skip_handler(event):
    if is_admin(event.sender_id):
        woodcraft.skip_next_message = True
        await event.reply("⏭️ Next message will be skipped.")

# Target channel management
@woodcraft.on(events.NewMessage(pattern=r'^/addtarget\s+(-?\d+)$'))
async def add_target(event):
    if is_admin(event.sender_id):
        chat_id = int(event.pattern_match.group(1))
        await add_target_channel(chat_id)
        await event.reply(f"✅ Target added: `{chat_id}`")

@woodcraft.on(events.NewMessage(pattern=r'^/removetarget\s+(-?\d+)$'))
async def remove_target(event):
    if is_admin(event.sender_id):
        chat_id = int(event.pattern_match.group(1))
        await remove_target_channel(chat_id)
        await event.reply(f"❌ Target removed: `{chat_id}`")

@woodcraft.on(events.NewMessage(pattern=r'^/listtargets$'))
async def list_targets(event):
    targets = await get_all_target_channels()
    msg = "**🎯 Target Channels:**\n" + "\n".join(f"`{tid}`" for tid in targets) if targets else "⚠️ No targets!"
    await event.reply(msg)

# Source channel management
@woodcraft.on(events.NewMessage(pattern=r'^/addsource\s+(-?\d+)$'))
async def add_source(event):
    if is_admin(event.sender_id):
        chat_id = int(event.pattern_match.group(1))
        await add_source_channel(chat_id)
        await event.reply(f"✅ Source added: `{chat_id}`")

@woodcraft.on(events.NewMessage(pattern=r'^/removesource\s+(-?\d+)$'))
async def remove_source(event):
    if is_admin(event.sender_id):
        chat_id = int(event.pattern_match.group(1))
        await remove_source_channel(chat_id)
        await event.reply(f"❌ Source removed: `{chat_id}`")

@woodcraft.on(events.NewMessage(pattern=r'^/listsources$'))
async def list_sources(event):
    sources = await get_all_source_channels()
    msg = "**📡 Source Channels:**\n" + "\n".join(f"`{cid}`" for cid in sources) if sources else "⚠️ No sources set!"
    await event.reply(msg)

# Regex caption replacements
@woodcraft.on(events.NewMessage(pattern=r'^/setreplace (.+?)\s*=>\s*(.+)$'))
async def set_replacement(event):
    if is_admin(event.sender_id):
        pattern, replacement = event.pattern_match.group(1), event.pattern_match.group(2)
        await add_replacement(pattern, replacement)
        await event.reply(f"✅ Added replacement:\n`{pattern}` => `{replacement}`")

@woodcraft.on(events.NewMessage(pattern=r'^/delreplace\s+(.+)$'))
async def delete_replacement(event):
    if is_admin(event.sender_id):
        pattern = event.pattern_match.group(1)
        await remove_replacement(pattern)
        await event.reply(f"🗑️ Removed pattern: `{pattern}`")

@woodcraft.on(events.NewMessage(pattern=r'^/listreplace$'))
async def list_replacement(event):
    if is_admin(event.sender_id):
        replacements = await list_replacements()
        if not replacements:
            return await event.reply("⚠️ No replacements set.")
        msg = "**✏️ Caption Replacements:**\n" + "\n".join(
            f"`{r['pattern']}` => `{r['replacement']}`" for r in replacements
        )
        await event.reply(msg)

# Flask app root
@app.route("/")
def home():
    return "🤖 Angel Bot is running!", 200

# Main entry
async def main():
    await woodcraft.start()
    print("✅ Bot started!")
    await load_initial_settings(woodcraft)
    setup_extra_handlers(woodcraft)

    if not await get_all_target_channels():
        print("⚠️ No target channels set. Use /addtarget.")
    if not await get_all_source_channels():
        print("⚠️ No source channels set. Use /addsource.")

    await woodcraft.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": PORT}).start()
    asyncio.run(main())
            
