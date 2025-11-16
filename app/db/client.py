from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from app.config.settings import Settings

# global variable mongo_client = None
mongo_client: MongoClient | None = None

def connect_to_mongo(settings: Settings) -> None:
    global mongo_client
    if mongo_client is not None:
        # Already connected, nothing to do
        return
    try:
        client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
        # Ping the server to check connection
        client.admin.command("ping")
        mongo_client = client
        print("Connected to MongoDB successfully.")
    except ServerSelectionTimeoutError as err:
        raise ConnectionError(f"Could not connect to MongoDB: {err}")

#function get_database(settings)
def get_database(settings: Settings):
    if mongo_client is None:
        raise RuntimeError("MongoDB client is not initialized, call connect_to_mongo first.")
    return mongo_client[settings.DATABASE_NAME]

#function get_candidate_collections(settings)
def get_candidate_collection(settings: Settings):
    db = get_database(settings)
    return db[settings.CANDIDATE_COLLECTIONS[0]]

#Function to close mongo connection
def close_mongo_connection():
    global mongo_client
    if mongo_client is not None:
        mongo_client.close()
        mongo_client = None



