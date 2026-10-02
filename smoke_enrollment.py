"""Verify the new enrollment endpoints end-to-end against a live server.

Read-only apart from enroll/drop on the seeded demo students, which is the
intended behaviour being verified. Run with the dev server on :8000.
"""

import json
import urllib.error
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


ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}: got {got}, want {want}")


api = API()
api.req("GET", "/accounts/csrf/")
st, body = api.req("POST", "/accounts/login/", {"identifier": "FE24B456", "password": "student123"})
assert st == 200, body

st, courses = api.req("GET", "/academic/courses/")
by_code = {c["code"]: c["id"] for c in courses["data"]}

print("== GET own enrollments ==")
st, body = api.req("GET", "/academic/enrollments/")
check("status", st, 200)
check("own active enrollments", len(body["data"]), 4)
check("peer courses absent", any(c["course"] == by_code["ME301"] for c in body["data"]), False)

print("== duplicate enrol -> conflict ==")
st, body = api.req("POST", "/academic/enrollments/", {"course": by_code["CEF444"]})
check("status", st, 409)
check("code", body["error"]["code"], "ALREADY_ENROLLED")

print("== forged role field rejected ==")
st, body = api.req("POST", "/academic/enrollments/", {"course": by_code["SE401"], "role": "ADMINISTRATOR"})
check("status", st, 400)

print("== enrol a new course ==")
st, body = api.req("POST", "/academic/enrollments/", {"course": by_code["SE401"]})
check("status", st, 201)
check("is_active", body["data"]["is_active"], True)

st, body = api.req("GET", "/academic/enrollments/")
check("now 5 enrollments", len(body["data"]), 5)

print("== drop it (deactivates, does not delete) ==")
st, body = api.req("DELETE", f"/academic/enrollments/{by_code['SE401']}/")
check("status", st, 200)
check("is_active", body["data"]["is_active"], False)

st, body = api.req("GET", "/academic/enrollments/")
check("back to 4 active", len(body["data"]), 4)

print("== forged ?student= as a student -> forbidden ==")
st, body = api.req("DELETE", f"/academic/enrollments/{by_code['CEF444']}/?student=00000000-0000-0000-0000-000000000000")
check("status", st, 403)

print("== drop a course we are not in -> not found ==")
st, body = api.req("DELETE", f"/academic/enrollments/{by_code['ME301']}/")
check("status", st, 404)

print("\n" + ("ALL ENROLLMENT CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
raise SystemExit(0 if ok else 1)
