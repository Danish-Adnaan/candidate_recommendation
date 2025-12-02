"""Pydantic DTOs for search routes and related filters."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import PyObjectId

MODEL_CONFIG = ConfigDict(populate_by_name=True, json_encoders={PyObjectId: str})


class SkillFilter(BaseModel):
    model_config = MODEL_CONFIG

    name: str
    minimum_level: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"


class CandidateFilter(BaseModel):
    model_config = MODEL_CONFIG

    industries: Optional[List[str]] = None
    min_experience_years: Optional[int] = None
    max_years_experience: Optional[int] = None
    skills: Optional[List[SkillFilter]] = None
    project_keywords: Optional[List[str]] = None
    education_levels: Optional[List[str]] = None
    ready_for_relocation: Optional[bool] = None


class PaginationParams(BaseModel):
    model_config = MODEL_CONFIG

    page: int = 1
    page_size: int = 20


class BasicSearchRequest(BaseModel):
    model_config = MODEL_CONFIG

    keyword: Optional[str] = None
    filters: Optional[CandidateFilter] = None
    pagination: PaginationParams = PaginationParams()


class SemanticSearchRequest(BaseModel):
    model_config = MODEL_CONFIG

    query: str
    filters: Optional[CandidateFilter] = None
    limit: int = 10
    min_score: float = 0.0


class CandidateSearchSnippet(BaseModel):
    model_config = MODEL_CONFIG

    id: PyObjectId = Field(alias="_id")
    full_name: str
    industry: Optional[str] = None
    years_experience: Optional[int] = None
    matched_skills: List[str] = Field(default_factory=list)
    score: Optional[float] = None


class SearchResponse(BaseModel):
    model_config = MODEL_CONFIG

    results: List[CandidateSearchSnippet]
    pagination: PaginationParams
    total_count: int


class SemanticSearchResponse(SearchResponse):
    model_config = MODEL_CONFIG

    embedding_model: Optional[str] = None


class SkillDetail(BaseModel):
    """Skill with proficiency level."""
    model_config = MODEL_CONFIG
    
    skill_name: str
    proficiency_level: Optional[str] = None  # Expert, Intermediate, Beginner


class ExperienceDetail(BaseModel):
    """Work experience entry."""
    model_config = MODEL_CONFIG
    
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    duration: Optional[str] = None  # e.g., "Jun 2022 - Present"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    is_current: Optional[bool] = False


class ContactInfo(BaseModel):
    """Contact information."""
    model_config = MODEL_CONFIG
    
    email: Optional[str] = None
    phone: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None


class SearchCandidateHit(BaseModel):
    """Comprehensive candidate information returned for search results."""

    model_config = MODEL_CONFIG

    # Basic identifiers
    candidate_id: PyObjectId = Field(alias="_id")
    user_id: Optional[PyObjectId] = None
    
    # Personal Information
    full_name: Optional[str] = None
    current_job_title: Optional[str] = None
    employment_status: Optional[str] = None  # "Currently Working", "Open to Opportunities", etc.
    location: Optional[str] = None
    
    # Contact Information
    contact_info: Optional[ContactInfo] = None
    
    # Skills with proficiency
    skills: List[SkillDetail] = Field(default_factory=list)
    skills_count: Optional[int] = None
    
    # Experience
    experience: List[ExperienceDetail] = Field(default_factory=list)
    experience_count: Optional[int] = None
    years_experience: Optional[float] = None
    
    # Search metadata
    similarity_score: Optional[float] = None
    source: Optional[str] = Field(default=None, description="'applied' or 'global'")
    embedding_model: Optional[str] = None
    embedding_generated_at: Optional[datetime] = None


class PaginationMeta(BaseModel):
    model_config = MODEL_CONFIG

    page: int = 1
    page_size: int = 50
    total_matches: Optional[int] = None





class GlobalSearchResponse(BaseModel):
    model_config = MODEL_CONFIG

    job_id: Optional[str] = None
    requested_count: int
    results: List[SearchCandidateHit]
    cache_hit: bool = False
    latency_ms: Optional[float] = None
    embedding_model: Optional[str] = None


# ========== Applied Search Specific Models ==========

class InitialQuestionAnswer(BaseModel):
    """Question and answer pair from application."""
    model_config = MODEL_CONFIG
    
    question: str
    candidate_answer: Optional[bool] = Field(None, alias="candidateAnswer")
    expected_answer: Optional[bool] = Field(None, alias="expectedAnswer")
    _id: Optional[PyObjectId] = None


class StageTimestamp(BaseModel):
    """Timestamp information for stages."""
    model_config = MODEL_CONFIG
    
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    _id: Optional[PyObjectId] = None


class RuthiSideStage(BaseModel):
    """Ruthi-side screening stage information."""
    model_config = MODEL_CONFIG
    
    name: str
    order: int
    is_completed: bool = Field(False, alias="isCompleted")
    timestamps: Optional[StageTimestamp] = None
    _id: Optional[PyObjectId] = None


class AppliedCandidateHit(BaseModel):
    """Combined candidate and application information for applied search."""
    model_config = MODEL_CONFIG
    
    # Application Collection fields
    application_id: PyObjectId = Field(alias="_id")
    candidate_id: PyObjectId = Field(alias="candidateId")
    job_id: PyObjectId = Field(alias="jobId")
    
    # From userprofiles
    full_name: Optional[str] = None
    job_status: Optional[str] = None  # "Fresher" or "{job_title} at {company}"
    skills: List[SkillDetail] = Field(default_factory=list)
    
    # Application details
    initial_questions_answers: List[InitialQuestionAnswer] = Field(default_factory=list, alias="initialQuestionsAnswers")
    current_status: str = Field(alias="currentStatus")
    ruthi_side_stages: List[RuthiSideStage] = Field(default_factory=list, alias="ruthiSideStages")
    moved_to_recruiter: bool = Field(False, alias="movedToRecruiter")
    notes: str = ""
    applied_at: Optional[datetime] = Field(None, alias="appliedAt")
    recruiter_side_stages: List = Field(default_factory=list, alias="recruiterSideStages")
    documents: List = Field(default_factory=list)
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    
    # Search metadata
    similarity_score: Optional[float] = None


class NewAppliedSearchResponse(BaseModel):
    """Response model for applied candidate search with application details."""
    model_config = MODEL_CONFIG
    
    job_id: str
    pagination: PaginationMeta
    results: List[AppliedCandidateHit]
    cache_hit: bool = False
    latency_ms: Optional[float] = None
    embedding_model: Optional[str] = None
