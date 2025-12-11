"""
Backfill script to generate embeddings for job listings.
Processes jobs that are missing embeddings or have stale/error status.
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
from app.services.job_listing_service import JobListingService
from app.utils.logger import setup_logger

logger = setup_logger(__name__, level="INFO")


async def backfill_job_embeddings(
    *,
    limit: int = 100,
    batch_size: int = 10,
    dry_run: bool = False,
):
    """
    Backfill embeddings for jobs.
    
    Args:
        limit: Maximum number of jobs to process
        batch_size: Number of jobs to process in each batch
        dry_run: If True, only show what would be processed without making changes
    """
    logger.info("=" * 60)
    logger.info("Job Embeddings Backfill Script")
    logger.info("=" * 60)
    logger.info(f"Limit: {limit}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)
    
    # Initialize settings and services
    settings = Settings()
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DATABASE_NAME]
    job_collection = db[settings.JOB_COLLECTION]
    
    embedding_service = EmbeddingService(settings=settings)
    job_service = JobListingService(
        collection=job_collection,
        embedding_service=embedding_service,
        settings=settings,
    )
    
    try:
        # Find jobs needing embeddings
        logger.info("Finding jobs needing embeddings...")
        jobs = await job_service.list_pending_embeddings(limit=limit)
        
        if not jobs:
            logger.info("✓ No jobs need embeddings. All done!")
            return
        
        logger.info(f"Found {len(jobs)} jobs needing embeddings")
        
        if dry_run:
            logger.info("\n--- DRY RUN MODE - No changes will be made ---")
            for i, job in enumerate(jobs, 1):
                job_id = str(job["_id"])
                title = job.get("title", "N/A")
                status = job.get("job_embedding_status", "missing")
                logger.info(f"{i}. Job {job_id}: {title} (status: {status})")
            logger.info("--- End of dry run ---\n")
            return
        
        # Process jobs in batches
        total_processed = 0
        total_success = 0
        total_failed = 0
        
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            logger.info(f"\nProcessing batch {batch_num} ({len(batch)} jobs)...")
            
            for job in batch:
                job_id = str(job["_id"])
                title = job.get("title", "N/A")
                
                try:
                    logger.info(f"  Processing job {job_id}: {title}")
                    await job_service.refresh_embedding(job_id)
                    total_success += 1
                    logger.info(f"  ✓ Successfully generated embedding for job {job_id}")
                except Exception as exc:
                    total_failed += 1
                    logger.error(f"  ✗ Failed to generate embedding for job {job_id}: {exc}")
                
                total_processed += 1
            
            logger.info(f"Batch {batch_num} complete. Progress: {total_processed}/{len(jobs)}")
        
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
        description="Backfill embeddings for job listings"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of jobs to process (default: 100)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of jobs to process in each batch (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes",
    )
    
    args = parser.parse_args()
    
    asyncio.run(
        backfill_job_embeddings(
            limit=args.limit,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
