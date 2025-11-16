from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from .models import Candidate
from .ml_scoring import ml_enhancer

@staff_member_required
def train_ml_model(request):
    """
    Admin view to train ML model based on hired/rejected candidates
    """
    if request.method == 'POST':
        # Get all candidates with status 'hired' or 'rejected'
        hired_candidates = list(Candidate.objects.filter(status='hired', score__isnull=False))
        rejected_candidates = list(Candidate.objects.filter(status='rejected', score__isnull=False))
        
        if len(hired_candidates) < 5 or len(rejected_candidates) < 5:
            messages.error(request, 'Need at least 5 hired and 5 rejected candidates to train model')
            return redirect('ml_train')
        
        # Prepare training data
        training_candidates = hired_candidates + rejected_candidates
        outcomes = [1] * len(hired_candidates) + [0] * len(rejected_candidates)
        
        # Train model
        success = ml_enhancer.train_model(training_candidates, outcomes)
        
        if success:
            messages.success(request, f'ML model trained successfully on {len(training_candidates)} candidates!')
        else:
            messages.error(request, 'Failed to train model')
        
        return redirect('dashboard')
    
    # Show training page
    hired_count = Candidate.objects.filter(status='hired', score__isnull=False).count()
    rejected_count = Candidate.objects.filter(status='rejected', score__isnull=False).count()
    
    context = {
        'hired_count': hired_count,
        'rejected_count': rejected_count,
        'can_train': hired_count >= 5 and rejected_count >= 5
    }
    
    return render(request, 'recruitment/ml_train.html', context)