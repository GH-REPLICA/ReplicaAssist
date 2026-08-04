from django.shortcuts import redirect
from django.contrib import messages


class PermissionMiddleware:

    BACKUP_ONLY_PATHS = (
        "/admin-backup/",
        "/admin-backup/export/",
        "/admin-backup/import/",
        "/admin-tickets/export/",
        "/admin-tickets/import/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if not request.user.is_authenticated:
            return self.get_response(request)

        profile = getattr(request.user, "profile", None)
        role_obj = getattr(profile, "role", None)
        role = getattr(role_obj, "name", None)

        # Restrict only backup routes; ticket management can be used by non-admin roles if permitted.
        if request.path in self.BACKUP_ONLY_PATHS and role != "ADMINISTRADOR":
            messages.error(request, "No tienes permisos para acceder a esa sección.")
            return redirect("dashboard")

        return self.get_response(request)