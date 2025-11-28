"""
Analytics Module
Provides advanced analytics and reporting for recruitment system
Generates insights, trends, and predictive metrics
"""

from .models import Candidate, Score, Skill, Education, Experience
from django.db.models import Avg, Count, Q, Max, Min
from datetime import datetime, timedelta
import json


class RecruitmentAnalytics:
    """
    Advanced analytics for recruitment data
    Provides insights on hiring trends, skill demands, and success patterns
    """
    
    def get_hiring_funnel_metrics(self):
        """
        Calculate conversion rates through hiring funnel
        """
        total_applications = Candidate.objects.count()
        
        if total_applications == 0:
            return {
                'status': 'no_data',
                'message': 'No candidates in system'
            }
        
        status_counts = {}
        for status, _ in Candidate.STATUS_CHOICES:
            status_counts[status] = Candidate.objects.filter(status=status).count()
        
        # Calculate conversion rates
        metrics = {
            'total_applications': total_applications,
            'received': status_counts.get('received', 0),
            'screening': status_counts.get('screening', 0),
            'interview': status_counts.get('interview', 0),
            'offered': status_counts.get('offered', 0),
            'hired': status_counts.get('hired', 0),
            'rejected': status_counts.get('rejected', 0)
        }
        
        # Calculate percentages
        if total_applications > 0:
            metrics['screening_rate'] = round(
                (metrics['screening'] / total_applications) * 100, 1
            )
            metrics['interview_rate'] = round(
                (metrics['interview'] / total_applications) * 100, 1
            )
            metrics['offer_rate'] = round(
                (metrics['offered'] / total_applications) * 100, 1
            )
            metrics['hire_rate'] = round(
                (metrics['hired'] / total_applications) * 100, 1
            )
            metrics['rejection_rate'] = round(
                (metrics['rejected'] / total_applications) * 100, 1
            )
        
        return metrics
    
    def get_top_skills(self, limit=10):
        """
        Identify most common skills among candidates
        """
        skills = Skill.objects.values('skill_name', 'category').annotate(
            count=Count('id')
        ).order_by('-count')[:limit]
        
        return list(skills)
    
    def get_islamic_finance_penetration(self):
        """
        Analyze Islamic Finance expertise across candidate pool
        """
        total_candidates = Candidate.objects.count()
        
        if total_candidates == 0:
            return {'status': 'no_data'}
        
        # Candidates with IF education
        if_education_count = Candidate.objects.filter(
            education__has_islamic_finance_cert=True
        ).distinct().count()
        
        # Candidates with IF experience
        if_experience_count = Candidate.objects.filter(
            experience__is_islamic_finance=True
        ).distinct().count()
        
        # Candidates with IF skills
        if_skills_count = Candidate.objects.filter(
            skills__category='islamic_finance'
        ).distinct().count()
        
        # Candidates with any IF background
        if_any_count = Candidate.objects.filter(
            Q(education__has_islamic_finance_cert=True) |
            Q(experience__is_islamic_finance=True) |
            Q(skills__category='islamic_finance')
        ).distinct().count()
        
        return {
            'total_candidates': total_candidates,
            'if_education': if_education_count,
            'if_experience': if_experience_count,
            'if_skills': if_skills_count,
            'if_any_background': if_any_count,
            'if_penetration_rate': round((if_any_count / total_candidates) * 100, 1)
        }
    
    def get_score_statistics(self):
        """
        Calculate comprehensive scoring statistics
        """
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
        
        # Round all values
        for key in stats:
            if stats[key] is not None:
                stats[key] = round(stats[key], 2)
        
        stats['total_scored'] = scores.count()
        
        # Score distribution
        stats['distribution'] = {
            'excellent': scores.filter(total_score__gte=80).count(),
            'good': scores.filter(total_score__gte=60, total_score__lt=80).count(),
            'average': scores.filter(total_score__gte=40, total_score__lt=60).count(),
            'below_average': scores.filter(total_score__lt=40).count()
        }
        
        return stats
    
    def get_education_analysis(self):
        """
        Analyze education levels in candidate pool
        """
        education_counts = Education.objects.values('degree').annotate(
            count=Count('id')
        ).order_by('-count')
        
        total = sum(item['count'] for item in education_counts)
        
        # Add percentages
        for item in education_counts:
            item['percentage'] = round((item['count'] / total) * 100, 1) if total > 0 else 0
        
        return {
            'total_records': total,
            'breakdown': list(education_counts)
        }
    
    def get_experience_analysis(self):
        """
        Analyze years of experience distribution
        """
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
        
        # Add percentages
        for key in experience_distribution:
            count = experience_distribution[key]
            experience_distribution[key] = {
                'count': count,
                'percentage': round((count / total) * 100, 1) if total > 0 else 0
            }
        
        # Average years
        experience_distribution['average_years'] = round(
            candidates.aggregate(Avg('years_experience'))['years_experience__avg'] or 0,
            1
        )
        
        return experience_distribution
    
    def generate_executive_summary(self):
        """
        Generate executive summary dashboard
        """
        return {
            'hiring_funnel': self.get_hiring_funnel_metrics(),
            'score_statistics': self.get_score_statistics(),
            'islamic_finance': self.get_islamic_finance_penetration(),
            'top_skills': self.get_top_skills(limit=5),
            'education_analysis': self.get_education_analysis(),
            'experience_analysis': self.get_experience_analysis(),
            'generated_at': datetime.now().isoformat()
        }


# Global analytics instance
analytics_engine = RecruitmentAnalytics()