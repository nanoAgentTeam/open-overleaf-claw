from pydantic import BaseModel
from typing import List, Optional, Any

class MessageAttachment(BaseModel):
    content_type: str
    url: str
    filename: Optional[str] = None
    height: Optional[int] = None
    width: Optional[int] = None
    size: Optional[int] = None

class Author(BaseModel):
    id: str
    user_openid: Optional[str] = None
    member_openid: Optional[str] = None
    username: Optional[str] = None

class MessageEvent(BaseModel):
    id: str
    content: str
    timestamp: str
    author: Author
    attachments: Optional[List[MessageAttachment]] = None
    group_openid: Optional[str] = None
    channel_id: Optional[str] = None

class WSPayload(BaseModel):
    op: int
    d: Optional[Any] = None
    s: Optional[int] = None
    t: Optional[str] = None
