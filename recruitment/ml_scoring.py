import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
import pickle
import os

class MLScoreEnhancer:
    """
    Machine Learning layer to enhance rule-based scores
    This learns from historical hiring decisions to refine scoring
    """
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=100)
        self.quality_predictor = RandomForestClassifier(n_estimators=50, random_state=42)
        self.is_trained = False
        self.model_path = 'recruitment/ml_models/'
        
    def extract_ml_features(self, candidate):
        """
        Extract features for ML model
        Combines text features with structured data
        """
        features = {}
        
        # Text-based features
        resume_text = candidate.resume.parsed_text.lower()
        
        # Structural features
        features['word_count'] = len(resume_text.split())
        features['education_count'] = candidate.education.count()
        features['experience_count'] = candidate.experience.count()
        features['skill_count'] = candidate.skills.count()
        features['has_islamic_finance'] = 1 if candidate.skills.filter(category='islamic_finance').exists() else 0
        
        # Keyword density features
        finance_keywords = ['financial', 'investment', 'portfolio', 'analysis']
        features['finance_keyword_density'] = sum(1 for kw in finance_keywords if kw in resume_text) / len(resume_text.split())
        
        # Score-based features (from rule-based system)
        if hasattr(candidate, 'score'):
            features['rule_education_score'] = candidate.score.education_score
            features['rule_experience_score'] = candidate.score.experience_score
            features['rule_skills_score'] = candidate.score.skills_score
            features['rule_if_score'] = candidate.score.islamic_finance_score
        
        return features
    
    def train_model(self, training_candidates, outcomes):
        """
        Train ML model on historical hiring data
        
        Args:
            training_candidates: List of Candidate objects
            outcomes: List of 1 (hired) or 0 (rejected)
        """
        if len(training_candidates) < 10:
            print("Not enough training data. Need at least 10 candidates.")
            return False
        
        # Extract features for all candidates
        X = []
        for candidate in training_candidates:
            features = self.extract_ml_features(candidate)
            X.append(list(features.values()))
        
        X = np.array(X)
        y = np.array(outcomes)
        
        # Train the model
        self.quality_predictor.fit(X, y)
        self.is_trained = True
        
        # Save model
        self.save_model()
        
        print(f"Model trained on {len(training_candidates)} candidates")
        print(f"Training accuracy: {self.quality_predictor.score(X, y):.2%}")
        
        return True
    
    def predict_quality(self, candidate):
        """
        Predict hiring likelihood (0-100)
        Returns None if model not trained
        """
        if not self.is_trained:
            return None
        
        features = self.extract_ml_features(candidate)
        X = np.array([list(features.values())])
        
        # Get probability of being hired
        probability = self.quality_predictor.predict_proba(X)[0][1]
        
        return round(probability * 100, 2)
    
    def get_enhanced_score(self, candidate, rule_based_score):
        """
        Combine rule-based score with ML prediction
        70% rule-based (explainable) + 30% ML (pattern-based)
        """
        ml_score = self.predict_quality(candidate)
        
        if ml_score is None:
            # ML not trained yet, use only rule-based
            return rule_based_score
        
        # Weighted combination
        enhanced_score = (rule_based_score * 0.7) + (ml_score * 0.3)
        
        return round(enhanced_score, 2)
    
    def save_model(self):
        """Save trained model to disk"""
        os.makedirs(self.model_path, exist_ok=True)
        
        with open(self.model_path + 'quality_predictor.pkl', 'wb') as f:
            pickle.dump(self.quality_predictor, f)
        
        with open(self.model_path + 'vectorizer.pkl', 'wb') as f:
            pickle.dump(self.vectorizer, f)
    
    def load_model(self):
        """Load trained model from disk"""
        try:
            with open(self.model_path + 'quality_predictor.pkl', 'rb') as f:
                self.quality_predictor = pickle.load(f)
            
            with open(self.model_path + 'vectorizer.pkl', 'rb') as f:
                self.vectorizer = pickle.load(f)
            
            self.is_trained = True
            return True
        except FileNotFoundError:
            return False


# Global ML enhancer instance
ml_enhancer = MLScoreEnhancer()
ml_enhancer.load_model()  # Try to load existing model