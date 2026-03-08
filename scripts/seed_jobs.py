#!/usr/bin/env python3
"""Seed DynamoDB with sample job postings for testing."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from common.models.job_posting import Availability, JobPosting, Location, SalaryRange
from common.repositories.job_posting_repository import JobPostingRepository

SAMPLE_POSTINGS = [
    # Bangalore
    {
        "job_type": "plumber",
        "location": {"area": "Koramangala", "city": "Bangalore"},
        "salary": {"min_amount": 600, "max_amount": 800, "period": "daily"},
        "skills": ["pipe fitting", "bathroom repair"],
        "urgency": "immediate",
    },
    {
        "job_type": "maid",
        "location": {"area": "Indiranagar", "city": "Bangalore"},
        "salary": {"min_amount": 8000, "max_amount": 10000, "period": "monthly"},
        "availability": {"days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"], "hours": "morning"},
        "skills": ["cleaning", "cooking"],
    },
    {
        "job_type": "electrician",
        "location": {"area": "HSR Layout", "city": "Bangalore"},
        "salary": {"min_amount": 700, "max_amount": 900, "period": "daily"},
        "skills": ["wiring", "AC repair"],
        "urgency": "within_week",
    },
    {
        "job_type": "cook",
        "location": {"area": "Whitefield", "city": "Bangalore"},
        "salary": {"min_amount": 12000, "max_amount": 15000, "period": "monthly"},
        "skills": ["north indian", "south indian"],
    },
    {
        "job_type": "driver",
        "location": {"area": "MG Road", "city": "Bangalore"},
        "salary": {"min_amount": 15000, "max_amount": 18000, "period": "monthly"},
        "skills": ["car driving", "route knowledge"],
    },
    {
        "job_type": "security_guard",
        "location": {"area": "Electronic City", "city": "Bangalore"},
        "salary": {"min_amount": 12000, "max_amount": 14000, "period": "monthly"},
        "availability": {"days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"], "hours": "night"},
    },
    {
        "job_type": "carpenter",
        "location": {"area": "Jayanagar", "city": "Bangalore"},
        "salary": {"min_amount": 800, "max_amount": 1000, "period": "daily"},
        "skills": ["furniture", "woodwork"],
    },
    # Mumbai
    {
        "job_type": "plumber",
        "location": {"area": "Andheri", "city": "Mumbai"},
        "salary": {"min_amount": 700, "max_amount": 900, "period": "daily"},
        "skills": ["pipe fitting", "leakage repair"],
        "urgency": "immediate",
    },
    {
        "job_type": "maid",
        "location": {"area": "Bandra", "city": "Mumbai"},
        "salary": {"min_amount": 10000, "max_amount": 12000, "period": "monthly"},
        "skills": ["cleaning", "washing"],
    },
    {
        "job_type": "delivery",
        "location": {"area": "Powai", "city": "Mumbai"},
        "salary": {"min_amount": 500, "max_amount": 700, "period": "daily"},
        "skills": ["bike riding", "navigation"],
        "urgency": "immediate",
    },
    {
        "job_type": "painter",
        "location": {"area": "Thane", "city": "Mumbai"},
        "salary": {"min_amount": 600, "max_amount": 800, "period": "daily"},
        "skills": ["wall painting", "waterproofing"],
    },
    # Delhi NCR
    {
        "job_type": "electrician",
        "location": {"area": "Lajpat Nagar", "city": "Delhi"},
        "salary": {"min_amount": 600, "max_amount": 800, "period": "daily"},
        "skills": ["wiring", "switch repair"],
    },
    {
        "job_type": "cook",
        "location": {"area": "Sector 18", "city": "Noida"},
        "salary": {"min_amount": 10000, "max_amount": 13000, "period": "monthly"},
        "skills": ["north indian", "chinese"],
    },
    {
        "job_type": "driver",
        "location": {"area": "DLF Phase 3", "city": "Gurgaon"},
        "salary": {"min_amount": 18000, "max_amount": 22000, "period": "monthly"},
        "skills": ["car driving", "commercial license"],
    },
    {
        "job_type": "maid",
        "location": {"area": "Saket", "city": "Delhi"},
        "salary": {"min_amount": 8000, "max_amount": 10000, "period": "monthly"},
        "availability": {"days": ["monday", "tuesday", "wednesday", "thursday", "friday"], "hours": "morning"},
    },
    # Chennai
    {
        "job_type": "plumber",
        "location": {"area": "T Nagar", "city": "Chennai"},
        "salary": {"min_amount": 500, "max_amount": 700, "period": "daily"},
        "skills": ["pipe fitting"],
    },
    {
        "job_type": "mason",
        "location": {"area": "Adyar", "city": "Chennai"},
        "salary": {"min_amount": 700, "max_amount": 900, "period": "daily"},
        "skills": ["cement work", "tile laying"],
        "urgency": "within_week",
    },
    # Hyderabad
    {
        "job_type": "security_guard",
        "location": {"area": "HITEC City", "city": "Hyderabad"},
        "salary": {"min_amount": 11000, "max_amount": 13000, "period": "monthly"},
        "availability": {"days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"], "hours": "night"},
    },
    {
        "job_type": "helper",
        "location": {"area": "Gachibowli", "city": "Hyderabad"},
        "salary": {"min_amount": 400, "max_amount": 500, "period": "daily"},
        "skills": ["loading", "unloading"],
    },
    # Kolkata
    {
        "job_type": "tailor",
        "location": {"area": "Park Street", "city": "Kolkata"},
        "salary": {"min_amount": 500, "max_amount": 700, "period": "daily"},
        "skills": ["stitching", "alteration"],
    },
]


def seed():
    repo = JobPostingRepository()
    print(f"Seeding {len(SAMPLE_POSTINGS)} job postings...")

    failed = []
    for data in SAMPLE_POSTINGS:
        try:
            posting = JobPosting(
                job_id=JobPosting.generate_id(),
                employer_phone="+919999999999",  # Dummy employer
                job_type=data["job_type"],
                location=Location.from_dict(data["location"]),
                salary=SalaryRange.from_dict(data.get("salary", {})),
                availability=Availability.from_dict(data.get("availability", {})),
                required_skills=data.get("skills", []),
                urgency=data.get("urgency", "flexible"),
            )
            repo.create_posting(posting)
            print(f"  Created: {posting.job_type} in {posting.location.area}, {posting.location.city}")
        except Exception as e:
            print(f"  FAILED: {data['job_type']} in {data['location'].get('city', '?')} - {e}")
            failed.append(data)

    succeeded = len(SAMPLE_POSTINGS) - len(failed)
    print(f"\nDone! {succeeded}/{len(SAMPLE_POSTINGS)} succeeded.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    seed()
