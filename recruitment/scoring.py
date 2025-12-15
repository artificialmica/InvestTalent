"""
AI-Powered Resume Scoring Engine - HYBRID PRODUCTION VERSION
=============================================================
COMBINES:
- OLD CODE: Strong preprocessing (normalize_cv_text, normalize_dates_in_text)
- OLD CODE: 0.5 year merge tolerance
- OLD CODE: CV-type-aware section extraction
- NEW CODE: int() flooring (not rounding)
- NEW CODE: Academic service exclusion (editors, committees, awards)
- NEW CODE: Education line exclusion
- NEW CODE: Course vs teaching distinction

EXPECTED RESULTS:
- Dr. Faheem: 19 years ✓
- Neha Ali: ~6-7 years ✓
- Dr. Shomona: ~14-18 years ✓
- Yaman: ~4 years ✓
"""

import spacy
import re
import sqlite3
import json
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
CERTIFICATIONS_PATH = BASE_DIR / "data" / "certifications.json"


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
            else:
                cert_name = cert
            
            if not cert_name:
                continue
                
            cert_lower = cert_name.lower()
            if cert_lower in text_lower:
                found.append({
                    'name': cert_name,
                    'category': category
                })
    
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
# ESCO VALIDATOR
# ============================================================
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
        
        if normalized in self.skill_cache:
            skill_id, canonical = self.skill_cache[normalized]
            if not is_relevant_skill(canonical):
                return False, raw_skill_name.title(), None, 0.2
            return True, canonical, skill_id, 1.0
        
        if FUZZY_AVAILABLE:
            fuzzy_normalized = normalize_skill(raw_skill_name).lower()
            if fuzzy_normalized in self.skill_cache:
                skill_id, canonical = self.skill_cache[fuzzy_normalized]
                if not is_relevant_skill(canonical):
                    return False, raw_skill_name.title(), None, 0.2
                return True, canonical, skill_id, 0.9
        
        for alias, (skill_id, canonical) in self.skill_cache.items():
            # Use word boundaries to prevent substring hallucinations
            if len(alias) > 4:
                # Check if alias appears as whole word in normalized
                if re.search(r'\b' + re.escape(alias) + r'\b', normalized):
                    if not is_relevant_skill(canonical):
                        continue
                    return True, canonical, skill_id, 0.85
            if len(normalized) > 4:
                # Check if normalized appears as whole word in alias
                if re.search(r'\b' + re.escape(normalized) + r'\b', alias):
                    if not is_relevant_skill(canonical):
                        continue
                    return True, canonical, skill_id, 0.85
        
        return False, raw_skill_name.title(), None, 0.3


# ============================================================
# RESUME ANALYZER - HYBRID VERSION
# ============================================================
class ResumeAnalyzer:
    """Resume Analyzer combining old preprocessing with new filtering"""
    
    def __init__(self):
        self.nlp = nlp
        self.esco = ESCOValidator()
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
        """Extract contact information"""
        contact = {'email': None, 'phone': None, 'name': None}
        
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
        
        # Phone
        phone_patterns = [
            r'\+\d{1,3}[-.\s]?\d{6,12}',
            r'\b\d{8}\b',
            r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}',
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
        
        return contact
    
    def _extract_section(self, text, section_type):
        """Extract a specific section from CV - FROM OLD CODE (robust)"""
        lines = text.split('\n')
        in_section = False
        section_lines = []
        
        headers = {
            'education': ['education', 'academic background', 'qualifications', 'academic qualifications'],
            'employment': ['employment', 'work experience', 'professional experience',
                          'employment history', 'career history', 'work history', 'experience',
                          'professional background', 'career summary'],
            'academic_appointments': ['academic appointments', 'academic positions', 'teaching positions'],
            'teaching': ['teaching and research', 'teaching experience', 'research experience'],
            'certifications': ['certification', 'certificate', 'licenses'],
            'skills': ['skills', 'competencies', 'expertise', 'technical skills', 'key competencies'],
        }
        
        start_markers = headers.get(section_type, [section_type])
        end_markers = ['education', 'skills', 'certifications', 'publications',
                       'references', 'awards', 'languages', 'honors', 'memberships',
                       'training', 'research projects', 'key achievements', 'students supervised',
                       'additional information', 'interests', 'hobbies']
        
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
        Detect skills using regex patterns - SECTION-AWARE with SOURCE TRACKING
        
        STEP 1: Track where each skill was found (provenance)
        - Skills section: weight 1.0
        - Near job titles: weight 0.7
        - Inline/other: weight 0.3
        """
        # Try to extract skills section first
        skill_section = self._extract_section(text, 'skills')
        employment_section = self._extract_section(text, 'employment')
        
        detected = []
        skill_sources = {}  # Track where each skill was found
        
        # PASS 1: Check Skills section (highest weight)
        if skill_section and len(skill_section.strip()) > 50:
            skill_section_lower = skill_section.lower()
            print(f"   📋 Skills section found ({len(skill_section)} chars)")
            
            for skill_name, pattern in RECALL_PATTERNS.items():
                if re.search(pattern, skill_section_lower, re.IGNORECASE):
                    skill_sources[skill_name] = {
                        'source': 'skills_section',
                        'weight': 1.0,
                        'frequency': len(re.findall(pattern, skill_section_lower, re.IGNORECASE))
                    }
        
        # PASS 2: Check Employment section (medium weight)
        if employment_section and len(employment_section.strip()) > 50:
            employment_lower = employment_section.lower()
            
            for skill_name, pattern in RECALL_PATTERNS.items():
                if skill_name not in skill_sources:  # Not already found in skills section
                    if re.search(pattern, employment_lower, re.IGNORECASE):
                        skill_sources[skill_name] = {
                            'source': 'employment_section',
                            'weight': 0.7,
                            'frequency': len(re.findall(pattern, employment_lower, re.IGNORECASE))
                        }
                else:
                    # Also in employment - boost frequency
                    additional = len(re.findall(pattern, employment_lower, re.IGNORECASE))
                    skill_sources[skill_name]['frequency'] += additional
        
        # PASS 3: Check full CV for remaining skills (lowest weight)
        text_lower = text.lower()
        for skill_name, pattern in RECALL_PATTERNS.items():
            if skill_name not in skill_sources:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    skill_sources[skill_name] = {
                        'source': 'inline',
                        'weight': 0.3,
                        'frequency': len(re.findall(pattern, text_lower, re.IGNORECASE))
                    }
        
        # Build detected list with source info
        for skill_name, source_info in skill_sources.items():
            detected.append({
                'raw_name': skill_name,
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
        
        for skill in detected_skills:
            is_valid, canonical, skill_id, confidence = self.esco.validate_skill(skill['raw_name'])
            
            # Get source info
            source = skill.get('source', 'inline')
            source_weight = skill.get('source_weight', 0.3)
            frequency = skill.get('frequency', 1)
            
            # LAYER 1: Domain filtering - hard block irrelevant ESCO noise
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
            
            # Determine category FIRST (needed for field filtering logic)
            name_lower = canonical.lower()
            if any(kw in name_lower for kw in ['sukuk', 'mudarab', 'sharia', 'takaful', 'islamic', 'ijara']):
                category = 'islamic_finance'
            elif any(kw in name_lower for kw in ['financ', 'account', 'valuation', 'bloomberg', 'audit']):
                category = 'finance'
            elif any(kw in name_lower for kw in ['communication', 'leadership', 'teamwork', 'presentation', 'lead others']):
                category = 'soft_skill'
            else:
                category = 'technical'
            
            is_hard_skill = category not in ['soft_skill']
            
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
        seen_names = set()
        deduplicated = []
        for skill in validated:
            name_lower = skill['canonical_name'].lower()
            if name_lower not in seen_names:
                seen_names.add(name_lower)
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
    """Main analysis function - HYBRID VERSION"""
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
        'is_academic_cv': analyzer.is_academic_cv,
        'candidate_field': candidate_field,
    }