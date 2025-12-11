from datetime import datetime
from typing import List, Optional ,Dict, Any, Literal
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId
from app.models.base import PyObjectId

class EducationEntry(BaseModel):
    id:PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    institution: str
    degree: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    cgpa_or_percentage: Optional[float] = None
    description: Optional[str] = ""

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# repeat for ExperienceEntry, SkillEntry (With proficiency enum), ProjectEntry, plus placeholders for other arrays even if empty

class ExperienceEntry(BaseModel):
    id:PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    company: str
    position: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class SkillEntry(BaseModel):
    id:PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    skill_name: str
    proficiency: Literal["Beginner","Intermediate","Expert"] = Field("Beginner", alias = "proficiency") # Could be an Enum for levels like Beginner, Intermediate, Expert

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class ProjectEntry(BaseModel):
    id:PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    project_name: str
    description: Optional[str] = None
    link: Optional[str] = None

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class PersonalInformation(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    expected_salary: Optional[int] = None

class EmbeddingMetadata(BaseModel):
    vector: Optional[List[float]] = Field(None, alias = "embedding_vector")
    model: Optional[str] = Field(None, alias = "embedding_model")
    dimensions: Optional[int] = Field(None, alias = "embedding_dimensions")
    version: Optional[str] = Field(None, alias = "embedding_version")
    last_generated_at: Optional[datetime] = Field(None, alias = "embedding_last_generated_at")
    status : Literal["queued", "processing", "ready", "error"] = Field("queued", alias="embedding_status")
    error: Optional[str] = Field(None, alias="embedding_error")

class CandidateBase(BaseModel):
    user_id : PyObjectId = Field(alias="user")
    personal_information: PersonalInformation
    industry: Optional[str] = None
    is_draft: bool = Field(False, alias="isDraft")
    socials: Dict[str, Any] = Field(default_factory=dict)
    education: List[EducationEntry] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    skills: List[SkillEntry] = Field(default_factory=list)
    personal_projects: List[ProjectEntry] = Field(default_factory=list)
    certifications: List[ProjectEntry] = Field(default_factory=list)
    achievements: List[ProjectEntry] = Field(default_factory=list)

    class Config:
        allow_population_by_field_name = True

class CandidateCreate(CandidateBase):
    embedding_metadata: Optional[EmbeddingMetadata] = None

class CandidateUpdate(BaseModel):
    personal_information : Optional[PersonalInformation]
    industry: Optional[str]
    is_draft : Optional[bool]
    socials: Optional[Dict[str, Any]]
    education : Optional[List[EducationEntry]]
    experience : Optional[List[ExperienceEntry]]
    skills : Optional[List[SkillEntry]]
    personal_projects : Optional[List[ProjectEntry]]
    certifications : Optional[List[ProjectEntry]]
    achievements : Optional[List[ProjectEntry]]
    

class CandidateInDB(CandidateBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    version: Optional[int] = Field(None, alias="__v")
    embedding_metadata: EmbeddingMetadata


class CandidateResponse(CandidateInDB):
        class Config:
            json_encoders = {PyObjectId: str}
            allow_population_by_field_name = True
            arbitrary_types_allowed = True