"""
Script to programmatically create MongoDB Atlas Vector Search index.
This creates the required index for semantic candidate search.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

from app.config.settings import Settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__, level="INFO")


async def create_vector_search_index():
    """
    Create Atlas Vector Search index for userprofiles collection.
    
    This index enables semantic similarity search on candidate embeddings.
    """
    logger.info("=" * 60)
    logger.info("MongoDB Atlas Vector Search Index Creation")
    logger.info("=" * 60)
    
    # Initialize settings and connection
    settings = Settings()
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DATABASE_NAME]
    collection = db[settings.USER_PROFILES_COLLECTION]
    
    index_name = settings.USERPROFILE_VECTOR_INDEX
    
    try:
        # Check if index already exists
        logger.info(f"Checking for existing index: {index_name}")
        
        try:
            # List existing search indexes
            existing_indexes = await collection.list_search_indexes().to_list(length=None)
            
            for idx in existing_indexes:
                if idx.get("name") == index_name:
                    logger.info(f"✓ Index '{index_name}' already exists!")
                    logger.info(f"  Status: {idx.get('status', 'unknown')}")
                    logger.info(f"  Type: {idx.get('type', 'unknown')}")
                    
                    if idx.get("status") == "READY":
                        logger.info("\n✓ Index is READY and can be used for searches.")
                        return
                    else:
                        logger.info(f"\n⚠ Index exists but status is: {idx.get('status')}")
                        logger.info("  Please wait for it to become READY.")
                        return
        except AttributeError:
            # list_search_indexes might not be available in older motor versions
            logger.warning("Unable to list search indexes (motor version may not support it)")
        
        # Create the vector search index
        logger.info(f"\nCreating vector search index: {index_name}")
        
        index_definition = {
            "name": index_name,
            "type": "vectorSearch",
            "definition": {
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding_vector",
                        "numDimensions": settings.EMBEDDING_VECTOR_SIZE,
                        "similarity": "cosine"
                    }
                ]
            }
        }
        
        logger.info(f"Index definition:")
        logger.info(f"  Collection: {settings.USER_PROFILES_COLLECTION}")
        logger.info(f"  Index name: {index_name}")
        logger.info(f"  Vector field: embedding_vector")
        logger.info(f"  Dimensions: {settings.EMBEDDING_VECTOR_SIZE}")
        logger.info(f"  Similarity: cosine")
        
        # Create the index using createSearchIndex command
        try:
            result = await db.command({
                "createSearchIndexes": settings.USER_PROFILES_COLLECTION,
                "indexes": [index_definition]
            })
            
            logger.info("\n✓ Vector search index creation initiated!")
            logger.info(f"  Result: {result}")
            logger.info("\n⏳ The index is now building. This may take 2-5 minutes.")
            logger.info("   You can check the status in MongoDB Atlas UI or run this script again.")
            
        except OperationFailure as e:
            if "already exists" in str(e).lower():
                logger.info(f"\n✓ Index '{index_name}' already exists!")
            else:
                raise
        
    except OperationFailure as exc:
        logger.error(f"\n✗ Failed to create vector search index: {exc}")
        logger.error("\nPossible reasons:")
        logger.error("1. Your MongoDB cluster doesn't support Atlas Search (requires M10+ tier)")
        logger.error("2. You don't have permissions to create search indexes")
        logger.error("3. The cluster is not an Atlas cluster (self-hosted MongoDB)")
        logger.error("\nIf you're using MongoDB Atlas, you may need to create the index via the UI.")
        raise
    except Exception as exc:
        logger.error(f"\n✗ Unexpected error: {exc}", exc_info=True)
        raise
    finally:
        client.close()
        logger.info("\n" + "=" * 60)


async def check_index_status():
    """Check the status of the vector search index."""
    settings = Settings()
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DATABASE_NAME]
    collection = db[settings.USER_PROFILES_COLLECTION]
    
    index_name = settings.USERPROFILE_VECTOR_INDEX
    
    try:
        logger.info(f"\nChecking status of index: {index_name}")
        
        try:
            existing_indexes = await collection.list_search_indexes().to_list(length=None)
            
            found = False
            for idx in existing_indexes:
                if idx.get("name") == index_name:
                    found = True
                    logger.info(f"\n✓ Found index: {index_name}")
                    logger.info(f"  Status: {idx.get('status', 'unknown')}")
                    logger.info(f"  Type: {idx.get('type', 'unknown')}")
                    
                    if idx.get("status") == "READY":
                        logger.info("\n✓ Index is READY! You can now use the search endpoints.")
                    else:
                        logger.info(f"\n⏳ Index is still building. Current status: {idx.get('status')}")
                        logger.info("   Please wait a few more minutes and check again.")
            
            if not found:
                logger.info(f"\n✗ Index '{index_name}' not found.")
                logger.info("   Run this script to create it.")
        except AttributeError:
            logger.warning("Unable to check index status (motor version may not support it)")
    finally:
        client.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Create or check MongoDB Atlas Vector Search index"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check index status, don't create"
    )
    
    args = parser.parse_args()
    
    if args.check_only:
        asyncio.run(check_index_status())
    else:
        asyncio.run(create_vector_search_index())


if __name__ == "__main__":
    main()
