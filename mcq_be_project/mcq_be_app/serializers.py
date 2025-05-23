from rest_framework import serializers
from .models import QuestionBank, Question, Answer, Course, Taxonomy, QuestionTaxonomy, TestQuestion, Test, TestDraft, QuestionGroup
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
    taxonomies = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()
    question_bank_id = serializers.IntegerField(source='question_bank.id', read_only=True)
    question_group_id = serializers.PrimaryKeyRelatedField(
        source='question_group',
        queryset=QuestionGroup.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Question
        fields = [
            "id",
            "question_text",
            "answers",
            "question_bank_id",
            "question_group_id",
            "created_at",
            "updated_at",
            "statistics",
            "taxonomies",
            "difficulty"
        ]

    def get_taxonomies(self, obj):
        question_taxonomies = obj.taxonomies.select_related('taxonomy').all()
        return [
            {
                'id': qt.id,
                'taxonomy': {
                    'id': qt.taxonomy.id,
                    'name': qt.taxonomy.name,
                    'description': qt.taxonomy.description,
                    'category': qt.taxonomy.category,
                    'levels': qt.taxonomy.levels
                },
                'level': qt.level
            }
            for qt in question_taxonomies
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
            guessing = float(irt.get('guessing', 0.25))
            
            # Scale difficulty from [-6, 6] to [0, 10]
            difficulty_score = (difficulty + 6) * (10 / 12)
            difficulty_score = max(0, min(10, difficulty_score))
            
            # Scale discrimination from [0, 4] to [0, 10]
            discrimination_score = discrimination * 2.5
            discrimination_score = max(0, min(10, discrimination_score))
            
            # Scale guessing from [0, 1] to [10, 0] (inverted because lower guessing is better)
            guessing_score = 10 - (guessing * 10)
            
            # Add scaled scores to the statistics
            stats['scaled_difficulty'] = round(difficulty_score, 2)
            stats['scaled_discrimination'] = round(discrimination_score, 2)
            stats['scaled_guessing'] = round(guessing_score, 2)
            
            # Define weights for the quality formula
            w1 = 1.0   # weight for discrimination
            w2 = 0.5   # penalty for difficulty deviation
            w3 = 2.0   # heavy penalty for guessing
            
            # Calculate raw quality score using the formula: w1*a - w2*|b| - w3*c
            # Note: We use the original IRT parameters, not the scaled scores
            raw_quality = (w1 * discrimination) - (w2 * abs(difficulty)) - (w3 * guessing)
            
            # Normalize to a 0-10 scale
            # Typical range for raw_quality might be from -3 to +3
            # We'll map this to 0-10 with a reasonable transformation
            normalized_quality = (raw_quality + 3) * (10/6)
            normalized_quality = max(0, min(10, normalized_quality))
            
            # Add quality score to statistics
            stats['quality_score'] = round(normalized_quality, 2)
            
            # Add a note about the formula used
            stats['quality_formula'] = "w1*a - w2*|b| - w3*c where w1=1.0, w2=0.5, w3=2.0"
        
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


class QuestionGroupSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    
    def get_question_count(self, obj):
        return obj.questions.count()
    
    class Meta:
        model = QuestionGroup
        fields = [
            'id',
            'name',
            'context',
            'group_id',
            'question_bank',
            'question_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['question_bank']
