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
]