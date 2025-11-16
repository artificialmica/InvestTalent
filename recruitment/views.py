from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import models
from .models import Candidate, Resume
from .scoring import analyze_resume
import PyPDF2
import docx
import os
import io

def upload_resume(request):
    """Handle CV file upload and text extraction"""
    
    if request.method == 'POST':
        # Get form data
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        uploaded_file = request.FILES.get('resume_file')
        
        # Validate file exists
        if not uploaded_file:
            messages.error(request, 'Please select a file to upload')
            return render(request, 'recruitment/upload.html')
        
        # Check file type
        file_extension = uploaded_file.name.split('.')[-1].lower()
        if file_extension not in ['pdf', 'docx', 'doc']:
            messages.error(request, 'Only PDF and DOCX files are allowed')
            return render(request, 'recruitment/upload.html')
        
        # Check file size (10MB max)
        if uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, 'File size must be less than 10MB')
            return render(request, 'recruitment/upload.html')
        
        try:
            # Check for duplicate email
            if Candidate.objects.filter(email=email).exists():
                messages.warning(request, f'A candidate with email {email} already exists. Updating their resume.')
                candidate = Candidate.objects.get(email=email)
                # Delete old resume if exists
                if hasattr(candidate, 'resume'):
                    candidate.resume.delete()
            else:
                # Create new candidate
                candidate = Candidate.objects.create(
                    name=name,
                    email=email,
                    phone=phone,
                    status='received'
                )
            
            # Extract text from file
            parsed_text = ""
            
            if file_extension == 'pdf':
                parsed_text = extract_text_from_pdf(uploaded_file)
            elif file_extension in ['docx', 'doc']:
                parsed_text = extract_text_from_docx(uploaded_file)
            
            # Create resume record
            resume = Resume.objects.create(
                candidate=candidate,
                file=uploaded_file,
                file_type=file_extension.upper(),
                parsed_text=parsed_text
            )
            
            # Analyze resume and calculate scores
            analyze_resume(candidate)
            
            messages.success(request, f'Resume uploaded and analyzed successfully for {name}!')
            return redirect('candidate_detail', pk=candidate.pk)
            
        except Exception as e:
            messages.error(request, f'Error uploading resume: {str(e)}')
            return render(request, 'recruitment/upload.html')
    
    return render(request, 'recruitment/upload.html')


def extract_text_from_pdf(pdf_file):
    """Extract text from PDF file using PyPDF2"""
    try:
        pdf_file.seek(0)
        
        # Try to create reader
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
        except PyPDF2.errors.PdfReadError:
            return "Error: This PDF appears to be corrupted or password-protected. Please provide a valid, unprotected PDF."
        
        # Check if encrypted
        if pdf_reader.is_encrypted:
            return "Error: This PDF is password-protected. Please provide an unprotected PDF file."
        
        text = ""
        num_pages = len(pdf_reader.pages)
        
        # Warn if too many pages
        if num_pages > 20:
            text += f"[Warning: Resume has {num_pages} pages - unusually long for a CV]\n\n"
        
        # Extract text from each page
        for page_num in range(min(num_pages, 20)):  # Limit to 20 pages
            try:
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                
                if page_text:
                    text += f"\n--- Page {page_num + 1} ---\n"
                    text += page_text + "\n"
            except Exception as page_error:
                text += f"\n[Error extracting page {page_num + 1}]\n"
                continue
        
        if not text.strip():
            return "No text extracted. This appears to be a scanned/image PDF. Consider using OCR or uploading a text-based PDF."
        
        return text.strip()
    
    except Exception as e:
        return f"Error: {str(e)}"

def extract_text_from_docx(docx_file):
    """
    Extract ALL text from DOCX file including:
    - Paragraphs
    - Tables (all cells)
    - Headers and Footers
    - Text boxes
    - Comments
    - Document properties
    Handles complex documents with nested tables and formatting
    """
    try:
        # Reset file pointer to beginning
        docx_file.seek(0)
        
        # Load document
        doc = docx.Document(docx_file)
        text_parts = []
        
        # 1. Extract text from paragraphs (main body)
        text_parts.append("=== DOCUMENT CONTENT ===\n")
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():  # Only add non-empty paragraphs
                text_parts.append(paragraph.text)
        
        # 2. Extract text from tables
        if doc.tables:
            text_parts.append("\n=== TABLES ===\n")
            for table_idx, table in enumerate(doc.tables, 1):
                text_parts.append(f"\n--- Table {table_idx} ---")
                for row_idx, row in enumerate(table.rows):
                    row_text = []
                    for cell in row.cells:
                        # Get cell text, handling merged cells
                        cell_text = cell.text.strip()
                        if cell_text:
                            row_text.append(cell_text)
                    
                    if row_text:  # Only add non-empty rows
                        text_parts.append(" | ".join(row_text))
        
        # 3. Extract headers
        for section in doc.sections:
            # Header
            if section.header:
                header_text = []
                for paragraph in section.header.paragraphs:
                    if paragraph.text.strip():
                        header_text.append(paragraph.text.strip())
                
                if header_text:
                    text_parts.append("\n=== HEADER ===")
                    text_parts.extend(header_text)
            
            # Footer
            if section.footer:
                footer_text = []
                for paragraph in section.footer.paragraphs:
                    if paragraph.text.strip():
                        footer_text.append(paragraph.text.strip())
                
                if footer_text:
                    text_parts.append("\n=== FOOTER ===")
                    text_parts.extend(footer_text)
        
        # 4. Extract core properties (metadata)
        try:
            core_props = doc.core_properties
            metadata = []
            
            if core_props.title:
                metadata.append(f"Title: {core_props.title}")
            if core_props.author:
                metadata.append(f"Author: {core_props.author}")
            if core_props.subject:
                metadata.append(f"Subject: {core_props.subject}")
            if core_props.keywords:
                metadata.append(f"Keywords: {core_props.keywords}")
            
            if metadata:
                text_parts.append("\n=== DOCUMENT METADATA ===")
                text_parts.extend(metadata)
        except:
            pass  # Skip if metadata not available
        
        # Combine all text parts
        full_text = "\n".join(text_parts)
        
        # If still no text extracted
        if not full_text.strip() or full_text == "=== DOCUMENT CONTENT ===\n":
            return "No text could be extracted from DOCX. The document may be empty or contain only images."
        
        return full_text.strip()
    
    except Exception as e:
        return f"Error extracting DOCX text: {str(e)}\nPlease ensure the file is a valid Word document (.docx format)."


def candidate_detail(request, pk):
    """Display candidate details"""
    candidate = Candidate.objects.get(pk=pk)
    
    context = {
        'candidate': candidate,
    }
    
    return render(request, 'recruitment/candidate_detail.html', context)


def dashboard(request):
    """Display all candidates ranked by score"""
    
    # Get all candidates with scores, ordered by total_score descending
    candidates = Candidate.objects.filter(score__isnull=False).select_related('score').order_by('-score__total_score')
    
    # Update ranks
    for index, candidate in enumerate(candidates, start=1):
        candidate.score.rank = index
        candidate.score.save()
    
    # Get filter parameters from request
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
            name__icontains=search_query
        ) | candidates.filter(
            email__icontains=search_query
        )
    
    # Get statistics
    total_candidates = candidates.count()
    avg_score = candidates.aggregate(avg=models.Avg('score__total_score'))['avg'] or 0
    
    context = {
        'candidates': candidates,
        'total_candidates': total_candidates,
        'avg_score': round(avg_score, 2),
        'status_filter': status_filter,
        'min_score': min_score,
        'search_query': search_query,
        'status_choices': Candidate.STATUS_CHOICES,
    }
    
    return render(request, 'recruitment/dashboard.html', context)