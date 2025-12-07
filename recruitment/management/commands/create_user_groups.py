"""
Django management command to create user groups and permissions for RBAC
Run with: python manage.py create_user_groups
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from recruitment.models import Candidate, Resume, Score, JobPosting


class Command(BaseCommand):
    help = 'Creates user groups and assigns permissions for RBAC'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('🔐 Creating RBAC Groups and Permissions...'))
        
        # Clear existing groups (for development)
        Group.objects.all().delete()
        
        # ============================================
        # 1. HR ADMIN - FULL ACCESS
        # ============================================
        hr_admin, created = Group.objects.get_or_create(name='HR Admin')
        
        # Get all permissions for recruitment models
        candidate_ct = ContentType.objects.get_for_model(Candidate)
        resume_ct = ContentType.objects.get_for_model(Resume)
        score_ct = ContentType.objects.get_for_model(Score)
        job_ct = ContentType.objects.get_for_model(JobPosting)
        
        hr_admin_permissions = [
            # Candidate permissions
            Permission.objects.get(codename='add_candidate', content_type=candidate_ct),
            Permission.objects.get(codename='change_candidate', content_type=candidate_ct),
            Permission.objects.get(codename='delete_candidate', content_type=candidate_ct),
            Permission.objects.get(codename='view_candidate', content_type=candidate_ct),
            
            # Resume permissions
            Permission.objects.get(codename='add_resume', content_type=resume_ct),
            Permission.objects.get(codename='change_resume', content_type=resume_ct),
            Permission.objects.get(codename='delete_resume', content_type=resume_ct),
            Permission.objects.get(codename='view_resume', content_type=resume_ct),
            
            # Score permissions
            Permission.objects.get(codename='add_score', content_type=score_ct),
            Permission.objects.get(codename='change_score', content_type=score_ct),
            Permission.objects.get(codename='delete_score', content_type=score_ct),
            Permission.objects.get(codename='view_score', content_type=score_ct),
            
            # Job Posting permissions
            Permission.objects.get(codename='add_jobposting', content_type=job_ct),
            Permission.objects.get(codename='change_jobposting', content_type=job_ct),
            Permission.objects.get(codename='delete_jobposting', content_type=job_ct),
            Permission.objects.get(codename='view_jobposting', content_type=job_ct),
        ]
        
        hr_admin.permissions.set(hr_admin_permissions)
        self.stdout.write(self.style.SUCCESS(f'✅ HR Admin group created with {len(hr_admin_permissions)} permissions'))
        
        # ============================================
        # 2. HIRING MANAGER - VIEW, CHANGE STATUS, NO DELETE
        # ============================================
        hiring_manager, created = Group.objects.get_or_create(name='Hiring Manager')
        
        hiring_manager_permissions = [
            # Can view and change candidates (update status)
            Permission.objects.get(codename='view_candidate', content_type=candidate_ct),
            Permission.objects.get(codename='change_candidate', content_type=candidate_ct),
            
            # Can view resumes and scores
            Permission.objects.get(codename='view_resume', content_type=resume_ct),
            Permission.objects.get(codename='view_score', content_type=score_ct),
            
            # Can view job postings
            Permission.objects.get(codename='view_jobposting', content_type=job_ct),
        ]
        
        hiring_manager.permissions.set(hiring_manager_permissions)
        self.stdout.write(self.style.SUCCESS(f'✅ Hiring Manager group created with {len(hiring_manager_permissions)} permissions'))
        
        # ============================================
        # 3. EXECUTIVE - READ-ONLY (VIEW ONLY)
        # ============================================
        executive, created = Group.objects.get_or_create(name='Executive')
        
        executive_permissions = [
            # View-only access to all data
            Permission.objects.get(codename='view_candidate', content_type=candidate_ct),
            Permission.objects.get(codename='view_resume', content_type=resume_ct),
            Permission.objects.get(codename='view_score', content_type=score_ct),
            Permission.objects.get(codename='view_jobposting', content_type=job_ct),
        ]
        
        executive.permissions.set(executive_permissions)
        self.stdout.write(self.style.SUCCESS(f'✅ Executive group created with {len(executive_permissions)} permissions'))
        
        # ============================================
        # SUMMARY
        # ============================================
        self.stdout.write(self.style.SUCCESS('\n📊 RBAC Groups Summary:'))
        self.stdout.write(self.style.SUCCESS('━' * 60))
        self.stdout.write(f'  👤 HR Admin        : {hr_admin.permissions.count()} permissions (FULL ACCESS)')
        self.stdout.write(f'  👤 Hiring Manager  : {hiring_manager.permissions.count()} permissions (VIEW + EDIT)')
        self.stdout.write(f'  👤 Executive       : {executive.permissions.count()} permissions (VIEW ONLY)')
        self.stdout.write(self.style.SUCCESS('━' * 60))
        
        self.stdout.write(self.style.SUCCESS('\n✅ RBAC setup complete!'))
        self.stdout.write(self.style.WARNING('\n📝 Next steps:'))
        self.stdout.write('   1. Assign users to groups in Django admin')
        self.stdout.write('   2. Add permission checks to views')
        self.stdout.write('   3. Update templates to hide buttons based on permissions')
