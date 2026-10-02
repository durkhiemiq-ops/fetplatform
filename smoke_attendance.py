"""End-to-end smoke test against the LIVE dev server (must be running on :8000).

Covers exact the flows Attendî will exercise:
  1. Lecturer login -> create session -> select checkpoint -> issue token
  2. Student login (by matricule) -> scan -> replay -> cross-student scan
  3. Milestone round-trip on the demo project
Uses only stdlib. Run: python smoke_attendance.py
"""

import json
import sys
import urllib.request
from http.cookiejar import CookieJar

BASE = "http://localhost:8000/api/v1"


def make_client():
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener


def call(opener, method, path, payload=None):
    csrf = None
    for c in opener.handlers and [] or []:
        pass
    # find csrftoken cookie
    host = "localhost"
    for cookie in []:  # placeholder
        pass
    # Simpler: read csrf from opener's cookiejar attribute
    cj = None
    for h in opener.handlers:
        pass
    # Actually extract from HTTPCookieProcessor's cookiejar
    for cookie in opener._handlers[1].__dict__.get('cookielib', None) or []:
        pass
    return None


class API:
    def __init__(self):
        self.cj = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def _csrf(self):
        for cookie in self.cj:
            if cookie.name == "csrftoken":
                return cookie.value
        return None

    def request(self, method, path, payload=None):
        url = f"{BASE}{path}"
        headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        if method != "GET" and self._csrf():
            headers["X-CSRFToken"] = self._csrf()
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def login(self, identifier, password):
        status, _ = self.request("GET", "/accounts/csrf/")
        assert status == 200
        status, body = self.request("POST", "/accounts/login/", {"identifier": identifier, "password": password})
        assert status == 200 and body.get("success"), f"login failed: {body}"
        return body["data"]


def main():
    print("== lecturer login ==")
    lec = API()
    me = lec.login("alida.vance@fet.edu", "lecturer123")
    assert me["role"] == "LECTURER"
    print("  ok:", me["email"])

    status, body = lec.request("GET", "/academic/classes/")
    assert status == 200
    classes = body["data"]
    assert classes, "no class sessions seeded"
    # Pick the first class whose course actually has enrollments.
    cs = next(c for c in classes if c["course_code"] == "CEF444")
    print("  class:", cs["course_code"], cs["id"])

    print("== start session, select checkpoint, issue token ==")
    status, body = lec.request("POST", "/attendance/sessions/", {"class_session": cs["id"], "duration_seconds": 120})
    assert status == 201, body
    session = body["data"]
    print("  session:", session["id"], session["status"])

    status, body = lec.request("GET", f"/attendance/sessions/{session['id']}/")
    eligible = body["data"]["eligible_students"]
    print("  eligible:", [f"{s['first_name']} {s['last_name']}" for s in eligible])
    assert len(eligible) >= 2

    status, body = lec.request("POST", f"/attendance/sessions/{session['id']}/checkpoints/", {"student_ids": [s["id"] for s in eligible]})
    assert status == 201, body
    cks = body["data"]["checkpoints"]
    print("  checkpoints:", len(cks))

    # Log alex in BEFORE issuing the token — the token TTL is 10s and
    # first login (password hashing) can exceed that on a slow machine.
    print("== student alex logs in, then scans ==")
    alex = API()
    me = alex.login("FE24A389", "student123")
    assert me["role"] == "STUDENT"

    status, body = lec.request("POST", f"/attendance/checkpoints/{cks[0]['id']}/token/")
    assert status == 201, body
    token = body["data"]["token"]
    print("  token ttl:", body["data"]["ttl_seconds"])

    status, body = alex.request("POST", "/attendance/scan/", {"token": token})
    assert status == 201, body
    print("  marked:", body["data"]["attendance_record_id"])

    print("== replay ==")
    status, body = alex.request("POST", "/attendance/scan/", {"token": token})
    assert status in (409, 404), body
    print("  replay ->", body["error"]["code"])

    print("== emma (not alex's checkpoint) cannot scan alex's token ==")
    emma = API()
    emma.login("FE24B456", "student123")
    status, body = lec.request("POST", f"/attendance/checkpoints/{cks[0]['id']}/token/")
    token2 = body["data"]["token"]
    status, body = emma.request("POST", "/attendance/scan/", {"token": token2})
    assert status == 403 and body["error"]["code"] == "TOKEN_STUDENT_MISMATCH", body
    print("  mismatch ->", body["error"]["code"])

    print("== milestones round-trip ==")
    status, body = lec.request("GET", "/projects/")
    proj = body["data"][0]
    status, body = lec.request("POST", f"/projects/{proj['id']}/milestones/", {"title": "Smoke milestone", "progress": 10})
    assert status == 201, body
    mid = body["data"]["id"]
    status, body = lec.request("PATCH", f"/projects/milestones/{mid}/", {"progress": 100})
    assert status == 200 and body["data"]["progress"] == 100, body
    status, body = lec.request("DELETE", f"/projects/milestones/{mid}/")
    assert status == 200, body
    print("  milestone crud ok")

    print("\nALL SMOKE PASSED")


if __name__ == "__main__":
    main()
