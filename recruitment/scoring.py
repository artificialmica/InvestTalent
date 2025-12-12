"""
AI-Powered Resume Scoring Engine - COMPREHENSIVE PRODUCTION VERSION
Multi-tier skill matching: Exact -> Fuzzy -> Semantic ML with REGEX patterns

ALL 12 CRITICAL FIXES APPLIED:
✅ FIX #1: Experience from Employment History only (not "X years" statements)
✅ FIX #2: Skills HARD STOP at Publications/References
✅ FIX #3: Publication vocabulary filter (DOI, ISSN, et al)
✅ FIX #4: Personal info filter (name, references, languages)
✅ FIX #5: PDF artifact cleaner (Javascr Ipt → Javascript)
✅ FIX #6: Simulator names filtered (OMNeT++, OPNET, Packet Tracer)
✅ FIX #7: OS names filtered (Windows, Linux, Mac OSX)
✅ FIX #8: Certificate codes filtered (77-727, H12-711)
✅ FIX #9: Education full field extraction
✅ FIX #10: Better deduplication
✅ FIX #11: Garbage phrases comprehensive filter
✅ FIX #12: CSV extraction with proper splitting
"""

import spacy
import re
from datetime import datetime
from collections import Counter
from .models import Candidate, Resume, Education, Experience, Skill, Score
from .fuzzy_matching import (
    normalize_skill, 
    is_hard_skill, 
    match_required_skills,
    match_skill_advanced
)

# Try to import ML enhancer
try:
    from .ml_scoring import ml_enhancer
    ML_AVAILABLE = True
except:
    ML_AVAILABLE = False
    print("ML scoring not available")

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    print("Downloading spaCy model...")
    import os
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# REGEX-BASED SKILL PATTERNS
SKILL_PATTERNS = {
    'python': r'\bpython\b',
    'java': r'\bjava\b',
    'javascript': r'\bjavascript\b|\bjs\b',
    'sql': r'\bsql\b',
    'mysql': r'\bmysql\b',
    'postgresql': r'\bpostgresql\b|\bpostgres\b',
    'excel': r'\bexcel\b',
    'machine learning': r'\bmachine\s+learning\b',
    'data analysis': r'\bdata\s+analys[ie]s\b',
    'data visualization': r'\bdata\s+visuali[sz]ation\b',
    'database management': r'\bdatabase\s+management\b',
    'financial modeling': r'\bfinancial\s+model(?:ing|ling)\b',
    'financial analysis': r'\bfinancial\s+analys[ie]s\b',
    'portfolio management': r'\bportfolio\s+management\b',
    'bloomberg terminal': r'\bbloomberg\b',
    'sukuk': r'\bsukuk\b',
    'mudarabah': r'\bmudarabah?\b',
    'sharia': r'\bsharia[h]?\b|\bislamic\s+finance\b',
    'takaful': r'\btakaful\b',
    'islamic banking': r'\bislamic\s+bank',
    'communication': r'\bcommunications?\b',
    'leadership': r'\bleadership\b',
    'teamwork': r'\bteamwork\b|\bteam\s+work\b',
    'problem solving': r'\bproblem.?solving\b',
    'golang': r'\bgolang\b',
    'go': r'\bgo\b',
    'react': r'\breact\b',
    'node.js': r'\bnode\.?js\b',
    'next.js': r'\bnext\.?js\b',
    'graphql': r'\bgraphql\b',
    'restful': r'\brestful\b|\brest\s+api\b',
}

TECHNICAL_SKILLS = ['python', 'java', 'javascript', 'sql', 'excel', 'machine learning', 'data analysis', 'data visualization', 'database management']

FINANCE_SKILLS = ['financial modeling', 'financial analysis', 'portfolio management', 'bloomberg terminal']

ISLAMIC_FINANCE_KEYWORDS = ['sukuk', 'mudarabah', 'sharia', 'takaful', 'islamic banking']

SOFT_SKILLS_LIST = ['communication', 'leadership', 'teamwork', 'problem solving']

# Comprehensive skill dictionaries
PROGRAMMING_KEYWORDS = [
    "python", "java", "c++", "c/c++", "php", "javascript", "html", "css",
    "sql", "mysql", "postgresql", "postgres", "matlab", "r", "latex", "c", "vba",
    "golang", "go", "rust", "swift", "kotlin", "typescript",
    "react", "node.js", "next.js", "flask", "fastapi", "django",
    "graphql", "restful", "rest api"
]

TECH_KEYWORDS = [
    "network security", "cybersecurity", "intrusion detection", "ids", 
    "penetration testing", "virtualization", "cloud computing", "tcp/ip",
    "wireless networks", "machine learning", "neural networks",
    "data analysis", "signal processing", "feature engineering",
    "artificial intelligence", "deep learning", "computer vision", "nlp"
]

NETWORKING_KEYWORDS = [
    "tcp/ip", "routing", "switching", "bgp", "ospf", 
    "optical networks", "wireless networks", "network simulation",
    "dns", "dhcp"
]

CYBERSECURITY_KEYWORDS = [
    "malware detection", "dhcp attacks", "nids", "threat hunting",
    "security analysis", "risk assessment", "cryptography",
    "intrusion detection system", "firewall configuration",
    "incident response"
]

ENGINEERING_KEYWORDS = [
    "signal processing", "energy efficiency", "adsl", 
    "telecommunication engineering", "electronics engineering",
    "protocol optimization", "rate adaptation"
]

SOFT_KEYWORDS = [
    "communication", "leadership", "teamwork", 
    "problem solving", "teaching", "supervision", "research"
]

DATABASE_KEYWORDS = [
    "sqlite", "postgres", "postgresql", "mongodb", "redis",
    "firebase", "supabase", "oracle", "cassandra", "dynamodb"
]

CLOUD_KEYWORDS = [
    "aws", "azure", "gcp", "docker", "kubernetes",
    "jenkins", "terraform", "ansible"
]

# FIX #6: Simulator names to COMPLETELY EXCLUDE
SIMULATOR_NAMES = [
    "omnet++", "opnet", "packet tracer", "routersim", "network visualizer",
    "netsim", "boson", "eve-ng", "semsim", "mathworks", "simulink",
    "multisim", "labview", "autocad", "octave"
]

# FIX #7: Operating system names to EXCLUDE
OS_NAMES = [
    "windows", "linux", "mac osx", "macos", "unix", "ubuntu",
    "cisco ios", "huawei vrp"
]

# Server/hosting names to FILTER OUT
SERVER_NAMES = [
    "apache", "nginx", "ngnix", "vercel", "netlify"
]

# Tool names to FILTER OUT
TOOL_NAMES = SIMULATOR_NAMES + OS_NAMES + SERVER_NAMES

# Islamic Finance Certifications
ISLAMIC_FINANCE_CERTS = [
    'cife', 'chartered islamic finance expert',
    'aaoifi', 'cibafi', 'islamic finance qualification',
    'cifp', 'cima', 'csaa'
]

# FIX #3: Publication vocabulary
PUBLICATION_KEYWORDS = [
    "journal", "issn", "doi", "proceedings", "conference",
    "et al", "pp.", "vol.", "published", "in:", "isbn",
    "publication", "article", "paper", "thesis", "dissertation"
]

# FIX #4: Personal info keywords
PERSONAL_INFO_KEYWORDS = [
    "references", "available on request", "mother tongue",
    "self-assessment", "european level", "proficient user",
    "basic user", "listening", "reading", "spoken interaction",
    "spoken production", "writing"
]

# Certificate keywords
CERT_KEYWORDS = [
    "certificate", "certified", "certification",
    "hcia", "hcip", "hcna", "hcnp",
    "mos", "microsoft office specialist",
    "google", "huawei", "oracle", "cisco"
]

CERT_SECTION_HEADERS = [
    "certifications", "certification", "licenses", "training", "courses"
]

GLOBAL_CERT_ACRONYMS = [
    "cfa", "cpa", "cma", "cima", "acca",
    "pmp", "prince2", "itil",
    "shrm", "cipd",
    "ielts", "toefl",
    "aws", "azure", "gcp",
    "scrum", "six sigma", "lean",
]

def is_certification_line(line):
    """Detect certification lines"""
    line_lower = line.lower()
    
    # Exclude job positions
    if re.match(r'^\s*\d{4}\s*[–-]\s*\d{4}.*?(professor|engineer|coordinator|member|editor)', line_lower):
        return False
    if re.match(r'^\s*\d{4}\s*[–-]\s*present', line_lower):
        return False
    
    # Exclude awards without certificate
    if 'award' in line_lower and 'certificate' not in line_lower:
        return False
    
    # Exclude publications
    if any(x in line_lower for x in ['thesis title:', 'doi:', 'isbn:', 'issn:']):
        return False
    
    # Exclude training without certification
    if 'training' in line_lower and 'certified' not in line_lower and 'certification' not in line_lower:
        return False
    
    # Exclude memberships
    if 'member' in line_lower and 'certificate' not in line_lower:
        return False
    
    # Include certificate keywords
    if re.search(r"\b(certified|certificate|certification)\b", line_lower):
        return True

    # Include certification acronyms
    if any(ac in line_lower for ac in GLOBAL_CERT_ACRONYMS):
        return True

    # Include exam codes
    if re.search(r"\b(mos|hcia|hcip|hcna|hcnp|comptia|cisco|google|huawei)\b", line_lower):
        if re.search(r"\b(certified|certificate|certification)\b", line_lower):
            return True
        if re.search(r"\b\d{2}[-]\d{3,4}\b", line_lower):
            return True

    return False

def clean_certificate_name(raw):
    """Clean certificate text"""
    text = raw

    # Remove certificate IDs and long numbers
    text = re.sub(r'certificate id[:\- ]*\S+', '', text, flags=re.I)
    text = re.sub(r'\d{5,}', '', text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"^\s*\d+\s*[-:]\s*", "", text)
    text = re.sub(r"^\s*\d{1,2}/\d{1,2}/\d{4}\s*", "", text)
    text = text.replace("•", " ")
    text = " ".join(text.split()).strip()

    if len(text) < 3 or len(text) > 80:
        return None
    
    text_lower = text.lower()
    if text_lower in ['microsoft office word', 'microsoft office excel', 'microsoft office powerpoint']:
        return None
    
    if text_lower.startswith('microsoft office') and 'mos' not in text_lower:
        return None

    return f"{text} (cert)"

# FIX #5: PDF artifact cleaner
def clean_pdf_artifacts(text):
    """Clean common PDF parsing artifacts"""
    # Fix broken words
    replacements = {
        r'Javascr\s*ipt': 'Javascript',
        r'Omne\s*T\+\+': 'OMNeT++',
        r'E\s*Nsp': 'eNSP',
        r'Ni\'?s\s+Multi\s*sim': 'Multisim',
        r'Lab\s*View': 'LabVIEW',
        r'Mac\s*Osx': 'Mac OSX',
        r'Wi\s*Max': 'WiMAX',
        r'Sim\s*ulators?': 'Simulators',
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Fix parentheses spacing
    text = text.replace('(', ' (')
    text = text.replace(')', ') ')
    
    # Normalize spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text

class ResumeAnalyzer:
    """Main class for resume analysis and scoring"""
    
    def __init__(self):
        self.nlp = nlp
    
    def extract_education(self, text):
        """
        FIX #9: Extract education with FULL field name
        """
        education_data = []
        field_of_study = None
        
        # Degree patterns
        degree_patterns = [
            r'\b(phd|ph\.d|doctorate|doctoral)\b',
            r'\b(mba|master|m\.s|m\.a|masters|msc|ma)\b',
            r'\b(bachelor|b\.s|b\.a|bachelors|bsc|ba|undergraduate)\b',
            r'\b(diploma|associate)\b'
        ]
        
        text_lower = text.lower()
        degree_type = None
        
        for pattern in degree_patterns:
            match = re.search(pattern, text_lower)
            if match:
                degree_type = match.group(0)
                
                # FIX #9: Extract FULL field name (up to 100 chars or "from")
                field_search = text[match.start():match.end()+300]
                field_pattern = r'\bin\s+([A-Za-z][A-Za-z\s&,.-]{5,100}?)(?:\s+from|\bat\b|\n|$)'
                field_match = re.search(field_pattern, field_search, re.IGNORECASE)
                
                if field_match:
                    field_of_study = field_match.group(1).strip()
                    # Clean up
                    field_of_study = re.sub(r'\s+', ' ', field_of_study)
                    # Stop at "from"
                    if ' from ' in field_of_study.lower():
                        field_of_study = field_of_study.split(' from ')[0]
                    field_of_study = field_of_study.strip()
                
                education_data.append({
                    'degree': degree_type,
                    'field': field_of_study,
                    'found': True
                })
                break
        
        # Check for Islamic Finance certifications
        has_if_cert = False
        cert_names = []
        
        for cert in ISLAMIC_FINANCE_CERTS:
            if re.search(r'\b' + re.escape(cert) + r'\b', text_lower):
                has_if_cert = True
                cert_names.append(cert)
        
        return {
            'degrees': education_data,
            'field_of_study': field_of_study,
            'has_islamic_finance_cert': has_if_cert,
            'certification_names': ', '.join(cert_names) if cert_names else None
        }
    
    def extract_experience(self, text):
        """
        FIX #1: Extract years ONLY from Employment History section
        DON'T trust "X years" statements (PDF artifacts)
        """
        # FIX #1: ONLY calculate from Employment History dates
        emp_patterns = [
            r'(?is)(employment\s+history)(.*?)(?=education|skills|certifications|research projects|trainings|students supervised|$)',
            r'(?is)(professional\s*experience)(.*?)(?=education|skills|certifications|key competencies|$)',
        ]
        
        emp_section = None
        for pattern in emp_patterns:
            match = re.search(pattern, text)
            if match:
                emp_section = match.group(2)
                print(f"✓ Found employment section ({len(match.group(2))} chars)")
                break
        
        if not emp_section:
            print("⚠️ No employment section found")
            return 0
        
        # Extract ALL date ranges from employment section
        dates = re.findall(r'(\d{4})\s*[–—-]\s*(?:(\d{4})|present|current)', emp_section, re.IGNORECASE)
        
        if not dates:
            print("⚠️ No date ranges found in employment section")
            return 0
        
        total_years = 0
        print(f"✓ Found {len(dates)} employment date ranges:")
        
        for start, end in dates:
            start_year = int(start)
            end_year = int(end) if end else datetime.now().year
            
            # Sanity check
            if end_year > start_year and start_year >= 1990:
                years = end_year - start_year
                total_years += years
                print(f"  {start} - {end or 'present'} = {years} years")
        
        # Cap at 40 years
        final_years = min(total_years, 40)
        print(f"✓ Total experience: {final_years} years")
        
        return final_years
    
    def check_islamic_finance_experience(self, text):
        """Check if candidate has Islamic Finance experience"""
        if_keywords = [
            'sukuk', 'sharia', 'islamic finance', 'islamic bank',
            'takaful', 'mudaraba', 'musharaka', 'ijara'
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in if_keywords)
    
    def is_skill_like(self, text):
        """
        FIX #11: Comprehensive garbage filter
        """
        t = text.lower().strip()

        # Too many words
        if len(text.split()) > 3:
            return False

        # FIX #3: Publication vocabulary
        if any(pub in t for pub in PUBLICATION_KEYWORDS):
            return False
        
        # FIX #4: Personal info
        if any(personal in t for personal in PERSONAL_INFO_KEYWORDS):
            return False

        # Exclusions
        if any(x in t for x in ["award", "member", "committee", "chair", "editor", "reviewer"]):
            return False
        if any(x in t for x in ["thesis", "project", "principal investigator"]):
            return False
        
        # Contains years
        if re.search(r'\d{4}', t):
            return False
        
        # Too long
        if len(text) > 40:
            return False
        
        # FIX #11: Garbage phrases
        if t in ["my", "my technical", "technical", "proficient", "languages", "development", "competences"]:
            return False
        
        # FIX #6: Simulator names
        if any(sim in t for sim in SIMULATOR_NAMES):
            return False
        
        # FIX #7: OS names
        if any(os in t for os in OS_NAMES):
            return False
        
        # FIX #8: Certificate codes (e.g., "77-727", "H12-711")
        if re.search(r'\b\d{2}[-:]\d{3,4}\b', t):
            return False

        return True
    
    def extract_skills_advanced(self, text):
        """
        COMPREHENSIVE skill extraction with ALL FIXES
        """
        extracted_skills = []
        skill_counts = Counter()
        
        # FIX #5: Clean PDF artifacts FIRST
        text = clean_pdf_artifacts(text)
        
        # FIX #2: HARD STOP at Publications section
        stop_markers = [
            'publications', 'references', 'additional information',
            'article', 'inbook', 'inproceedings'
        ]
        
        for marker in stop_markers:
            pattern = rf'(?i)^{marker}\s*$'
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                text = text[:match.start()]
                print(f"✓ Stopped extraction at: {marker}")
                break
        
        text_lower = text.lower()
        
        # Prevent certificate lines from being treated as skills
        certification_lines = set()
        for line in text.split("\n"):
            if is_certification_line(line):
                certification_lines.add(line.strip())
        
        # Expanded skill section headers
        SKILL_SECTION_HEADERS = [
            'programming skills', 'technical skills', 'soft skills', 'competencies',
            'personal skills', 'development', 'simulators', 'operating systems',
            'tools', 'technologies', 'languages', 'skills',
            'back-end', 'backend', 'front-end', 'frontend',
            'apis', 'databases', 'frameworks', 'hosting',
            'key competencies', 'core skills', 'personal skills and competences'
        ]
        
        skills_section = ""
        for header in SKILL_SECTION_HEADERS:
            section_patterns = [
                rf'(?i)^{re.escape(header)}\s*[:\-]?\s*$(.*?)(?=^[A-Z][A-Za-z\s]{{2,30}}[:\-]?$)',
            ]
            for pattern in section_patterns:
                match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
                if match:
                    skills_section += match.group(1) + "\n"
        
        # Fallback: if no header found but keywords exist
        if not skills_section.strip() or len(skills_section) < 30:
            print("⚠️ No strict header found, checking for keyword-dense sections...")
            for line in text.split("\n"):
                keyword_count = sum(1 for kw in PROGRAMMING_KEYWORDS + DATABASE_KEYWORDS if kw in line.lower())
                if keyword_count >= 3:
                    skills_section += line + "\n"
        
        if not skills_section.strip() or len(skills_section) < 20:
            print("⚠️ No skills section found - returning empty")
            return []
        
        print(f"✓ Found skills section ({len(skills_section)} chars)")
        
        # TIER 1: REGEX Pattern Matching
        skills_section_lower = skills_section.lower()
        for skill_name, pattern in SKILL_PATTERNS.items():
            matches = re.findall(pattern, skills_section_lower, re.IGNORECASE)
            if matches:
                count = len(matches)
                normalized_key = normalize_skill(skill_name)
                skill_counts[normalized_key] += count
        
        # TIER 1.5: Dictionary-based scanning
        combined_dict = (
            PROGRAMMING_KEYWORDS +
            TECH_KEYWORDS +
            NETWORKING_KEYWORDS +
            CYBERSECURITY_KEYWORDS +
            ENGINEERING_KEYWORDS +
            SOFT_KEYWORDS +
            DATABASE_KEYWORDS +
            CLOUD_KEYWORDS
        )
        
        for keyword in combined_dict:
            if len(keyword) > 1:
                pattern = r'\b' + re.escape(keyword) + r'\b'
                matches = re.findall(pattern, skills_section_lower)
                if matches:
                    normalized_key = normalize_skill(keyword)
                    skill_counts[normalized_key] += len(matches)
        
        # FIX #12: CSV extraction with proper splitting
        for line in skills_section.split("\n"):
            if "," in line or ";" in line:
                items = re.split(r'[,;]', line)
                for item in items:
                    item = item.strip().lower()
                    item = re.sub(r'[^\w\s\.\-\+]', '', item)
                    # Check if it's in our dictionaries
                    if item in combined_dict and len(item.split()) <= 3:
                        normalized_key = normalize_skill(item)
                        skill_counts[normalized_key] += 1
        
        # TIER 2: NLP-based extraction (filtered)
        doc = self.nlp(skills_section[:5000])
        for chunk in doc.noun_chunks:
            text_chunk = chunk.text.strip()
            lower = text_chunk.lower()

            # Word count constraint
            words = text_chunk.split()
            if not (1 <= len(words) <= 3):
                continue

            # Skip if contains verbs, AUX, ADV, NUM
            if any(t.pos_ in ("VERB", "AUX", "ADV", "NUM") for t in chunk):
                continue

            # Must be skill-like
            if not self.is_skill_like(text_chunk):
                continue

            # At this point, it's a valid skill
            normalized = normalize_skill(text_chunk)
            if normalized not in [s.lower() for s in skill_counts.keys()]:
                skill_counts[normalized] += 1
        
        # FIX #10: Better deduplication with normalization
        seen = set()
        
        for skill_name, matches_in_doc in skill_counts.items():
            # Normalize for deduplication
            skill_lower = skill_name.lower().replace('-', ' ').replace('.', '').strip()
            
            # Skip if already seen
            if skill_lower in seen:
                continue
            seen.add(skill_lower)
            
            # Filter out server names unless appearing 2+ times
            if skill_lower in SERVER_NAMES and matches_in_doc < 2:
                continue
            
            # Categorize
            category = 'technical'
            if skill_lower in PROGRAMMING_KEYWORDS:
                category = 'technical'
            elif skill_lower in TECH_KEYWORDS:
                category = 'technical'
            elif skill_lower in NETWORKING_KEYWORDS:
                category = 'technical'
            elif skill_lower in CYBERSECURITY_KEYWORDS:
                category = 'technical'
            elif skill_lower in ENGINEERING_KEYWORDS:
                category = 'technical'
            elif skill_lower in DATABASE_KEYWORDS:
                category = 'technical'
            elif skill_lower in CLOUD_KEYWORDS:
                category = 'technical'
            elif skill_lower in ISLAMIC_FINANCE_KEYWORDS:
                category = 'islamic_finance'
            elif skill_lower in SOFT_KEYWORDS:
                category = 'soft_skill'
            elif skill_lower in SOFT_SKILLS_LIST:
                category = 'soft_skill'
            
            is_hard = is_hard_skill(skill_name)
            
            # Final garbage filter
            title = skill_name.title()
            title_lower = title.lower()
            
            skip = False
            
            # Certificate IDs
            if 'certificate' in title_lower and 'id' in title_lower:
                skip = True
            
            # Too long
            if len(title) > 50:
                skip = True
            
            # Contains commas or weird punctuation
            if ',' in title:
                skip = True
            
            # Known garbage
            if title_lower in ['co', 'collaborations', 'research projects', 
                                'engineering', 'technology', 'my', 'languages',
                                'proficient', 'development', 'competences']:
                skip = True
            
            if skip:
                continue
            
            extracted_skills.append({
                'skill_name': title,
                'category': category,
                'is_hard_skill': is_hard,
                'count': matches_in_doc
            })
        
        # Certificate extraction (existing logic)
        cert_skills = []
        cert_section = ""
        for header in CERT_SECTION_HEADERS:
            m = re.search(
                header + r"(.*?)(?:experience|education|skills|projects|$)",
                text,
                flags=re.I | re.DOTALL
            )
            if m:
                cert_section = m.group(1)
                break

        if cert_section:
            for line in cert_section.split("\n"):
                if is_certification_line(line):
                    cleaned = clean_certificate_name(line)
                    if cleaned:
                        cert_skills.append(cleaned)

        for line in text.split("\n"):
            if is_certification_line(line):
                cleaned = clean_certificate_name(line)
                if cleaned:
                    cert_skills.append(cleaned)

        cert_skills = list(dict.fromkeys(cert_skills))

        for cert_skill in cert_skills:
            extracted_skills.append({
                "skill_name": cert_skill,
                "category": "technical",
                "is_hard_skill": True,
                "count": 1
            })
        
        print(f"✓ Extracted {len(extracted_skills)} skills")
        return extracted_skills
    
    def calculate_education_score(self, education_data):
        """Calculate education score"""
        if not education_data['degrees']:
            return 50
        
        degree = education_data['degrees'][0]['degree'].lower()
        degree_clean = degree.replace('.', '').replace(' ', '')
        
        if 'phd' in degree_clean or 'doctorate' in degree_clean:
            score = 100
        elif 'master' in degree_clean or 'mba' in degree_clean:
            score = 90
        elif 'bachelor' in degree_clean:
            score = 70
        else:
            score = 50
        
        if education_data['has_islamic_finance_cert']:
            score = min(100, score + 20)
        
        return score
    
    def calculate_experience_score(self, years, has_if_experience=False):
        """Calculate experience score"""
        if years >= 10:
            score = 100
        elif years >= 7:
            score = 90
        elif years >= 5:
            score = 80
        elif years >= 3:
            score = 60
        elif years >= 1:
            score = 50
        else:
            score = 30
        
        if has_if_experience:
            score = min(100, score + 15)
        
        return score
    
    def calculate_skills_score(self, skills, hard_weight=0.7, soft_weight=0.3):
        """Calculate skills score"""
        if not skills:
            return 20
        
        hard_skills = [s for s in skills if s['is_hard_skill']]
        soft_skills = [s for s in skills if not s['is_hard_skill']]
        
        hard_score = min(100, len(hard_skills) * 8)
        soft_score = min(100, len(soft_skills) * 12)
        final_score = (hard_score * hard_weight) + (soft_score * soft_weight)
        
        return final_score
    
    def calculate_islamic_finance_score(self, education_data, has_if_experience, skills):
        """Calculate Islamic Finance score"""
        score = 0
        
        if education_data['has_islamic_finance_cert']:
            score += 40
        
        if has_if_experience:
            score += 30
        
        if_skills = [s for s in skills if s['category'] == 'islamic_finance']
        score += min(30, len(if_skills) * 10)
        
        return min(100, score)


def analyze_resume(candidate, job_posting=None, use_ml=True):
    """Main analysis function"""
    analyzer = ResumeAnalyzer()
    
    print(f"\n{'='*60}")
    print(f"ANALYZING RESUME: {candidate.name}")
    print(f"{'='*60}\n")
    
    if not hasattr(candidate, 'resume'):
        print("No resume found")
        return None
    
    resume = candidate.resume
    text = resume.parsed_text
    
    if not text:
        print("No text available")
        return None
    
    # Extract information
    print("Extracting education...")
    education_data = analyzer.extract_education(text)
    
    print("Extracting experience...")
    years_experience = analyzer.extract_experience(text)
    has_if_experience = analyzer.check_islamic_finance_experience(text)
    
    print("Extracting skills...")
    skills_data = analyzer.extract_skills_advanced(text)
    
    # Get weights
    if job_posting:
        education_weight = job_posting.education_weight
        experience_weight = job_posting.experience_weight
        skills_weight = job_posting.skills_weight
        islamic_finance_weight = job_posting.islamic_finance_weight
    else:
        education_weight = 0.25
        experience_weight = 0.30
        skills_weight = 0.25
        islamic_finance_weight = 0.20
    
    # Calculate scores
    print("\nCalculating scores...")
    education_score = analyzer.calculate_education_score(education_data)
    experience_score = analyzer.calculate_experience_score(years_experience, has_if_experience)
    skills_score = analyzer.calculate_skills_score(skills_data)
    islamic_finance_score = analyzer.calculate_islamic_finance_score(
        education_data, has_if_experience, skills_data
    )
    
    total_score = (
        (education_score * education_weight) +
        (experience_score * experience_weight) +
        (skills_score * skills_weight) +
        (islamic_finance_score * islamic_finance_weight)
    )
    
    # Apply ML if available
    if use_ml and ML_AVAILABLE and ml_enhancer.is_trained:
        print("\nApplying ML enhancement...")
        total_score = ml_enhancer.get_enhanced_score(candidate, total_score)
    
    # Round scores
    education_score = round(education_score, 1)
    experience_score = round(experience_score, 1)
    skills_score = round(skills_score, 1)
    islamic_finance_score = round(islamic_finance_score, 1)
    total_score = round(total_score, 1)
    
    print(f"\nFinal Scores:")
    print(f"  Education: {education_score}/100")
    print(f"  Experience: {experience_score}/100 ({years_experience} years)")
    print(f"  Skills: {skills_score}/100 ({len(skills_data)} skills)")
    print(f"  Islamic Finance: {islamic_finance_score}/100")
    print(f"  TOTAL: {total_score}/100")
    
    # Save to database
    print("\nSaving to database...")
    
    candidate.years_experience = years_experience
    candidate.save()
    
    for edu in education_data['degrees']:
        Education.objects.update_or_create(
            candidate=candidate,
            degree=edu['degree'],
            defaults={
                'institution': 'Not specified',
                'field_of_study': education_data.get('field_of_study') or 'Not specified',
                'has_islamic_finance_cert': education_data['has_islamic_finance_cert']
            }
        )
    
    for skill in skills_data:
        Skill.objects.get_or_create(
            candidate=candidate,
            skill_name=skill['skill_name'],
            defaults={
                'category': skill['category'],
                'is_hard_skill': skill['is_hard_skill']
            }
        )
    
    Score.objects.update_or_create(
        candidate=candidate,
        defaults={
            'education_score': education_score,
            'experience_score': experience_score,
            'skills_score': skills_score,
            'islamic_finance_score': islamic_finance_score,
            'total_score': total_score
        }
    )
    
    print("Analysis complete!")
    print(f"{'='*60}\n")
    
    return {
        'education_score': education_score,
        'experience_score': experience_score,
        'skills_score': skills_score,
        'islamic_finance_score': islamic_finance_score,
        'total_score': total_score,
        'years_experience': years_experience,
        'skills_extracted': len(skills_data)
    }