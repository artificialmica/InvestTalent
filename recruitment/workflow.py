"""
Workflow Tracking Module
Tracks candidate progress through recruitment pipeline
Provides status history, timeline tracking, and workflow analytics
"""

from django.db import models
from django.utils import timezone
from .models import Candidate
import json


class WorkflowEvent(models.Model):
    """
    Tracks individual events in the recruitment workflow
    """
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name='workflow_events'
    )
    event_type = models.CharField(max_length=50)
    old_status = models.CharField(max_length=20, null=True, blank=True)
    new_status = models.CharField(max_length=20)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100, default='System')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.candidate.name} - {self.event_type} - {self.created_at}"


class WorkflowTracker:
    """
    Manages candidate workflow tracking and analysis
    """
    
    def __init__(self):
        self.workflow_stages = [
            'received',
            'screening',
            'interview',
            'offered',
            'hired',
            'rejected'
        ]
    
    def log_status_change(self, candidate, new_status, notes='', user='System'):
        """
        Log a status change event for a candidate
        """
        old_status = candidate.status
        
        # Create workflow event
        event = WorkflowEvent.objects.create(
            candidate=candidate,
            event_type='status_change',
            old_status=old_status,
            new_status=new_status,
            notes=notes,
            created_by=user
        )
        
        # Update candidate status
        candidate.status = new_status
        candidate.save()
        
        return event
    
    def log_custom_event(self, candidate, event_type, notes='', user='System'):
        """
        Log a custom event (e.g., interview scheduled, document requested)
        """
        event = WorkflowEvent.objects.create(
            candidate=candidate,
            event_type=event_type,
            new_status=candidate.status,
            notes=notes,
            created_by=user
        )
        
        return event
    
    def get_candidate_timeline(self, candidate):
        """
        Get complete timeline of events for a candidate
        """
        events = WorkflowEvent.objects.filter(candidate=candidate)
        
        timeline = []
        for event in events:
            timeline.append({
                'timestamp': event.created_at.isoformat(),
                'event_type': event.event_type,
                'old_status': event.old_status,
                'new_status': event.new_status,
                'notes': event.notes,
                'created_by': event.created_by
            })
        
        return timeline
    
    def calculate_time_in_stage(self, candidate):
        """
        Calculate how long candidate has been in each stage
        """
        events = WorkflowEvent.objects.filter(
            candidate=candidate,
            event_type='status_change'
        ).order_by('created_at')
        
        if not events.exists():
            return {}
        
        stage_times = {}
        
        for i, event in enumerate(events):
            stage = event.new_status
            start_time = event.created_at
            
            # Get end time (next event or now)
            if i < len(events) - 1:
                end_time = events[i + 1].created_at
            else:
                end_time = timezone.now()
            
            duration = (end_time - start_time).total_seconds() / 3600  # Convert to hours
            
            if stage not in stage_times:
                stage_times[stage] = 0
            
            stage_times[stage] += duration
        
        # Round to 2 decimal places
        for stage in stage_times:
            stage_times[stage] = round(stage_times[stage], 2)
        
        return stage_times
    
    def get_average_time_to_hire(self):
        """
        Calculate average time from application to hire
        """
        hired_candidates = Candidate.objects.filter(status='hired')
        
        if not hired_candidates.exists():
            return None
        
        total_time = 0
        count = 0
        
        for candidate in hired_candidates:
            # Get first event (application received)
            first_event = WorkflowEvent.objects.filter(
                candidate=candidate
            ).order_by('created_at').first()
            
            # Get hire event
            hire_event = WorkflowEvent.objects.filter(
                candidate=candidate,
                new_status='hired'
            ).order_by('created_at').first()
            
            if first_event and hire_event:
                duration = (hire_event.created_at - first_event.created_at).total_seconds() / 86400  # Days
                total_time += duration
                count += 1
        
        if count == 0:
            return None
        
        return round(total_time / count, 2)
    
    def get_bottleneck_analysis(self):
        """
        Identify stages where candidates spend most time
        """
        all_stage_times = {}
        candidate_count = {}
        
        # Get all candidates with events
        candidates = Candidate.objects.filter(workflow_events__isnull=False).distinct()
        
        for candidate in candidates:
            stage_times = self.calculate_time_in_stage(candidate)
            
            for stage, time in stage_times.items():
                if stage not in all_stage_times:
                    all_stage_times[stage] = 0
                    candidate_count[stage] = 0
                
                all_stage_times[stage] += time
                candidate_count[stage] += 1
        
        # Calculate averages
        average_times = {}
        for stage in all_stage_times:
            if candidate_count[stage] > 0:
                average_times[stage] = round(
                    all_stage_times[stage] / candidate_count[stage],
                    2
                )
        
        # Sort by time (descending)
        sorted_stages = sorted(
            average_times.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return {
            'stage_average_hours': dict(sorted_stages),
            'bottleneck_stage': sorted_stages[0][0] if sorted_stages else None,
            'bottleneck_time': sorted_stages[0][1] if sorted_stages else None
        }
    
    def get_conversion_rates(self):
        """
        Calculate conversion rates between stages
        """
        conversions = {}
        
        for i in range(len(self.workflow_stages) - 1):
            current_stage = self.workflow_stages[i]
            next_stage = self.workflow_stages[i + 1]
            
            # Count candidates who reached current stage
            current_count = WorkflowEvent.objects.filter(
                new_status=current_stage
            ).values('candidate').distinct().count()
            
            # Count candidates who progressed to next stage
            next_count = WorkflowEvent.objects.filter(
                old_status=current_stage,
                new_status=next_stage
            ).values('candidate').distinct().count()
            
            if current_count > 0:
                conversion_rate = round((next_count / current_count) * 100, 2)
            else:
                conversion_rate = 0
            
            conversions[f"{current_stage}_to_{next_stage}"] = {
                'from_count': current_count,
                'to_count': next_count,
                'conversion_rate': conversion_rate
            }
        
        return conversions
    
    def generate_workflow_report(self):
        """
        Generate comprehensive workflow analytics report
        """
        return {
            'average_time_to_hire_days': self.get_average_time_to_hire(),
            'bottleneck_analysis': self.get_bottleneck_analysis(),
            'conversion_rates': self.get_conversion_rates(),
            'total_candidates': Candidate.objects.count(),
            'total_events': WorkflowEvent.objects.count(),
            'generated_at': timezone.now().isoformat()
        }


# Global workflow tracker instance
workflow_tracker = WorkflowTracker()