"""
User profile service with comprehensive embedding management.
Handles candidate profile CRUD operations and embedding generation/refresh.
"""
from datetime import datetime
from typing import Any, Dict, List

from bson import ObjectId

from app.config.settings import Settings
from app.services.base import NotFoundError
from app.services.embedding_service import EmbeddingResult, EmbeddingService, EmbeddingServiceError
from app.utils.logger import get_logger

logger = get_logger(__name__)


# Fields that affect embedding and require regeneration when changed
EMBEDDING_SENSITIVE_FIELDS = {
    "skills",
    "experience",
    "education",
    "courses",
    "personal_projects",
    "awards_and_achievements",
    "position_of_responsibility",
    "competitions",
    "extra_curricular_activities",
    "publications",
    "personal_information",
    "summary",
    "about",
    "industry",
    "socials",
}


class UserProfileService:
    """Service for managing user profiles and their embeddings."""
    
    def __init__(self, *, collection, embedding_service: EmbeddingService, settings: Settings):
        self._collection = collection
        self._embedding_service = embedding_service
        self._settings = settings
        logger.info("UserProfileService initialized")

    async def create_profile(self, payload: Dict[str, Any]) -> str:
        """
        Create a new candidate profile.
        
        Args:
            payload: Profile data
            
        Returns:
            Created profile ID
        """
        now = datetime.utcnow()
        payload.update({
            "embedding_status": "pending",
            "embedding_vector": None,
            "embedding_model": None,
            "embedding_dimensions": self._settings.EMBEDDING_VECTOR_SIZE,
            "embedding_last_generated_at": None,
            "embedding_error": None,
            "embedding_version": None,
            "createdAt": now,
            "updatedAt": now,
        })
        result = await self._collection.insert_one(payload)
        candidate_id = str(result.inserted_id)
        
        logger.info(f"Created candidate profile: {candidate_id}")
        # TODO: Enqueue background embedding job here
        return candidate_id

    async def update_profile(self, candidate_id: str, updates: Dict[str, Any]) -> None:
        """
        Update a candidate profile.
        
        Args:
            candidate_id: Candidate identifier
            updates: Fields to update
            
        Raises:
            NotFoundError: If candidate doesn't exist
        """
        updates["updatedAt"] = datetime.utcnow()
        
        # Check if updates affect embedding
        if self._touches_embedding_fields(updates):
            logger.info(f"Update touches embedding fields for candidate {candidate_id}, marking as stale")
            updates.update({
                "embedding_status": "stale",
                "embedding_vector": None,
                "embedding_error": None,
                "embedding_last_generated_at": None,
                "embedding_version": None,
            })
            # TODO: Enqueue background embedding job here
        
        result = await self._collection.update_one(
            {"_id": ObjectId(candidate_id)},
            {"$set": updates}
        )
        
        if result.matched_count == 0:
            logger.warning(f"Candidate not found for update: {candidate_id}")
            raise NotFoundError(f"Candidate with id {candidate_id} not found")
        
        logger.debug(f"Updated candidate profile: {candidate_id}")

    async def refresh_embedding(self, candidate_id: str) -> None:
        """
        Generate or refresh embedding for a candidate.
        
        Args:
            candidate_id: Candidate identifier
            
        Raises:
            NotFoundError: If candidate doesn't exist
            EmbeddingServiceError: If embedding generation fails
        """
        logger.info(f"Starting embedding refresh for candidate: {candidate_id}")
        
        doc = await self._collection.find_one({"_id": ObjectId(candidate_id)})
        if not doc:
            logger.warning(f"Candidate not found: {candidate_id}")
            raise NotFoundError(f"Candidate with id {candidate_id} not found")
        
        # Update status to processing
        await self._collection.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "embedding_status": "processing",
                    "embedding_error": None
                }
            }
        )
        logger.debug(f"Set candidate {candidate_id} embedding status to 'processing'")
        
        try:
            result = await self._embedding_service.generate_candidate_embedding(doc)
            logger.info(f"Successfully generated embedding for candidate {candidate_id}")
        except EmbeddingServiceError as exc:
            logger.error(f"Embedding service error for candidate {candidate_id}: {exc}")
            await self._collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "embedding_status": "error",
                        "embedding_error": str(exc)
                    }
                },
            )
            raise
        except Exception as exc:
            logger.error(f"Unexpected error generating embedding for candidate {candidate_id}: {exc}", exc_info=True)
            await self._collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "embedding_status": "error",
                        "embedding_error": f"Unexpected error: {str(exc)}"
                    }
                },
            )
            raise
        else:
            await self._persist_embedding(doc["_id"], result)
            logger.info(f"Persisted embedding for candidate {candidate_id}")

    async def get_profile(self, candidate_id: str, *, include_embedding_vector: bool = False) -> Dict:
        """
        Retrieve a candidate profile.
        
        Args:
            candidate_id: Candidate identifier
            include_embedding_vector: Whether to include the embedding vector in response
            
        Returns:
            Candidate profile document
            
        Raises:
            NotFoundError: If candidate doesn't exist
        """
        projection = None if include_embedding_vector else {"embedding_vector": 0}
        profile = await self._collection.find_one({"_id": ObjectId(candidate_id)}, projection)
        
        if not profile:
            logger.warning(f"Candidate not found: {candidate_id}")
            raise NotFoundError(f"Candidate with id {candidate_id} not found")
        
        logger.debug(f"Retrieved candidate profile: {candidate_id}")
        return profile

    async def list_pending_embeddings(self, *, limit: int = 100) -> List[Dict]:
        """
        Find candidates that need embedding generation.
        
        Args:
            limit: Maximum number of candidates to return
            
        Returns:
            List of candidate documents needing embeddings
        """
        query = {
            "$or": [
                {"embedding_status": {"$in": ["pending", "stale", "error"]}},
                {"embedding_vector": {"$exists": False}},
                {"embedding_vector": None},
            ]
        }
        
        cursor = self._collection.find(query).limit(limit)
        candidates = await cursor.to_list(length=limit)
        
        logger.info(f"Found {len(candidates)} candidates needing embeddings (limit: {limit})")
        return candidates

    def _touches_embedding_fields(self, updates: Dict) -> bool:
        """
        Check if updates affect fields that require embedding regeneration.
        
        Args:
            updates: Update dictionary
            
        Returns:
            True if any embedding-sensitive field is being updated
        """
        return any(field in EMBEDDING_SENSITIVE_FIELDS for field in updates)

    async def _persist_embedding(self, candidate_id: ObjectId, result: EmbeddingResult) -> None:
        """
        Persist embedding to database.
        
        Args:
            candidate_id: Candidate ObjectId
            result: Embedding result from embedding service
        """
        await self._collection.update_one(
            {"_id": candidate_id},
            {
                "$set": {
                    "embedding_vector": result.vector,
                    "embedding_model": result.model,
                    "embedding_dimensions": self._settings.EMBEDDING_VECTOR_SIZE,
                    "embedding_status": "ready",
                    "embedding_last_generated_at": result.generated_at,
                    "embedding_error": None,
                    "embedding_version": result.model,
                }
            },
        )
        logger.debug(f"Persisted embedding for candidate {candidate_id}")
