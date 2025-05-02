import re
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
import os

# MongoDB config
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://abcd:abcdeas@cluster0.flillxf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
DB_NAME = "angel_forward_bot"

client = MongoClient(os.getenv("MONGODB_URI"))
db = client.get_default_database()

settings_col = db["settings"]
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

collection = db.forwarded_messages
targets_col = db.target_channels
sources_col = db.source_channels
replace_col = db.replacements

# Target Forwarding Tracking
async def is_forwarded_for_target(msg_id, target_id):
    doc = await collection.find_one({"msg_id": msg_id, "target_id": target_id})
    return doc is not None

async def mark_as_forwarded_for_target(msg_id, target_id):
    await collection.insert_one({"msg_id": msg_id, "target_id": target_id})

# Caption Replacements
async def apply_replacements(text):
    replacements = await list_replacements()
    for item in replacements:
        try:
            pattern = re.compile(item["pattern"])
            text = pattern.sub(item["replacement"], text)
        except re.error as e:
            print(f"Regex error for pattern {item['pattern']}: {e}")
    return text

async def add_replacement(pattern, replacement):
    await replace_col.update_one(
        {"pattern": pattern},
        {"$set": {"replacement": replacement}},
        upsert=True
    )

async def remove_replacement(pattern):
    await replace_col.delete_one({"pattern": pattern})

async def list_replacements():
    return await replace_col.find().to_list(length=100)

# Target Channel Management
async def add_target_channel(chat_id):
    await targets_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"chat_id": chat_id}},
        upsert=True
    )

async def remove_target_channel(chat_id):
    await targets_col.delete_one({"chat_id": chat_id})

async def get_all_target_channels():
    docs = await targets_col.find().to_list(length=100)
    return [doc["chat_id"] for doc in docs]

# Source Channel Management
async def add_source_channel(chat_id):
    await sources_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"chat_id": chat_id}},
        upsert=True
    )

async def remove_source_channel(chat_id):
    await sources_col.delete_one({"chat_id": chat_id})

async def get_all_source_channels():
    docs = await sources_col.find().to_list(length=100)
    return [doc["chat_id"] for doc in docs]
