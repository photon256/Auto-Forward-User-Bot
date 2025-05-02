# angel_db.py
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv()
# ===== WOODcraft ==== SudoR2spr ==== #

MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["forwardBot"]

# Collections
# ===== WOODcraft ==== SudoR2spr ==== 
collection = db["forwarded_files"]
settings_col = db["settings"]
admin_col = db["admins"]
extra_targets_col = db["extra_targets"]
# ===== WOODcraft ==== SudoR2spr ==== 

# Index setup
collection.create_index([("message_id", 1), ("target_id", 1)], unique=True)

# Utility functions
async def is_forwarded_for_target(msg_id, target_id):
    return collection.find_one({"message_id": msg_id, "target_id": target_id}) is not None

async def mark_as_forwarded_for_target(msg_id, target_id):
    try:
        collection.insert_one({"message_id": msg_id, "target_id": target_id})
    except DuplicateKeyError:
        pass
