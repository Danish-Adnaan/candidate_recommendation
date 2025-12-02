"""Shared helpers for service modules (exceptions, pagination)"""

from typing import List, Dict , Any

class ServiceError(Exception):
    """Base exception for service layer errors."""
    
class NotFoundError(ServiceError):
    """Raised when a requested resource is not found."""

def paginate_results(results: List[Any], *, page: int, page_size: int) -> Dict[str, Any]:
    """Wrap result lists with pagination metadata."""
    total = len(results)
    return {
        "results" : results,
        "pagination" : {
            "page" : page,
            "page_size" : page_size,
            "total_count" : total,
        },
    }