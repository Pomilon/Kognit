from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from kognit.models.analysis import RepoAnalysis

class ProjectHighlight(BaseModel):
    name: str = Field(..., description="Name of the project")
    description: str = Field(..., description="Brief summary of the project and its unique selling point")
    technical_complexity: str = Field(default="Not specified", description="Analysis of the technical challenges and complexity")
    impact: str = Field(default="Significant technical contribution", description="The impact of the project (e.g., 'Reduced latency by 20%')")
    technologies: List[str] = Field(default_factory=list, description="Technologies used in this project")
    role: str = Field(default="Developer", description="Developer's role in the project (e.g., Architect, Maintainer, Contributor)")
    url: Optional[str] = None

class TechnicalDNA(BaseModel):
    languages: List[str] = Field(default_factory=list, description="Primary programming languages with weighted expertise")
    frameworks: List[str] = Field(default_factory=list, description="Frameworks and libraries frequently used")
    tools: List[str] = Field(default_factory=list, description="Development tools and infrastructure (e.g., Docker, K8s, Redis)")
    specialization: str = Field(default="Generalist Systems Engineering", description="Core area of expertise inferred from activity")

class ExternalFootprint(BaseModel):
    writing_style: str = Field(default="Technical and objective", description="Analysis of the developer's writing style and communication")
    interests: List[str] = Field(default_factory=list, description="Research interests or hobbies identified from external sources")
    community_signals: List[str] = Field(default_factory=list, description="Signals of community involvement (e.g., stars, follows, discussions)")

class DeveloperIdentity(BaseModel):
    name: str = Field(..., description="Full name or primary handle of the developer")
    avatar_url: Optional[str] = Field(None, description="URL to the developer's profile picture")
    headline: str = Field(..., description="A professional one-liner summarizing the developer's identity")
    summary: str = Field(..., description="A multi-paragraph technical biography focusing on impact and patterns")
    technical_dna: TechnicalDNA = Field(default_factory=TechnicalDNA)
    project_highlights: List[ProjectHighlight] = Field(default_factory=list)
    external_footprint: ExternalFootprint = Field(default_factory=ExternalFootprint)
    role_inference: str = Field(default="Software Engineer", description="Final inference of the developer's primary persona")
    external_links: List[str] = Field(default_factory=list, description="Verified links to GitHub, blogs, portfolios, etc.")
    
    # Extended Analysis Fields
    technical_depth_report: Optional[str] = Field(None, description="A deep-dive analysis of architectural patterns, code complexity, and technical decisions. (Markdown)")
    ecosystem_report: Optional[str] = Field(None, description="Analysis of the developer's connections, community influence, and ecosystem reach. (Markdown)")
    
    # Full Dive Data (Direct Injection)
    repository_analyses: Optional[List[RepoAnalysis]] = Field(default_factory=list, description="Detailed analyses of individual repositories.")