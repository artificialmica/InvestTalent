from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

# Candidate Model 
class Candidate(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    current_position = models.CharField(max_length=200, blank=True, null=True)
    years_experience = models.IntegerField(default=0)
    linkedin_url = models.URLField(blank=True, null=True)
    
    # Audit fields
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    file_hash = models.CharField(max_length=64, null=True, blank=True)  # SHA-256 hash
    is_verified = models.BooleanField(default=False)
    security_flags = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    STATUS_CHOICES = [
        ('received', 'Application Received'),
        ('screening', 'Under Screening'),
        ('shortlisted', 'Shortlisted'),
        ('interview', 'Interview Scheduled'),
        ('offer', 'Offer Extended'),
        ('hired', 'Hired'),
        ('rejected', 'Rejected'),
    ]
    
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='received'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Candidate'
        verbose_name_plural = 'Candidates'


# Resume Model - NOTICE: No indentation before "class"
class Resume(models.Model):
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='resume')
    file = models.FileField(upload_to='resumes/')
    file_type = models.CharField(max_length=10)
    parsed_text = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Resume for {self.candidate.name}"
    
    class Meta:
        verbose_name = 'Resume'
        verbose_name_plural = 'Resumes'


# Education Model - Same level as Resume and Candidate
class Education(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='education')
    degree = models.CharField(max_length=100)
    institution = models.CharField(max_length=200)
    field_of_study = models.CharField(max_length=100)
    graduation_year = models.IntegerField(blank=True, null=True)
    has_islamic_finance_cert = models.BooleanField(default=False)
    certification_names = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.degree} - {self.institution}"
    
    class Meta:
        verbose_name = 'Education'
        verbose_name_plural = 'Education Records'
        ordering = ['-graduation_year']


# Experience Model
class Experience(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='experience')
    company = models.CharField(max_length=200)
    position = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)
    is_islamic_finance = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.position} at {self.company}"
    
    class Meta:
        verbose_name = 'Work Experience'
        verbose_name_plural = 'Work Experience Records'
        ordering = ['-start_date']


# Skill Model
class Skill(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='skills')
    skill_name = models.CharField(max_length=100)
    
    PROFICIENCY_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ]
    
    proficiency_level = models.CharField(max_length=20, choices=PROFICIENCY_LEVELS, default='intermediate')
    
    SKILL_CATEGORIES = [
        ('technical', 'Technical'),
        ('finance', 'Finance'),
        ('islamic_finance', 'Islamic Finance'),
        ('soft_skill', 'Soft Skill'),
        ('language', 'Language'),
    ]
    
    category = models.CharField(max_length=20, choices=SKILL_CATEGORIES, default='technical')
    
    def __str__(self):
        return f"{self.skill_name} ({self.proficiency_level})"
    
    class Meta:
        verbose_name = 'Skill'
        verbose_name_plural = 'Skills'


# Score Model
class Score(models.Model):
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='score')
    education_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    experience_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    skills_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    islamic_finance_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    total_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    rank = models.IntegerField(blank=True, null=True)
    evaluated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Score for {self.candidate.name}: {self.total_score}/100"
    
    class Meta:
        verbose_name = 'Score'
        verbose_name_plural = 'Scores'
        ordering = ['-total_score']