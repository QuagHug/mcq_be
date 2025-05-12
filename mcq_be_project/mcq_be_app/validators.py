import re
import spacy
from typing import List, Dict, Any

# Load spaCy model for grammatical analysis
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Fallback if model isn't installed
    import en_core_web_sm
    nlp = en_core_web_sm.load()

def check_missing_fields(mcq: Dict[str, Any]) -> List[str]:
    """Check if any required fields are missing."""
    errors = []
    required_fields = ["question", "options", "correct"]
    
    for field in required_fields:
        if field not in mcq or not mcq[field]:
            errors.append(f"Missing required field: {field}")
    
    return errors

def validate_options(mcq: Dict[str, Any]) -> List[str]:
    """Validate the options structure and content."""
    errors = []
    options = mcq.get("options", {})
    
    # Check if options exist
    if not options or not isinstance(options, dict):
        errors.append("Options must be a non-empty dictionary")
        return errors
    
    # Check if there are at least 3 options
    if len(options) < 3:
        errors.append(f"Too few options: {len(options)}. At least 3 required.")
    
    # Check if correct answer is among the options
    correct = mcq.get("correct")
    if correct and correct not in options:
        errors.append(f"Correct answer '{correct}' not found in options")
    
    # Check for duplicate options
    option_values = [str(v).lower().strip() for v in options.values()]
    if len(option_values) != len(set(option_values)):
        errors.append("Duplicate option values detected")
    
    return errors

def check_grammatical_consistency(mcq: Dict[str, Any]) -> List[str]:
    """Check if options are grammatically consistent."""
    errors = []
    options = mcq.get("options", {})
    
    if not options:
        return errors
    
    # Extract option texts
    option_texts = list(options.values())
    
    # Analyze grammatical structure
    option_docs = [nlp(text) for text in option_texts]
    
    # Check if all options start with the same part of speech
    start_pos = [doc[0].pos_ for doc in option_docs if len(doc) > 0]
    if len(set(start_pos)) > 1:
        errors.append("Options are not grammatically consistent (different starting parts of speech)")
    
    # Check if all options are similar in structure (e.g., all noun phrases or all verb phrases)
    structures = []
    for doc in option_docs:
        if len(doc) == 0:
            continue
        # Simplified structure check - first 2 POS tags
        structure = " ".join([token.pos_ for token in doc[:2]])
        structures.append(structure)
    
    if len(set(structures)) > 1:
        errors.append("Options have inconsistent grammatical structures")
    
    return errors

def check_common_flaws(mcq: Dict[str, Any]) -> List[str]:
    """Check for common MCQ flaws."""
    errors = []
    question = mcq.get("question", "").lower()
    options = {k: v.lower() for k, v in mcq.get("options", {}).items()}
    
    # Check for negative phrasing
    negative_patterns = [
        r"\bnot\b", r"\bexcept\b", r"\bunless\b", r"\bwithout\b",
        r"which of the following is not", r"which is not", r"which are not"
    ]
    
    for pattern in negative_patterns:
        if re.search(pattern, question):
            errors.append("Question contains negative phrasing")
            break
    
    # Check for problematic option types
    problematic_options = ["all of the above", "none of the above", "both a and b"]
    for option_text in options.values():
        for problematic in problematic_options:
            if problematic in option_text:
                errors.append(f"Option contains problematic phrase: '{problematic}'")
                break
    
    # Check for option length consistency
    option_lengths = [len(text.split()) for text in options.values()]
    avg_length = sum(option_lengths) / len(option_lengths) if option_lengths else 0
    
    if any(abs(length - avg_length) > 5 for length in option_lengths):
        errors.append("Options have significantly different lengths")
    
    return errors

def check_option_similarity(mcq: Dict[str, Any]) -> List[str]:
    """Check if options are too similar to each other."""
    errors = []
    options = list(mcq.get("options", {}).values())
    
    if len(options) < 2:
        return errors
    
    # Check for options that differ by only 1-2 words
    for i in range(len(options)):
        for j in range(i+1, len(options)):
            words1 = set(options[i].lower().split())
            words2 = set(options[j].lower().split())
            
            # Calculate Jaccard similarity
            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))
            
            if union > 0 and intersection / union > 0.8:
                errors.append(f"Options are too similar: '{options[i]}' and '{options[j]}'")
    
    return errors

def validate_mcq(mcq: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an MCQ and return validation results."""
    all_errors = []
    
    # Run all validation checks
    all_errors.extend(check_missing_fields(mcq))
    all_errors.extend(validate_options(mcq))
    all_errors.extend(check_grammatical_consistency(mcq))
    all_errors.extend(check_common_flaws(mcq))
    all_errors.extend(check_option_similarity(mcq))
    
    # Calculate quality score based on number of errors
    quality_score = 10
    if all_errors:
        # Deduct points for each error, with a minimum score of 1
        quality_score = max(1, 10 - len(all_errors))
    
    return {
        "is_valid": len(all_errors) == 0,
        "errors": all_errors,
        "quality_score": quality_score
    }

def validate_mcq_batch(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate a batch of MCQs and return validation results for each."""
    results = []
    
    for question in questions:
        validation_result = validate_mcq(question)
        results.append({
            "question": question.get("question", ""),
            "validation": validation_result
        })
    
    return results 