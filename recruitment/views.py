from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from .models import Candidate, Resume
from .scoring import analyze_resume
from .fairness import fairness_analyzer
from .analytics import analytics_engine
from .workflow import workflow_tracker
from .security import security_validator
from .integration import system_integration
import PyPDF2
import docx
import os
import io


def get_client_ip(request):
    """Extract client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def upload_resume(request):
    """Handle CV file upload and text extraction with security validation"""
    
    if request.method == 'POST':
        # Get form data
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        uploaded_file = request.FILES.get('resume_file')
        
        # Security: Validate inputs
        is_valid, errors = security_validator.validate_candidate_input(name, email, phone)
        if not is_valid:
            for error in errors:
                messages.error(request, error)
            return render(request, 'recruitment/upload.html')
        
        # Validate file exists
        if not uploaded_file:
            messages.error(request, 'Please select a file to upload')
            return render(request, 'recruitment/upload.html')
        
        # Security: Validate file upload
        is_valid, error_message = security_validator.validate_file_upload(uploaded_file)
        if not is_valid:
            messages.error(request, error_message)
            return render(request, 'recruitment/upload.html')
        
        # Security: Rate limit check
        client_ip = get_client_ip(request)
        if not security_validator.rate_limit_check(client_ip):
            messages.error(request, 'Too many upload attempts. Please try again later.')
            return render(request, 'recruitment/upload.html')
        
        try:
            # Check for duplicate email
            if Candidate.objects.filter(email=email).exists():
                messages.warning(
                    request, 
                    f'A candidate with email {email} already exists. Creating new application.'
                )
            
            # Create candidate
            candidate = Candidate.objects.create(
                name=name,
                email=email,
                phone=phone,
                status='received',
                ip_address=client_ip
            )
            
            # Extract text from file
            file_extension = uploaded_file.name.split('.')[-1].lower()
            parsed_text = ""
            
            if file_extension == 'pdf':
                parsed_text = extract_text_from_pdf(uploaded_file)
            elif file_extension in ['docx', 'doc']:
                parsed_text = extract_text_from_docx(uploaded_file)
            
            # Security: Sanitize extracted text
            parsed_text = security_validator.sanitize_text(parsed_text)
            
            # Security: Detect malicious content
            threats = security_validator.detect_malicious_content(parsed_text)
            if threats:
                candidate.security_flags = {'threats': threats}
                candidate.save()
                for threat in threats:
                    messages.warning(request, f'Security warning: {threat}')
            
            # Create resume record
            resume = Resume.objects.create(
                candidate=candidate,
                file=uploaded_file,
                file_type=file_extension.upper(),
                parsed_text=parsed_text
            )
            
            # Generate file hash for duplicate detection
            uploaded_file.seek(0)
            file_hash = security_validator.generate_file_hash(uploaded_file.read())
            candidate.file_hash = file_hash
            candidate.save()
            
            # Use system integration for complete processing
            result = system_integration.process_candidate_application(
                candidate, 
                uploaded_file,
                ip_address=client_ip
            )
            
            if result['success']:
                messages.success(
                    request, 
                    f'Resume uploaded and analyzed successfully for {name}! '
                    f'Score: {result["score"]}/100'
                )
            else:
                messages.warning(request, 'Resume uploaded but analysis had issues.')
            
            # Log workflow event
            workflow_tracker.log_custom_event(
                candidate,
                'resume_uploaded',
                notes=f'Uploaded {file_extension.upper()} file from IP {client_ip}'
            )
            
            return redirect('candidate_detail', pk=candidate.pk)
            
        except Exception as e:
            messages.error(request, f'Error uploading resume: {str(e)}')
            return render(request, 'recruitment/upload.html')
    
    return render(request, 'recruitment/upload.html')


def extract_text_from_pdf(pdf_file):
    """
    Extract text from PDF file using PyPDF2
    Handles multi-page PDFs and various PDF formats
    """
    try:
        pdf_file.seek(0)
        
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
        except PyPDF2.errors.PdfReadError:
            return "Error: This PDF appears to be corrupted or password-protected."
        
        if pdf_reader.is_encrypted:
            return "Error: This PDF is password-protected. Please provide an unprotected PDF."
        
        text = ""
        num_pages = len(pdf_reader.pages)
        
        if num_pages > 20:
            text += f"[Warning: Resume has {num_pages} pages - unusually long for a CV]\n\n"
        
        for page_num in range(min(num_pages, 20)):
            try:
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                
                if page_text:
                    text += f"\n--- Page {page_num + 1} ---\n"
                    text += page_text + "\n"
            except Exception:
                text += f"\n[Error extracting page {page_num + 1}]\n"
                continue
        
        if not text.strip():
            return "No text extracted. This appears to be a scanned/image PDF."
        
        return text.strip()
    
    except Exception as e:
        return f"Error: {str(e)}"


def extract_text_from_docx(docx_file):
    """
    Extract ALL text from DOCX file including tables, headers, footers
    """
    try:
        docx_file.seek(0)
        doc = docx.Document(docx_file)
        text_parts = []
        
        # Extract paragraphs
        text_parts.append("=== DOCUMENT CONTENT ===\n")
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)
        
        # Extract tables
        if doc.tables:
            text_parts.append("\n=== TABLES ===\n")
            for table_idx, table in enumerate(doc.tables, 1):
                text_parts.append(f"\n--- Table {table_idx} ---")
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        cell_text = cell.text.strip()
                        if cell_text:
                            row_text.append(cell_text)
                    
                    if row_text:
                        text_parts.append(" | ".join(row_text))
        
        # Extract headers and footers
        for section in doc.sections:
            if section.header:
                header_text = []
                for paragraph in section.header.paragraphs:
                    if paragraph.text.strip():
                        header_text.append(paragraph.text.strip())
                
                if header_text:
                    text_parts.append("\n=== HEADER ===")
                    text_parts.extend(header_text)
            
            if section.footer:
                footer_text = []
                for paragraph in section.footer.paragraphs:
                    if paragraph.text.strip():
                        footer_text.append(paragraph.text.strip())
                
                if footer_text:
                    text_parts.append("\n=== FOOTER ===")
                    text_parts.extend(footer_text)
        
        # Extract metadata
        try:
            core_props = doc.core_properties
            metadata = []
            
            if core_props.title:
                metadata.append(f"Title: {core_props.title}")
            if core_props.author:
                metadata.append(f"Author: {core_props.author}")
            
            if metadata:
                text_parts.append("\n=== DOCUMENT METADATA ===")
                text_parts.extend(metadata)
        except:
            pass
        
        full_text = "\n".join(text_parts)
        
        if not full_text.strip() or full_text == "=== DOCUMENT CONTENT ===\n":
            return "No text could be extracted from DOCX."
        
        return full_text.strip()
    
    except Exception as e:
        return f"Error: {str(e)}"


def candidate_detail(request, pk):
    """Display candidate details with timeline and analytics"""
    candidate = get_object_or_404(Candidate, pk=pk)
    
    # Get workflow timeline
    timeline = workflow_tracker.get_candidate_timeline(candidate)
    
    # Calculate time in each stage
    stage_times = workflow_tracker.calculate_time_in_stage(candidate)
    
    context = {
        'candidate': candidate,
        'timeline': timeline,
        'stage_times': stage_times,
    }
    
    return render(request, 'recruitment/candidate_detail.html', context)


def dashboard(request):
    """Display all candidates with filtering and analytics"""
    
    # Get all candidates with scores
    candidates = Candidate.objects.filter(
        score__isnull=False
    ).select_related('score').order_by('-score__total_score')
    
    # Update ranks
    for index, candidate in enumerate(candidates, start=1):
        candidate.score.rank = index
        candidate.score.save()
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    min_score = request.GET.get('min_score', '')
    search_query = request.GET.get('search', '')
    
    # Apply filters
    if status_filter:
        candidates = candidates.filter(status=status_filter)
    
    if min_score:
        try:
            min_score_value = float(min_score)
            candidates = candidates.filter(score__total_score__gte=min_score_value)
        except ValueError:
            pass
    
    if search_query:
        candidates = candidates.filter(
            models.Q(name__icontains=search_query) |
            models.Q(email__icontains=search_query)
        )
    
    # Get statistics
    total_candidates = candidates.count()
    avg_score = candidates.aggregate(avg=models.Avg('score__total_score'))['avg'] or 0
    
    # Get analytics summary
    analytics_summary = analytics_engine.generate_executive_summary()
    
    context = {
        'candidates': candidates,
        'total_candidates': total_candidates,
        'avg_score': round(avg_score, 2),
        'status_filter': status_filter,
        'min_score': min_score,
        'search_query': search_query,
        'status_choices': Candidate.STATUS_CHOICES,
        'analytics': analytics_summary,
    }
    
    return render(request, 'recruitment/dashboard.html', context)


@staff_member_required
def analytics_dashboard(request):
    """Comprehensive analytics dashboard for administrators"""
    
    # Generate complete analytics report
    analytics_data = analytics_engine.generate_executive_summary()
    
    # Generate fairness report
    fairness_report = fairness_analyzer.generate_fairness_report()
    
    # Generate workflow report
    workflow_report = workflow_tracker.generate_workflow_report()
    
    context = {
        'analytics': analytics_data,
        'fairness': fairness_report,
        'workflow': workflow_report,
    }
    
    return render(request, 'recruitment/analytics_dashboard.html', context)


@staff_member_required
def fairness_report(request):
    """Detailed fairness analysis report"""
    
    report = fairness_analyzer.generate_fairness_report()
    
    context = {
        'report': report,
    }
    
    return render(request, 'recruitment/fairness_report.html', context)


@staff_member_required
def system_health(request):
    """System health check dashboard"""
    
    health = system_integration.get_system_health_check()
    
    context = {
        'health': health,
    }
    
    return render(request, 'recruitment/system_health.html', context)


@require_http_methods(["POST"])
def update_candidate_status(request, pk):
    """Update candidate status with workflow tracking"""
    
    candidate = get_object_or_404(Candidate, pk=pk)
    new_status = request.POST.get('status')
    notes = request.POST.get('notes', '')
    
    if new_status in dict(Candidate.STATUS_CHOICES):
        # Log status change with workflow tracker
        workflow_tracker.log_status_change(
            candidate,
            new_status,
            notes=notes,
            user=request.user.username if request.user.is_authenticated else 'System'
        )
        
        messages.success(request, f'Status updated to {new_status}')
    else:
        messages.error(request, 'Invalid status')
    
    return redirect('candidate_detail', pk=pk)


# API Endpoints for AJAX requests

@require_http_methods(["GET"])
def api_analytics_summary(request):
    """API endpoint for analytics summary"""
    summary = analytics_engine.generate_executive_summary()
    return JsonResponse(summary)


@require_http_methods(["GET"])
def api_fairness_report(request):
    """API endpoint for fairness report"""
    report = fairness_analyzer.generate_fairness_report()
    return JsonResponse(report)


@require_http_methods(["GET"])
def api_workflow_report(request):
    """API endpoint for workflow report"""
    report = workflow_tracker.generate_workflow_report()
    return JsonResponse(report)


@require_http_methods(["GET"])
def api_system_health(request):
    """API endpoint for system health"""
    health = system_integration.get_system_health_check()
    return JsonResponse(health)


@require_http_methods(["GET"])
def api_candidate_timeline(request, pk):
    """API endpoint for candidate timeline"""
    candidate = get_object_or_404(Candidate, pk=pk)
    timeline = workflow_tracker.get_candidate_timeline(candidate)
    return JsonResponse({'timeline': timeline})


def export_analytics_report(request):
    """Export complete analytics report as JSON"""
    
    report = system_integration.generate_system_report()
    
    response = HttpResponse(
        content_type='application/json',
        headers={'Content-Disposition': 'attachment; filename="analytics_report.json"'},
    )
    
    import json
    response.write(json.dumps(report, indent=2, default=str))
    
    return response

def debug_resume(request, pk):
    """DEBUG: See exactly what's being extracted"""
    from django.http import JsonResponse
    
    candidate = Candidate.objects.get(pk=pk)
    
    debug_data = {
        'candidate_name': candidate.name,
        'resume_text_length': len(candidate.resume.parsed_text) if hasattr(candidate, 'resume') else 0,
        'resume_text_preview': candidate.resume.parsed_text[:500] if hasattr(candidate, 'resume') else 'NO RESUME',
        'years_experience': candidate.years_experience,
        'education_count': candidate.education.count(),
        'education_details': list(candidate.education.values('degree', 'field_of_study', 'has_islamic_finance_cert')),
        'experience_count': candidate.experience.count(),
        'experience_details': list(candidate.experience.values('position', 'is_islamic_finance')),
        'skills_count': candidate.skills.count(),
        'skills_details': list(candidate.skills.values('skill_name', 'category')),
        'score': {
            'education': candidate.score.education_score if hasattr(candidate, 'score') else 'NO SCORE',
            'experience': candidate.score.experience_score if hasattr(candidate, 'score') else 'NO SCORE',
            'skills': candidate.score.skills_score if hasattr(candidate, 'score') else 'NO SCORE',
            'islamic_finance': candidate.score.islamic_finance_score if hasattr(candidate, 'score') else 'NO SCORE',
            'total': candidate.score.total_score if hasattr(candidate, 'score') else 'NO SCORE',
        }
    }
    
    return JsonResponse(debug_data, json_dumps_params={'indent': 2})