# recruitment/job_matching.py
"""
JOB-CANDIDATE MATCHING ENGINE
=============================
Based on real ATS design principles:
- Parse CV once, score per job
- Job-specific weights and requirements
- Required skills gating, preferred skills boosting
- Explainable decisions
"""

from dataclasses import dataclass, field
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

# Generic skills that shouldn't dominate ranking
GENERIC_SKILLS = {
    'communication', 'teamwork', 'time management', 'teaching',
    'project management', 'leadership', 'problem solving',
    'critical thinking', 'adaptability', 'creativity',
    'attention to detail', 'organization', 'interpersonal skills',
    'english', 'arabic', 'presentation skills'
}

# Finance domain-core skills (high value for finance jobs)
FINANCE_CORE_SKILLS = {
    'risk management', 'financial modeling', 'investment analysis',
    'credit analysis', 'due diligence', 'asset management',
    'financial reporting', 'budgeting', 'valuation', 'portfolio management',
    'equity research', 'mergers and acquisitions', 'private equity',
    'corporate finance', 'financial analysis', 'trading',
    'islamic finance', 'sukuk', 'takaful', 'shariah compliance',
    'islamic banking', 'mudaraba', 'musharaka', 'ijara', 'aaoifi standards'
}


@dataclass
class MatchResult:
    """Result of matching a candidate to a job."""
    job_fit_score: int = 0
    matched_required: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    matched_preferred: List[str] = field(default_factory=list)
    skills_score: float = 0.0
    experience_score: float = 0.0
    education_score: float = 0.0
    domain_score: float = 0.0
    experience_met: bool = True
    summary: str = ""


def get_candidate_skills(candidate) -> set:
    """Extract all skill names from a candidate."""
    skills = set()
    if hasattr(candidate, 'extracted_skills'):
        for extracted in candidate.extracted_skills.all():
            # Field is 'skill' - a ForeignKey to SkillDefinition
            if hasattr(extracted, 'skill') and extracted.skill:
                skills.add(extracted.skill.canonical_name.lower())
    return skills


def experience_gate(candidate_years: int, min_required: int) -> Tuple[bool, float]:
    """Check if candidate meets experience requirement."""
    if min_required == 0:
        return True, 1.0
    if candidate_years >= min_required:
        return True, 1.0
    gap = min_required - candidate_years
    if gap <= 1:
        return False, 0.8
    elif gap <= 2:
        return False, 0.6
    else:
        return False, 0.3


def match_required_skills(candidate_skills: set, required_skills) -> Tuple[List[str], List[str]]:
    """Match candidate skills against required skills."""
    matched, missing = [], []
    for skill in required_skills:
        skill_name = skill.canonical_name.lower()
        if skill_name in candidate_skills:
            matched.append(skill.canonical_name)
        else:
            found = False
            for cand_skill in candidate_skills:
                if skill_name in cand_skill or cand_skill in skill_name:
                    matched.append(skill.canonical_name)
                    found = True
                    break
            if not found:
                missing.append(skill.canonical_name)
    return matched, missing


def match_preferred_skills(candidate_skills: set, preferred_skills) -> List[str]:
    """Match candidate skills against preferred skills."""
    matched = []
    for skill in preferred_skills:
        skill_name = skill.canonical_name.lower()
        if skill_name in candidate_skills:
            matched.append(skill.canonical_name)
        else:
            for cand_skill in candidate_skills:
                if skill_name in cand_skill or cand_skill in skill_name:
                    matched.append(skill.canonical_name)
                    break
    return matched


def calculate_skills_score(matched_required, missing_required, matched_preferred, total_preferred, job_domain='') -> float:
    """
    Calculate skills score (0-100) with intelligent weighting.
    - Generic required skills (communication, teamwork) = low weight
    - Domain-core skills (finance, risk) = high weight
    - Preferred domain skills = boost
    """
    # Separate matched required into core vs generic
    matched_core_required = [s for s in matched_required if s.lower() not in GENERIC_SKILLS]
    matched_generic_required = [s for s in matched_required if s.lower() in GENERIC_SKILLS]
    
    missing_core_required = [s for s in missing_required if s.lower() not in GENERIC_SKILLS]
    missing_generic_required = [s for s in missing_required if s.lower() in GENERIC_SKILLS]
    
    total_core_required = len(matched_core_required) + len(missing_core_required)
    total_generic_required = len(matched_generic_required) + len(missing_generic_required)
    
    # Core required skills = 50% of score
    if total_core_required > 0:
        core_ratio = len(matched_core_required) / total_core_required
        core_score = core_ratio * 50
    else:
        core_score = 25  # No core required = modest base
    
    # Preferred skills = 40% of score (domain-core preferred get bonus)
    preferred_score = 0
    if total_preferred > 0:
        for skill in matched_preferred:
            skill_lower = skill.lower()
            if skill_lower in FINANCE_CORE_SKILLS:
                preferred_score += 2.0  # Finance-core = double weight
            else:
                preferred_score += 1.0
        
        # Normalize: max possible = total_preferred * 2 (if all are finance-core)
        max_possible = total_preferred * 1.5  # Balanced expectation
        preferred_score = min(40, (preferred_score / max_possible) * 40)
    else:
        preferred_score = 10  # No preferred defined = small base
    
    # Generic required = 10% of score (low priority)
    if total_generic_required > 0:
        generic_ratio = len(matched_generic_required) / total_generic_required
        generic_score = generic_ratio * 10
    else:
        generic_score = 5
    
    return min(100, core_score + preferred_score + generic_score)


def calculate_experience_score(candidate_years: int, min_required: int) -> float:
    """Calculate experience score (0-100)."""
    if min_required == 0:
        if candidate_years >= 10:
            return 100
        elif candidate_years >= 5:
            return 85
        elif candidate_years >= 2:
            return 70
        return 50
    
    if candidate_years >= min_required:
        return 100 if (candidate_years - min_required) <= 10 else 85
    return max(20, (candidate_years / min_required) * 100)


def calculate_education_score(candidate) -> float:
    """Calculate education score based on candidate's education."""
    if not hasattr(candidate, 'education'):
        return 50
    educations = candidate.education.all()
    if not educations.exists():
        return 50
    
    degree_scores = {
        'phd': 100, 'doctorate': 100, 'master': 85, 'mba': 85,
        'bachelor': 70, 'bsc': 70, 'ba': 70, 'diploma': 55, 'certificate': 40
    }
    highest = 30
    for edu in educations:
        degree = getattr(edu, 'degree', '').lower()
        for key, score in degree_scores.items():
            if key in degree and score > highest:
                highest = score
    return highest


def calculate_domain_score(candidate, job_domain: str) -> float:
    """Calculate domain relevance score."""
    if not job_domain:
        return 50
    job_domain_lower = job_domain.lower()
    
    if hasattr(candidate, 'experience'):
        for exp in candidate.experience.all():
            title = (getattr(exp, 'title', '') or '').lower()
            company = (getattr(exp, 'company', '') or '').lower()
            for word in job_domain_lower.replace('_', ' ').split():
                if len(word) > 3 and (word in title or word in company):
                    return 100
    
    current = (getattr(candidate, 'current_position', '') or '').lower()
    if current:
        for word in job_domain_lower.replace('_', ' ').split():
            if len(word) > 3 and word in current:
                return 80
    return 40


def match_candidate_to_job(candidate, job_posting) -> MatchResult:
    """Main matching function - scores a candidate against a job."""
    role_profile = job_posting.role_profile
    
    min_experience = 0
    job_domain = ''
    required_skills = []
    preferred_skills = []
    
    if role_profile:
        min_experience = role_profile.min_experience or 0
        job_domain = role_profile.domain or ''
        required_skills = role_profile.required_skills.all()
        preferred_skills = role_profile.preferred_skills.all()
    
    candidate_years = candidate.years_experience or 0
    candidate_skills = get_candidate_skills(candidate)
    
    exp_met, exp_multiplier = experience_gate(candidate_years, min_experience)
    matched_req, missing_req = match_required_skills(candidate_skills, required_skills)
    matched_pref = match_preferred_skills(candidate_skills, preferred_skills)
    
    skills_score = calculate_skills_score(matched_req, missing_req, matched_pref, len(list(preferred_skills)), job_domain)
    experience_score = calculate_experience_score(candidate_years, min_experience)
    education_score = calculate_education_score(candidate)
    domain_score = calculate_domain_score(candidate, job_domain)
    
    if not exp_met:
        skills_score *= exp_multiplier
    
    # Get weights from job posting
    weights = {
        'education': job_posting.education_weight or 0.15,
        'experience': job_posting.experience_weight or 0.20,
        'skills': job_posting.skills_weight or 0.30,
        'hard_skills': job_posting.hard_skills_weight or 0.15,
        'soft_skills': job_posting.soft_skills_weight or 0.10,
        'domain': job_posting.domain_weight or 0.10,
    }
    
    # Skills weight includes hard + soft
    total_skills_weight = weights['skills'] + weights['hard_skills'] + weights['soft_skills']
    
    total_score = (
        education_score * weights['education'] +
        experience_score * weights['experience'] +
        skills_score * total_skills_weight +
        domain_score * weights['domain']
    )
    
    # Domain-specific boost for candidates WITH finance skills in finance jobs
    job_domain_lower = job_domain.lower() if job_domain else ''
    if 'islamic' in job_domain_lower or 'finance' in job_domain_lower or 'investment' in job_domain_lower or 'banking' in job_domain_lower or 'equity' in job_domain_lower:
        # Check if candidate has finance-related skills
        finance_keywords = {
            'finance', 'financial', 'banking', 'investment', 'islamic', 
            'sukuk', 'takaful', 'shariah', 'accounting', 'audit',
            'risk', 'credit', 'asset', 'portfolio', 'equity', 'trading',
            'valuation', 'budget', 'treasury', 'capital', 'fund',
            'analyst', 'due diligence', 'compliance', 'reporting'
        }
        has_finance = any(
            any(kw in skill for kw in finance_keywords) 
            for skill in candidate_skills
        )
        if has_finance:
            total_score *= 1.3  # 30% BOOST for having finance background
        else:
            total_score *= 0.6  # 40% penalty for NO finance background
    
    job_fit_score = min(100, max(0, round(total_score)))
    
    summary_parts = [f"Score: {job_fit_score}%"]
    if required_skills:
        summary_parts.append(f"Skills: {len(matched_req)}/{len(matched_req) + len(missing_req)} required")
    if not exp_met:
        summary_parts.append(f"Experience: {candidate_years}yr (need {min_experience}yr)")
    else:
        summary_parts.append(f"Experience: {candidate_years}yr ✓")
    
    return MatchResult(
        job_fit_score=job_fit_score,
        matched_required=matched_req,
        missing_required=missing_req,
        matched_preferred=matched_pref,
        skills_score=skills_score,
        experience_score=experience_score,
        education_score=education_score,
        domain_score=domain_score,
        experience_met=exp_met,
        summary=" | ".join(summary_parts)
    )


def match_all_candidates(job_posting) -> List[Tuple]:
    """Match all candidates to a job, return sorted by score."""
    from .models import Candidate
    results = []
    for candidate in Candidate.objects.all():
        try:
            result = match_candidate_to_job(candidate, job_posting)
            results.append((candidate, result))
        except Exception as e:
            logger.error(f"Error matching candidate {candidate.id}: {e}")
            results.append((candidate, MatchResult(job_fit_score=0, summary=f"Error: {e}")))
    results.sort(key=lambda x: x[1].job_fit_score, reverse=True)
    return results


def save_application(candidate, job_posting, match_result: MatchResult):
    """Save match result to CandidateJobApplication."""
    from .models import CandidateJobApplication
    application, created = CandidateJobApplication.objects.update_or_create(
        candidate=candidate,
        job_posting=job_posting,
        defaults={'job_fit_score': match_result.job_fit_score}
    )
    return application