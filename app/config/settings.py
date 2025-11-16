import os
from pathlib import Path
from dotenv import load_dotenv

# Base_DIR -> project root (candidate_recommendation/)
# From settings.py: parent = config/, parent.parent = app/, parent.parent.parent = project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


# If MongoDB is missing it shall not start the application
class Settings:
    # Read MONGO_URI, DATABASE_NAME, MONGO_CANDIDATE_COLLECTIONS from environment.
    def __init__(self):
        # Load .env in __init__ to ensure it works in Uvicorn's child processes
        if not ENV_PATH.exists():
            raise FileNotFoundError(f".env file not found at: {ENV_PATH}")
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        self.MONGO_URI = os.environ.get("MONGO_URI", "").strip()
        self.DATABASE_NAME = os.environ.get("DATABASE_NAME", "").strip()
        mongo_collections_raw = os.environ.get("MONGO_CANDIDATE_COLLECTIONS", "").strip()

        # if MongoURI is empty
        if not self.MONGO_URI:
            raise ValueError("MONGO_URI environment variable is not set.")
        if not self.DATABASE_NAME:
            raise ValueError("DATABASE_NAME environment variable is not set.")
        if not mongo_collections_raw:
            raise ValueError("MONGO_CANDIDATE_COLLECTIONS environment variable is not set.")
        
        # CANDIDATE_COLLECTIONS = Split MONGO_CANDIDATE_COLLECTIONS by comma and strip whitespace
        self.CANDIDATE_COLLECTIONS = [col.strip() for col in mongo_collections_raw.split(",") if col.strip()]

        self.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
        if not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        
        self.EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "").strip()
        if not self.EMBEDDING_MODEL:
            raise ValueError("EMBEDDING_MODEL environment variable is not set.")
        if self.EMBEDDING_MODEL == "text-embedding-3-large":
            expected_dim = 3072
        else:
            raise ValueError(f"Unsupported EMBEDDING_MODEL: {self.EMBEDDING_MODEL}")    

        dim_raw = os.environ.get("EMBEDDING_DIMENSIONS", "").strip()
        if not dim_raw:
            raise ValueError("EMBEDDING_DIMENSIONS environment variable is not set.")
        self.EMBEDDING_DIMENSIONS = int(dim_raw)

        if self.EMBEDDING_DIMENSIONS != expected_dim:
            raise ValueError(f"EMBEDDING_DIMENSIONS for model {self.EMBEDDING_MODEL} must be {expected_dim}.")
        
        rate_raw = os.environ.get("RATE_LIMIT_REQUESTS_PER_MINUTE", "60").strip()
        if not rate_raw:
            raise ValueError("RATE_LIMIT_REQUESTS_PER_MINUTE environment variable is not set.")
        self.RATE_LIMIT_REQUESTS_PER_MINUTE = int(rate_raw)
        if self.RATE_LIMIT_REQUESTS_PER_MINUTE <= 0:
            raise ValueError("RATE_LIMIT_REQUESTS_PER_MINUTE must be a positive integer.")
        
        cost_raw = os.environ.get("COST_THRESHOLD", "").strip()
        if not cost_raw:
            raise ValueError("COST_THRESHOLD environment variable is not set.")
        self.COST_THRESHOLD = float(cost_raw)
        if self.COST_THRESHOLD < 0:
            raise ValueError("COST_THRESHOLD must be a non-negative float.")


