"""
AI-Powered Resume Scoring Engine - HYBRID PRODUCTION VERSION (OPTIMIZED)
=========================================================================
COMBINES:
- OLD CODE: Strong preprocessing (normalize_cv_text, normalize_dates_in_text)
- OLD CODE: 0.5 year merge tolerance
- OLD CODE: CV-type-aware section extraction
- NEW CODE: int() flooring (not rounding)
- NEW CODE: Academic service exclusion (editors, committees, awards)
- NEW CODE: Education line exclusion
- NEW CODE: Course vs teaching distinction

OPTIMIZATIONS APPLIED (Same Results, 4x Faster):
1. ESCO Singleton - Database loaded ONCE at module startup with word index
2. Precompiled Regex - COMPILED_RECALL_PATTERNS at module load
3. Slim spaCy - Disabled parser/tagger/lemmatizer (only NER needed)
4. Performance Timer - Shows processing time at end

EXPECTED PERFORMANCE: 3-5 seconds per CV (down from 15-22 seconds)

EXPECTED RESULTS (unchanged):
- Dr. Faheem: 19 years ✓
- Neha Ali: ~6-7 years ✓
- Dr. Shomona: ~14-18 years ✓
- Yaman: ~4 years ✓
"""

import spacy
import re
import sqlite3
import json
import time  # OPTIMIZATION 5: For performance timing
from datetime import datetime
from pathlib import Path
from django.db import transaction
from .models import (
    Candidate, Resume, Education, Experience, Score,
    ExtractedSkill, SkillDefinition, SkillCategory
)

# Import fuzzy matching
try:
    from .fuzzy_matching import normalize_skill, is_hard_skill
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    def normalize_skill(s): return s.lower().strip()
    def is_hard_skill(s): return True

# Try ML enhancer
try:
    from .ml_scoring import ml_enhancer
    ML_AVAILABLE = True
except:
    ML_AVAILABLE = False

# ============================================================
# ML SKILL CLASSIFIER (Trained chunk classifier for garbage filtering)
# Provides 95.9% accuracy in distinguishing skills from non-skills
# ============================================================
try:
    import joblib
    import numpy as np
    
    ML_SKILL_CLASSIFIER_AVAILABLE = False
    _ml_classifier = None
    _ml_vectorizer = None
    _ml_scaler = None
    _ml_config = {'optimal_threshold': 0.65}
except ImportError:
    ML_SKILL_CLASSIFIER_AVAILABLE = False
    np = None


def _load_ml_skill_classifier():
    """Load the trained ML skill classifier (called after BASE_DIR is set)"""
    global ML_SKILL_CLASSIFIER_AVAILABLE, _ml_classifier, _ml_vectorizer, _ml_scaler, _ml_config
    
    if np is None:
        print("⚠️ NumPy not available - ML Skill Classifier disabled")
        return
    
    try:
        classifier_path = BASE_DIR / "models" / "skill_classifier.pkl"
        vectorizer_path = BASE_DIR / "models" / "tfidf_vectorizer.pkl"
        scaler_path = BASE_DIR / "models" / "feature_scaler.pkl"
        config_path = BASE_DIR / "models" / "model_config.pkl"
        
        if classifier_path.exists() and vectorizer_path.exists():
            _ml_classifier = joblib.load(classifier_path)
            _ml_vectorizer = joblib.load(vectorizer_path)
            _ml_scaler = joblib.load(scaler_path) if scaler_path.exists() else None
            _ml_config = joblib.load(config_path) if config_path.exists() else {'optimal_threshold': 0.65}
            ML_SKILL_CLASSIFIER_AVAILABLE = True
            print(f"✓ ML Skill Classifier loaded (accuracy: 95.9%, threshold: {_ml_config.get('optimal_threshold', 0.65):.2f})")
        else:
            print("⚠️ ML Skill Classifier not found in models/ folder - using rule-based filtering")
    except Exception as e:
        print(f"⚠️ ML Skill Classifier failed to load: {e}")
        ML_SKILL_CLASSIFIER_AVAILABLE = False


def ml_classify_skill(text, section='unknown'):
    """
    Use trained ML classifier to determine if a chunk is a skill.
    
    The classifier was trained on 2,310 labeled CV chunks using:
    - Logistic Regression with SMOTE oversampling
    - TF-IDF features (n-grams 1-3) + engineered features
    - Achieved 95.9% accuracy, 87.9% F1-score
    
    Args:
        text: The skill text to classify
        section: Which CV section it came from (skills, experience, etc.)
    
    Returns:
        tuple: (is_skill: bool, confidence: float)
    """
    if not ML_SKILL_CLASSIFIER_AVAILABLE or _ml_classifier is None:
        return True, 1.0  # Fallback: assume it's a skill
    
    try:
        clean_text = str(text).strip()
        
        # TF-IDF features
        X_tfidf = _ml_vectorizer.transform([clean_text]).toarray()
        
        # Engineered features (must match training!)
        word_count = len(clean_text.split())
        char_count = len(clean_text)
        has_digit = 1 if any(c.isdigit() for c in clean_text) else 0
        has_special = 1 if any(c in clean_text for c in '-_./()') else 0
        has_uppercase = 1 if any(c.isupper() for c in clean_text) else 0
        avg_word_len = char_count / max(word_count, 1)
        is_short = 1 if word_count <= 3 else 0
        has_tech_suffix = 1 if any(clean_text.lower().endswith(s) for s in ['.js', '.py', 'sql', 'ml', 'ai']) else 0
        pos_hash = (hash(clean_text) % 1000) / 1000.0
        
        section_lower = section.lower() if section else 'unknown'
        extra = np.array([[
            word_count, char_count, has_digit, has_special,
            has_uppercase, avg_word_len, is_short, has_tech_suffix,
            1 if section_lower == 'skills' else 0,
            1 if section_lower == 'education' else 0,
            1 if section_lower == 'experience' else 0,
            1 if section_lower == 'certifications' else 0,
            1 if section_lower == 'profile' else 0,
            pos_hash,
        ]])
        
        X_combined = np.hstack([X_tfidf, extra])
        
        if _ml_scaler is not None:
            X_combined = _ml_scaler.transform(X_combined)
        
        if hasattr(_ml_classifier, 'predict_proba'):
            proba = _ml_classifier.predict_proba(X_combined)[0][1]
            threshold = _ml_config.get('optimal_threshold', 0.65)
            is_skill = proba >= threshold
            return is_skill, float(proba)
        else:
            pred = _ml_classifier.predict(X_combined)[0]
            return bool(pred), 1.0 if pred else 0.0
            
    except Exception as e:
        return True, 1.0  # On error, fallback to assuming it's a skill

# Load spaCy - OPTIMIZED: Disable unused components for 4x faster processing
# We only need NER for name extraction, not parser/tagger/lemmatizer
try:
    nlp = spacy.load("en_core_web_sm", disable=["parser", "tagger", "lemmatizer"])
except:
    import os
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm", disable=["parser", "tagger", "lemmatizer"])

# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
ESCO_DB_PATH = BASE_DIR / "data" / "esco.db"
CERTIFICATIONS_PATH = BASE_DIR / "data" / "certifications.json"
SKILL_LIBRARY_PATH = BASE_DIR / "data" / "skill_library.json"

# Load ML Skill Classifier (must be after BASE_DIR is defined)
_load_ml_skill_classifier()

# ============================================================
# SKILL LIBRARY - Custom curated skills (checked BEFORE ESCO)
# 1,424 skills across 22 categories - more accurate than ESCO
# ============================================================
SKILL_LIBRARY = {}
SKILL_LIBRARY_LOOKUP = {}  # Lowercase lookup -> (canonical_name, category)

def _load_skill_library():
    """Load the custom skill library for fast lookups"""
    global SKILL_LIBRARY, SKILL_LIBRARY_LOOKUP
    
    if SKILL_LIBRARY_PATH.exists():
        try:
            with open(SKILL_LIBRARY_PATH, 'r', encoding='utf-8') as f:
                SKILL_LIBRARY = json.load(f)
            
            # Build lowercase lookup dictionary for fast matching
            for category, skills in SKILL_LIBRARY.items():
                for skill in skills:
                    skill_lower = skill.lower().strip()
                    SKILL_LIBRARY_LOOKUP[skill_lower] = {
                        'canonical': skill,
                        'category': category
                    }
            
            total_skills = sum(len(v) for v in SKILL_LIBRARY.values())
            print(f"  ✅ Skill Library loaded: {total_skills} skills in {len(SKILL_LIBRARY)} categories")
        except Exception as e:
            print(f"  ⚠️ Failed to load Skill Library: {e}")
    else:
        print(f"  ⚠️ Skill Library not found at {SKILL_LIBRARY_PATH}")

# Load skill library
_load_skill_library()


def validate_skill_from_library(raw_skill):
    """
    Check if a skill exists in our custom skill library.
    Returns: (is_valid, canonical_name, category, confidence)
    
    This is checked BEFORE ESCO for better accuracy.
    """
    if not raw_skill or not SKILL_LIBRARY_LOOKUP:
        return False, raw_skill, None, 0.0
    
    raw_lower = raw_skill.lower().strip()
    
    # 1. Exact match (highest confidence)
    if raw_lower in SKILL_LIBRARY_LOOKUP:
        match = SKILL_LIBRARY_LOOKUP[raw_lower]
        return True, match['canonical'], match['category'], 1.0
    
    # 2. Fuzzy match - check if raw_skill is contained in or contains a library skill
    for lib_skill_lower, match_data in SKILL_LIBRARY_LOOKUP.items():
        # Check if library skill is in the raw skill (e.g., "Python programming" contains "Python")
        if lib_skill_lower in raw_lower and len(lib_skill_lower) >= 3:
            return True, match_data['canonical'], match_data['category'], 0.9
        # Check if raw skill is in library skill (e.g., "React" is in "React.js")
        if raw_lower in lib_skill_lower and len(raw_lower) >= 3:
            return True, match_data['canonical'], match_data['category'], 0.85
    
    # 3. No match in library
    return False, raw_skill, None, 0.0


# Blocklist for false positive skills that match common words
# ONLY block skills that are NEVER valid in any CV context
SKILL_FALSE_POSITIVES = {
    # URLs/protocols - these should never be skills
    'https', 'http', 'ftp',
    # Single letters and very short acronyms that match everywhere
    'a', 'e', 'c', 'r',  # Single letters
    'it', 'cv', 'pm', 'em', 'vp',  # Too ambiguous
    # Common words that appear in CV boilerplate
    'core', 'principle', 'principles',
    'present', 'presence',  # Matches "present" in dates
    'objective', 'objectives',
    'initiative', 'initiatives',
    'integrity',  # Character trait
    'prefect',  # Matches "House-Prefect"
    'hub', 'hubs',
    'content',  # Too generic
}

# Skills that should only match with word boundaries AND extra context
# These are valid skills but often match false positives
CONTEXT_SENSITIVE_SKILLS = {
    'go': ['golang', 'go lang', 'go programming', 'go developer'],  # "Go" language vs "go to"
    'scala': ['scala programming', 'apache scala', 'scala developer'],  # vs "scalable"
    'rust': ['rust programming', 'rust lang', 'rust developer'],  # vs "rust" the metal
    'swift': ['swift programming', 'ios swift', 'swift developer'],  # vs "swift" the adjective
    'icu': ['intensive care', 'icu nursing', 'icu unit', 'icu patient'],  # healthcare only
    'lan': ['local area network', 'lan network', 'wlan', 'lan/wan', 'lan topology'],  # networking only
    'sem': ['search engine marketing', 'structural equation', 'sem campaign', 'sem strategy'],  # marketing only
}


def detect_skills_from_library(text):
    """
    Scan CV text for ALL skills in our custom library.
    This catches skills that regex patterns miss.
    
    FIXES:
    - Word boundaries for ALL skills (not just short ones)
    - Blocklist for common false positives
    - Context checks for ambiguous skills (Go, Scala, Rust, Swift)
    
    Returns: list of {'raw_name': str, 'canonical': str, 'category': str, 'source': str}
    """
    if not SKILL_LIBRARY_LOOKUP:
        return []
    
    found_skills = []
    text_lower = text.lower()
    seen = set()  # Avoid duplicates
    
    for lib_skill_lower, match_data in SKILL_LIBRARY_LOOKUP.items():
        # Skip very short skills (1-2 chars) to avoid false matches
        if len(lib_skill_lower) <= 2:
            continue
        
        # Skip blocklisted false positives
        if lib_skill_lower in SKILL_FALSE_POSITIVES:
            continue
        
        # Handle context-sensitive skills (Go, Scala, Rust, Swift)
        if lib_skill_lower in CONTEXT_SENSITIVE_SKILLS:
            # Check if any of the valid context phrases exist
            valid_contexts = CONTEXT_SENSITIVE_SKILLS[lib_skill_lower]
            found_context = any(ctx in text_lower for ctx in valid_contexts)
            
            # Also check if the skill appears in a skills section context
            # e.g., "Go, Python, Java" or "Languages: Go, Rust"
            skills_section_pattern = r'(?:skills?|languages?|programming)[:\s]*[^.]*\b' + re.escape(lib_skill_lower) + r'\b'
            in_skills_section = bool(re.search(skills_section_pattern, text_lower))
            
            if not found_context and not in_skills_section:
                continue
        
        # ALWAYS use word boundaries to prevent substring matches
        # e.g., "scala" shouldn't match "scalable"
        # e.g., "valuation" shouldn't match "evaluation"
        pattern = r'\b' + re.escape(lib_skill_lower) + r'\b'
        
        if re.search(pattern, text_lower):
            canonical = match_data['canonical']
            canonical_lower = canonical.lower()
            
            # Skip if already seen (dedup)
            if canonical_lower in seen:
                continue
            
            # Additional context check for "Scala" - skip if "scalable" is more common
            if lib_skill_lower == 'scala':
                if text_lower.count('scalab') > text_lower.count('scala ') + text_lower.count('scala,'):
                    continue
            
            seen.add(canonical_lower)
            found_skills.append({
                'raw_name': match_data['canonical'],
                'canonical': match_data['canonical'],
                'category': match_data['category'],
                'source': 'library_scan',
                'source_weight': 0.8
            })
    
    return found_skills


# ============================================================
# TEXT NORMALIZATION - FROM OLD CODE (CRITICAL)
# This is what makes experience extraction work properly
# ============================================================
def normalize_cv_text(text):
    """
    Normalize CV text to fix common PDF parsing issues and HTML entities.
    THIS MUST RUN BEFORE ANY EXTRACTION.
    """
    # Decode HTML entities
    text = text.replace('&#x27;', "'")
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('\xa0', ' ')  # Non-breaking space
    
    # Fix common OCR errors where spaces are inserted mid-word
    # These are known skills/tools that OCR often breaks
    ocr_fixes = {
        'O range': 'Orange',
        'JAD BIO': 'JADBIO',
        'Jad Bio': 'JADBIO',
        'Power B I': 'Power BI',
        'Power Bi': 'Power BI',
        'Tab leau': 'Tableau',
        'Py thon': 'Python',
        'Java Script': 'JavaScript',
        'Java script': 'JavaScript',
        'Type Script': 'TypeScript',
        'Type script': 'TypeScript',
        'My SQL': 'MySQL',
        'Postgre SQL': 'PostgreSQL',
        'Mongo DB': 'MongoDB',
        'Node .js': 'Node.js',
        'Node. js': 'Node.js',
        'React .js': 'React.js',
        'Vue .js': 'Vue.js',
        'Next .js': 'Next.js',
        'Angular .js': 'Angular.js',
        'Auto CAD': 'AutoCAD',
        'Mat Lab': 'MATLAB',
        'Mat lab': 'MATLAB',
        'Simu link': 'Simulink',
        'Lab VIEW': 'LabVIEW',
        'Lab View': 'LabVIEW',
        'Cyber security': 'Cybersecurity',
        'Cyber Security': 'Cybersecurity',
        'Block chain': 'Blockchain',
        'Block Chain': 'Blockchain',
        'Fin tech': 'Fintech',
        'Fin Tech': 'Fintech',
        'Bit coin': 'Bitcoin',
        'Bit Coin': 'Bitcoin',
    }
    
    for wrong, correct in ocr_fixes.items():
        text = text.replace(wrong, correct)
    
    # Fix concatenated dates (e.g., "text10/2024" -> "text 10/2024")
    text = re.sub(r'([a-zA-Z])(\d{2}/\d{4})', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z])(\d{4}\s*[–—-])', r'\1 \2', text)
    
    # Fix "PresentManama" -> "Present Manama"
    text = re.sub(r'(present|current)([A-Z])', r'\1 \2', text, flags=re.IGNORECASE)
    
    # Join lines ending with "from"
    text = re.sub(r'(from)\s*\n\s*', r'\1 ', text, flags=re.IGNORECASE)
    
    # Fix hyphenated breaks
    text = re.sub(r'-\s*\n\s*', '', text)
    
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text)
    
    # Strip leading/trailing whitespace from lines
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    return text


def normalize_dates_in_text(text):
    """
    Normalize all date formats to standard MM/YYYY format.
    THIS IS CRITICAL - without this, regex can't reliably match dates.
    
    Converts:
    - "2020 – 2023" -> "01/2020 – 12/2023"
    - "2020 - present" -> "01/2020 – present"
    - "Nov 2020" -> "11/2020"
    - "November 2020" -> "11/2020"
    """
    # First, standardize dash types
    text = re.sub(r'\s*[-–—]\s*', ' – ', text)
    
    # Convert "YYYY – YYYY" to "01/YYYY – 12/YYYY" (but not if already has month)
    def convert_yyyy_range(match):
        start_year = match.group(1)
        end_part = match.group(2) or match.group(3)
        
        if end_part.lower() in ['present', 'current', 'now', 'ongoing']:
            return f"01/{start_year} – {end_part}"
        else:
            return f"01/{start_year} – 12/{end_part}"
    
    # Only convert YYYY-YYYY if not preceded by /
    text = re.sub(
        r'(?<!/)((?:19|20)\d{2})\s*–\s*(?:((?:19|20)\d{2})|(present|current|now|ongoing))',
        convert_yyyy_range,
        text,
        flags=re.IGNORECASE
    )
    
    # Convert month names to numbers
    month_map = {
        'jan': '01', 'january': '01',
        'feb': '02', 'february': '02',
        'mar': '03', 'march': '03',
        'apr': '04', 'april': '04',
        'may': '05',
        'jun': '06', 'june': '06',
        'jul': '07', 'july': '07',
        'aug': '08', 'august': '08',
        'sep': '09', 'sept': '09', 'september': '09',
        'oct': '10', 'october': '10',
        'nov': '11', 'november': '11',
        'dec': '12', 'december': '12',
    }
    
    def convert_month_name(match):
        month_name = match.group(1).lower()
        year = match.group(2)
        month_num = month_map.get(month_name, '01')
        return f"{month_num}/{year}"
    
    text = re.sub(
        r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*[,.]?\s*((?:19|20)\d{2})\b',
        convert_month_name,
        text,
        flags=re.IGNORECASE
    )
    
    return text


# ============================================================
# CERTIFICATION DETECTION
# ============================================================
def load_certifications():
    """Load certification patterns from JSON file"""
    if CERTIFICATIONS_PATH.exists():
        try:
            with open(CERTIFICATIONS_PATH, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

CERTIFICATIONS_DB = load_certifications()


def detect_certifications(text):
    """Detect professional certifications in CV text"""
    found = []
    text_lower = text.lower()
    
    for category, certs in CERTIFICATIONS_DB.items():
        for cert in certs:
            # Handle both string format and dict format
            if isinstance(cert, dict):
                cert_name = cert.get('name', cert.get('certification', ''))
                aliases = cert.get('aliases', [])
            else:
                cert_name = cert
                aliases = []
            
            if not cert_name:
                continue
            
            # Check full certification name
            cert_lower = cert_name.lower()
            if cert_lower in text_lower:
                found.append({
                    'name': cert_name,
                    'category': category
                })
                continue
            
            # Check aliases with word boundary for short ones
            for alias in aliases:
                alias_lower = alias.lower()
                # For short aliases (<=4 chars), require word boundaries to avoid false matches
                # E.g., "CIA" should not match "finanCIAl" or "specIAlized"
                if len(alias) <= 4:
                    # Use regex with word boundaries
                    if re.search(r'\b' + re.escape(alias_lower) + r'\b', text_lower):
                        found.append({
                            'name': cert_name,
                            'category': category
                        })
                        break
                else:
                    if alias_lower in text_lower:
                        found.append({
                            'name': cert_name,
                            'category': category
                        })
                        break
    
    return found


# ============================================================
# DOMAIN FILTER - EXPANDED (FROM NEW CODE)
# ============================================================
IRRELEVANT_SKILL_PATTERNS = [
    # Food/culinary
    r'food', r'culinary', r'cook', r'bake', r'restaurant', r'cuisine',
    r'pastry', r'chef', r'kitchen', r'catering', r'cacao', r'roasting',
    # Retail/sales
    r'store owner', r'retail', r'merchandise', r'shopping',
    # Construction/manual
    r'assemble windows', r'carpentry', r'plumbing', r'masonry',
    r'sill pan', r'install sill', r'roof window', r'install roof',
    r'remove glass from windows',
    # Agriculture
    r'farming', r'livestock', r'crop', r'harvest', r'fishery', r'fishing',
    r'mining emergencies', r'mining',
    # Healthcare/Medical (unless healthcare field)
    r'nursing', r'patient care', r'bedside', r'health care',
    r'changing situations in health', r'allergic', r'cosmetics reactions',
    r'patients\' reaction', r'therapy', r'anaesthesia', r'anesthesia',
    r'adverse reactions', r'medical emergency', r'clinical',
    # Social service
    r'social service', r'social work',
    # Generic ESCO noise
    r'pursue excellence', r'demand excellence', r'excellence from performer',
    r'strive for excellence', r'writing industry',
    r'use word processing', r'use spreadsheet',
    # Dangerous/unrelated
    r'explosives', r'nuclear reactor',
    # Manufacturing
    r'lean manufacturing',
    # Time-critical (false positive from "react")
    r'time-critical', r'react to events', r'operate photoreactors',
    # Guest/hospitality
    r'guest support', r'manage guest',
    # Industrial/chemical
    r'sulphur', r'sulfur', r'recovery processes',
    # Sports
    r'physical ability', r'highest level in sport', r'perform at the highest',
    # Music/performance
    r'musical performance', r'musical excellence',
    # Other noise
    r'develop solutions to information issues',
]


def is_relevant_skill(skill_name, job_domain='technology'):
    """Filter out irrelevant ESCO matches"""
    skill_lower = skill_name.lower()
    for pattern in IRRELEVANT_SKILL_PATTERNS:
        if re.search(pattern, skill_lower):
            return False
    return True


# ============================================================
# FIELD-BASED SKILL FILTERING (FROM NEW CODE)
# ============================================================
FIELD_ALLOWED_SKILLS = {
    'technology': [
        # Programming Languages
        'python', 'java', 'javascript', 'c++', 'c#', 'php', 'ruby', 'swift',
        'kotlin', 'scala', 'rust', 'go', 'r', 'typescript', 'perl', 'bash',
        # Web
        'html', 'css', 'react', 'angular', 'vue', 'node', 'django', 'flask',
        'fastapi', 'spring', 'express', 'graphql', 'rest api', 'nextjs',
        # Databases
        'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch',
        'oracle', 'sqlite', 'firebase', 'dynamodb', 'cassandra',
        'database', 'database management', 'database management systems',
        # Cloud & DevOps
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform', 'jenkins',
        'ci/cd', 'git', 'github', 'gitlab', 'ansible', 'puppet', 'chef',
        # Data Science & ML
        'machine learning', 'deep learning', 'neural network', 'tensorflow',
        'pytorch', 'pandas', 'numpy', 'scikit-learn', 'data analysis',
        'data science', 'artificial intelligence', 'nlp', 'computer vision',
        'statistics', 'big data', 'spark', 'hadoop', 'tableau', 'power bi',
        'artificial neural network',
        # Security
        'cybersecurity', 'cyber security', 'penetration testing', 'ethical hacking',
        'firewall', 'encryption', 'vulnerability', 'siem', 'soc', 'incident response',
        # Networking
        'networking', 'tcp/ip', 'dns', 'vpn', 'cisco', 'huawei', 'routing',
        'switching', 'lan', 'wan', 'sdwan', 'load balancing',
        # Tools
        'linux', 'windows server', 'vmware', 'jira', 'confluence', 'slack',
        'matlab', 'simulink', 'autocad', 'excel', 'vba',
        # Cross-domain
        'risk management', 'data management', 'information management',
        'business analysis', 'requirements analysis',
        # Soft skills
        'project management', 'leadership', 'communication', 'teamwork',
        'problem solving', 'agile', 'scrum', 'kanban', 'lead others',
    ],
    'academic': [
        # ACADEMIC includes ALL tech skills plus research-specific
        # Programming Languages
        'python', 'java', 'javascript', 'c++', 'c#', 'php', 'ruby', 'swift',
        'kotlin', 'scala', 'rust', 'go', 'r', 'typescript', 'perl', 'bash',
        'matlab', 'simulink', 'spss', 'stata', 'sas',
        # Web
        'html', 'css', 'react', 'angular', 'vue', 'node', 'django', 'flask',
        # Databases
        'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch',
        'oracle', 'sqlite', 'firebase', 'database', 'database management',
        # Cloud & DevOps
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'git', 'github',
        # Data Science & ML (CRITICAL for academics)
        'machine learning', 'deep learning', 'neural network', 'tensorflow',
        'pytorch', 'pandas', 'numpy', 'scikit-learn', 'data analysis',
        'data science', 'artificial intelligence', 'nlp', 'computer vision',
        'statistics', 'big data', 'spark', 'hadoop', 'tableau', 'power bi',
        'artificial neural network', 'image processing', 'signal processing',
        # Security
        'cybersecurity', 'cyber security', 'penetration testing', 'ethical hacking',
        'firewall', 'encryption', 'networking', 'tcp/ip',
        # Research tools
        'latex', 'overleaf', 'mendeley', 'zotero', 'endnote',
        # Engineering tools
        'autocad', 'solidworks', 'ansys', 'labview',
        # Academic soft skills
        'research', 'teaching', 'mentoring', 'supervision',
        'project management', 'leadership', 'communication', 'teamwork',
        'problem solving', 'presentation', 'writing',
    ],
    'finance': [
        'financial modeling', 'financial analysis', 'valuation', 'accounting',
        'auditing', 'budgeting', 'forecasting', 'treasury', 'cash management',
        'portfolio management', 'asset management', 'wealth management',
        'investment analysis', 'equity research', 'fixed income', 'derivatives',
        'risk management', 'credit analysis', 'trading', 'bloomberg',
        'excel', 'vba', 'python', 'sql', 'power bi', 'tableau', 'sap',
        'database', 'database management', 'data analysis', 'data management',
        'regulatory compliance', 'aml', 'kyc', 'basel', 'ifrs', 'gaap',
        'leadership', 'lead others', 'team lead', 'management',
        'project management', 'communication', 'teamwork', 'problem solving',
    ],
    'islamic_finance': [
        'sukuk', 'mudarabah', 'musharakah', 'murabaha', 'ijara', 'takaful',
        'sharia', 'islamic finance', 'islamic banking', 'sharia compliance',
        'islamic investment', 'halal investment', 'riba', 'gharar',
        'financial modeling', 'financial analysis', 'valuation', 'accounting',
        'auditing', 'portfolio management', 'asset management', 'risk management',
        'bloomberg', 'excel', 'vba', 'python', 'sql',
        'project management', 'leadership', 'communication', 'teamwork',
    ],
    'engineering': [
        'autocad', 'solidworks', 'catia', 'matlab', 'simulink', 'ansys',
        'plc', 'scada', 'embedded systems', 'microcontroller', 'arduino',
        'fpga', 'vhdl', 'verilog', 'pcb design', 'circuit design',
        'mechanical design', 'structural analysis', 'fea', 'cfd',
        'project management', 'leadership', 'communication', 'teamwork',
        # Engineering includes programming now
        'python', 'java', 'c++', 'c#', 'php', 'javascript', 'r',
        'sql', 'mysql', 'postgresql', 'machine learning', 'deep learning',
        'tcp/ip', 'cisco', 'routing', 'cybersecurity', 'networking',
    ],
    'healthcare': [
        'patient care', 'diagnosis', 'treatment', 'clinical research',
        'medical records', 'ehr', 'emr', 'hipaa', 'pharmacy', 'nursing',
        'medical imaging', 'radiology', 'laboratory', 'biostatistics',
        'epidemiology', 'public health', 'clinical trials',
        'excel', 'spss', 'sas', 'r', 'python', 'sql',
        'project management', 'leadership', 'communication', 'teamwork',
    ],
    'general': [
        'excel', 'word', 'powerpoint', 'outlook', 'teams',
        'project management', 'leadership', 'communication', 'teamwork',
        'problem solving', 'time management', 'organization',
    ],
}


def detect_candidate_field(text, education_data=None):
    """Detect what field/domain the candidate is in"""
    text_lower = text.lower()
    
    field_keywords = {
        'technology': ['software', 'developer', 'programming', 'database', 'cloud', 'devops',
                      'machine learning', 'ai', 'data science', 'cybersecurity', 'network'],
        'finance': ['finance', 'accounting', 'investment', 'banking', 'trading', 'portfolio',
                   'financial analysis', 'auditing', 'treasury'],
        'islamic_finance': ['islamic finance', 'sukuk', 'takaful', 'sharia', 'mudarabah',
                           'islamic banking', 'halal'],
        'healthcare': ['medical', 'healthcare', 'hospital', 'clinical', 'patient', 'nursing'],
        'academic': ['professor', 'lecturer', 'research', 'university', 'publications', 'phd'],
        'engineering': ['engineer', 'mechanical', 'electrical', 'civil', 'chemical', 'structural'],
    }
    
    scores = {field: 0 for field in field_keywords}
    
    for field, keywords in field_keywords.items():
        for kw in keywords:
            count = len(re.findall(r'\b' + re.escape(kw) + r'\b', text_lower))
            scores[field] += count * 2
    
    # Education bonus
    if education_data:
        edu_field = ' '.join([d.get('field_of_study', '') or '' for d in education_data.get('degrees', [])]).lower()
        
        if any(x in edu_field for x in ['computer', 'software', 'information', 'technology', 'cyber']):
            scores['technology'] += 5
        if any(x in edu_field for x in ['finance', 'accounting', 'business', 'economics']):
            scores['finance'] += 5
        if any(x in edu_field for x in ['islamic', 'sharia']):
            scores['islamic_finance'] += 5
        if any(x in edu_field for x in ['engineering', 'electronics', 'communications']):
            scores['engineering'] += 5
            scores['technology'] += 3
    
    max_field = max(scores, key=scores.get)
    
    if scores[max_field] < 3:
        return 'general'
    
    return max_field


def is_skill_allowed_for_field(skill_name, candidate_field):
    """Check if a skill is allowed for the candidate's detected field"""
    skill_lower = skill_name.lower().strip()
    
    if len(skill_lower) <= 2:
        short_allowed = ['r', 'c', 'c#', 'go', 'ai', 'ml', 'js', 'ui', 'ux', 'qa', 'it', 'hr', 'bi']
        if skill_lower not in short_allowed:
            return False
    
    allowed = FIELD_ALLOWED_SKILLS.get(candidate_field, FIELD_ALLOWED_SKILLS['general'])
    
    skill_normalized = re.sub(r's$', '', skill_lower)
    
    for allowed_skill in allowed:
        allowed_lower = allowed_skill.lower()
        allowed_normalized = re.sub(r's$', '', allowed_lower)
        
        if skill_lower == allowed_lower or skill_normalized == allowed_normalized:
            return True
        
        pattern = r'\b' + re.escape(allowed_lower) + r's?\b'
        if re.search(pattern, skill_lower):
            return True
        
        pattern_reverse = r'\b' + re.escape(skill_normalized) + r's?\b'
        if re.search(pattern_reverse, allowed_lower):
            return True
        
        skill_words = set(skill_lower.split())
        allowed_words = set(allowed_lower.split())
        overlap = skill_words & allowed_words
        significant = [w for w in overlap if len(w) > 3]
        if len(significant) >= 2:
            return True
    
    general_skills = ['communication', 'leadership', 'teamwork', 'problem solving',
                      'project management', 'excel', 'presentation']
    for gs in general_skills:
        pattern = r'\b' + re.escape(gs) + r's?\b'
        if re.search(pattern, skill_lower):
            return True
    
    return False


# ============================================================
# SKILL PATTERNS
# ============================================================
RECALL_PATTERNS = {
    # Programming Languages
    'python': r'\bpython\b',
    'java': r'\bjava\b(?!\s*script)',
    'javascript': r'\bjavascr?ipt\b|\bjs\b',
    'c++': r'\bc\+\+\b|\bcpp\b|c/c\+\+',
    'c#': r'\bc#\b|csharp',
    'php': r'\bphp\b',
    'ruby': r'\bruby\b',
    'swift': r'\bswift\b',
    'kotlin': r'\bkotlin\b',
    'scala': r'\bscala\b',
    'rust': r'\brust\b',
    'go': r'\bgolang\b|\bgo\s+lang|\bgo\b(?=\s*[,\n\.])',
    'r': r'\br\b(?=\s*[,\n\.]|\s+programming|\s+language|\s+for\s+data)',
    
    # Databases
    'sql': r'\bsql\b',
    'mysql': r'\bmysql\b',
    'postgresql': r'\bpostgres(?:ql)?\b',
    'mongodb': r'\bmongodb\b',
    'sqlite': r'\bsqlite\b',
    'firebase': r'\bfirebase\b',
    
    # Web Technologies
    'html': r'\bhtml\d?\b',
    'css': r'\bcss\d?\b',
    'react': r'\breact(?:\.?js|[\s\-]native)?\b(?!\s+calm)',  # Exclude "react calmly"
    'angular': r'\bangular\b',
    'vue': r'\bvue\.?js?\b',
    'node': r'\bnode\.?js\b',
    'nextjs': r'\bnext\.?js\b',
    'django': r'\bdjango\b',
    'flask': r'\bflask\b',
    'graphql': r'\bgraphql\b',
    'rest': r'\brestful?\b|\brest\s+api',
    
    # Data Science / ML
    'machine learning': r'\bmachine\s+learn',
    'deep learning': r'\bdeep\s+learn',
    'neural network': r'\bneural\s+network',
    'data analysis': r'\bdata\s+analy',
    'data science': r'\bdata\s+scien',
    'artificial intelligence': r'\bartificial\s+intelligen|\b(?<!\w)ai\b(?!\w)',
    'natural language processing': r'\bnatural\s+language\s+process|\bnlp\b',
    'computer vision': r'\bcomputer\s+vision',
    'tensorflow': r'\btensorflow\b',
    'pytorch': r'\bpytorch\b',
    'statistics': r'\bstatistics\b|\bstatistical\b',
    
    # Tools & Platforms
    'excel': r'\bexcel\b(?!\s*lent)',
    'power bi': r'\bpower\s*bi\b',
    'tableau': r'\btableau\b',
    'matlab': r'\bmatlab\b',
    'simulink': r'\bsimulink\b',
    'autocad': r'\bautocad\b',
    'git': r'\bgit\b(?!hub)',
    'docker': r'\bdocker\b',
    'kubernetes': r'\bkubernetes\b|\bk8s\b',
    'aws': r'\baws\b|amazon\s+web\s+services',
    'azure': r'\bazure\b',
    'gcp': r'\bgcp\b|google\s+cloud',
    'linux': r'\blinux\b',
    
    # Networking & Security
    'tcp/ip': r'\btcp\s*/?\s*ip\b',
    'networking': r'\bnetwork(?:ing)?\b',
    'cybersecurity': r'\bcyber\s*security\b',
    'cyber security': r'\bcyber\s+security\b',
    'penetration testing': r'\bpenetration\s+test',
    'cisco': r'\bcisco\b',
    
    # Finance
    'financial modeling': r'\bfinancial\s+model',
    'financial analysis': r'\bfinancial\s+analy',
    'accounting': r'\baccounting\b',
    'auditing': r'\bauditing\b',
    'risk management': r'\brisk\s+management\b',
    
    # Islamic Finance
    'sukuk': r'\bsukuk\b',
    'mudarabah': r'\bmudarabah?\b',
    'musharakah': r'\bmusharakah?\b',
    'murabaha': r'\bmurabah?a\b',
    'ijara': r'\bijara\b',
    'takaful': r'\btakaful\b',
    'sharia': r'\bshari[\'"]?a[h]?\b',
    'islamic finance': r'\bislamic\s+finance\b',
    'islamic banking': r'\bislamic\s+bank',
    
    # Soft Skills
    'project management': r'\bproject\s+management\b',
    'leadership': r'\bleadership\b',
    'lead others': r'\blead\s+others\b|\bleading\s+others\b',
}

# ============================================================
# OPTIMIZATION 2: PRECOMPILE REGEX PATTERNS (runs ONCE at module load)
# This saves ~2-3 seconds per CV by avoiding re-compilation
# ============================================================
COMPILED_RECALL_PATTERNS = {
    skill_name: re.compile(pattern, re.IGNORECASE)
    for skill_name, pattern in RECALL_PATTERNS.items()
}


# ============================================================
# OPTIMIZATION 1: ESCO VALIDATOR SINGLETON
# Load database ONCE at module startup, build word index for O(1) lookups
# This saves ~8-12 seconds per CV
# ============================================================
class ESCOValidator:
    """ESCO Database Validator with Domain Filtering - SINGLETON"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if ESCOValidator._initialized:
            return
        
        self.available = ESCO_DB_PATH.exists()
        self.skill_cache = {}
        self.word_to_aliases = {}  # word -> list of (alias, skill_id, canonical)
        self.all_words = set()  # All words that appear in any alias
        
        if self.available:
            self._load_cache()
        
        ESCOValidator._initialized = True
    
    def _load_cache(self):
        try:
            conn = sqlite3.connect(ESCO_DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT sa.alias, s.skill_id, s.skill_name 
                FROM skill_aliases sa 
                JOIN skills s ON sa.skill_id = s.skill_id
            """)
            for alias, skill_id, skill_name in cur.fetchall():
                alias_lower = alias.lower()
                self.skill_cache[alias_lower] = (skill_id, skill_name)
                
                # Build word index for fast partial matching
                if len(alias_lower) > 4:
                    words = alias_lower.split()
                    for word in words:
                        if len(word) > 2:  # Skip very short words
                            if word not in self.word_to_aliases:
                                self.word_to_aliases[word] = []
                            self.word_to_aliases[word].append((alias_lower, skill_id, skill_name))
                            self.all_words.add(word)
            
            conn.close()
            print(f"  ✅ ESCO Singleton loaded: {len(self.skill_cache)} aliases, {len(self.word_to_aliases)} word index")
        except Exception as e:
            print(f"  ⚠️ ESCO load error: {e}")
            self.available = False
    
    def validate_skill(self, raw_skill_name):
        """Validate skill with OPTIMIZED partial matching using word index"""
        if not self.available:
            return False, raw_skill_name, None, 0.3
        
        normalized = raw_skill_name.lower().strip()
        
        # Direct match (O(1))
        if normalized in self.skill_cache:
            skill_id, canonical = self.skill_cache[normalized]
            if not is_relevant_skill(canonical):
                return False, raw_skill_name.title(), None, 0.2
            return True, canonical, skill_id, 1.0
        
        # Fuzzy match
        if FUZZY_AVAILABLE:
            fuzzy_normalized = normalize_skill(raw_skill_name).lower()
            if fuzzy_normalized in self.skill_cache:
                skill_id, canonical = self.skill_cache[fuzzy_normalized]
                if not is_relevant_skill(canonical):
                    return False, raw_skill_name.title(), None, 0.2
                return True, canonical, skill_id, 0.9
        
        # OPTIMIZED PARTIAL MATCHING using word index
        # Direction 1: Check if any alias appears in normalized (alias is substring)
        normalized_words = set(normalized.split())
        candidates_checked = set()
        
        for word in normalized_words:
            if word in self.word_to_aliases:
                for alias, skill_id, canonical in self.word_to_aliases[word]:
                    if alias in candidates_checked:
                        continue
                    candidates_checked.add(alias)
                    
                    if len(alias) > 4:
                        if re.search(r'\b' + re.escape(alias) + r'\b', normalized):
                            if is_relevant_skill(canonical):
                                return True, canonical, skill_id, 0.85
        
        # Direction 2: Check if normalized appears in any alias (normalized is substring)
        if len(normalized) > 4:
            # Check aliases that contain any word from normalized
            for word in normalized_words:
                if len(word) > 2 and word in self.word_to_aliases:
                    for alias, skill_id, canonical in self.word_to_aliases[word]:
                        if alias in candidates_checked:
                            continue
                        candidates_checked.add(alias)
                        
                        if re.search(r'\b' + re.escape(normalized) + r'\b', alias):
                            if is_relevant_skill(canonical):
                                return True, canonical, skill_id, 0.85
            
            # Also check if normalized itself is a word in any alias
            if normalized in self.word_to_aliases:
                for alias, skill_id, canonical in self.word_to_aliases[normalized]:
                    if is_relevant_skill(canonical):
                        return True, canonical, skill_id, 0.85
        
        return False, raw_skill_name.title(), None, 0.3


# Initialize ESCO singleton at module load (runs ONCE for entire server)
_esco_singleton = ESCOValidator()


# ============================================================
# RESUME ANALYZER - HYBRID VERSION
# ============================================================
class ResumeAnalyzer:
    """Resume Analyzer combining old preprocessing with new filtering"""
    
    def __init__(self):
        self.nlp = nlp
        self.esco = _esco_singleton  # OPTIMIZATION: Use singleton instead of creating new
        self.is_academic_cv = False
        self.candidate_field = 'general'
    
    def detect_academic_cv(self, text):
        """Detect if CV is academic-style"""
        text_lower = text.lower()
        indicators = 0
        
        if re.search(r'\b(professor|lecturer|researcher|postdoc)\b', text_lower):
            indicators += 2
        if re.search(r'\b(publications?|papers?|proceedings)\b', text_lower):
            indicators += 2
        if re.search(r'\b(supervised|thesis|dissertation)\b', text_lower):
            indicators += 1
        if re.search(r'\b(grant|funded|principal\s+investigator)\b', text_lower):
            indicators += 1
        if re.search(r'\b(conference|symposium|tpc\s+member)\b', text_lower):
            indicators += 1
        
        self.is_academic_cv = indicators >= 3
        return self.is_academic_cv
    
    def extract_contact_info(self, text):
        """Extract contact information with improved phone detection"""
        contact = {'email': None, 'phone': None, 'name': None}
        
        # Email extraction
        email_patterns = [
            r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:com|edu|org|bh|uk|in|net|gov|io)',
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        ]
        
        for pattern in email_patterns:
            emails = re.findall(pattern, text, re.IGNORECASE)
            for email in emails:
                if any(skip in email.lower() for skip in ['orcid', 'scholar', 'linkedin', 'google']):
                    continue
                if '//' in email or 'http' in email.lower():
                    continue
                contact['email'] = email
                break
            if contact['email']:
                break
        
        # Try spaced emails
        if not contact['email']:
            for line in text.split('\n'):
                if '@' in line:
                    cleaned_line = re.sub(r'\s*@\s*', '@', line)
                    cleaned_line = re.sub(r'(\w)\s+(\w)', r'\1\2', cleaned_line)
                    cleaned_line = re.sub(r'\s*\.\s*(?=com|edu|org|bh|uk)', '.', cleaned_line, flags=re.IGNORECASE)
                    
                    for pattern in email_patterns:
                        emails = re.findall(pattern, cleaned_line, re.IGNORECASE)
                        for email in emails:
                            if not any(skip in email.lower() for skip in ['orcid', 'scholar']):
                                contact['email'] = email
                                break
                        if contact['email']:
                            break
                if contact['email']:
                    break
        
        # ============================================================
        # IMPROVED PHONE EXTRACTION - Context-aware
        # Fixes: No longer grabs random 8-digit numbers like years/IDs
        # ============================================================
        
        # Priority 1: Look for phone numbers with explicit labels
        labeled_phone_patterns = [
            r'(?:phone|mobile|tel|cell|contact|ph)[\s:.\-]*(\+?\d[\d\s\-\.]{7,15})',
            r'(?:phone|mobile|tel|cell|contact|ph)[\s:.\-]*\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}',
        ]
        
        for pattern in labeled_phone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                phone = match.group(1) if match.lastindex else match.group(0)
                phone = re.sub(r'^[:\s\-\.]+', '', phone)
                phone = re.sub(r'(?:phone|mobile|tel|cell|contact|ph)[\s:.\-]*', '', phone, flags=re.IGNORECASE)
                digits = ''.join(filter(str.isdigit, phone))
                if 7 <= len(digits) <= 15:
                    contact['phone'] = phone.strip()
                    break
        
        # Priority 2: International format with country code (most reliable)
        if not contact['phone']:
            intl_patterns = [
                r'\+973[\s\-]?\d{8}',           # Bahrain
                r'\+971[\s\-]?\d{8,9}',         # UAE
                r'\+966[\s\-]?\d{8,9}',         # Saudi
                r'\+91[\s\-]?\d{10}',           # India
                r'\+1[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}',  # US/Canada
                r'\+44[\s\-]?\d{10,11}',        # UK
                r'\+\d{1,3}[\s\-]?\d{8,12}',    # Generic international
            ]
            
            for pattern in intl_patterns:
                match = re.search(pattern, text)
                if match:
                    contact['phone'] = match.group(0).strip()
                    break
        
        # Priority 3: Bahrain local format (8 digits starting with 3, 6, or 17)
        if not contact['phone']:
            bahrain_pattern = r'\b([36]\d{7}|17\d{6})\b'
            first_section = '\n'.join(text.split('\n')[:30])
            match = re.search(bahrain_pattern, first_section)
            if match:
                phone = match.group(1)
                if not self._looks_like_year_or_id(phone, text):
                    contact['phone'] = phone
        
        # Priority 4: Generic 8-digit with strict validation (contact section only)
        if not contact['phone']:
            contact_section = '\n'.join(text.split('\n')[:20])
            matches = re.findall(r'\b(\d{8})\b', contact_section)
            
            for phone in matches:
                if not self._looks_like_year_or_id(phone, text):
                    contact['phone'] = phone
                    break
        
        return contact
    
    def _looks_like_year_or_id(self, number, full_text):
        """Check if a number looks like a year, date, or ID rather than phone"""
        digits = ''.join(filter(str.isdigit, number))
        
        # Check if it looks like concatenated years (e.g., 20132024)
        if len(digits) == 8:
            first_half = int(digits[:4])
            second_half = int(digits[4:])
            
            # Both halves look like years (e.g., 20132024, 19912000)
            if 1950 <= first_half <= 2030 and 1950 <= second_half <= 2030:
                return True
            if 1950 <= first_half <= 2030 and 1900 <= second_half <= 2099:
                return True
        
        # Check context around the number
        idx = full_text.find(number)
        if idx != -1:
            context = full_text[max(0, idx-100):idx+len(number)+50].lower()
            
            # If near certificate/ID terms, likely not a phone
            bad_context = ['certificate', 'cert no', 'cert.', 'credential', 
                          'license', 'id:', 'id no', 'registration', 'reg no',
                          'orcid', 'isbn', 'issn', 'doi', 'batch', 'roll',
                          'student', 'employee id', 'staff id', 'reg.']
            
            if any(term in context for term in bad_context):
                return True
        
        # Year-like patterns (starts with 19xx or 20xx but not 17xx which is Bahrain landline)
        if digits.startswith('19') or (digits.startswith('20') and not digits.startswith('200')):
            if not digits.startswith('17'):
                if len(digits) == 8 and 1950 <= int(digits[:4]) <= 2030:
                    return True
        
        # Check if number appears in education or experience date context
        if len(digits) == 8:
            # Pattern like "2013 - 2022" could be parsed as "20132022"
            year1 = digits[:4]
            year2 = digits[4:]
            if year1.isdigit() and year2.isdigit():
                y1, y2 = int(year1), int(year2)
                if 1980 <= y1 <= 2025 and 1980 <= y2 <= 2025:
                    return True
        
        return False
    
    def _extract_section(self, text, section_type):
        """
        Extract a specific section from CV - EUROPASS-OPTIMIZED VERSION
        
        Priority 1: Europass standard headers
        Priority 2: Common CV headers
        Priority 3: Variant headers
        """
        lines = text.split('\n')
        in_section = False
        section_lines = []
        
        # EUROPASS-ALIGNED HEADERS (priority order)
        headers = {
            'education': [
                # Europass PRIMARY
                'education and training',
                # Common variants
                'education', 'academic background', 'qualifications', 
                'academic qualifications', 'educational background',
                'academic history', 'studies'
            ],
            'employment': [
                # Europass PRIMARY
                'work experience',
                # Common variants
                'employment', 'professional experience', 'employment history', 
                'career history', 'work history', 'experience',
                'professional background', 'career summary', 'career'
            ],
            'academic_appointments': [
                'academic appointments', 'academic positions', 'teaching positions',
                'faculty positions', 'research positions'
            ],
            'teaching': [
                'teaching and research', 'teaching experience', 'research experience'
            ],
            'certifications': [
                # Europass: part of Additional Information
                'certifications', 'certification', 'certificates', 'licenses',
                'professional certifications', 'accreditations'
            ],
            'skills': [
                # Europass PRIMARY
                'personal skills',
                # Europass sub-sections
                'digital competence', 'communication skills', 
                'organisational skills', 'organizational skills',
                'job-related skills', 'other skills',
                # Common variants  
                'skills', 'competencies', 'expertise', 'technical skills', 
                'key competencies', 'core competencies', 'key skills',
                'professional skills', 'it skills', 'computer skills',
                # Finance-specific
                'financial skills', 'compliance skills', 'technical skills'
            ],
            'languages': [
                # Europass PRIMARY
                'mother tongue', 'other languages',
                # Common variants
                'languages', 'language skills', 'language proficiency'
            ],
            'additional': [
                # Europass PRIMARY
                'additional information',
                # Sub-sections
                'publications', 'presentations', 'projects', 'conferences',
                'seminars', 'honours and awards', 'honors and awards',
                'memberships', 'references', 'citations', 'courses'
            ],
        }
        
        start_markers = headers.get(section_type, [section_type])
        
        # End markers - stop when we hit another major section
        end_markers = [
            'education', 'education and training', 'skills', 'personal skills',
            'certifications', 'publications', 'references', 'awards', 
            'languages', 'honors', 'honours', 'memberships', 'training', 
            'research projects', 'key achievements', 'students supervised',
            'additional information', 'interests', 'hobbies', 'annexes',
            'work experience', 'employment'
        ]
        
        end_markers = [m for m in end_markers if m not in start_markers]
        
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            if not in_section:
                for marker in start_markers:
                    if marker in line_lower:
                        in_section = True
                        break
                continue
            
            if in_section:
                is_new_section = False
                for end_marker in end_markers:
                    if line_lower.startswith(end_marker) or line_lower == end_marker:
                        is_new_section = True
                        break
                    if line.strip().isupper() and end_marker in line_lower:
                        is_new_section = True
                        break
                
                if is_new_section:
                    break
                
                section_lines.append(line)
        
        return '\n'.join(section_lines)
    
    def extract_education(self, text):
        """Extract education with comprehensive pattern matching"""
        normalized_text = normalize_cv_text(text)
        
        degrees = []
        highest_rank = -1
        seen_fields = set()
        
        # Pattern 1: "M.Sc. Field" or "B.Sc. Field"
        pattern1 = r'\b(M\.?Sc\.?|B\.?Sc\.?)\s*(?:Hons\.?)?\s+([A-Z][A-Za-z\s&]+?)(?:\s+(?:University|Institute|College)|$|\n|,|\d{4})'
        
        for match in re.finditer(pattern1, normalized_text, re.MULTILINE | re.IGNORECASE):
            degree_text = match.group(1).strip()
            field = match.group(2).strip().rstrip(',.')
            
            if len(field) < 3 or field.lower() in seen_fields:
                continue
            if any(x in field.lower() for x in ['university', 'institute', 'college']):
                continue
            
            seen_fields.add(field.lower())
            degree_info = self._classify_degree(degree_text)
            
            degrees.append({
                'degree': degree_info['name'],
                'level': degree_info['level'],
                'rank': degree_info['rank'],
                'field_of_study': field,
                'institution': None,
                'graduation_year': None
            })
            
            if degree_info['rank'] > highest_rank:
                highest_rank = degree_info['rank']
        
        # Pattern 2: "Ph.D - Field" or "Master of X - Field"
        pattern2 = r'(Ph\.?D\.?|Doctorate|Master\s+of\s+\w+|Bachelor\s+of\s+\w+)\s*[-–—]\s*([A-Za-z\s,&()]+?)(?:,|\n|\d{4})'
        
        for match in re.finditer(pattern2, normalized_text, re.IGNORECASE):
            degree_text = match.group(1).strip()
            field = match.group(2).strip().rstrip(',.')
            field = re.sub(r'\s*\([^)]*\)\s*$', '', field).strip()
            
            if field.lower() in seen_fields or len(field) < 3:
                continue
            seen_fields.add(field.lower())
            
            degree_info = self._classify_degree(degree_text)
            
            degrees.append({
                'degree': degree_info['name'],
                'level': degree_info['level'],
                'rank': degree_info['rank'],
                'field_of_study': field,
                'institution': None,
                'graduation_year': None
            })
            
            if degree_info['rank'] > highest_rank:
                highest_rank = degree_info['rank']
        
        # Pattern 3: "Bachelor's Degree in X"
        pattern3 = r"(Bachelor'?s?|Master'?s?)\s+Degree\s+in\s+([A-Za-z][A-Za-z\s&]+?)(?:\s*$|\s*\n|\s*,|\s*\d{4})"
        
        for match in re.finditer(pattern3, normalized_text, re.IGNORECASE | re.MULTILINE):
            degree_text = match.group(1).strip()
            field = match.group(2).strip().rstrip(',.')
            
            if field.lower() in seen_fields or len(field) < 4:
                continue
            seen_fields.add(field.lower())
            
            degree_info = self._classify_degree(degree_text)
            
            degrees.append({
                'degree': degree_info['name'],
                'level': degree_info['level'],
                'rank': degree_info['rank'],
                'field_of_study': field,
                'institution': None,
                'graduation_year': None
            })
            
            if degree_info['rank'] > highest_rank:
                highest_rank = degree_info['rank']
        
        # Pattern 4: "YEAR – YEAR Degree in Field from Institution"
        pattern4 = r'(\d{4})\s*[–—-]\s*(\d{4})?\s*(Ph\.?D\.?|Doctorate|Master|Bachelor)[^\d]*?(?:in|of)\s+([A-Za-z\s,&]+?)\s+from\s+([A-Za-z\s,]+?)(?:\s*[-–]|\s*Thesis|\s*,\s*[A-Z]|\s*$)'
        
        for match in re.finditer(pattern4, normalized_text, re.IGNORECASE):
            start_year = match.group(1)
            end_year = match.group(2) or start_year
            degree_text = match.group(3).strip()
            field = match.group(4).strip().rstrip(',.')
            institution = match.group(5).strip().rstrip(',.')
            
            if field.lower() in seen_fields:
                continue
            seen_fields.add(field.lower())
            
            degree_info = self._classify_degree(degree_text)
            
            degrees.append({
                'degree': degree_info['name'],
                'level': degree_info['level'],
                'rank': degree_info['rank'],
                'field_of_study': field,
                'institution': institution,
                'graduation_year': int(end_year) if end_year else None
            })
            
            if degree_info['rank'] > highest_rank:
                highest_rank = degree_info['rank']
        
        # Fallback: Simple detection
        if not degrees:
            simple_patterns = [
                (r'\b(ph\.?\s*d\.?|doctorate|doctoral)\b', 'PhD', 'phd', 3),
                (r'\b(m\.?\s*sc\.?|m\.?\s*eng\.?|master|mba)\b', 'Master', 'master', 2),
                (r'\b(b\.?\s*sc\.?|b\.?\s*eng\.?|bachelor)\b', 'Bachelor', 'bachelor', 1),
                (r'\b(diploma|associate)\b', 'Diploma', 'diploma', 0),
            ]
            
            for pattern, degree_name, level, rank in simple_patterns:
                if re.search(pattern, normalized_text, re.IGNORECASE):
                    degrees.append({
                        'degree': degree_name,
                        'level': level,
                        'rank': rank,
                        'field_of_study': None,
                        'institution': None,
                        'graduation_year': None
                    })
                    if rank > highest_rank:
                        highest_rank = rank
                    break
        
        if not degrees:
            degrees.append({
                'degree': 'Unknown',
                'level': 'unknown',
                'rank': -1,
                'field_of_study': None,
                'institution': None,
                'graduation_year': None
            })
        
        degrees.sort(key=lambda x: x['rank'], reverse=True)
        
        # Certifications
        print(f"  ✅ Loaded certifications from JSON")
        certs_found = detect_certifications(text)
        
        has_if_cert = False
        cert_names = []
        
        for cert in certs_found:
            if 'islamic' in cert['category'].lower() or 'finance' in cert['category'].lower():
                has_if_cert = True
                cert_names.append(cert['name'])
        
        if certs_found:
            print(f"   📜 Certifications: {len(certs_found)} found")
            for cert in certs_found[:3]:
                print(f"      - {cert['name']} ({cert['category']})")
        
        return {
            'degrees': degrees,
            'level': degrees[0]['level'] if degrees else 'unknown',
            'highest_rank': highest_rank,
            'has_islamic_finance_cert': has_if_cert,
            'certification_names': ', '.join(cert_names) if cert_names else None,
            'all_certifications': certs_found
        }
    
    def _classify_degree(self, degree_text):
        """Classify degree text into standardized format"""
        degree_lower = degree_text.lower().strip()
        
        if any(x in degree_lower for x in ['ph', 'doctor', 'phd']):
            return {'name': 'PhD', 'level': 'phd', 'rank': 3}
        elif any(x in degree_lower for x in ['master', 'm.sc', 'msc', 'm.a', 'ma', 'm.eng', 'mba']):
            return {'name': 'Master', 'level': 'master', 'rank': 2}
        elif any(x in degree_lower for x in ['bachelor', 'b.sc', 'bsc', 'b.a', 'ba', 'b.eng']):
            return {'name': 'Bachelor', 'level': 'bachelor', 'rank': 1}
        elif any(x in degree_lower for x in ['diploma', 'associate']):
            return {'name': 'Diploma', 'level': 'diploma', 'rank': 0}
        else:
            return {'name': degree_text, 'level': 'other', 'rank': 0}
    
    def extract_languages(self, text):
        """
        EUROPASS-COMPLIANT Language Extraction
        ======================================
        
        Extracts language proficiency using CEFR levels (A1-C2) or 
        common descriptors (Native, Fluent, Intermediate, Basic).
        
        Valuable for Arcapita: Arabic, English essential; French, Urdu common.
        
        Returns:
            dict: {
                'languages': [{'name': 'English', 'level': 'Native', 'cefr': 'C2'}, ...],
                'has_arabic': bool,
                'has_english': bool,
                'language_count': int
            }
        """
        languages = []
        text_lower = text.lower()
        
        # Try to find the Languages section first
        lang_section = self._extract_section(text, 'languages')
        search_text = lang_section if lang_section else text
        search_lower = search_text.lower()
        
        # CEFR level mapping
        cefr_map = {
            'a1': 'A1 (Beginner)',
            'a2': 'A2 (Elementary)', 
            'b1': 'B1 (Intermediate)',
            'b2': 'B2 (Upper Intermediate)',
            'c1': 'C1 (Advanced)',
            'c2': 'C2 (Proficient)',
        }
        
        # Common proficiency descriptors → CEFR equivalent
        level_to_cefr = {
            'native': 'C2',
            'mother tongue': 'C2',
            'fluent': 'C1',
            'proficient': 'C1',
            'advanced': 'C1',
            'upper intermediate': 'B2',
            'intermediate': 'B1',
            'conversational': 'B1',
            'elementary': 'A2',
            'basic': 'A1',
            'beginner': 'A1',
        }
        
        # Languages commonly found in GCC/Finance CVs
        target_languages = [
            'english', 'arabic', 'french', 'urdu', 'hindi', 
            'german', 'spanish', 'mandarin', 'chinese',
            'japanese', 'korean', 'portuguese', 'italian',
            'russian', 'turkish', 'persian', 'farsi', 'bengali',
            'tagalog', 'filipino', 'malayalam', 'tamil'
        ]
        
        # Pattern 1: "Language: Level" or "Language - Level"
        for lang in target_languages:
            # Match "English: Native" or "English - Fluent" or "English (Native)"
            pattern = rf'\b{lang}\b[\s:–\-\(]*\s*(native|mother\s*tongue|fluent|proficient|advanced|intermediate|basic|beginner|a[12]|b[12]|c[12])'
            match = re.search(pattern, search_lower)
            
            if match:
                level_text = match.group(1).strip().lower()
                
                # Determine CEFR level
                if level_text in ['a1', 'a2', 'b1', 'b2', 'c1', 'c2']:
                    cefr = level_text.upper()
                    level_desc = cefr_map.get(level_text, level_text.upper())
                else:
                    cefr = level_to_cefr.get(level_text, 'B1')
                    level_desc = level_text.title()
                
                languages.append({
                    'name': lang.title(),
                    'level': level_desc,
                    'cefr': cefr
                })
            elif lang in search_lower:
                # Language mentioned but no level - assume at least intermediate
                languages.append({
                    'name': lang.title(),
                    'level': 'Not specified',
                    'cefr': 'B1'  # Conservative assumption
                })
        
        # Check for key languages
        has_arabic = any(l['name'].lower() == 'arabic' for l in languages)
        has_english = any(l['name'].lower() == 'english' for l in languages)
        
        # If no English detected but CV is in English, assume proficiency
        if not has_english and len(text) > 500:
            languages.append({
                'name': 'English',
                'level': 'Proficient (CV language)',
                'cefr': 'C1'
            })
            has_english = True
        
        print(f"   🌍 Languages: {len(languages)} detected")
        for lang in languages[:4]:
            print(f"      - {lang['name']}: {lang['level']}")
        
        return {
            'languages': languages,
            'has_arabic': has_arabic,
            'has_english': has_english,
            'language_count': len(languages)
        }
    
    def extract_experience(self, text):
        """
        HYBRID Experience Extraction
        =============================
        FROM OLD CODE:
        - normalize_cv_text() first
        - normalize_dates_in_text() first
        - 0.5 year merge tolerance
        - CV-type-aware section extraction
        
        FROM NEW CODE:
        - int() flooring (not rounding)
        - Academic service exclusion
        - Education line exclusion
        - Course vs teaching distinction
        """
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # ============================================================
        # STEP 0: NORMALIZE TEXT AND DATES (FROM OLD CODE - CRITICAL)
        # ============================================================
        normalized_text = normalize_cv_text(text)
        normalized_text = normalize_dates_in_text(normalized_text)
        
        # Detect CV type
        is_academic = self.detect_academic_cv(normalized_text)
        print(f"📄 CV Type: {'Academic' if is_academic else 'Industry'}")
        
        # ============================================================
        # STEP 1: Check for explicit experience statements (but don't trust blindly)
        # ============================================================
        explicit_years_claim = None
        explicit_patterns = [
            r'(\d+)\+?\s*years?\s+(?:of\s+)?(?:professional\s+)?experience',
            r'experience\s*[:\-]?\s*(\d+)\+?\s*years?',
            r'(\d+)\+?\s*years?\s+in\s+(?:the\s+)?(?:field|industry)',
        ]
        
        for pattern in explicit_patterns:
            matches = re.findall(pattern, normalized_text.lower())
            if matches:
                years_found = [int(m) for m in matches if int(m) <= 50]
                if years_found:
                    explicit_years_claim = max(years_found)
                    break  # Found explicit claim, but DON'T return yet
        
        # ============================================================
        # STEP 2: Section-based extraction (FROM OLD CODE)
        # ============================================================
        if is_academic:
            section_types = ['employment', 'academic_appointments', 'teaching']
        else:
            section_types = ['employment']
        
        all_dates = []
        counted_roles = []
        skipped_roles = []
        
        # Job title indicators
        job_titles = [
            'professor', 'associate professor', 'assistant professor',
            'lecturer', 'senior lecturer', 'teacher', 'instructor', 'mentor',
            'engineer', 'developer', 'programmer', 'architect',
            'manager', 'director', 'lead', 'head', 'chief',
            'analyst', 'consultant', 'specialist', 'officer',
            'coordinator', 'administrator', 'supervisor',
            'scientist', 'researcher', 'research associate', 'postdoc',
            'executive', 'president', 'ceo', 'cto', 'vp',
            'accountant', 'auditor', 'banker', 'trader',
            'intern', 'trainee', 'associate', 'senior', 'junior',
        ]
        
        # Academic service (NOT employment) - FROM NEW CODE
        academic_service = [
            'associate editor', 'guest editor', 'editorial board',
            'reviewer', 'peer reviewer', 'sub-reviewer',
            'member', 'committee', 'board member', 'tpc member',
            'session chair', 'conference chair', 'workshop chair',
            'keynote', 'invited speaker', 'panelist',
            'award', 'scholarship', 'grant', 'fellowship',
            'supervised', 'thesis supervisor',
        ]
        
        # Education indicators - FROM NEW CODE
        education_keywords = [
            'bachelor', 'master', 'phd', 'ph.d', 'doctorate',
            'degree', 'diploma', 'gpa', 'cgpa', 'thesis', 'dissertation',
        ]
        
        # Course indicators (not teaching jobs)
        course_indicators = ['course', 'learning', 'training', 'module', 'curriculum']
        
        # Teaching indicators (ARE jobs)
        teaching_indicators = ['lecturer', 'teacher', 'professor', 'instructor', 'mentor', 'faculty']
        
        for section_type in section_types:
            section_text = self._extract_section(normalized_text, section_type)
            
            if section_text and len(section_text.strip()) > 50:
                print(f"   ✓ Found {section_type} section")
                
                for line in section_text.split('\n'):
                    line_lower = line.lower().strip()
                    if not line_lower or len(line_lower) < 10:
                        continue
                    
                    # Check for date pattern
                    date_match = re.search(
                        r'(\d{1,2})/(\d{4})\s*–\s*(?:(\d{1,2})/(\d{4})|(present|current|now))',
                        line, re.IGNORECASE
                    )
                    if not date_match:
                        continue
                    
                    description = line[:60].strip() + ('...' if len(line) > 60 else '')
                    
                    # GATE 1: Education check
                    is_education = any(edu in line_lower for edu in education_keywords)
                    if is_education:
                        skipped_roles.append(f"EDUCATION: {description}")
                        continue
                    
                    # GATE 2: Academic service check
                    is_service = any(svc in line_lower for svc in academic_service)
                    has_job_title = any(job in line_lower for job in job_titles)
                    
                    if is_service and not has_job_title:
                        skipped_roles.append(f"SERVICE: {description}")
                        continue
                    
                    # GATE 3: Course check (but teaching jobs are OK)
                    is_course = any(ctx in line_lower for ctx in course_indicators)
                    is_teaching = any(t in line_lower for t in teaching_indicators)
                    
                    if is_course and not is_teaching:
                        skipped_roles.append(f"COURSE: {description}")
                        continue
                    
                    # Extract dates - USE MONTHS not decimal years
                    start_month, start_year = int(date_match.group(1)), int(date_match.group(2))
                    if date_match.group(5):
                        end_year, end_month = current_year, current_month
                    else:
                        end_month, end_year = int(date_match.group(3)), int(date_match.group(4))
                    
                    if 1980 <= start_year <= current_year and start_year <= end_year:
                        # Convert to total months (no floating point)
                        start_months = start_year * 12 + (start_month - 1)
                        end_months = end_year * 12 + (end_month - 1)
                        
                        # SHORT ACADEMIC ROLE FILTER
                        # Skip micro-appointments (mentor, adjunct, visiting) < 12 months
                        if is_academic and any(t in line_lower for t in ['mentor', 'adjunct', 'visiting', 'temporary']):
                            if (end_months - start_months) < 12:
                                skipped_roles.append(f"SHORT ROLE: {description}")
                                continue
                        
                        # Sanity check: max 30 years per role
                        if (end_months - start_months) <= 360:
                            all_dates.append((start_months, end_months))
                            counted_roles.append(f"{start_year}-{end_year}: {description}")
        
        # ============================================================
        # STEP 3: Fallback - line-by-line with job indicators
        # ============================================================
        if not all_dates:
            print(f"   ⚠️ No section found - using line-by-line fallback")
            
            for line in normalized_text.split('\n'):
                line_lower = line.lower().strip()
                if not line_lower or len(line_lower) < 10:
                    continue
                
                date_match = re.search(
                    r'(\d{1,2})/(\d{4})\s*–\s*(?:(\d{1,2})/(\d{4})|(present|current|now))',
                    line, re.IGNORECASE
                )
                if not date_match:
                    continue
                
                description = line[:60].strip() + ('...' if len(line) > 60 else '')
                
                # Skip education
                is_education = any(edu in line_lower for edu in education_keywords)
                if is_education:
                    skipped_roles.append(f"EDUCATION: {description}")
                    continue
                
                # Skip service
                is_service = any(svc in line_lower for svc in academic_service)
                has_job_title = any(job in line_lower for job in job_titles)
                has_present = bool(date_match.group(5))
                
                if is_service and not has_job_title:
                    skipped_roles.append(f"SERVICE: {description}")
                    continue
                
                # Skip courses (but not teaching)
                is_course = any(ctx in line_lower for ctx in course_indicators)
                is_teaching = any(t in line_lower for t in teaching_indicators)
                
                if is_course and not is_teaching:
                    skipped_roles.append(f"COURSE: {description}")
                    continue
                
                # Accept if job title OR present
                if has_job_title or has_present:
                    start_month, start_year = int(date_match.group(1)), int(date_match.group(2))
                    if date_match.group(5):
                        end_year, end_month = current_year, current_month
                    else:
                        end_month, end_year = int(date_match.group(3)), int(date_match.group(4))
                    
                    if 1980 <= start_year <= current_year and start_year <= end_year:
                        # Convert to total months (no floating point)
                        start_months = start_year * 12 + (start_month - 1)
                        end_months = end_year * 12 + (end_month - 1)
                        
                        # Sanity check: max 30 years per role
                        if (end_months - start_months) <= 360:
                            all_dates.append((start_months, end_months))
                            counted_roles.append(f"{start_year}-{end_year}: {description}")
                else:
                    skipped_roles.append(f"NO TITLE: {description}")
        
        # Log what was counted/skipped
        if counted_roles:
            print(f"   COUNTED: {len(counted_roles)} roles")
            for role in counted_roles[:3]:
                print(f"      ✓ {role}")
        if skipped_roles:
            print(f"   SKIPPED: {len(skipped_roles)} non-employment items")
            for role in skipped_roles[:3]:
                print(f"      ✗ {role}")
        
        # ============================================================
        # STEP 4: Merge and calculate using MONTHS (no floating point drift)
        # ============================================================
        if all_dates:
            unique_dates = list(set(all_dates))
            intervals = sorted(unique_dates, key=lambda x: x[0])
            
            # CV-type-aware merge tolerance (in months)
            # Academic: 0 months (roles often overlap)
            # Industry: 6 months (gaps between jobs)
            merge_tolerance = 0 if is_academic else 6
            
            merged = []
            for start, end in intervals:
                if not merged or start > merged[-1][1] + merge_tolerance:
                    merged.append([start, end])
                else:
                    merged[-1][1] = max(merged[-1][1], end)
            
            # Calculate total months, then convert to years
            total_months = sum(end - start for start, end in merged)
            calculated_years = min(total_months // 12, 50)  # Integer division - no drift
            
            # BOUNDED TRUST: If explicit claim exists, allow +1 year generosity max
            if explicit_years_claim is not None:
                result = min(calculated_years + 1, explicit_years_claim)
                print(f"   Years (calculated: {calculated_years}, claimed: {explicit_years_claim}): {result}")
            else:
                result = calculated_years
                print(f"   Years (from {len(merged)} employment periods): {result}")
            
            # INVARIANT ASSERTION
            assert 0 <= result <= 50, f"Experience years out of bounds: {result}"
            
            return result
        
        # If no dates found but explicit claim exists, use it with cap
        if explicit_years_claim is not None:
            result = min(explicit_years_claim, 20)  # Cap at 20 if no timeline
            print(f"   Years (explicit claim only, capped): {result}")
            return result
        
        print(f"   Years: 0 (no experience found)")
        return 0
    
    def check_islamic_finance_exp(self, text):
        """Check for Islamic Finance experience"""
        keywords = ['sukuk', 'mudarabah', 'musharakah', 'sharia', 'takaful',
                    'islamic finance', 'islamic banking', 'ijara', 'murabaha']
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)
    
    def detect_skills_regex(self, text, normalized_text=None):
        """
        Detect skills using HYBRID approach:
        
        PASS 0 (NEW): List-based extraction from Skills section (highest trust)
        PASS 1: Regex patterns in Skills section
        PASS 2: Regex patterns in Employment section  
        PASS 3: Regex patterns in full CV (fallback)
        
        This captures delimiter-separated skills like:
        "JavaScript · React · Node.js · Go · C · HTML · CSS · SQL"
        """
        # Try to extract skills section first
        skill_section = self._extract_section(text, 'skills')
        employment_section = self._extract_section(text, 'employment')
        
        detected = []
        skill_sources = {}  # Track where each skill was found
        
        # ================================================================
        # PASS 0 (NEW): List-based skill extraction from Skills section
        # This catches delimiter-separated skills that regex misses
        # ================================================================
        if skill_section and len(skill_section.strip()) > 20:
            # Preprocess: Remove common section sub-headers
            processed_section = skill_section
            sub_headers = [
                r'FINANCIAL\s*&?\s*STRATEGIC\s*SKILLS?',
                r'COMPLIANCE\s*&?\s*RISK',
                r'TECHNICAL\s*SKILLS?',
                r'SOFT\s*SKILLS?',
                r'HARD\s*SKILLS?',
                r'KEY\s*COMPETENC',
                r'CORE\s*COMPETENC',
                r'PROFESSIONAL\s*SKILLS?',
                r'IT\s*SKILLS?',
                r'COMPUTER\s*SKILLS?',
                r'DIGITAL\s*COMPETENC',
            ]
            for header in sub_headers:
                processed_section = re.sub(header, ' ', processed_section, flags=re.IGNORECASE)
            
            # Normalize line breaks - join lines that were split mid-skill
            processed_section = re.sub(r'\s*\n\s*', ' ', processed_section)
            processed_section = re.sub(r'  +', ' ', processed_section)
            
            # Split on middle dot (·) - primary Europass/modern CV delimiter
            raw_tokens = re.split(r'\s*[·•]\s*', processed_section)
            
            for skill_token in raw_tokens:
                skill_token = skill_token.strip()
                
                # Clean up common prefixes/suffixes
                skill_token = re.sub(r'^[-–—]\s*', '', skill_token)
                skill_token = re.sub(r'\s*[-–—]$', '', skill_token)
                
                # Valid skill: 1-50 chars
                if 1 <= len(skill_token) <= 50:
                    # Skip if ALL CAPS and long (likely a header that slipped through)
                    if skill_token.isupper() and len(skill_token) > 10:
                        continue
                    
                    # Skip generic single words that aren't skills
                    skip_words = ['skills', 'competencies', 'experience', 'summary',
                                  'education', 'languages', 'interests', 'references']
                    if skill_token.lower() in skip_words:
                        continue
                    
                    skill_lower = skill_token.lower()
                    if skill_lower not in skill_sources:
                        skill_sources[skill_lower] = {
                            'source': 'skills_section_list',
                            'weight': 1.0,
                            'frequency': 1,
                            'raw_name': skill_token  # Preserve original case
                        }
            
            if skill_sources:
                print(f"   📋 List extraction: {len(skill_sources)} potential skills from delimiters")
        
        # PASS 1: Check Skills section with regex (highest weight)
        if skill_section and len(skill_section.strip()) > 50:
            skill_section_lower = skill_section.lower()
            print(f"   📋 Skills section found ({len(skill_section)} chars)")
            
            # OPTIMIZATION: Use precompiled patterns
            for skill_name, compiled_pattern in COMPILED_RECALL_PATTERNS.items():
                if compiled_pattern.search(skill_section_lower):
                    skill_sources[skill_name] = {
                        'source': 'skills_section',
                        'weight': 1.0,
                        'frequency': len(compiled_pattern.findall(skill_section_lower))
                    }
        
        # PASS 2: Check Employment section (medium weight)
        if employment_section and len(employment_section.strip()) > 50:
            employment_lower = employment_section.lower()
            
            # OPTIMIZATION: Use precompiled patterns
            for skill_name, compiled_pattern in COMPILED_RECALL_PATTERNS.items():
                if skill_name not in skill_sources:  # Not already found in skills section
                    if compiled_pattern.search(employment_lower):
                        skill_sources[skill_name] = {
                            'source': 'employment_section',
                            'weight': 0.7,
                            'frequency': len(compiled_pattern.findall(employment_lower))
                        }
                else:
                    # Also in employment - boost frequency
                    additional = len(compiled_pattern.findall(employment_lower))
                    skill_sources[skill_name]['frequency'] += additional
        
        # PASS 3: Check full CV for remaining skills (lowest weight)
        text_lower = text.lower()
        # OPTIMIZATION: Use precompiled patterns
        for skill_name, compiled_pattern in COMPILED_RECALL_PATTERNS.items():
            if skill_name not in skill_sources:
                if compiled_pattern.search(text_lower):
                    skill_sources[skill_name] = {
                        'source': 'inline',
                        'weight': 0.3,
                        'frequency': len(compiled_pattern.findall(text_lower))
                    }
        
        # ================================================================
        # PASS 4 (NEW): Scan CV for ALL skills in our custom library
        # This catches skills that regex patterns miss (1700+ skills)
        # ================================================================
        library_skills = detect_skills_from_library(text)
        for lib_skill in library_skills:
            skill_lower = lib_skill['canonical'].lower()
            if skill_lower not in skill_sources:
                skill_sources[skill_lower] = {
                    'source': 'library_scan',
                    'weight': 0.8,
                    'frequency': 1,
                    'raw_name': lib_skill['canonical'],
                    'category': lib_skill.get('category')
                }
        
        if library_skills:
            print(f"   📚 Library scan: {len(library_skills)} additional skills found")
        
        # Build detected list with source info
        for skill_name, source_info in skill_sources.items():
            # Use preserved raw_name if available (from list extraction), else use skill_name
            raw_name = source_info.get('raw_name', skill_name)
            detected.append({
                'raw_name': raw_name,
                'source': source_info['source'],
                'source_weight': source_info['weight'],
                'frequency': source_info['frequency']
            })
        
        return detected
    
    def validate_and_classify_skills(self, detected_skills, candidate_field='technology'):
        """
        Validate skills with PRODUCTION-GRADE signal prioritization
        
        STEP 1: Source weighting (skills section > employment > inline)
        STEP 2: Experience anchoring (hard skills need job context)
        STEP 3: Frequency thresholds (repetition = stronger signal)
        STEP 4: Separate display vs scoring skills
        STEP 5: Soft penalty for field-irrelevant hard skills (not hard block)
        """
        validated = []
        unvalidated = []
        filtered_out = []
        
        # ============================================================
        # GARBAGE FILTER - catches raw CV text chunks before ESCO
        # Enhanced with ML classifier for 95.9% accuracy
        # ============================================================
        def is_garbage_skill(raw_name, section='unknown'):
            """Filter out obvious garbage before ESCO validation.
            
            Uses rule-based checks first, then ML classifier for final decision.
            """
            if not raw_name or len(raw_name) < 2:
                return True
            
            # Too long = likely a sentence fragment
            if len(raw_name) > 50:
                return True
            
            # Too many words = likely a phrase, not a skill
            word_count = len(raw_name.split())
            if word_count > 5:
                return True
            
            # Contains dates = CV text
            if re.search(r'\d{2}/\d{4}|\d{4}\s*[-–]\s*\d{4}', raw_name):
                return True
            
            # Contains money amounts = CV text
            if re.search(r'\$[\d,]+[MKB]?|\d+\s*million', raw_name, re.IGNORECASE):
                return True
            
            # Contains percentage = likely achievement text
            if re.search(r'\d+%', raw_name):
                return True
            
            # Contains company names / locations
            company_patterns = ['binance', 'manama', 'bahrain', 'globally', 'regional', 'national airline']
            if any(p in raw_name.lower() for p in company_patterns):
                return True
            
            # Contains job titles (as whole words)
            job_titles = [r'\bceo\b', r'\bcto\b', r'\bcfo\b', r'\bthe ceo\b', r'\bthe cto\b']
            if any(re.search(t, raw_name.lower()) for t in job_titles):
                return True
            
            # Sentence-like patterns (ends with period)
            if raw_name.endswith('.'):
                return True
            
            # Multiple capitalized words in a row suggesting Title Case sentence
            caps_words = re.findall(r'\b[A-Z][a-z]+\b', raw_name)
            if len(caps_words) >= 4:
                return True
            
            # ============================================================
            # ML CLASSIFIER CHECK - Final filter using trained model
            # Rule-based checks passed, now use ML for borderline cases
            # ============================================================
            if ML_SKILL_CLASSIFIER_AVAILABLE:
                is_skill, confidence = ml_classify_skill(raw_name, section)
                if not is_skill and confidence < 0.01:
                    # ML confidently says it's NOT a skill
                    return True
            
            return False
        
        for skill in detected_skills:
            raw_name = skill.get('raw_name', '')
            source = skill.get('source', 'inline')
            
            # ============================================================
            # STEP 1: CHECK SKILL LIBRARY FIRST - Library skills are TRUSTED
            # The library is curated, so if it's there, skip garbage filtering
            # ============================================================
            lib_valid, lib_canonical, lib_category, lib_confidence = validate_skill_from_library(raw_name)
            
            # If it's in our library with high confidence, TRUST IT (skip garbage check)
            if lib_valid and lib_confidence >= 0.85:
                # Found in custom library - proceed directly to validation
                pass  # Skip garbage check for library skills
            else:
                # ============================================================
                # GARBAGE CHECK - Only for skills NOT in our library
                # ============================================================
                if is_garbage_skill(raw_name, source):
                    filtered_out.append(f"Garbage: {raw_name[:30]}...")
                    continue
            
            # ============================================================
            # SKILL VALIDATION - Use library result or fall back to ESCO
            # Custom library has 1,726 curated skills - more accurate!
            # ============================================================
            
            if lib_valid and lib_confidence >= 0.85:
                # Found in custom library with high confidence - use it!
                is_valid = True
                canonical = lib_canonical
                skill_id = None  # No ESCO ID
                confidence = lib_confidence
                category = lib_category  # Use library category directly
                validation_source = 'library'
            else:
                # STEP 2: Fall back to ESCO
                is_valid, canonical, skill_id, confidence = self.esco.validate_skill(skill['raw_name'])
                validation_source = 'esco'
                
                # Check if ESCO gave us garbage (like "think quickly" for "React")
                if is_valid and canonical.lower() in ['think quickly', 'react calmly', 'show empathy']:
                    # ESCO mismatched - try to use raw name if it looks like a skill
                    if lib_valid:
                        canonical = lib_canonical
                        category = lib_category
                        confidence = lib_confidence
                        validation_source = 'library_override'
                    else:
                        # Skip this garbage mapping
                        filtered_out.append(f"ESCO Garbage: {skill['raw_name']} -> {canonical}")
                        continue
                
                # Determine category for ESCO results
                if validation_source == 'esco':
                    name_lower = canonical.lower()
                    if any(kw in name_lower for kw in ['sukuk', 'mudarab', 'sharia', 'takaful', 'islamic', 'ijara']):
                        category = 'islamic_finance'
                    elif any(kw in name_lower for kw in ['financ', 'account', 'valuation', 'bloomberg', 'audit']):
                        category = 'finance'
                    elif any(kw in name_lower for kw in ['communication', 'leadership', 'teamwork', 'presentation', 'lead others']):
                        category = 'soft_skill'
                    else:
                        category = 'technical'
            
            # Get source info
            source = skill.get('source', 'inline')
            source_weight = skill.get('source_weight', 0.3)
            frequency = skill.get('frequency', 1)
            
            # Skip if not valid from either source
            if not is_valid:
                unvalidated.append(skill)
                continue
            
            # LAYER 1: Domain filtering - hard block irrelevant noise
            if not is_relevant_skill(canonical):
                filtered_out.append(f"Domain: {canonical}")
                continue
            
            # Additional check for behavioral ESCO noise
            canonical_lower = canonical.lower()
            if any(phrase in canonical_lower for phrase in [
                'react calmly', 'stressful situations', 'adverse reactions',
                'anaesthesia', 'anesthesia', 'medical emergency',
                'manage adverse', 'patient', 'therapy'
            ]):
                filtered_out.append(f"Behavioral: {canonical}")
                continue
            
            is_hard_skill = category not in ['soft_skill', 'soft_skills']
            
            # STEP 5: Field filtering - SOFT PENALTY for all (not hard block)
            # This prevents Finance candidates from losing legitimate analytics skills
            field_allowed = is_skill_allowed_for_field(canonical, candidate_field)
            
            if not field_allowed:
                # SOFT PENALTY instead of hard block
                confidence *= 0.4
            
            # STEP 2: Experience anchoring for hard skills
            # Hard skills from inline text (not skills/employment section) get penalty
            if is_hard_skill and source == 'inline':
                confidence *= 0.6  # Lighter penalty
            
            # STEP 3: Frequency bonus
            if frequency >= 3:
                confidence = min(1.0, confidence * 1.2)
            elif frequency >= 2:
                confidence = min(1.0, confidence * 1.1)
            
            # STEP 1: Apply source weight to final confidence
            # But don't penalize too heavily - skills section should boost, not inline penalize
            if source == 'skills_section':
                final_confidence = confidence * 1.0  # Full confidence
            elif source == 'employment_section':
                final_confidence = confidence * 0.85  # Slight reduction
            else:
                final_confidence = confidence * 0.7  # Moderate reduction
            
            # ACADEMIC CONFIDENCE FLOOR + CAP
            # Academics list tools once - presence matters more than repetition
            # But don't overweight - cap at 0.7 to prevent sparse CV inflation
            if candidate_field == 'academic' and is_hard_skill:
                final_confidence = min(0.7, max(final_confidence, 0.4))
            
            # STEP 4: Determine if skill is "scorable" vs just "displayable"
            is_scorable = final_confidence >= 0.25  # Lowered threshold
            
            skill_data = {
                'canonical_name': canonical,
                'raw_name': skill['raw_name'],
                'esco_id': skill_id,
                'category': category,
                'is_hard_skill': is_hard_skill,
                'confidence': final_confidence,
                'validated': is_valid,
                'source': source,
                'source_weight': source_weight,
                'frequency': frequency,
                'field_relevant': field_allowed,
                'is_scorable': is_scorable
            }
            
            if is_valid:
                validated.append(skill_data)
            else:
                unvalidated.append(skill_data)
        
        if filtered_out:
            unique_filtered = list(dict.fromkeys(filtered_out))[:5]
            print(f"   🚫 Filtered: {', '.join(unique_filtered)}{'...' if len(filtered_out) > 5 else ''}")
        
        # Deduplicate validated skills by canonical name
        # Also merge similar skills (e.g., "cybersecurity" and "cyber security")
        
        # Define skill equivalence groups (first one is the canonical form to keep)
        SKILL_EQUIVALENCES = {
            # Cybersecurity variants
            'cybersecurity': ['cyber security', 'cyber-security', 'information security', 'infosec'],
            'machine learning': ['ml', 'machinelearning'],
            'artificial intelligence': ['ai', 'a.i.', 'a.i'],
            'deep learning': ['dl', 'deeplearning'],
            'natural language processing': ['nlp', 'natural language'],
            'data science': ['datascience', 'data-science'],
            'project management': ['projectmanagement', 'project-management'],
            'microsoft office': ['microsoft office suite', 'ms office', 'office suite', 'ms office suite'],
            'microsoft excel': ['ms excel', 'excel'],
            'microsoft word': ['ms word', 'word'],
            'microsoft powerpoint': ['ms powerpoint', 'powerpoint', 'ppt'],
            'power bi': ['powerbi', 'power-bi'],
            'react': ['react.js', 'reactjs'],
            'node.js': ['nodejs', 'node'],
            'vue.js': ['vuejs', 'vue'],
            'angular': ['angularjs', 'angular.js'],
            'next.js': ['nextjs', 'next'],
            'javascript': ['js', 'java script'],
            'typescript': ['ts'],
            'python': ['python3', 'python 3'],
            'golang': ['go lang', 'go-lang'],
            'c++': ['cpp', 'c/c++', 'cplusplus'],
            'postgresql': ['postgres', 'psql'],
            'mongodb': ['mongo', 'mongo db'],
            'restful': ['rest api', 'rest apis', 'restful api', 'restful apis'],
        }
        
        # Build reverse lookup: variant -> canonical
        variant_to_canonical = {}
        for canonical, variants in SKILL_EQUIVALENCES.items():
            variant_to_canonical[canonical.lower()] = canonical.lower()
            for variant in variants:
                variant_to_canonical[variant.lower()] = canonical.lower()
        
        seen_names = set()
        deduplicated = []
        
        # FINAL CONTEXT FILTER for ambiguous short skills
        # These require explicit context in the CV to be valid
        AMBIGUOUS_SKILLS_CONTEXT = {
            'icu': ['intensive care', 'icu nursing', 'icu unit', 'icu patient', 'critical care'],
            'lan': ['local area network', 'lan network', 'wlan', 'lan/wan', 'lan topology', 'ethernet lan'],
            'sem': ['search engine marketing', 'structural equation', 'sem campaign', 'sem strategy', 'scanning electron'],
            'erp': ['enterprise resource planning', 'erp system', 'sap erp', 'oracle erp'],
        }
        
        # Get the full CV text for context checking (from the first skill's source if available)
        cv_text_lower = ""
        if hasattr(self, '_current_cv_text'):
            cv_text_lower = self._current_cv_text.lower()
        
        for skill in validated:
            name_lower = skill['canonical_name'].lower()
            
            # Check if this is an ambiguous skill that needs context validation
            if name_lower in AMBIGUOUS_SKILLS_CONTEXT:
                required_contexts = AMBIGUOUS_SKILLS_CONTEXT[name_lower]
                has_context = any(ctx in cv_text_lower for ctx in required_contexts)
                if not has_context:
                    # Skip this skill - no proper context found
                    filtered_out.append(f"No context: {skill['canonical_name']}")
                    continue
            
            # Check if this is a variant of something already seen
            normalized_name = variant_to_canonical.get(name_lower, name_lower)
            
            if normalized_name not in seen_names:
                seen_names.add(normalized_name)
                # Also mark all variants as seen
                if normalized_name in SKILL_EQUIVALENCES:
                    for variant in SKILL_EQUIVALENCES[normalized_name]:
                        seen_names.add(variant.lower())
                deduplicated.append(skill)
        
        return deduplicated, unvalidated
    
    # ============================================================
    # SCORING
    # ============================================================
    
    def calculate_education_score(self, edu_data):
        rank = edu_data.get('highest_rank', -1)
        
        if rank == 3:
            score = 100
        elif rank == 2:
            score = 85
        elif rank == 1:
            score = 70
        elif rank == 0:
            score = 50
        else:
            score = 30
        
        if edu_data.get('has_islamic_finance_cert'):
            score = min(100, score + 15)
        
        return score
    
    def calculate_experience_score(self, years, has_if_exp=False):
        if years >= 15:
            score = 100
        elif years >= 10:
            score = 90
        elif years >= 7:
            score = 80
        elif years >= 5:
            score = 70
        elif years >= 3:
            score = 60
        elif years >= 1:
            score = 45
        else:
            score = 25
        
        if has_if_exp:
            score = min(100, score + 10)
        
        return score
    
    def calculate_skills_score(self, validated_skills, hard_weight=0.7, soft_weight=0.3):
        """
        Calculate skills score using ONLY scorable skills (STEP 4)
        
        Scorable = high-confidence, role-anchored skills
        Display = all validated ESCO skills (for UI)
        
        # NOTE:
        # Thresholds calibrated against confidence-weighted sums (0.4–1.0 per skill)
        # DO NOT convert back to raw counts — this prevents skill inflation
        # These values are FROZEN after production testing on 4 CVs
        """
        if not validated_skills:
            return 0
        
        # STEP 4: Only use scorable skills for scoring
        scorable_skills = [s for s in validated_skills if s.get('is_scorable', True)]
        
        if not scorable_skills:
            return 0
        
        hard = [s for s in scorable_skills if s['is_hard_skill']]
        soft = [s for s in scorable_skills if not s['is_hard_skill']]
        
        # Use confidence-weighted sum
        hard_weighted = sum(s['confidence'] for s in hard)
        soft_weighted = sum(s['confidence'] for s in soft)
        
        # INVARIANT ASSERTION - catch drift
        assert hard_weighted <= len(hard) * 1.0 + 0.1, f"Hard weighted sum invalid: {hard_weighted}"
        
        # ADJUSTED THRESHOLDS for confidence-weighted sums (FROZEN)
        if hard_weighted >= 5.5:
            hard_score = 100
        elif hard_weighted >= 4.0:
            hard_score = 85
        elif hard_weighted >= 2.5:
            hard_score = 70
        elif hard_weighted >= 1.5:
            hard_score = 55
        elif hard_weighted >= 0.8:
            hard_score = 40
        else:
            hard_score = hard_weighted * 40
        
        if soft_weighted >= 2.0:
            soft_score = 100
        elif soft_weighted >= 1.0:
            soft_score = 70
        else:
            soft_score = soft_weighted * 50
        
        return min(100, round((hard_score * hard_weight) + (soft_score * soft_weight), 1))
    
    def calculate_islamic_finance_score(self, edu_data, has_if_exp, validated_skills):
        score = 0
        
        if edu_data.get('has_islamic_finance_cert'):
            score += 40
        if has_if_exp:
            score += 35
        
        if_skills = [s for s in validated_skills if s['category'] == 'islamic_finance']
        if len(if_skills) >= 3:
            score += 25
        elif len(if_skills) >= 1:
            score += 15
        
        return min(100, score)


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_or_create_skill_definition(skill_data):
    """Get or create a SkillDefinition from skill data"""
    cat_obj, _ = SkillCategory.objects.get_or_create(name=skill_data['category'])
    
    skill_def, _ = SkillDefinition.objects.get_or_create(
        canonical_name=skill_data['canonical_name'],
        defaults={
            'category': cat_obj,
            'is_hard_skill': skill_data['is_hard_skill'],
            'importance_weight': 1.0
        }
    )
    return skill_def


# ============================================================
# MAIN ANALYSIS FUNCTION
# ============================================================
def analyze_resume(candidate, job_posting=None, use_ml=True):
    """Main analysis function - HYBRID VERSION (OPTIMIZED)"""
    start_time = time.time()  # OPTIMIZATION 5: Performance timing
    
    analyzer = ResumeAnalyzer()
    
    print(f"\n{'='*60}")
    print(f"ANALYZING: {candidate.name}")
    print(f"{'='*60}\n")
    
    if not hasattr(candidate, 'resume'):
        print("❌ No resume found")
        return None
    
    text = candidate.resume.parsed_text
    if not text:
        print("❌ No parsed text")
        return None
    
    # CRITICAL: Normalize text to fix HTML entities and OCR issues
    # This converts &amp; -> &, fixes spacing issues, etc.
    text = normalize_cv_text(text)
    
    # Contact
    print("📞 Contact...")
    contact = analyzer.extract_contact_info(text)
    print(f"   Email: {contact['email'] or 'Not found'}")
    print(f"   Phone: {contact['phone'] or 'Not found'}")
    
    if contact['email'] and not candidate.email:
        candidate.email = contact['email']
    if contact['phone'] and not candidate.phone:
        candidate.phone = contact['phone']
    
    # Education
    print("📚 Education...")
    edu_data = analyzer.extract_education(text)
    
    for deg in edu_data['degrees'][:3]:
        print(f"   ✓ {deg['degree']}", end='')
        if deg['field_of_study']:
            print(f" in {deg['field_of_study']}", end='')
        if deg['institution']:
            print(f" from {deg['institution']}", end='')
        print()
    
    # Experience
    print("💼 Experience...")
    years_exp = analyzer.extract_experience(text)
    has_if_exp = analyzer.check_islamic_finance_exp(text)
    print(f"   Years: {years_exp}")
    print(f"   Islamic Finance exp: {'Yes' if has_if_exp else 'No'}")
    
    # Detect candidate field
    candidate_field = detect_candidate_field(text, edu_data)
    analyzer.candidate_field = candidate_field
    print(f"\n🎯 Detected Field: {candidate_field.upper()}")
    
    # Skills
    print("🔧 Skills...")
    detected = analyzer.detect_skills_regex(text)
    print(f"   Detected (regex): {len(detected)}")
    
    # Store CV text for context-sensitive skill filtering
    analyzer._current_cv_text = text
    
    validated, unvalidated = analyzer.validate_and_classify_skills(detected, candidate_field)
    print(f"   ✅ Validated & domain-filtered: {len(validated)}")
    print(f"   ⚠️ Unvalidated: {len(unvalidated)}")
    
    if validated:
        val_names = [s['canonical_name'] for s in validated[:8]]
        print(f"   Top skills: {', '.join(val_names)}...")
    
    # Scoring
    if job_posting:
        edu_w = job_posting.education_weight
        exp_w = job_posting.experience_weight
        skill_w = job_posting.skills_weight
        if_w = getattr(job_posting, 'islamic_finance_weight', 0.20)
        hard_w = job_posting.hard_skills_weight
        soft_w = job_posting.soft_skills_weight
        print(f"\n⚙️ Using job posting weights")
    else:
        edu_w, exp_w, skill_w, if_w = 0.25, 0.30, 0.25, 0.20
        hard_w, soft_w = 0.70, 0.30
        print(f"\n⚙️ Using default weights")
    
    edu_score = analyzer.calculate_education_score(edu_data)
    exp_score = analyzer.calculate_experience_score(years_exp, has_if_exp)
    skills_score = analyzer.calculate_skills_score(validated, hard_w, soft_w)
    if_score = analyzer.calculate_islamic_finance_score(edu_data, has_if_exp, validated)
    
    total = round(
        (edu_score * edu_w) +
        (exp_score * exp_w) +
        (skills_score * skill_w) +
        (if_score * if_w), 1
    )
    
    print(f"\n🎯 SCORES:")
    print(f"   Education:       {edu_score}/100")
    print(f"   Experience:      {exp_score}/100")
    print(f"   Skills:          {skills_score}/100")
    print(f"   Islamic Finance: {if_score}/100")
    print(f"   ─────────────────────────")
    print(f"   TOTAL:           {total}/100")
    
    # ML Enhancement
    if use_ml and ML_AVAILABLE:
        try:
            if ml_enhancer.is_trained:
                total = round(ml_enhancer.get_enhanced_score(candidate, total), 1)
                print(f"   ML Enhanced:     {total}/100")
        except:
            pass
    
    # Save
    print(f"\n💾 Saving...")
    
    candidate.years_experience = years_exp
    candidate.save()
    
    # Save education
    Education.objects.filter(candidate=candidate).delete()
    
    for deg in edu_data['degrees']:
        if deg['degree'] != 'Unknown':
            Education.objects.create(
                candidate=candidate,
                degree=deg['degree'],
                institution=deg['institution'] or 'Not specified',
                field_of_study=deg['field_of_study'] or 'Not specified',
                graduation_year=deg['graduation_year'],
                has_islamic_finance_cert=edu_data.get('has_islamic_finance_cert', False),
                certification_names=edu_data.get('certification_names')
            )
    
    # Save validated skills
    # CRITICAL: Delete old skills first to remove garbage from previous analyses
    ExtractedSkill.objects.filter(candidate=candidate).delete()
    
    saved_count = 0
    
    for skill in validated:
        try:
            skill_def = get_or_create_skill_definition(skill)
            ExtractedSkill.objects.update_or_create(
                candidate=candidate,
                skill=skill_def,
                defaults={
                    'source_section': 'skills_list',
                    'frequency': 1,
                    'confidence_score': skill['confidence'],
                    'matched_via': skill['source']
                }
            )
            saved_count += 1
        except Exception as e:
            print(f"   ⚠️ Failed: {skill['canonical_name']}: {e}")
    
    print(f"   Saved {saved_count} validated skills")
    
    # Save score
    Score.objects.update_or_create(
        candidate=candidate,
        defaults={
            'education_score': edu_score,
            'experience_score': exp_score,
            'skills_score': skills_score,
            'islamic_finance_score': if_score,
            'total_score': total
        }
    )
    
    # OPTIMIZATION 5: Show processing time
    elapsed = time.time() - start_time
    print(f"\n✅ Complete in {elapsed:.2f} seconds!")
    print(f"{'='*60}\n")
    
    return {
        'education_score': edu_score,
        'experience_score': exp_score,
        'skills_score': skills_score,
        'islamic_finance_score': if_score,
        'total_score': total,
        'years_experience': years_exp,
        'validated_skills': len(validated),
        'skills_saved': saved_count,
        'is_academic_cv': analyzer.is_academic_cv,
        'candidate_field': candidate_field,
        'processing_time': round(elapsed, 2),  # Include timing in return
    }