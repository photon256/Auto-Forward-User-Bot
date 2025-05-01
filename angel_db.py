import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["forwardBot"]

# Collections
collection = db["forwarded_files"]
settings_col = db["settings"]
admin_col = db["admins"]
extra_targets_col = db["extra_targets"]
replacements_col = db["replacements"]  # New collection for replacements

# Index setup
collection.create_index([("message_id", 1), ("target_id", 1)], unique=True)

# Forward tracking
async def is_forwarded_for_target(msg_id, target_id):
    return collection.find_one({"message_id": msg_id, "target_id": target_id}) is not None

async def mark_as_forwarded_for_target(msg_id, target_id):
    try:
        collection.insert_one({"message_id": msg_id, "target_id": target_id})
    except DuplicateKeyError:
        pass

# Replacement handling
async def add_replacement(pattern: str, replacement: str):
    replacements_col.update_one(
        {"pattern": pattern},
        {"$set": {"replacement": replacement}},
        upsert=True
    )

async def remove_replacement(pattern: str):
    replacements_col.delete_one({"pattern": pattern})

async def list_replacements():
    return list(replacements_col.find({}, {"_id": 0}))

async def apply_replacements(text: str) -> str:
    import re
    rules = await list_replacements()
    for rule in rules:
        try:
            text = re.sub(rule["pattern"], rule["replacement"], text)
        except re.error as e:
            print(f"Invalid regex pattern: {rule['pattern']} ({e})")
    return text
    
