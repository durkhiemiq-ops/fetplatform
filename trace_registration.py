import os
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings_dev')
django.setup()

from django.contrib.auth import get_user_model
from apps.accounts.services.auth_service import register_account, DuplicateAccountError, AuthError
from apps.accounts.serializers import RegisterSerializer

print("=== TRACING ACCOUNT REGISTRATION REQUEST ===")
print()

# Step 1: Request data (simulating HTTP request body)
request_data = {
    "email": "test@example.com",
    "username": "testuser",
    "first_name": "Test",
    "last_name": "User",
    "password": "SecurePass123!"
}
print("Step 1: Request data received")
print(f"  Data: {request_data}")
print()

# Step 2: Serializer validation
print("Step 2: Serializer validation")
serializer = RegisterSerializer(data=request_data)
try:
    serializer.is_valid(raise_exception=True)
    validated_data = serializer.validated_data
    print("  [+] Validation passed")
    print(f"  Validated data: {validated_data}")
except Exception as e:
    print(f"  [-] Validation failed: {e}")
    exit(1)
print()

# Step 3: Service call
print("Step 3: Calling register_account service")
try:
    account = register_account(
        email=validated_data["email"],
        username=validated_data["username"],
        first_name=validated_data["first_name"],
        last_name=validated_data["last_name"],
        password=validated_data["password"],
        AccountModel=get_user_model()
    )
    print("  [+] Service call succeeded")
    print(f"  Account created: {account.email} ({account.username})")
    print(f"  Account ID: {account.id}")
    print(f"  Account role: {account.role}")
    print(f"  Account is_active: {account.is_active}")
except DuplicateAccountError as e:
    print(f"  [-] Duplicate account error: {e}")
    exit(1)
except AuthError as e:
    print(f"  [-] Auth error: {e}")
    exit(1)
except Exception as e:
    print(f"  [-] Unexpected error: {e}")
    exit(1)
print()

# Step 4: Response preparation (simulating view response)
print("Step 4: Preparing response")
from apps.accounts.serializers import UserSerializer
response_data = {
    "success": True,
    "data": UserSerializer(account).data
}
print("  [+] Response prepared")
print(f"  Response: {response_data}")
print()

print("=== REQUEST TRACE COMPLETE ===")