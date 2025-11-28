import spacy
import re
from datetime import datetime
from .models import Education, Experience, Skill, Score

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# Islamic Finance Keywords
ISLAMIC_FINANCE_KEYWORDS = [
    'sukuk', 'mudarabah', 'musharakah', 'murabaha', 'ijarah',
    'takaful', 'sharia', 'shariah', 'islamic finance', 'islamic banking',
    'halal investment', 'riba', 'zakat', 'gharar', 'maysir',
    'sharia compliant', 'islamic investment', 'islamic economics',
    'fiqh', 'fatwa', 'aaoifi', 'cife', 'cibafi'
]

# Islamic Finance Certifications
ISLAMIC_FINANCE_CERTS = [
    'cife', 'aaoifi', 'cibafi', 'cima islamic finance',
    'islamic finance qualification', 'cifp', 'csaa'
]

# Degree levels with scores
DEGREE_SCORES = {
    'phd': 100,
    'doctorate': 100,
    'master': 85,
    'mba': 85,
    'bachelor': 70,
    'diploma': 50,
    'high school': 30
}

# Negative context indicators
NEGATIVE_INDICATORS = [
    'no ', 'not ', 'never ', 'without ', 'lack of ', 'lacking ',
    'weak ', 'poor ', 'failed ', 'unsuccessful ', 'unable to ',
    'don\'t ', 'doesn\'t ', 'didn\'t ', 'won\'t ', 'cannot ',
    'beginner at ', 'learning ', 'studying ', 'want to learn ',
    'interested in learning', 'hoping to learn', 'trying to learn',
    'need to learn', 'should learn', 'will learn', 'basic understanding',
    'limited experience', 'minimal experience', 'no experience'
]

# Positive skill indicators
POSITIVE_SKILL_INDICATORS = [
    'proficient', 'experienced', 'expert', 'skilled', 'strong',
    'years of', 'experience with', 'experience in', 'expertise in',
    'advanced', 'fluent', 'certified', 'mastery', 'specialist',
    'worked with', 'used', 'implemented', 'developed using',
    'built with', 'created using', 'knowledge of', 'familiar with',
    'competent', 'capable', 'successful', 'accomplished',
    'proficiency in', 'skilled in', 'background in', 'specialized in',
    'hands-on', 'practical experience', 'demonstrated ability'
]


def analyze_resume(candidate):
    """
    Main function to analyze resume and calculate all scores
    """
    print("\n=== STARTING RESUME ANALYSIS ===")
    
    # Validate resume exists and has text
    if not hasattr(candidate, 'resume') or not candidate.resume.parsed_text:
        print("ERROR: NO RESUME TEXT")
        Score.objects.update_or_create(
            candidate=candidate,
            defaults={
                'education_score': 0,
                'experience_score': 0,
                'skills_score': 0,
                'islamic_finance_score': 0,
                'total_score': 0
            }
        )
        return candidate
    
    resume_text = candidate.resume.parsed_text.lower()
    print(f"Resume text length: {len(resume_text)}")
    print(f"First 200 chars: {resume_text[:200]}")
    
    # Check if resume is too short (likely empty or invalid)
    if len(resume_text) < 50:
        print("ERROR: RESUME TOO SHORT")
        Score.objects.update_or_create(
            candidate=candidate,
            defaults={
                'education_score': 0,
                'experience_score': 0,
                'skills_score': 0,
                'islamic_finance_score': 0,
                'total_score': 0
            }
        )
        return candidate
    
    # ANTI-CHEATING: Detect keyword stuffing
    if detect_keyword_stuffing(resume_text):
        print("ERROR: KEYWORD STUFFING DETECTED")
        Score.objects.update_or_create(
            candidate=candidate,
            defaults={
                'education_score': 0,
                'experience_score': 0,
                'skills_score': 0,
                'islamic_finance_score': 0,
                'total_score': 0
            }
        )
        return candidate
    
    print("Passed validation checks")
    
    # Extract information
    print("\nExtracting education...")
    extract_education(candidate, resume_text)
    print(f"Education records created: {candidate.education.count()}")
    
    print("\nExtracting experience...")
    extract_experience(candidate, resume_text)
    print(f"Experience records created: {candidate.experience.count()}")
    print(f"Years of experience: {candidate.years_experience}")
    
    print("\nExtracting skills...")
    extract_skills(candidate, resume_text)
    print(f"Skills records created: {candidate.skills.count()}")
    
    # Calculate scores
    print("\nCalculating scores...")
    calculate_scores(candidate)
    
    if hasattr(candidate, 'score'):
        print(f"\nFINAL SCORES:")
        print(f"  Education: {candidate.score.education_score}")
        print(f"  Experience: {candidate.score.experience_score}")
        print(f"  Skills: {candidate.score.skills_score}")
        print(f"  Islamic Finance: {candidate.score.islamic_finance_score}")
        print(f"  TOTAL: {candidate.score.total_score}")
    
    print("=== ANALYSIS COMPLETE ===\n")
    
    return candidate


def detect_keyword_stuffing(text):
    """
    Detect if resume has suspicious keyword stuffing patterns
    """
    # Count total words
    words = text.split()
    word_count = len(words)
    
    if word_count < 50:
        return False
    
    # Check for excessive repetition
    word_freq = {}
    for word in words:
        if len(word) > 3:  # Only count meaningful words
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # UPDATED: Increase threshold to 10% (was 5%)
    # Islamic Finance resumes naturally repeat "islamic", "finance", "investment"
    for word, count in word_freq.items():
        if count / word_count > 0.10:  # Changed from 0.05 to 0.10
            print(f"  WARNING: Word '{word}' appears {count} times ({count/word_count*100:.1f}%)")
            return True
    
    # Check for unnatural density of skill keywords
    all_skills = [
        'python', 'sql', 'excel', 'java', 'javascript', 'c++',
        'financial modeling', 'portfolio management', 'valuation',
        'sukuk', 'islamic finance', 'sharia', 'mudarabah'
    ]
    
    
    skill_count = sum(1 for skill in all_skills if skill in text)
    
    # UPDATED: Increase threshold to 30 skills (was 20)
    if skill_count > 30 and word_count < 500:
        print(f"  WARNING: {skill_count} skills found in only {word_count} words")
        return True
    
    return False

def check_skill_context(text, skill):
    """
    Enhanced context checking for skills
    Returns True only if skill appears in clearly positive context
    """
    # Find all occurrences of the skill
    pattern = re.compile(r'\b' + re.escape(skill) + r'\b', re.IGNORECASE)
    
    for match in pattern.finditer(text):
        # Get context window (100 chars before and after)
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        context = text[start:end].lower()
        
        # FIRST: Check for negative indicators
        for negative in NEGATIVE_INDICATORS:
            if negative in context:
                return False
        
        # SECOND: Check if in a "Skills:" section (MORE LENIENT)
        # Look for common section headers
        skill_section_indicators = [
            'skills:', 'technical skills:', 'core competencies:',
            'tools:', 'technologies:', 'expertise:', 'proficiencies:',
            'technical expertise:', 'core skills:', 'competencies:',
            'skills include:', 'proficient in:', 'experienced in:',
            'areas of expertise:'
        ]
        
        # Get larger context to check for section headers (300 chars back)
        large_context_start = max(0, match.start() - 300)
        large_context = text[large_context_start:end].lower()
        
        # Check if ANY skill section indicator appears before this skill
        for section_header in skill_section_indicators:
            if section_header in large_context:
                # Make sure the skill comes AFTER the header
                header_pos = large_context.rfind(section_header)  # Last occurrence
                skill_pos = match.start() - large_context_start
                if skill_pos > header_pos:
                    return True
        
        # THIRD: Must have at least ONE positive indicator nearby
        has_positive = any(positive in context for positive in POSITIVE_SKILL_INDICATORS)
        
        if has_positive:
            return True
    
    # If we get here, skill was mentioned but not in a valid context
    return False


def extract_education(candidate, text):
    """Extract education information from resume text"""
    
    # Common degree patterns (MORE FLEXIBLE)
    degree_patterns = [
        r'(phd|doctorate|ph\.d\.?)\s+(?:degree\s+)?(?:of\s+)?(?:in\s+)?([a-z\s]+)',
        r'(master|mba|m\.sc|m\.s\.?|ma|m\.a\.?)\s+(?:degree\s+)?(?:of\s+)?(?:in\s+)?([a-z\s]+)',
        r'(bachelor|b\.sc|b\.s\.?|ba|b\.a\.?|bba)\s+(?:degree\s+)?(?:of\s+)?(?:in\s+)?([a-z\s]+)',
        r'(diploma)\s+(?:degree\s+)?(?:of\s+)?(?:in\s+)?([a-z\s]+)',
    ]
    
    # Track what we've already added to prevent duplicates
    added_degrees = set()
    
    # Extract degrees
    found_degrees = False
    for pattern in degree_patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            degree_type = match.group(1)
            field = match.group(2).strip() if len(match.groups()) > 1 else "Not specified"
            
            # Clean up field name
            field = re.sub(r'\s+', ' ', field).strip()
            
            # Create unique key for this degree
            degree_key = f"{degree_type.lower()}_{field.lower()[:30]}"
            
            # Skip if we already added this degree
            if degree_key in added_degrees:
                print(f"  Skipped duplicate: {degree_type} in {field}")
                continue
            
            print(f"  Found degree: {degree_type} in {field}")
            
            # Verify this is a positive mention
            match_context_start = max(0, match.start() - 50)
            match_context_end = min(len(text), match.end() + 50)
            context = text[match_context_start:match_context_end]
            
            # Skip if negative context
            if any(neg in context for neg in NEGATIVE_INDICATORS):
                print(f"    Skipped (negative context)")
                continue
            
            # Check for Islamic finance
            has_if_cert = any(keyword in text for keyword in ISLAMIC_FINANCE_CERTS)
            
            Education.objects.create(
                candidate=candidate,
                degree=degree_type.upper(),
                field_of_study=field.title(),
                institution="Extracted from resume",
                has_islamic_finance_cert=has_if_cert
            )
            
            added_degrees.add(degree_key)
            print(f"    Created education record (IF cert: {has_if_cert})")
            
            found_degrees = True
    
    # If no degrees found, create a basic entry
    if not found_degrees:
        print("  No degrees found, creating default entry")
        Education.objects.create(
            candidate=candidate,
            degree="Not specified",
            field_of_study="Not specified",
            institution="Not specified"
        )

def extract_experience(candidate, text):
    """Extract work experience from resume text"""
    
    # Look for years of experience
    years_pattern = r'(\d+)\s*\+?\s*years?\s+(?:of\s+)?experience'
    years_match = re.search(years_pattern, text)
    
    if years_match:
        years = int(years_match.group(1))
        print(f"  Found: {years} years of experience")
        
        # Check context around the years mention
        match_start = max(0, years_match.start() - 50)
        match_end = min(len(text), years_match.end() + 50)
        context = text[match_start:match_end]
        
        # Must have positive indicators AND no negative indicators
        has_positive = any(pos in context for pos in POSITIVE_SKILL_INDICATORS)
        has_negative = any(neg in context for neg in NEGATIVE_INDICATORS)
        
        if has_positive and not has_negative:
            candidate.years_experience = years
            candidate.save()
            print(f"    Saved years: {years}")
        elif not has_negative:
            # If no explicit negative, still accept the years
            candidate.years_experience = years
            candidate.save()
            print(f"    Saved years: {years}")
    else:
        print("  No years of experience pattern found")
    
    # Common job titles in finance
    job_titles = [
        'investment analyst', 'portfolio manager', 'financial analyst',
        'investment manager', 'fund manager', 'asset manager',
        'relationship manager', 'investment advisor', 'senior analyst'
    ]
    
    # Check for Islamic finance experience
    is_islamic_finance = any(
        keyword in text and check_skill_context(text, keyword) 
        for keyword in ISLAMIC_FINANCE_KEYWORDS
    )
    
    print(f"  Islamic finance experience detected: {is_islamic_finance}")
    
    # Create experience entries for found job titles WITH CONTEXT
    for title in job_titles:
        if title in text:
            print(f"  Found job title: {title}")
            # Get context around the job title
            pattern = re.compile(r'\b' + re.escape(title) + r'\b', re.IGNORECASE)
            match = pattern.search(text)
            
            if match:
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                context = text[start:end]
                
                # Check if it's in work experience context
                experience_indicators = [
                    'worked as', 'role as', 'position as', 'served as',
                    'employed as', 'current', 'previous', 'years as',
                    'experience as', 'working as', 'worked at'
                ]
                
                has_exp_indicator = any(ind in context for ind in experience_indicators)
                has_negative = any(neg in context for neg in NEGATIVE_INDICATORS)
                
                if has_exp_indicator and not has_negative:
                    Experience.objects.create(
                        candidate=candidate,
                        company="Extracted from resume",
                        position=title.title(),
                        start_date=datetime.now().date(),
                        is_islamic_finance=is_islamic_finance
                    )
                    print(f"    Created experience record")
                    break
                else:
                    print(f"    Skipped (no valid context)")


def extract_skills(candidate, text):
    """Extract skills from resume text with enhanced context validation"""
    
    # Financial skills
    financial_skills = [
        'financial modeling', 'valuation', 'portfolio management',
        'risk management', 'excel', 'bloomberg', 'financial analysis',
        'investment analysis', 'equity research', 'fixed income',
        'derivatives', 'asset allocation', 'due diligence'
    ]
    
    # Islamic finance specific skills
    islamic_skills = [
        'sukuk structuring', 'sharia compliance', 'islamic banking',
        'takaful', 'mudarabah', 'musharakah', 'murabaha',
        'islamic finance', 'halal investment'
    ]
    
    # Technical skills
    technical_skills = [
        'python', 'sql', 'tableau', 'power bi', 'r programming',
        'vba', 'excel', 'bloomberg terminal', 'java', 'javascript',
        'c++', 'c#', 'ruby', 'php', 'swift', 'kotlin'
    ]
    
    # Extract financial skills WITH ENHANCED CONTEXT CHECK
    for skill in financial_skills:
        if skill in text:
            if check_skill_context(text, skill):
                Skill.objects.create(
                    candidate=candidate,
                    skill_name=skill.title(),
                    category='finance',
                    proficiency_level='intermediate'
                )
                print(f"  Added skill: {skill} (finance)")
    
    # Extract Islamic finance skills WITH ENHANCED CONTEXT CHECK
    for skill in islamic_skills:
        if skill in text:
            if check_skill_context(text, skill):
                Skill.objects.create(
                    candidate=candidate,
                    skill_name=skill.title(),
                    category='islamic_finance',
                    proficiency_level='advanced'
                )
                print(f"  Added skill: {skill} (islamic_finance)")
    
    # Extract technical skills WITH ENHANCED CONTEXT CHECK
    for skill in technical_skills:
        if skill in text:
            if check_skill_context(text, skill):
                Skill.objects.create(
                    candidate=candidate,
                    skill_name=skill.title(),
                    category='technical',
                    proficiency_level='intermediate'
                )
                print(f"  Added skill: {skill} (technical)")


def calculate_scores(candidate):
    """Calculate all component scores and total score"""
    
    # 1. EDUCATION SCORE (0-100, weight 25%)
    education_score = calculate_education_score(candidate)
    print(f"  Education score: {education_score}")
    
    # 2. EXPERIENCE SCORE (0-100, weight 30%)
    experience_score = calculate_experience_score(candidate)
    print(f"  Experience score: {experience_score}")
    
    # 3. SKILLS SCORE (0-100, weight 25%)
    skills_score = calculate_skills_score(candidate)
    print(f"  Skills score: {skills_score}")
    
    # 4. ISLAMIC FINANCE SCORE (0-100, weight 20%)
    islamic_finance_score = calculate_islamic_finance_score(candidate)
    print(f"  Islamic Finance score: {islamic_finance_score}")
    
    # Calculate weighted total (RULE-BASED SCORE ONLY)
    final_score = (
        (education_score * 0.25) +
        (experience_score * 0.30) +
        (skills_score * 0.25) +
        (islamic_finance_score * 0.20)
    )
    
    print(f"  Weighted total: {final_score}")
    
    # Create or update score record
    Score.objects.update_or_create(
        candidate=candidate,
        defaults={
            'education_score': education_score,
            'experience_score': experience_score,
            'skills_score': skills_score,
            'islamic_finance_score': islamic_finance_score,
            'total_score': round(final_score, 2)
        }
    )
    
    return final_score


def calculate_education_score(candidate):
    """Calculate education component score"""
    
    educations = candidate.education.all()
    
    if not educations.exists():
        return 0
    
    # Get highest degree
    highest_score = 0
    for edu in educations:
        degree_lower = edu.degree.lower()
        for degree_type, degree_score in DEGREE_SCORES.items():
            if degree_type in degree_lower:
                highest_score = max(highest_score, degree_score)
        
        # Bonus for Islamic finance certification
        if edu.has_islamic_finance_cert:
            highest_score = min(100, highest_score + 20)
    
    return highest_score


def calculate_experience_score(candidate):
    """Calculate experience component score"""
    years = candidate.years_experience
    
    # Score based on years
    if years >= 10:
        score = 100
    elif years >= 7:
        score = 90
    elif years >= 5:
        score = 80
    elif years >= 3:
        score = 70
    elif years >= 1:
        score = 50
    else:
        score = 30
    
    # Bonus for Islamic finance experience
    if candidate.experience.filter(is_islamic_finance=True).exists():
        score = min(100, score + 15)
    
    return score


def calculate_skills_score(candidate):
    """Calculate skills component score"""
    skills = candidate.skills.all()
    skill_count = skills.count()
    
    if skill_count == 0:
        return 0
    
    # Base score from number of skills
    if skill_count >= 10:
        score = 100
    elif skill_count >= 7:
        score = 85
    elif skill_count >= 5:
        score = 70
    elif skill_count >= 3:
        score = 55
    else:
        score = 40
    
    # Bonus for Islamic finance skills
    if_skills = skills.filter(category='islamic_finance').count()
    if if_skills > 0:
        score = min(100, score + (if_skills * 10))
    
    return score


def calculate_islamic_finance_score(candidate):
    """Calculate Islamic finance expertise score"""
    score = 0
    resume_text = candidate.resume.parsed_text.lower()
    
    # 1. Islamic finance certifications (40 points)
    if candidate.education.filter(has_islamic_finance_cert=True).exists():
        score += 40
    
    # 2. Islamic finance experience (30 points)
    if candidate.experience.filter(is_islamic_finance=True).exists():
        score += 30
    
    # 3. Islamic finance skills (20 points)
    if_skills = candidate.skills.filter(category='islamic_finance').count()
    score += min(20, if_skills * 5)
    
    # 4. Keyword density (10 points) - WITH CONTEXT CHECK
    valid_keyword_count = sum(
        1 for keyword in ISLAMIC_FINANCE_KEYWORDS 
        if keyword in resume_text and check_skill_context(resume_text, keyword)
    )
    score += min(10, valid_keyword_count * 2)
    
    return min(100, score)