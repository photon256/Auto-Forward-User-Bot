import os
import re
from pymongo import MongoClient

# Load MongoDB URI from environment and specify DB manually
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["angeldb"]  # <-- Replace 'angeldb' with your actual DB name if different

collection = db["forwarded"]
replacements_col = db["replacements"]
settings_col = db["settings"]

# Forward Tracking
async def is_forwarded_for_target(message_id, target_chat_id):
    return collection.find_one({"_id": message_id, "targets": target_chat_id}) is not None

async def mark_as_forwarded_for_target(message_id, target_chat_id):
    collection.update_one(
        {"_id": message_id},
        {"$addToSet": {"targets": target_chat_id}},
        upsert=True
    )

# Caption Replacements
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
    for item in replacements:
        try:
            text = re.sub(item["pattern"], item["replacement"], text)
        except re.error:
            continue
    return text

# Source Channels
async def get_all_source_channels():
    doc = settings_col.find_one({"_id": "sources"})
    return doc["channels"] if doc else []

async def add_source_channel(chat_id):
    settings_col.update_one(
        {"_id": "sources"},
        {"$addToSet": {"channels": chat_id}},
        upsert=True
    )

async def remove_source_channel(chat_id):
    settings_col.update_one(
        {"_id": "sources"},
        {"$pull": {"channels": chat_id}},
        upsert=True
)
        
