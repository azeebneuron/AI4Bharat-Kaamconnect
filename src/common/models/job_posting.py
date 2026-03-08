from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4


@dataclass
class Location:
    city: str
    area: Optional[str] = None
    pincode: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"city": self.city}
        if self.area is not None:
            d["area"] = self.area
        if self.pincode is not None:
            d["pincode"] = self.pincode
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        return cls(city=data.get("city", ""), area=data.get("area"), pincode=data.get("pincode"))


@dataclass
class SalaryRange:
    period: str = "daily"  # "daily" | "monthly"
    min_amount: Optional[int] = None
    max_amount: Optional[int] = None

    def to_dict(self) -> dict:
        d: dict = {"period": self.period}
        if self.min_amount is not None:
            d["min_amount"] = self.min_amount
        if self.max_amount is not None:
            d["max_amount"] = self.max_amount
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SalaryRange":
        return cls(
            min_amount=data.get("min_amount") or data.get("min"),
            max_amount=data.get("max_amount") or data.get("max"),
            period=data.get("period", "daily"),
        )


@dataclass
class Availability:
    days: list[str] = field(default_factory=list)
    hours: str = "flexible"  # "morning" | "afternoon" | "evening" | "night" | "flexible"

    def to_dict(self) -> dict:
        return {"days": self.days, "hours": self.hours}

    @classmethod
    def from_dict(cls, data: dict) -> "Availability":
        return cls(days=data.get("days", []), hours=data.get("hours", "flexible"))


@dataclass
class JobPosting:
    job_id: str
    employer_phone: str
    job_type: str
    location: Location
    salary: SalaryRange
    availability: Availability = field(default_factory=Availability)
    required_skills: list[str] = field(default_factory=list)
    description: Optional[str] = None
    urgency: str = "flexible"  # "immediate" | "within_week" | "flexible"
    status: str = "active"  # "active" | "filled" | "expired"
    created_at: str = ""
    expires_at: int = 0

    def __post_init__(self):
        now = datetime.now(timezone.utc)
        if not self.created_at:
            self.created_at = now.isoformat()
        if not self.expires_at:
            # Job postings expire in 7 days by default
            self.expires_at = int((now + timedelta(days=7)).timestamp())

    @property
    def gsi1pk(self) -> str:
        """GSI1 partition key: LOC#<city>"""
        return f"LOC#{self.location.city.lower()}"

    @property
    def gsi1sk(self) -> str:
        """GSI1 sort key: TYPE#<job_type>#<created_at>"""
        return f"TYPE#{self.job_type.lower()}#{self.created_at}"

    def to_dynamodb_item(self) -> dict:
        item = {
            "job_id": self.job_id,
            "employer_phone": self.employer_phone,
            "job_type": self.job_type,
            "location": self.location.to_dict(),
            "salary": self.salary.to_dict(),
            "availability": self.availability.to_dict(),
            "required_skills": self.required_skills,
            "urgency": self.urgency,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "gsi1pk": self.gsi1pk,
            "gsi1sk": self.gsi1sk,
        }
        if self.description is not None:
            item["description"] = self.description
        return item

    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "JobPosting":
        return cls(
            job_id=item["job_id"],
            employer_phone=item["employer_phone"],
            job_type=item["job_type"],
            location=Location.from_dict(item.get("location", {})),
            salary=SalaryRange.from_dict(item.get("salary", {})),
            availability=Availability.from_dict(item.get("availability", {})),
            required_skills=item.get("required_skills", []),
            description=item.get("description"),
            urgency=item.get("urgency", "flexible"),
            status=item.get("status", "active"),
            created_at=item.get("created_at", ""),
            expires_at=int(item.get("expires_at", 0)),
        )

    @staticmethod
    def generate_id() -> str:
        return f"job_{uuid4().hex[:12]}"
