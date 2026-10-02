"""Fresh functional trace for audit regression checks 2 and 6.

Check 2 : duplicate-email registration vs malformed-input registration
          must be indistinguishable (same status, code, envelope shape).
Check 6 : RegisterView, LoginView, CurrentUserView, ChangeRoleView must
          each return {"success": false, "error": {"code", "message"}}
          for a malformed request (never DRF's raw field-error format).

Run: python scripts/trace_envelope.py
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")

import django

django.setup()

from django.core.cache import cache
from django.test import Client

from apps.accounts.models import User

cache.clear()

BASE = "/api/v1/accounts/"
results = []


def show(label, response):
    body = response.content.decode()
    print(f"--- {label}: HTTP {response.status_code}")
    print(f"    {body}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = None
    if response.status_code < 400:
        # Success responses must use the success envelope instead.
        ok = (
            isinstance(data, dict)
            and data.get("success") is True
            and isinstance(data.get("data"), dict)
        )
    else:
        ok = (
            isinstance(data, dict)
            and data.get("success") is False
            and isinstance(data.get("error"), dict)
            and isinstance(data["error"].get("code"), str)
            and isinstance(data["error"].get("message"), str)
            and set(data.keys()) == {"success", "error"}
            and set(data["error"].keys()) == {"code", "message"}
        )
    results.append((label, response.status_code, ok))
    return response.status_code, data


client = Client()

# ---------- Check 2: duplicate email vs malformed input -------------------
suffix = uuid.uuid4().hex[:8]
email = f"trace.{suffix}@example.com"

baseline = {
    "email": email,
    "username": f"user{suffix}",
    "first_name": "Trace",
    "last_name": "User",
    "password": "Sup3rSecret!1",
}
r = client.post(
    BASE + "register/", json.dumps(baseline), content_type="application/json"
)
show("baseline registration", r)

# Ensure a clean slate if this script is re-run inside the same minute.
User.objects.filter(email=email).delete()
r = client.post(
    BASE + "register/", json.dumps(baseline), content_type="application/json"
)
show("baseline registration (after cleanup)", r)

duplicate = dict(baseline, username=f"other{suffix}")
r_dup = client.post(
    BASE + "register/", json.dumps(duplicate), content_type="application/json"
)
status_dup, data_dup = show("CHECK2 duplicate-email", r_dup)

malformed = dict(baseline, email="not-an-email", username=f"bad{suffix}")
r_bad = client.post(
    BASE + "register/", json.dumps(malformed), content_type="application/json"
)
status_bad, data_bad = show("CHECK2 malformed-input", r_bad)

check2 = (
    status_dup == status_bad == 400
    and data_dup is not None
    and data_bad is not None
    and set(data_dup.keys()) == set(data_bad.keys()) == {"success", "error"}
    and set(data_dup["error"].keys())
    == set(data_bad["error"].keys()) == {"code", "message"}
    and data_dup["error"]["code"] == data_bad["error"]["code"] == "INVALID_DATA"
    and data_dup["success"] is False
    and data_bad["success"] is False
)
print(
    f"\nCHECK2 duplicate vs malformed identical: {check2}\n"
    f"  duplicate status/code : {status_dup} / {data_dup and data_dup['error']['code']}\n"
    f"  malformed status/code : {status_bad} / {data_bad and data_bad['error']['code']}\n"
    f"  duplicate message     : {data_dup and data_dup['error']['message']}\n"
    f"  malformed message     : {data_bad and data_bad['error']['message']}"
)
results.append(("CHECK2 duplicate == malformed (status/code/shape)", 0, check2))

# ---------- Check 6: four views, malformed requests -----------------------
# (a) RegisterView already traced above (CHECK2 malformed-input line).

# (b) LoginView: missing password entirely.
r = client.post(
    BASE + "login/", json.dumps({"identifier": f"user{suffix}"}), content_type="application/json"
)
show("CHECK6 LoginView missing password", r)

# (c) CurrentUserView PATCH: authenticated, blank first_name.
user = User.objects.get(email=email)
client.force_login(user)
r = client.patch(
    BASE + "me/", json.dumps({"first_name": ""}), content_type="application/json"
)
show("CHECK6 CurrentUserView PATCH blank first_name", r)

# (d) ChangeRoleView: authenticated administrator, malformed user_id.
admin = User.objects.create_superuser(
    email=f"trace.admin.{suffix}@example.com",
    username=f"traceadmin{suffix}",
    first_name="Trace",
    last_name="Admin",
    password="Adm1nSecret!1",
)
client.force_login(admin)
r = client.post(
    BASE + "change-role/",
    json.dumps({"user_id": "not-a-uuid", "new_role": "STUDENT"}),
    content_type="application/json",
)
show("CHECK6 ChangeRoleView malformed user_id", r)

# Bonus: invalid role choice (validation error after admin gate).
r = client.post(
    BASE + "change-role/",
    json.dumps({"user_id": str(user.id), "new_role": "WIZARD"}),
    content_type="application/json",
)
show("CHECK6 ChangeRoleView invalid role choice", r)

# ---------- Summary --------------------------------------------------------
print("\n================ SUMMARY ================")
all_ok = True
for label, code, ok in results:
    flag = "OK  " if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  [{flag}] {label}" + (f" (HTTP {code})" if code else ""))
print(f"\nALL PASS: {all_ok}")
sys.exit(0 if all_ok else 1)
