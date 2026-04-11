"""Small core views (health checks, etc.)."""

from django.http import HttpResponse


def health(request):
    """Liveness/readiness for orchestrators and Docker healthchecks."""
    return HttpResponse('ok', content_type='text/plain')
