from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from .models import Candidate, Resume, JobPosting, CandidateJobApplication
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


def upload_resume(request):
    """
    Simplified CV upload with automatic contact extraction
    No manual form fields - everything extracted from CV
    """
    
    if request.method == 'POST':
        uploaded_file = request.FILES.get('resume_file')
        job_id = request.POST.get('job_posting_id')
        
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
                application_source='direct'
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
                print(f"\n🚀 Starting AI analysis for candidate #{candidate.id}")
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
                    
                    # # Check ATS readability
                    # if candidate.ats_readability_score < 70:
                    #     messages.warning(
                    #         request,
                    #         f'⚠️ ATS Readability: {candidate.ats_readability_score}/100 - Resume may have formatting issues'
                    #     )
                    #     if candidate.ats_issues:
                    #         messages.info(
                    #             request,
                    #             f"📋 Issues: {', '.join(candidate.ats_issues[:3])}"
                    #         )
                    
                    # # If job posting selected, create application
                    # if job_posting:
                    #     CandidateJobApplication.objects.create(
                    #         candidate=candidate,
                    #         job_posting=job_posting,
                    #         job_fit_score=scores['total_score']
                    #     )
                    #     messages.success(
                    #         request,
                    #         f'✅ Resume analyzed! Score: {scores["total_score"]}/100 for {job_posting.title}'
                    #     )
                    # else:
                    #     messages.success(
                    #         request,
                    #         f'✅ Resume analyzed! Overall Score: {scores["total_score"]}/100'
                    #     )
                    
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
    """Main dashboard view"""
    # Get all candidates with scores
    candidates = Candidate.objects.filter(score__isnull=False).select_related('score').order_by('-score__total_score')
    
    # Get statistics
    total_candidates = Candidate.objects.count()
    total_hired = Candidate.objects.filter(status='hired').count()
    total_rejected = Candidate.objects.filter(status='rejected').count()
    avg_score = Candidate.objects.filter(score__isnull=False).aggregate(
        avg=models.Avg('score__total_score')
    )['avg'] or 0
    
    context = {
        'candidates': candidates[:50],  # Top 50
        'total_candidates': total_candidates,
        'total_hired': total_hired,
        'total_rejected': total_rejected,
        'avg_score': round(avg_score, 2),
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
        candidate = get_object_or_404(Candidate, pk=pk)
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        if new_status:
            # Log status change
            workflow_tracker.log_status_change(
                candidate,
                new_status,
                notes=notes,
                user=request.user.username if request.user.is_authenticated else 'System'
            )
            
            messages.success(request, f'Status updated to {new_status}')
        
        return redirect('candidate_detail', pk=pk)
    
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


# ============================================================================
# JOB POSTINGS AND CUSTOMIZABLE SCORING
# ============================================================================

@staff_member_required
def create_job_posting(request):
    """Allow HR to create job with custom requirements and weights"""
    if request.method == 'POST':
        title = request.POST.get('title')
        department = request.POST.get('department', '')
        description = request.POST.get('description', '')
        
        # Skills
        required_skills_text = request.POST.get('required_skills', '')
        required_skills = [s.strip() for s in required_skills_text.split(',') if s.strip()]
        
        preferred_skills_text = request.POST.get('preferred_skills', '')
        preferred_skills = [s.strip() for s in preferred_skills_text.split(',') if s.strip()]
        
        # Experience
        min_years = int(request.POST.get('min_years_experience', 0))
        max_years = request.POST.get('max_years_experience')
        if max_years:
            max_years = int(max_years)
        
        # Education
        min_education = request.POST.get('min_education_level', '')
        required_certs = request.POST.get('required_certifications', '')
        special_req = request.POST.get('special_requirements', '')
        
        # Weights
        edu_weight = float(request.POST.get('education_weight', 0.25))
        exp_weight = float(request.POST.get('experience_weight', 0.30))
        skill_weight = float(request.POST.get('skills_weight', 0.25))
        if_weight = float(request.POST.get('islamic_finance_weight', 0.20))
        hard_weight = float(request.POST.get('hard_skills_weight', 0.70))
        soft_weight = float(request.POST.get('soft_skills_weight', 0.30))
        
        # Create job posting
        job = JobPosting.objects.create(
            title=title,
            department=department,
            description=description,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            min_years_experience=min_years,
            max_years_experience=max_years,
            min_education_level=min_education,
            required_certifications=required_certs,
            special_requirements=special_req,
            education_weight=edu_weight,
            experience_weight=exp_weight,
            skills_weight=skill_weight,
            islamic_finance_weight=if_weight,
            hard_skills_weight=hard_weight,
            soft_skills_weight=soft_weight,
            created_by=request.user.username if request.user.is_authenticated else 'HR Manager'
        )
        
        messages.success(request, f'Job posting "{title}" created successfully!')
        return redirect('job_posting_detail', job_id=job.id)
    
    return render(request, 'recruitment/create_job_posting.html')


def job_posting_detail(request, job_id):
    """View job posting and matched candidates"""
    job = get_object_or_404(JobPosting, id=job_id)
    
    # Get all candidates with scores
    candidates = Candidate.objects.filter(score__isnull=False).select_related('score')
    
    # Calculate job fit for each candidate
    candidate_matches = []
    for candidate in candidates:
        # Get candidate skills
        candidate_skills = [s.skill.canonical_name for s in candidate.extracted_skills.all()]
        
        # Match against required skills
        skill_match = match_required_skills(candidate_skills, job.required_skills)
        
        # Calculate job-specific score
        job_fit = (
            (candidate.score.education_score * job.education_weight) +
            (candidate.score.experience_score * job.experience_weight) +
            (candidate.score.skills_score * job.skills_weight) +
            (candidate.score.islamic_finance_score * job.islamic_finance_weight)
        )
        
        # Adjust for skill match
        if skill_match['match_percentage'] < 50:
            job_fit *= 0.8
        elif skill_match['match_percentage'] >= 80:
            job_fit *= 1.1
        
        job_fit = min(100, round(job_fit, 2))
        
        candidate_matches.append({
            'candidate': candidate,
            'job_fit_score': job_fit,
            'skill_match_percentage': skill_match['match_percentage'],
            'matched_skills': skill_match['matched_count'],
            'total_required': skill_match['total_required'],
            'matches': skill_match['matches']
        })
    
    # Sort by job fit score
    candidate_matches.sort(key=lambda x: x['job_fit_score'], reverse=True)
    
    context = {
        'job': job,
        'candidate_matches': candidate_matches[:20],  # Top 20
        'total_candidates': len(candidate_matches)
    }
    
    return render(request, 'recruitment/job_posting_detail.html', context)


@staff_member_required
def apply_candidate_to_job(request, candidate_id, job_id):
    """Link candidate to specific job and calculate fit score"""
    candidate = get_object_or_404(Candidate, id=candidate_id)
    job = get_object_or_404(JobPosting, id=job_id)
    
    # Get candidate skills
    candidate_skills = [s.skill.canonical_name for s in candidate.extracted_skills.all()]
    
    # Match skills
    skill_match = match_required_skills(candidate_skills, job.required_skills)
    
    # Calculate job fit
    if hasattr(candidate, 'score'):
        job_fit = (
            (candidate.score.education_score * job.education_weight) +
            (candidate.score.experience_score * job.experience_weight) +
            (candidate.score.skills_score * job.skills_weight) +
            (candidate.score.islamic_finance_score * job.islamic_finance_weight)
        )
        
        if skill_match['match_percentage'] < 50:
            job_fit *= 0.8
        elif skill_match['match_percentage'] >= 80:
            job_fit *= 1.1
        
        job_fit = min(100, round(job_fit, 2))
    else:
        job_fit = 0
    
    # Create or update application
    app, created = CandidateJobApplication.objects.update_or_create(
        candidate=candidate,
        job_posting=job,
        defaults={'job_fit_score': job_fit}
    )
    
    if created:
        messages.success(request, f'{candidate.name} applied to {job.title}. Job fit: {job_fit}%')
    else:
        messages.info(request, f'Updated job fit score for {candidate.name}: {job_fit}%')
    
    return redirect('candidate_detail', pk=candidate_id)


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
    
    candidates = Candidate.objects.filter(id__in=candidate_ids).select_related('score')
    
    # Build comparison data
    comparison = []
    for candidate in candidates:
        data = {
            'candidate': candidate,
            'education': list(candidate.education.all()),
            'experience': list(candidate.experience.all()),
            'skills': list(candidate.extracted_skills.all()),
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