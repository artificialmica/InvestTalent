"""
Noun Chunk Extraction Script
Extracts all noun chunks from CVs for classifier training

Usage:
    python extract_chunks.py --input_dir /path/to/cvs --output chunks_dataset.csv
"""

import spacy
import pandas as pd
import sys
import os
from pathlib import Path
import argparse
import re

# ----------------------------
# Load spaCy model
# ----------------------------
try:
    nlp = spacy.load("en_core_web_sm")
except:
    print("Downloading spaCy model...")
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


# ============================================================
#  Text Extraction
# ============================================================
def extract_text_from_file(filepath):
    """Extract text from .txt, .pdf, or .docx (future expansion)."""
    try:
        if filepath.endswith(".txt"):
            return Path(filepath).read_text(encoding="utf-8", errors="ignore")

        elif filepath.endswith(".pdf"):
            print(f"[!] PDF parsing requires pdfplumber/PyPDF2 - skipping {filepath}")
            return ""

        elif filepath.endswith(".docx"):
            print(f"[!] DOCX parsing requires python-docx - skipping {filepath}")
            return ""

        else:
            return Path(filepath).read_text(encoding="utf-8", errors="ignore")

    except Exception as e:
        print(f"[!] Error reading {filepath}: {e}")
        return ""


# ============================================================
# Section Detection (Europass-friendly)
# ============================================================
EUROPASS_SECTIONS = {
    "work experience": "experience",
    "professional experience": "experience",
    "employment history": "experience",

    "education": "education",
    "education and training": "education",

    "skills": "skills",
    "digital skills": "skills",
    "personal skills": "skills",
    "communication skills": "skills",
    "interpersonal skills": "skills",

    "certifications": "certifications",
    "certificates": "certifications",
}


def detect_section(text_before):
    """Detect which section the noun chunk belongs to."""
    ctx = text_before[-300:].lower()

    # Europass section keywords
    for key, value in EUROPASS_SECTIONS.items():
        if key in ctx:
            return value

    # Generic fallback
    if any(x in ctx for x in ["skills:", "technical skills"]):
        return "skills"
    if any(x in ctx for x in ["experience", "employment"]):
        return "experience"
    if any(x in ctx for x in ["education", "academic"]):
        return "education"

    return "unknown"


# ============================================================
# Chunk Cleaning Heuristics
# ============================================================
STOPWORDS = set([
    "and", "or", "the", "a", "an", "in", "for", "on", "of", "to", "at",
    "by", "with", "about", "into", "research", "journal", "conference",
    "study", "paper", "chapter", "section"
])

FORBIDDEN_KEYWORDS = [
    "journal", "study", "conference", "paper", "chapter", "quality",
    "water", "groundwater", "investigator", "coordinator"
]


def is_valid_chunk(text):
    """Filters obviously invalid noun chunks BEFORE training."""
    words = text.lower().split()

    # Too short or too long
    if len(words) < 1 or len(words) > 5:
        return False

    # Contains stopwords → very unlikely to be a skill
    if any(w in STOPWORDS for w in words):
        return False

    # Contains forbidden patterns
    if any(k in text.lower() for k in FORBIDDEN_KEYWORDS):
        return False

    # No alphabetic characters → reject
    if not re.search(r"[a-zA-Z]", text):
        return False

    return True


# ============================================================
# Chunk Extraction
# ============================================================
def extract_chunks_from_cv(filepath, cv_id):
    """Extract all noun chunks from a single CV."""
    text = extract_text_from_file(filepath)
    if not text:
        return []

    print(f"Processing: {Path(filepath).name} ({len(text)} chars)")

    doc = nlp(text[:50000])

    chunks_output = []
    seen = set()

    for chunk in doc.noun_chunks:
        chunk_text = chunk.text.strip()

        # Deduplicate
        if chunk_text.lower() in seen:
            continue
        seen.add(chunk_text.lower())

        # Validate structure
        if not is_valid_chunk(chunk_text):
            continue

        # Position and section
        pos = chunk.start_char
        section = detect_section(text[:pos])

        # POS pattern normalization
        pos_tags = [tok.pos_ for tok in chunk]
        pos_pattern = "-".join(pos_tags)

        chunks_output.append({
            "chunk_id": f"{cv_id}_{len(chunks_output)}",
            "text": chunk_text,
            "cv_id": cv_id,
            "source_file": Path(filepath).name,
            "section": section,
            "word_count": len(chunk_text.split()),
            "char_count": len(chunk_text),
            "pos_pattern": pos_pattern,
            "has_digit": any(c.isdigit() for c in chunk_text),
            "has_special": any(c in chunk_text for c in ['’', '“', '”']),
            "label": None
        })

    print(f" → {len(chunks_output)} valid chunks\n")
    return chunks_output


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", default=".", help="Folder containing CVs")
    parser.add_argument("--output", default="chunks_dataset.csv")
    parser.add_argument("--max_cvs", type=int, default=15)

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    cv_files = []

    for ext in ("*.txt", "*.pdf", "*.docx"):
        cv_files.extend(list(input_dir.glob(ext)))

    cv_files = cv_files[:args.max_cvs]

    all_chunks = []

    for idx, cv in enumerate(cv_files, start=1):
        chunks = extract_chunks_from_cv(str(cv), f"cv{idx:03d}")
        all_chunks.extend(chunks)

    df = pd.DataFrame(all_chunks)
    df.to_csv(args.output, index=False)

    print(f"\nSaved {len(df)} chunks → {args.output}")
    print("Label ~300 chunks before training.")


if __name__ == "__main__":
    main()
