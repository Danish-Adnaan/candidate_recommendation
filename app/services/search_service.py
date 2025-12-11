"""
Search service coordinating semantic candidate search.
Handles both applied-only and global candidate searches using vector similarity.
"""
from datetime import datetime as dt
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId

from app.config.settings import Settings
from app.models.search_models import (
    AppliedCandidateHit,
    ContactInfo,
    ExperienceDetail,
    GlobalSearchResponse,
    InitialQuestionAnswer,
    NewAppliedSearchResponse,
    PaginationMeta,
    RuthiSideStage,
    SearchCandidateHit,
    SkillDetail,
    StageTimestamp,
)
from app.services.base import NotFoundError
from app.services.embedding_service import EmbeddingService
from app.services.job_listing_service import JobListingService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SearchService:
    """Coordinates applied/global semantic searches with JD embedding caching."""

    def __init__(
        self,
        settings: Settings,
        *,
        job_collection=None,
        userprofiles_collection=None,
        application_collection=None,
        embedding_service=None,
    ) -> None:
        self._settings = settings
        self._jobs = job_collection
        self._userprofiles = userprofiles_collection
        self._applications = application_collection
        self._embedding_service = embedding_service
        
        # Initialize job listing service for embedding management
        self._job_service = JobListingService(
            collection=job_collection,
            embedding_service=embedding_service,
            settings=settings,
        )
        
        logger.info("SearchService initialized")

    async def search_applied(self, job_id: str, *, page: int, count: int) -> NewAppliedSearchResponse:
        """
        Search for candidates who have applied to a specific job.
        
        Args:
            job_id: Job identifier
            page: Page number (1-indexed)
            count: Results per page
            
        Returns:
            Applied search response with ranked candidates and application details
            
        Raises:
            NotFoundError: If job doesn't exist
        """
        logger.info(f"Starting applied search for job {job_id}, page={page}, count={count}")
        
        # Get job and ensure it has an embedding
        job = await self._get_job_or_404(job_id)
        jd_embedding, meta = await self._ensure_job_embedding(job)
        
        # Fetch ALL applications for the job to ensure we rank everyone
        # We'll handle pagination after ranking
        applications, total = await self._fetch_applications(
            job_id, page=1, page_size=0  # 0 means fetch all
        )
        
        if not applications:
            logger.info(f"No applied candidates found for job {job_id}")
            pagination = PaginationMeta(page=page, page_size=count, total_matches=0)
            return NewAppliedSearchResponse(
                job_id=job_id,
                pagination=pagination,
                results=[],
                cache_hit=meta["cache_hit"],
                embedding_model=meta["model"],
            )
        
        # Extract candidate IDs to fetch profiles
        candidate_ids = [str(app["candidateId"]) for app in applications if app.get("candidateId")]
        logger.debug(f"Found {len(candidate_ids)} applied candidates for job {job_id}")
        
        # Rank candidates manually since we have a specific list of IDs
        # This avoids the issue where $vectorSearch limits might filter out our candidates
        # before the $match stage can select them.
        ranked_hits = await self._fetch_and_rank_profiles_manually(
            jd_embedding=jd_embedding,
            candidate_ids=candidate_ids,
        )
        
        # Create a map of user_id -> SearchCandidateHit for easy lookup
        # IMPORTANT: Key by user_id (which matches Application.candidateId), NOT candidate_id (which is UserProfile._id)
        profile_map = {str(hit.user_id): hit for hit in ranked_hits if hit.user_id}
        
        logger.debug(f"Mapped {len(profile_map)} profiles by user_id. Sample keys: {list(profile_map.keys())[:3]}")
        
        # Merge Application Data with User Profile Data
        results: List[AppliedCandidateHit] = []
        
        for app in applications:
            cand_id = str(app.get("candidateId"))
            profile = profile_map.get(cand_id)
            
            # Skip if profile not found (shouldn't happen if data is consistent)
            if not profile:
                logger.warning(f"Profile not found for candidate {cand_id} in application {app.get('_id')}")
                continue
                
            # Map Application fields
            initial_questions = []
            if "initialQuestionsAnswers" in app:
                for qa in app["initialQuestionsAnswers"]:
                    initial_questions.append(InitialQuestionAnswer(
                        question=qa.get("question", ""),
                        candidate_answer=qa.get("candidateAnswer"),
                        expected_answer=qa.get("expectedAnswer"),
                        _id=qa.get("_id")
                    ))
            
            ruthi_stages = []
            if "ruthiSideStages" in app:
                for stage in app["ruthiSideStages"]:
                    timestamps = None
                    if "timestamps" in stage:
                        ts = stage["timestamps"]
                        timestamps = StageTimestamp(
                            updated_at=ts.get("updatedAt"),
                            created_at=ts.get("createdAt"),
                            _id=ts.get("_id")
                        )
                    
                    ruthi_stages.append(RuthiSideStage(
                        name=stage.get("name", ""),
                        order=stage.get("order", 0),
                        is_completed=stage.get("isCompleted", False),
                        timestamps=timestamps,
                        _id=stage.get("_id")
                    ))
            
            # Determine job status (Fresher vs Experienced)
            job_status = "Fresher"
            if profile.current_job_title:
                # Need to find company name from experience list
                company = "Unknown Company"
                if profile.experience:
                    # Find the experience entry that matches current job title
                    for exp in profile.experience:
                        if exp.job_title == profile.current_job_title:
                            company = exp.company_name or company
                            break
                    # Fallback to first experience if no match found but title exists
                    if company == "Unknown Company" and profile.experience:
                         company = profile.experience[0].company_name or company
                
                job_status = f"{profile.current_job_title} at {company}"
            elif profile.experience:
                 # Has experience but no current title identified?
                 latest = profile.experience[0]
                 job_status = f"{latest.job_title} at {latest.company_name}"

            # Construct the combined hit
            hit = AppliedCandidateHit(
                _id=app.get("_id"),
                candidateId=app.get("candidateId"),
                jobId=app.get("jobId"),
                full_name=profile.full_name,
                job_status=job_status,
                skills=profile.skills,
                initialQuestionsAnswers=initial_questions,
                currentStatus=app.get("currentStatus", "Applied"),
                ruthiSideStages=ruthi_stages,
                movedToRecruiter=app.get("movedToRecruiter", False),
                notes=app.get("notes", ""),
                appliedAt=app.get("appliedAt"),
                recruiterSideStages=app.get("recruiterSideStages", []),
                documents=app.get("documents", []),
                createdAt=app.get("createdAt"),
                updatedAt=app.get("updatedAt"),
                similarity_score=profile.similarity_score
            )
            results.append(hit)
        
        # Sort final results by similarity score descending
        results.sort(key=lambda x: x.similarity_score or -1.0, reverse=True)
        
        # Apply pagination to the ranked results
        start_idx = (page - 1) * count
        end_idx = start_idx + count
        paginated_results = results[start_idx:end_idx]
        
        logger.info(f"Constructed {len(results)} total results, returning page {page} ({len(paginated_results)} items)")
        
        pagination = PaginationMeta(page=page, page_size=count, total_matches=total)
        return NewAppliedSearchResponse(
            job_id=job_id,
            pagination=pagination,
            results=paginated_results,
            cache_hit=meta["cache_hit"],
            embedding_model=meta["model"],
        )

    async def search_global(self, job_id: str, *, count: Optional[int] = None) -> GlobalSearchResponse:
        """
        Search for candidates globally ranked by semantic similarity to job description.
        
        Args:
            job_id: Job identifier for context
            count: Number of results to return (default from settings)
            
        Returns:
            Global search response with ranked candidates
            
        Raises:
            NotFoundError: If job doesn't exist
        """
        logger.info(f"Starting global search for job {job_id}, count={count}")
        
        # Get job and ensure it has an embedding
        job = await self._get_job_or_404(job_id)
        jd_embedding, meta = await self._ensure_job_embedding(job)

        # Determine result count
        requested = count or self._settings.DEFAULT_GLOBAL_LIMIT
        requested = max(1, min(requested, self._settings.MAX_GLOBAL_LIMIT))
        
        logger.debug(f"Requesting {requested} global candidates for job {job_id}")

        # Rank candidates via vector search (no filtering by application)
        ranked_hits = await self._rank_candidates_via_vector_search(
            jd_embedding=jd_embedding,
            candidate_scope="global",
            candidate_ids=None,
            limit=requested,
        )
        
        logger.info(f"Found {len(ranked_hits)} global candidates for job {job_id}")

        return GlobalSearchResponse(
            job_id=job_id,
            requested_count=requested,
            results=ranked_hits,
            cache_hit=meta["cache_hit"],
            embedding_model=meta["model"],
        )

    async def _get_job_or_404(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieve job or raise 404 error.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job document
            
        Raises:
            NotFoundError: If job doesn't exist or ID is invalid
        """
        try:
            object_id = ObjectId(job_id)
        except InvalidId as exc:
            logger.warning(f"Invalid job ID format: {job_id}")
            raise NotFoundError(f"Job with id {job_id} not found") from exc
        
        job = await self._jobs.find_one({"_id": object_id})
        if not job:
            logger.warning(f"Job not found: {job_id}")
            raise NotFoundError(f"Job with id {job_id} not found")
        
        return job

    async def _ensure_job_embedding(self, job_doc: Dict[str, Any]) -> tuple[List[float], Dict[str, Any]]:
        """
        Ensure job has a valid embedding, generating if necessary.
        
        Args:
            job_doc: Job document
            
        Returns:
            Tuple of (embedding vector, metadata dict with cache_hit and model)
        """
        job_id = str(job_doc["_id"])
        
        # Use job_listing_service to ensure embedding
        try:
            vector = await self._job_service.ensure_embedding(job_doc)
            
            # Determine if this was a cache hit
            last_generated = job_doc.get("job_embedding_last_generated_at")
            updated_at = job_doc.get("updatedAt")
            cache_hit = bool(
                last_generated and (not updated_at or last_generated >= updated_at)
            )
            
            logger.debug(f"Job {job_id} embedding: cache_hit={cache_hit}")
            
            return vector, {
                "cache_hit": cache_hit,
                "model": job_doc.get("job_embedding_model"),
            }
        except Exception as exc:
            logger.error(f"Failed to ensure job embedding for {job_id}: {exc}")
            raise

    async def _fetch_applications(
        self, job_id: str, *, page: int, page_size: int
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Fetch full application documents for a job.
        
        Args:
            job_id: Job identifier
            page: Page number (1-indexed)
            page_size: Results per page
            
        Returns:
            Tuple of (list of application documents, total count)
        """
        try:
            job_object_id = ObjectId(job_id)
        except InvalidId as exc:
            raise NotFoundError(f"Job with id {job_id} not found") from exc

        query = {"jobId": job_object_id, "currentStatus": "Applied"}
        total = await self._applications.count_documents(query)
        
        if total == 0:
            logger.debug(f"No applications found for job {job_id}")
            return [], 0

        if page_size > 0:
            skip = max(page - 1, 0) * page_size
            cursor = (
                self._applications.find(query)
                .skip(skip)
                .limit(page_size)
            )
            docs = await cursor.to_list(length=page_size)
        else:
            # Fetch all documents if page_size is 0
            cursor = self._applications.find(query)
            docs = await cursor.to_list(length=None)
        
        logger.info(f"Fetched {len(docs)} applications for job {job_id}")
        return docs, total



    async def _rank_candidates_via_vector_search(
        self,
        jd_embedding: List[float],
        *,
        candidate_scope: str,
        candidate_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[SearchCandidateHit]:
        """
        Rank candidates using MongoDB Atlas vector search.
        
        Args:
            jd_embedding: Job description embedding vector
            candidate_scope: "applied" or "global"
            candidate_ids: Optional list of candidate IDs to filter by
            limit: Maximum results to return
            
        Returns:
            List of ranked candidate hits
        """
        if self._userprofiles is None:
            raise RuntimeError("User profiles collection not configured for SearchService.")

        limit = limit or self._settings.DEFAULT_GLOBAL_LIMIT
        
        # Convert candidate IDs to ObjectIds
        object_ids = []
        if candidate_ids:
            logger.info(f"Converting {len(candidate_ids)} candidate IDs to ObjectIds")
            for candidate_id in candidate_ids:
                try:
                    obj_id = ObjectId(candidate_id)
                    object_ids.append(obj_id)
                except InvalidId:
                    logger.warning(f"Invalid candidate ID format: {candidate_id}")
                    continue
            logger.info(f"Successfully converted {len(object_ids)} candidate IDs to ObjectIds")
            logger.info(f"Sample ObjectIds: {object_ids[:3]}...")

        # Build aggregation pipeline
        pipeline: List[Dict[str, Any]] = []
        
        # Vector search stage (MUST be first stage)
        # For applied search, we'll use $match AFTER $vectorSearch to filter by candidate IDs
        # This avoids requiring _id to be indexed as a filter field in the vector search index
        
        # Calculate how many results to fetch from vector search
        # If filtering by candidate IDs, fetch more results to account for filtering
        vector_search_limit = limit
        if object_ids:
            # Fetch 3x the limit to ensure we have enough results after filtering
            # This helps when the applied candidates are not the top matches
            vector_search_limit = min(limit * 3, 500)
            logger.debug(f"Fetching {vector_search_limit} results from vector search, will filter to {len(object_ids)} candidate IDs")
        
        vector_search_stage = {
            "index": self._settings.USERPROFILE_VECTOR_INDEX,
            "path": "embedding_vector",
            "queryVector": jd_embedding,
            "limit": vector_search_limit,
            "numCandidates": max(vector_search_limit * 2, 200),
        }
        
        pipeline.append({"$vectorSearch": vector_search_stage})
        
        # Add $match stage AFTER $vectorSearch to filter by candidate IDs
        # This works without requiring 'user' to be indexed as a filter field
        # IMPORTANT: Match on 'user' field, not '_id', because ApplicationCollection.candidateId 
        # references userprofiles.user, not userprofiles._id
        if object_ids:
            match_stage = {
                "$match": {
                    "user": {"$in": object_ids}  # Match on 'user' field, not '_id'
                }
            }
            pipeline.append(match_stage)
            logger.info(f"Added post-filter for {len(object_ids)} candidate IDs (matching on 'user' field)")
            logger.info(f"Match filter: {match_stage}")
        
        # Limit results after filtering
        pipeline.append({"$limit": limit})
        
        # Project comprehensive candidate fields
        pipeline.append(
            {
                "$project": {
                    "_id": 1,
                    "user": 1,
                    "personal_information": 1,
                    "socials": 1,
                    "skills": 1,
                    "experience": 1,
                    "education": 1,
                    "location": 1,
                    "embedding_model": 1,
                    "embedding_last_generated_at": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            }
        )

        logger.info(f"Executing vector search with vector_limit={vector_search_limit}, final_limit={limit}, scope={candidate_scope}")
        logger.info(f"Full aggregation pipeline: {pipeline}")
        
        # Execute aggregation
        cursor = self._userprofiles.aggregate(pipeline)
        documents = await cursor.to_list(length=limit)
        
        logger.info(f"Vector search returned {len(documents)} documents")
        if len(documents) == 0 and object_ids:
            logger.warning(f"⚠️  Vector search returned 0 documents despite filtering for {len(object_ids)} candidate IDs!")
            logger.warning(f"This suggests candidates either lack embeddings or IDs don't match userprofiles._id")

        # Convert to SearchCandidateHit objects with comprehensive information
        results: List[SearchCandidateHit] = []
        for doc in documents:
            personal = doc.get("personal_information") or {}
            socials = doc.get("socials") or {}
            location_value = doc.get("location") or personal.get("location")
            
            # Extract personal information
            full_name = personal.get("full_name") or f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
            
            # Get current job info from most recent experience
            experiences_raw = doc.get("experience", [])
            current_job_title = None
            employment_status = None
            if experiences_raw and isinstance(experiences_raw, list) and len(experiences_raw) > 0:
                # Check if first experience is current
                latest_exp = experiences_raw[0]
                if isinstance(latest_exp, dict):
                    # Extract title from 'position' field first, fallback to 'role' or 'title'
                    current_job_title = latest_exp.get("position") or latest_exp.get("role") or latest_exp.get("title")
                    # Check if this is a current position
                    end_date_raw = latest_exp.get("end_date") or latest_exp.get("endDate")
                    # Position is current if end_date is None, or if it's a string saying "present"
                    is_current_position = (
                        not end_date_raw or 
                        (isinstance(end_date_raw, str) and end_date_raw.lower() == "present")
                    )
                    if is_current_position:
                        employment_status = "Currently Working"
                    else:
                        employment_status = "Open to Opportunities"
            
            # Extract contact info
            contact_info = ContactInfo(
                email=personal.get("email"),
                phone=personal.get("phone") or personal.get("phone_number"),
                github=socials.get("github"),
                linkedin=socials.get("linkedin")
            )
            
            # Extract skills with proficiency levels
            skills_list = []
            skills_raw = doc.get("skills", [])
            if isinstance(skills_raw, list):
                for skill in skills_raw:
                    if isinstance(skill, str):
                        skills_list.append(SkillDetail(skill_name=skill, proficiency_level=None))
                    elif isinstance(skill, dict):
                        skill_name = skill.get("skill_name") or skill.get("name")
                        # MongoDB stores as 'skill_proficiency', check that first
                        proficiency = (
                            skill.get("skill_proficiency") or 
                            skill.get("proficiency_level") or 
                            skill.get("proficiency") or 
                            skill.get("level")
                        )
                        if skill_name:
                            skills_list.append(SkillDetail(skill_name=skill_name, proficiency_level=proficiency))
            
            # Extract experience details
            experience_list = []
            if isinstance(experiences_raw, list):
                for exp in experiences_raw:
                    if isinstance(exp, dict):
                        # Format duration - handle datetime objects from MongoDB
                        start_date_raw = exp.get("start_date") or exp.get("startDate")
                        end_date_raw = exp.get("end_date") or exp.get("endDate")
                        
                        # Convert datetime objects to strings
                        if isinstance(start_date_raw, dt):
                            start_date = start_date_raw.strftime("%b %Y")  # e.g., "Jun 2022"
                        else:
                            start_date = str(start_date_raw) if start_date_raw else ""
                        
                        if isinstance(end_date_raw, dt):
                            end_date = end_date_raw.strftime("%b %Y")
                        elif not end_date_raw:
                            end_date = "Present"
                        else:
                            end_date = str(end_date_raw)
                        
                        duration = f"{start_date} - {end_date}" if start_date else None
                        
                        is_current = not end_date_raw or (isinstance(end_date_raw, str) and end_date_raw.lower() == "present")
                        
                        experience_list.append(ExperienceDetail(
                            company_name=exp.get("company") or exp.get("company_name"),
                            job_title=exp.get("position") or exp.get("role") or exp.get("title"),
                            duration=duration,
                            start_date=start_date,
                            end_date=end_date,
                            description=exp.get("description"),
                            is_current=is_current
                        ))
            
            hit = SearchCandidateHit(
                candidate_id=doc["_id"],
                user_id=doc.get("user"),
                full_name=full_name,
                current_job_title=current_job_title,
                employment_status=employment_status,
                location=location_value,
                contact_info=contact_info,
                skills=skills_list,
                skills_count=len(skills_list),
                experience=experience_list,
                experience_count=len(experience_list),
                similarity_score=doc.get("score"),
                source=candidate_scope,
                embedding_model=doc.get("embedding_model"),
                embedding_generated_at=doc.get("embedding_last_generated_at"),
            )
            results.append(hit)

        logger.debug(f"Ranked {len(results)} candidates")
        return results

    async def _fetch_and_rank_profiles_manually(
        self,
        jd_embedding: List[float],
        candidate_ids: List[str],
    ) -> List[SearchCandidateHit]:
        """
        Fetch profiles by ID and rank them manually using cosine similarity.
        Used for applied search to ensure all applicants are returned regardless of vector search limits.
        """
        if not candidate_ids:
            return []
            
        # Convert IDs to ObjectIds
        object_ids = []
        for cid in candidate_ids:
            try:
                object_ids.append(ObjectId(cid))
            except InvalidId:
                continue
                
        # Fetch all profiles directly
        cursor = self._userprofiles.find({"user": {"$in": object_ids}})
        documents = await cursor.to_list(length=len(object_ids))
        
        logger.info(f"Manually fetched {len(documents)} profiles for ranking")
        
        # Calculate cosine similarity manually
        import numpy as np
        from numpy.linalg import norm
        
        results = []
        jd_vec = np.array(jd_embedding)
        jd_norm = norm(jd_vec)
        
        for doc in documents:
            # Calculate score
            score = 0.0
            if "embedding_vector" in doc and doc["embedding_vector"]:
                cand_vec = np.array(doc["embedding_vector"])
                cand_norm = norm(cand_vec)
                if jd_norm > 0 and cand_norm > 0:
                    score = float(np.dot(jd_vec, cand_vec) / (jd_norm * cand_norm))
            
            # Add score to doc for processing
            doc["score"] = score
            
            # Process document into SearchCandidateHit (reuse logic)
            personal = doc.get("personal_information") or {}
            socials = doc.get("socials") or {}
            location_value = doc.get("location") or personal.get("location")
            
            # Extract personal information
            full_name = personal.get("full_name") or f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
            
            # Get current job info from most recent experience
            experiences_raw = doc.get("experience", [])
            current_job_title = None
            employment_status = None
            if experiences_raw and isinstance(experiences_raw, list) and len(experiences_raw) > 0:
                # Check if first experience is current
                latest_exp = experiences_raw[0]
                if isinstance(latest_exp, dict):
                    # Extract title from 'position' field first, fallback to 'role' or 'title'
                    current_job_title = latest_exp.get("position") or latest_exp.get("role") or latest_exp.get("title")
                    # Check if this is a current position
                    end_date_raw = latest_exp.get("end_date") or latest_exp.get("endDate")
                    # Position is current if end_date is None, or if it's a string saying "present"
                    is_current_position = (
                        not end_date_raw or 
                        (isinstance(end_date_raw, str) and end_date_raw.lower() == "present")
                    )
                    if is_current_position:
                        employment_status = "Currently Working"
                    else:
                        employment_status = "Open to Opportunities"
            
            # Extract contact info
            contact_info = ContactInfo(
                email=personal.get("email"),
                phone=personal.get("phone") or personal.get("phone_number"),
                github=socials.get("github"),
                linkedin=socials.get("linkedin")
            )
            
            # Extract skills with proficiency levels
            skills_list = []
            skills_raw = doc.get("skills", [])
            if isinstance(skills_raw, list):
                for skill in skills_raw:
                    if isinstance(skill, str):
                        skills_list.append(SkillDetail(skill_name=skill, proficiency_level=None))
                    elif isinstance(skill, dict):
                        skill_name = skill.get("skill_name") or skill.get("name")
                        # MongoDB stores as 'skill_proficiency', check that first
                        proficiency = (
                            skill.get("skill_proficiency") or 
                            skill.get("proficiency_level") or 
                            skill.get("proficiency") or 
                            skill.get("level")
                        )
                        if skill_name:
                            skills_list.append(SkillDetail(skill_name=skill_name, proficiency_level=proficiency))
            
            # Extract experience details
            experience_list = []
            if isinstance(experiences_raw, list):
                for exp in experiences_raw:
                    if isinstance(exp, dict):
                        # Format duration - handle datetime objects from MongoDB
                        start_date_raw = exp.get("start_date") or exp.get("startDate")
                        end_date_raw = exp.get("end_date") or exp.get("endDate")
                        
                        # Convert datetime objects to strings
                        if isinstance(start_date_raw, dt):
                            start_date = start_date_raw.strftime("%b %Y")  # e.g., "Jun 2022"
                        else:
                            start_date = str(start_date_raw) if start_date_raw else ""
                        
                        if isinstance(end_date_raw, dt):
                            end_date = end_date_raw.strftime("%b %Y")
                        elif not end_date_raw:
                            end_date = "Present"
                        else:
                            end_date = str(end_date_raw)
                        
                        duration = f"{start_date} - {end_date}" if start_date else None
                        
                        is_current = not end_date_raw or (isinstance(end_date_raw, str) and end_date_raw.lower() == "present")
                        
                        experience_list.append(ExperienceDetail(
                            company_name=exp.get("company") or exp.get("company_name"),
                            job_title=exp.get("position") or exp.get("role") or exp.get("title"),
                            duration=duration,
                            start_date=start_date,
                            end_date=end_date,
                            description=exp.get("description"),
                            is_current=is_current
                        ))
            
            hit = SearchCandidateHit(
                candidate_id=doc["_id"],
                user_id=doc.get("user"),
                full_name=full_name,
                current_job_title=current_job_title,
                employment_status=employment_status,
                location=location_value,
                contact_info=contact_info,
                skills=skills_list,
                skills_count=len(skills_list),
                experience=experience_list,
                experience_count=len(experience_list),
                similarity_score=score,
                source="applied",
                embedding_model=doc.get("embedding_model"),
                embedding_generated_at=doc.get("embedding_last_generated_at"),
            )
            results.append(hit)
            
        return results
