"""
Job listing service with comprehensive embedding management.
Handles job CRUD operations and embedding generation/refresh.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId

from app.config.settings import Settings
from app.services.base import NotFoundError
from app.services.embedding_service import EmbeddingResult, EmbeddingService, EmbeddingServiceError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class JobListingService:
    """Service for managing job listings and their embeddings."""
    
    def __init__(self, *, collection, embedding_service: EmbeddingService, settings: Settings):
        self._collection = collection
        self._embedding_service = embedding_service
        self._settings = settings
        logger.info("JobListingService initialized")

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieve a job by ID.
        
        Args:
            job_id: Job identifier (MongoDB ObjectId as string)
            
        Returns:
            Job document
            
        Raises:
            NotFoundError: If job doesn't exist
        """
        try:
            object_id = ObjectId(job_id)
        except InvalidId as exc:
            logger.warning(f"Invalid job ID format: {job_id}")
            raise NotFoundError(f"Job with id {job_id} not found") from exc

        job = await self._collection.find_one({"_id": object_id})
        if not job:
            logger.warning(f"Job not found: {job_id}")
            raise NotFoundError(f"Job with id {job_id} not found")
        
        logger.debug(f"Retrieved job: {job_id}")
        return job

    async def refresh_embedding(self, job_id: str) -> None:
        """
        Generate or refresh embedding for a job.
        
        Args:
            job_id: Job identifier
            
        Raises:
            NotFoundError: If job doesn't exist
            EmbeddingServiceError: If embedding generation fails
        """
        logger.info(f"Starting embedding refresh for job: {job_id}")
        job = await self.get_job(job_id)
        
        # Update status to processing
        await self._collection.update_one(
            {"_id": job["_id"]}, 
            {
                "$set": {
                    "job_embedding_status": "processing",
                    "job_embedding_error": None
                }
            }
        )
        logger.debug(f"Set job {job_id} embedding status to 'processing'")
        
        try:
            result = await self._embedding_service.generate_job_embedding(job)
            logger.info(f"Successfully generated embedding for job {job_id}")
        except EmbeddingServiceError as exc:
            logger.error(f"Embedding service error for job {job_id}: {exc}")
            await self._collection.update_one(
                {"_id": job["_id"]},
                {
                    "$set": {
                        "job_embedding_status": "error",
                        "job_embedding_error": str(exc)
                    }
                },
            )
            raise
        except Exception as exc:
            logger.error(f"Unexpected error generating embedding for job {job_id}: {exc}", exc_info=True)
            await self._collection.update_one(
                {"_id": job["_id"]},
                {
                    "$set": {
                        "job_embedding_status": "error",
                        "job_embedding_error": f"Unexpected error: {str(exc)}"
                    }
                },
            )
            raise
        else:
            await self._persist_embedding(job["_id"], result)
            logger.info(f"Persisted embedding for job {job_id}")

    async def list_pending_embeddings(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Find jobs that need embedding generation.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of job documents needing embeddings
        """
        query = {
            "$or": [
                {"job_embedding_status": {"$in": ["pending", "stale", "error"]}},
                {"job_embedding_vector": {"$exists": False}},
                {"job_embedding_vector": None},
            ]
        }
        
        cursor = self._collection.find(query).limit(limit)
        jobs = await cursor.to_list(length=limit)
        
        logger.info(f"Found {len(jobs)} jobs needing embeddings (limit: {limit})")
        return jobs

    async def ensure_embedding(self, job: Dict[str, Any]) -> List[float]:
        """
        Ensure job has a valid embedding, generating if necessary.
        
        This method checks if the job has a valid embedding and generates one
        if it's missing or stale (job updated after embedding was generated).
        
        Args:
            job: Job document
            
        Returns:
            Embedding vector
            
        Raises:
            EmbeddingServiceError: If embedding generation fails
        """
        job_id = str(job["_id"])
        vector = job.get("job_embedding_vector")
        last_generated = job.get("job_embedding_last_generated_at")
        updated_at = job.get("updatedAt")
        
        # Check if embedding exists and is up-to-date
        if vector and last_generated:
            if not updated_at or last_generated >= updated_at:
                logger.debug(f"Using cached embedding for job {job_id}")
                return vector
            else:
                logger.info(f"Job {job_id} embedding is stale (job updated after embedding)")
        
        # Generate new embedding
        logger.info(f"Generating new embedding for job {job_id}")
        await self.refresh_embedding(job_id)
        
        # Fetch updated job to get the new embedding
        updated_job = await self.get_job(job_id)
        vector = updated_job.get("job_embedding_vector")
        
        if not vector:
            raise EmbeddingServiceError(f"Failed to generate embedding for job {job_id}")
        
        return vector

    async def _persist_embedding(self, job_id: ObjectId, result: EmbeddingResult) -> None:
        """
        Persist embedding to database.
        
        Args:
            job_id: Job ObjectId
            result: Embedding result from embedding service
        """
        await self._collection.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "job_embedding_vector": result.vector,
                    "job_embedding_model": result.model,
                    "job_embedding_dimensions": self._settings.EMBEDDING_VECTOR_SIZE,
                    "job_embedding_status": "ready",
                    "job_embedding_last_generated_at": result.generated_at,
                    "job_embedding_error": None,
                }
            },
        )
        logger.debug(f"Persisted embedding for job {job_id}")
