from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib import admin


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    ROLE_CHOICES = [
        ("teacher", "Teacher"),
        ("it_admin", "IT Admin"),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.user.username} - {self.role}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


class Course(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    course_id = models.CharField(max_length=100, default="CO0000", unique=True)
    image_url = models.URLField(null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class QuestionBank(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    bank_id = models.CharField(max_length=100, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="question_banks"
    ) 
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='children'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Question(models.Model):
    question_text = models.TextField()
    image_url = models.URLField(null=True, blank=True)
    question_bank = models.ForeignKey(
        "QuestionBank", related_name="questions", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.question_text


class Answer(models.Model):
    question = models.ForeignKey(
        Question, related_name="answers", on_delete=models.CASCADE
    )
    answer_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    explanation = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.answer_text[:50]


class Taxonomy(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    category = models.CharField(max_length=255)
    levels = models.JSONField(default=list)  # Store levels as JSON array

    def __str__(self):
        return self.name


class QuestionTaxonomy(models.Model):
    question = models.ForeignKey(
        "Question", on_delete=models.CASCADE, related_name="taxonomies"
    )
    taxonomy = models.ForeignKey(
        "Taxonomy", on_delete=models.CASCADE, related_name="questions"
    )
    level = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("question", "taxonomy")

    def __str__(self):
        return f"{self.question.question_text[:30]} - {self.taxonomy.name} (Level: {self.level})"


class Test(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='tests')
    configuration = models.JSONField(default=dict)
    title = models.CharField(max_length=255, default='Untitled Test')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Test {self.id} for {self.course.name}"


class TestQuestion(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='test_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='test_questions')
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        unique_together = [('test', 'question')]

    def __str__(self):
        return f"Question {self.question.id} in Test {self.test.id}"


admin.site.register(Course)
admin.site.register(QuestionBank)
admin.site.register(Question)
admin.site.register(Answer)
