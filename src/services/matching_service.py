"""Job matching algorithm with weighted scoring.

Scores job postings against worker preferences using:
- Job type compatibility (30%)
- Location proximity (25%)
- Salary alignment (20%)
- Availability overlap (15%)
- Skills match (10%)
"""

from typing import Optional

from common import config
from common.logger import get_logger, log_context
from common.models.job_posting import Availability, JobPosting, Location, SalaryRange
from common.repositories.job_posting_repository import JobPostingRepository

logger = get_logger(__name__)

# Scoring weights from design doc
WEIGHTS = {
    "job_type": 0.30,
    "location": 0.25,
    "salary": 0.20,
    "availability": 0.15,
    "skills": 0.10,
}

# Related job types for partial matching
RELATED_JOBS: dict[str, list[str]] = {
    "plumber": ["pipe_fitter", "bathroom_installer", "ac_mechanic"],
    "electrician": ["wiring_technician", "ac_mechanic"],
    "maid": ["house_cleaner", "cook", "cleaner"],
    "cook": ["maid", "catering_helper"],
    "driver": ["delivery", "auto_driver", "cab_driver"],
    "carpenter": ["furniture_maker", "woodworker"],
    "painter": ["wall_painter", "decorator"],
    "mason": ["construction_worker", "tile_layer"],
    "security_guard": ["watchman"],
    "delivery": ["driver", "warehouse"],
    "warehouse": ["delivery", "helper", "factory"],
    "factory": ["warehouse", "helper", "machine_operator"],
    "tailor": ["seamstress", "alteration"],
    "gardener": ["landscaper", "mali"],
    "ac_mechanic": ["electrician", "plumber"],
    "welder": ["fabricator", "metalworker"],
    "helper": ["factory", "warehouse", "construction_worker"],
    "cleaner": ["maid", "house_cleaner"],
    "watchman": ["security_guard"],
}

# Nearby city mappings for location expansion
NEARBY_CITIES: dict[str, list[str]] = {
    "bangalore": ["bengaluru", "whitefield", "electronic city"],
    "bengaluru": ["bangalore", "whitefield", "electronic city"],
    "mumbai": ["navi mumbai", "thane", "kalyan"],
    "delhi": ["new delhi", "noida", "gurgaon", "gurugram", "faridabad", "ghaziabad"],
    "new delhi": ["delhi", "noida", "gurgaon"],
    "noida": ["delhi", "greater noida", "ghaziabad"],
    "gurgaon": ["gurugram", "delhi", "faridabad"],
    "gurugram": ["gurgaon", "delhi", "faridabad"],
    "chennai": ["tambaram", "avadi"],
    "hyderabad": ["secunderabad", "cyberabad"],
    "kolkata": ["howrah", "salt lake"],
    "pune": ["pimpri", "chinchwad", "hinjewadi"],
}


class MatchingService:
    """Finds and ranks job matches for workers."""

    def __init__(self, job_repo: Optional[JobPostingRepository] = None):
        self._job_repo = job_repo or JobPostingRepository()

    def find_matches(self, worker_data: dict, limit: int = 3) -> list[dict]:
        """Find top job matches for a worker's preferences.

        Returns list of {"posting": JobPosting, "score": float, "breakdown": dict}.
        """
        city = (worker_data.get("location") or {}).get("city", "")
        if not city:
            logger.warning("No city in worker data, cannot match")
            return []

        # Query candidates from DynamoDB
        candidates = self._job_repo.get_active_postings_by_city(city)

        # Expand to nearby cities if few results (cap total to avoid unbounded growth)
        if len(candidates) < 10:
            for nearby in NEARBY_CITIES.get(city.lower(), []):
                if len(candidates) >= 100:
                    break
                candidates.extend(self._job_repo.get_active_postings_by_city(nearby, limit=20))

        # Deduplicate by job_id
        seen = set()
        unique = []
        for posting in candidates:
            if posting.job_id not in seen:
                seen.add(posting.job_id)
                unique.append(posting)
        candidates = unique

        # Score each candidate
        scored = []
        for posting in candidates:
            score, breakdown = self._calculate_score(worker_data, posting)
            if score >= config.MATCH_THRESHOLD:
                scored.append({"posting": posting, "score": score, "breakdown": breakdown})

        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)

        logger.info(
            "Matching complete",
            extra=log_context(
                candidates=len(candidates),
                above_threshold=len(scored),
                returned=min(limit, len(scored)),
            ),
        )

        return scored[:limit]

    def _calculate_score(self, worker: dict, posting: JobPosting) -> tuple[float, dict]:
        """Calculate match score and breakdown."""
        jt = self._score_job_type(worker.get("job_type"), posting.job_type)
        loc = self._score_location(worker.get("location", {}), posting.location)
        sal = self._score_salary(worker.get("salary", {}), posting.salary)
        avail = self._score_availability(worker.get("availability", {}), posting.availability)
        skills = self._score_skills(worker.get("skills", []), posting.required_skills)

        breakdown = {
            "job_type": jt,
            "location": loc,
            "salary": sal,
            "availability": avail,
            "skills": skills,
        }

        total = (
            jt * WEIGHTS["job_type"]
            + loc * WEIGHTS["location"]
            + sal * WEIGHTS["salary"]
            + avail * WEIGHTS["availability"]
            + skills * WEIGHTS["skills"]
        )

        return total, breakdown

    def _score_job_type(self, worker_type: Optional[str], posting_type: str) -> float:
        """Score job type compatibility."""
        if not worker_type or not posting_type:
            return 0.0
        if worker_type.lower() == posting_type.lower():
            return 1.0
        if posting_type.lower() in RELATED_JOBS.get(worker_type.lower(), []):
            return 0.7
        return 0.0

    def _score_location(self, worker_loc: dict, posting_loc: Location) -> float:
        """Score location proximity."""
        if not worker_loc or not posting_loc:
            return 0.0

        worker_area = (worker_loc.get("area") or "").lower()
        worker_city = (worker_loc.get("city") or "").lower()
        posting_area = (posting_loc.area or "").lower()
        posting_city = posting_loc.city.lower()

        # Same area in same city
        if worker_area and posting_area and worker_area == posting_area and worker_city == posting_city:
            return 1.0
        # Same city
        if worker_city == posting_city:
            return 0.8
        # Nearby city
        if posting_city in NEARBY_CITIES.get(worker_city, []):
            return 0.6
        return 0.2

    def _score_salary(self, worker_sal: dict, posting_sal: SalaryRange) -> float:
        """Score salary alignment."""
        if not worker_sal or not posting_sal:
            return 0.5  # Unknown salary gets partial credit

        # Normalize to daily amounts
        worker_min = self._normalize_daily(worker_sal.get("min"), worker_sal.get("period", "daily"))
        worker_max = self._normalize_daily(worker_sal.get("max"), worker_sal.get("period", "daily"))
        posting_min = self._normalize_daily(posting_sal.min_amount, posting_sal.period)
        posting_max = self._normalize_daily(posting_sal.max_amount, posting_sal.period)

        if not any([worker_min, worker_max, posting_min, posting_max]):
            return 0.5

        # Use midpoints for comparison
        worker_sum = (worker_min or 0) + (worker_max or worker_min or 0)
        worker_mid = worker_sum / 2 if worker_sum else None

        posting_sum = (posting_min or 0) + (posting_max or posting_min or 0)
        posting_mid = posting_sum / 2 if posting_sum else None

        if worker_mid is None or posting_mid is None:
            return 0.5

        # Calculate alignment
        diff_pct = abs(worker_mid - posting_mid) / max(worker_mid, posting_mid)
        if diff_pct <= 0.1:
            return 1.0
        elif diff_pct <= 0.25:
            return 0.8
        elif diff_pct <= 0.5:
            return 0.4
        return 0.0

    def _score_availability(self, worker_avail: dict, posting_avail: Availability) -> float:
        """Score availability overlap."""
        if not worker_avail or not posting_avail:
            return 0.7  # Unknown gets decent score

        # Hours compatibility
        worker_hours = (worker_avail.get("hours") or "flexible").lower()
        posting_hours = posting_avail.hours.lower()

        if worker_hours == "flexible" or posting_hours == "flexible":
            hours_score = 1.0
        elif worker_hours == posting_hours:
            hours_score = 1.0
        else:
            hours_score = 0.3

        # Days overlap
        worker_days = set(d.lower() for d in (worker_avail.get("days") or []))
        posting_days = set(d.lower() for d in (posting_avail.days or []))

        if not worker_days or not posting_days:
            days_score = 0.7
        else:
            overlap = len(worker_days & posting_days)
            days_score = overlap / max(len(posting_days), 1)

        return (hours_score + days_score) / 2

    def _score_skills(self, worker_skills: list, required_skills: list) -> float:
        """Score skills match."""
        if not required_skills:
            return 1.0  # No requirements = anyone qualifies
        if not worker_skills:
            return 0.5  # Unknown skills get partial credit

        worker_set = set(s.lower() for s in worker_skills)
        required_set = set(s.lower() for s in required_skills)
        matched = len(worker_set & required_set)
        return matched / len(required_set)

    def _normalize_daily(self, amount: Optional[int], period: str) -> Optional[int]:
        """Normalize salary to daily amount."""
        if amount is None:
            return None
        if period == "monthly":
            return amount // 30
        return amount
