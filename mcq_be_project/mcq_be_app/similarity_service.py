from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from typing import List, Dict, Tuple, Optional
from .models import Question
import logging

logger = logging.getLogger(__name__)

class SimilarityService:
    """Service for finding similar questions using vector embeddings and FAISS."""
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize the similarity service with a sentence transformer model.
        
        Args:
            model_name: Name of the sentence-transformers model to use
        """
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.question_ids = []
        self.dimension = self.model.get_sentence_embedding_dimension()
        
        # Initialize an empty FAISS index
        self.reset_index()
    
    def reset_index(self):
        """Reset the FAISS index."""
        self.index = faiss.IndexFlatL2(self.dimension)
        self.question_ids = []
    
    def add_questions(self, questions: List[Dict]):
        """
        Add questions to the index.
        
        Args:
            questions: List of question dictionaries with 'id' and 'question_text' fields
        """
        if not questions:
            return
            
        texts = [q.get('question_text', '') for q in questions]
        ids = [q.get('id') for q in questions]
        
        # Generate embeddings
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        
        # Add to FAISS index
        self.index.add(np.array(embeddings).astype('float32'))
        self.question_ids.extend(ids)
        
        logger.info(f"Added {len(questions)} questions to similarity index")
    
    def build_index_from_db(self, question_bank_id: Optional[int] = None):
        """
        Build the index from questions in the database.
        
        Args:
            question_bank_id: Optional ID to filter questions by question bank
        """
        # Reset the index
        self.reset_index()
        
        # Query questions from database
        queryset = Question.objects.all()
        if question_bank_id:
            queryset = queryset.filter(question_bank_id=question_bank_id)
            
        questions = list(queryset.values('id', 'question_text'))
        self.add_questions(questions)
        
        logger.info(f"Built similarity index with {len(questions)} questions")
        return len(questions)
    
    def find_similar_questions(
        self, 
        query_text: str, 
        threshold: float = 0.75, 
        top_k: int = 5
    ) -> List[Dict]:
        """
        Find questions similar to the query text.
        
        Args:
            query_text: The question text to find similarities for
            threshold: Similarity threshold (lower distance = more similar)
            top_k: Maximum number of similar questions to return
            
        Returns:
            List of similar questions with similarity scores
        """
        if not self.index or self.index.ntotal == 0:
            logger.warning("Similarity index is empty")
            return []
            
        # Generate embedding for query
        query_embedding = self.model.encode([query_text], convert_to_numpy=True)
        
        # Search the index
        distances, indices = self.index.search(
            np.array(query_embedding).astype('float32'), 
            min(top_k, self.index.ntotal)
        )
        
        # Format results
        results = []
        for i, (idx, distance) in enumerate(zip(indices[0], distances[0])):
            # Convert distance to similarity score (1 = identical, 0 = completely different)
            similarity = 1 - min(distance / 10, 1.0)  # Normalize and invert
            
            if similarity >= threshold:
                question_id = self.question_ids[idx]
                results.append({
                    'question_id': question_id,
                    'similarity': round(float(similarity), 4)
                })
                
        return results
    
    def find_similar_pairs(
        self, 
        question_bank_id: Optional[int] = None,
        threshold: float = 0.85,
        max_pairs: int = 100
    ) -> List[Dict]:
        """
        Find all pairs of similar questions within a question bank.
        
        Args:
            question_bank_id: Optional ID to filter questions by question bank
            threshold: Similarity threshold
            max_pairs: Maximum number of pairs to return
            
        Returns:
            List of similar question pairs with similarity scores
        """
        # Build or update the index
        self.build_index_from_db(question_bank_id)
        
        if self.index.ntotal < 2:
            return []
            
        # Get all questions
        queryset = Question.objects.all()
        if question_bank_id:
            queryset = queryset.filter(question_bank_id=question_bank_id)
            
        questions = list(queryset.values('id', 'question_text'))
        
        # Find similar pairs
        similar_pairs = []
        for i, question in enumerate(questions):
            if len(similar_pairs) >= max_pairs:
                break
                
            similar = self.find_similar_questions(
                question['question_text'],
                threshold=threshold,
                top_k=10
            )
            
            # Filter out self-matches and format pairs
            for match in similar:
                if match['question_id'] != question['id']:
                    similar_pairs.append({
                        'question1_id': question['id'],
                        'question1_text': question['question_text'],
                        'question2_id': match['question_id'],
                        'question2_text': next(
                            (q['question_text'] for q in questions if q['id'] == match['question_id']), 
                            ''
                        ),
                        'similarity': match['similarity']
                    })
                    
                    if len(similar_pairs) >= max_pairs:
                        break
        
        # Sort by similarity (highest first)
        similar_pairs.sort(key=lambda x: x['similarity'], reverse=True)
        return similar_pairs

    def compare_tests(
        self,
        test1_questions: List[Dict],
        test2_questions: List[Dict],
        similarity_threshold: float = 0.75
    ) -> Dict:
        """
        Calculate the similarity between two tests based on their questions.
        
        Args:
            test1_questions: List of question dictionaries from first test
            test2_questions: List of question dictionaries from second test
            similarity_threshold: Threshold to consider questions as similar (0.0-1.0)
            
        Returns:
            Dict containing:
                - overall_similarity: Float representing overall test similarity (0.0-1.0)
                - similar_question_pairs: List of pairs of similar questions
                - similarity_metrics: Additional similarity metrics
        """
        # Initialize results
        similar_question_pairs = []
        similarity_scores = []
        
        # Validate inputs
        if not test1_questions or not test2_questions:
            logger.warning("One or both test question lists are empty")
            return {
                'overall_similarity': 0.0,
                'similar_question_pairs': [],
                'similarity_metrics': {
                    'max_similarity': 0.0,
                    'similar_question_count': 0,
                    'question_coverage': 0.0,
                    'average_similarity': 0.0
                }
            }
        
        # Generate embeddings for all questions in both tests
        test1_texts = [q.get('question_text', '') for q in test1_questions if q.get('question_text')]
        test2_texts = [q.get('question_text', '') for q in test2_questions if q.get('question_text')]
        
        if not test1_texts or not test2_texts:
            logger.warning("No valid question texts found in one or both tests")
            return {
                'overall_similarity': 0.0,
                'similar_question_pairs': [],
                'similarity_metrics': {
                    'max_similarity': 0.0,
                    'similar_question_count': 0,
                    'question_coverage': 0.0,
                    'average_similarity': 0.0
                }
            }
        
        test1_embeddings = self.model.encode(test1_texts, convert_to_numpy=True)
        test2_embeddings = self.model.encode(test2_texts, convert_to_numpy=True)
        
        # Calculate similarity between each pair of questions
        for i, (embed1, text1) in enumerate(zip(test1_embeddings, test1_texts)):
            for j, (embed2, text2) in enumerate(zip(test2_embeddings, test2_texts)):
                # Calculate cosine similarity
                norm1 = np.linalg.norm(embed1)
                norm2 = np.linalg.norm(embed2)
                
                if norm1 > 0 and norm2 > 0:  # Avoid division by zero
                    similarity = float(np.dot(embed1, embed2) / (norm1 * norm2))
                    similarity_scores.append(similarity)
                    
                    # If similarity exceeds threshold, record the pair
                    if similarity >= similarity_threshold:
                        similar_question_pairs.append({
                            'test1_question_index': i,
                            'test1_question_text': text1,
                            'test1_question_id': test1_questions[i].get('id'),
                            'test2_question_index': j,
                            'test2_question_text': text2,
                            'test2_question_id': test2_questions[j].get('id'),
                            'similarity_score': round(similarity, 4)
                        })
        
        # Calculate overall similarity metrics
        if similarity_scores:
            overall_similarity = sum(similarity_scores) / len(similarity_scores)
            max_similarity = max(similarity_scores) if similarity_scores else 0
            similar_question_count = len(similar_question_pairs)
            total_possible_pairs = len(test1_texts) * len(test2_texts)
            similar_pair_ratio = similar_question_count / total_possible_pairs if total_possible_pairs > 0 else 0
            question_coverage = similar_question_count / min(len(test1_texts), len(test2_texts))
        else:
            overall_similarity = 0
            max_similarity = 0
            similar_question_count = 0
            similar_pair_ratio = 0
            question_coverage = 0
        
        # Sort similar pairs by similarity score (highest first)
        similar_question_pairs.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Return results
        return {
            'overall_similarity': round(float(overall_similarity), 4),
            'similar_question_pairs': similar_question_pairs,
            'similarity_metrics': {
                'max_similarity': round(float(max_similarity), 4),
                'similar_question_count': similar_question_count,
                'similar_pair_ratio': round(float(similar_pair_ratio), 4),
                'question_coverage': round(float(question_coverage), 4),
                'total_questions_test1': len(test1_texts),
                'total_questions_test2': len(test2_texts)
            }
        }
