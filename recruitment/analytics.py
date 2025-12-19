"""
Analytics Module - F11 DIVERSITY METRICS (Self-Reported, PDPL-Compliant)

IMPORTANT: Diversity data is collected via OPTIONAL self-reported fields.
NO inference from names or CV content is performed.

This design aligns with:
- GDPR Art. 5(1)(c) - Data minimization
- Bahrain PDPL principles
- Industry best practices (Workday, Greenhouse, Lever)

References:
- Santamaria & Mihaljevic (2018): Name-based gender inference is unreliable
- Karimi et al. (2016): Cultural variation significantly reduces inference accuracy
"""

from .models import Candidate, Score, Skill, Education, Experience, ExtractedSkill
from django.db.models import Avg, Count, Q, Max, Min
from datetime import datetime
from collections import Counter


class RecruitmentAnalytics:
    """
    Advanced analytics for recruitment data.
    Diversity metrics use SELF-REPORTED data only (not inference).
    """
    
    def get_hiring_funnel_metrics(self):
        """Calculate conversion rates through hiring funnel"""
        total_applications = Candidate.objects.count()
        
        if total_applications == 0:
            return {'status': 'no_data', 'message': 'No candidates in system'}
        
        status_counts = {}
        for status, _ in Candidate.STATUS_CHOICES:
            status_counts[status] = Candidate.objects.filter(status=status).count()
        
        metrics = {
            'total_applications': total_applications,
            'received': status_counts.get('received', 0),
            'screening': status_counts.get('screening', 0),
            'interview': status_counts.get('interview', 0),
            'offered': status_counts.get('offered', 0),
            'hired': status_counts.get('hired', 0),
            'rejected': status_counts.get('rejected', 0)
        }
        
        if total_applications > 0:
            metrics['screening_rate'] = round((metrics['screening'] / total_applications) * 100, 1)
            metrics['interview_rate'] = round((metrics['interview'] / total_applications) * 100, 1)
            metrics['offer_rate'] = round((metrics['offered'] / total_applications) * 100, 1)
            metrics['hire_rate'] = round((metrics['hired'] / total_applications) * 100, 1)
            metrics['rejection_rate'] = round((metrics['rejected'] / total_applications) * 100, 1)
        
        return metrics
    
    def get_top_skills(self, limit=10):
        """Identify most common skills among candidates"""
        skills = ExtractedSkill.objects.values(
            'skill__canonical_name', 
            'skill__category__name'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:limit]
        
        result = []
        for s in skills:
            result.append({
                'skill_name': s['skill__canonical_name'],
                'category': s['skill__category__name'],
                'count': s['count']
            })
        
        return result
    
    def get_islamic_finance_penetration(self):
        """Analyze Islamic Finance expertise across candidate pool"""
        total_candidates = Candidate.objects.count()
        
        if total_candidates == 0:
            return {'status': 'no_data'}
        
        if_education_count = Candidate.objects.filter(
            education__has_islamic_finance_cert=True
        ).distinct().count()
        
        if_experience_count = Candidate.objects.filter(
            experience__is_islamic_finance=True
        ).distinct().count()
        
        if_skills_count = Candidate.objects.filter(
            extracted_skills__skill__category__name='islamic_finance'
        ).distinct().count()
        
        if_any_count = Candidate.objects.filter(
            Q(education__has_islamic_finance_cert=True) |
            Q(experience__is_islamic_finance=True) |
            Q(extracted_skills__skill__category__name='islamic_finance')
        ).distinct().count()
        
        return {
            'total_candidates': total_candidates,
            'if_education': if_education_count,
            'if_experience': if_experience_count,
            'if_skills': if_skills_count,
            'if_any_background': if_any_count,
            'if_penetration_rate': round((if_any_count / total_candidates) * 100, 1) if total_candidates > 0 else 0
        }
    
    def get_score_statistics(self):
        """Calculate comprehensive scoring statistics"""
        scores = Score.objects.all()
        
        if not scores.exists():
            return {'status': 'no_data'}
        
        stats = scores.aggregate(
            avg_total=Avg('total_score'),
            max_total=Max('total_score'),
            min_total=Min('total_score'),
            avg_education=Avg('education_score'),
            avg_experience=Avg('experience_score'),
            avg_skills=Avg('skills_score'),
            avg_if=Avg('islamic_finance_score')
        )
        
        for key in stats:
            if stats[key] is not None:
                stats[key] = round(stats[key], 2)
        
        stats['total_scored'] = scores.count()
        stats['distribution'] = {
            'excellent': scores.filter(total_score__gte=80).count(),
            'good': scores.filter(total_score__gte=60, total_score__lt=80).count(),
            'average': scores.filter(total_score__gte=40, total_score__lt=60).count(),
            'below_average': scores.filter(total_score__lt=40).count()
        }
        
        return stats
    
    def get_education_analysis(self):
        """Analyze education levels in candidate pool"""
        education_counts = Education.objects.values('degree').annotate(
            count=Count('id')
        ).order_by('-count')
        
        total = sum(item['count'] for item in education_counts)
        
        for item in education_counts:
            item['percentage'] = round((item['count'] / total) * 100, 1) if total > 0 else 0
        
        return {
            'total_records': total,
            'breakdown': list(education_counts)
        }
    
    def get_experience_analysis(self):
        """Analyze years of experience distribution"""
        candidates = Candidate.objects.all()
        
        if not candidates.exists():
            return {'status': 'no_data'}
        
        experience_distribution = {
            'entry_level': candidates.filter(years_experience__lt=2).count(),
            'junior': candidates.filter(years_experience__gte=2, years_experience__lt=5).count(),
            'mid_level': candidates.filter(years_experience__gte=5, years_experience__lt=10).count(),
            'senior': candidates.filter(years_experience__gte=10).count()
        }
        
        total = candidates.count()
        
        for key in experience_distribution:
            count = experience_distribution[key]
            experience_distribution[key] = {
                'count': count,
                'percentage': round((count / total) * 100, 1) if total > 0 else 0
            }
        
        experience_distribution['average_years'] = round(
            candidates.aggregate(Avg('years_experience'))['years_experience__avg'] or 0, 1
        )
        
        return experience_distribution
    
    # ============================================================
    # F11: DIVERSITY METRICS (SELF-REPORTED, NOT INFERRED)
    # ============================================================
    def get_diversity_metrics(self):
        """
        Calculate diversity metrics using SELF-REPORTED data only.
        
        IMPORTANT: This method does NOT infer gender or nationality from
        names or CV content. It only reports what candidates voluntarily
        disclosed via optional form fields.
        
        This design choice is based on:
        1. Research showing name-based inference fails across cultures
           (Santamaria & Mihaljevic, 2018; Karimi et al., 2016)
        2. GDPR/PDPL data minimization principles
        3. Industry best practices (Workday, Greenhouse, Lever)
        
        The data is NEVER used for scoring or ranking decisions.
        """
        candidates = Candidate.objects.all()
        
        if not candidates.exists():
            return {'status': 'no_data', 'message': 'No candidates in system'}
        
        total = candidates.count()
        
        def calc_pct(count):
            return round((count / total) * 100, 1) if total > 0 else 0
        
        # Count self-reported gender
        gender_counts = Counter()
        for c in candidates:
            gender = getattr(c, 'gender', '') or ''
            if gender == '':
                gender = 'not_disclosed'
            gender_counts[gender] += 1
        
        # Count self-reported nationality
        nationality_counts = Counter()
        for c in candidates:
            nationality = getattr(c, 'nationality', '') or ''
            if nationality == '':
                nationality = 'not_disclosed'
            nationality_counts[nationality] += 1
        
        # Calculate disclosure rates
        gender_disclosed = total - gender_counts.get('not_disclosed', 0)
        nationality_disclosed = total - nationality_counts.get('not_disclosed', 0)
        
        return {
            'status': 'ok',
            'total_candidates': total,
            'data_source': 'self_reported',
            'gender_distribution': {
                'male': {
                    'count': gender_counts.get('male', 0),
                    'percentage': calc_pct(gender_counts.get('male', 0))
                },
                'female': {
                    'count': gender_counts.get('female', 0),
                    'percentage': calc_pct(gender_counts.get('female', 0))
                },
                'non_binary': {
                    'count': gender_counts.get('non_binary', 0),
                    'percentage': calc_pct(gender_counts.get('non_binary', 0))
                },
                'other': {
                    'count': gender_counts.get('other', 0),
                    'percentage': calc_pct(gender_counts.get('other', 0))
                },
                'not_disclosed': {
                    'count': gender_counts.get('not_disclosed', 0),
                    'percentage': calc_pct(gender_counts.get('not_disclosed', 0))
                }
            },
            'nationality_distribution': {
                'bahraini': {
                    'count': nationality_counts.get('bahraini', 0),
                    'percentage': calc_pct(nationality_counts.get('bahraini', 0)),
                    'label': 'Bahraini'
                },
                'gcc': {
                    'count': nationality_counts.get('gcc', 0),
                    'percentage': calc_pct(nationality_counts.get('gcc', 0)),
                    'label': 'GCC National'
                },
                'south_asian': {
                    'count': nationality_counts.get('south_asian', 0),
                    'percentage': calc_pct(nationality_counts.get('south_asian', 0)),
                    'label': 'South Asian'
                },
                'middle_eastern': {
                    'count': nationality_counts.get('middle_eastern', 0),
                    'percentage': calc_pct(nationality_counts.get('middle_eastern', 0)),
                    'label': 'Middle Eastern'
                },
                'western': {
                    'count': nationality_counts.get('western', 0),
                    'percentage': calc_pct(nationality_counts.get('western', 0)),
                    'label': 'Western'
                },
                'other': {
                    'count': nationality_counts.get('other', 0),
                    'percentage': calc_pct(nationality_counts.get('other', 0)),
                    'label': 'Other'
                },
                'not_disclosed': {
                    'count': nationality_counts.get('not_disclosed', 0),
                    'percentage': calc_pct(nationality_counts.get('not_disclosed', 0)),
                    'label': 'Not Disclosed'
                }
            },
            'disclosure_rates': {
                'gender': calc_pct(gender_disclosed),
                'nationality': calc_pct(nationality_disclosed)
            },
            'notice': 'All diversity data is voluntarily self-reported by candidates. '
                      'This information is used for aggregate analytics only and is '
                      'explicitly excluded from scoring and ranking decisions.'
        }
    
    def generate_executive_summary(self):
        """Generate executive summary dashboard"""
        return {
            'hiring_funnel': self.get_hiring_funnel_metrics(),
            'score_statistics': self.get_score_statistics(),
            'islamic_finance': self.get_islamic_finance_penetration(),
            'top_skills': self.get_top_skills(limit=5),
            'education_analysis': self.get_education_analysis(),
            'experience_analysis': self.get_experience_analysis(),
            'diversity_metrics': self.get_diversity_metrics(),
            'generated_at': datetime.now().isoformat()
        }
    
    def generate_comprehensive_report(self):
        """Generate comprehensive analytics report - called by views.py"""
        return self.generate_executive_summary()


# Global analytics instance
analytics_engine = RecruitmentAnalytics()