from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout as auth_logout
from .models import Candidate, Resume, JobPosting, CandidateJobApplication, Score
from .scoring import analyze_resume
from .fairness import fairness_analyzer
from .analytics import analytics_engine
from .workflow import workflow_tracker
from .security import security_validator
from .integration import system_integration
from .fuzzy_matching import match_required_skills, find_skill_variations
import PyPDF2
import docx
import os
import io
import json
import hashlib


def get_client_ip(request):
    """Extract client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def extract_text_from_pdf(uploaded_file):
    """Extract text from PDF file"""
    try:
        pdf_file = io.BytesIO(uploaded_file.read())
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        
        return text
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return ""


def extract_text_from_docx(uploaded_file):
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(uploaded_file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        print(f"Error extracting DOCX: {e}")
        return ""


# LOGOUT VIEW - Works with GET requests
def logout_view(request):
    """Custom logout view that works with GET requests"""
    auth_logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('dashboard')


def upload_resume(request):
    """
    Simplified CV upload with automatic contact extraction
    No manual form fields - everything extracted from CV
    """
    
    if request.method == 'POST':
        uploaded_file = request.FILES.get('resume_file')
        job_id = request.POST.get('job_posting_id')
        application_source = request.POST.get('application_source', 'direct')
        
        # F11: Get self-reported diversity data (optional)
        gender = request.POST.get('gender', '')
        nationality = request.POST.get('nationality', '')
        
        # Validate file exists
        if not uploaded_file:
            messages.error(request, 'Please select a resume file to upload')
            job_postings = JobPosting.objects.filter(is_active=True).order_by('-created_at')
            return render(request, 'recruitment/upload.html', {'job_postings': job_postings})
        
        # Security: Validate file upload
        is_valid, error_message = security_validator.validate_file_upload(uploaded_file)
        if not is_valid:
            messages.error(request, error_message)
            job_postings = JobPosting.objects.filter(is_active=True).order_by('-created_at')
            return render(request, 'recruitment/upload.html', {'job_postings': job_postings})
        
        # Security: Rate limit check
        client_ip = get_client_ip(request)
        if not security_validator.rate_limit_check(client_ip):
            messages.error(request, 'Too many upload attempts. Please try again in a few minutes.')
            job_postings = JobPosting.objects.filter(is_active=True).order_by('-created_at')
            return render(request, 'recruitment/upload.html', {'job_postings': job_postings})
        
        try:
            # Extract text from file FIRST
            file_extension = uploaded_file.name.split('.')[-1].lower()
            parsed_text = ""
            
            # Reset file pointer
            uploaded_file.seek(0)
            
            if file_extension == 'pdf':
                parsed_text = extract_text_from_pdf(uploaded_file)
            elif file_extension in ['docx', 'doc']:
                parsed_text = extract_text_from_docx(uploaded_file)
            
            # Security: Sanitize extracted text
            parsed_text = security_validator.sanitize_text(parsed_text)
            
            # Check if text extraction worked
            if len(parsed_text) < 50:
                messages.error(
                    request, 
                    '⚠️ Unable to extract text from resume. Please ensure your file is readable and not password-protected.'
                )
                job_postings = JobPosting.objects.filter(is_active=True).order_by('-created_at')
                return render(request, 'recruitment/upload.html', {'job_postings': job_postings})
            
            # Security: Detect malicious content
            threats = security_validator.detect_malicious_content(parsed_text)
            
            # Calculate file hash for duplicate detection
            uploaded_file.seek(0)
            file_hash = hashlib.sha256(uploaded_file.read()).hexdigest()
            
            # Check for duplicate file
            if Resume.objects.filter(candidate__file_hash=file_hash).exists():
                messages.warning(
                    request,
                    '⚠️ This resume has already been uploaded. Redirecting to existing candidate profile.'
                )
                existing_candidate = Candidate.objects.get(file_hash=file_hash)
                return redirect('candidate_detail', pk=existing_candidate.id)
            
            # Reset file pointer again
            uploaded_file.seek(0)
            
            # Create candidate with minimal info (will be filled by analyzer)
            candidate = Candidate.objects.create(
                name='Processing...',  # Temporary - will be updated by analyzer
                email=None,  # Will be extracted
                phone=None,  # Will be extracted
                status='received',
                ip_address=client_ip,
                file_hash=file_hash,
                application_source=application_source,
                # F11: Self-reported diversity data
                gender=gender,
                nationality=nationality,
            )
            
            # Add security flags if threats detected
            if threats:
                candidate.security_flags = {'threats': threats}
                candidate.save()
                for threat in threats:
                    messages.warning(request, f'🔒 Security note: {threat}')
            
            # Create Resume object
            Resume.objects.create(
                candidate=candidate,
                file=uploaded_file,
                file_type=file_extension,
                parsed_text=parsed_text
            )
            
            # Get job posting if selected
            job_posting = None
            if job_id:
                try:
                    job_posting = JobPosting.objects.get(id=job_id, is_active=True)
                except JobPosting.DoesNotExist:
                    pass
            
            # Analyze resume (this will extract contact info, skills, etc.)
            try:
                print(f"\n Starting AI analysis for candidate #{candidate.id}")
                scores = analyze_resume(candidate, job_posting=job_posting, use_ml=True)
                
                if scores:
                    # Reload candidate to get updated info
                    candidate.refresh_from_db()
                    
                    # Check if contact info was extracted
                    if not candidate.name or candidate.name == 'Processing...':
                        candidate.name = f"Candidate #{candidate.id}"
                        candidate.save()
                        messages.warning(
                            request,
                            '⚠️ Unable to extract name from resume. Please update manually in the admin panel.'
                        )
                    
                    if not candidate.email:
                        messages.warning(
                            request,
                            '⚠️ Unable to extract email from resume. Please update manually in the admin panel.'
                        )
                    
                    # Show extraction summary
                    if scores.get('contact_info'):
                        contact = scores['contact_info']
                        extracted_info = []
                        if contact.get('name'):
                            extracted_info.append(f"Name: {contact['name']}")
                        if contact.get('email'):
                            extracted_info.append(f"Email: {contact['email']}")
                        if contact.get('phone'):
                            extracted_info.append(f"Phone: {contact['phone']}")
                        
                        if extracted_info:
                            messages.info(
                                request,
                                f"📇 Extracted: {' | '.join(extracted_info)}"
                            )
                    
                    return redirect('candidate_detail', pk=candidate.id)
                else:
                    messages.warning(
                        request, 
                        'Resume uploaded but scoring failed. Please review in admin panel.'
                    )
                    return redirect('candidate_detail', pk=candidate.id)
                    
            except Exception as e:
                messages.error(request, f'Error analyzing resume: {str(e)}')
                print(f"Error in analyze_resume: {e}")
                import traceback
                traceback.print_exc()
                return redirect('candidate_detail', pk=candidate.id)
                
        except Exception as e:
            messages.error(request, f'Error processing file: {str(e)}')
            print(f"Error in upload_resume: {e}")
            import traceback
            traceback.print_exc()
    
    # GET request - show upload form
    job_postings = JobPosting.objects.filter(is_active=True).order_by('-created_at')
    
    return render(request, 'recruitment/upload.html', {'job_postings': job_postings})


def candidate_list(request):
    """Display list of all candidates"""
    candidates = Candidate.objects.all().select_related('score').order_by('-created_at')
    
    context = {
        'candidates': candidates
    }
    
    return render(request, 'recruitment/candidate_list.html', context)


def candidate_detail(request, pk):
    """Display detailed view of a single candidate"""
    candidate = get_object_or_404(Candidate, pk=pk)
    
    # Get related data
    education = candidate.education.all()
    experience = candidate.experience.all()
    skills = candidate.extracted_skills.all()
    
    # Separate skills by source
    regex_skills = skills.filter(matched_via='regex')
    esco_skills = skills.filter(matched_via='esco')
    
    # Get job applications
    job_applications = candidate.job_applications.all().select_related('job_posting')
    # Get workflow events
    timeline = workflow_tracker.get_candidate_timeline(candidate)
    
    context = {
        'candidate': candidate,
        'education': education,
        'experience': experience,
        'skills': skills,
        'regex_skills': regex_skills,
        'esco_skills': esco_skills,
        'job_applications': job_applications,
        'timeline': timeline,
    }
    
    return render(request, 'recruitment/candidate_detail.html', context)


def dashboard(request):
    """Main dashboard view with weight slider support"""
    from django.db.models import Avg
    
    # Check if re-scoring requested
    action = request.GET.get('action')
    if action == 'rescore':
        # Get custom weights from request
        edu_weight = float(request.GET.get('education_weight', 0.25))
        exp_weight = float(request.GET.get('experience_weight', 0.30))
        skill_weight = float(request.GET.get('skills_weight', 0.25))
        if_weight = float(request.GET.get('islamic_finance_weight', 0.20))
        
        # Re-score all candidates - ACTUALLY call analyze_resume to re-extract skills!
        candidates_to_rescore = Candidate.objects.filter(score__isnull=False)
        rescored_count = 0
        
        for candidate in candidates_to_rescore:
            try:
                # ACTUALLY RE-ANALYZE the resume (this re-extracts skills with new filters!)
                if hasattr(candidate, 'resume') and candidate.resume.parsed_text:
                    print(f"\n{'='*60}")
                    print(f"RE-SCORING: {candidate.name}")
                    print(f"{'='*60}")
                    analyze_resume(candidate, job_posting=None, use_ml=True)
                    rescored_count += 1
                else:
                    print(f"Skipping {candidate.name} - no resume text")
            except Exception as e:
                print(f"Error rescoring {candidate.name}: {e}")
                import traceback
                traceback.print_exc()
        
        # Update ranks after all rescoring is done
        all_scores = Score.objects.all().order_by('-total_score')
        for i, score in enumerate(all_scores, 1):
            score.rank = i
            score.save()
        
        messages.success(request, f'✅ Re-scored {rescored_count} candidates! Skills re-extracted with domain filtering.')
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    min_score = request.GET.get('min_score', '')
    
    # Base queryset
    candidates = Candidate.objects.filter(score__isnull=False).select_related('score')
    
    # Apply filters
    if search_query:
        candidates = candidates.filter(
            models.Q(name__icontains=search_query) | 
            models.Q(email__icontains=search_query)
        )
    
    if status_filter:
        candidates = candidates.filter(status=status_filter)
    
    if min_score:
        try:
            min_score_val = float(min_score)
            candidates = candidates.filter(score__total_score__gte=min_score_val)
        except ValueError:
            pass
    
    # Order by score
    candidates = candidates.order_by('-score__total_score')
    
    # ============================================
    # FIX: Calculate ranks dynamically for display
    # ============================================
    candidates_list = list(candidates[:50])
    for i, candidate in enumerate(candidates_list, start=1):
        if hasattr(candidate, 'score') and candidate.score:
            candidate.score.rank = i
    
    # Get statistics
    total_candidates = Candidate.objects.count()
    shortlisted_count = Candidate.objects.filter(status='shortlisted').count()
    avg_score = Candidate.objects.filter(score__isnull=False).aggregate(
        avg=Avg('score__total_score')
    )['avg'] or 0
    
    # Status choices for filter dropdown
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('screening', 'Screening'),
        ('shortlisted', 'Shortlisted'),
        ('interview', 'Interview'),
        ('offer', 'Offer'),
        ('hired', 'Hired'),
        ('rejected', 'Rejected'),
    ]
    status_choices = STATUS_CHOICES
    
    context = {
        'candidates': candidates_list,  # Use the list with ranks calculated
        'total_candidates': total_candidates,
        'shortlisted_count': shortlisted_count,
        'avg_score': round(avg_score, 1),
        'search_query': search_query,
        'status_filter': status_filter,
        'min_score': min_score,
        'status_choices': status_choices,
    }
    
    return render(request, 'recruitment/dashboard.html', context)


def analytics_dashboard(request):
    """Analytics and insights dashboard"""
    report = analytics_engine.generate_comprehensive_report()
    
    context = {
        'report': report,
    }
    
    return render(request, 'recruitment/analytics.html', context)


def fairness_report(request):
    """Fairness and bias analysis report"""
    report = fairness_analyzer.generate_fairness_report()
    
    context = {
        'report': report,
    }
    
    return render(request, 'recruitment/fairness.html', context)


def system_health(request):
    """System health check"""
    health = system_integration.check_system_health()
    
    return JsonResponse(health)


def export_analytics_report(request):
    """Export analytics as JSON"""
    report = analytics_engine.generate_comprehensive_report()
    
    response = HttpResponse(
        json.dumps(report, indent=2, default=str),
        content_type='application/json'
    )
    response['Content-Disposition'] = 'attachment; filename="analytics_report.json"'
    
    return response


@staff_member_required
def update_candidate_status(request, pk):
    """Update candidate status"""
    if request.method == 'POST':
        print(f"DEBUG: request.path = '{request.path}'")
        print(f"DEBUG: request.method = '{request.method}'")
        
        try:
            candidate = get_object_or_404(Candidate, pk=pk)
            
            # Handle both JSON and form data
            if request.content_type == 'application/json':
                import json
                data = json.loads(request.body)
                new_status = data.get('status')
                notes = data.get('notes', '')
            else:
                new_status = request.POST.get('status')
                notes = request.POST.get('notes', '')
            
            print(f"DEBUG: new_status = '{new_status}'")
            
            if new_status:
                # Log status change
                workflow_tracker.log_status_change(
                    candidate,
                    new_status,
                    notes=notes,
                    user=request.user.username if request.user.is_authenticated else 'System'
                )
                
                print(f"DEBUG: Status changed successfully")
                
                # Check if API call FIRST, before messages
                if request.path.startswith('/api/'):
                    print("DEBUG: API call detected - returning JSON")
                    return JsonResponse({
                        'success': True,
                        'message': f'Status updated to {new_status}',
                        'new_status': new_status
                    })
                
                # Only add message if NOT API
                messages.success(request, f'Status updated to {new_status}')
                print("DEBUG: Returning redirect")
                return redirect('candidate_detail', pk=pk)
            
            # If no status provided
            if request.path.startswith('/api/'):
                return JsonResponse({'success': False, 'error': 'No status provided'}, status=400)
            return redirect('candidate_detail', pk=pk)
        
        except Exception as e:
            print(f"ERROR updating status: {str(e)}")
            import traceback
            traceback.print_exc()
            
            if request.path.startswith('/api/'):
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=400)
            
            messages.error(request, f'Error updating status: {str(e)}')
            return redirect('candidate_detail', pk=pk)
    
    # If not POST
    if request.path.startswith('/api/'):
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    return redirect('dashboard')


# API Endpoints
def api_analytics_summary(request):
    """API: Get analytics summary"""
    report = analytics_engine.generate_comprehensive_report()
    return JsonResponse(report)


def api_fairness_report(request):
    """API: Get fairness report"""
    report = fairness_analyzer.generate_fairness_report()
    return JsonResponse(report)


def api_workflow_report(request):
    """API: Get workflow report"""
    report = workflow_tracker.generate_workflow_report()
    return JsonResponse(report)


def api_system_health(request):
    """API: System health check"""
    health = system_integration.check_system_health()
    return JsonResponse(health)


def api_candidate_timeline(request, pk):
    """API: Get candidate timeline"""
    candidate = get_object_or_404(Candidate, pk=pk)
    timeline = workflow_tracker.get_candidate_timeline(candidate)
    return JsonResponse({'timeline': timeline})


def debug_resume(request, pk):
    """Debug view to see raw extracted text"""
    candidate = get_object_or_404(Candidate, pk=pk)
    
    if hasattr(candidate, 'resume'):
        text = candidate.resume.parsed_text
    else:
        text = "No resume found"
    
    return HttpResponse(f"<pre>{text}</pre>")


@staff_member_required
def skill_variations(request):
    """Help HR see variations of a skill (API endpoint)"""
    skill = request.GET.get('skill', '')
    
    if skill:
        variations = find_skill_variations(skill)
    else:
        variations = []
    
    return JsonResponse({
        'skill': skill,
        'variations': variations
    })


@staff_member_required
def compare_candidates(request):
    """Side-by-side comparison of candidates"""
    candidate_ids = request.GET.getlist('candidates')
    
    if not candidate_ids or len(candidate_ids) < 2:
        messages.error(request, 'Please select at least 2 candidates to compare')
        return redirect('dashboard')
    
    if len(candidate_ids) > 4:
        messages.warning(request, 'Showing first 4 candidates for comparison')
        candidate_ids = candidate_ids[:4]
    
    # Get candidates ordered by score (highest first)
    candidates = Candidate.objects.filter(id__in=candidate_ids).select_related('score').order_by('-score__total_score')
    
    # Build comparison data
    comparison = []
    for candidate in candidates:
        # Get skills - handle both old and new model structures
        try:
            skills_list = list(candidate.extracted_skills.filter(is_validated=True)[:15])
        except:
            skills_list = list(candidate.extracted_skills.all()[:15])
        
        data = {
            'candidate': candidate,
            'education': list(candidate.education.all()),
            'experience': list(candidate.experience.all()),
            'skills': skills_list,
            'years_experience': candidate.years_experience,
        }
        comparison.append(data)
    
    context = {
        'comparison': comparison,
    }
    
    return render(request, 'recruitment/compare_candidates.html', context)


# Export candidates CSV
def export_candidates_csv(request):
    """Export candidates to CSV"""
    import csv
    from django.utils import timezone
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="candidates_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Email', 'Phone', 'Status', 
        'Total Score', 'Education Score', 'Experience Score', 
        'Skills Score', 'Islamic Finance Score',
        'Years Experience', 'ATS Readability',
        'Created At'
    ])
    
    candidates = Candidate.objects.select_related('score').all()
    
    for candidate in candidates:
        score = candidate.score if hasattr(candidate, 'score') else None
        writer.writerow([
            candidate.name,
            candidate.email,
            candidate.phone,
            candidate.get_status_display(),
            score.total_score if score else 0,
            score.education_score if score else 0,
            score.experience_score if score else 0,
            score.skills_score if score else 0,
            score.islamic_finance_score if score else 0,
            candidate.years_experience,
            candidate.ats_readability_score,
            candidate.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    
    return response


# ============================================================================
# JOB POSTING FEATURE - STYLED TO MATCH DASHBOARD
# ============================================================================

from django.db.models import Avg
from .models import JobRoleProfile, SkillDefinition, SkillCategory
from .job_matching import match_candidate_to_job, match_all_candidates, save_application


def job_list(request):
    """List all job postings - styled with navy/gold theme."""
    jobs = JobPosting.objects.filter(is_active=True).select_related('role_profile')
    
    rows = ""
    for job in jobs:
        apps = CandidateJobApplication.objects.filter(job_posting=job)
        count = apps.count()
        avg = apps.aggregate(Avg('job_fit_score'))['job_fit_score__avg'] or 0
        req_count = job.role_profile.required_skills.count() if job.role_profile else 0
        pref_count = job.role_profile.preferred_skills.count() if job.role_profile else 0
        
        if avg >= 70:
            score_style = "background: #2D8659; color: white;"
        elif avg >= 50:
            score_style = "background: #C9A227; color: #1B3C53;"
        elif count > 0:
            score_style = "background: #FCEAEA; color: #C23B3B;"
        else:
            score_style = "background: #E3E3E3; color: #6B7C88;"
        
        rows += f'''
        <tr style="border-bottom: 1px solid rgba(227,227,227,0.5); transition: background 0.2s;" onmouseover="this.style.background='rgba(35,76,106,0.02)'" onmouseout="this.style.background='white'">
            <td style="padding: 18px 16px;">
                <a href="/jobs/{job.id}/" style="color: #234C6A; font-weight: 600; text-decoration: none; font-size: 15px;">{job.title}</a>
                <br><small style="color: #6B7C88;">{job.department or "No department"}</small>
            </td>
            <td style="padding: 18px 16px; text-align: center;">
                <span style="background: #FCEAEA; color: #C23B3B; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">{req_count}</span>
            </td>
            <td style="padding: 18px 16px; text-align: center;">
                <span style="background: #E8F5EE; color: #2D8659; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;">{pref_count}</span>
            </td>
            <td style="padding: 18px 16px; text-align: center; font-weight: 600; color: #1B3C53;">{count}</td>
            <td style="padding: 18px 16px; text-align: center;">
                <span style="{score_style} padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 13px;">{avg:.0f}%</span>
            </td>
            <td style="padding: 18px 16px; text-align: center;">
                <a href="/jobs/{job.id}/match/" style="background: #2D8659; color: white; padding: 6px 12px; border-radius: 6px; text-decoration: none; font-size: 12px; margin-right: 5px; font-weight: 500;">Match</a>
                <a href="/jobs/{job.id}/" style="background: #1B3C53; color: white; padding: 6px 12px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: 500;">View</a>
            </td>
        </tr>'''
    
    total_jobs = len(jobs)
    total_matches = sum(CandidateJobApplication.objects.filter(job_posting=j).count() for j in jobs)
    jobs_with_qualified = sum(1 for j in jobs if CandidateJobApplication.objects.filter(job_posting=j, job_fit_score__gte=50).exists())
    total_candidates = Candidate.objects.count()
    
    empty_row = '<tr><td colspan="6" style="padding: 50px; text-align: center; color: #6B7C88;"><h3 style="font-family: Playfair Display, serif; color: #456882;">No job postings yet</h3><p style="margin-top:10px;">Create your first job to start matching candidates</p><a href="/jobs/create/" style="display:inline-block;margin-top:15px;background:#1B3C53;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:500;">Create Job</a></td></tr>'
    
    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Job Postings - InvestTalent-AI</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #F8F9FA; color: #1B3C53; }}
            .navbar {{ background: #1B3C53; color: white; padding: 20px 40px; box-shadow: 0 4px 12px rgba(27,60,83,0.08); }}
            .navbar h1 {{ font-family: 'Playfair Display', Georgia, serif; font-size: 24px; margin-bottom: 4px; font-weight: 600; }}
            .navbar p {{ opacity: 0.8; font-size: 13px; }}
            .nav-links {{ margin-top: 12px; display: flex; gap: 8px; }}
            .nav-links a {{ color: white; text-decoration: none; padding: 6px 14px; border-radius: 6px; opacity: 0.85; font-size: 13px; font-weight: 500; transition: all 0.2s; }}
            .nav-links a:hover {{ opacity: 1; background: rgba(255,255,255,0.15); }}
            .nav-links a.active {{ opacity: 1; background: rgba(255,255,255,0.2); font-weight: 600; }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 30px 40px; }}
            .header-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
            .header-row h2 {{ font-family: 'Playfair Display', Georgia, serif; color: #1B3C53; font-size: 22px; font-weight: 600; }}
            .btn-create {{ background: #C9A227; color: #1B3C53; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; box-shadow: 0 4px 12px rgba(201,162,39,0.3); transition: all 0.2s; }}
            .btn-create:hover {{ transform: translateY(-1px); box-shadow: 0 6px 16px rgba(201,162,39,0.4); }}
            .stats-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 2px rgba(27,60,83,0.05); text-align: center; border-left: 4px solid #234C6A; }}
            .stat-card .value {{ font-family: 'Playfair Display', Georgia, serif; font-size: 28px; font-weight: 700; color: #1B3C53; }}
            .stat-card .label {{ font-size: 11px; color: #6B7C88; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 6px; font-weight: 600; }}
            .table-card {{ background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(27,60,83,0.08); overflow: hidden; }}
            table {{ width: 100%; border-collapse: collapse; }}
            thead {{ background: #1B3C53; }}
            th {{ padding: 14px 16px; text-align: left; color: white; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }}
            th:nth-child(2), th:nth-child(3), th:nth-child(4), th:nth-child(5), th:nth-child(6) {{ text-align: center; }}
            tbody tr {{ background: white; }}
        </style>
    </head>
    <body>
        <div class="navbar">
            <h1>Job Postings</h1>
            <p>Manage job requirements and match candidates</p>
            <div class="nav-links">
                <a href="/">Candidates</a>
                <a href="/jobs/" class="active">Job Postings</a>
                <a href="/analytics/">Analytics</a>
                <a href="/fairness/">Fairness</a>
            </div>
        </div>
        <div class="container">
            <div class="header-row">
                <h2>Active Positions</h2>
                <a href="/jobs/create/" class="btn-create">+ Create New Job</a>
            </div>
            <div class="stats-row">
                <div class="stat-card"><div class="value">{total_jobs}</div><div class="label">Active Jobs</div></div>
                <div class="stat-card"><div class="value">{total_matches}</div><div class="label">Total Matches</div></div>
                <div class="stat-card"><div class="value">{jobs_with_qualified}</div><div class="label">Jobs with Qualified</div></div>
                <div class="stat-card"><div class="value">{total_candidates}</div><div class="label">Total Candidates</div></div>
            </div>
            <div class="table-card">
                <table>
                    <thead><tr><th>Job Title</th><th>Required</th><th>Preferred</th><th>Candidates</th><th>Avg Score</th><th>Actions</th></tr></thead>
                    <tbody>{rows if rows else empty_row}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>'''
    
    return HttpResponse(html)


def job_create(request):
    """Create a job posting - styled with navy/gold theme."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        department = request.POST.get('department', '').strip()
        min_exp = int(request.POST.get('min_experience', 0))
        domain = request.POST.get('domain', 'General')
        
        profile = JobRoleProfile.objects.create(name=f"{title} Profile", min_experience=min_exp, domain=domain)
        
        req_ids = request.POST.getlist('required_skills')
        pref_ids = request.POST.getlist('preferred_skills')
        if req_ids: profile.required_skills.set(req_ids)
        if pref_ids: profile.preferred_skills.set(pref_ids)
        
        job = JobPosting.objects.create(
            title=title, department=department, role_profile=profile,
            education_weight=float(request.POST.get('education_weight', 20))/100,
            experience_weight=float(request.POST.get('experience_weight', 25))/100,
            skills_weight=float(request.POST.get('skills_weight', 25))/100,
            hard_skills_weight=float(request.POST.get('hard_skills_weight', 15))/100,
            soft_skills_weight=float(request.POST.get('soft_skills_weight', 10))/100,
            domain_weight=float(request.POST.get('domain_weight', 5))/100,
        )
        
        return redirect('job_match', job_id=job.pk)
    
    skill_html = ""
    for cat in SkillCategory.objects.all():
        skills = SkillDefinition.objects.filter(category=cat).order_by('canonical_name')[:20]
        if skills:
            boxes = "".join([f'<label style="display:inline-block;margin:3px;padding:4px 8px;background:#F8F9FA;border-radius:8px;font-size:12px;cursor:pointer;border:1px solid #E3E3E3;transition:all 0.2s;"><input type="checkbox" name="required_skills" value="{s.id}" style="margin-right:4px;">{s.canonical_name}</label>' for s in skills])
            skill_html += f'<div style="margin-bottom:12px;"><strong style="color:#234C6A;font-size:13px;">{cat.name.title()}</strong><div style="margin-top:6px;">{boxes}</div></div>'
    
    empty_skills = '<p style="color:#6B7C88;">No skills in database yet.</p>'
    csrf_token = request.META.get('CSRF_COOKIE', '')
    
    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Create Job - InvestTalent-AI</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #F8F9FA; color: #1B3C53; }}
            .navbar {{ background: #1B3C53; color: white; padding: 20px 40px; box-shadow: 0 4px 12px rgba(27,60,83,0.08); }}
            .navbar h1 {{ font-family: 'Playfair Display', Georgia, serif; font-size: 24px; font-weight: 600; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 30px 40px; }}
            .form-card {{ background: white; padding: 24px; border-radius: 12px; box-shadow: 0 4px 12px rgba(27,60,83,0.08); margin-bottom: 20px; }}
            .form-card h3 {{ color: #1B3C53; margin-bottom: 16px; font-size: 15px; border-bottom: 2px solid #C9A227; padding-bottom: 10px; font-family: 'Playfair Display', Georgia, serif; }}
            input[type="text"], input[type="number"], select {{ width: 100%; padding: 12px; border: 1px solid #E3E3E3; border-radius: 8px; font-size: 14px; margin-bottom: 15px; font-family: 'Inter', sans-serif; }}
            input[type="text"]:focus, select:focus {{ outline: none; border-color: #234C6A; box-shadow: 0 0 0 3px rgba(35,76,106,0.1); }}
            .btn-submit {{ background: #1B3C53; color: white; padding: 14px 30px; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.2s; }}
            .btn-submit:hover {{ background: #234C6A; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(27,60,83,0.2); }}
            .btn-cancel {{ color: #6B7C88; text-decoration: none; margin-left: 15px; font-weight: 500; }}
            .btn-cancel:hover {{ color: #1B3C53; }}
        </style>
    </head>
    <body>
        <div class="navbar">
            <h1>Create Job Posting</h1>
        </div>
        <div class="container">
            <form method="post">
                <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">
                <div class="form-card">
                    <h3>Basic Information</h3>
                    <input type="text" name="title" placeholder="Job Title *" required>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                        <input type="text" name="department" placeholder="Department">
                        <select name="domain">
                            <option value="General">General</option>
                            <option value="Islamic Finance">Islamic Finance</option>
                            <option value="Private Equity">Private Equity</option>
                            <option value="Investment Banking">Investment Banking</option>
                        </select>
                    </div>
                    <div>
                        <label style="color: #6B7C88; font-size: 13px;">Minimum Experience Required:</label>
                        <input type="number" name="min_experience" value="0" min="0" style="width: 100px;"> years
                    </div>
                </div>
                <div class="form-card">
                    <h3>Required Skills</h3>
                    <div style="max-height: 250px; overflow-y: auto; border: 1px solid #E3E3E3; padding: 15px; border-radius: 8px;">
                        {skill_html if skill_html else empty_skills}
                    </div>
                </div>
                <div class="form-card">
                    <h3>Scoring Weights</h3>
                    <input type="hidden" name="education_weight" value="20">
                    <input type="hidden" name="experience_weight" value="25">
                    <input type="hidden" name="skills_weight" value="25">
                    <input type="hidden" name="hard_skills_weight" value="15">
                    <input type="hidden" name="soft_skills_weight" value="10">
                    <input type="hidden" name="domain_weight" value="5">
                    <p style="color: #6B7C88; font-size: 13px;">
                        Education: 20% | Experience: 25% | Skills: 25% | Hard Skills: 15% | Soft Skills: 10% | Domain: 5%
                    </p>
                </div>
                <button type="submit" class="btn-submit">Create & Match Candidates</button>
                <a href="/jobs/" class="btn-cancel">Cancel</a>
            </form>
        </div>
    </body>
    </html>'''
    
    return HttpResponse(html)


def job_detail(request, job_id):
    """Show job with matched candidates - styled with navy/gold theme."""
    job = get_object_or_404(JobPosting.objects.select_related('role_profile'), pk=job_id)
    apps = CandidateJobApplication.objects.filter(job_posting=job).select_related('candidate').order_by('-job_fit_score')
    
    req_skills = pref_skills = ""
    if job.role_profile:
        req_skills = "".join([f'<span style="background:#FCEAEA;color:#C23B3B;padding:6px 12px;border-radius:15px;font-size:12px;margin:3px;display:inline-block;font-weight:500;">{s.canonical_name}</span>' for s in job.role_profile.required_skills.all()])
        pref_skills = "".join([f'<span style="background:#E8F5EE;color:#2D8659;padding:6px 12px;border-radius:15px;font-size:12px;margin:3px;display:inline-block;font-weight:500;">{s.canonical_name}</span>' for s in job.role_profile.preferred_skills.all()])
    
    total_candidates = apps.count()
    avg_score = sum(a.job_fit_score for a in apps) / total_candidates if total_candidates > 0 else 0
    top_score = apps.first().job_fit_score if apps.exists() else 0
    qualified_count = sum(1 for a in apps if a.job_fit_score >= 50)
    
    rows = ""
    for i, app in enumerate(apps, 1):
        c = app.candidate
        score = app.job_fit_score
        
        if i == 1:
            rank_style = "background: #C9A227; color: #1B3C53;"
            rank_icon = "#1"
        elif i == 2:
            rank_style = "background: #9AACB8; color: white;"
            rank_icon = "#2"
        elif i == 3:
            rank_style = "background: #B87333; color: white;"
            rank_icon = "#3"
        else:
            rank_style = "background: #E3E3E3; color: #6B7C88;"
            rank_icon = f"#{i}"
        
        if score >= 70:
            score_style = "background: #2D8659; color: white;"
            status = "Strong Match"
        elif score >= 50:
            score_style = "background: #C9A227; color: #1B3C53;"
            status = "Qualified"
        elif score >= 30:
            score_style = "background: #FDF6E3; color: #D4A012;"
            status = "Review"
        else:
            score_style = "background: #FCEAEA; color: #C23B3B;"
            status = "Low Match"
        
        position = c.current_position or '<span style="color:#9AACB8;">Not specified</span>'
        
        rows += f'''
        <tr style="border-bottom: 1px solid rgba(227,227,227,0.5); transition: all 0.2s;" onmouseover="this.style.background='rgba(35,76,106,0.02)'" onmouseout="this.style.background='white'">
            <td style="padding: 18px 16px; text-align: center;">
                <span style="{rank_style} display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: 50%; font-weight: bold; font-size: 13px;">{rank_icon}</span>
            </td>
            <td style="padding: 18px 16px;">
                <a href="/candidate/{c.id}/" style="color: #234C6A; font-weight: 600; text-decoration: none; font-size: 15px;">{c.name}</a>
                <br><small style="color: #6B7C88;">{c.email}</small>
            </td>
            <td style="padding: 18px 16px; color: #456882;">{position}</td>
            <td style="padding: 18px 16px; text-align: center;">
                <span style="background: #E8F4F8; color: #2D7D9A; padding: 5px 12px; border-radius: 12px; font-weight: 600;">{c.years_experience or 0} yrs</span>
            </td>
            <td style="padding: 18px 16px; text-align: center;">
                <div style="{score_style} padding: 8px 16px; border-radius: 20px; font-weight: bold; font-size: 16px; display: inline-block;">{score:.0f}%</div>
                <div style="font-size: 11px; color: #6B7C88; margin-top: 4px;">{status}</div>
            </td>
            <td style="padding: 18px 16px; text-align: center;">
                <a href="/candidate/{c.id}/" style="background: #1B3C53; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: 500;">View Profile</a>
            </td>
        </tr>'''
    
    empty_table = '<tr><td colspan="6" style="padding: 50px; text-align: center; color: #6B7C88;"><h3 style="font-family: Playfair Display, serif; color: #456882;">No candidates matched yet</h3><p style="margin-top:10px;">Click "Re-Match All Candidates" to run the matching algorithm</p></td></tr>'
    no_req = '<span style="color:#9AACB8;">No required skills specified</span>'
    no_pref = '<span style="color:#9AACB8;">No preferred skills specified</span>'
    
    job_date = job.created_at.strftime("%b %d, %Y") if job.created_at else "N/A"
    job_domain = job.role_profile.domain if job.role_profile else "General"
    job_min_exp = job.role_profile.min_experience if job.role_profile else 0
    req_count = job.role_profile.required_skills.count() if job.role_profile else 0
    pref_count = job.role_profile.preferred_skills.count() if job.role_profile else 0
    cand_word = "candidates" if total_candidates != 1 else "candidate"
    
    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{job.title} - InvestTalent-AI</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #F8F9FA; color: #1B3C53; }}
            .navbar {{ background: #1B3C53; color: white; padding: 20px 40px; box-shadow: 0 4px 12px rgba(27,60,83,0.08); }}
            .navbar h1 {{ font-family: 'Playfair Display', Georgia, serif; font-size: 24px; margin-bottom: 4px; font-weight: 600; }}
            .navbar p {{ opacity: 0.8; font-size: 13px; }}
            .nav-links {{ margin-top: 12px; display: flex; gap: 8px; }}
            .nav-links a {{ color: white; text-decoration: none; padding: 6px 14px; border-radius: 6px; opacity: 0.85; font-size: 13px; font-weight: 500; transition: all 0.2s; }}
            .nav-links a:hover {{ opacity: 1; background: rgba(255,255,255,0.15); }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 30px 40px; }}
            .back-link {{ color: #234C6A; text-decoration: none; font-weight: 500; display: inline-flex; align-items: center; gap: 5px; font-size: 14px; }}
            .back-link:hover {{ text-decoration: underline; }}
            .job-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin: 20px 0 25px 0; }}
            .job-title {{ font-family: 'Playfair Display', Georgia, serif; font-size: 28px; color: #1B3C53; margin-bottom: 8px; font-weight: 600; }}
            .job-meta {{ color: #6B7C88; font-size: 14px; }}
            .job-meta span {{ margin-right: 20px; }}
            .btn-match {{ background: #2D8659; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; box-shadow: 0 4px 12px rgba(45,134,89,0.3); transition: all 0.2s; }}
            .btn-match:hover {{ transform: translateY(-1px); box-shadow: 0 6px 16px rgba(45,134,89,0.4); }}
            .stats-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 2px rgba(27,60,83,0.05); text-align: center; border-left: 4px solid #234C6A; }}
            .stat-card .value {{ font-family: 'Playfair Display', Georgia, serif; font-size: 28px; font-weight: 700; color: #1B3C53; }}
            .stat-card .label {{ font-size: 11px; color: #6B7C88; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 6px; font-weight: 600; }}
            .skills-section {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
            .skills-card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 12px rgba(27,60,83,0.08); }}
            .skills-card h3 {{ font-size: 14px; color: #1B3C53; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; }}
            .skills-card h3 .count {{ background: #234C6A; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; }}
            .table-card {{ background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(27,60,83,0.08); overflow: hidden; }}
            .table-header {{ background: #1B3C53; color: white; padding: 20px; display: flex; justify-content: space-between; align-items: center; }}
            .table-header h3 {{ font-size: 16px; font-family: 'Playfair Display', Georgia, serif; }}
            table {{ width: 100%; border-collapse: collapse; }}
            thead {{ background: #F8F9FA; }}
            th {{ padding: 14px 16px; text-align: left; color: #6B7C88; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; border-bottom: 2px solid #E3E3E3; }}
            th:nth-child(1), th:nth-child(4), th:nth-child(5), th:nth-child(6) {{ text-align: center; }}
            tbody tr {{ background: white; }}
        </style>
    </head>
    <body>
        <div class="navbar">
            <h1>{job.title}</h1>
            <p>{job.department or "No department"} - Created {job_date}</p>
            <div class="nav-links">
                <a href="/">Candidates</a>
                <a href="/jobs/">Job Postings</a>
                <a href="/analytics/">Analytics</a>
                <a href="/fairness/">Fairness</a>
            </div>
        </div>
        <div class="container">
            <a href="/jobs/" class="back-link">← Back to All Jobs</a>
            <div class="job-header">
                <div>
                    <h1 class="job-title">{job.title}</h1>
                    <div class="job-meta">
                        <span>{job.department or "No department"}</span>
                        <span>{job_domain}</span>
                        <span>Min {job_min_exp} years experience</span>
                    </div>
                </div>
                <a href="/jobs/{job.id}/match/" class="btn-match">Re-Match All Candidates</a>
            </div>
            <div class="stats-row">
                <div class="stat-card"><div class="value">{total_candidates}</div><div class="label">Total Matched</div></div>
                <div class="stat-card"><div class="value" style="color: #2D8659;">{qualified_count}</div><div class="label">Qualified (50%+)</div></div>
                <div class="stat-card"><div class="value">{avg_score:.0f}%</div><div class="label">Average Score</div></div>
                <div class="stat-card"><div class="value" style="color: #234C6A;">{top_score:.0f}%</div><div class="label">Top Score</div></div>
            </div>
            <div class="skills-section">
                <div class="skills-card">
                    <h3>Required Skills <span class="count">{req_count}</span></h3>
                    <div>{req_skills if req_skills else no_req}</div>
                </div>
                <div class="skills-card">
                    <h3>Preferred Skills <span class="count">{pref_count}</span></h3>
                    <div>{pref_skills if pref_skills else no_pref}</div>
                </div>
            </div>
            <div class="table-card">
                <div class="table-header">
                    <h3>Matched Candidates</h3>
                    <span>{total_candidates} {cand_word}</span>
                </div>
                <table>
                    <thead><tr><th>Rank</th><th>Candidate</th><th>Current Position</th><th>Experience</th><th>Job Fit Score</th><th>Action</th></tr></thead>
                    <tbody>{rows if rows else empty_table}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>'''
    
    return HttpResponse(html)


def job_match(request, job_id):
    """Match all candidates to this job."""
    job = get_object_or_404(JobPosting.objects.select_related('role_profile'), pk=job_id)
    
    results = match_all_candidates(job)
    for candidate, result in results:
        save_application(candidate, job, result)
    
    return redirect('job_detail', job_id=job.pk)