"""
Skill Classifier Inference Module
Wrapper for loading and using the trained skill classifier
"""

import joblib
import numpy as np
from pathlib import Path
import sys

class SkillClassifier:
    """Wrapper class for skill classification"""
    
    def __init__(self, classifier, vectorizer):
        self.classifier = classifier
        self.vectorizer = vectorizer
        self._is_loaded = True
    
    @classmethod
    def load(cls, model_dir='models'):
        model_path = Path(model_dir)
        
        classifier_file = model_path / 'skill_classifier.pkl'
        vectorizer_file = model_path / 'tfidf_vectorizer.pkl'
        
        if not classifier_file.exists():
            raise FileNotFoundError(f"Classifier not found: {classifier_file}")
        if not vectorizer_file.exists():
            raise FileNotFoundError(f"Vectorizer not found: {vectorizer_file}")
        
        classifier = joblib.load(classifier_file)
        vectorizer = joblib.load(vectorizer_file)
        
        return cls(classifier, vectorizer)
    
    def _extract_features(self, text_chunks):
        """
        Build full feature vector for inference.
        Matches EXACT preprocessing from training.
        """

        if isinstance(text_chunks, str):
            text_chunks = [text_chunks]
        
        # TF-IDF
        X_tfidf = self.vectorizer.transform(text_chunks).toarray()

        additional_features = []
        for text in text_chunks:

            # FIXED: match training — detect straight + curly quotes
            has_special = int(any(c in text for c in [
                "'", "’", "‘",           # single quotes
                '"', "“", "”"            # double quotes
            ]))
            
            # Training normalizes pos_hash as (hash % 1000) / 1000 → [0,1]
            pos_hash = 0.5
            
            features = [
                len(text.split()),             # word_count
                len(text),                     # char_count
                int(any(c.isdigit() for c in text)),
                has_special,
                0,                             # section flags unknown at inference
                0,
                0,
                pos_hash,
            ]
            
            additional_features.append(features)
        
        additional_features = np.array(additional_features)
        
        # Combine
        return np.hstack([X_tfidf, additional_features])
    
    def predict(self, text_chunks):
        single = isinstance(text_chunks, str)
        
        X = self._extract_features(text_chunks)
        preds = self.classifier.predict(X)
        
        if single:
            return int(preds[0])
        return preds.astype(int)
    
    def predict_proba(self, text_chunks):
        single = isinstance(text_chunks, str)
        
        X = self._extract_features(text_chunks)
        probs = self.classifier.predict_proba(X)[:, 1]
        
        if single:
            return float(probs[0])
        return probs
    
    def batch_predict(self, text_chunks):
        X = self._extract_features(text_chunks)
        preds = self.classifier.predict(X)
        probs = self.classifier.predict_proba(X)[:, 1]
        
        return [
            {
                'text': text,
                'is_skill': bool(pred),
                'confidence': float(prob)
            }
            for text, pred, prob in zip(text_chunks, preds, probs)
        ]
    
    def filter_skills(self, text_chunks, threshold=0.6):
        results = self.batch_predict(text_chunks)
        return [r['text'] for r in results if r['confidence'] >= threshold]
    
    def is_loaded(self):
        return self._is_loaded


# -----------------------------------------------------------
# Convenience API
# -----------------------------------------------------------

_global_classifier = None

def load_classifier(model_dir='models'):
    global _global_classifier
    _global_classifier = SkillClassifier.load(model_dir)
    return _global_classifier

def predict_skill(text):
    if _global_classifier is None:
        raise RuntimeError("Classifier not loaded. Call load_classifier().")
    return _global_classifier.predict(text)

def get_skill_probability(text):
    if _global_classifier is None:
        raise RuntimeError("Classifier not loaded. Call load_classifier().")
    return _global_classifier.predict_proba(text)


# -----------------------------------------------------------
# Self-test
# -----------------------------------------------------------

if __name__ == "__main__":
    try:
        classifier = SkillClassifier.load('models')
        print("✓ Classifier loaded\n")
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)
    
    test_chunks = [
        "Python Programming",
        "Machine Learning",
        "Network Security",
        "Arabian Journal of Science",
        "Comparative Analysis of Models",
        "Signal Processing",
        "Research",
        "Leadership",
        "International Conference on AI",
        "SQL Database Management",
    ]
    
    results = classifier.batch_predict(test_chunks)
    
    print("Testing classifier:")
    print("="*70)
    for r in results:
        flag = "✓ SKILL" if r['is_skill'] else "✗ NOT SKILL"
        print(f"{flag:15s} ({r['confidence']:.2%})  |  {r['text']}")
    
    print("\nFiltered (>60% confidence):")
    for skill in classifier.filter_skills(test_chunks):
        print(f"  • {skill}")
