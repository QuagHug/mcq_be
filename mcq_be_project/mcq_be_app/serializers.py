from rest_framework import serializers
from .models import QuestionBank, Question, Answer, Course

class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'name', 'description', 'created_at', 'updated_at']

class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ['id', 'answer_text', 'is_correct', 'explanation']

class QuestionSerializer(serializers.ModelSerializer):
    answers = AnswerSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ['id', 'question_text', 'image_url', 'answers']

class QuestionBankSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = QuestionBank
        fields = ['id', 'name', 'description', 'bank_id', 'is_child', 'created_by', 'questions']
        read_only_fields = ['created_by'] 

class CourseSerializer(serializers.ModelSerializer):
    question_banks = QuestionBankSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = ['id', 'name', 'description', 'image_url', 'created_by', 'question_banks', 'created_at', 'updated_at']
        read_only_fields = ['created_by'] 