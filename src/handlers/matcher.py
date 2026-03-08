"""Matcher Lambda - Finds best job matches for a worker.

Scores available job postings against worker preferences
using weighted criteria (job type, location, salary, availability, skills).
"""

from common.exceptions import MatchingError
from common.logger import get_logger, log_context

logger = get_logger(__name__)


def handler(event, context):
    """Find job matches for worker data.

    Input: {"worker_data": dict, "limit": int}
    Output: {"matches": [{"posting": dict, "score": float, "breakdown": dict}]}
    """
    worker_data = event.get("worker_data", {})
    limit = event.get("limit", 3)

    logger.info("Finding job matches", extra=log_context(job_type=worker_data.get("job_type")))

    try:
        from services.matching_service import MatchingService

        matching_service = MatchingService()
        matches = matching_service.find_matches(worker_data=worker_data, limit=limit)

        # Serialize postings for Lambda response
        serialized = []
        for match in matches:
            serialized.append({
                "posting": match["posting"].to_dynamodb_item(),
                "score": match["score"],
                "breakdown": match["breakdown"],
            })

        logger.info("Found matches", extra=log_context(match_count=len(serialized)))
        return {"statusCode": 200, "matches": serialized}
    except MatchingError as e:
        logger.exception("Matching failed")
        return {"statusCode": 500, "error": str(e), "matches": []}
