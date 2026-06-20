from pydantic import BaseModel, Field
from typing import List

class IngestRequest(BaseModel):
    repo_url: str = Field(..., description="The GitHub repository HTTPS URL to ingest.")

class IngestResponse(BaseModel):
    message: str
    total_chunks: int
    total_files: int

class QueryRequest(BaseModel):
    question: str = Field(..., description="The question about the codebase.")

class Citation(BaseModel):
    file: str
    start_line: int
    end_line: int

class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]