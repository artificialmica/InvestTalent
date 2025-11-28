"""
System Integration Module
Coordinates all modules and provides unified interface
"""

from .scoring import analyze_resume
from .fairness import fairness_analyzer
from .analytics import analytics_engine
from .workflow import workflow_tracker, WorkflowEvent
from .security import security_validator
from django.db import transaction


class SystemIntegration:
    """
    Central coordinator for all system modules
    """
    
    def process_candidate_application(self, candidate, uploaded_file, ip_address=None):
        """
        Complete end-to-end processing of candidate application
        """
        result = {
            'success': False,
            'candidate_id': None,
            'score': None,
            'errors': [],
            'warnings': []
        }
        
        try:
            with transaction.atomic():
                # Step 1: Security validation
                threats = security_validator.detect_malicious_content(
                    candidate.resume.parsed_text
                )
                
                if threats:
                    candidate.security_flags = {'threats': threats}
                    candidate.save()
                    result['warnings'].extend(threats)
                
                # Step 2: Store audit info
                if ip_address:
                    candidate.ip_address = ip_address
                
                if uploaded_file:
                    file_hash = security_validator.generate_file_hash(
                        uploaded_file.read()
                    )
                    uploaded_file.seek(0)
                    candidate.file_hash = file_hash
                
                candidate.save()
                
                # Step 3: Analyze resume and score
                analyze_resume(candidate)
                
                # Step 4: Log workflow event
                workflow_tracker.log_custom_event(
                    candidate,
                    'application_processed',
                    notes='Resume analyzed and scored by AI system'
                )
                
                # Step 5: Get final score
                if hasattr(candidate, 'score'):
                    result['score'] = candidate.score.total_score
                
                result['success'] = True
                result['candidate_id'] = candidate.id
        
        except Exception as e:
            result['errors'].append(str(e))
        
        return result
    
    def get_system_health_check(self):
        """
        Comprehensive system health check
        """
        health = {
            'status': 'healthy',
            'checks': {},
            'timestamp': None
        }
        
        # Check 1: Database connectivity
        try:
            from .models import Candidate
            Candidate.objects.count()
            health['checks']['database'] = 'OK'
        except Exception as e:
            health['checks']['database'] = f'ERROR: {str(e)}'
            health['status'] = 'unhealthy'
        
        # Check 2: Fairness system
        try:
            fairness_report = fairness_analyzer.generate_fairness_report()
            if fairness_report['fairness_score'] >= 70:
                health['checks']['fairness'] = 'OK'
            else:
                health['checks']['fairness'] = f"WARNING: Score {fairness_report['fairness_score']}"
                health['status'] = 'degraded'
        except Exception as e:
            health['checks']['fairness'] = f'ERROR: {str(e)}'
        
        # Check 3: Analytics engine
        try:
            analytics_engine.get_score_statistics()
            health['checks']['analytics'] = 'OK'
        except Exception as e:
            health['checks']['analytics'] = f'ERROR: {str(e)}'
        
        # Check 4: Workflow tracking
        try:
            WorkflowEvent.objects.count()
            health['checks']['workflow'] = 'OK'
        except Exception as e:
            health['checks']['workflow'] = f'ERROR: {str(e)}'
        
        return health
    
    def generate_system_report(self):
        """
        Generate comprehensive system report
        """
        return {
            'analytics': analytics_engine.generate_executive_summary(),
            'fairness': fairness_analyzer.generate_fairness_report(),
            'workflow': workflow_tracker.generate_workflow_report(),
            'health': self.get_system_health_check()
        }


# Global system integration instance
system_integration = SystemIntegration()