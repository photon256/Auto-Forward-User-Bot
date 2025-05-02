import os
import asyncio
import threading
import logging
from flask import Flask
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

from settings import (
    setup_extra_handlers,
    load_initial_settings,
    is_admin,
    get_all_target_channels,
    add_target_channel,
    remove_target_channel
)
from angel_db import (
    is_forwarded_for_target,
    mark_as_forwarded_for_target,
    collection
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='[%(levelname)s %(asctime)s] %(name)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram API credentials
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
STATUS_URL = os.getenv("STATUS_URL")
SOURCE_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID"))
PORT = int(os.getenv("PORT", 8080))

# Initialize Telegram client
woodcraft = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
woodcraft.delay_seconds = 5
woodcraft.skip_next_message = False
forwarding_enabled = True

# Initialize Flask app
app = Flask(__name__)

async def send_without_tag(original_msg):
    try:
        targets = await get_all_target_channels()
        if not targets:
            logger.warning("No target channels configured.")
            return False

        forwarded = False
        for target in targets:
            if await is_forwarded_for_target(original_msg.id, target):
                logger.info(f"Message {original_msg.id} already forwarded to {target}. Skipping.")
                continue

            logger.info(f"Forwarding message {original_msg.id} to {target}.")

            if original_msg.media:
                await woodcraft.send_file(
                    entity=target,
                    file=original_msg.media,
                    caption=original_msg.text,
                    silent=True
                )
            else:
                await woodcraft.send_message(
                    entity=target,
                    message=original_msg.text,
                    formatting_entities=original_msg.entities,
                    silent=True
                )

            await mark_as_forwarded_for_target(original_msg.id, target)
            forwarded = True
            await asyncio.sleep(woodcraft.delay_seconds)

        return forwarded

    except FloodWaitError as e:
        logger.warning(f"FloodWaitError: Waiting for {e.seconds} seconds.")
        await asyncio.sleep(e.seconds + 5)
        return await send_without_tag(original_msg)
    except Exception as e:
        logger.error(f"Error in send_without_tag: {str(e)}")
        return False

async def forward_old_messages():
    logger.info("Starting to forward old messages...")
    async for message in woodcraft.iter_messages(SOURCE_CHAT_ID, reverse=True):
        if forwarding_enabled:
            await send_without_tag(message)
            await asyncio.sleep(woodcraft.delay_seconds)

async def forward_old_messages_to_new_target(new_target_id):
    logger.info(f"Forwarding old messages to new target: {new_target_id}")
    async for message in woodcraft.iter_messages(SOURCE_CHAT_ID, reverse=True):
        if await is_forwarded_for_target(message.id, new_target_id):
            continue
        try:
            if message.media:
                await woodcraft.send_file(
                    new_target_id,
                    file=message.media,
                    caption=message.text,
                    silent=True
                )
            else:
                await woodcraft.send_message(
                    new_target_id,
                    message=message.text,
                    formatting_entities=message.entities,
                    silent=True
                )
            await mark_as_forwarded_for_target(message.id, new_target_id)
            logger.info(f"Message {message.id} forwarded to {new_target_id}")
            await asyncio.sleep(woodcraft.delay_seconds)
        except FloodWaitError as e:
            logger.warning(f"FloodWaitError: Waiting for {e.seconds} seconds.")
            await asyncio.sleep(e.seconds + 5)
        except Exception as e:
            logger.error(f"Error forwarding message {message.id} to {new_target_id}: {str(e)}")
            break

@woodcraft.on(events.NewMessage(pattern=r'^/status$'))
async def status(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ No permission!")
        return

    status_text = "Active ✅" if forwarding_enabled else "Inactive ❌"
    total_forwarded_files = collection.count_documents({})

    caption = (
        f"◉ Total Forwarded Files: `{total_forwarded_files}`\n"
        f"◉ Status: {status_text}\n"
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
    await event.reply(f"✅ Added target: `{chat_id}`")
    await forward_old_messages_to_new_target(chat_id)

@woodcraft.on(events.NewMessage(pattern=r'^/removetarget\s+(-?\d+)$'))
async def removetarget_handler(event):
    if not is_admin(event.sender_id):
        return
    chat_id = int(event.pattern_match.group(1))
    await remove_target_channel(chat_id)
    await event.reply(f"❌ Removed target: `{chat_id}`")

@woodcraft.on(events.NewMessage(pattern=r'^/listtargets$'))
async def list_targets_handler(event):
    targets = await get_all_target_channels()
    if targets:
        msg = "**🎯 Target channels:**\n" + "\n".join(f"`{tid}`" for tid in targets)
    else:
        msg = "No target channels configured."
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
        logger.info("Message skipped.")
        woodcraft.skip_next_message = False

@app.route("/")
def home():
    return "🤖 Angel bot is active!", 200

async def main():
    await woodcraft.start()
    logger.info("Bot started successfully.")
    await load_initial_settings(woodcraft)
    setup_extra_handlers(woodcraft)

    targets = await get_all_target_channels()
    if not targets:
        logger.warning("No target channels configured. Use /addtarget to add.")

    asyncio.create_task(forward_old_messages())
    await woodcraft.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": PORT}).start()
    asyncio.run(main())
