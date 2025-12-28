"""
recruitment/auto_extractor.py
FIXED VERSION - Works with your certifications.json format
"""

import re
import spacy
from datetime import datetime
from typing import Dict, List, Optional
import json
import os
import sqlite3

# Load spaCy
try:
    nlp = spacy.load("en_core_web_sm")
except:
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


class CVAutoExtractor:
    
    def __init__(self, text: str):
        self.text = text
        self.text_lower = text.lower()
        self.doc = nlp(text[:10000])
        
    def extract_all(self) -> Dict:
        """Extract ALL information automatically"""
        return {
            'name': self.extract_name(),
            'email': self.extract_email(),
            'phone': self.extract_phone(),
            'linkedin': self.extract_linkedin(),
            'location': self.extract_location(),
            'education': self.extract_education(),
            'experience': self.extract_experience(),
            'certifications': self.extract_certifications(),
            'languages': self.extract_languages(),
            'summary': self.extract_summary(),
        }
    
    # Contact Information (same as before)
    def extract_name(self) -> Optional[str]:
        """Extract candidate name - IMPROVED for edge cases"""
        # Strategy 1: Pattern - case insensitive, handles "Name / Surname"
        name_pattern = r'(?i)(?:name|surname)\s*[/:]\s*(?:surname\s*)?([A-Z][a-z]+(?: [A-Z][a-z]+){1,3})'
        match = re.search(name_pattern, self.text)
        if match:
            potential_name = match.group(1).strip()
            # Exclude common header words
            if potential_name not in ['Professional', 'Email', 'Nationality', 'Gender', 'Employment', 'History', 'Education', 'Scholar', 'Google', 'Updated', 'Surname', 'Name']:
                return potential_name
        
        # Strategy 2: First line with improved detection - scan for name within line
        first_lines = self.text.split('\n')[:10]
        for line in first_lines:
            line = line.strip()
            # Remove common titles
            line = re.sub(r'^(Dr\.|Prof\.|Mr\.|Mrs\.|Ms\.)\s*', '', line)
            words = line.split()
            
            # Try to find 2-4 consecutive capitalized words in the line
            for i in range(len(words)):
                candidate_name = ' '.join(words[i:min(i+4, len(words))])
                name_words = candidate_name.split()
                if 2 <= len(name_words) <= 4:
                    if all(w and len(w) > 1 and w[0].isupper() for w in name_words):
                        if 10 < len(candidate_name) < 50 and not any(c.isdigit() for c in candidate_name):
                            # Exclude header words
                            if not any(header in candidate_name for header in ['Professional', 'Email', 'Nationality', 'Gender', 'Scholar', 'Employment', 'Google', 'Updated', 'Surname', 'Name']):
                                return candidate_name
        
        # Strategy 3: spaCy NER
        # Strategy 3: spaCy NER
        for ent in self.doc.ents:
            if ent.label_ == 'PERSON':
                name = ent.text.strip()
                if 5 < len(name) < 50:
                    # Clean up any labels that spaCy might have included
                    name = re.sub(r'^(surname|name)\s*[:/\-]?\s*', '', name, flags=re.IGNORECASE).strip()
                    if name and not any(header in name for header in ['Professional', 'Email', 'Nationality', 'Gender', 'Scholar']):
                        return name
        
        return None

    
    def extract_email(self) -> Optional[str]:
        """Extract email"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, self.text)
        return match.group(0) if match else None
    
    def extract_phone(self) -> Optional[str]:
        """Extract phone"""
        patterns = [
            r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            r'\d{3}[-.\s]?\d{4}[-.\s]?\d{3,4}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.text)
            if match:
                phone = match.group(0)
                phone = re.sub(r'[^\d+]', '', phone)
                if len(phone) >= 8:
                    return phone
        
        return None
    
    def extract_linkedin(self) -> Optional[str]:
        """Extract LinkedIn"""
        linkedin_pattern = r'linkedin\.com/in/[\w\-]+'
        match = re.search(linkedin_pattern, self.text_lower)
        return f"https://{match.group(0)}" if match else None
    
    def extract_location(self) -> Optional[str]:
        """Extract location"""
        locations = []
        for ent in list(self.doc.ents)[:30]:
            if ent.label_ == 'GPE':
                locations.append(ent.text)
        return locations[0] if locations else None
    
    # Education (same as before)
    def extract_education(self) -> List[Dict]:
        """Extract education"""
        education_list = []
        edu_section = self._find_section('education') or self.text
        
        degree_patterns = {
            'PhD': r'\b(ph\.?d\.?|doctorate|doctoral)\b',
            'Master': r'\b(master|msc|m\.s|m\.sc|mba|m\.e|m\.eng)\b',
            'Bachelor': r'\b(bachelor|bsc|b\.s|b\.sc|b\.e|b\.eng|undergraduate)\b',
            'Diploma': r'\b(diploma|associate)\b',
        }
        
        for degree_name, pattern in degree_patterns.items():
            matches = list(re.finditer(pattern, edu_section.lower()))
            
            for match in matches:
                start = max(0, match.start() - 200)
                end = min(len(edu_section), match.end() + 300)
                context = edu_section[start:end]
                
                # Field
                field_pattern = r'in\s+([A-Z][A-Za-z\s,&\-]{4,80})'
                field_match = re.search(field_pattern, context)
                field = field_match.group(1).strip() if field_match else None
                
                # Institution
                inst_pattern = r'(?:from|at|,)\s+([A-Z][A-Za-z\s,&\-\.\']{5,80}(?:University|Institute|College|School|Academy|Polytechnic))'
                inst_match = re.search(inst_pattern, context)
                institution = inst_match.group(1).strip() if inst_match else None
                
                # Year
                year_pattern = r'\b(19\d{2}|20\d{2})\b'
                years = re.findall(year_pattern, context)
                graduation_year = max(map(int, years)) if years else None
                
                education_list.append({
                    'degree': degree_name,
                    'field_of_study': field,
                    'institution': institution,
                    'graduation_year': graduation_year,
                })
                
                # break removed - now extracts all degrees
        
        return education_list
    
    # Experience (same as before)
    def extract_experience(self) -> List[Dict]:
        """Extract work experience"""
        experience_list = []
        exp_section = self._find_section('experience') or self._find_section('employment')
        if not exp_section:
            return []
        
        entries = re.split(r'\n(?=\d{4}\s*[â€“\-]|\d{4}\s+[-â€“])', exp_section)
        
        for entry in entries[:15]:
            if len(entry) < 20:
                continue
            
            date_pattern = r'(\d{4})\s*[â€“\-â€”]\s*(\d{4}|present|current)'
            date_match = re.search(date_pattern, entry.lower())
            
            if date_match:
                start_year = date_match.group(1)
                end_str = date_match.group(2)
                
                lines = entry.split('\n')
                position = None
                company = None
                
                for i, line in enumerate(lines[:5]):
                    line = line.strip()
                    
                    if any(title in line.lower() for title in ['professor', 'engineer', 'manager', 'analyst', 'director', 'coordinator', 'associate', 'specialist']):
                        position = line
                        
                        if 'at ' in line.lower():
                            parts = line.split(' at ')
                            if len(parts) == 2:
                                position = parts[0].strip()
                                company = parts[1].strip()
                        elif i + 1 < len(lines):
                            company = lines[i + 1].strip()
                        
                        break
                
                description = '\n'.join(lines[2:5]) if len(lines) > 2 else ''
                
                if position or company:
                    experience_list.append({
                        'position': position,
                        'company': company,
                        'start_date': f"{start_year}-01-01",
                        'end_date': 'Present' if end_str.lower() in ['present', 'current'] else f"{end_str}-12-31",
                        'description': description[:500],
                        'is_current': end_str.lower() in ['present', 'current']
                    })
        
        return experience_list
    
    # FIXED: Certifications with YOUR JSON format
    def extract_certifications(self) -> List[Dict]:
        """
        Extract certifications - FIXED for your JSON format
        """
        certifications_found = []
        
        # Load YOUR certification database
        cert_db_path = os.path.join(os.path.dirname(__file__), 'data', 'certifications.json')
        
        try:
            with open(cert_db_path, 'r', encoding='utf-8') as f:
                cert_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load certifications.json: {e}")
            return []
        
        # YOUR FORMAT: {"categories": [{name: "", certifications: [...]}]}
        if 'categories' in cert_data:
            categories = cert_data['categories']
        else:
            categories = []
        
        # Search for each certification
        for category_obj in categories:
            category_name = category_obj.get('name', 'Unknown')
            certs = category_obj.get('certifications', [])
            
            for cert in certs:
                cert_name = cert.get('name', '')
                aliases = cert.get('aliases', [])
                issuer = cert.get('issuer', 'Not specified')
                level = cert.get('level', 'Professional')
                
                # Search for main name
                cert_lower = cert_name.lower()
                if cert_lower in self.text_lower:
                    certifications_found.append({
                        'name': cert_name,
                        'category': category_name,
                        'issuer': issuer,
                        'level': level,
                    })
                    continue
                
                # Search aliases
                found_via_alias = False
                for alias in aliases:
                    alias_lower = alias.lower()
                    # Use word boundaries for accurate matching
                    pattern = r'\b' + re.escape(alias_lower) + r'\b'
                    if re.search(pattern, self.text_lower):
                        certifications_found.append({
                            'name': cert_name,
                            'category': category_name,
                            'issuer': issuer,
                            'level': level,
                        })
                        found_via_alias = True
                        break
                
                if found_via_alias:
                    continue
        
        return certifications_found
    
    # Languages (same)
    def extract_languages(self) -> List[str]:
        """Extract languages"""
        common_languages = [
            'english', 'arabic', 'french', 'spanish', 'german',
            'chinese', 'mandarin', 'hindi', 'urdu', 'italian',
            'portuguese', 'russian', 'japanese', 'korean'
        ]
        
        found_languages = []
        for lang in common_languages:
            pattern = r'\b' + lang + r'\b'
            if re.search(pattern, self.text_lower):
                found_languages.append(lang.capitalize())
        
        return found_languages
    
    # Summary (same)
    def extract_summary(self) -> Optional[str]:
        """Extract summary"""
        summary_section = self._find_section('summary') or self._find_section('objective') or self._find_section('profile')
        
        if summary_section:
            lines = summary_section.split('\n')
            summary = ' '.join(lines[1:6])
            return summary[:500] if summary else None
        
        return None
    
    # Helper
    def _find_section(self, section_name: str) -> Optional[str]:
        """Find CV section"""
        patterns = {
            'education': r'(education|academic\s+background|academic\s+qualifications)',
            'experience': r'(experience|employment\s+history|work\s+experience|professional\s+experience)',
            'employment': r'(employment|work\s+history)',
            'skills': r'(skills|technical\s+skills|core\s+competencies)',
            'certifications': r'(certifications?|licenses?|credentials?)',
            'summary': r'(summary|professional\s+summary)',
            'objective': r'(objective|career\s+objective)',
            'profile': r'(profile|professional\s+profile)',
        }
        
        pattern = patterns.get(section_name, section_name)
        match = re.search(pattern, self.text_lower)
        if not match:
            return None
        
        start_pos = match.start()
        next_section_pattern = r'\n\s*\n\s*(?:education|experience|skills|certifications|publications|references|honors|awards)'
        next_match = re.search(next_section_pattern, self.text_lower[start_pos + 100:])
        
        if next_match:
            end_pos = start_pos + 100 + next_match.start()
        else:
            end_pos = start_pos + 3000
        
        return self.text[start_pos:end_pos]


def auto_extract_cv(cv_text: str) -> Dict:
    """Main function: Auto-extract everything from CV"""
    extractor = CVAutoExtractor(cv_text)
    return extractor.extract_all()

import sqlite3
import re

def extract_esco_skills(text):
    """Extract ESCO skills from resume text using whole-word matching"""
    text = text.lower()
    conn = sqlite3.connect("data/esco.db")
    cur = conn.cursor()
    
    found_skills = {}  # skill_id -> skill_name
    
    # Get all skill aliases
    cur.execute("SELECT skill_id, alias FROM skill_aliases")
    
    for skill_id, alias in cur.fetchall():
        # Skip single-letter aliases (too many false positives)
        if len(alias) <= 2:
            continue
            
        # Create word boundary pattern
        pattern = r'\b' + re.escape(alias) + r'\b'
        
        if re.search(pattern, text):
            # Get the actual skill name
            if skill_id not in found_skills:
                cur.execute("SELECT skill_name FROM skills WHERE skill_id = ?", (skill_id,))
                result = cur.fetchone()
                if result:
                    found_skills[skill_id] = result[0]
    
    conn.close()
    
    # Return both IDs and names
    return [
        {"skill_id": sid, "skill_name": name}
        for sid, name in found_skills.items()
    ]