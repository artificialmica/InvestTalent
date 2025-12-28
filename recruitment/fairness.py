"""
Fairness Framework Module - FULLY ADAPTIVE
Automatically adjusts to any number of candidates with clear messaging
"""

from .models import Candidate, Score
from django.db.models import Avg, Count
import statistics


class FairnessAnalyzer:
    """
    Analyzes scoring patterns for potential bias
    Adaptive thresholds based on actual candidate count
    """
    
    def __init__(self):
        self.fairness_threshold = 0.8
        
    def analyze_score_distribution(self):
        """Adaptive score distribution - works with ANY number of candidates"""
        all_scores = Score.objects.all().values_list('total_score', flat=True)
        sample_size = len(all_scores)
        
        # Show progress message if too few
        if sample_size == 0:
            return {
                'status': 'no_data',
                'message': 'No scored candidates yet',
                'current_count': 0,
                'minimum_needed': 3,
                'progress': '0/3 candidates'
            }
        
        if sample_size < 3:
            return {
                'status': 'insufficient_data',
                'message': f'Need at least 3 candidates for fairness analysis',
                'current_count': sample_size,
                'minimum_needed': 3,
                'progress': f'{sample_size}/3 candidates',
                'note': f'Upload {3 - sample_size} more candidate(s) to enable analysis'
            }
        
        # We have enough! Run analysis
        scores_list = list(all_scores)
        
        analysis = {
            'status': 'success',
            'total_candidates': len(scores_list),
            # Template-compatible keys
            'mean': round(statistics.mean(scores_list), 2),
            'median': round(statistics.median(scores_list), 2),
            'std_dev': round(statistics.stdev(scores_list), 2) if len(scores_list) > 1 else 0,
            'min': round(min(scores_list), 2),
            'max': round(max(scores_list), 2),
            'range': round(max(scores_list) - min(scores_list), 2),
            # Keep original keys too for compatibility
            'mean_score': round(statistics.mean(scores_list), 2),
            'median_score': round(statistics.median(scores_list), 2),
            'std_deviation': round(statistics.stdev(scores_list), 2) if len(scores_list) > 1 else 0,
            'min_score': round(min(scores_list), 2),
            'max_score': round(max(scores_list), 2),
            'score_range': round(max(scores_list) - min(scores_list), 2),
            'sample_size_quality': self._get_sample_quality(sample_size)
        }
        
        # Adaptive concern detection based on sample size
        analysis['concerns'] = []
        
        if sample_size < 10:
            # Relaxed thresholds for small samples
            if analysis['range'] < 15:
                analysis['concerns'].append(f"Score range narrow ({analysis['score_range']}) - acceptable for {sample_size} candidates")
            if analysis['mean'] > 85:
                analysis['concerns'].append(f"High average ({analysis['mean_score']}) - may indicate strong candidate pool")
        else:
            # Standard thresholds for larger samples
            if analysis['range'] < 20:
                analysis['concerns'].append("Score range may be too narrow")
            if analysis['mean'] > 80:
                analysis['concerns'].append(f"Average score is high ({analysis['mean_score']})")
        
        if analysis['mean'] < 30:
            analysis['concerns'].append("Average score is very low")
        
        if analysis['std_dev'] > 25:
            analysis['concerns'].append(f"High score variation ({analysis['std_deviation']})")
        
        analysis['is_fair'] = len(analysis['concerns']) == 0
        
        return analysis
    
    def detect_keyword_bias(self):
        """Adaptive keyword bias detection"""
        # Get ALL candidates first for keyword analysis
        all_candidates_list = list(Candidate.objects.all())
        
        # Analyze keywords regardless of sample size
        keyword_stats = self._analyze_keyword_frequencies(all_candidates_list)
        
        # Now check IF vs non-IF
        if_candidates = Candidate.objects.filter(
            experience__is_islamic_finance=True
        ).distinct()
        
        non_if_candidates = Candidate.objects.exclude(
            id__in=if_candidates.values_list('id', flat=True)
        )
        
        if_count = if_candidates.count()
        non_if_count = non_if_candidates.count()
        total = if_count + non_if_count
        
        # Progressive requirements
        if total < 2:
            return {
                'status': 'insufficient_data',
                'message': 'Need at least 2 scored candidates for bias analysis',
                'current_count': total,
                'minimum_needed': 2,
                'progress': f'{total}/2 candidates',
                'top_keywords': keyword_stats  # Keywords from all candidates
            }
        
        if if_count == 0 or non_if_count == 0:
            return {
                'status': 'insufficient_data',
                'message': 'Need candidates in both groups (IF and non-IF)',
                'if_count': if_count,
                'non_if_count': non_if_count,
                'note': 'Current sample is homogeneous - cannot detect bias',
                'top_keywords': keyword_stats  # Keywords from all candidates
            }
        
        # We have enough! Run analysis
        if_avg = Score.objects.filter(
            candidate__in=if_candidates
        ).aggregate(Avg('total_score'))['total_score__avg'] or 0
        
        non_if_avg = Score.objects.filter(
            candidate__in=non_if_candidates
        ).aggregate(Avg('total_score'))['total_score__avg'] or 0
        
        score_difference = abs(if_avg - non_if_avg)
        
        # Adaptive bias threshold based on sample size
        if total < 10:
            bias_threshold = 20  # More lenient for small samples
        else:
            bias_threshold = 15  # Standard threshold
        
        analysis = {
            'status': 'success',
            'islamic_finance_avg': round(if_avg, 2),
            'non_islamic_finance_avg': round(non_if_avg, 2),
            'score_difference': round(score_difference, 2),
            'if_candidate_count': if_count,
            'non_if_candidate_count': non_if_count,
            'bias_threshold': bias_threshold,
            'sample_size_quality': self._get_sample_quality(total),
            'top_keywords': keyword_stats  # For template
        }
        
        if score_difference > bias_threshold:
            analysis['bias_detected'] = True
            analysis['recommendation'] = (
                f"Score difference of {score_difference:.1f} exceeds threshold of {bias_threshold}. "
                "Review Islamic Finance scoring component."
            )
            analysis['issues'] = [analysis['recommendation']]
        else:
            analysis['bias_detected'] = False
            analysis['recommendation'] = "No significant keyword bias detected ✓"
            analysis['issues'] = []
        
        return analysis
    
    def check_experience_bias(self):
        """Adaptive experience bias check"""
        junior = Candidate.objects.filter(years_experience__lt=3)
        mid_level = Candidate.objects.filter(years_experience__gte=3, years_experience__lt=7)
        senior = Candidate.objects.filter(years_experience__gte=7)
        
        total = junior.count() + mid_level.count() + senior.count()
        
        if total < 3:
            return {
                'status': 'insufficient_data',
                'message': 'Need at least 3 scored candidates for experience analysis',
                'current_count': total,
                'minimum_needed': 3,
                'progress': f'{total}/3 candidates'
            }
        
        # Count groups with data
        groups_with_data = sum([
            junior.count() > 0,
            mid_level.count() > 0,
            senior.count() > 0
        ])
        
        if groups_with_data < 2:
            return {
                'status': 'limited_data',
                'message': 'Need candidates across multiple experience levels',
                'distribution': {
                    'junior': junior.count(),
                    'mid_level': mid_level.count(),
                    'senior': senior.count()
                }
            }
        
        # Calculate averages (only for groups with data)
        junior_avg = Score.objects.filter(candidate__in=junior).aggregate(
            Avg('total_score'))['total_score__avg'] or 0 if junior.count() > 0 else None
        
        mid_avg = Score.objects.filter(candidate__in=mid_level).aggregate(
            Avg('total_score'))['total_score__avg'] or 0 if mid_level.count() > 0 else None
        
        senior_avg = Score.objects.filter(candidate__in=senior).aggregate(
            Avg('total_score'))['total_score__avg'] or 0 if senior.count() > 0 else None
        
        analysis = {
            'status': 'success',
            # Original keys
            'junior_avg': round(junior_avg, 2) if junior_avg else None,
            'mid_level_avg': round(mid_avg, 2) if mid_avg else None,
            'senior_avg': round(senior_avg, 2) if senior_avg else None,
            'junior_count': junior.count(),
            'mid_level_count': mid_level.count(),
            'senior_count': senior.count(),
            # Template aliases (different template expects different names)
            'entry_level_avg': round(junior_avg, 2) if junior_avg else None,
            'entry_level_count': junior.count(),
            'sample_size_quality': self._get_sample_quality(total)
        }
        
        # Calculate experience gap (compare highest and lowest)
        scores = [s for s in [junior_avg, mid_avg, senior_avg] if s is not None]
        if len(scores) >= 2:
            experience_gap = max(scores) - min(scores)
            analysis['score_variance'] = round(experience_gap, 1)  # For template
        else:
            analysis['score_variance'] = 0
            
            # Adaptive threshold
            bias_threshold = 50 if total < 10 else 40
            
            if experience_gap > bias_threshold:
                analysis['bias_detected'] = True
                analysis['recommendation'] = (
                    f"Experience gap of {experience_gap:.1f} points may indicate over-weighting. "
                    f"Threshold is {bias_threshold}."
                )
                analysis['concern'] = analysis['recommendation']
            else:
                analysis['bias_detected'] = False
                analysis['recommendation'] = "Experience weighting appears balanced ✓"
                analysis['concern'] = None
        
        return analysis
    
    def generate_fairness_report(self):
        """
        Generate comprehensive fairness report
        FULLY ADAPTIVE - works with any number of candidates
        """
        total_candidates = Candidate.objects.count()
        scored_candidates = Score.objects.count()
        
        report = {
            'timestamp': str(Candidate.objects.latest('created_at').created_at) if Candidate.objects.exists() else 'N/A',
            'total_candidates': total_candidates,
            'scored_candidates': scored_candidates,
        }
        
        # Overall status
        if scored_candidates == 0:
            report['status'] = 'no_data'
            report['message'] = 'No candidates scored yet. Upload and score candidates to generate fairness report.'
            report['progress'] = '0/3 candidates minimum'
            return report
        
        if scored_candidates < 3:
            report['status'] = 'insufficient_data'
            report['message'] = f'Need at least 3 scored candidates. Currently have {scored_candidates}.'
            report['progress'] = f'{scored_candidates}/3 candidates'
            report['action'] = f'Upload and score {3 - scored_candidates} more candidate(s)'
            return report
        
        # We have enough data! Run all analyses
        report['status'] = 'success'
        # Store both keys for compatibility
        distribution = self.analyze_score_distribution()
        report['overall_distribution'] = distribution
        report['score_distribution'] = distribution  # Template compatibility
        report['keyword_bias'] = self.detect_keyword_bias()
        report['experience_bias'] = self.check_experience_bias()
        
        # Calculate overall fairness score
        concerns_count = 0
        
        if report['overall_distribution'].get('concerns'):
            concerns_count += len(report['overall_distribution']['concerns'])
        
        if report.get('keyword_bias', {}).get('bias_detected'):
            concerns_count += 1
        
        if report.get('experience_bias', {}).get('bias_detected'):
            concerns_count += 1
        
        # Fairness score (0-100)
        max_concerns = 6
        fairness_score = max(0, 100 - (concerns_count * 100 / max_concerns))
        
        report['fairness_score'] = round(fairness_score, 2)
        report['fairness_grade'] = self._get_fairness_grade(fairness_score)
        report['overall_fairness_grade'] = report['fairness_grade'].split(' - ')[0]  # Letter only
        report['recommendations'] = self._generate_recommendations(report)
        
        # Sample size quality indicator
        report['confidence_level'] = self._get_confidence_level(scored_candidates)
        
        return report
    
    def _analyze_keyword_frequencies(self, candidates):
        """Analyze keyword frequencies across candidates - ROBUST"""
        from collections import Counter
        
        # Common keywords to track
        target_keywords = [
            'python', 'java', 'javascript', 'react', 'django', 'flask',
            'sql', 'postgresql', 'mysql', 'mongodb', 'aws', 'docker', 'git',
            'machine learning', 'ai', 'artificial intelligence', 'data analysis',
            'islamic finance', 'sharia', 'sukuk', 'murabaha', 'takaful',
            'project management', 'leadership', 'communication', 'teamwork'
        ]
        
        keyword_counts = Counter()
        total_words = 0
        candidates_processed = 0
        
        for candidate in candidates:
            try:
                # Try to get resume text
                if hasattr(candidate, 'resume') and candidate.resume:
                    text = ''
                    if candidate.resume.parsed_text:
                        text = candidate.resume.parsed_text.lower()
                    
                    if text:
                        words = text.split()
                        total_words += len(words)
                        candidates_processed += 1
                        
                        # Count keywords
                        for keyword in target_keywords:
                            count = text.count(keyword.lower())
                            if count > 0:
                                keyword_counts[keyword] += count
            except Exception as e:
                # Skip problematic candidates
                continue
        
        # Format for template
        keyword_list = []
        
        if keyword_counts:
            for keyword, count in keyword_counts.most_common(15):  # Top 15
                density = (count / total_words * 100) if total_words > 0 else 0
                # Suspicious if density > 2% OR count > 25
                is_suspicious = (density > 2.0) or (count > 25)
                
                keyword_list.append({
                    'keyword': keyword.title(),  # Capitalize for display
                    'count': count,
                    'density': round(density, 3),
                    'is_suspicious': is_suspicious
                })
        
        # If no keywords found, return placeholder
        if not keyword_list:
            keyword_list = [{
                'keyword': 'No keywords detected',
                'count': 0,
                'density': 0.0,
                'is_suspicious': False
            }]
        
        return keyword_list
    
    def _get_sample_quality(self, size):
        """Return sample quality description"""
        if size < 5:
            return "Small sample - results preliminary"
        elif size < 10:
            return "Limited sample - moderate confidence"
        elif size < 30:
            return "Good sample - adequate for analysis"
        else:
            return "Large sample - high confidence"
    
    def _get_confidence_level(self, size):
        """Return confidence level based on sample size"""
        if size < 5:
            return "LOW - Expand sample for robust analysis"
        elif size < 10:
            return "MODERATE - Adequate for preliminary assessment"
        elif size < 30:
            return "GOOD - Sufficient for reliable conclusions"
        else:
            return "HIGH - Large sample enables confident analysis"
    
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
        
        # Distribution recommendations
        if report.get('overall_distribution', {}).get('concerns'):
            recommendations.extend(report['overall_distribution']['concerns'])
        
        # Keyword bias recommendations
        if report.get('keyword_bias', {}).get('bias_detected'):
            recommendations.append(report['keyword_bias']['recommendation'])
        
        # Experience bias recommendations
        if report.get('experience_bias', {}).get('bias_detected'):
            recommendations.append(report['experience_bias']['recommendation'])
        
        # General recommendations
        if len(recommendations) == 0:
            recommendations.append(
                "✓ System demonstrates fair, unbiased evaluation across all metrics"
            )
        
        # Sample size recommendations
        if report['scored_candidates'] < 10:
            recommendations.append(
                f"Consider expanding candidate pool (currently {report['scored_candidates']}) for more robust statistical analysis"
            )
        
        return recommendations


# Global fairness analyzer instance
fairness_analyzer = FairnessAnalyzer()