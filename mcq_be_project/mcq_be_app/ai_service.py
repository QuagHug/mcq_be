from openai import OpenAI
from django.conf import settings
from typing import List, Dict
import json


class AIService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate_questions(
        self,
        context: str,
        num_questions: int = 1,
        taxonomy_level: str = "Remember",
        difficulty: str = "medium",
    ) -> List[Dict]:
        prompt = f"""
        Based on the following context, generate multiple choice questions:
        
        Context: {context}
        
        Format each question as a JSON array with the following structure:
        [
            {{
                "question_text": "The question",
                "difficulty": "{difficulty}",
                "answers": [
                    {{"answer_text": "Correct answer", "is_correct": true, "explanation": "Why this is correct"}},
                    {{"answer_text": "Wrong answer 1", "is_correct": false, "explanation": "Why this is wrong"}},
                    {{"answer_text": "Wrong answer 2", "is_correct": false, "explanation": "Why this is wrong"}},
                    {{"answer_text": "Wrong answer 3", "is_correct": false, "explanation": "Why this is wrong"}}
                ],
                "taxonomies": [
                    {{
                        "taxonomy_id": 1,
                        "level": "{taxonomy_level}",
                        "difficulty": "{difficulty}"
                    }}
                ]
            }}
        ]
        
        Please ensure:
        1. Each question has exactly one correct answer
        2. All explanations are clear and educational
        3. Difficulty should be one of: easy, medium, hard
        """

        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert teacher creating multiple choice questions. Always return response in a JSON array format.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )

        try:
            # Log the raw response for debugging
            print("AI Response:", response.choices[0].message.content)

            # Clean the response content
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]  # Remove ```json
            if content.endswith("```"):
                content = content[:-3]  # Remove ```
            content = content.strip()

            # Parse the cleaned JSON
            questions = json.loads(content)

            # Ensure we always return a list
            if isinstance(questions, dict):
                questions = [questions]

            # Validate the structure and quality of questions
            validated_questions = self._validate_questions(questions)

            return validated_questions

        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {str(e)}")
            print(f"Raw Content: {content}")
            raise ValueError(f"Failed to parse AI response into valid JSON: {str(e)}")
        except Exception as e:
            print(f"Unexpected Error: {str(e)}")
            raise ValueError(f"Error processing AI response: {str(e)}")

    def _validate_questions(self, questions: List[Dict]) -> List[Dict]:
        """
        Validate the structure and quality of AI-generated questions.
        
        Args:
            questions: List of question dictionaries from the AI
            
        Returns:
            List of questions with validation metadata added
        """
        validated_questions = []
        
        for question in questions:
            # Initialize metadata
            if "metadata" not in question:
                question["metadata"] = {}
            
            # Check structure validity
            structure_valid = self._validate_question_structure(question)
            question["metadata"]["structure_valid"] = structure_valid
            
            if not structure_valid:
                print(f"Structure issues in question: {question.get('question_text', '')}")
                question["metadata"]["structure_issues"] = self._get_structure_issues(question)
            
            # Check quality criteria (even for structurally invalid questions)
            quality_issues = self._check_question_quality(question)
            if quality_issues:
                print(f"Quality issues in question: {question.get('question_text', '')}")
                print(f"Issues: {', '.join(quality_issues)}")
                question["metadata"]["quality_issues"] = quality_issues
            
            validated_questions.append(question)
        
        return validated_questions

    def _get_structure_issues(self, question: Dict) -> List[str]:
        """
        Identify specific structure issues with a question.
        
        Returns:
            List of structure issues found
        """
        issues = []
        
        # Check for required top-level fields
        required_fields = ["question_text", "difficulty", "answers", "taxonomies"]
        for field in required_fields:
            if field not in question:
                issues.append(f"Missing required field: {field}")
        
        # Validate difficulty value if present
        if "difficulty" in question and question["difficulty"] not in ["easy", "medium", "hard"]:
            issues.append(f"Invalid difficulty value: {question['difficulty']}")
        
        # Validate answers structure if present
        if "answers" in question:
            answers = question["answers"]
            if not isinstance(answers, list):
                issues.append("Answers must be a list")
            elif len(answers) < 2:
                issues.append(f"Too few answers: {len(answers)}. At least 2 required.")
            else:
                # Check that exactly one answer is marked correct
                correct_count = sum(1 for answer in answers if answer.get("is_correct") is True)
                if correct_count != 1:
                    issues.append(f"Question must have exactly one correct answer, found {correct_count}")
                
                # Validate each answer has required fields
                for i, answer in enumerate(answers):
                    missing_fields = []
                    for key in ["answer_text", "is_correct", "explanation"]:
                        if key not in answer:
                            missing_fields.append(key)
                    if missing_fields:
                        issues.append(f"Answer {i+1} missing fields: {', '.join(missing_fields)}")
        
        # Validate taxonomies if present
        if "taxonomies" in question:
            taxonomies = question["taxonomies"]
            if not isinstance(taxonomies, list):
                issues.append("Taxonomies must be a list")
            elif not taxonomies:
                issues.append("Taxonomies list is empty")
            else:
                for i, taxonomy in enumerate(taxonomies):
                    missing_fields = []
                    for key in ["taxonomy_id", "level", "difficulty"]:
                        if key not in taxonomy:
                            missing_fields.append(key)
                    if missing_fields:
                        issues.append(f"Taxonomy {i+1} missing fields: {', '.join(missing_fields)}")
        
        return issues

    def _validate_question_structure(self, question: Dict) -> bool:
        """
        Validate that a question has the expected structure.
        
        Returns:
            bool: True if structure is valid, False otherwise
        """
        # Check for required top-level fields
        required_fields = ["question_text", "difficulty", "answers", "taxonomies"]
        for field in required_fields:
            if field not in question:
                return False
        
        # Validate difficulty value
        if question["difficulty"] not in ["easy", "medium", "hard"]:
            return False
        
        # Validate answers structure
        answers = question.get("answers", [])
        if not isinstance(answers, list) or len(answers) < 2:
            return False
        
        # Check that exactly one answer is marked correct
        correct_count = sum(1 for answer in answers if answer.get("is_correct") is True)
        if correct_count != 1:
            return False
        
        # Validate each answer has required fields
        for answer in answers:
            if not all(key in answer for key in ["answer_text", "is_correct", "explanation"]):
                return False
        
        # Validate taxonomies
        taxonomies = question.get("taxonomies", [])
        if not isinstance(taxonomies, list) or not taxonomies:
            return False
        
        for taxonomy in taxonomies:
            if not all(key in taxonomy for key in ["taxonomy_id", "level", "difficulty"]):
                return False
        
        return True

    def _check_question_quality(self, question: Dict) -> List[str]:
        """
        Check the quality of a question based on various criteria.
        
        Returns:
            List of quality issues found (empty if no issues)
        """
        issues = []
        
        # Check question text length
        question_text = question.get("question_text", "")
        if len(question_text) < 10:
            issues.append("Question text is too short")
        
        # Check for question marks in question text
        if not question_text.endswith("?") and "?" not in question_text:
            issues.append("Question text should include a question mark")
        
        # Check answers
        answers = question.get("answers", [])
        
        # Check for duplicate answers
        answer_texts = [a.get("answer_text", "").strip().lower() for a in answers]
        if len(answer_texts) != len(set(answer_texts)):
            issues.append("Contains duplicate answers")
        
        # Check answer length consistency
        answer_lengths = [len(a.get("answer_text", "")) for a in answers]
        avg_length = sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0
        if any(abs(length - avg_length) > avg_length * 0.7 for length in answer_lengths):
            issues.append("Answer lengths are inconsistent")
        
        # Check explanation quality
        for answer in answers:
            explanation = answer.get("explanation", "")
            if len(explanation) < 5:
                issues.append("One or more explanations are too short")
                break
        
        return issues

    def generate_distractors(
        self,
        question_text: str,
        correct_answer: str,
        difficulty_distribution: Dict[str, int] = None,
        num_distractors: int = 3,
        difficulty: str = "medium",
    ) -> List[Dict]:
        """
        Generate plausible distractors for a given question and correct answer.
        
        Args:
            question_text: The question text
            correct_answer: The correct answer
            difficulty_distribution: Dictionary mapping difficulty levels to number of distractors
                                    (e.g., {"easy": 2, "medium": 2, "hard": 1})
            num_distractors: Total number of distractors if difficulty_distribution not provided
            difficulty: Default difficulty level if difficulty_distribution not provided
            
        Returns:
            List of distractor dictionaries with answer_text, explanation, and difficulty
        """
        # If difficulty distribution is provided, use it instead of num_distractors and difficulty
        if difficulty_distribution:
            all_distractors = []
            
            # Generate distractors for each difficulty level
            for diff_level, count in difficulty_distribution.items():
                if count <= 0:
                    continue
                    
                prompt = self._create_distractor_prompt(
                    question_text, correct_answer, count, diff_level
                )
                
                distractors = self._generate_distractors_with_prompt(prompt, max_distractors=count)
                
                # Add difficulty level to each distractor
                for distractor in distractors:
                    distractor["difficulty"] = diff_level
                    
                all_distractors.extend(distractors)
                
            return all_distractors
        else:
            # Use the original implementation for backward compatibility
            prompt = self._create_distractor_prompt(
                question_text, correct_answer, num_distractors, difficulty
            )
            
            distractors = self._generate_distractors_with_prompt(prompt, max_distractors=num_distractors)
            
            # Add difficulty level to each distractor
            for distractor in distractors:
                distractor["difficulty"] = difficulty
                
            return distractors

    def _create_distractor_prompt(
        self, question_text: str, correct_answer: str, num_distractors: int, difficulty: str
    ) -> str:
        """Create a prompt for generating distractors with specific difficulty."""
        # Create example JSON with exactly the requested number of distractors
        example_json = "[\n"
        for i in range(num_distractors):
            example_json += f'    {{"answer_text": "Distractor {i+1}", "explanation": "Why this is wrong"}}'
            if i < num_distractors - 1:
                example_json += ","
            example_json += "\n"
        example_json += "]"
        
        return f"""
        Based on the following question and correct answer, generate EXACTLY {num_distractors} plausible but incorrect answer options (distractors):
        
        Question: {question_text}
        Correct Answer: {correct_answer}
        Difficulty: {difficulty}
        
        Format the distractors as a JSON array with the following structure:
        {example_json}
        
        Please ensure:
        1. Generate EXACTLY {num_distractors} distractor(s), no more and no less
        2. Each distractor is clearly incorrect but plausible
        3. Distractors are distinct from each other and from the correct answer
        4. Explanations clearly state why the distractor is incorrect
        5. Distractors match the grammatical structure of the correct answer
        6. Difficulty level ({difficulty}) is reflected in how plausible/tricky the distractors are:
           - Easy: Obviously wrong to most students but still relevant to the topic
           - Medium: Plausible but clearly incorrect with careful thought
           - Hard: Very plausible and requires deep understanding to recognize as incorrect
        """

    def _generate_distractors_with_prompt(self, prompt: str, max_distractors: int = None) -> List[Dict]:
        """Generate distractors using the given prompt."""
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert teacher creating plausible distractors for multiple choice questions. Always return response in a JSON array format.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )

        try:
            # Clean the response content
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]  # Remove ```json
            if content.endswith("```"):
                content = content[:-3]  # Remove ```
            content = content.strip()

            # Parse the cleaned JSON
            distractors = json.loads(content)

            # Ensure we always return a list
            if isinstance(distractors, dict):
                distractors = [distractors]

            # Limit the number of distractors if specified
            if max_distractors is not None and len(distractors) > max_distractors:
                distractors = distractors[:max_distractors]

            # Validate the structure of distractors
            validated_distractors = self._validate_distractors(distractors)

            return validated_distractors

        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {str(e)}")
            print(f"Raw Content: {content}")
            raise ValueError(f"Failed to parse AI response into valid JSON: {str(e)}")
        except Exception as e:
            print(f"Unexpected Error: {str(e)}")
            raise ValueError(f"Error processing AI response: {str(e)}")

    def _validate_distractors(self, distractors: List[Dict]) -> List[Dict]:
        """
        Validate the structure and quality of AI-generated distractors.
        
        Args:
            distractors: List of distractor dictionaries from the AI
            
        Returns:
            List of validated distractors
        """
        validated_distractors = []
        
        for distractor in distractors:
            # Initialize metadata
            if "metadata" not in distractor:
                distractor["metadata"] = {}
            
            # Check structure validity
            structure_valid = self._validate_distractor_structure(distractor)
            distractor["metadata"]["structure_valid"] = structure_valid
            
            if not structure_valid:
                print(f"Structure issues in distractor: {distractor.get('answer_text', '')}")
                distractor["metadata"]["structure_issues"] = self._get_distractor_structure_issues(distractor)
            
            # Check quality criteria (even for structurally invalid distractors)
            quality_issues = self._check_distractor_quality(distractor)
            if quality_issues:
                print(f"Quality issues in distractor: {distractor.get('answer_text', '')}")
                print(f"Issues: {', '.join(quality_issues)}")
                distractor["metadata"]["quality_issues"] = quality_issues
            
            # Add is_correct flag (always false for distractors)
            distractor["is_correct"] = False
            
            validated_distractors.append(distractor)
        
        return validated_distractors

    def _validate_distractor_structure(self, distractor: Dict) -> bool:
        """
        Validate that a distractor has the expected structure.
        
        Returns:
            bool: True if structure is valid, False otherwise
        """
        # Check for required fields
        required_fields = ["answer_text", "explanation"]
        for field in required_fields:
            if field not in distractor:
                return False
        
        # Check that answer_text is not empty
        if not distractor.get("answer_text", "").strip():
            return False
        
        # Check that explanation is not empty
        if not distractor.get("explanation", "").strip():
            return False
        
        return True

    def _get_distractor_structure_issues(self, distractor: Dict) -> List[str]:
        """
        Identify specific structure issues with a distractor.
        
        Returns:
            List of structure issues found
        """
        issues = []
        
        # Check for required fields
        required_fields = ["answer_text", "explanation"]
        for field in required_fields:
            if field not in distractor:
                issues.append(f"Missing required field: {field}")
        
        # Check that answer_text is not empty
        if "answer_text" in distractor and not distractor["answer_text"].strip():
            issues.append("Answer text is empty")
        
        # Check that explanation is not empty
        if "explanation" in distractor and not distractor["explanation"].strip():
            issues.append("Explanation is empty")
        
        return issues

    def _check_distractor_quality(self, distractor: Dict) -> List[str]:
        """
        Check the quality of a distractor based on various criteria.
        
        Returns:
            List of quality issues found (empty if no issues)
        """
        issues = []
        
        # Check answer text length
        answer_text = distractor.get("answer_text", "")
        if len(answer_text) < 2:
            issues.append("Answer text is too short")
        
        # Check explanation quality
        explanation = distractor.get("explanation", "")
        if len(explanation) < 10:
            issues.append("Explanation is too short")
        
        # Check for generic explanations
        generic_phrases = ["this is incorrect", "this is wrong", "not the right answer"]
        if any(phrase in explanation.lower() for phrase in generic_phrases) and len(explanation) < 30:
            issues.append("Explanation is too generic")
        
        return issues
