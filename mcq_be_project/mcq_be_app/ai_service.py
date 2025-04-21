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

            return questions

        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {str(e)}")
            print(f"Raw Content: {content}")
            raise ValueError(f"Failed to parse AI response into valid JSON: {str(e)}")
        except Exception as e:
            print(f"Unexpected Error: {str(e)}")
            raise ValueError(f"Error processing AI response: {str(e)}")
