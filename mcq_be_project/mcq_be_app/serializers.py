from rest_framework import serializers
from .models import QuestionBank, Question, Answer, Course, Taxonomy, QuestionTaxonomy
from django.utils.timezone import localtime


class CourseSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField()

    def get_owner(self, obj):
        return obj.owner.username if obj.owner else None

    class Meta:
        model = Course
        fields = [
            "id",
            "name",
            "description",
            "image_url",
            "course_id",
            "owner",
            "created_at",
            "updated_at",
        ]


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ["id", "answer_text", "is_correct", "explanation"]


class TaxonomySerializer(serializers.ModelSerializer):
    class Meta:
        model = Taxonomy
        fields = ["id", "name", "description", "category", "levels"]


class QuestionTaxonomySerializer(serializers.ModelSerializer):
    taxonomy = TaxonomySerializer(read_only=True)

    class Meta:
        model = QuestionTaxonomy
        fields = ["id", "taxonomy", "level", "difficulty"]


class QuestionSerializer(serializers.ModelSerializer):
    answers = AnswerSerializer(many=True, required=False)
    taxonomies = QuestionTaxonomySerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = [
            "id",
            "question_text",
            "image_url",
            "answers",
            "taxonomies",
            "updated_at",
        ]


class QuestionBankSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    question_count = serializers.SerializerMethodField()
    last_modified = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        return obj.questions.count()

    def get_last_modified(self, obj):
        # Get the latest update time from either the bank itself or its questions
        latest_question = obj.questions.order_by("-updated_at").first()
        bank_updated = localtime(obj.updated_at) if hasattr(obj, "updated_at") else None
        question_updated = (
            localtime(latest_question.updated_at) if latest_question else None
        )

        if bank_updated and question_updated:
            return max(bank_updated, question_updated)
        return bank_updated or question_updated or None

    class Meta:
        model = QuestionBank
        fields = [
            "id",
            "name",
            "description",
            "bank_id",
            "is_child",
            "created_by",
            "questions",
            "question_count",
            "last_modified",
        ]
        read_only_fields = ["created_by"]
