import logging
import json
import time
import config
import supabase_utils
from collections import defaultdict
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import List
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

client = genai.Client(api_key=config.GEMINI_FIRST_API_KEY)

BATCH_SIZE = 10       # Job descriptions per Gemini call
SLEEP_BETWEEN = 6     # Seconds between API calls to avoid rate limiting
MAX_JOBS = 200        # Cap per run to avoid excessive API usage


# --- Pydantic schema for Gemini structured output ---
class KeywordItem(BaseModel):
    keyword: str
    category: str  # 'skill' | 'technology' | 'certification' | 'attribute'

class KeywordList(BaseModel):
    keywords: List[KeywordItem]


SYSTEM_PROMPT = """
You are an expert technical recruiter and resume analyst.
Your job is to extract the most important keywords from job descriptions.

You MUST categorize every keyword into exactly one of these four categories:
- "skill": Soft skills and professional competencies (e.g. "Project Management", "Agile", "Communication", "Leadership")
- "technology": Specific tools, platforms, languages, frameworks, or software (e.g. "Python", "Azure", "Docker", "SAP", "Salesforce")
- "certification": Named certifications, licenses, or credentials (e.g. "PMP", "AWS Solutions Architect", "CISSP", "Scrum Master")
- "attribute": Candidate traits, experience levels, or general qualifications (e.g. "5+ years experience", "Bachelor's degree", "bilingual", "remote work")

Rules:
- Only extract keywords that are explicitly requested or emphasized in the job description
- Normalize keywords to their canonical form (e.g. "MS Azure" -> "Azure", "proj mgmt" -> "Project Management")
- Do not include generic filler words like "team player" unless they are specifically emphasized
- Output ONLY the JSON object, no other text
"""


def fetch_unanalyzed_jobs() -> list:
    """Fetch only jobs that have not yet been analyzed."""
    response = supabase_utils.supabase.table(config.SUPABASE_TABLE_NAME) \
        .select("job_id, job_title, description") \
        .eq("is_active", True) \
        .eq("job_state", "new") \
        .is_("insights_analyzed_at", None) \
        .not_.is_("description", None) \
        .limit(MAX_JOBS) \
        .execute()

    if response.data:
        logging.info(f"Fetched {len(response.data)} unanalyzed jobs.")
        return response.data
    logging.info("No new unanalyzed jobs found.")
    return []


def extract_keywords_from_batch(batch: list) -> List[KeywordItem]:
    """Send a batch of job descriptions to Gemini and extract keywords."""
    combined = ""
    for i, job in enumerate(batch):
        combined += f"\n\n--- JOB {i+1}: {job.get('job_title', 'Unknown')} ---\n{job.get('description', '')}"

    prompt = f"""
Extract all requested skills, technologies, certifications, and candidate attributes from the following {len(batch)} job description(s).

{combined}
"""

    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                system_instruction=SYSTEM_PROMPT,
                response_mime_type='application/json',
                response_schema=KeywordList,
            )
        )
        parsed = KeywordList.model_validate_json(response.text.strip())
        logging.info(f"Extracted {len(parsed.keywords)} keywords from batch of {len(batch)}")
        return parsed.keywords
    except Exception as e:
        logging.error(f"Error extracting keywords from batch: {e}")
        return []


def aggregate_keywords(all_keywords: List[KeywordItem]) -> dict:
    """Aggregate keyword counts by (keyword, category)."""
    counts = defaultdict(int)
    for item in all_keywords:
        key = (item.keyword.strip().title(), item.category.strip().lower())
        counts[key] += 1
    return counts


def upsert_insights(counts: dict):
    """
    Increment existing keyword counts rather than wiping and recomputing.
    """
    if not counts:
        logging.warning("No keywords to upsert.")
        return

    db = supabase_utils.supabase

    # Fetch existing counts for the keywords we're about to upsert
    keywords_list = [kw for (kw, _) in counts.keys()]
    existing_response = db.table("keyword_insights") \
        .select("keyword, category, count") \
        .in_("keyword", keywords_list) \
        .execute()

    existing = {}
    for row in (existing_response.data or []):
        existing[(row["keyword"], row["category"])] = row["count"]

    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for (keyword, category), new_count in counts.items():
        prior = existing.get((keyword, category), 0)
        rows.append({
            "keyword": keyword,
            "category": category,
            "count": prior + new_count,
            "last_updated": now,
        })

    # Upsert in batches of 100
    for i in range(0, len(rows), 100):
        chunk = rows[i:i+100]
        db.table("keyword_insights") \
            .upsert(chunk, on_conflict="keyword,category") \
            .execute()

    logging.info(f"Upserted {len(rows)} keyword insight rows.")


def mark_jobs_analyzed(job_ids: list):
    """Stamp insights_analyzed_at on all processed jobs."""
    if not job_ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    supabase_utils.supabase.table(config.SUPABASE_TABLE_NAME) \
        .update({"insights_analyzed_at": now}) \
        .in_("job_id", job_ids) \
        .execute()
    logging.info(f"Marked {len(job_ids)} jobs as analyzed.")


def run():
    logging.info("Starting job insights analysis...")

    jobs = fetch_unanalyzed_jobs()
    if not jobs:
        logging.info("No new jobs to analyze. Exiting.")
        return

    all_keywords = []
    processed_job_ids = []

    for i in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[i:i + BATCH_SIZE]
        logging.info(f"Processing batch {i // BATCH_SIZE + 1} ({len(batch)} jobs)...")
        keywords = extract_keywords_from_batch(batch)
        all_keywords.extend(keywords)
        processed_job_ids.extend(job["job_id"] for job in batch)
        if i + BATCH_SIZE < len(jobs):
            logging.info(f"Sleeping {SLEEP_BETWEEN}s before next batch...")
            time.sleep(SLEEP_BETWEEN)

    logging.info(f"Total keywords extracted: {len(all_keywords)}")

    counts = aggregate_keywords(all_keywords)
    logging.info(f"Unique keyword/category pairs: {len(counts)}")

    upsert_insights(counts)
    mark_jobs_analyzed(processed_job_ids)

    logging.info("Insights analysis complete.")


if __name__ == "__main__":
    run()
