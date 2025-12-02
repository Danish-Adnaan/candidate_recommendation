"""Search endpoints for applied and global candidate matches."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config.settings import Settings
from app.db.client import get_database
from app.models.search_models import GlobalSearchResponse, NewAppliedSearchResponse
from app.services.base import NotFoundError
from app.services.embedding_service import EmbeddingService
from app.services.search_service import SearchService
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


async def get_search_service() -> SearchService:
    """Provide a fully wired SearchService instance per request."""
    settings = Settings()
    db = get_database(settings)

    jobs = db[settings.JOB_COLLECTION]
    userprofiles = db[settings.USER_PROFILES_COLLECTION]
    applications = db[settings.APPLICATION_COLLECTION]
    embedding_service = EmbeddingService(settings=settings)

    return SearchService(
        settings=settings,
        job_collection=jobs,
        userprofiles_collection=userprofiles,
        application_collection=applications,
        embedding_service=embedding_service,
    )


@router.get("/applied", response_model=NewAppliedSearchResponse)
async def search_applied_candidates(
    job_id: str = Query(..., description="Job identifier from jobcollections"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    count: int = Query(50, ge=1, le=200, description="Results per page"),
    service: SearchService = Depends(get_search_service),
):
    """
    Search for candidates who have applied to a specific job.
    
    Results are ranked by semantic similarity between the job description
    and candidate profiles using vector embeddings.
    
    Args:
        job_id: Job identifier
        page: Page number (1-indexed)
        count: Number of results per page (1-200)
        service: Injected search service
        
    Returns:
        Applied search response with ranked candidates
        
    Raises:
        HTTPException: 404 if job not found, 500 for other errors
    """
    logger.info(f"Applied search request: job_id={job_id}, page={page}, count={count}")
    
    try:
        response = await service.search_applied(job_id=job_id, page=page, count=count)
        logger.info(f"Applied search completed: {len(response.results)} results")
        return response
    except NotFoundError as exc:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Applied search error for job {job_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(exc)}") from exc


@router.get("/global", response_model=GlobalSearchResponse)
async def search_global_candidates(
    job_id: str = Query(..., description="Job identifier from jobcollections"),
    count: int = Query(50, ge=1, le=200, description="Number of results to return"),
    service: SearchService = Depends(get_search_service),
):
    """
    Search for candidates globally (not limited to applicants).
    
    Results are ranked by semantic similarity between the job description
    and candidate profiles using vector embeddings.
    
    Args:
        job_id: Job identifier for context
        count: Number of results to return (1-200)
        service: Injected search service
        
    Returns:
        Global search response with ranked candidates
        
    Raises:
        HTTPException: 404 if job not found, 500 for other errors
    """
    logger.info(f"Global search request: job_id={job_id}, count={count}")
    
    try:
        response = await service.search_global(job_id=job_id, count=count)
        logger.info(f"Global search completed: {len(response.results)} results")
        return response
    except NotFoundError as exc:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Global search error for job {job_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(exc)}") from exc
