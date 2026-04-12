import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import yaml

from models import Resume

logging.basicConfig(level=logging.INFO)

ACCENT_COLOR = "#1976D2"


def _parse_date(raw: Optional[str]) -> Optional[str]:
    """Convert loose date strings to RenderCV's YYYY-MM format."""
    if not raw or raw.strip().lower() == "present":
        return "present"

    raw = raw.strip()

    month_map = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
        "january": "01", "february": "02", "march": "03",
        "april": "04", "june": "06", "july": "07",
        "august": "08", "september": "09", "october": "10",
        "november": "11", "december": "12",
    }

    match = re.match(
        r"(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})", raw
    )
    if match:
        month = month_map.get(match.group("month").lower())
        if month:
            return f"{match.group('year')}-{month}"

    match = re.match(r"(?P<year>\d{4})\s*-\s*(?P<month>\d{1,2})", raw)
    if match:
        return f"{match.group('year')}-{int(match.group('month')):02d}"

    match = re.match(r"(?P<year>\d{4})$", raw)
    if match:
        return f"{match.group('year')}-01"

    match = re.match(r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})", raw)
    if match:
        return f"{match.group('year')}-{match.group('month')}"

    return raw


def _extract_username(url: str) -> Optional[str]:
    """Extract username from a social network URL."""
    if not url:
        return None
    url = url.rstrip("/")
    for pattern in [
        r"linkedin\.com/in/([^/?#]+)",
        r"github\.com/([^/?#]+)",
    ]:
        m = re.search(pattern, url, re.IGNORECASE)
        if m:
            return m.group(1)
    parts = url.split("/")
    return parts[-1] if parts[-1] else None


def _build_rendercv_yaml(resume: Resume) -> dict:
    """Convert a Resume Pydantic model into a RenderCV YAML structure."""
    cv: dict = {
        "name": resume.name or "",
    }

    if resume.email:
        cv["email"] = resume.email
    if resume.phone:
        cv["phone"] = resume.phone
    if resume.location:
        cv["location"] = resume.location

    social_networks = []
    if resume.links:
        if resume.links.linkedin:
            username = _extract_username(resume.links.linkedin)
            if username:
                social_networks.append({"network": "LinkedIn", "username": username})
        if resume.links.github:
            username = _extract_username(resume.links.github)
            if username:
                social_networks.append({"network": "GitHub", "username": username})
    if social_networks:
        cv["social_networks"] = social_networks

    sections: dict = {}

    if resume.summary:
        cleaned = resume.summary
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        sections["summary"] = [cleaned]

    if resume.skills:
        sections["skills"] = [
            {
                "label": "Skills",
                "details": ", ".join(resume.skills),
            }
        ]

    if resume.experience:
        entries = []
        for exp in resume.experience:
            entry: dict = {
                "company": exp.company,
                "position": exp.job_title,
            }
            if exp.start_date:
                entry["start_date"] = _parse_date(exp.start_date)
            if exp.end_date:
                entry["end_date"] = _parse_date(exp.end_date)
            if exp.location:
                entry["location"] = exp.location
            if exp.description:
                bullets = [
                    b.strip().lstrip("•- ").strip()
                    for b in exp.description.split("\n")
                    if b.strip()
                ]
                if bullets:
                    entry["highlights"] = bullets
            entries.append(entry)
        sections["experience"] = entries

    if resume.education:
        entries = []
        for edu in resume.education:
            entry: dict = {
                "institution": edu.institution,
                "area": edu.field_of_study or "",
            }
            if edu.degree:
                entry["degree"] = edu.degree
            if edu.start_year:
                entry["start_date"] = _parse_date(edu.start_year)
            if edu.end_year:
                entry["end_date"] = _parse_date(edu.end_year)
            entries.append(entry)
        sections["education"] = entries

    if resume.projects:
        entries = []
        for proj in resume.projects:
            entry: dict = {"name": proj.name}
            if proj.description:
                bullets = [
                    b.strip().lstrip("•- ").strip()
                    for b in proj.description.split("\n")
                    if b.strip()
                ]
                if bullets:
                    entry["highlights"] = bullets
            if proj.technologies:
                entry["summary"] = f"Technologies: {', '.join(proj.technologies)}"
            entries.append(entry)
        sections["projects"] = entries

    if resume.certifications:
        entries = []
        for cert in resume.certifications:
            entry: dict = {"name": cert.name}
            if cert.issuer:
                entry["summary"] = cert.issuer
            if cert.year:
                entry["date"] = _parse_date(cert.year)
            entries.append(entry)
        sections["certifications"] = entries

    if resume.languages:
        sections["languages"] = [
            {
                "label": "Languages",
                "details": ", ".join(resume.languages),
            }
        ]

    cv["sections"] = sections

    design = {
        "theme": "engineeringresumes",
        "page": {
            "size": "us-letter",
            "top_margin": "0.6in",
            "bottom_margin": "0.6in",
            "left_margin": "0.6in",
            "right_margin": "0.6in",
        },
        "colors": {
            "name": ACCENT_COLOR,
            "headline": ACCENT_COLOR,
            "section_titles": ACCENT_COLOR,
            "links": ACCENT_COLOR,
            "connections": ACCENT_COLOR,
        },
        "typography": {
            "font_family": "Source Sans 3",
            "alignment": "justified",
        },
    }

    return {"cv": cv, "design": design}


def create_resume_pdf(resume: Resume) -> bytes:
    """
    Generates a PDF resume using RenderCV (YAML -> Typst -> PDF).
    Returns the PDF content as bytes.
    """
    rendercv_yaml = _build_rendercv_yaml(resume)

    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_path = Path(tmpdir) / "resume_CV.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(rendercv_yaml, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        logging.info("RenderCV YAML written to %s", yaml_path)

        result = subprocess.run(
            ["rendercv", "render", str(yaml_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            logging.error("RenderCV stderr: %s", result.stderr)
            raise RuntimeError(f"RenderCV failed: {result.stderr}")

        pdf_path = yaml_path.with_suffix(".pdf")
        if not pdf_path.exists():
            raise RuntimeError(f"RenderCV did not produce expected PDF at {pdf_path}")

        return pdf_path.read_bytes()
