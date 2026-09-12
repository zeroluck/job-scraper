import pdfplumber
import config
import json
import logging
import models
import os
import re
import sys
import tempfile
import time
from llm_client import primary_client
from lane_catalog import canonical_context, canonical_lane_slug
from pydantic import BaseModel, ValidationError


logger = logging.getLogger(__name__)

TRUNCATED_OUTPUT = "truncated_output"
INVALID_JSON = "invalid_json"
SCHEMA_VALIDATION_FAILED = "schema_validation_failed"


class ResumeParseError(ValueError):
    def __init__(self, category, stage, detail):
        super().__init__(detail)
        self.category = category
        self.stage = stage
        self.detail = detail


def _find_object_end(text, start):
    stack = []
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character in "{[":
            stack.append(character)
        elif character in "}]":
            expected = "{" if character == "}" else "["
            if not stack or stack[-1] != expected:
                return index + 1
            stack.pop()
            if not stack:
                return index + 1

    return None


def extract_first_json_object(response_text):
    """Extract the first complete, valid top-level JSON object from LLM text."""
    if not isinstance(response_text, str) or not response_text.strip():
        raise ResumeParseError(INVALID_JSON, "extraction", "empty response")

    search_from = 0
    found_object_start = False
    last_decode_error = None

    while True:
        start = response_text.find("{", search_from)
        if start == -1:
            break

        following_text = response_text[start + 1:].lstrip()
        if following_text and not following_text.startswith(('"', '}')):
            search_from = start + 1
            continue

        found_object_start = True
        end = _find_object_end(response_text, start)
        if end is None:
            raise ResumeParseError(
                TRUNCATED_OUTPUT,
                "extraction",
                "JSON object was not closed before the response ended",
            )

        candidate = response_text[start:end]
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError as error:
            last_decode_error = error
            search_from = end
            continue

        if isinstance(decoded, dict):
            return candidate
        search_from = end

    if found_object_start and last_decode_error is not None:
        detail = f"JSON decoding failed at position {last_decode_error.pos}"
    else:
        detail = "response did not contain a JSON object"
    raise ResumeParseError(INVALID_JSON, "json_decode", detail)


def _sanitize_payload_snippet(payload, limit=160):
    if not isinstance(payload, str):
        return "<empty>"

    snippet = " ".join(payload.split())
    snippet = re.sub(r"[\w@.+/-]+", "<text>", snippet)
    return snippet[:limit]


def _log_parse_failure(error, payload, attempt, max_retries):
    response_length = len(payload) if isinstance(payload, str) else 0
    model_name = getattr(primary_client, "model", "unknown")
    snippet = _sanitize_payload_snippet(payload)
    logger.warning(
        "Resume parse failed: category=%s stage=%s attempt=%s/%s "
        "response_length=%s model=%s payload_snippet=%s",
        error.category,
        error.stage,
        attempt,
        max_retries,
        response_length,
        model_name,
        snippet,
        extra={
            "event": "resume_parse_failure",
            "parse_category": error.category,
            "parse_stage": error.stage,
            "attempt": attempt,
            "max_attempts": max_retries,
            "response_length": response_length,
            "llm_model": model_name,
            "payload_snippet": snippet,
        },
    )

def extract_text_from_pdf(pdf_path):
    """
    Extracts text from a given PDF file.

    Args:
        pdf_path (str): The file path to the PDF resume.

    Returns:
        str: The extracted text content from the PDF.
    """
    print(f"Extracting text from: {pdf_path}")
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Extract the visible text
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
            
            # Extract embedded hyperlinks which are not captured by extract_text()
            if page.hyperlinks:
                for link in page.hyperlinks:
                    uri = link.get("uri")
                    if uri:
                        text += f"Embedded Link: {uri}\n"
    return text

def parse_resume_with_ai(resume_text):
    """
    Send resume text to an AI model and get structured information back.
    
    Args:
        resume_text (str): The plain text extracted from the resume
        
    Returns:
        str: JSON string of structured resume information
    """
    print("Processing resume with AI model...")

    prompt = f"""Extract and return the structured resume information from the text below. 
    Only use what is explicitly stated in the text and do not infer or invent any details.
    
    Keep descriptions concise and do not repeat source text. Use at most four sentences per
    experience or project description and include each skill only once.

    CRITICAL: If any information is missing or not available in the text, use "NA" for that field.
    This applies to all fields (e.g., summary, dates, location, links, etc.). 
    Do NOT leave fields empty or use empty strings.

    Resume text:
    {resume_text}
    """

    response_text = primary_client.generate_content(
        prompt=prompt,
        response_format=models.Resume,
        reasoning_effort="low",
        max_tokens=12000,
    )
    return response_text

def replace_empty_with_na(data):
    """
    Recursively replaces empty strings or None values in a dictionary or list with "NA".
    """
    if isinstance(data, dict):
        return {k: replace_empty_with_na(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_empty_with_na(i) for i in data]
    elif data == "" or data is None:
        return "NA"
    return data


def _has_meaningful_value(value):
    if isinstance(value, BaseModel):
        return _has_meaningful_value(value.model_dump())
    if isinstance(value, dict):
        return any(_has_meaningful_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_meaningful_value(item) for item in value)
    return value not in (None, "", "NA")

def parse_and_validate_resume(resume_text, max_retries=config.MAX_RETRIES):
    """
    Attempts to parse resume text with AI, with retry logic for JSON errors or empty responses.
    
    Args:
        resume_text (str): The extracted text from the resume.
        max_retries (int): Maximum number of attempts.
        
    Returns:
        dict: The structured resume data with empty values replaced by "NA".
    """
    for attempt in range(max_retries):
        parsed_resume_details_str = parse_resume_with_ai(resume_text)

        try:
            json_object = extract_first_json_object(parsed_resume_details_str)
            resume_data_dict = replace_empty_with_na(json.loads(json_object))
            validated = models.Resume.model_validate(resume_data_dict)
            meaningful_fields = (
                validated.name,
                validated.email,
                validated.phone,
                validated.summary,
                validated.skills,
                validated.education,
                validated.experience,
                validated.projects,
                validated.certifications,
            )
            if not any(_has_meaningful_value(value) for value in meaningful_fields):
                raise ResumeParseError(
                    SCHEMA_VALIDATION_FAILED,
                    "usability_validation",
                    "Resume payload contains no usable identity, contact, or history data",
                )
            return replace_empty_with_na(validated.model_dump())
        except ValidationError as error:
            parse_error = ResumeParseError(
                SCHEMA_VALIDATION_FAILED,
                "schema_validation",
                f"Resume validation failed with {error.error_count()} error(s)",
            )
        except ResumeParseError as error:
            parse_error = error

        _log_parse_failure(
            parse_error,
            parsed_resume_details_str,
            attempt + 1,
            max_retries,
        )
        print(
            f"Attempt {attempt + 1}: Resume parse failed "
            f"({parse_error.category}). Retrying..."
        )
        if attempt < max_retries - 1:
            time.sleep(config.RETRY_DELAY_SECONDS)

    print(f"ERROR: Failed to parse resume after {max_retries} attempts.")
    sys.exit(1)

def parse_storage_resume(storage_key, *, local_fallback=None, storage=None):
    """Download, parse, and always remove the temporary source PDF."""
    if storage is None:
        import supabase_utils

        storage = supabase_utils

    pdf_bytes = storage.download_resume_from_storage(storage_key)
    temporary_path = None
    pdf_path = None
    try:
        if pdf_bytes:
            descriptor, temporary_path = tempfile.mkstemp(suffix=".pdf")
            with os.fdopen(descriptor, "wb") as pdf_file:
                pdf_file.write(pdf_bytes)
            pdf_path = temporary_path
            print(f"Successfully downloaded {storage_key} from Supabase Storage.")
        elif local_fallback and os.path.exists(local_fallback):
            pdf_path = local_fallback
            print(f"Supabase Storage download failed. Using local file: {local_fallback}")
        else:
            raise RuntimeError(f"Could not find {storage_key} in resume storage")

        resume_text = extract_text_from_pdf(pdf_path)
        if not resume_text:
            raise RuntimeError(f"Resume PDF {storage_key} contains no extractable text")
        return parse_and_validate_resume(resume_text)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


def _parse_target(raw_target):
    target = str(raw_target or "").strip().lower()
    if target in {"", "global"}:
        return "global"
    if target == "all":
        return "all"
    canonical_context(target)
    return canonical_lane_slug(target)


def main(target=None, db=None):
    """
    Main function to orchestrate the resume parsing process.
    Downloads the resume PDF from Supabase Storage, parses it with AI, 
    and saves the structured data to both local file and Supabase DB.
    """
    import supabase_utils

    parsed_target = _parse_target(
        target if target is not None else os.getenv("RESUME_PARSE_ARCHETYPE", "")
    )
    if parsed_target == "global":
        resume_data = parse_storage_resume(
            "resume.pdf", local_fallback="./resume.pdf", storage=supabase_utils
        )
        if not supabase_utils.save_base_resume(resume_data):
            raise RuntimeError("Failed to save parsed resume to Supabase database")
        try:
            with open(config.BASE_RESUME_PATH, "w", encoding="utf-8") as output:
                json.dump(resume_data, output, indent=4)
        except OSError as exc:
            logger.warning("Could not write local resume cache: %s", exc)
        print("Successfully saved parsed global resume.")
        return {"global": resume_data}

    if parsed_target == "all":
        from downstream_orchestration import enabled_lane_slugs

        if not supabase_utils.get_base_resume():
            raise RuntimeError("Parse the global resume before parsing lane profiles")
        lanes = enabled_lane_slugs(db or supabase_utils.supabase)
    else:
        lanes = (parsed_target,)

    profiles = {}
    for lane in lanes:
        profiles[lane] = parse_storage_resume(
            f"archetypes/{lane}.pdf", storage=supabase_utils
        )
    if not profiles:
        raise RuntimeError("No enabled career lanes were available to parse")
    if not supabase_utils.save_archetype_resume_profiles(profiles):
        raise RuntimeError("Failed to save parsed archetype resume profiles")
    print(f"Successfully saved parsed resume profiles for: {', '.join(profiles)}")
    return profiles

    print("\nResume processing finished.")


if __name__ == "__main__":
    print("Starting resume processing...")
    main()
