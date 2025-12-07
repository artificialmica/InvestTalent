"""
Advanced Skill Matching Module
Three-tier matching: Exact → Fuzzy → Semantic ML
"""

from fuzzywuzzy import fuzz, process
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Load semantic model (cached after first load)
try:
    semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
    SEMANTIC_ENABLED = True
except:
    SEMANTIC_ENABLED = False
    print("Warning: Semantic matching disabled - sentence-transformers not available")


# Master skill database
SKILL_VARIATIONS = {
    'python': ['python', 'python3', 'python 3', 'py', 'python2', 'python 2', 'python programming', 'python developer'],
    'java': ['java', 'java8', 'java 8', 'java11', 'java 11', 'java programming', 'java developer'],
    'javascript': ['javascript', 'js', 'java script', 'ecmascript', 'node.js', 'nodejs'],
    'c++': ['c++', 'cpp', 'c plus plus', 'cplusplus'],
    'sql': ['sql', 'mysql', 'postgresql', 'tsql', 't-sql', 'database', 'sql queries'],
    'excel': ['excel', 'ms excel', 'microsoft excel', 'spreadsheet', 'spreadsheets'],
    'power bi': ['power bi', 'powerbi', 'power-bi', 'microsoft power bi'],
    'tableau': ['tableau', 'tableu', 'tablaeu', 'data visualization'],
    'r': ['r programming', 'r language', 'r-programming', 'r statistics'],
    'machine learning': ['machine learning', 'ml', 'deep learning', 'ai', 'artificial intelligence', 'neural networks'],
    'data analysis': ['data analysis', 'data analytics', 'analytics', 'data science', 'data scientist'],
    'financial modeling': ['financial modeling', 'financial modelling', 'fin modeling', 'financial models'],
    'portfolio management': ['portfolio management', 'portfolio mgmt', 'asset management', 'investment management'],
    'risk management': ['risk management', 'risk mgmt', 'risk analysis', 'risk assessment'],
    'sukuk': ['sukuk', 'sukuks', 'islamic bonds', 'sharia bonds'],
    'mudarabah': ['mudarabah', 'mudaraba', 'mudharabah'],
    'musharakah': ['musharakah', 'musharaka', 'mushaarakah'],
    'sharia': ['sharia', 'shariah', 'shari\'a', 'sharia compliant', 'islamic finance'],
    'communication': ['communication', 'communications', 'verbal communication', 'written communication'],
    'leadership': ['leadership', 'team leadership', 'leading teams', 'team management'],
    'project management': ['project management', 'pm', 'agile', 'scrum', 'project manager'],
}

HARD_SKILLS = [
    'python', 'java', 'javascript', 'c++', 'sql', 'r', 'excel', 'power bi', 'tableau',
    'financial modeling', 'valuation', 'portfolio management', 'data analysis',
    'machine learning', 'statistics', 'econometrics', 'bloomberg terminal',
    'sukuk', 'mudarabah', 'musharakah', 'takaful', 'accounting', 'auditing'
]

SOFT_SKILLS = [
    'communication', 'leadership', 'teamwork', 'problem solving', 'time management',
    'creativity', 'adaptability', 'critical thinking', 'presentation', 'negotiation'
]


def get_semantic_similarity(text1, text2):
    """
    Calculate semantic similarity using ML embeddings
    Returns: 0.0 to 1.0 (higher = more similar)
    """
    if not SEMANTIC_ENABLED:
        return 0.0
    
    try:
        embeddings = semantic_model.encode([text1, text2])
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        return float(similarity)
    except:
        return 0.0


def match_skill_advanced(candidate_skill, required_skill):
    """
    Three-tier skill matching system
    
    Returns: (score, match_type)
        score: 0-100
        match_type: 'exact', 'fuzzy', 'semantic', or 'no_match'
    """
    candidate_lower = candidate_skill.lower().strip()
    required_lower = required_skill.lower().strip()
    
    # TIER 1: Exact match
    if candidate_lower == required_lower:
        return 100, 'exact'
    
    # TIER 2: Fuzzy string matching
    fuzzy_score = fuzz.token_sort_ratio(candidate_lower, required_lower)
    if fuzzy_score >= 85:
        return fuzzy_score, 'fuzzy'
    
    # TIER 3: Semantic ML matching
    if SEMANTIC_ENABLED:
        semantic_score = get_semantic_similarity(candidate_skill, required_skill)
        if semantic_score >= 0.75:  # 75% semantic threshold
            return int(semantic_score * 100), 'semantic'
    
    # No match
    return 0, 'no_match'


def normalize_skill(skill_text):
    """Normalize skill to standard form"""
    skill_lower = skill_text.lower().strip()
    
    # Check variations database
    for standard_skill, variations in SKILL_VARIATIONS.items():
        if skill_lower in variations:
            return standard_skill
    
    # Fuzzy match against standard skills
    all_standard = list(SKILL_VARIATIONS.keys())
    match = process.extractOne(skill_lower, all_standard, scorer=fuzz.token_sort_ratio)
    
    if match and match[1] > 80:
        return match[0]
    
    # Semantic match if available
    if SEMANTIC_ENABLED:
        best_match = None
        best_score = 0
        
        for standard_skill in all_standard:
            score = get_semantic_similarity(skill_lower, standard_skill)
            if score > best_score:
                best_score = score
                best_match = standard_skill
        
        if best_score > 0.75:
            return best_match
    
    return skill_text.title()


def is_hard_skill(skill_name):
    """Determine if skill is hard or soft"""
    skill_lower = skill_name.lower()
    
    for hard_skill in HARD_SKILLS:
        if fuzz.partial_ratio(skill_lower, hard_skill) > 85:
            return True
    
    for soft_skill in SOFT_SKILLS:
        if fuzz.partial_ratio(skill_lower, soft_skill) > 85:
            return False
    
    return True  # Default to hard skill


def match_required_skills(candidate_skills, required_skills):
    """
    Match candidate skills against job requirements
    Uses three-tier matching system
    """
    matches = []
    matched_count = 0
    
    for required in required_skills:
        best_match = None
        best_score = 0
        best_type = 'no_match'
        
        for candidate_skill in candidate_skills:
            score, match_type = match_skill_advanced(candidate_skill, required)
            
            if score > best_score:
                best_score = score
                best_match = candidate_skill
                best_type = match_type
        
        if best_score >= 75:  # Minimum 75% match
            matches.append({
                'required': required,
                'found': best_match,
                'score': best_score,
                'match_type': best_type
            })
            matched_count += 1
    
    return {
        'matched_count': matched_count,
        'total_required': len(required_skills),
        'match_percentage': (matched_count / len(required_skills) * 100) if required_skills else 0,
        'matches': matches
    }


def find_skill_variations(skill_text):
    """
    Find all variations of a skill using semantic matching
    Useful for HR to see what candidates might write
    """
    if not SEMANTIC_ENABLED:
        return []
    
    variations = []
    all_skills = []
    
    for variations_list in SKILL_VARIATIONS.values():
        all_skills.extend(variations_list)
    
    for skill in all_skills:
        similarity = get_semantic_similarity(skill_text, skill)
        if similarity > 0.70:
            variations.append({
                'skill': skill,
                'similarity': round(similarity * 100, 1)
            })
    
    return sorted(variations, key=lambda x: x['similarity'], reverse=True)[:10]