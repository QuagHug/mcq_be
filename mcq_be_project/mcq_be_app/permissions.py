from rest_framework import permissions
from .models import Course

class IsCourseTeacherOrOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners or associated teachers of a course to access it.
    """
    
    def has_permission(self, request, view):
        # Allow all authenticated users to list courses
        # Specific course access will be checked in has_object_permission
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Check if the user is the owner or an associated teacher
        if hasattr(obj, 'owner'):
            # Direct course object
            return obj.owner == request.user or request.user in obj.teachers.all()
        
        # For objects that belong to a course (like QuestionBank, Question, etc.)
        if hasattr(obj, 'course'):
            course = obj.course
            return course.owner == request.user or request.user in course.teachers.all()
        
        # For objects with indirect course relationship (like Question -> QuestionBank -> Course)
        if hasattr(obj, 'question_bank') and hasattr(obj.question_bank, 'course'):
            course = obj.question_bank.course
            return course.owner == request.user or request.user in course.teachers.all()
            
        return False 