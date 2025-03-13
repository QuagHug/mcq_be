from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes
from .models import QuestionBank, Question, Answer, Course, Taxonomy, QuestionTaxonomy
from .serializers import QuestionBankSerializer, QuestionSerializer, CourseSerializer
import uuid
from django.db import transaction
from .ai_service import AIService

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    data = request.data
    user = User.objects.create(
        username=data['username'],
        password=make_password(data['password'])
    )
    
    # Update the user's profile
    user.profile.first_name = data.get('first_name', '')
    user.profile.last_name = data.get('last_name', '')
    user.profile.role = data.get('role', 'teacher')  # default to teacher if not specified
    user.profile.save()
    
    return Response({'message': 'User created successfully'}, status=status.HTTP_201_CREATED)

# QuestionBank CRUD operations
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def question_bank_list(request, course_id):
    try:
        course = Course.objects.get(pk=course_id)
    except Course.DoesNotExist:
        return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        # Only get root-level question banks (those without parents)
        question_banks = QuestionBank.objects.filter(course=course, parent=None)
        serializer = QuestionBankSerializer(question_banks, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = request.data.copy()
        data['bank_id'] = str(uuid.uuid4())
        serializer = QuestionBankSerializer(data=data)
        if serializer.is_valid():
            serializer.save(
                created_by=request.user,
                course=course
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def question_bank_detail(request, course_id, pk):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=pk, course=course)
    except (Course.DoesNotExist, QuestionBank.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = QuestionBankSerializer(question_bank)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = QuestionBankSerializer(question_bank, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        question_bank.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# Question CRUD operations
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def question_list(request, course_id, bank_id):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
    except (Course.DoesNotExist, QuestionBank.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        questions = Question.objects.filter(question_bank=question_bank)
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = request.data.copy()
        answers_data = data.pop('answers', [])
        
        serializer = QuestionSerializer(data=data)
        if serializer.is_valid():
            question = serializer.save(question_bank=question_bank)
        
            # Create answers
            for answer_data in answers_data:
                Answer.objects.create(question=question, **answer_data)
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def question_detail(request, course_id, bank_id, pk):
    try:
        course = Course.objects.get(pk=course_id)
        question = Question.objects.get(pk=pk, question_bank_id=bank_id, question_bank__course=course)
    except (Course.DoesNotExist,Question.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = QuestionSerializer(question)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = QuestionSerializer(question, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        question.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def course_list(request):
    if request.method == 'GET':
        courses = Course.objects.all()
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = CourseSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def course_detail(request, pk):
    try:
        course = Course.objects.get(pk=pk)
    except Course.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = CourseSerializer(course)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = CourseSerializer(course, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        course.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def question_bulk_create(request, course_id, bank_id):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
    except (Course.DoesNotExist, QuestionBank.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    if not isinstance(request.data, list):
        return Response(
            {"error": "Data must be a list of questions"}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    created_questions = []
    
    try:
        with transaction.atomic():
            for i, question_data in enumerate(request.data):
                # Add debug logging
                print(f"\nProcessing question {i + 1}:")
                print(f"Question data received: {question_data}")
                
                # Extract answers from the question data
                answers_data = question_data.pop('answers', [])
                taxonomies_data = question_data.pop('taxonomies', [])
                
                print(f"Answers data: {answers_data}")
                print(f"Taxonomies data: {taxonomies_data}")
                
                # Create question
                serializer = QuestionSerializer(data=question_data)
                if serializer.is_valid():
                    question = serializer.save(question_bank=question_bank)
                    
                    # Create answers for this question
                    for answer_data in answers_data:
                        Answer.objects.create(question=question, **answer_data)
                    
                    # Create taxonomy relationships
                    for taxonomy_data in taxonomies_data:
                        taxonomy_id = taxonomy_data.get('taxonomy_id')
                        level = taxonomy_data.get('level')
                        difficulty = taxonomy_data.get('difficulty', 'medium')
                        
                        try:
                            taxonomy = Taxonomy.objects.get(pk=taxonomy_id)
                            QuestionTaxonomy.objects.create(
                                question=question,
                                taxonomy=taxonomy,
                                level=level,
                                difficulty=difficulty
                            )
                        except Taxonomy.DoesNotExist:
                            raise ValueError(f"Taxonomy with id {taxonomy_id} does not exist")
                    
                    created_questions.append(question)
                else:
                    print(f"Serializer validation errors: {serializer.errors}")
                    print(f"Invalid fields: {list(serializer.errors.keys())}")
                    print(f"Full question data: {question_data}")
                    raise ValueError(f"Invalid question data for question {i + 1}: {serializer.errors}")

        # Serialize all created questions
        response_serializer = QuestionSerializer(created_questions, many=True)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_questions(request):
    context = request.data.get('context', '')
    
    if not context:
        return Response(
            {"error": "Context is required"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        ai_service = AIService()
        questions = ai_service.generate_questions(context)
        return Response(questions, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )