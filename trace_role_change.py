import os
import django
import random
import string
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_dev')
django.setup()

from django.contrib.auth import get_user_model
from apps.accounts.services.auth_service import register_account, change_user_role, SelfRoleAssignmentError, UnauthorizedRoleChangeError, InvalidRoleError
from core.academic_access import ADMIN_ROLES, normalize_role
from apps.accounts.serializers import ChangeRoleSerializer, UserSerializer

def random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))

print("=== TRACING ROLE CHANGE REQUEST ===")
print()

# Setup: Create test users
print("Setup: Creating test users")
# Create a regular user (target)
target_email = f"target.{random_string()}@example.com"
target_username = f"targetuser{random_string()}"
target_user = register_account(
    email=target_email,
    username=target_username,
    first_name="Target",
    last_name="User",
    password="SecurePass123!",
    AccountModel=get_user_model()
)
print(f"  Target user: {target_user.email} (ID: {target_user.id}, Role: {target_user.role})")

# Create an admin user (actor)
admin_email = f"admin.{random_string()}@example.com"
admin_username = f"adminuser{random_string()}"
admin_user = register_account(
    email=admin_email,
    username=admin_username,
    first_name="Admin",
    last_name="User",
    password="SecurePass123!",
    AccountModel=get_user_model()
)
# Make the admin user an administrator
admin_user.role = "ADMINISTRATOR"
admin_user.save()
print(f"  Admin user: {admin_user.email} (ID: {admin_user.id}, Role: {admin_user.role})")
print()

# Step 1: Request data (simulating HTTP request body)
request_data = {
    "user_id": str(target_user.id),
    "new_role": "LECTURER"
}
print("Step 1: Request data received")
print(f"  Data: {request_data}")
print()

# Step 2: Serializer validation
print("Step 2: Serializer validation")
serializer = ChangeRoleSerializer(data=request_data)
try:
    serializer.is_valid(raise_exception=True)
    validated_data = serializer.validated_data
    print("  [+] Validation passed")
    print(f"  Validated data: {validated_data}")
except Exception as e:
    print(f"  [-] Validation failed: {e}")
    exit(1)
print()

# Store the role before the service call for accurate reporting
target_user_role_before = target_user.role

# Step 3: Service call
print("Step 3: Calling change_user_role service")
try:
    updated_account = change_user_role(
        account=target_user,
        new_role=validated_data["new_role"],
        actor=admin_user
    )
    print("  [+] Service call succeeded")
    print(f"  Account role changed from '{target_user_role_before}' to '{updated_account.role}'")
    print(f"  Account ID: {updated_account.id}")
    print(f"  Account email: {updated_account.email}")
except SelfRoleAssignmentError as e:
    print(f"  [-] Self role assignment error: {e}")
    exit(1)
except UnauthorizedRoleChangeError as e:
    print(f"  [-] Unauthorized role change error: {e}")
    exit(1)
except InvalidRoleError as e:
    print(f"  [-] Invalid role error: {e}")
    exit(1)
except Exception as e:
    print(f"  [-] Unexpected error: {e}")
    exit(1)
print()

# Step 4: Response preparation (simulating view response)
print("Step 4: Preparing response")
response_data = {
    "success": True,
    "data": UserSerializer(updated_account).data
}
print("  [+] Response prepared")
print(f"  Response: {response_data}")
print()

print("=== REQUEST TRACE COMPLETE ===")