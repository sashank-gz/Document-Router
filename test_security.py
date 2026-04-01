import logging
from pathlib import Path

import pyzipper

from app.security_utils import is_encrypted, unlock_document

logging.basicConfig(level=logging.INFO)


def test_generic_encryption():
    # Construct an encrypted zip file
    test_zip = Path("test_encrypted.zip")
    pwd = b"secret!"

    print("\n--- Creating Encrypted ZIP ---")
    with pyzipper.AESZipFile(
        test_zip, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(pwd)
        zf.writestr("secret.txt", b"This is a highly confidential document.")
    print("Created test_encrypted.zip with password 'secret!'")

    # 1. Test Detection
    encrypted = is_encrypted(test_zip)
    print(f"Is test_encrypted.zip encrypted? {encrypted}")

    if not encrypted:
        print("❌ FAILED: Did not detect zip encryption!")
        return

    # 2. Test Unlocking Failure
    print("\n--- Testing Unlock (Wrong Password) ---")
    success_wrong = unlock_document(test_zip, "wrongpass")
    print(f"Did it unlock with wrong password? {success_wrong}")
    if success_wrong:
        print("❌ FAILED: Unlocked with wrong password!")
        return

    # 3. Test Unlocking Success
    print("\n--- Testing Unlock (Correct Password) ---")
    success_right = unlock_document(test_zip, "secret!")
    print(f"Did it unlock with correct password? {success_right}")

    if not success_right:
        print("❌ FAILED: Could not unlock with correct password!")
        return

    # 4. Verify Final State
    encrypted_after = is_encrypted(test_zip)
    print(f"Is test_encrypted.zip encrypted after unlock? {encrypted_after}")

    if encrypted_after:
        print("❌ FAILED: File still marked as encrypted after unlock!")
        return

    print("\n✅ Generic Security utilities are functioning perfectly.")

    # Cleanup
    if test_zip.exists():
        test_zip.unlink()


if __name__ == "__main__":
    test_generic_encryption()
