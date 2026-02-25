# Bcrypt Password Hashing Bug Fix

## Problem

Users were unable to sign up for Open WebUI, receiving an error:
```
password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72])
```

This error occurred even with short passwords like "1234" (4 bytes).

## Root Cause

The `passlib` library's `CryptContext` wrapper around bcrypt was incorrectly validating password length. The validation check was triggering erroneously, reporting that a 4-byte password exceeded the 72-byte bcrypt limit.

**Debug evidence:**
```
DEBUG get_password_hash: input password length = 4, bytes = 4
DEBUG get_password_hash: truncated password length = 4, bytes = 4
ERROR: password cannot be longer than 72 bytes
```

The password was clearly only 4 bytes, but the passlib library still threw the error during `pwd_context.hash()`.

## Solution

Bypassed the buggy passlib wrapper and used the `bcrypt` library directly.

### Code Changes

**File:** `/front/backend/open_webui/utils/auth.py`

**Before:**
```python
def get_password_hash(password):
    return pwd_context.hash(password)
```

**After:**
```python
def get_password_hash(password):
    # Bcrypt has a 72 byte limit - work around library bug by passing bytes directly
    password_bytes = password.encode('utf-8')[:72]
    
    # Use bcrypt directly instead of through passlib to avoid validation bug
    import bcrypt
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    result = hashed.decode('utf-8')
    
    return result
```

### Why This Works

1. **Direct byte handling:** Converts password to bytes and truncates at 72 bytes (the bcrypt limit)
2. **Bypasses passlib:** Goes directly to bcrypt library, avoiding the buggy validation
3. **Standard bcrypt format:** Output is still a standard bcrypt hash compatible with existing verification code
4. **Maintains security:** Still uses proper salting and bcrypt hashing

## Impact

- ✅ User signup now works with any password length
- ✅ Passwords are properly truncated to 72 bytes before hashing
- ✅ Existing password verification still works (passlib can verify bcrypt hashes)
- ✅ No data migration needed
- ✅ Maintains full security standards

## Testing

Tested with:
- Short password: "1234" ✅ Works
- Medium password: 20-30 characters ✅ Works
- Long password: 100+ characters ✅ Works (truncated to 72 bytes)

## Date Fixed

February 11, 2026
