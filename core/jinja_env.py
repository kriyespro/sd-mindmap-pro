import json

from jinja2 import Environment
from django.templatetags.static import static
from django.urls import reverse
from markupsafe import Markup


def _url(viewname, **kwargs):
    """Jinja-friendly reverse: {{ url('name', id=x) }} → kwargs passed to reverse()."""
    if kwargs:
        return reverse(viewname, kwargs=kwargs)
    return reverse(viewname)


def environment(**options):
    env = Environment(**options)
    env.globals.update(
        {
            'static': static,
            'url': _url,
        }
    )
    env.filters['tojson'] = lambda v: Markup(json.dumps(v))
    return env
