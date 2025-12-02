from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from openai import AzureOpenAI
from openai._exceptions import OpenAIError

from app.config.settings import Settings


class EmbeddingServiceError(RuntimeError):
    """Raised when Azure OpenAI returns an error or malformed payload."""


@dataclass(frozen=True)
class EmbeddingResult:
    vector: List[float]
    model: str
    generated_at: datetime


class EmbeddingService:
    def __init__(
        self,
        settings: Settings,
        *,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        self.settings = settings
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds

    async def generate_candidate_embedding(self, candidate_doc: Dict[str, Any]) -> EmbeddingResult:
        text = self._build_candidate_text(candidate_doc)
        vector = await self._generate_embedding(text)
        self._validate_vector(vector)
        return EmbeddingResult(
            vector=vector,
            model=self.settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            generated_at=datetime.utcnow(),
        )

    async def generate_job_embedding(self, job_doc: Dict[str, Any]) -> EmbeddingResult:
        text = self._build_job_text(job_doc)
        vector = await self._generate_embedding(text)
        self._validate_vector(vector)
        return EmbeddingResult(
            vector=vector,
            model=self.settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            generated_at=datetime.utcnow(),
        )

    async def _generate_embedding(self, text: str) -> List[float]:
        return await asyncio.to_thread(self._sync_generate_embedding, text)

    def _sync_generate_embedding(self, text: str) -> List[float]:
        client = _get_azure_client(self.settings)
        attempt = 0
        while True:
            try:
                response = client.embeddings.create(
                    model=self.settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
                    input=text,
                )
                vector = response.data[0].embedding
                if not isinstance(vector, list):
                    raise EmbeddingServiceError("Embedding vector missing or invalid.")
                return vector
            except OpenAIError as exc:
                attempt += 1
                if attempt >= self._max_retries:
                    raise EmbeddingServiceError("Azure OpenAI embedding request failed") from exc
                time.sleep(self._retry_delay_seconds * attempt)

    def _validate_vector(self, vector: Sequence[float]) -> None:
        if len(vector) != self.settings.EMBEDDING_VECTOR_SIZE:
            raise ValueError(
                f"Expected embedding length {self.settings.EMBEDDING_VECTOR_SIZE}, got {len(vector)}."
            )

    def _build_candidate_text(self, doc: Dict[str, Any]) -> str:
        personal = doc.get("personal_information", {})
        first = (personal.get("first_name") or "").strip()
        last = (personal.get("last_name") or "").strip()
        full_name = " ".join(part for part in [first, last] if part) or "Unnamed candidate"

        skills = doc.get("skills") or []
        skills_str = ", ".join(skills) if skills else "Skills not provided"

        experiences = doc.get("experience") or []
        exp_segments: List[str] = []
        for exp in experiences:
            role = exp.get("role") or exp.get("title") or "Role n/a"
            company = exp.get("company") or exp.get("organization") or "Org n/a"
            years = exp.get("duration") or exp.get("years") or ""
            exp_segments.append(f"{role} at {company} ({years})".strip())
        experience_str = "; ".join(exp_segments) if exp_segments else "Experience not provided"

        summary = doc.get("summary") or doc.get("about") or "No summary provided"

        return (
            f"{full_name} | Skills: {skills_str} | Experience: {experience_str} | Summary: {summary}"
        )

    def _build_job_text(self, doc: Dict[str, Any]) -> str:
        title = doc.get("title") or "Untitled role"
        employment_type = doc.get("employmentType") or doc.get("employment_type") or "Type n/a"
        work_model = doc.get("workModel") or doc.get("work_model") or "Work model n/a"
        experience_range = (doc.get("experienceRange") or {}).get("summary") or "Experience range n/a"

        skills = doc.get("skillsRequired") or doc.get("skills") or []
        skills_str = ", ".join(skills) if skills else "Skills not provided"

        industry = doc.get("industry") or doc.get("industries") or []
        industry_str = ", ".join(industry) if isinstance(industry, list) else str(industry or "Industry n/a")

        locations = doc.get("locations") or doc.get("location") or []
        if isinstance(locations, list):
            loc_strs = []
            for loc in locations:
                if isinstance(loc, dict):
                    # Extract city, state, country if available
                    parts = [loc.get(k) for k in ["city", "state", "country"] if loc.get(k)]
                    if parts:
                        loc_strs.append(", ".join(parts))
                elif isinstance(loc, str):
                    loc_strs.append(loc)
            locations_str = ", ".join(loc_strs) if loc_strs else "Locations not provided"
        else:
            locations_str = locations or "Locations not provided"

        description = doc.get("description") or "Description not provided"

        parts = [
            title,
            employment_type,
            work_model,
            experience_range,
            f"Skills: {skills_str}",
            f"Industry: {industry_str}",
            f"Locations: {locations_str}",
            f"Description: {description}",
        ]
        return " | ".join(part.strip() for part in parts)

    @staticmethod
    def jd_cache_key(job_id: str, updated_at: datetime) -> str:
        return f"{job_id}:{updated_at.isoformat()}"


_azure_client: Optional[AzureOpenAI] = None


def _get_azure_client(settings: Settings) -> AzureOpenAI:
    global _azure_client
    if _azure_client is None:
        _azure_client = AzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
    return _azure_client