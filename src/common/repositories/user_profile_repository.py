from datetime import datetime, timezone
from typing import Optional

from common import config
from common.logger import get_logger
from common.models.user_profile import UserProfile
from common.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


class UserProfileRepository(BaseRepository):
    """Repository for user profiles in DynamoDB."""

    def __init__(self):
        super().__init__(config.USER_PROFILES_TABLE)

    def get_profile(self, phone_number: str) -> Optional[UserProfile]:
        """Get a user profile by phone number."""
        item = self.get_item({"phone_number": phone_number})
        if item:
            return UserProfile.from_dynamodb_item(item)
        return None

    def get_or_create_profile(self, phone_number: str, user_type: Optional[str] = None) -> UserProfile:
        """Get existing profile or create a new one."""
        profile = self.get_profile(phone_number)
        if profile:
            return profile

        profile = UserProfile(phone_number=phone_number, user_type=user_type)
        self.put_item(profile.to_dynamodb_item())
        logger.info("Created new user profile")
        return profile

    def update_profile(self, phone_number: str, updates: dict) -> UserProfile:
        """Update profile fields."""
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = self.update_item(key={"phone_number": phone_number}, updates=updates)
        return UserProfile.from_dynamodb_item(updated)

    def add_match_to_history(self, phone_number: str, match_record: dict) -> None:
        """Append a match record to the user's match history."""
        profile = self.get_profile(phone_number)
        if not profile:
            return

        history = profile.match_history
        history.append(match_record)

        self.update_item(
            key={"phone_number": phone_number},
            updates={
                "match_history": history,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
