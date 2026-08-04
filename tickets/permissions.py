def has_permission(user, module, action):

    if not user.is_authenticated:
        return False

    profile = getattr(user, "profile", None)

    if not profile or not profile.role:
        return False

    return profile.role.permissions.filter(
        module=module,
        action=action
    ).exists()
    
from django.shortcuts import redirect

def permission_required(permission_code):

    def decorator(view_func):

        def wrapper(request, *args, **kwargs):

            if not has_permission(request.user, permission_code):
                return redirect("dashboard")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator