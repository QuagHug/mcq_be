from rest_framework import serializers
from .models import QuestionBank, Question, Answer, Course, Taxonomy, QuestionTaxonomy, TestQuestion, Test, TestDraft
from django.utils.timezone import localtime


class CourseSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField()

    def get_owner(self, obj):
        return obj.owner.first_name + " " + obj.owner.last_name if obj.owner else None

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
        fields = ["id", "taxonomy", "level"]


class QuestionSerializer(serializers.ModelSerializer):
    answers = AnswerSerializer(many=True, read_only=True)
    taxonomies = QuestionTaxonomySerializer(source='question_taxonomies', many=True, read_only=True)
    statistics = serializers.SerializerMethodField()
    question_bank_id = serializers.IntegerField(source='question_bank.id', read_only=True)

    class Meta:
        model = Question
        fields = [
            "id",
            "question_text",
            "answers",
            "taxonomies",
            "question_bank_id",
            "created_at",
            "updated_at",
            "statistics"
        ]

    def update(self, instance, validated_data):
        answers_data = validated_data.pop('answers', [])
        taxonomies_data = validated_data.pop('taxonomies', [])

        # Update question fields
        instance.question_text = validated_data.get('question_text', instance.question_text)
        instance.save()

        # Update answers
        if answers_data:
            # Delete existing answers
            instance.answers.all().delete()
            # Create new answers
            for answer_data in answers_data:
                Answer.objects.create(question=instance, **answer_data)

        # Update taxonomies
        if taxonomies_data:
            # Delete existing taxonomies
            instance.questiontaxonomy_set.all().delete()
            # Create new taxonomies
            for taxonomy_data in taxonomies_data:
                taxonomy_id = taxonomy_data.pop('taxonomy_id', None)
                if taxonomy_id:
                    taxonomy = Taxonomy.objects.get(id=taxonomy_id)
                    QuestionTaxonomy.objects.create(
                        question=instance,
                        taxonomy=taxonomy,
                        **taxonomy_data
                    )

        return instance

    def get_statistics(self, obj):
        if not obj.statistics:
            return None

        stats = obj.statistics.copy()
        
        if 'irt_parameters' in stats:
            irt = stats['irt_parameters']
            difficulty = float(irt.get('difficulty', 0))
            discrimination = float(irt.get('discrimination', 0))
            
            # Scale difficulty from [-6, 3] to [0, 10]
            difficulty_score = 10 - ((difficulty + 6) * (10 / 9))
            difficulty_score = max(0, min(10, difficulty_score))
            
            # Scale discrimination from [0.2, 0.5] to [0, 10]
            discrimination_score = (discrimination - 0.2) * (10 / 0.3)
            discrimination_score = max(0, min(10, discrimination_score))
            
            # Add scaled scores to the statistics
            stats['scaled_difficulty'] = round(difficulty_score, 2)
            stats['scaled_discrimination'] = round(discrimination_score, 2)
        
        return stats


class QuestionBankSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    question_count = serializers.SerializerMethodField()
    last_modified = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    parent_id = serializers.PrimaryKeyRelatedField(
        source='parent',
        queryset=QuestionBank.objects.all(),
        required=False,
        allow_null=True
    )

    def get_children(self, obj):
        children = obj.children.all()
        return QuestionBankSerializer(children, many=True).data

    def get_question_count(self, obj):
        return obj.questions.count()

    def get_last_modified(self, obj):
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
            "parent",
            "parent_id",
            "children",
            "created_by",
            "questions",
            "question_count",
            "last_modified",
        ]
        read_only_fields = ["created_by"]


class TestQuestionSerializer(serializers.ModelSerializer):
    question_data = QuestionSerializer(source='question', read_only=True)
    
    class Meta:
        model = TestQuestion
        fields = ['id', 'test', 'question', 'question_data', 'order']
        read_only_fields = ['test']


class TestSerializer(serializers.ModelSerializer):
    questions = TestQuestionSerializer(source='test_questions', many=True, read_only=True)
    question_count = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        return obj.test_questions.count()

    class Meta:
        model = Test
        fields = [
            'id',
            'course',
            'title',
            'configuration',
            'questions',
            'question_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['course']


class TestDraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestDraft
        fields = ['id', 'course', 'draft_data', 'created_at', 'updated_at', 'created_by']
        read_only_fields = ['created_by']
