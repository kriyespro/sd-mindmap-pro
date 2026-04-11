from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.views.generic import TemplateView

from users.forms import AppLoginForm, SignUpForm


class LandingView(TemplateView):
    template_name = 'pages/landing.jinja'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('planner:board_personal')
        return super().dispatch(request, *args, **kwargs)


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'pages/auth.jinja'
    success_url = reverse_lazy('planner:board_personal')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('planner:board_personal')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, 'Welcome! Your workspace is ready.')
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_signup'] = True
        return ctx


class AppLoginView(LoginView):
    template_name = 'pages/auth.jinja'
    authentication_form = AppLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('planner:board_personal')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_signup'] = False
        return ctx


class AppLogoutView(LogoutView):
    next_page = reverse_lazy('users:login')
