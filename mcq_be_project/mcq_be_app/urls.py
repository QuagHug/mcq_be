from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('courses/', views.course_list, name='course-list'),
    path('courses/<int:pk>/', views.course_detail, name='course-detail'),
    path('courses/<int:course_id>/question-banks/', views.question_bank_list, name='question-bank-list'),
    path('courses/<int:course_id>/question-banks/<int:pk>/', views.question_bank_detail, name='question-bank-detail'),
    path('courses/<int:course_id>/question-banks/<int:bank_id>/questions/', views.question_list, name='question-list'),
    path('courses/<int:course_id>/question-banks/<int:bank_id>/questions/<int:pk>/', views.question_detail, name='question-detail'),
    path('courses/<int:course_id>/question-banks/<int:bank_id>/questions/bulk/', 
         views.question_bulk_create, 
         name='question-bulk-create'),
    path('generate-questions/', 
         views.generate_questions, 
         name='generate-questions'),
    path('courses/<int:course_id>/tests/', views.test_list, name='test-list'),
    path('courses/<int:course_id>/tests/<int:pk>/', views.test_detail, name='test-detail'),
    path('courses/<int:course_id>/tests/<int:test_id>/questions/', views.test_add_questions, name='test-add-questions'),
    path('courses/<int:course_id>/tests/create/', views.create_test, name='create-test'),
    path('courses/<int:course_id>/tests/<int:test_id>/results/upload/',
         views.upload_test_results,
         name='upload-test-results'),
    path('test-drafts/', views.test_draft_create, name='test-draft-create'),
    path('test-drafts/list/', views.test_draft_list, name='test-draft-list'),
    path('test-drafts/<int:draft_id>', views.test_draft_detail, name='test-draft-detail'),
]