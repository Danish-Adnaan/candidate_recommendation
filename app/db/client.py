from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ServerSelectionTimeoutError
from app.config.settings import Settings

# global variable mongo_client = None
mongo_client: AsyncIOMotorClient | None = None

async def connect_to_mongo(settings: Settings) -> None:
    global mongo_client
    if mongo_client is not None:
        # Already connected, nothing to do
        return
    try:
        client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
        # Ping the server to check connection
        await client.admin.command("ping")
        mongo_client = client
        print("Connected to MongoDB successfully.")
    except ServerSelectionTimeoutError as err:
        raise ConnectionError(f"Could not connect to MongoDB: {err}")

def get_database(settings: Settings):
    if mongo_client is None:
        raise RuntimeError("MongoDB client is not initialized, call connect_to_mongo first.")
    return mongo_client[settings.DATABASE_NAME]

def get_candidate_collection(settings: Settings):
    db = get_database(settings)
    # Assuming CANDIDATE_COLLECTIONS is a list in settings, but checking settings.py it was USER_PROFILES_COLLECTION
    # The original code used settings.CANDIDATE_COLLECTIONS[0], but settings.py has USER_PROFILES_COLLECTION.
    # I should probably fix this to use the correct setting or keep it generic if I can't see settings.py right now.
    # I saw settings.py earlier, it has USER_PROFILES_COLLECTION.
    # The original code had `settings.CANDIDATE_COLLECTIONS[0]`, which might be wrong if settings.py doesn't have it.
    # I'll check settings.py again to be sure, or just use USER_PROFILES_COLLECTION if I recall correctly.
    # Let's check settings.py content from history.
    # Step 25: settings.py has USER_PROFILES_COLLECTION, APPLICATION_COLLECTION, JOB_COLLECTION.
    # It does NOT have CANDIDATE_COLLECTIONS.
    # So the original code in client.py was likely broken or referring to an old version of settings.
    # I will update this function to return the user profiles collection as a safe bet, or just remove it if not used.
    # But to be safe and minimal, I'll use USER_PROFILES_COLLECTION.
    return db[settings.USER_PROFILES_COLLECTION]

async def close_mongo_connection():
    global mongo_client
    if mongo_client is not None:
        mongo_client.close()
        mongo_client = None




