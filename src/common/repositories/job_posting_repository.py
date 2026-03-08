from typing import Optional

from boto3.dynamodb.conditions import Attr, Key

from common import config
from common.logger import get_logger
from common.models.job_posting import JobPosting
from common.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


class JobPostingRepository(BaseRepository):
    """Repository for job postings in DynamoDB."""

    GSI1_NAME = "gsi1-location-jobtype"
    GSI2_NAME = "gsi2-status-created"

    def __init__(self):
        super().__init__(config.JOB_POSTINGS_TABLE)

    def create_posting(self, posting: JobPosting) -> None:
        """Create a new job posting."""
        self.put_item(posting.to_dynamodb_item())
        logger.info("Created job posting", extra={"job_id": posting.job_id})

    def get_posting(self, job_id: str) -> Optional[JobPosting]:
        """Get a job posting by ID."""
        item = self.get_item({"job_id": job_id})
        if item:
            return JobPosting.from_dynamodb_item(item)
        return None

    def get_active_postings_by_city(self, city: str, limit: int = 50) -> list[JobPosting]:
        """Query active postings for a city using GSI1."""
        items = self.query(
            key_condition=Key("gsi1pk").eq(f"LOC#{city.lower()}"),
            index_name=self.GSI1_NAME,
            filter_expression=Attr("status").eq("active"),
            limit=limit,
        )
        return [JobPosting.from_dynamodb_item(item) for item in items]

    def get_postings_by_location_and_type(
        self, city: str, job_type: Optional[str] = None, limit: int = 50
    ) -> list[JobPosting]:
        """Query postings by city and optionally by job type using GSI1."""
        key_condition = Key("gsi1pk").eq(f"LOC#{city.lower()}")
        if job_type:
            key_condition = key_condition & Key("gsi1sk").begins_with(f"TYPE#{job_type.lower()}")

        items = self.query(
            key_condition=key_condition,
            index_name=self.GSI1_NAME,
            filter_expression=Attr("status").eq("active"),
            limit=limit,
        )
        return [JobPosting.from_dynamodb_item(item) for item in items]

    def mark_filled(self, job_id: str) -> None:
        """Mark a job posting as filled."""
        self.update_item(key={"job_id": job_id}, updates={"status": "filled"})
        logger.info("Marked job as filled", extra={"job_id": job_id})

    def mark_expired(self, job_id: str) -> None:
        """Mark a job posting as expired."""
        self.update_item(key={"job_id": job_id}, updates={"status": "expired"})
