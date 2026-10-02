"""Root URLconf import and route-surface regression guard.

Why this file exists
--------------------
``config/urls.py`` imports ``apps.accounts.auth_alias_urls`` at the top level
of the root URLconf. That module was, at one point, untracked in git while
still being imported. The failure mode was catastrophic and silent: a fresh
clone or a CI runner raised ``ModuleNotFoundError`` during ``django.setup()``,
so *every* endpoint disappeared rather than just the ``/api/v1/auth/*`` ones.

Nothing in the suite caught it, because no test imported the root URLconf. This
module does.

Run with::

    python manage.py test core.tests_urlconf --settings=config.settings_test
"""

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, get_resolver, reverse


def _api_patterns(resolver=None, prefix=""):
    """Flatten every concrete pattern under ``/api/v1``."""
    resolver = resolver or get_resolver()
    found = []
    for entry in resolver.url_patterns:
        if hasattr(entry, "url_patterns"):
            found.extend(_api_patterns(entry, prefix + str(entry.pattern)))
        else:
            full = "/" + prefix
            if "api/v1" in full:
                found.append(full)
    return found


class RootUrlconfImportTests(SimpleTestCase):
    """The URLconf must import cleanly and expose the documented surface."""

    def test_root_urlconf_imports(self):
        """A missing urlconf module must fail here, not during django.setup()."""
        import config.urls  # noqa: F401

        self.assertTrue(
            getattr(config.urls, "urlpatterns", None),
            "config.urls must define a non-empty urlpatterns list",
        )

    def test_auth_alias_urlconf_module_is_importable(self):
        """Direct guard for the outage described in this module's docstring.

        ``config/urls.py`` mounts ``api/v1/auth/`` from this module. If it is
        deleted, renamed, or left untracked, this test fails loudly instead of
        the whole application failing to boot.
        """
        import apps.accounts.auth_alias_urls as alias

        self.assertTrue(
            getattr(alias, "urlpatterns", None),
            "apps.accounts.auth_alias_urls must define urlpatterns",
        )
        names = {p.name for p in alias.urlpatterns if p.name}
        expected = {
            "auth-login",
            "auth-logout",
            "auth-me",
            "auth-register",
            "auth-self-register",
            "auth-verify-email",
            "auth-change-password",
            "auth-refresh",
        }
        self.assertEqual(
            expected - names,
            set(),
            f"auth alias routes missing; found {sorted(names)}",
        )

    def test_api_surface_has_not_shrunk(self):
        """Guard the route count.

        The live resolver currently exposes 54 concrete patterns under
        ``/api/v1`` (including the eight auth aliases). This is a floor, not an
        exact figure: Wave 1 adds flat routes and intentionally keeps the old
        prefixed paths as temporary aliases, so the number should only ever
        grow. A drop means something was unmounted by accident.
        """
        patterns = _api_patterns()
        self.assertGreaterEqual(
            len(patterns),
            54,
            f"API route surface shrank: {len(patterns)} patterns under /api/v1",
        )
        # Distinct namespaces we must never lose wholesale.
        for required in (
            "/api/v1/accounts/",
            "/api/v1/auth/",
            "/api/v1/attendance/",
            "/api/v1/academic/",
            "/api/v1/announcements/",
            "/api/v1/assessments/",
            "/api/v1/projects/",
            "/api/v1/notifications/",
        ):
            self.assertIn(
                required,
                patterns,
                f"namespace missing from the URLconf: {required}",
            )

    def test_key_named_routes_reverse(self):
        """Named routes must resolve, or reverse() in views/tests raises 500."""
        checks = {
            "accounts:csrf_token": "/api/v1/accounts/csrf/",
            "accounts:login": "/api/v1/accounts/login/",
            "accounts:logout": "/api/v1/accounts/logout/",
            "accounts:current-user": "/api/v1/accounts/me/",
            "accounts:change-role": "/api/v1/accounts/change-role/",
            "accounts:register": "/api/v1/accounts/register/",
            "auth-login": "/api/v1/auth/login/",
            "auth-me": "/api/v1/auth/me/",
            "auth-change-password": "/api/v1/auth/change-password/",
            "auth-refresh": "/api/v1/auth/refresh/",
        }
        for name, expected in checks.items():
            with self.subTest(route=name):
                try:
                    self.assertEqual(reverse(name), expected)
                except NoReverseMatch as exc:  # pragma: no cover - failure path
                    self.fail(f"reverse({name!r}) failed: {exc}")

    def test_health_probe_reaches_the_api(self):
        """The ``/api/v1/`` prefix itself must not 404 the whole surface."""
        response = self.client.get("/api/v1/accounts/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("success"))