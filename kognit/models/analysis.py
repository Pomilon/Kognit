from typing import List
from pydantic import BaseModel, Field

class RepoAnalysis(BaseModel):
    name: str
    summary: str
    technical_deconstruction: str = Field(default="Analysis unavailable.", description="Deep technical breakdown of the repository.")
    key_technologies: List[str] = Field(default_factory=list)
    complexity_score: int = Field(default=5, description="1-10 score of technical difficulty")
