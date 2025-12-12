"""
Skill Classifier Testing Script
Evaluate the trained classifier on CV files (txt only!)
Shows cleaned skill predictions and before/after comparison.

Usage:
    python test_classifier.py --cv_file cv.txt
    python test_classifier.py --cv_file cv.txt --comparison
"""

import sys
from pathlib import Path
import argparse

# Import classifier
try:
    from skill_classifier import SkillClassifier
except ImportError:
    print("[!] Error: skill_classifier.py not found in this directory.")
    sys.exit(1)

import spacy

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    import os
    print("Downloading spaCy model...")
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


# ----------------------------------------------------------
#  NOUN CHUNK EXTRACTION
# ----------------------------------------------------------

def extract_noun_chunks_from_cv(filepath):
    """Extract noun chunks from a CV (TXT ONLY)."""

    if filepath.endswith(".pdf") or filepath.endswith(".docx"):
        print("[!] WARNING: This script cannot parse PDF or DOCX.")
        print("    Convert your CV to .txt first for testing.")
        print()

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        print(f"[!] Error reading file: {e}")
        sys.exit(1)

    # Limit to 50k characters to protect memory
    doc = nlp(text[:50000])

    chunks = []
    seen = set()

    for chunk in doc.noun_chunks:
        chunk_text = chunk.text.strip()

        # Filter short/long fragments
        if not 2 <= len(chunk_text) <= 80:
            continue

        # Deduplicate
        key = chunk_text.lower()
        if key in seen:
            continue
        seen.add(key)

        chunks.append(chunk_text)

    return chunks


# ----------------------------------------------------------
#  CLASSIFIER TESTING
# ----------------------------------------------------------

def test_classifier_on_cv(cv_file, classifier, threshold=0.6):
    """Run classifier on a CV file and show categorized results."""
    
    print("=" * 70)
    print("TESTING CLASSIFIER ON CV")
    print("=" * 70)
    print(f"CV File: {cv_file}")
    print(f"Confidence Threshold: {threshold:.0%}")
    print()

    print("Extracting noun chunks...")
    chunks = extract_noun_chunks_from_cv(cv_file)
    print(f"✓ Extracted {len(chunks)} unique noun chunks\n")

    print("Classifying chunks...")
    results = classifier.batch_predict(chunks)
    print("✓ Classification complete\n")

    skills = [r for r in results if r["confidence"] >= threshold and r["is_skill"]]
    non_skills = [r for r in results if not r["is_skill"] or r["confidence"] < threshold]

    skills.sort(key=lambda x: x["confidence"], reverse=True)
    non_skills.sort(key=lambda x: x["confidence"])

    print("=" * 70)
    print(f"CLASSIFIED AS SKILLS ({len(skills)})")
    print("=" * 70)
    print()
    for r in skills:
        print(f"  ✓ ({r['confidence']:.0%}) {r['text']}")
    if not skills:
        print("  (none)")
    print()

    print("=" * 70)
    print(f"CLASSIFIED AS NON-SKILLS ({len(non_skills)})")
    print("=" * 70)
    print()

    # Confidence ranges
    very_low = [r for r in non_skills if r["confidence"] < 0.2]
    low = [r for r in non_skills if 0.2 <= r["confidence"] < 0.4]
    mid = [r for r in non_skills if 0.4 <= r["confidence"] < threshold]

    if very_low:
        print("Very confident NON-skills (<20% skill probability):")
        for r in very_low[:10]:
            print(f"  ✗ ({r['confidence']:.0%}) {r['text']}")
        if len(very_low) > 10:
            print(f"  ... and {len(very_low) - 10} more")
        print()

    if low:
        print("Likely non-skills (20–40% skill probability):")
        for r in low[:5]:
            print(f"  ✗ ({r['confidence']:.0%}) {r['text']}")
        if len(low) > 5:
            print(f"  ... and {len(low) - 5} more")
        print()

    if mid:
        print(f"Uncertain (40–{threshold:.0%} skill probability):")
        for r in mid[:5]:
            print(f"  ? ({r['confidence']:.0%}) {r['text']}")
        if len(mid) > 5:
            print(f"  ... and {len(mid) - 5} more")
        print()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print(f"Total noun chunks: {len(chunks)}")
    print(f"Skills predicted: {len(skills)} ({len(skills)/len(chunks)*100:.1f}%)")
    print(f"Non-skills: {len(non_skills)} ({len(non_skills)/len(chunks)*100:.1f}%)")
    print()

    if skills:
        avg_conf = sum(r["confidence"] for r in skills) / len(skills)
        print(f"Average skill confidence: {avg_conf:.1%}")
    print()

    return skills, non_skills


# ----------------------------------------------------------
#  BEFORE/AFTER COMPARISON
# ----------------------------------------------------------

def compare_with_without_classifier(cv_file):
    """Show how classifier removes garbage from raw noun chunks."""

    chunks = extract_noun_chunks_from_cv(cv_file)

    print("=" * 70)
    print("BEFORE vs AFTER CLASSIFIER")
    print("=" * 70)
    print("\nWITHOUT classifier (raw chunks):")
    print(f"  Total: {len(chunks)} chunks\n")

    for i, c in enumerate(chunks[:20], 1):
        print(f"  {i:2d}. {c}")
    if len(chunks) > 20:
        print(f"  ... and {len(chunks) - 20} more\n")

    # Load classifier
    classifier = SkillClassifier.load("models")

    skills_only = classifier.filter_skills(chunks, threshold=0.6)

    print("WITH classifier (filtered skills):")
    print(f"  Total: {len(skills_only)}\n")

    for i, s in enumerate(skills_only, 1):
        print(f"  {i:2d}. {s}")

    removed = [c for c in chunks if c not in skills_only]

    print()
    print(f"REMOVED as noise: {len(removed)} chunks\n")
    for i, c in enumerate(removed[:15], 1):
        print(f"  {i:2d}. {c}")
    if len(removed) > 15:
        print(f"  ... and {len(removed) - 15} more\n")

    print("=" * 70)
    print("NOISE REDUCTION SUMMARY")
    print("=" * 70)
    print()
    print(f"Noise filtered: {len(removed)/len(chunks)*100:.1f}%")
    print(f"Skills retained: {len(skills_only)}")


# ----------------------------------------------------------
#  MAIN EXECUTION
# ----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv_file", type=str, help="Path to TXT CV file")
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--comparison", action="store_true")
    args = parser.parse_args()

    # Model check
    if not Path("models/skill_classifier.pkl").exists():
        print("[!] Model not found. Train with train_classifier.py first.")
        sys.exit(1)

    print("Loading classifier...")
    classifier = SkillClassifier.load("models")
    print("✓ Classifier loaded\n")

    if args.comparison and args.cv_file:
        compare_with_without_classifier(args.cv_file)
    
    elif args.cv_file:
        test_classifier_on_cv(args.cv_file, classifier, args.threshold)

    else:
        # Interactive mode
        print("=" * 70)
        print("INTERACTIVE CLASSIFIER TEST")
        print("=" * 70)
        print("Enter chunks manually. Type 'quit' to exit.\n")

        while True:
            text = input("Chunk: ").strip()
            if text.lower() in ("quit", "exit", "q"):
                break
            if not text:
                continue

            pred = classifier.predict(text)
            prob = classifier.predict_proba(text)

            if pred == 1:
                print(f"  ✓ SKILL ({prob:.0%} confidence)\n")
            else:
                print(f"  ✗ NOT SKILL ({(1 - prob):.0%} confidence)\n")


if __name__ == "__main__":
    main()
