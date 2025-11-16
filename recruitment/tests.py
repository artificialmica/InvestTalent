from django.test import TestCase
from .models import Candidate, Resume, Score
from .scoring import analyze_resume
import tempfile
from docx import Document

class ScoringTestCase(TestCase):
    
    def create_test_resume(self, text):
        """Helper to create a test Word document"""
        doc = Document()
        doc.add_paragraph(text)
        
        temp_file = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
        doc.save(temp_file.name)
        temp_file.seek(0)
        
        return temp_file
    
    def test_perfect_candidate(self):
        """Test Case 1: Perfect candidate with Islamic Finance expertise"""
        cv_text = """
        SARAH AHMAD - Investment Portfolio Manager
        
        EDUCATION
        PhD in Islamic Finance - University of Bahrain, 2020
        CIFE Certified Islamic Finance Expert
        
        PROFESSIONAL EXPERIENCE
        Senior Portfolio Manager at ABC Islamic Bank (2018-Present)
        7 years managing Sukuk portfolios
        
        SKILLS
        Proficient in: Financial modeling, Bloomberg, Excel
        Expert in: Python, SQL, Sukuk structuring
        """
        
        candidate = Candidate.objects.create(
            name="Sarah Ahmad",
            email="sarah@test.com"
        )
        
        Resume.objects.create(
            candidate=candidate,
            file_type="DOCX",
            parsed_text=cv_text
        )
        
        analyze_resume(candidate)
        
        score = Score.objects.get(candidate=candidate)
        
        # Assertions
        self.assertGreaterEqual(score.education_score, 100)  # PhD + IF cert
        self.assertGreaterEqual(score.experience_score, 90)  # 7 years + IF
        self.assertGreaterEqual(score.skills_score, 85)     # Multiple skills
        self.assertGreaterEqual(score.islamic_finance_score, 80)  # Strong IF
        self.assertGreaterEqual(score.total_score, 90)      # Overall excellent
    
    def test_keyword_stuffing_detection(self):
        """Test Case 4: Keyword stuffing should be flagged"""
        cv_text = """
        python sql excel python sql excel python sql excel
        python sql excel python sql excel python sql excel
        """
        
        candidate = Candidate.objects.create(
            name="Fake Candidate",
            email="fake@test.com"
        )
        
        Resume.objects.create(
            candidate=candidate,
            file_type="DOCX",
            parsed_text=cv_text
        )
        
        analyze_resume(candidate)
        
        score = Score.objects.get(candidate=candidate)
        
        # Should be flagged as 0
        self.assertEqual(score.total_score, 0)
    
    def test_negative_context_filtering(self):
        """Test Case 5: Negative mentions should be filtered"""
        cv_text = """
        I don't know Python. I have no SQL experience.
        I am not proficient in Excel. I lack financial modeling skills.
        """
        
        candidate = Candidate.objects.create(
            name="Negative Candidate",
            email="negative@test.com"
        )
        
        Resume.objects.create(
            candidate=candidate,
            file_type="DOCX",
            parsed_text=cv_text
        )
        
        analyze_resume(candidate)
        
        score = Score.objects.get(candidate=candidate)
        
        # No skills should be extracted
        self.assertEqual(candidate.skills.count(), 0)
        self.assertLess(score.total_score, 20)
    
    def test_junior_candidate(self):
        """Test Case 3: Junior candidate with minimal experience"""
        cv_text = """
        MARIA GARCIA - Recent Graduate
        
        Bachelor in Economics - 2024
        
        Summer Intern at Finance Corp (2023)
        3 months assisting with research
        
        Basic Excel, Learning Python
        """
        
        candidate = Candidate.objects.create(
            name="Maria Garcia",
            email="maria@test.com"
        )
        
        Resume.objects.create(
            candidate=candidate,
            file_type="DOCX",
            parsed_text=cv_text
        )
        
        analyze_resume(candidate)
        
        score = Score.objects.get(candidate=candidate)
        
        # Should have low scores
        self.assertLess(score.experience_score, 50)
        self.assertLess(score.skills_score, 50)
        self.assertLess(score.total_score, 50)
    
    def test_ambiguous_mentions(self):
        """Test Case 7: Mentions without claiming skills"""
        cv_text = """
        During studies, learned about SQL databases.
        Course covered Python programming.
        Manager used Excel for modeling.
        """
        
        candidate = Candidate.objects.create(
            name="Ambiguous",
            email="ambiguous@test.com"
        )
        
        Resume.objects.create(
            candidate=candidate,
            file_type="DOCX",
            parsed_text=cv_text
        )
        
        analyze_resume(candidate)
        
        # Should extract very few or no skills
        self.assertLess(candidate.skills.count(), 2)

# Run tests with: python manage.py test recruitment