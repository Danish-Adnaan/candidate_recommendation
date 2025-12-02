"""
Backfill script to generate embeddings for candidate profiles.
Processes candidates that are missing embeddings or have stale/error status.
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient

from app.config.settings import Settings
from app.services.embedding_service import EmbeddingService
from app.services.user_profile_service import UserProfileService
from app.utils.logger import setup_logger

logger = setup_logger(__name__, level="INFO")


async def backfill_candidate_embeddings(
    *,
    limit: int = 100,
    batch_size: int = 10,
    dry_run: bool = False,
):
    """
    Backfill embeddings for candidate profiles.
    
    Args:
        limit: Maximum number of candidates to process
        batch_size: Number of candidates to process in each batch
        dry_run: If True, only show what would be processed without making changes
    """
    logger.info("=" * 60)
    logger.info("Candidate Embeddings Backfill Script")
    logger.info("=" * 60)
    logger.info(f"Limit: {limit}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)
    
    # Initialize settings and services
    settings = Settings()
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DATABASE_NAME]
    userprofiles_collection = db[settings.USER_PROFILES_COLLECTION]
    
    embedding_service = EmbeddingService(settings=settings)
    profile_service = UserProfileService(
        collection=userprofiles_collection,
        embedding_service=embedding_service,
        settings=settings,
    )
    
    try:
        # Find candidates needing embeddings
        logger.info("Finding candidates needing embeddings...")
        candidates = await profile_service.list_pending_embeddings(limit=limit)
        
        if not candidates:
            logger.info("✓ No candidates need embeddings. All done!")
            return
        
        logger.info(f"Found {len(candidates)} candidates needing embeddings")
        
        if dry_run:
            logger.info("\n--- DRY RUN MODE - No changes will be made ---")
            for i, candidate in enumerate(candidates, 1):
                candidate_id = str(candidate["_id"])
                personal = candidate.get("personal_information", {})
                name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip() or "N/A"
                status = candidate.get("embedding_status", "missing")
                logger.info(f"{i}. Candidate {candidate_id}: {name} (status: {status})")
            logger.info("--- End of dry run ---\n")
            return
        
        # Process candidates in batches
        total_processed = 0
        total_success = 0
        total_failed = 0
        
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            logger.info(f"\nProcessing batch {batch_num} ({len(batch)} candidates)...")
            
            for candidate in batch:
                candidate_id = str(candidate["_id"])
                personal = candidate.get("personal_information", {})
                name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip() or "N/A"
                
                try:
                    logger.info(f"  Processing candidate {candidate_id}: {name}")
                    await profile_service.refresh_embedding(candidate_id)
                    total_success += 1
                    logger.info(f"  ✓ Successfully generated embedding for candidate {candidate_id}")
                except Exception as exc:
                    total_failed += 1
                    logger.error(f"  ✗ Failed to generate embedding for candidate {candidate_id}: {exc}")
                
                total_processed += 1
            
            logger.info(f"Batch {batch_num} complete. Progress: {total_processed}/{len(candidates)}")
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("BACKFILL COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total processed: {total_processed}")
        logger.info(f"Successful: {total_success}")
        logger.info(f"Failed: {total_failed}")
        logger.info("=" * 60)
        
    finally:
        client.close()
        logger.info("Database connection closed")


def main():
    """Parse arguments and run backfill."""
    parser = argparse.ArgumentParser(
        description="Backfill embeddings for candidate profiles"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of candidates to process (default: 100)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of candidates to process in each batch (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes",
    )
    
    args = parser.parse_args()
    
    asyncio.run(
        backfill_candidate_embeddings(
            limit=args.limit,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
