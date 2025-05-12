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
