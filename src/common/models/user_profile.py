from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class UserProfile:
    phone_number: str
    user_type: Optional[str] = None  # "worker" | "employer"
    profile_data: dict = field(default_factory=dict)  # skills, preferred locations, salary expectations
    preferences: dict = field(default_factory=dict)  # language, notification prefs
    match_history: list[dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dynamodb_item(self) -> dict:
        item = {
            "phone_number": self.phone_number,
            "profile_data": self.profile_data,
            "preferences": self.preferences,
            "match_history": self.match_history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.user_type is not None:
            item["user_type"] = self.user_type
        return item

    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "UserProfile":
        return cls(
            phone_number=item["phone_number"],
            user_type=item.get("user_type"),
            profile_data=item.get("profile_data", {}),
            preferences=item.get("preferences", {}),
            match_history=item.get("match_history", []),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )
