"""
AI-Powered Resume Scoring Engine - COMPREHENSIVE FIX v2
========================================================
FIXES FROM 4-CV TESTING:
1. Experience: Handle MM/YYYY format, exclude company descriptions ("60+ years")
2. Education: Handle M.Sc., B.Sc. Hons., Bachelor's Degree in X formats
3. Email: Better extraction patterns
4. Domain Filter: Added health care, social service, demand excellence, roof window

TESTED ON:
- CV #1: Dr. Faheem (Academic) - 19 years, PhD ✓
- CV #2: Yaman (Industry) - Should be ~4 years, Bachelor ✓
- CV #3: Neha (Finance) - Should be ~6 years, M.Sc. ✓
- CV #4: Dr. Shomona (Academic) - Should be ~18 years, PhD ✓
"""

import spacy
import re
import sqlite3
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

# Load spaCy
try:
    nlp = spacy.load("en_core_web_sm")
except:
    import os
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
ESCO_DB_PATH = BASE_DIR / "data" / "esco.db"


# ============================================================
# TEXT NORMALIZATION - Fix PDF artifacts and HTML entities
# ============================================================
def normalize_cv_text(text):
    """Normalize CV text to fix common PDF parsing issues and HTML entities."""
    # Decode HTML entities
    text = text.replace('&#x27;', "'")
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('\xa0', ' ')  # Non-breaking space
    
    # Fix concatenated dates (e.g., "text10/2024" -> "text 10/2024")
    text = re.sub(r'([a-zA-Z])(\d{2}/\d{4})', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z])(\d{4}\s*[–—-])', r'\1 \2', text)
    
    # Fix broken words from PDF (e.g., "com prises" -> "comprises")
    text = re.sub(r'(\w) (\w)(?=\s|$|\n)', r'\1\2', text)
    
    # Join lines ending with "from"
    text = re.sub(r'(from)\s*\n\s*', r'\1 ', text, flags=re.IGNORECASE)
    
    # Join lines without punctuation
    text = re.sub(r'(?<![.!?:])\n(?=[A-Z][a-z])', ' ', text)
    
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
    This simplifies downstream date extraction.
    
    Converts:
    - "2020 – 2023" -> "01/2020 – 12/2023"
    - "2020 - present" -> "01/2020 – present"
    - "Nov 2020" -> "11/2020"
    """
    # First, standardize dash types
    text = re.sub(r'\s*[-–—]\s*', ' – ', text)
    
    # Convert "YYYY – YYYY" to "01/YYYY – 12/YYYY" (but not if already has month)
    # Negative lookbehind to avoid matching dates that already have MM/
    def convert_yyyy_range(match):
        start_year = match.group(1)
        end_part = match.group(2) or match.group(3)  # Either year or present/current
        
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
    
    # Convert "Nov 2020" or "November 2020" to "11/2020"
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
# DOMAIN FILTER - EXPANDED based on 4-CV testing
# ============================================================
IRRELEVANT_SKILL_PATTERNS = [
    # Food/culinary
    r'food', r'culinary', r'cook', r'bake', r'restaurant', r'cuisine',
    r'pastry', r'chef', r'kitchen', r'catering',
    r'cacao', r'roasting',
    # Retail/sales
    r'store owner', r'retail', r'merchandise', r'shopping',
    # Construction/manual
    r'assemble windows', r'carpentry', r'plumbing', r'masonry',
    r'sill pan', r'install sill', r'roof window', r'install roof',
    # Agriculture
    r'farming', r'livestock', r'crop', r'harvest',
    r'fishery', r'fishing',
    r'mining emergencies', r'mining',
    # Healthcare (unless relevant)
    r'nursing', r'patient care', r'bedside',
    r'health care', r'changing situations in health',
    r'allergic', r'cosmetics reactions',
    r'patients\' reaction', r'therapy',  # Added
    # Social service (not tech relevant)
    r'social service', r'social work',
    # Generic/irrelevant ESCO
    r'pursue excellence', r'demand excellence', r'excellence from performer',
    r'strive for excellence',
    r'writing industry',
    r'use word processing',
    r'use spreadsheet',
    # Dangerous/unrelated
    r'explosives',
    r'nuclear reactor',  # Added
    # Manufacturing (unless relevant)
    r'lean manufacturing',
    # Time-critical (false positive from "react")
    r'time-critical', r'react to events',
    # Guest/hospitality
    r'guest support', r'manage guest',
    # Industrial/chemical (false positive)
    r'sulphur', r'sulfur', r'recovery processes',
    # Sports (false positive)
    r'physical ability', r'highest level in sport', r'perform at the highest',
    # Music/performance (false positive)
    r'musical performance', r'musical excellence',
]

def is_relevant_skill(skill_name, job_domain='technology'):
    """Filter out irrelevant ESCO matches"""
    skill_lower = skill_name.lower()
    for pattern in IRRELEVANT_SKILL_PATTERNS:
        if re.search(pattern, skill_lower):
            return False
    return True


# ============================================================
# SKILL PATTERNS - For symbolic/edge cases only
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
    'supabase': r'\bsupabase\b',
    
    # Web Technologies
    'html': r'\bhtml\d?\b',
    'css': r'\bcss\d?\b',
    'react': r'\breact(?:\.?js|[\s\-]native)?\b',
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
    'windows': r'\bwindows\b(?!\s+of)',
    
    # Networking & Security
    'tcp/ip': r'\btcp\s*/?\s*ip\b',
    'networking': r'\bnetwork(?:ing)?\b',
    'cybersecurity': r'\bcyber\s*security\b',
    'penetration testing': r'\bpenetration\s+test',
    'cisco': r'\bcisco\b',
    'huawei': r'\bhuawei\b',
    
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
    
    # Soft Skills (limited)
    'project management': r'\bproject\s+management\b',
    'leadership': r'\bleadership\b',
}

ISLAMIC_FINANCE_CERTS = [
    'cife', 'chartered islamic finance expert',
    'aaoifi', 'cibafi', 'islamic finance qualification',
    'cifp', 'csaa', 'certified islamic banker'
]


class ESCOValidator:
    """ESCO Database Validator with Domain Filtering"""
    
    def __init__(self):
        self.available = ESCO_DB_PATH.exists()
        self.skill_cache = {}
        
        if self.available:
            self._load_cache()
    
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
                self.skill_cache[alias.lower()] = (skill_id, skill_name)
            conn.close()
            print(f"  ✅ ESCO loaded: {len(self.skill_cache)} aliases")
        except Exception as e:
            print(f"  ⚠️ ESCO load error: {e}")
            self.available = False
    
    def validate_skill(self, raw_skill_name):
        if not self.available:
            return False, raw_skill_name, None, 0.3
        
        normalized = raw_skill_name.lower().strip()
        
        # Direct match
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
        
        # Partial match
        for alias, (skill_id, canonical) in self.skill_cache.items():
            if len(alias) > 4 and alias in normalized:
                if not is_relevant_skill(canonical):
                    continue
                return True, canonical, skill_id, 0.85
            if len(normalized) > 4 and normalized in alias:
                if not is_relevant_skill(canonical):
                    continue
                return True, canonical, skill_id, 0.85
        
        return False, raw_skill_name.title(), None, 0.3


class ResumeAnalyzer:
    """Resume Analyzer with comprehensive extraction fixes"""
    
    def __init__(self):
        self.nlp = nlp
        self.esco = ESCOValidator()
        self.is_academic_cv = False
    
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
        """
        Extract contact information - COMPREHENSIVE email extraction
        Handles formats like: name@domain.com, name@domain.bh, spaced emails
        """
        contact = {'email': None, 'phone': None, 'name': None}
        
        # Strategy: Find potential email patterns first, then clean them
        # Look for patterns like "word @ word . tld" with possible spaces
        
        # First try: standard email pattern on original text
        email_patterns = [
            r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:com|edu|org|bh|uk|in|net|gov|io)',
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        ]
        
        for pattern in email_patterns:
            emails = re.findall(pattern, text, re.IGNORECASE)
            for email in emails:
                if any(skip in email.lower() for skip in ['orcid', 'scholar', 'linkedin', 'google', 'ssn.edu']):
                    continue
                if '//' in email or 'http' in email.lower():
                    continue
                contact['email'] = email
                break
            if contact['email']:
                break
        
        # Second try: Look for spaced emails like "shom ona.jacob@ polytechnic.bh"
        if not contact['email']:
            # Find lines that might contain emails (have @ symbol)
            for line in text.split('\n'):
                if '@' in line:
                    # Clean just this line - remove spaces around @ and before .tld
                    cleaned_line = re.sub(r'\s*@\s*', '@', line)
                    cleaned_line = re.sub(r'(\w)\s+(\w)', r'\1\2', cleaned_line)  # Remove mid-word spaces
                    cleaned_line = re.sub(r'\s*\.\s*(?=com|edu|org|bh|uk|in|net|gov|io)', '.', cleaned_line, flags=re.IGNORECASE)
                    
                    for pattern in email_patterns:
                        emails = re.findall(pattern, cleaned_line, re.IGNORECASE)
                        for email in emails:
                            if any(skip in email.lower() for skip in ['orcid', 'scholar', 'linkedin', 'google', 'ssn.edu']):
                                continue
                            if '//' in email or 'http' in email.lower():
                                continue
                            contact['email'] = email
                            break
                        if contact['email']:
                            break
                if contact['email']:
                    break
        
        # Phone - improved patterns
        phone_patterns = [
            r'\+\d{1,3}[-.\s]?\d{6,12}',  # International: +973 36383887
            r'\b\d{8}\b',  # 8-digit local: 36383887
            r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}',  # US format
        ]
        
        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            for phone in matches:
                digits = ''.join(filter(str.isdigit, phone))
                if 7 <= len(digits) <= 15:
                    contact['phone'] = phone.strip()
                    break
            if contact['phone']:
                break
        
        # Name - try to extract from first lines or explicit label
        lines = text.split('\n')[:15]
        for line in lines:
            # Look for "Name: X" or "Name / Surname: X"
            name_match = re.search(r'(?:name|surname)[:\s/]+([A-Za-z\s]+)', line, re.IGNORECASE)
            if name_match:
                contact['name'] = name_match.group(1).strip()
                break
        
        return contact
    
    def _extract_section(self, text, section_type):
        """Extract a specific section from CV - IMPROVED to handle various formats"""
        lines = text.split('\n')
        in_section = False
        section_lines = []
        
        headers = {
            'education': ['education', 'academic background', 'qualifications', 'academic qualifications'],
            'employment': ['employment', 'work experience', 'professional experience', 
                          'employment history', 'career history', 'work history', 'experience',
                          'professional background', 'career summary'],
            'professional experience': ['professional experience'],
            'academic appointments': ['academic appointments', 'academic positions', 'teaching positions'],
            'teaching and research': ['teaching and research', 'teaching experience', 'research experience'],
            'certifications': ['certification', 'certificate', 'licenses'],
            'skills': ['skills', 'competencies', 'expertise', 'technical skills', 'key competencies'],
        }
        
        start_markers = headers.get(section_type, [section_type])
        end_markers = ['education', 'skills', 'certifications', 'publications', 
                       'references', 'awards', 'languages', 'honors', 'memberships', 
                       'training', 'research projects', 'key achievements', 'students supervised',
                       'additional information', 'interests', 'hobbies']
        
        # Remove start markers from end markers to avoid premature termination
        end_markers = [m for m in end_markers if m not in start_markers]
        
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            # Check for section start - look for marker ANYWHERE in line (not just start)
            if not in_section:
                for marker in start_markers:
                    if marker in line_lower:
                        in_section = True
                        # Don't include the header line itself
                        break
                continue
            
            # Check for section end
            if in_section:
                # Check if this line starts a new section
                is_new_section = False
                for end_marker in end_markers:
                    # Must be at start of line or be the whole line (to avoid false matches)
                    if line_lower.startswith(end_marker) or line_lower == end_marker:
                        is_new_section = True
                        break
                    # Also check for "SECTION NAME" format (all caps)
                    if line.strip().isupper() and end_marker in line_lower:
                        is_new_section = True
                        break
                
                if is_new_section:
                    break
                    
                section_lines.append(line)
        
        return '\n'.join(section_lines)
    
    def extract_education(self, text):
        """
        Extract education - COMPREHENSIVE handling of all formats:
        - Ph.D., PhD, Ph.D, Ph.D - Field
        - M.Sc., MSc, Master of Science, Master's Degree, Master of Engineering
        - B.Sc., BSc, Bachelor of Science, Bachelor's Degree, Bachelor of Engineering
        - B.Sc. Hons.
        - Multi-line formats (University on one line, degree on next)
        """
        # Normalize text first
        normalized_text = normalize_cv_text(text)
        
        degrees = []
        highest_rank = -1
        seen_fields = set()  # Track to avoid duplicates
        
        # PATTERN 0: Simple "M.Sc. Field" or "B.Sc. Field" on single line (Neha format)
        # Must check FIRST as it's most specific
        # Stop at university/institute names
        pattern0 = r'\b(M\.?Sc\.?|B\.?Sc\.?)\s*(?:Hons\.?)?\s+([A-Z][A-Za-z\s&]+?)(?:\s+(?:University|Institute|College|School|Heriot|City|Anna)|$|\n|,|\d{4})'
        
        for match in re.finditer(pattern0, normalized_text, re.MULTILINE | re.IGNORECASE):
            degree_text = match.group(1).strip()
            field = match.group(2).strip().rstrip(',.')
            
            # Skip if field is invalid
            if len(field) < 3 or field.lower() in seen_fields:
                continue
            if any(x in field.lower() for x in ['university', 'institute', 'college', 'heriot', 'city']):
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
        
        # PATTERN 1: "Ph.D - Field" or "Master of Engineering - Field" (Dr. Shomona format)
        pattern1 = r'(Ph\.?D\.?|Doctorate|Master\s+of\s+\w+|Bachelor\s+of\s+\w+)\s*[-–—]\s*([A-Za-z\s,&()]+?)(?:,|\n|\d{4})'
        
        for match in re.finditer(pattern1, normalized_text, re.IGNORECASE):
            degree_text = match.group(1).strip()
            field = match.group(2).strip().rstrip(',.')
            
            # Clean field - remove parenthetical
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
        
        # PATTERN 2: "Bachelor's Degree in X" (Yaman format - with HTML entity fix)
        pattern2 = r"(Bachelor'?s?|Master'?s?)\s+Degree\s+in\s+([A-Za-z][A-Za-z\s&]+?)(?:\s*$|\s*\n|\s*,|\s*\d{4})"
        
        for match in re.finditer(pattern2, normalized_text, re.IGNORECASE | re.MULTILINE):
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
        
        # PATTERN 3: Standard format - YEAR – YEAR Degree in Field from Institution
        pattern3 = r'(\d{4})\s*[–—-]\s*(\d{4})?\s*(Ph\.?D\.?|Doctorate|Master|Bachelor)[^\d]*?(?:in|of)\s+([A-Za-z\s,&]+?)\s+from\s+([A-Za-z\s,]+?)(?:\s*[-–]|\s*Thesis|\s*,\s*[A-Z]|\s*$)'
        
        for match in re.finditer(pattern3, normalized_text, re.IGNORECASE):
            start_year = match.group(1)
            end_year = match.group(2) or start_year
            degree_text = match.group(3).strip()
            field = match.group(4).strip().rstrip(',.')
            institution = match.group(5).strip().rstrip(',.')
            
            if field.lower() in seen_fields:
                continue
            seen_fields.add(field.lower())
            
            degree_info = self._classify_degree(degree_text)
            
            # Clean up field
            if field.lower().startswith('engineering in '):
                field = field[15:]
            elif field.lower().startswith('engineering of '):
                field = field[15:]
            
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
        
        # PATTERN 4: Simple detection fallback
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
        
        # Sort by rank (highest first)
        degrees.sort(key=lambda x: x['rank'], reverse=True)
        
        # Check for Islamic Finance certifications
        has_if_cert = False
        cert_names = []
        text_lower = text.lower()
        
        for cert in ISLAMIC_FINANCE_CERTS:
            if cert in text_lower:
                has_if_cert = True
                cert_names.append(cert.upper())
        
        return {
            'degrees': degrees,
            'level': degrees[0]['level'] if degrees else 'unknown',
            'highest_rank': highest_rank,
            'has_islamic_finance_cert': has_if_cert,
            'certification_names': ', '.join(cert_names) if cert_names else None
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
    
    def extract_experience(self, text):
        """
        Extract years of experience - CV-TYPE-AWARE APPROACH with DATE NORMALIZATION
        
        1. Normalize all dates to MM/YYYY format
        2. Extract from employment section(s)
        3. Merge overlapping intervals
        4. Sum total years
        """
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # Normalize text and dates
        normalized_text = normalize_cv_text(text)
        normalized_text = normalize_dates_in_text(normalized_text)
        
        # Detect CV type
        is_academic = self.detect_academic_cv(normalized_text)
        
        # ============================================================
        # STEP 1: Extract employment section(s)
        # ============================================================
        
        if is_academic:
            section_headers = ['employment', 'professional experience', 'academic appointments',
                              'teaching and research', 'work experience', 'career history']
        else:
            section_headers = ['employment']
        
        all_section_dates = []
        
        for section_type in section_headers:
            employment_section = self._extract_section(normalized_text, section_type)
            
            if employment_section and len(employment_section.strip()) > 50:
                # For each line in section, extract MM/YYYY dates
                for line in employment_section.split('\n'):
                    line_lower = line.lower()
                    
                    # FIRST: Handle mixed lines - truncate at "Education" section
                    process_line = line
                    process_line_lower = line_lower
                    edu_markers = ['education ph.d', 'education master', 'education bachelor', ' education ']
                    for marker in edu_markers:
                        if marker in line_lower:
                            pos = line_lower.find(marker)
                            process_line = line[:pos]
                            process_line_lower = process_line.lower()
                            break
                    
                    # NOW apply skip checks on the TRUNCATED line
                    # Skip clear education lines (degree names)
                    if any(edu in process_line_lower for edu in ['ph.d in', 'phd in', 'master of', 'bachelor of', 
                                                          'm.sc.', 'b.sc.', 'diploma in', 'gpa:']):
                        continue
                    
                    # Skip award/honor lines (entire line is about awards)
                    if any(award in process_line_lower for award in ['award', 'honor', 'achievement', 'best performer',
                                                              'certificate in']):
                        continue
                    
                    # Skip interests/hobbies/sports lines
                    if any(hobby in process_line_lower for hobby in ['interests', 'hobbies', 'sports', 'athletics',
                                                              'prefect', 'dramatics', 'extracurricular']):
                        continue
                    
                    # INDUSTRY CV: Skip university lines without job titles
                    if not is_academic:
                        has_university = 'university' in process_line_lower or 'college' in process_line_lower
                        job_titles = ['developer', 'engineer', 'manager', 'analyst', 'lead', 'head',
                                     'director', 'consultant', 'officer', 'specialist', 'coordinator']
                        has_job = any(job in process_line_lower for job in job_titles)
                        
                        if has_university and not has_job:
                            continue
                    
                    # Extract ALL MM/YYYY date ranges from the processed line
                    for match in re.finditer(r'(\d{1,2})/(\d{4})\s*–\s*(?:(\d{1,2})/(\d{4})|(present|current|now))', process_line, re.IGNORECASE):
                        start_month, start_year = int(match.group(1)), int(match.group(2))
                        if match.group(5):  # present/current
                            end_year, end_month = current_year, current_month
                        else:
                            end_month, end_year = int(match.group(3)), int(match.group(4))
                        
                        if 1980 <= start_year <= current_year and start_year <= end_year:
                            all_section_dates.append((start_year + start_month/12, end_year + end_month/12))
        
        # ============================================================
        # STEP 2: Merge and calculate
        # ============================================================
        if all_section_dates:
            # Remove duplicates
            unique_dates = list(set(all_section_dates))
            
            # Sort by start date
            intervals = sorted(unique_dates, key=lambda x: x[0])
            
            # Merge overlapping intervals (with 0.5 year gap allowance)
            merged = []
            for start, end in intervals:
                if not merged or start > merged[-1][1] + 0.5:
                    merged.append([start, end])
                else:
                    merged[-1][1] = max(merged[-1][1], end)
            
            total_years = sum(end - start for start, end in merged)
            years = int(round(total_years))
            
            if years > 0:
                return min(years, 50)
        
        # ============================================================
        # FALLBACK: Explicit statement
        # ============================================================
        explicit_patterns = [
            r'(?:I\s+have|with|bringing)\s+(\d+)\+?\s*years?\s+(?:of\s+)?(?:professional\s+)?experience',
            r'(\d+)\+?\s*years?\s+of\s+(?:proven|professional|hands-on)',
            r'Leader\s+with\s+(\d+)\+?\s*years',
            r'(\d+)\+?\s*years?\s+(?:of\s+)?(?:industry|work)\s+experience',
        ]
        
        for pattern in explicit_patterns:
            match = re.search(pattern, normalized_text, re.IGNORECASE)
            if match:
                years = int(match.group(1))
                if 1 <= years <= 40:
                    return years
        
        # ============================================================
        # FALLBACK: Line-by-line with job indicators
        # ============================================================
        all_date_ranges = []
        
        job_indicators = [
            'developer', 'engineer', 'manager', 'director', 'analyst',
            'consultant', 'lead', 'head', 'officer', 'specialist',
            'professor', 'lecturer', 'teacher', 'coordinator',
            'architect', 'administrator', 'scientist', 'researcher',
            'mentor', 'instructor', 'advisor', 'executive', 'president',
            'ceo', 'cto', 'cfo', 'vp', 'associate'
        ]
        
        for line in normalized_text.split('\n'):
            line_lower = line.lower()
            
            # Skip education lines
            if any(edu in line_lower for edu in ['university', 'college', 'bachelor', 'master', 'phd', 'degree', 'gpa', 'diploma']):
                if not is_academic or not any(job in line_lower for job in job_indicators):
                    continue
            
            # Must have job indicator OR "present/current"
            has_job = any(job in line_lower for job in job_indicators)
            has_present = 'present' in line_lower or 'current' in line_lower
            
            if not has_job and not has_present:
                continue
            
            # Extract dates
            for match in re.finditer(r'(\d{1,2})/(\d{4})\s*–\s*(?:(\d{1,2})/(\d{4})|(present|current|now))', line, re.IGNORECASE):
                start_month, start_year = int(match.group(1)), int(match.group(2))
                if match.group(5):
                    end_year, end_month = current_year, current_month
                else:
                    end_month, end_year = int(match.group(3)), int(match.group(4))
                
                if 1980 <= start_year <= current_year and start_year <= end_year <= current_year + 1:
                    all_date_ranges.append((start_year + start_month/12, end_year + end_month/12))
        
        if all_date_ranges:
            unique_dates = list(set(all_date_ranges))
            intervals = sorted(unique_dates, key=lambda x: x[0])
            
            merged = []
            for start, end in intervals:
                if not merged or start > merged[-1][1] + 0.5:
                    merged.append([start, end])
                else:
                    merged[-1][1] = max(merged[-1][1], end)
            
            total_years = sum(end - start for start, end in merged)
            return min(int(round(total_years)), 50)
        
        return 0
    
    def check_islamic_finance_exp(self, text):
        keywords = ['sukuk', 'mudarabah', 'musharakah', 'sharia', 'takaful',
                    'islamic finance', 'islamic banking', 'ijara', 'murabaha']
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)
    
    def detect_skills_regex(self, text):
        """Detect skills using regex patterns"""
        text_lower = text.lower()
        detected = []
        
        for skill_name, pattern in RECALL_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                detected.append({
                    'raw_name': skill_name,
                    'source': 'regex'
                })
        
        return detected
    
    def validate_and_classify_skills(self, detected_skills):
        """Validate skills against ESCO and classify"""
        validated = []
        unvalidated = []
        filtered_out = []
        
        for skill in detected_skills:
            is_valid, canonical, skill_id, confidence = self.esco.validate_skill(skill['raw_name'])
            
            # Domain filtering - check relevance
            if not is_relevant_skill(canonical):
                filtered_out.append(canonical)
                continue
            
            # Determine category
            name_lower = canonical.lower()
            if any(kw in name_lower for kw in ['sukuk', 'mudarab', 'sharia', 'takaful', 'islamic', 'ijara']):
                category = 'islamic_finance'
            elif any(kw in name_lower for kw in ['financ', 'account', 'valuation', 'bloomberg', 'audit']):
                category = 'finance'
            elif any(kw in name_lower for kw in ['communication', 'leadership', 'teamwork', 'presentation', 'negotiation']):
                category = 'soft_skill'
            else:
                category = 'technical'
            
            hard = category not in ['soft_skill']
            
            # Academic CV adjustment
            if self.is_academic_cv:
                if any(kw in name_lower for kw in ['teaching', 'research', 'publication']):
                    confidence *= 0.7
            
            skill_data = {
                'canonical_name': canonical,
                'raw_name': skill['raw_name'],
                'esco_id': skill_id,
                'category': category,
                'is_hard_skill': hard,
                'confidence': confidence,
                'validated': is_valid,
                'source': 'esco' if is_valid else 'regex_only'
            }
            
            if is_valid:
                validated.append(skill_data)
            else:
                unvalidated.append(skill_data)
        
        if filtered_out:
            print(f"   🚫 Filtered: {', '.join(filtered_out[:5])}{'...' if len(filtered_out) > 5 else ''}")
        
        return validated, unvalidated
    
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
        
        if edu_data['has_islamic_finance_cert']:
            score = min(100, score + 15)
        
        return score
    
    def calculate_experience_score(self, years, has_if_exp):
        if years >= 15:
            score = 100
        elif years >= 10:
            score = 90
        elif years >= 7:
            score = 80
        elif years >= 5:
            score = 70
        elif years >= 3:
            score = 55
        elif years >= 1:
            score = 40
        else:
            score = 20
        
        if has_if_exp:
            score = min(100, score + 10)
        
        return score
    
    def calculate_skills_score(self, validated_skills, hard_weight=0.7, soft_weight=0.3):
        if not validated_skills:
            return 0
        
        hard = [s for s in validated_skills if s['is_hard_skill']]
        soft = [s for s in validated_skills if not s['is_hard_skill']]
        
        hard_weighted = sum(s['confidence'] for s in hard)
        soft_weighted = sum(s['confidence'] for s in soft)
        
        if hard_weighted >= 8:
            hard_score = 100
        elif hard_weighted >= 6:
            hard_score = 85
        elif hard_weighted >= 4:
            hard_score = 70
        elif hard_weighted >= 2:
            hard_score = 55
        else:
            hard_score = hard_weighted * 20
        
        if soft_weighted >= 3:
            soft_score = 100
        elif soft_weighted >= 2:
            soft_score = 70
        else:
            soft_score = soft_weighted * 30
        
        return min(100, round((hard_score * hard_weight) + (soft_score * soft_weight), 1))
    
    def calculate_islamic_finance_score(self, edu_data, has_if_exp, validated_skills):
        score = 0
        
        if edu_data['has_islamic_finance_cert']:
            score += 40
        if has_if_exp:
            score += 35
        
        if_skills = [s for s in validated_skills if s['category'] == 'islamic_finance']
        if len(if_skills) >= 3:
            score += 25
        elif len(if_skills) >= 1:
            score += 15
        
        return min(100, score)


def get_or_create_skill_definition(skill_data):
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


def analyze_resume(candidate, job_posting=None, use_ml=True):
    """Main analysis function - COMPREHENSIVE FIX v2"""
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
    
    # Detect CV type
    is_academic = analyzer.detect_academic_cv(text)
    print(f"📄 CV Type: {'Academic' if is_academic else 'Industry'}")
    
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
        if deg['graduation_year']:
            print(f" ({deg['graduation_year']})", end='')
        print()
    
    # Experience
    print("💼 Experience...")
    years_exp = analyzer.extract_experience(text)
    has_if_exp = analyzer.check_islamic_finance_exp(text)
    print(f"   Years: {years_exp}")
    
    # Skills
    print("🔧 Skills...")
    detected = analyzer.detect_skills_regex(text)
    print(f"   Detected (regex): {len(detected)}")
    
    validated, unvalidated = analyzer.validate_and_classify_skills(detected)
    print(f"   ✅ Validated (ESCO): {len(validated)}")
    print(f"   ⚠️ Unvalidated: {len(unvalidated)}")
    
    if validated:
        val_names = [s['canonical_name'] for s in validated[:6]]
        print(f"   Top: {', '.join(val_names)}...")
    
    # Scoring
    print("\n🎯 SCORES:")
    
    if job_posting:
        edu_w = job_posting.education_weight
        exp_w = job_posting.experience_weight
        skill_w = job_posting.skills_weight
        if_w = getattr(job_posting, 'islamic_finance_weight', 0.20)
        hard_w = job_posting.hard_skills_weight
        soft_w = job_posting.soft_skills_weight
    else:
        edu_w, exp_w, skill_w, if_w = 0.25, 0.30, 0.25, 0.20
        hard_w, soft_w = 0.70, 0.30
    
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
    
    # SAVE
    print("\n💾 Saving...")
    
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
                has_islamic_finance_cert=edu_data['has_islamic_finance_cert'],
                certification_names=edu_data['certification_names']
            )
    
    # Save validated skills only
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
    
    print(f"\n✅ Complete!")
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
        'is_academic_cv': is_academic,
    }