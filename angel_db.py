import os
import re
from pymongo import MongoClient

client = MongoClient(os.getenv("MONGODB_URI"))
db = client.get_default_database()

# Collections
settings_col = db["settings"]
replacements_col = db["replacements"]
forwarded_col = db["forwarded_messages"]

# ---------------- Target Channels ---------------- #

async def get_all_target_channels():
    doc = settings_col.find_one({"_id": "channels"})
    return doc.get("targets", []) if doc else []

async def add_target_channel(channel_id):
    settings_col.update_one(
        {"_id": "channels"},
        {"$addToSet": {"targets": channel_id}},
        upsert=True
    )

async def remove_target_channel(channel_id):
    settings_col.update_one(
        {"_id": "channels"},
        {"$pull": {"targets": channel_id}}
    )

# ---------------- Source Channels ---------------- #

async def get_all_source_channels():
    doc = settings_col.find_one({"_id": "channels"})
    return doc.get("sources", []) if doc else []

async def add_source_channel(channel_id):
    settings_col.update_one(
        {"_id": "channels"},
        {"$addToSet": {"sources": channel_id}},
        upsert=True
    )

async def remove_source_channel(channel_id):
    settings_col.update_one(
        {"_id": "channels"},
        {"$pull": {"sources": channel_id}}
    )

# ---------------- Message Forward Tracking ---------------- #

async def is_forwarded_for_target(message_id, target_id):
    return forwarded_col.find_one({"_id": f"{message_id}_{target_id}"}) is not None

async def mark_as_forwarded_for_target(message_id, target_id):
    forwarded_col.insert_one({"_id": f"{message_id}_{target_id}"})

# ---------------- Regex Replacements ---------------- #

async def add_replacement(pattern, replacement):
    replacements_col.update_one(
        {"pattern": pattern},
        {"$set": {"replacement": replacement}},
        upsert=True
    )

async def remove_replacement(pattern):
    replacements_col.delete_one({"pattern": pattern})

async def list_replacements():
    return list(replacements_col.find({}, {"_id": 0}))

async def apply_replacements(text):
    replacements = await list_replacements()
    for r in replacements:
        text = re.sub(r["pattern"], r["replacement"], text)
    return text
