from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes
from .models import QuestionBank, Question, Answer, Course, Taxonomy, QuestionTaxonomy, Test, TestQuestion, TestResult, TestDraft, QuestionGroup
from .serializers import QuestionBankSerializer, QuestionSerializer, CourseSerializer, TestSerializer, TestDraftSerializer, QuestionTaxonomySerializer, QuestionGroupSerializer
import uuid
from django.db import transaction
from .ai_service import AIService
import io
import csv
from rest_framework.parsers import MultiPartParser
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from girth import twopl_mml
from datetime import datetime
from .similarity_service import SimilarityService
from .permissions import IsCourseTeacherOrOwner

# Initialize the similarity service
similarity_service = SimilarityService()

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
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_bank_list(request, course_id):
    try:
        course = Course.objects.get(pk=course_id)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
        
        if request.method == 'GET':
            parent_id = request.query_params.get('parent_id')
            if parent_id:
                # Get children of specific parent
                question_banks = QuestionBank.objects.filter(course=course, parent_id=parent_id)
            else:
                # Get root-level banks (those without parent)
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
            
    except Course.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_bank_detail(request, course_id, pk):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=pk, course=course)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
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
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_list(request, course_id, bank_id):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except (Course.DoesNotExist, QuestionBank.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        questions = Question.objects.filter(question_bank=question_bank)
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = request.data.copy()
        answers_data = data.pop('answers', [])
        taxonomies_data = data.pop('taxonomies', [])  # Extract taxonomies
        question_group_id = data.pop('question_group_id', None)
        
        serializer = QuestionSerializer(data=data)
        if serializer.is_valid():
            question = serializer.save(question_bank=question_bank)
            
            # Set question group if provided
            if question_group_id:
                try:
                    question_group = QuestionGroup.objects.get(pk=question_group_id, question_bank=question_bank)
                    question.question_group = question_group
                    question.save()
                except QuestionGroup.DoesNotExist:
                    pass
            
            # Create answers
            for answer_data in answers_data:
                Answer.objects.create(question=question, **answer_data)
            
            # Create taxonomy relationships
            for taxonomy_data in taxonomies_data:
                taxonomy_id = taxonomy_data.get('taxonomy_id')
                level = taxonomy_data.get('level')
                
                try:
                    taxonomy = Taxonomy.objects.get(pk=taxonomy_id)
                    QuestionTaxonomy.objects.create(
                        question=question,
                        taxonomy=taxonomy,
                        level=level
                    )
                except Taxonomy.DoesNotExist:
                    pass
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_detail(request, course_id, bank_id, pk):
    try:
        course = Course.objects.get(pk=course_id)
        question = Question.objects.get(pk=pk, question_bank_id=bank_id, question_bank__course=course)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
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
        # Filter courses to only include those where the user is owner or teacher
        owned_courses = Course.objects.filter(owner=request.user)
        teaching_courses = Course.objects.filter(teachers=request.user)
        
        # Combine the querysets and remove duplicates
        courses = (owned_courses | teaching_courses).distinct()
        
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = CourseSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(owner=request.user)  # Set the current user as owner
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def course_detail(request, course_id):
    try:
        course = Course.objects.get(pk=course_id)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
        
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
            
    except Course.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_bulk_create(request, course_id, bank_id):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
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
                        
                        try:
                            taxonomy = Taxonomy.objects.get(pk=taxonomy_id)
                            QuestionTaxonomy.objects.create(
                                question=question,
                                taxonomy=taxonomy,
                                level=level
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
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
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

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def test_list(request, course_id):
    try:
        course = Course.objects.get(pk=course_id)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except Course.DoesNotExist:
        return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        tests = Test.objects.filter(course=course)
        serializer = TestSerializer(tests, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = request.data.copy()
        serializer = TestSerializer(data=data)
        if serializer.is_valid():
            serializer.save(course=course)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def test_detail(request, course_id, pk):
    try:
        test = Test.objects.get(course_id=course_id, pk=pk)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, test.course):
            return Response({"detail": "You do not have permission to access this test."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except Test.DoesNotExist:
        return Response({'error': 'Test not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = TestSerializer(test)
        return Response(serializer.data)

    elif request.method == 'PUT':
        # Update basic test info
        test.title = request.data.get('title', test.title)
        test.configuration = request.data.get('config', test.configuration)
        test.save()
        
        # Update question relationships
        if 'question_ids' in request.data:
            # Clear existing questions
            TestQuestion.objects.filter(test=test).delete()
            
            # Add new questions
            question_ids = request.data['question_ids']
            for index, q_id in enumerate(question_ids):
                TestQuestion.objects.create(
                    test=test,
                    question_id=q_id,
                    order=index
                )
        
        # Return updated test data
        serializer = TestSerializer(test)
        return Response(serializer.data)

    elif request.method == 'DELETE':
        test.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def test_add_questions(request, course_id, test_id):
    try:
        test = Test.objects.get(course_id=course_id, pk=test_id)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, test.course):
            return Response({"detail": "You do not have permission to access this test."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except Test.DoesNotExist:
        return Response({'error': 'Test not found'}, status=status.HTTP_404_NOT_FOUND)

    questions_data = request.data.get('questions', [])
    created_questions = []

    for question_data in questions_data:
        question_id = question_data.get('question_id')
        order = question_data.get('order', 0)

        try:
            question = Question.objects.get(pk=question_id)
            test_question, created = TestQuestion.objects.get_or_create(
                test=test,
                question=question,
                defaults={'order': order}
            )
            if not created:
                test_question.order = order
                test_question.save()
            
            created_questions.append({
                'id': test_question.id,
                'question_id': question_id,
                'order': order
            })
        except Question.DoesNotExist:
            return Response(
                {'error': f'Question {question_id} not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

    return Response(created_questions, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def create_test(request, course_id):
    try:
        # Extract data from request
        title = request.data.get('title', 'Untitled Test')
        question_ids = request.data.get('question_ids', [])
        config = request.data.get('config', {})
        
        # Validate and transform config
        configuration = {
            'letterCase': config.get('letterCase', 'uppercase'),
            'separator': config.get('separator', ')'),
            'includeAnswerKey': config.get('includeAnswerKey', False)
        }
        
        # Validate course exists
        try:
            course = Course.objects.get(id=course_id)
            # Check object-level permissions
            if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
                return Response({"detail": "You do not have permission to access this course."}, 
                               status=status.HTTP_403_FORBIDDEN)
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create the test
        test = Test.objects.create(
            title=title,
            course=course,
            configuration=configuration
        )
        
        # Create test questions with order
        for index, question_id in enumerate(question_ids):
            try:
                question = Question.objects.get(id=question_id)
                TestQuestion.objects.create(
                    test=test,
                    question=question,
                    order=index
                )
            except Question.DoesNotExist:
                continue
        
        serializer = TestSerializer(test)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
@parser_classes([MultiPartParser])
def upload_test_results(request, course_id, test_id):
    try:
        test = Test.objects.get(course_id=course_id, pk=test_id)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, test.course):
            return Response({"detail": "You do not have permission to access this test."}, 
                           status=status.HTTP_403_FORBIDDEN)
        
        test_questions = Question.objects.filter(
            test_questions__test=test
        ).order_by('test_questions__order')
        
        # Get the number of questions in this test
        num_questions = test_questions.count()
        print(f"Number of questions in test: {num_questions}")
        
    except Test.DoesNotExist:
        return Response({'error': 'Test not found'}, status=status.HTTP_404_NOT_FOUND)

    if 'file' not in request.FILES:
        return Response({'error': 'File is required'}, status=status.HTTP_400_BAD_REQUEST)

    file = request.FILES['file']
    results = []
    response_matrix = []

    try:
        # Read all sheets from Excel file
        excel_file = pd.ExcelFile(file)
        
        # Read answers from first sheet
        df_answers = pd.read_excel(excel_file, sheet_name=0)
        
        # Read mapping from third sheet
        df_mapping = pd.read_excel(excel_file, sheet_name=2)
        print("Available columns:", df_mapping.columns.tolist())
        
        # Create mapping dictionaries for each version
        version_mappings = {}
        db_col = df_mapping.columns[0]  # First column has our DB question numbers
        
        # For each version (each column after the first)
        for version_col in df_mapping.columns[1:]:
            version_mapping = {}
            # For each row in mapping
            for index, row in df_mapping.iterrows():
                db_question = row[db_col]      # Get the DB question number
                version_q = row[version_col]   # Get the shuffled question number
                if pd.notna(db_question) and pd.notna(version_q):
                    # Map from shuffled question number to DB question number
                    version_mapping[int(version_q)] = int(db_question)
            version_mappings[version_col] = version_mapping
        
        # Verify that the mapping contains all questions from the test
        for version, mapping in version_mappings.items():
            mapped_questions = set(mapping.values())
            if len(mapped_questions) != num_questions:
                return Response({
                    'error': f'Mapping mismatch: Test has {num_questions} questions, but mapping for version {version} has {len(mapped_questions)} questions',
                    'test_questions': num_questions,
                    'mapped_questions': len(mapped_questions)
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Initialize response matrix
        response_matrix = []
        
        # Process each student's answers
        for idx, row in df_answers.iterrows():
            student_responses = [0] * num_questions  # Initialize with zeros
            has_answers = False
            student_id = str(uuid.uuid4())
            
            # Get all C columns that exist
            c_columns = [col for col in df_answers.columns if col.startswith('C')]
            
            # Try each version's mapping until we find one that works
            used_version = None
            for version, mapping in version_mappings.items():
                test_responses = [0] * num_questions
                valid_answers = 0
                
                # Try mapping all answers using this version
                for col in c_columns:
                    if pd.notna(row[col]):
                        q_num = int(col[1:])  # Extract number from C1, C2, etc.
                        if q_num in mapping:
                            db_q_num = mapping[q_num]  # Get original DB question number
                            answer_value = str(row[col])
                            is_correct = answer_value.endswith('1')
                            
                            # Adjust index to 0-based
                            mapped_index = db_q_num - 1
                            if 0 <= mapped_index < num_questions:
                                test_responses[mapped_index] = 1 if is_correct else 0
                                valid_answers += 1
                
                # If this version gave us the most valid answers, use it
                if valid_answers > sum(student_responses):
                    student_responses = test_responses
                    used_version = version
                    has_answers = valid_answers > 0
            
            if has_answers:
                print(f"Student {idx} used version {used_version} with {sum(student_responses)} valid answers")
                
                # Check if the number of valid answers matches the test's question count
                if valid_answers != num_questions:
                    print(f"Warning: Student {idx} has {valid_answers} valid answers, but test has {num_questions} questions")
                
                response_matrix.append(student_responses)
                # Create TestResult record
                TestResult.objects.create(
                    test=test,
                    student_id=student_id,
                    answers=student_responses
                )
                results.append({
                    'student_id': student_id,
                    'answers': student_responses,
                    'version': used_version
                })
            else:
                print(f"Skipped student {idx} - no valid answers found in any version")
        
        # Check if we have any valid responses
        if len(response_matrix) == 0:
            return Response({
                'error': 'No valid student responses found in the uploaded file'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Convert to numpy array for IRT calculation
        response_matrix = np.array(response_matrix)
        print(f"Final response matrix shape: {response_matrix.shape}")

        # Verify response matrix dimensions match test questions
        if response_matrix.shape[1] != num_questions:
            return Response({
                'error': f'Response matrix has {response_matrix.shape[1]} columns, but test has {num_questions} questions',
                'test_questions': num_questions,
                'response_columns': response_matrix.shape[1]
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            print("Attempting IRT calculation...")
            print(f"Response matrix shape before IRT: {response_matrix.shape}")
            
            # Create a mapping of array index to question ID
            index_to_question = {}
            for i, question in enumerate(test_questions):
                index_to_question[i] = question
            
            # Calculate classical statistics first
            question_stats = {}
            for i in range(response_matrix.shape[1]):
                if i in index_to_question:
                    question = index_to_question[i]
                    total_responses = len(response_matrix)
                    correct_responses = int(response_matrix[:, i].sum())
                    p_value = float(correct_responses / total_responses) if total_responses > 0 else 0
                    
                    question_stats[question.id] = {
                        'classical_parameters': {
                            'p_value': p_value,
                            'total_responses': total_responses,
                            'correct_responses': correct_responses,
                        }
                    }
                    print(f"Classical stats for question {question.id}: p={p_value}, correct={correct_responses}/{total_responses}")
            
            try:
                # Import 3PL model from girth
                from girth import threepl_mml
                
                # Call threepl_mml without the guessing parameter
                # Let the function handle guessing initialization internally
                irt_result = threepl_mml(response_matrix)
                
                # Extract parameters from result
                discrimination = irt_result['Discrimination']
                difficulty = irt_result['Difficulty']
                guessing = irt_result['Guessing']  # The guessing param should be in the result
                
                # Update statistics for each question
                for i, question in enumerate(test_questions):
                    if not question.statistics:
                        question.statistics = {}
                    
                    if question.id in question_stats:
                        new_stats = {
                            'irt_parameters': {
                                'difficulty': float(difficulty[i]),
                                'discrimination': float(discrimination[i]),
                                'guessing': float(guessing[i]),
                            },
                            'classical_parameters': question_stats[question.id]['classical_parameters'],
                            'last_updated': str(datetime.now())
                        }
                        
                        print(f"Updating statistics for question {question.id}:")
                        print(f"Old statistics: {question.statistics}")
                        print(f"New statistics: {new_stats}")
                        
                        question.statistics.update(new_stats)
                        question.save()
            
            except Exception as irt_calc_error:
                print(f"IRT calculation specific error: {str(irt_calc_error)}")
                # Even if IRT fails, save the classical statistics
                for question in test_questions:
                    if not question.statistics:
                        question.statistics = {}
                    
                    if question.id in question_stats:
                        question.statistics.update({
                            'classical_parameters': question_stats[question.id]['classical_parameters'],
                            'error': f'IRT calculation failed: {str(irt_calc_error)}',
                            'last_updated': str(datetime.now())
                        })
                        question.save()
                raise

        except Exception as irt_error:
            print(f"IRT calculation error: {str(irt_error)}")
            # Fallback to classical statistics
            for i, question in enumerate(test_questions):
                if not question.statistics:
                    question.statistics = {}
                
                total_responses = len(response_matrix)
                correct_responses = int(response_matrix[:, i].sum()) if len(response_matrix) > 0 else 0
                
                new_stats = {
                    'classical_parameters': {
                        'p_value': float(correct_responses / total_responses) if total_responses > 0 else 0,
                        'total_responses': total_responses,
                        'correct_responses': correct_responses,
                    },
                    'error': f'IRT calculation failed: {str(irt_error)}',
                    'last_updated': str(datetime.now())
                }
                
                print(f"Updating statistics for question {question.id} (error fallback):")
                print(f"Old statistics: {question.statistics}")
                print(f"New statistics: {new_stats}")
                
                question.statistics.update(new_stats)
                question.save()

        return Response({
            'message': 'Test results uploaded successfully',
            'test_id': test.id,
            'results_count': len(results),
            'irt_calculated': True,
            'model_used': '3PL'  # Add information about which model was used
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def test_draft_create(request):
    if request.method == 'DELETE':
        deleted_count, _ = TestDraft.objects.filter(created_by=request.user).delete()
        return Response({
            'message': f'Successfully deleted {deleted_count} draft(s)',
            'deleted_count': deleted_count
        }, status=status.HTTP_200_OK)
    
    try:
        # Get course ID from request
        course_id = request.data.get('courseId')
        
        # Validate course exists
        try:
            course = Course.objects.get(id=course_id)
            # Check object-level permissions
            if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
                return Response({"detail": "You do not have permission to access this course."}, 
                               status=status.HTTP_403_FORBIDDEN)
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Delete any existing drafts for this user (regardless of course)
        TestDraft.objects.filter(created_by=request.user).delete()
        
        # Create test draft
        test_draft = TestDraft.objects.create(
            course=course,
            draft_data=request.data,
            created_by=request.user
        )
        
        serializer = TestDraftSerializer(test_draft)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def test_draft_detail(request, draft_id):
    try:
        draft = TestDraft.objects.get(pk=draft_id, created_by=request.user)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, draft.course):
            return Response({"detail": "You do not have permission to access this test draft."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except TestDraft.DoesNotExist:
        return Response({'error': 'Test draft not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = TestDraftSerializer(draft)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        draft.draft_data = request.data
        draft.save()
        serializer = TestDraftSerializer(draft)
        return Response(serializer.data)
    
    elif request.method == 'DELETE':
        draft.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def test_draft_list(request):
    # Get course_id from query params if provided
    course_id = request.query_params.get('course_id')
    
    if course_id:
        drafts = TestDraft.objects.filter(course_id=course_id, created_by=request.user)
    else:
        drafts = TestDraft.objects.filter(created_by=request.user)
        
    serializer = TestDraftSerializer(drafts, many=True)
    return Response(serializer.data)

@api_view(['GET', 'POST', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_taxonomy_mapping(request, question_id):
    try:
        question = Question.objects.get(pk=question_id)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, question.question_bank.course):
            return Response({"detail": "You do not have permission to access this question."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except Question.DoesNotExist:
        return Response({'error': 'Question not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        # Get all taxonomy mappings for this question
        mappings = QuestionTaxonomy.objects.filter(question=question)
        serializer = QuestionTaxonomySerializer(mappings, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        # Create a new taxonomy mapping
        taxonomy_id = request.data.get('taxonomy_id')
        level = request.data.get('level')
        
        try:
            taxonomy = Taxonomy.objects.get(pk=taxonomy_id)
            mapping = QuestionTaxonomy.objects.create(
                question=question,
                taxonomy=taxonomy,
                level=level
            )
            serializer = QuestionTaxonomySerializer(mapping)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Taxonomy.DoesNotExist:
            return Response(
                {'error': f'Taxonomy with id {taxonomy_id} does not exist'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    elif request.method == 'PUT':
        # Update an existing mapping
        mapping_id = request.data.get('mapping_id')
        try:
            mapping = QuestionTaxonomy.objects.get(pk=mapping_id, question=question)
            
            # Update fields
            if 'level' in request.data:
                mapping.level = request.data['level']
            
            mapping.save()
            serializer = QuestionTaxonomySerializer(mapping)
            return Response(serializer.data)
        except QuestionTaxonomy.DoesNotExist:
            return Response(
                {'error': 'Mapping not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    elif request.method == 'DELETE':
        # Delete a mapping
        mapping_id = request.data.get('mapping_id')
        if mapping_id:
            try:
                mapping = QuestionTaxonomy.objects.get(pk=mapping_id, question=question)
                mapping.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
            except QuestionTaxonomy.DoesNotExist:
                return Response(
                    {'error': 'Mapping not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Delete all mappings for this question
            QuestionTaxonomy.objects.filter(question=question).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['PUT'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def update_test(request, course_id, test_id):
    try:
        # Get test and verify it belongs to the course
        test = Test.objects.get(pk=test_id, course_id=course_id)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, test.course):
            return Response({"detail": "You do not have permission to access this test."}, 
                           status=status.HTTP_403_FORBIDDEN)
        
        # Update basic test info
        test.title = request.data.get('title', test.title)
        test.config = request.data.get('config', test.config)
        test.save()
        
        # Update question relationships
        if 'question_ids' in request.data:
            # Clear existing questions
            TestQuestion.objects.filter(test=test).delete()
            
            # Add new questions
            question_ids = request.data['question_ids']
            for index, q_id in enumerate(question_ids):
                TestQuestion.objects.create(
                    test=test,
                    question_id=q_id,
                    order=index
                )
        
        # Return updated test data
        serializer = TestSerializer(test)
        return Response(serializer.data)
        
    except Test.DoesNotExist:
        return Response({'error': 'Test not found'}, status=status.HTTP_404_NOT_FOUND)
    except Question.DoesNotExist:
        return Response({'error': 'One or more questions not found'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_group_list(request, course_id, bank_id):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except (Course.DoesNotExist, QuestionBank.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        groups = QuestionGroup.objects.filter(question_bank=question_bank)
        serializer = QuestionGroupSerializer(groups, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = request.data.copy()
        data['group_id'] = str(uuid.uuid4())
        serializer = QuestionGroupSerializer(data=data)
        if serializer.is_valid():
            serializer.save(question_bank=question_bank)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_group_detail(request, course_id, bank_id, pk):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
        question_group = QuestionGroup.objects.get(pk=pk, question_bank=question_bank)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except (Course.DoesNotExist, QuestionBank.DoesNotExist, QuestionGroup.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = QuestionGroupSerializer(question_group)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = QuestionGroupSerializer(question_group, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        question_group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def question_group_questions(request, course_id, bank_id, group_id):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
        question_group = QuestionGroup.objects.get(pk=group_id, question_bank=question_bank)
        # Check object-level permissions
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({"detail": "You do not have permission to access this course."}, 
                           status=status.HTTP_403_FORBIDDEN)
    except (Course.DoesNotExist, QuestionBank.DoesNotExist, QuestionGroup.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    questions = Question.objects.filter(question_group=question_group)
    serializer = QuestionSerializer(questions, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def check_question_similarity(request):
    """
    Check if a question is similar to existing questions in the database.
    """
    question_text = request.data.get('question_text')
    question_bank_id = request.data.get('question_bank_id')
    threshold = request.data.get('threshold', 0.75)
    
    if not question_text:
        return Response(
            {"error": "Question text is required"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Build or update the index if question_bank_id is provided
    if question_bank_id:
        try:
            question_bank = QuestionBank.objects.get(pk=question_bank_id)
            similarity_service.build_index_from_db(question_bank_id)
        except QuestionBank.DoesNotExist:
            return Response(
                {"error": f"Question bank with id {question_bank_id} does not exist"}, 
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        # Use all questions if no question bank specified
        similarity_service.build_index_from_db()
    
    # Find similar questions
    similar_questions = similarity_service.find_similar_questions(
        question_text, 
        threshold=threshold
    )
    
    # Get full question details
    if similar_questions:
        question_ids = [q['question_id'] for q in similar_questions]
        questions = Question.objects.filter(id__in=question_ids)
        
        # Enrich results with question details
        for result in similar_questions:
            question = next((q for q in questions if q.id == result['question_id']), None)
            if question:
                result['question_text'] = question.question_text
                result['question_bank_id'] = question.question_bank_id
    
    return Response({
        "question_text": question_text,
        "similar_questions": similar_questions,
        "total_matches": len(similar_questions)
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def find_similar_question_pairs(request, question_bank_id=None):
    """
    Find all pairs of similar questions within a question bank.
    """
    threshold = float(request.query_params.get('threshold', 0.85))
    max_pairs = int(request.query_params.get('max_pairs', 100))
    
    # Validate question bank if provided
    if question_bank_id:
        try:
            QuestionBank.objects.get(pk=question_bank_id)
        except QuestionBank.DoesNotExist:
            return Response(
                {"error": f"Question bank with id {question_bank_id} does not exist"}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    # Find similar pairs
    similar_pairs = similarity_service.find_similar_pairs(
        question_bank_id=question_bank_id,
        threshold=threshold,
        max_pairs=max_pairs
    )
    
    return Response(similar_pairs, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def generate_distractors(request):
    """
    Generate plausible distractors for a given question and correct answer.
    
    Supports either:
    - num_distractors + difficulty: Generate a specific number of distractors at one difficulty level
    - difficulty_distribution: Generate distractors with different difficulty levels
      (e.g., {"easy": 2, "medium": 2, "hard": 1})
    """
    question_text = request.data.get('question_text', '')
    correct_answer = request.data.get('correct_answer', '')
    difficulty_distribution = request.data.get('difficulty_distribution')
    num_distractors = request.data.get('num_distractors', 3)
    difficulty = request.data.get('difficulty', 'medium')
    
    if not question_text or not correct_answer:
        return Response(
            {"error": "Question text and correct answer are required"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate difficulty distribution if provided
    if difficulty_distribution:
        if not isinstance(difficulty_distribution, dict):
            return Response(
                {"error": "difficulty_distribution must be a dictionary"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_difficulties = ['easy', 'medium', 'hard']
        for diff, count in difficulty_distribution.items():
            if diff not in valid_difficulties:
                return Response(
                    {"error": f"Invalid difficulty level: {diff}. Must be one of {valid_difficulties}"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not isinstance(count, int) or count < 0:
                return Response(
                    {"error": f"Count for {diff} must be a non-negative integer"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
    
    try:
        ai_service = AIService()
        distractors = ai_service.generate_distractors(
            question_text=question_text,
            correct_answer=correct_answer,
            difficulty_distribution=difficulty_distribution,
            num_distractors=num_distractors,
            difficulty=difficulty
        )
        
        # Format the response to include both the correct answer and distractors
        response_data = {
            "question_text": question_text,
            "correct_answer": {
                "answer_text": correct_answer,
                "is_correct": True,
                "explanation": request.data.get('explanation', "This is the correct answer"),
                "difficulty": "correct"
            },
            "distractors": distractors
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def add_distractors_to_question(request, question_id):
    """
    Add generated distractors to an existing question in the database.
    
    Expected request body:
    {
        "distractors": [
            {
                "answer_text": "Distractor 1",
                "explanation": "Why this is wrong",
                "difficulty": "medium"
            },
            ...
        ]
    }
    """
    try:
        question = Question.objects.get(pk=question_id)
        
        # Check permissions
        course = question.question_bank.course
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response(
                {"error": "You do not have permission to modify this question"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get distractors from request
        distractors = request.data.get('distractors', [])
        if not distractors or not isinstance(distractors, list):
            return Response(
                {"error": "Distractors must be provided as a list"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Save distractors to database
        created_answers = []
        with transaction.atomic():
            for distractor in distractors:
                # Extract fields
                answer_text = distractor.get('answer_text')
                explanation = distractor.get('explanation', '')
                difficulty = distractor.get('difficulty', 'medium')
                
                if not answer_text:
                    continue
           
                # Create the answer
                answer = Answer.objects.create(
                    question=question,
                    answer_text=answer_text,
                    is_correct=False,
                    explanation=explanation
                )
                created_answers.append(answer)
        
        # Return the updated question with all answers
        question_serializer = QuestionSerializer(question)
        
        return Response({
            'message': f'Successfully added {len(created_answers)} distractors to question',
            'question': question_serializer.data
        }, status=status.HTTP_200_OK)
        
    except Question.DoesNotExist:
        return Response(
            {"error": f"Question with id {question_id} does not exist"}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def compare_tests(request):
    """
    Compare two tests for similarity.
    
    Expected request body:
    {
        "test1_id": 123,
        "test2_id": 456,
        "similarity_threshold": 0.75  # optional
    }
    
    Or to compare by question lists:
    {
        "test1_questions": [{...}, {...}],
        "test2_questions": [{...}, {...}],
        "similarity_threshold": 0.75  # optional
    }
    """
    # Get parameters
    test1_id = request.data.get('test1_id')
    test2_id = request.data.get('test2_id')
    test1_questions = request.data.get('test1_questions')
    test2_questions = request.data.get('test2_questions')
    similarity_threshold = float(request.data.get('similarity_threshold', 0.75))
    
    # Validate that we have either test IDs or question lists
    if not ((test1_id and test2_id) or (test1_questions and test2_questions)):
        return Response({
            "error": "You must provide either test IDs or question lists for comparison"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # If test IDs are provided, fetch the questions
        if test1_id and test2_id:
            try:
                test1 = Test.objects.get(pk=test1_id)
                test2 = Test.objects.get(pk=test2_id)
                
                # Check permissions
                if not request.user.is_staff:
                    course1 = test1.course
                    course2 = test2.course
                    if not (IsCourseTeacherOrOwner().has_object_permission(request, None, course1) and
                            IsCourseTeacherOrOwner().has_object_permission(request, None, course2)):
                        return Response({
                            "error": "You do not have permission to access one or both tests"
                        }, status=status.HTTP_403_FORBIDDEN)
                
                # Get questions from tests
                test1_questions = list(Question.objects.filter(
                    test_questions__test=test1
                ).values('id', 'question_text'))
                
                test2_questions = list(Question.objects.filter(
                    test_questions__test=test2
                ).values('id', 'question_text'))
                
            except Test.DoesNotExist:
                return Response({
                    "error": "One or both test IDs are invalid"
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate similarity
        similarity_result = similarity_service.compare_tests(
            test1_questions=test1_questions,
            test2_questions=test2_questions,
            similarity_threshold=similarity_threshold
        )
        
        # Add test information to the response
        if test1_id and test2_id:
            similarity_result['test1'] = {
                'id': test1_id,
                'title': test1.title,
                'question_count': len(test1_questions)
            }
            similarity_result['test2'] = {
                'id': test2_id,
                'title': test2.title,
                'question_count': len(test2_questions)
            }
        else:
            similarity_result['test1'] = {
                'question_count': len(test1_questions)
            }
            similarity_result['test2'] = {
                'question_count': len(test2_questions)
            }
        
        return Response(similarity_result, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "error": str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def find_similar_tests(request, test_id):
    """
    Find tests that are similar to the specified test within the same question bank.
    
    Query parameters:
    - threshold: Similarity threshold (default: 0.75)
    - max_results: Maximum number of similar tests to return (default: 5)
    """
    try:
        # Get parameters
        threshold = float(request.query_params.get('threshold', 0.75))
        max_results = int(request.query_params.get('max_results', 5))
        
        # Get the test and check permissions
        test = Test.objects.get(pk=test_id)
        course = test.course
        
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({
                "error": "You do not have permission to access this test"
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get questions from the target test
        test_questions = list(Question.objects.filter(
            test_questions__test=test
        ).values('id', 'question_text'))
        
        # Find other tests in the same course
        other_tests = Test.objects.filter(course=course).exclude(pk=test_id)
        
        similar_tests = []
        
        # Compare with each other test
        for other_test in other_tests:
            other_test_questions = list(Question.objects.filter(
                test_questions__test=other_test
            ).values('id', 'question_text'))
            
            if not other_test_questions:
                continue
            
            # Calculate similarity
            similarity_result = similarity_service.compare_tests(
                test1_questions=test_questions,
                test2_questions=other_test_questions,
                similarity_threshold=threshold
            )
            
            # Add to results if there's meaningful similarity
            if similarity_result['overall_similarity'] > threshold:
                # Get the actual list of unique questions from test1 and test2 that appear in similar pairs
                unique_test1_questions = set()
                unique_test2_questions = set()
                
                for pair in similarity_result['similar_question_pairs']:
                    if pair.get('test1_question_id'):
                        unique_test1_questions.add(pair['test1_question_id'])
                    if pair.get('test2_question_id'):
                        unique_test2_questions.add(pair['test2_question_id'])
                
                similar_tests.append({
                    'test_id': other_test.id,
                    'test_title': other_test.title,
                    'similarity_score': similarity_result['overall_similarity'],
                    'similar_question_count': len(unique_test2_questions),  # Count of unique questions in other test that have similarities
                    'total_questions': len(other_test_questions),
                    'question_coverage': len(unique_test2_questions) / len(other_test_questions) if len(other_test_questions) > 0 else 0
                })
        
        # Sort by similarity (highest first)
        similar_tests.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Limit results
        similar_tests = similar_tests[:max_results]
        
        return Response({
            'test_id': test_id,
            'test_title': test.title,
            'total_questions': len(test_questions),
            'similar_tests': similar_tests,
            'total_similar_tests': len(similar_tests)
        }, status=status.HTTP_200_OK)
        
    except Test.DoesNotExist:
        return Response({
            "error": f"Test with id {test_id} does not exist"
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            "error": str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated, IsCourseTeacherOrOwner])
def check_test_similarity_before_creation(request, course_id):
    """
    Check if the questions a user is about to add to a new test
    are similar to any existing tests in the course.
    
    Expected request body:
    {
        "question_ids": [1, 2, 3, ...],
        "threshold": 0.75,  # optional
        "max_results": 5    # optional
    }
    """
    # Get parameters
    question_ids = request.data.get('question_ids', [])
    threshold = float(request.data.get('threshold', 0.75))
    max_results = int(request.data.get('max_results', 5))
    
    # Validate input
    if not question_ids:
        return Response({
            "error": "Please provide question IDs to check for similar tests"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Get course and check permissions
        course = Course.objects.get(pk=course_id)
        if not IsCourseTeacherOrOwner().has_object_permission(request, None, course):
            return Response({
                "error": "You do not have permission to access this course"
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get the questions being considered for the new test
        candidate_questions = list(Question.objects.filter(
            id__in=question_ids
        ).values('id', 'question_text'))
        
        # If some questions weren't found, note them
        found_ids = [q['id'] for q in candidate_questions]
        missing_ids = [qid for qid in question_ids if qid not in found_ids]
        
        # Find all tests in the course
        existing_tests = Test.objects.filter(course=course)
        
        similar_tests = []
        
        # Compare with each existing test
        for existing_test in existing_tests:
            existing_test_questions = list(Question.objects.filter(
                test_questions__test=existing_test
            ).values('id', 'question_text'))
            
            if not existing_test_questions:
                continue
            
            # Calculate similarity
            similarity_result = similarity_service.compare_tests(
                test1_questions=candidate_questions,
                test2_questions=existing_test_questions,
                similarity_threshold=threshold
            )
            
            # Add to results if there's meaningful similarity
            if similarity_result['overall_similarity'] > threshold:
                # Get the actual list of unique questions from both tests that appear in similar pairs
                unique_candidate_questions = set()
                unique_existing_questions = set()
                
                for pair in similarity_result['similar_question_pairs']:
                    if pair.get('test1_question_id'):
                        unique_candidate_questions.add(pair['test1_question_id'])
                    if pair.get('test2_question_id'):
                        unique_existing_questions.add(pair['test2_question_id'])
                
                similar_tests.append({
                    'test_id': existing_test.id,
                    'test_title': existing_test.title,
                    'similarity_score': similarity_result['overall_similarity'],
                    'similar_question_count': len(unique_existing_questions),  # Count of unique questions with similarities
                    'total_questions_in_existing_test': len(existing_test_questions),
                    'question_coverage': len(unique_existing_questions) / len(existing_test_questions) if len(existing_test_questions) > 0 else 0,
                    'similar_question_pairs': similarity_result['similar_question_pairs'][:5]  # Limit number of pairs returned
                })
        
        # Sort by similarity (highest first)
        similar_tests.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Limit results
        similar_tests = similar_tests[:max_results]
        
        return Response({
            'candidate_questions_count': len(candidate_questions),
            'missing_question_ids': missing_ids if missing_ids else None,
            'similar_tests': similar_tests,
            'total_similar_tests': len(similar_tests)
        }, status=status.HTTP_200_OK)
        
    except Course.DoesNotExist:
        return Response({
            "error": f"Course with id {course_id} does not exist"
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            "error": str(e)
        }, status=status.HTTP_400_BAD_REQUEST)