"""
Security Module
Implements security measures for CV parsing and data handling
Includes input validation, sanitization, and threat detection
"""

import re
import hashlib
from django.core.exceptions import ValidationError
from django.utils.html import escape
import magic  # python-magic for file type verification


class SecurityValidator:
    """
    Validates and sanitizes user inputs and file uploads
    """
    
    def __init__(self):
        # Maximum file sizes (in bytes)
        self.MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        self.MAX_TEXT_LENGTH = 50000  # 50K characters
        
        # Allowed MIME types
        self.ALLOWED_MIME_TYPES = [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
            'application/msword'  # .doc
        ]
        
        # Dangerous patterns in text
        self.DANGEROUS_PATTERNS = [
            r'<script[^>]*>.*?</script>',  # JavaScript
            r'javascript:',  # JavaScript protocol
            r'on\w+\s*=',  # Event handlers
            r'<iframe',  # iframes
            r'<object',  # object tags
            r'<embed',  # embed tags
        ]
    
    def validate_file_upload(self, uploaded_file):
        """
        Comprehensive file upload validation
        Returns: (is_valid, error_message)
        """
        # Check 1: File exists
        if not uploaded_file:
            return False, "No file provided"
        
        # Check 2: File size
        if uploaded_file.size > self.MAX_FILE_SIZE:
            return False, f"File size exceeds maximum allowed ({self.MAX_FILE_SIZE / 1024 / 1024}MB)"
        
        # Check 3: File extension
        file_name = uploaded_file.name.lower()
        allowed_extensions = ['.pdf', '.docx', '.doc']
        
        if not any(file_name.endswith(ext) for ext in allowed_extensions):
            return False, "File type not allowed. Only PDF and DOCX files are accepted"
        
        # Check 4: Verify actual MIME type (not just extension)
        try:
            # Read first 2048 bytes to determine file type
            uploaded_file.seek(0)
            file_header = uploaded_file.read(2048)
            uploaded_file.seek(0)
            
            # Use python-magic to detect actual file type
            mime = magic.from_buffer(file_header, mime=True)
            
            if mime not in self.ALLOWED_MIME_TYPES:
                return False, f"Invalid file type detected: {mime}"
        
        except Exception as e:
            # If magic fails, do basic checks
            if not file_name.endswith(('.pdf', '.docx', '.doc')):
                return False, "File validation failed"
        
        # Check 5: Filename sanitization
        if not self.is_safe_filename(file_name):
            return False, "Filename contains invalid characters"
        
        return True, None
    
    def is_safe_filename(self, filename):
        """
        Check if filename is safe (no path traversal, etc.)
        """
        # Check for path traversal attempts
        if '..' in filename or '/' in filename or '\\' in filename:
            return False
        
        # Check for null bytes
        if '\x00' in filename:
            return False
        
        # Only block dangerous characters, allow most normal ones
        # Block: < > : " / \ | ? * and control characters
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in dangerous_chars:
            if char in filename:
                return False
        
        # Check for control characters
        if any(ord(char) < 32 for char in filename):
            return False
        
        return True
    
    def sanitize_text(self, text):
        """
        Sanitize extracted text from CVs
        """
        if not text:
            return ""
        
        # Check length
        if len(text) > self.MAX_TEXT_LENGTH:
            text = text[:self.MAX_TEXT_LENGTH]
        
        # Remove dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Escape HTML entities
        text = escape(text)
        
        return text
    
    def validate_email(self, email):
        """
        Validate email format
        """
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(email_pattern, email):
            raise ValidationError("Invalid email format")
        
        # Check for common disposable email domains
        disposable_domains = [
            'tempmail.com', 'throwaway.email', '10minutemail.com',
            'guerrillamail.com', 'mailinator.com'
        ]
        
        domain = email.split('@')[1].lower()
        if domain in disposable_domains:
            raise ValidationError("Disposable email addresses are not allowed")
        
        return True
    
    def validate_phone(self, phone):
        """
        Validate phone number format
        """
        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)
        
        # Check length (international format)
        if len(cleaned) < 8 or len(cleaned) > 15:
            raise ValidationError("Invalid phone number length")
        
        # Basic format check
        phone_pattern = r'^\+?\d{8,15}$'
        if not re.match(phone_pattern, cleaned):
            raise ValidationError("Invalid phone number format")
        
        return True
    
    def validate_candidate_input(self, name, email, phone):
        """
        Validate all candidate input fields
        """
        errors = []
        
        # Validate name
        if not name or len(name.strip()) < 2:
            errors.append("Name must be at least 2 characters")
        
        if len(name) > 100:
            errors.append("Name must be less than 100 characters")
        
        # Only allow letters, spaces, hyphens, apostrophes
        if not re.match(r"^[a-zA-Z\s'-]+$", name):
            errors.append("Name contains invalid characters")
        
        # Validate email
        try:
            self.validate_email(email)
        except ValidationError as e:
            errors.append(str(e))
        
        # Validate phone
        try:
            self.validate_phone(phone)
        except ValidationError as e:
            errors.append(str(e))
        
        if errors:
            return False, errors
        
        return True, None
    
    def detect_malicious_content(self, text):
        """
        Detect potentially malicious content in text
        """
        threats = []
        
        # Check for SQL injection patterns
        sql_patterns = [
            r'(union\s+select|drop\s+table|insert\s+into|delete\s+from)',
            r'(--|\#|\/\*)',
            r'(xp_cmdshell|exec\s+master)',
        ]
        
        for pattern in sql_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                threats.append("Potential SQL injection detected")
                break
        
        # Check for XSS patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                threats.append("Potential XSS attack detected")
                break
        
        # Check for command injection
        command_patterns = [
            r'(\||;|`|\$\()',
            r'(bash|sh|cmd|powershell)\s',
        ]
        
        for pattern in command_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                threats.append("Potential command injection detected")
                break
        
        return threats
    
    def generate_file_hash(self, file_content):
        """
        Generate SHA-256 hash of file content
        Useful for duplicate detection
        """
        return hashlib.sha256(file_content).hexdigest()
    
    def rate_limit_check(self, ip_address, max_uploads=10, time_window=3600):
        """
        Check if IP has exceeded rate limit
        time_window in seconds (default 1 hour)
        """
        # This would typically use Redis or database
        # For now, return True (allowed)
        # TODO: Implement with Redis cache
        return True


class DataEncryption:
    """
    Handles encryption of sensitive data
    """
    
    def __init__(self):
        # In production, use environment variables for keys
        self.encryption_key = None  # Would be loaded from secure storage
    
    def encrypt_sensitive_data(self, data):
        """
        Encrypt sensitive candidate data
        TODO: Implement with cryptography library
        """
        # Placeholder for encryption implementation
        return data
    
    def decrypt_sensitive_data(self, encrypted_data):
        """
        Decrypt sensitive candidate data
        TODO: Implement with cryptography library
        """
        # Placeholder for decryption implementation
        return encrypted_data
    
    def hash_password(self, password):
        """
        Hash password using SHA-256
        """
        return hashlib.sha256(password.encode()).hexdigest()


# Global security validator instance
security_validator = SecurityValidator()
data_encryptor = DataEncryption()