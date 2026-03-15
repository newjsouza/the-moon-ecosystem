"""
models.py - Data models for GitHub Skill
Used for repository management and issue tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class IssueState(Enum):
    OPEN = "open"
    CLOSED = "closed"

@dataclass
class GitHubRepo:
    """Represents a GitHub repository"""
    id: str
    name: str
    full_name: str
    owner: str
    html_url: str
    description: Optional[str] = None
    private: bool = False
    stargazers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    language: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "full_name": self.full_name,
            "owner": self.owner,
            "html_url": self.html_url,
            "description": self.description,
            "private": self.private,
            "stargazers": self.stargazers_count,
            "open_issues": self.open_issues_count,
            "language": self.language
        }

@dataclass
class GitHubIssue:
    """Represents a GitHub issue"""
    id: str
    number: int
    title: str
    body: Optional[str] = None
    state: IssueState = IssueState.OPEN
    author: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    labels: List[str] = field(default_factory=list)
    html_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "state": self.state.value,
            "author": self.author,
            "labels": self.labels,
            "url": self.html_url
        }
