from django.shortcuts import redirect

def staff_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper
