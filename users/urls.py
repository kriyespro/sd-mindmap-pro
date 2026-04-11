from django.urls import path

from users.views import AppLoginView, AppLogoutView, SignUpView

app_name = 'users'

urlpatterns = [
    path('login/', AppLoginView.as_view(), name='login'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('logout/', AppLogoutView.as_view(), name='logout'),
]
