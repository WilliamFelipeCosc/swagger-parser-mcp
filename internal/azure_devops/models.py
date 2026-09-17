from typing import Optional

from pydantic import BaseModel


class Comment(BaseModel):
    id: int
    text: Optional[str] = None
    created_by: Optional[str] = None
    created_date: Optional[str] = None


class WorkItem(BaseModel):
    id: int
    parent_id: Optional[int] = None
    title: Optional[str] = None
    state: Optional[str] = None
    assigned_to: Optional[str] = None
    area_path: Optional[str] = None
    iteration_path: Optional[str] = None
    priority: Optional[int] = None
    effort: Optional[float] = None
    business_value: Optional[float] = None
    time_criticality: Optional[float] = None
    start_date: Optional[str] = None
    target_date: Optional[str] = None
    created_date: str
    changed_date: str
    description: Optional[str] = None
    tags: Optional[str] = None
    url: str
    comments: Optional[list[Comment]] = None
    children: Optional[list["WorkItem"]] = None


WorkItem.model_rebuild()
