import os
from pathlib import Path
from dotenv import load_dotenv


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
        if not self.MONGO_URI:
            raise ValueError("MONGO_URI environment variable is not set.")
        
        self.DATABASE_NAME = os.environ.get("DATABASE_NAME", "").strip()
        if not self.DATABASE_NAME:
            raise ValueError("DATABASE_NAME environment variable is not set.")
        

        self.USER_PROFILES_COLLECTION = os.environ.get("USER_PROFILES_COLLECTION", "").strip()
        self.APPLICATION_COLLECTION = os.environ.get("APPLICATION_COLLECTION", "").strip()
        self.JOB_COLLECTION = os.environ.get("JOB_COLLECTION", "").strip()

        if not all([self.USER_PROFILES_COLLECTION, self.APPLICATION_COLLECTION, self.JOB_COLLECTION]):
            raise ValueError("One or more required collection names are not set in environment variables.")
        


        self.AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        self.AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
        self.AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15").strip()
        self.AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "").strip()

        for attr, value in{
            "AZURE_OPENAI_API_KEY": self.AZURE_OPENAI_API_KEY,
            "AZURE_OPENAI_ENDPOINT": self.AZURE_OPENAI_ENDPOINT,
            "AZURE_OPENAI_API_VERSION": self.AZURE_OPENAI_API_VERSION,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": self.AZURE_OPENAI_EMBEDDING_DEPLOYMENT
        }.items():
            if not value:
                raise ValueError(f"{attr} environment variable is not set.")
            

        dim_raw = os.environ.get("EMBEDDING_DIMENSIONS", "").strip()
        if not dim_raw:
            raise ValueError("EMBEDDING_DIMENSION environment variable is not set.")
        
        self.EMBEDDING_VECTOR_SIZE = int(dim_raw)
        if self.EMBEDDING_VECTOR_SIZE != 3072:
            raise ValueError("EMBEDDING_DIMENSION_RAW must be 3072 for the specified Azure OpenAI embedding model.")
        

        rate_raw = os.environ.get("RATE_LIMIT_REQUESTS_PER_MINUTE", "60").strip()
        self.RATE_LIMIT_REQUESTS_PER_MINUTE = int(rate_raw)
        if self.RATE_LIMIT_REQUESTS_PER_MINUTE <= 0:
            raise ValueError("RATE_LIMIT_REQUESTS_PER_MINUTE must be a positive integer.")
        
        cost_raw = os.environ.get("COST_THRESHOLD", "").strip()
        if not cost_raw:
            raise ValueError("COST_THRESHOLD environment variable is not set.")
        self.COST_THRESHOLD = float(cost_raw)
        if self.COST_THRESHOLD < 0:
            raise ValueError("COST_THRESHOLD must be a positive number.")
        

        self.DEFAULT_APPLIED_PAGE_SIZE = 50
        self.MAX_APPLIED_PAGE_SIZE = 200
        self.DEFAULT_GLOBAL_LIMIT = 50
        self.MAX_GLOBAL_LIMIT = 200
        
        # Vector search index name for userprofiles collection
        self.USERPROFILE_VECTOR_INDEX = os.environ.get("USERPROFILE_VECTOR_INDEX", "userprofiles_embedding_index").strip()
        
