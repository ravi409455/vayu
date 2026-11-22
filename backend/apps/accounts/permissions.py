from rest_framework.permissions import BasePermission


class PasswordChangeNotRequired(BasePermission):
    def has_permission(self, request, view):
        return True  # real rule in Task 1.3
