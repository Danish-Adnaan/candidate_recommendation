from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

from app.models.base import PyObjectId


class JobEmbeddingMetadata(BaseModel):
    vector: Optional[List[float]] = Field(default=None, alias="job_embedding_vector")
    vector_size: Optional[int] = Field(default=None, alias="job_embedding_vector_size")
    model: Optional[str] = Field(default=None, alias="job_embedding_model")
    generated_at: Optional[datetime] = Field(default=None, alias="job_embedding_updated_at")
    status: Optional[str] = Field(default="pending", alias="job_embedding_status")
    error: Optional[str] = Field(default=None, alias="job_embedding_error")

    class Config:
        allow_population_by_field_name = True


class JobListingBase(BaseModel):
    title: str
    description: str
    company_id: str = Field(alias="companyId")
    posted_by: str = Field(alias="postedBy")
    employment_type: Optional[str] = Field(default=None, alias="employmentType")
    work_model: Optional[str] = Field(default=None, alias="workModel")
    experience_range: Optional[Dict[str, int]] = Field(default=None, alias="experienceRange")
    compensation: Optional[Dict[str, Any]] = None
    skills_required: List[str] = Field(default_factory=list, alias="skillsRequired")
    industry: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    initial_questions: List[Dict[str, Any]] = Field(default_factory=list, alias="initialQuestions")
    short_id: Optional[str] = Field(default=None, alias="shortId")
    is_hiring: Optional[bool] = Field(default=None, alias="isHiring")

    class Config:
        allow_population_by_field_name = True


class JobListingInDB(JobListingBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    updated_at: datetime = Field(default_factory=datetime.utcnow, alias="updatedAt")
    embedding: JobEmbeddingMetadata = Field(default_factory=JobEmbeddingMetadata)

    class Config:
        allow_population_by_field_name = True
        json_encoders = {PyObjectId: str}
