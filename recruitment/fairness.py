"""
Fairness Framework Module
Implements bias detection and fairness metrics for AI scoring system
Ensures equitable evaluation across demographic groups
"""

from .models import Candidate, Score
from django.db.models import Avg, Count
import statistics


class FairnessAnalyzer:
    """
    Analyzes scoring patterns for potential bias
    Implements fairness metrics and recommendations
    """
    
    def __init__(self):
        self.fairness_threshold = 0.8  # 80% fairness score required
        
    def analyze_score_distribution(self):
        """
        Analyze overall score distribution
        Returns statistics and potential bias indicators
        """
        all_scores = Score.objects.all().values_list('total_score', flat=True)
        
        if len(all_scores) < 10:
            return {
                'status': 'insufficient_data',
                'message': 'Need at least 10 scored candidates for fairness analysis',
                'sample_size': len(all_scores)
            }
        
        scores_list = list(all_scores)
        
        analysis = {
            'total_candidates': len(scores_list),
            'mean_score': round(statistics.mean(scores_list), 2),
            'median_score': round(statistics.median(scores_list), 2),
            'std_deviation': round(statistics.stdev(scores_list), 2) if len(scores_list) > 1 else 0,
            'min_score': min(scores_list),
            'max_score': max(scores_list),
            'score_range': max(scores_list) - min(scores_list)
        }
        
        # Check for concerning patterns
        analysis['concerns'] = []
        
        # Check 1: Too narrow score range
        if analysis['score_range'] < 20:
            analysis['concerns'].append(
                "Score range is very narrow - system may not be differentiating candidates effectively"
            )
        
        # Check 2: Too high average (possible grade inflation)
        if analysis['mean_score'] > 80:
            analysis['concerns'].append(
                "Average score is very high - scoring criteria may be too lenient"
            )
        
        # Check 3: Too low average (possibly too strict)
        if analysis['mean_score'] < 30:
            analysis['concerns'].append(
                "Average score is very low - scoring criteria may be too strict"
            )
        
        # Check 4: High standard deviation
        if analysis['std_deviation'] > 25:
            analysis['concerns'].append(
                "High score variation detected - scoring may be inconsistent"
            )
        
        analysis['fairness_passed'] = len(analysis['concerns']) == 0
        
        return analysis
    
    def detect_keyword_bias(self):
        """
        Detect if certain keywords disproportionately affect scores
        """
        # Get candidates with Islamic Finance keywords
        if_candidates = Candidate.objects.filter(
            experience__is_islamic_finance=True
        ).distinct()
        
        non_if_candidates = Candidate.objects.exclude(
            id__in=if_candidates.values_list('id', flat=True)
        )
        
        if if_candidates.count() < 3 or non_if_candidates.count() < 3:
            return {
                'status': 'insufficient_data',
                'message': 'Need more candidates in both groups for comparison'
            }
        
        # Compare average scores
        if_avg = Score.objects.filter(
            candidate__in=if_candidates
        ).aggregate(Avg('total_score'))['total_score__avg'] or 0
        
        non_if_avg = Score.objects.filter(
            candidate__in=non_if_candidates
        ).aggregate(Avg('total_score'))['total_score__avg'] or 0
        
        score_difference = abs(if_avg - non_if_avg)
        
        analysis = {
            'islamic_finance_avg': round(if_avg, 2),
            'non_islamic_finance_avg': round(non_if_avg, 2),
            'score_difference': round(score_difference, 2),
            'if_candidate_count': if_candidates.count(),
            'non_if_candidate_count': non_if_candidates.count()
        }
        
        # Check for significant bias
        if score_difference > 15:
            analysis['bias_detected'] = True
            analysis['recommendation'] = (
                "Significant score difference detected between Islamic Finance "
                "and non-Islamic Finance candidates. Review scoring weights."
            )
        else:
            analysis['bias_detected'] = False
            analysis['recommendation'] = "No significant keyword bias detected"
        
        return analysis
    
    def check_experience_bias(self):
        """
        Check if years of experience creates unfair advantage
        """
        # Group candidates by experience ranges
        junior = Candidate.objects.filter(years_experience__lt=3)
        mid_level = Candidate.objects.filter(years_experience__gte=3, years_experience__lt=7)
        senior = Candidate.objects.filter(years_experience__gte=7)
        
        if junior.count() < 2 or mid_level.count() < 2 or senior.count() < 2:
            return {
                'status': 'insufficient_data',
                'message': 'Need more candidates in each experience level'
            }
        
        junior_avg = Score.objects.filter(candidate__in=junior).aggregate(
            Avg('total_score'))['total_score__avg'] or 0
        mid_avg = Score.objects.filter(candidate__in=mid_level).aggregate(
            Avg('total_score'))['total_score__avg'] or 0
        senior_avg = Score.objects.filter(candidate__in=senior).aggregate(
            Avg('total_score'))['total_score__avg'] or 0
        
        analysis = {
            'junior_avg': round(junior_avg, 2),
            'mid_level_avg': round(mid_avg, 2),
            'senior_avg': round(senior_avg, 2),
            'junior_count': junior.count(),
            'mid_level_count': mid_level.count(),
            'senior_count': senior.count()
        }
        
        # Check if progression is reasonable
        if senior_avg < mid_avg or mid_avg < junior_avg:
            analysis['concern'] = "Score progression doesn't align with experience levels"
        else:
            analysis['concern'] = None
        
        # Check if experience weight is too high
        experience_gap = senior_avg - junior_avg
        if experience_gap > 50:
            analysis['bias_detected'] = True
            analysis['recommendation'] = (
                "Experience weight may be too high. "
                f"Senior candidates score {experience_gap} points higher on average."
            )
        else:
            analysis['bias_detected'] = False
            analysis['recommendation'] = "Experience weighting appears balanced"
        
        return analysis
    
    def generate_fairness_report(self):
        """
        Generate comprehensive fairness report
        """
        report = {
            'overall_distribution': self.analyze_score_distribution(),
            'keyword_bias': self.detect_keyword_bias(),
            'experience_bias': self.check_experience_bias(),
            'timestamp': None
        }
        
        # Calculate overall fairness score
        concerns_count = 0
        if report['overall_distribution'].get('concerns'):
            concerns_count += len(report['overall_distribution']['concerns'])
        if report['keyword_bias'].get('bias_detected'):
            concerns_count += 1
        if report['experience_bias'].get('bias_detected'):
            concerns_count += 1
        
        # Fairness score (0-100)
        max_concerns = 6  # Maximum possible concerns
        fairness_score = max(0, 100 - (concerns_count * 100 / max_concerns))
        
        report['fairness_score'] = round(fairness_score, 2)
        report['fairness_grade'] = self._get_fairness_grade(fairness_score)
        report['recommendations'] = self._generate_recommendations(report)
        
        return report
    
    def _get_fairness_grade(self, score):
        """Convert fairness score to letter grade"""
        if score >= 90:
            return 'A - Excellent'
        elif score >= 80:
            return 'B - Good'
        elif score >= 70:
            return 'C - Acceptable'
        elif score >= 60:
            return 'D - Needs Improvement'
        else:
            return 'F - Significant Issues'
    
    def _generate_recommendations(self, report):
        """Generate actionable recommendations"""
        recommendations = []
        
        # Overall distribution recommendations
        if report['overall_distribution'].get('concerns'):
            recommendations.extend(report['overall_distribution']['concerns'])
        
        # Keyword bias recommendations
        if report['keyword_bias'].get('bias_detected'):
            recommendations.append(report['keyword_bias']['recommendation'])
        
        # Experience bias recommendations
        if report['experience_bias'].get('bias_detected'):
            recommendations.append(report['experience_bias']['recommendation'])
        
        # General recommendations
        if len(recommendations) == 0:
            recommendations.append(
                "System is performing well. Continue monitoring fairness metrics."
            )
        
        return recommendations


# Global fairness analyzer instance
fairness_analyzer = FairnessAnalyzer()