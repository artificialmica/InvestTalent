"""
AI-Powered Resume Scoring Engine - FIXED ULTIMATE VERSION
Bug fixes:
1. Education pattern order (check Bachelor before Master)
2. Word boundaries to prevent false matches
3. Skill deduplication
4. Better section extraction
"""

import spacy
import re
from datetime import datetime
from collections import Counter
from .models import Candidate, Resume, Education, Experience, Skill, Score

# Try sentence transformers
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    SEMANTIC_AVAILABLE = True
except:
    SEMANTIC_AVAILABLE = False

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

# TIER 1: CRITICAL SKILL PATTERNS (with word boundaries!)
CRITICAL_SKILLS = {
    # Technical
    'Python': r'\bpython\b',
    'Java': r'\bjava\b',
    'JavaScript': r'\bjavascript\b|\bjs\b',
    'SQL': r'\bsql\b|\bmysql\b|\bpostgresql\b',
    'Excel': r'\bexcel\b|\bms\s*excel\b',
    'R Programming': r'\bR\s+programming\b|\bR\s+language\b',
    'MATLAB': r'\bmatlab\b',
    'VBA': r'\bvba\b',
    
    # Finance
    'Financial Modeling': r'\bfinancial\s+model(?:ing|ling|s)?\b',
    'Financial Analysis': r'\bfinancial\s+analys[ie]s\b',
    'Portfolio Management': r'\bportfolio\s+management\b',
    'Risk Management': r'\brisk\s+management\b',
    'Investment Analysis': r'\binvestment\s+analys[ie]s\b',
    'Equity Research': r'\bequity\s+research\b',
    'Fixed Income': r'\bfixed\s+income\b',
    'Derivatives': r'\bderivatives?\b',
    'Valuation': r'\bvaluation\b',
    
    # Tools
    'Bloomberg Terminal': r'\bbloomberg\b',
    'PowerBI': r'\bpower\s*bi\b|\bpowerbi\b',
    'Tableau': r'\btableau\b',
    'SAP': r'\bsap\b',
    'Oracle': r'\boracle\b',
    
    # Islamic Finance
    'Sukuk': r'\bsukuk\b',
    'Sharia': r'\bsharia[h]?\b',
    'Mudaraba': r'\bmudaraba[h]?\b',
    'Musharaka': r'\bmusharaka[h]?\b',
    'Takaful': r'\btakaful\b',
    'Islamic Finance': r'\bislamic\s+finance\b|\bislamic\s+banking\b',
    
    # Data Science
    'Machine Learning': r'\bmachine\s+learning\b',
    'Data Analysis': r'\bdata\s+analys[ie]s\b',
    'Data Science': r'\bdata\s+science\b',
    
    # Soft Skills
    'Leadership': r'\bleadership\b',
    'Communication': r'\bcommunication\b',
    'Teamwork': r'\bteamwork\b|\bteam\s+work\b',
    'Problem Solving': r'\bproblem\s+solving\b',
    'Project Management': r'\bproject\s+management\b',
}

ISLAMIC_FINANCE_CERTS = ['cife', 'aaoifi', 'cibafi', 'cifp', 'csaa', 'cipa', 'ifq']


class HybridExtractor:
    
    def __init__(self):
        self.nlp = nlp
        
        if SEMANTIC_AVAILABLE:
            try:
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                self.ml_ready = True
                self.skill_categories = {
                    'technical': ['programming', 'software', 'database', 'coding'],
                    'finance': ['investment', 'portfolio', 'trading', 'valuation', 'financial'],
                    'islamic_finance': ['sukuk', 'sharia', 'islamic', 'takaful', 'halal'],
                    'soft_skill': ['communication', 'leadership', 'teamwork', 'problem solving']
                }
                self.category_embeddings = {
                    cat: self.model.encode(keywords)
                    for cat, keywords in self.skill_categories.items()
                }
            except:
                self.ml_ready = False
        else:
            self.ml_ready = False
    
    def extract_education_smart(self, text):
        """FIXED: Extract education with proper pattern order"""
        # Find EDUCATION section more reliably
        edu_match = re.search(r'EDUCATION(.*?)(?:WORK EXPERIENCE|EXPERIENCE|SKILLS|CERTIFICATIONS|$)', text, re.DOTALL | re.IGNORECASE)
        
        if edu_match:
            education_text = edu_match.group(1)
        else:
            # Fallback: use full text
            education_text = text
        
        # FIXED: Check patterns in correct order (Bachelor BEFORE Master!)
        # Use word boundaries to prevent false matches
        degree = 'Bachelor'  # Default
        degree_patterns = [
            (r'\bPh\.?D\.?\b|\bDoctorate\b|\bDoctoral\b', 'PhD'),
            (r'\bBachelor\b|\bB\.S\.?\b|\bB\.A\.?\b|\bBSc\b|\bBA\b', 'Bachelor'),  # CHECK FIRST!
            (r'\bMBA\b|\bMaster\b|\bM\.S\.?\b|\bM\.A\.?\b|\bMSc\b|\bMA\b', 'Master'),  # Then Master
            (r'\bDiploma\b|\bAssociate\b', 'Diploma')
        ]
        
        for pattern, name in degree_patterns:
            if re.search(pattern, education_text, re.IGNORECASE):
                degree = name
                break
        
        # Extract field
        field = None
        field_patterns = [
            r'(?:Bachelor|Master|MBA|Ph\.?D\.?|B\.S\.?|M\.S\.?)\s+(?:of\s+)?(?:Science|Arts|Business)?\s+(?:in|of)\s+([A-Za-z\s&]+?)(?:\n|,|from|at|University|College|\||Graduated)',
        ]
        
        for pattern in field_patterns:
            match = re.search(pattern, education_text, re.IGNORECASE)
            if match:
                field = match.group(1).strip()
                field = re.sub(r'\s+', ' ', field)
                if 3 < len(field) < 50:
                    break
        
        # Extract institution
        institution = None
        inst_match = re.search(r'([A-Z][A-Za-z\s&-]+?(?:University|College|Institute|School|Polytechnic))', education_text)
        if inst_match:
            institution = inst_match.group(1).strip()
        
        # Extract year
        year = None
        year_match = re.search(r'(?:Graduated|Graduation).*?(\d{4})', education_text)
        if year_match:
            year = int(year_match.group(1))
        
        # Check IF cert
        has_if_cert = any(cert in text.lower() for cert in ISLAMIC_FINANCE_CERTS)
        
        return {
            'degrees': [{'degree': degree, 'found': True}],
            'field_of_study': field or 'Not specified',
            'institution': institution or 'Not specified',
            'graduation_year': year,
            'has_islamic_finance_cert': has_if_cert,
            'certification_names': None
        }
    
    def extract_skills_hybrid(self, text):
        """FIXED: Hybrid extraction with deduplication"""
        all_skills = {}  # key = lowercase skill name
        text_lower = text.lower()
        
        # TIER 1: CRITICAL SKILLS (Regex)
        print("  🎯 Tier 1: Critical skills (Regex)...")
        for skill_name, pattern in CRITICAL_SKILLS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                key = skill_name.lower()
                all_skills[key] = {
                    'skill_name': skill_name,
                    'method': 'regex',
                    'confidence': 1.0
                }
        
        print(f"     Found {len(all_skills)} critical skills")
        
        # TIER 2: NLP EXTRACTION
        print("  🔍 Tier 2: NLP extraction...")
        skills_section = self._extract_skills_section(text)
        
        if skills_section:
            # Comma-separated lists
            list_patterns = [
                r'Technical\s+Skills?:\s*([^\n]+)',
                r'Soft\s+Skills?:\s*([^\n]+)',
                r'Skills?:\s*([^\n]+)',
            ]
            
            for pattern in list_patterns:
                matches = re.findall(pattern, skills_section, re.IGNORECASE)
                for match in matches:
                    items = re.split(r',|;', match)
                    for item in items:
                        clean = item.strip()
                        clean = re.sub(r'\([^)]*\)', '', clean)  # Remove (Advanced)
                        clean = clean.strip('• ').strip()
                        
                        if clean and 3 < len(clean) < 40:
                            key = clean.lower()
                            if key not in all_skills:
                                all_skills[key] = {
                                    'skill_name': clean.title(),
                                    'method': 'nlp_list',
                                    'confidence': 0.9
                                }
            
            # spaCy noun chunks (2-3 words only to avoid single words)
            doc = self.nlp(skills_section)
            for chunk in doc.noun_chunks:
                words = chunk.text.split()
                if 2 <= len(words) <= 3:  # Only multi-word
                    clean = chunk.text.strip()
                    key = clean.lower()
                    if key not in all_skills and len(clean) > 5:
                        all_skills[key] = {
                            'skill_name': clean.title(),
                            'method': 'nlp_chunk',
                            'confidence': 0.7
                        }
        
        print(f"     Total unique: {len(all_skills)}")
        
        # TIER 3: CATEGORIZATION
        print("  🤖 Tier 3: Categorization...")
        final_skills = []
        
        for skill_key, skill_data in all_skills.items():
            category = self._categorize_skill_smart(skill_data['skill_name'])
            is_hard = self._is_hard_skill(skill_data['skill_name'])
            
            final_skills.append({
                'skill_name': skill_data['skill_name'],
                'category': category,
                'is_hard_skill': is_hard
            })
        
        print(f"  ✅ Extracted {len(final_skills)} unique skills")
        return final_skills
    
    def _extract_skills_section(self, text):
        """Extract skills section"""
        match = re.search(r'SKILLS(.*?)(?:CERTIFICATIONS|WORK EXPERIENCE|EDUCATION|$)', text, re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else ''
    
    def _categorize_skill_smart(self, skill):
        """Categorize skill"""
        skill_lower = skill.lower()
        
        if any(w in skill_lower for w in ['python', 'java', 'sql', 'programming', 'code']):
            return 'technical'
        if any(w in skill_lower for w in ['investment', 'portfolio', 'financial', 'trading', 'equity', 'valuation']):
            return 'finance'
        if any(w in skill_lower for w in ['sukuk', 'sharia', 'islamic', 'takaful']):
            return 'islamic_finance'
        if any(w in skill_lower for w in ['communication', 'leadership', 'teamwork', 'problem']):
            return 'soft_skill'
        
        if self.ml_ready:
            try:
                skill_emb = self.model.encode([skill])
                best_cat = 'technical'
                best_score = 0
                
                for cat, embeddings in self.category_embeddings.items():
                    sim = cosine_similarity(skill_emb, embeddings)
                    max_sim = np.max(sim)
                    if max_sim > best_score:
                        best_score = max_sim
                        best_cat = cat
                
                return best_cat
            except:
                pass
        
        return 'technical'
    
    def _is_hard_skill(self, skill):
        """Determine if hard or soft"""
        soft_keywords = ['communication', 'leadership', 'teamwork', 'problem solving',
                        'thinking', 'attention', 'interpersonal']
        return not any(kw in skill.lower() for kw in soft_keywords)


class ResumeAnalyzer:
    
    def __init__(self):
        self.nlp = nlp
        self.extractor = HybridExtractor()
    
    def extract_education(self, text):
        return self.extractor.extract_education_smart(text)
    
    def extract_experience(self, text):
        patterns = [
            r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
            r'experience\s*:\s*(\d+)\+?\s*years?',
        ]
        
        years = []
        for pattern in patterns:
            matches = re.findall(pattern, text.lower())
            years.extend([int(m) for m in matches])
        
        if years:
            return max(years)
        
        job_count = len(re.findall(r'\d{4}\s*-\s*(?:\d{4}|present)', text.lower(), re.IGNORECASE))
        return max(1, job_count * 2) if job_count > 0 else 0
    
    def check_islamic_finance_experience(self, text):
        if_keywords = ['sukuk', 'sharia', 'islamic finance', 'islamic bank', 'takaful']
        return any(kw in text.lower() for kw in if_keywords)
    
    def extract_skills_advanced(self, text):
        return self.extractor.extract_skills_hybrid(text)
    
    def calculate_education_score(self, education_data):
        if not education_data['degrees']:
            return 50
        
        degree = education_data['degrees'][0]['degree'].lower()
        
        if 'phd' in degree:
            score = 100
        elif 'master' in degree:
            score = 90
        elif 'bachelor' in degree:
            score = 70
        else:
            score = 50
        
        if education_data['has_islamic_finance_cert']:
            score = min(100, score + 20)
        
        return score
    
    def calculate_experience_score(self, years, has_if_exp):
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
        
        if has_if_exp:
            score = min(100, score + 15)
        
        return score
    
    def calculate_skills_score(self, skills, hard_weight=0.7, soft_weight=0.3):
        if not skills:
            return 20
        
        hard_skills = [s for s in skills if s['is_hard_skill']]
        soft_skills = [s for s in skills if not s['is_hard_skill']]
        
        hard_score = min(100, len(hard_skills) * 8)
        soft_score = min(100, len(soft_skills) * 12)
        
        return (hard_score * hard_weight) + (soft_score * soft_weight)
    
    def calculate_islamic_finance_score(self, education_data, has_if_exp, skills):
        score = 0
        
        if education_data['has_islamic_finance_cert']:
            score += 40
        if has_if_exp:
            score += 30
        
        if_skills = [s for s in skills if s['category'] == 'islamic_finance']
        score += min(30, len(if_skills) * 10)
        
        return min(100, score)


def analyze_resume(candidate, job_posting=None, use_ml=True):
    """Main analysis function"""
    analyzer = ResumeAnalyzer()
    
    print(f"\n{'='*60}")
    print(f"🎯 ANALYZING: {candidate.name}")
    print(f"{'='*60}\n")
    
    if not hasattr(candidate, 'resume'):
        print("❌ No resume found")
        return None
    
    text = candidate.resume.parsed_text
    if not text:
        print("❌ No parsed text")
        return None
    
    # Extract
    print("📚 Extracting education...")
    education_data = analyzer.extract_education(text)
    print(f"   Degree: {education_data['degrees'][0]['degree']}")
    print(f"   Field: {education_data.get('field_of_study')}")
    
    print("\n💼 Extracting experience...")
    years_exp = analyzer.extract_experience(text)
    has_if_exp = analyzer.check_islamic_finance_experience(text)
    print(f"   Years: {years_exp}, IF: {has_if_exp}")
    
    print("\n🔧 Extracting skills...")
    skills_data = analyzer.extract_skills_advanced(text)
    
    # Weights
    if job_posting:
        edu_weight = job_posting.education_weight
        exp_weight = job_posting.experience_weight
        skill_weight = job_posting.skills_weight
        if_weight = job_posting.islamic_finance_weight
    else:
        edu_weight = 0.25
        exp_weight = 0.30
        skill_weight = 0.25
        if_weight = 0.20
    
    # Calculate
    print(f"\n🎯 Calculating scores...")
    education_score = analyzer.calculate_education_score(education_data)
    experience_score = analyzer.calculate_experience_score(years_exp, has_if_exp)
    skills_score = analyzer.calculate_skills_score(skills_data)
    if_score = analyzer.calculate_islamic_finance_score(education_data, has_if_exp, skills_data)
    
    total_score = (
        (education_score * edu_weight) +
        (experience_score * exp_weight) +
        (skills_score * skill_weight) +
        (if_score * if_weight)
    )
    
    # ML enhancement
    if use_ml and ML_AVAILABLE and ml_enhancer.is_trained:
        total_score = ml_enhancer.get_enhanced_score(candidate, total_score)
    
    # Round
    education_score = round(education_score, 1)
    experience_score = round(experience_score, 1)
    skills_score = round(skills_score, 1)
    if_score = round(if_score, 1)
    total_score = round(total_score, 1)
    
    print(f"\n📊 SCORES: Edu={education_score} Exp={experience_score} Skills={skills_score} IF={if_score} TOTAL={total_score}")
    
    # Save
    candidate.years_experience = years_exp
    candidate.save()
    
    Education.objects.update_or_create(
        candidate=candidate,
        degree=education_data['degrees'][0]['degree'],
        defaults={
            'institution': education_data.get('institution', 'Not specified'),
            'field_of_study': education_data.get('field_of_study', 'Not specified'),
            'graduation_year': education_data.get('graduation_year'),
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
            'islamic_finance_score': if_score,
            'total_score': total_score
        }
    )
    
    print("✅ Complete!\n")
    
    return {
        'education_score': education_score,
        'experience_score': experience_score,
        'skills_score': skills_score,
        'islamic_finance_score': if_score,
        'total_score': total_score
    }