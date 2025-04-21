from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
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

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def test_list(request, course_id):
    try:
        course = Course.objects.get(pk=course_id)
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
@permission_classes([IsAuthenticated])
def test_detail(request, course_id, pk):
    try:
        test = Test.objects.get(course_id=course_id, pk=pk)
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
@permission_classes([IsAuthenticated])
def test_add_questions(request, course_id, test_id):
    try:
        test = Test.objects.get(course_id=course_id, pk=test_id)
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
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def upload_test_results(request, course_id, test_id):
    try:
        test = Test.objects.get(course_id=course_id, pk=test_id)
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
                # Fit 2PL IRT model using girth
                irt_result = twopl_mml(response_matrix)
                discrimination = irt_result['Discrimination']
                difficulty = irt_result['Difficulty']
                
                # Update statistics for each question
                for i, question in enumerate(test_questions):
                    if not question.statistics:
                        question.statistics = {}
                    
                    if question.id in question_stats:
                        new_stats = {
                            'irt_parameters': {
                                'difficulty': float(difficulty[i]),
                                'discrimination': float(discrimination[i]),
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
            'irt_calculated': True
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
def test_draft_detail(request, draft_id):
    try:
        draft = TestDraft.objects.get(pk=draft_id, created_by=request.user)
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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
def question_taxonomy_mapping(request, question_id):
    try:
        question = Question.objects.get(pk=question_id)
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
        difficulty = request.data.get('difficulty', 'medium')
        
        try:
            taxonomy = Taxonomy.objects.get(pk=taxonomy_id)
            mapping = QuestionTaxonomy.objects.create(
                question=question,
                taxonomy=taxonomy,
                level=level,
                difficulty=difficulty
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
            if 'difficulty' in request.data:
                mapping.difficulty = request.data['difficulty']
                
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
@permission_classes([IsAuthenticated])
def update_test(request, course_id, test_id):
    try:
        # Get test and verify it belongs to the course
        test = Test.objects.get(pk=test_id, course_id=course_id)
        
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
@permission_classes([IsAuthenticated])
def question_group_list(request, course_id, bank_id):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
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
@permission_classes([IsAuthenticated])
def question_group_detail(request, course_id, bank_id, pk):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
        question_group = QuestionGroup.objects.get(pk=pk, question_bank=question_bank)
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
@permission_classes([IsAuthenticated])
def question_group_questions(request, course_id, bank_id, group_id):
    try:
        course = Course.objects.get(pk=course_id)
        question_bank = QuestionBank.objects.get(pk=bank_id, course=course)
        question_group = QuestionGroup.objects.get(pk=group_id, question_bank=question_bank)
    except (Course.DoesNotExist, QuestionBank.DoesNotExist, QuestionGroup.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)

    questions = Question.objects.filter(question_group=question_group)
    serializer = QuestionSerializer(questions, many=True)
    return Response(serializer.data)