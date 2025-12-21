"""
ML Classifier Visualization Script
Generates thesis-ready charts for skill classification results

Charts generated:
1. Confusion Matrix (heatmap)
2. ROC Curve with AUC
3. Precision-Recall Curve
4. Feature Importance (top 20)
5. Class Distribution (before/after SMOTE)
6. Cross-Validation Scores
7. Classification Metrics Bar Chart

Author: InvestTalent-AI Project
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit, cross_val_score
from sklearn.metrics import (
    confusion_matrix, classification_report, accuracy_score,
    f1_score, precision_score, recall_score, roc_curve, auc,
    precision_recall_curve, roc_auc_score
)
from sklearn.preprocessing import StandardScaler
import joblib
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Try to import SMOTE
try:
    from imblearn.over_sampling import SMOTE
    SMOTE_AVAILABLE = True
except ImportError:
    SMOTE_AVAILABLE = False
    print("[!] Install imbalanced-learn for SMOTE: pip install imbalanced-learn")

# Set style for thesis-quality plots
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['figure.figsize'] = (10, 8)
plt.rcParams['font.size'] = 12
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['figure.dpi'] = 150

# Colors - professional blue palette
COLORS = {
    'primary': '#2563eb',
    'secondary': '#7c3aed', 
    'success': '#059669',
    'danger': '#dc2626',
    'warning': '#d97706',
    'info': '#0891b2',
    'light': '#f3f4f6',
    'dark': '#1f2937'
}


def load_and_prepare_data(filepath):
    """Load data and prepare features"""
    print(f"Loading data from {filepath}...")
    df = pd.read_csv(filepath)
    df = df[df['label'].notna()].copy()
    
    texts = df["text"].fillna("").astype(str).values
    
    vectorizer = TfidfVectorizer(
        max_features=2000,
        ngram_range=(1, 3),
        min_df=1,
        max_df=0.95,
        strip_accents="unicode",
        lowercase=True,
        sublinear_tf=True
    )
    X_tfidf = vectorizer.fit_transform(texts)
    feature_names = list(vectorizer.get_feature_names_out())
    
    X = X_tfidf.toarray()
    
    # Add engineered features
    extra = []
    for _, row in df.iterrows():
        text = str(row["text"]) if pd.notna(row["text"]) else ""
        pos_hash = (hash(str(row["pos_pattern"])) % 1000) / 1000.0
        section = str(row["section"]).lower() if pd.notna(row["section"]) else ""
        word_count = row["word_count"] if pd.notna(row["word_count"]) else 0
        char_count = row["char_count"] if pd.notna(row["char_count"]) else 0
        has_uppercase = 1 if any(c.isupper() for c in text) else 0
        avg_word_len = char_count / max(word_count, 1)
        is_short = 1 if word_count <= 3 else 0
        text_lower = text.lower()
        has_tech_suffix = 1 if any(text_lower.endswith(s) for s in ['.js', '.py', 'sql', 'ml', 'ai']) else 0
        
        item = [
            word_count, char_count,
            int(row["has_digit"]) if pd.notna(row["has_digit"]) else 0,
            int(row["has_special"]) if pd.notna(row["has_special"]) else 0,
            has_uppercase, avg_word_len, is_short, has_tech_suffix,
            1 if section == "skills" else 0,
            1 if section == "education" else 0,
            1 if section == "experience" else 0,
            1 if section == "certifications" else 0,
            1 if section == "profile" else 0,
            pos_hash,
        ]
        extra.append(item)
    
    extra = np.array(extra)
    extra_names = [
        'word_count', 'char_count', 'has_numbers', 'has_special',
        'has_uppercase', 'avg_word_len', 'is_short', 'has_tech_suffix',
        'section_skills', 'section_education', 'section_experience',
        'section_certifications', 'section_profile', 'pos_hash'
    ]
    feature_names.extend(extra_names)
    
    X_combined = np.hstack([X, extra])
    scaler = StandardScaler(with_mean=False)
    X_combined = scaler.fit_transform(X_combined)
    
    y = df["label"].values.astype(int)
    
    return X_combined, y, feature_names, df


def plot_confusion_matrix(y_test, y_pred, save_path='confusion_matrix.png'):
    """Plot beautiful confusion matrix heatmap"""
    cm = confusion_matrix(y_test, y_pred)
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=['Non-Skill', 'Skill'],
                yticklabels=['Non-Skill', 'Skill'],
                annot_kws={'size': 20, 'weight': 'bold'},
                ax=ax)
    
    ax.set_xlabel('Predicted Label', fontsize=14, fontweight='bold')
    ax.set_ylabel('Actual Label', fontsize=14, fontweight='bold')
    ax.set_title('Confusion Matrix\nSkill Classification Model', fontsize=16, fontweight='bold', pad=20)
    
    # Add accuracy annotation
    accuracy = (cm[0,0] + cm[1,1]) / cm.sum()
    ax.text(0.5, -0.15, f'Accuracy: {accuracy:.1%}', transform=ax.transAxes,
            ha='center', fontsize=12, style='italic')
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Saved: {save_path}")
    return cm


def plot_roc_curve(y_test, y_proba, save_path='roc_curve.png'):
    """Plot ROC curve with AUC"""
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    roc_auc = auc(fpr, tpr)
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    ax.plot(fpr, tpr, color=COLORS['primary'], lw=3, 
            label=f'ROC Curve (AUC = {roc_auc:.3f})')
    ax.plot([0, 1], [0, 1], color=COLORS['danger'], lw=2, linestyle='--', 
            label='Random Classifier')
    
    ax.fill_between(fpr, tpr, alpha=0.3, color=COLORS['primary'])
    
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.set_xlabel('False Positive Rate', fontsize=14, fontweight='bold')
    ax.set_ylabel('True Positive Rate', fontsize=14, fontweight='bold')
    ax.set_title('ROC Curve\nSkill Classification Model', fontsize=16, fontweight='bold', pad=20)
    ax.legend(loc='lower right', fontsize=12)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Saved: {save_path}")
    return roc_auc


def plot_precision_recall_curve(y_test, y_proba, save_path='precision_recall_curve.png'):
    """Plot Precision-Recall curve"""
    precision, recall, _ = precision_recall_curve(y_test, y_proba)
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    ax.plot(recall, precision, color=COLORS['secondary'], lw=3, 
            label='Precision-Recall Curve')
    ax.fill_between(recall, precision, alpha=0.3, color=COLORS['secondary'])
    
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.set_xlabel('Recall', fontsize=14, fontweight='bold')
    ax.set_ylabel('Precision', fontsize=14, fontweight='bold')
    ax.set_title('Precision-Recall Curve\nSkill Classification Model', fontsize=16, fontweight='bold', pad=20)
    ax.legend(loc='lower left', fontsize=12)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Saved: {save_path}")


def plot_feature_importance(classifier, feature_names, save_path='feature_importance.png', top_n=20):
    """Plot top feature importances"""
    if hasattr(classifier, 'coef_'):
        importance = classifier.coef_[0]
    else:
        print("Classifier doesn't have feature importances")
        return
    
    # Get top positive and negative features
    indices = np.argsort(importance)
    top_positive = indices[-top_n:]
    top_negative = indices[:top_n]
    
    top_indices = np.concatenate([top_negative[:10], top_positive[-10:]])
    top_importance = importance[top_indices]
    top_names = [feature_names[i] if i < len(feature_names) else f'feature_{i}' for i in top_indices]
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    colors = [COLORS['danger'] if x < 0 else COLORS['success'] for x in top_importance]
    bars = ax.barh(range(len(top_importance)), top_importance, color=colors, edgecolor='white', linewidth=0.5)
    
    ax.set_yticks(range(len(top_importance)))
    ax.set_yticklabels(top_names, fontsize=10)
    ax.set_xlabel('Feature Coefficient', fontsize=14, fontweight='bold')
    ax.set_title('Top 20 Feature Importances\nGreen = Skill Indicator | Red = Non-Skill Indicator', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    ax.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Saved: {save_path}")


def plot_class_distribution(y_original, y_smote, save_path='class_distribution.png'):
    """Plot class distribution before and after SMOTE"""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Before SMOTE
    counts_before = [sum(y_original == 0), sum(y_original == 1)]
    colors = [COLORS['info'], COLORS['warning']]
    
    axes[0].bar(['Non-Skill', 'Skill'], counts_before, color=colors, edgecolor='white', linewidth=2)
    axes[0].set_title('Before SMOTE', fontsize=14, fontweight='bold')
    axes[0].set_ylabel('Count', fontsize=12, fontweight='bold')
    for i, v in enumerate(counts_before):
        axes[0].text(i, v + 20, str(v), ha='center', fontweight='bold', fontsize=12)
    
    # After SMOTE
    counts_after = [sum(y_smote == 0), sum(y_smote == 1)]
    axes[1].bar(['Non-Skill', 'Skill'], counts_after, color=colors, edgecolor='white', linewidth=2)
    axes[1].set_title('After SMOTE', fontsize=14, fontweight='bold')
    axes[1].set_ylabel('Count', fontsize=12, fontweight='bold')
    for i, v in enumerate(counts_after):
        axes[1].text(i, v + 20, str(v), ha='center', fontweight='bold', fontsize=12)
    
    fig.suptitle('Class Distribution: Effect of SMOTE Oversampling', fontsize=16, fontweight='bold', y=1.02)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Saved: {save_path}")


def plot_metrics_comparison(metrics_dict, save_path='metrics_comparison.png'):
    """Plot bar chart of classification metrics"""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    metrics = list(metrics_dict.keys())
    values = list(metrics_dict.values())
    
    colors = [COLORS['primary'], COLORS['secondary'], COLORS['success'], 
              COLORS['warning'], COLORS['info'], COLORS['danger']][:len(metrics)]
    
    bars = ax.bar(metrics, values, color=colors, edgecolor='white', linewidth=2)
    
    ax.set_ylim(0, 1.1)
    ax.set_ylabel('Score', fontsize=14, fontweight='bold')
    ax.set_title('Classification Model Performance Metrics', fontsize=16, fontweight='bold', pad=20)
    ax.axhline(y=0.9, color='green', linestyle='--', alpha=0.5, label='Target (90%)')
    
    # Add value labels
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02, 
                f'{val:.1%}', ha='center', fontweight='bold', fontsize=11)
    
    ax.legend(loc='lower right')
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Saved: {save_path}")


def plot_cv_scores(cv_scores, save_path='cv_scores.png'):
    """Plot cross-validation scores"""
    fig, ax = plt.subplots(figsize=(8, 5))
    
    folds = [f'Fold {i+1}' for i in range(len(cv_scores))]
    colors = [COLORS['primary']] * len(cv_scores)
    
    bars = ax.bar(folds, cv_scores, color=colors, edgecolor='white', linewidth=2)
    ax.axhline(y=np.mean(cv_scores), color=COLORS['danger'], linestyle='--', 
               linewidth=2, label=f'Mean: {np.mean(cv_scores):.1%}')
    
    ax.set_ylim(0, 1.1)
    ax.set_ylabel('F1 Score', fontsize=14, fontweight='bold')
    ax.set_title('5-Fold Cross-Validation Results', fontsize=16, fontweight='bold', pad=20)
    ax.legend(loc='lower right', fontsize=12)
    
    for bar, val in zip(bars, cv_scores):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{val:.1%}', ha='center', fontweight='bold', fontsize=10)
    
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Saved: {save_path}")


def plot_all_in_one(cm, y_test, y_proba, metrics_dict, cv_scores, save_path='model_summary.png'):
    """Create a comprehensive summary figure with all key visualizations"""
    fig = plt.figure(figsize=(16, 12))
    
    # Confusion Matrix (top left)
    ax1 = fig.add_subplot(2, 3, 1)
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=['Non-Skill', 'Skill'],
                yticklabels=['Non-Skill', 'Skill'],
                annot_kws={'size': 14, 'weight': 'bold'}, ax=ax1)
    ax1.set_xlabel('Predicted', fontweight='bold')
    ax1.set_ylabel('Actual', fontweight='bold')
    ax1.set_title('Confusion Matrix', fontsize=12, fontweight='bold')
    
    # ROC Curve (top middle)
    ax2 = fig.add_subplot(2, 3, 2)
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    roc_auc = auc(fpr, tpr)
    ax2.plot(fpr, tpr, color=COLORS['primary'], lw=2, label=f'AUC = {roc_auc:.3f}')
    ax2.plot([0, 1], [0, 1], color=COLORS['danger'], lw=1, linestyle='--')
    ax2.fill_between(fpr, tpr, alpha=0.3, color=COLORS['primary'])
    ax2.set_xlabel('False Positive Rate', fontweight='bold')
    ax2.set_ylabel('True Positive Rate', fontweight='bold')
    ax2.set_title('ROC Curve', fontsize=12, fontweight='bold')
    ax2.legend(loc='lower right')
    ax2.grid(True, alpha=0.3)
    
    # Precision-Recall Curve (top right)
    ax3 = fig.add_subplot(2, 3, 3)
    precision, recall, _ = precision_recall_curve(y_test, y_proba)
    ax3.plot(recall, precision, color=COLORS['secondary'], lw=2)
    ax3.fill_between(recall, precision, alpha=0.3, color=COLORS['secondary'])
    ax3.set_xlabel('Recall', fontweight='bold')
    ax3.set_ylabel('Precision', fontweight='bold')
    ax3.set_title('Precision-Recall Curve', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    
    # Metrics Bar Chart (bottom left)
    ax4 = fig.add_subplot(2, 3, 4)
    metrics = list(metrics_dict.keys())
    values = list(metrics_dict.values())
    colors = [COLORS['primary'], COLORS['secondary'], COLORS['success'], 
              COLORS['warning'], COLORS['info']][:len(metrics)]
    bars = ax4.bar(metrics, values, color=colors, edgecolor='white')
    ax4.set_ylim(0, 1.1)
    ax4.set_ylabel('Score', fontweight='bold')
    ax4.set_title('Performance Metrics', fontsize=12, fontweight='bold')
    for bar, val in zip(bars, values):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{val:.0%}', ha='center', fontsize=9, fontweight='bold')
    ax4.tick_params(axis='x', rotation=45)
    ax4.grid(True, alpha=0.3, axis='y')
    
    # Cross-Validation Scores (bottom middle)
    ax5 = fig.add_subplot(2, 3, 5)
    folds = [f'F{i+1}' for i in range(len(cv_scores))]
    ax5.bar(folds, cv_scores, color=COLORS['primary'], edgecolor='white')
    ax5.axhline(y=np.mean(cv_scores), color=COLORS['danger'], linestyle='--', 
                linewidth=2, label=f'Mean: {np.mean(cv_scores):.0%}')
    ax5.set_ylim(0, 1.1)
    ax5.set_ylabel('F1 Score', fontweight='bold')
    ax5.set_title('Cross-Validation', fontsize=12, fontweight='bold')
    ax5.legend(loc='lower right', fontsize=9)
    ax5.grid(True, alpha=0.3, axis='y')
    
    # Summary Text (bottom right)
    ax6 = fig.add_subplot(2, 3, 6)
    ax6.axis('off')
    
    summary_text = f"""
    MODEL SUMMARY
    ─────────────────────────
    Algorithm: Logistic Regression
    Technique: SMOTE Oversampling
    
    RESULTS
    ─────────────────────────
    Accuracy:     {metrics_dict.get('Accuracy', 0):.1%}
    F1-Score:     {metrics_dict.get('F1-Score', 0):.1%}
    Precision:    {metrics_dict.get('Precision', 0):.1%}
    Recall:       {metrics_dict.get('Recall', 0):.1%}
    ROC-AUC:      {roc_auc:.1%}
    
    Cross-Val F1: {np.mean(cv_scores):.1%} (±{np.std(cv_scores)*2:.1%})
    
    CONFUSION MATRIX
    ─────────────────────────
    True Positives:  {cm[1,1]}
    True Negatives:  {cm[0,0]}
    False Positives: {cm[0,1]}
    False Negatives: {cm[1,0]}
    """
    
    ax6.text(0.1, 0.9, summary_text, transform=ax6.transAxes, fontsize=11,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    fig.suptitle('InvestTalent-AI: ML Skill Classifier Performance Report', 
                 fontsize=18, fontweight='bold', y=0.98)
    
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"✓ Saved: {save_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate ML Visualization Charts")
    parser.add_argument("--input", default="labeled_chunks_dataset.csv", help="Input CSV file")
    parser.add_argument("--output_dir", default="charts", help="Output directory for charts")
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    print("=" * 70)
    print(" ML CLASSIFIER VISUALIZATION - THESIS CHARTS")
    print("=" * 70 + "\n")
    
    # Load data
    X, y, feature_names, df = load_and_prepare_data(args.input)
    
    # Split data
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    for train_idx, test_idx in sss.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
    
    # Apply SMOTE
    y_train_original = y_train.copy()
    if SMOTE_AVAILABLE:
        print("Applying SMOTE...")
        smote = SMOTE(sampling_strategy=0.5, random_state=42, 
                      k_neighbors=min(5, sum(y_train == 1) - 1))
        X_train_smote, y_train_smote = smote.fit_resample(X_train, y_train)
        print(f"  Before: {sum(y_train == 1)} skills, {sum(y_train == 0)} non-skills")
        print(f"  After:  {sum(y_train_smote == 1)} skills, {sum(y_train_smote == 0)} non-skills\n")
    else:
        X_train_smote, y_train_smote = X_train, y_train
    
    # Train model
    print("Training Logistic Regression...")
    classifier = LogisticRegression(max_iter=2000, C=0.8, class_weight="balanced", random_state=42)
    classifier.fit(X_train_smote, y_train_smote)
    print("✓ Training complete\n")
    
    # Get predictions
    y_proba = classifier.predict_proba(X_test)[:, 1]
    optimal_threshold = 0.65
    y_pred = (y_proba >= optimal_threshold).astype(int)
    
    # Calculate metrics
    accuracy = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_proba)
    
    metrics_dict = {
        'Accuracy': accuracy,
        'F1-Score': f1,
        'Precision': precision,
        'Recall': recall,
        'ROC-AUC': roc_auc
    }
    
    # Cross-validation
    print("Running cross-validation...")
    cv_scores = cross_val_score(classifier, X, y, cv=5, scoring='f1')
    print(f"CV F1 scores: {cv_scores}")
    print(f"Mean: {cv_scores.mean():.1%}\n")
    
    # Generate individual charts
    print("Generating charts...\n")
    
    cm = plot_confusion_matrix(y_test, y_pred, output_dir / 'confusion_matrix.png')
    plot_roc_curve(y_test, y_proba, output_dir / 'roc_curve.png')
    plot_precision_recall_curve(y_test, y_proba, output_dir / 'precision_recall_curve.png')
    plot_feature_importance(classifier, feature_names, output_dir / 'feature_importance.png')
    
    if SMOTE_AVAILABLE:
        plot_class_distribution(y_train_original, y_train_smote, output_dir / 'class_distribution.png')
    
    plot_metrics_comparison(metrics_dict, output_dir / 'metrics_comparison.png')
    plot_cv_scores(cv_scores, output_dir / 'cv_scores.png')
    
    # Generate all-in-one summary
    plot_all_in_one(cm, y_test, y_proba, metrics_dict, cv_scores, output_dir / 'model_summary.png')
    
    print("\n" + "=" * 70)
    print(" VISUALIZATION COMPLETE!")
    print("=" * 70)
    print(f"\nAll charts saved to: {output_dir.absolute()}")
    print("\nFiles generated:")
    for f in output_dir.glob('*.png'):
        print(f"  📊 {f.name}")


if __name__ == "__main__":
    main()