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
    try:
        with pyzipper.AESZipFile(
            test_zip, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
        ) as zf:
            zf.setpassword(pwd)
            zf.writestr("secret.txt", b"This is a highly confidential document.")
        print("Created test_encrypted.zip with password 'secret!'")

        # 1. Test Detection
        encrypted = is_encrypted(test_zip)
        print(f"Is test_encrypted.zip encrypted? {encrypted}")
        assert encrypted is True, f"Failed to detect zip encryption on {test_zip}"

        # 2. Test Unlocking Failure
        print("\n--- Testing Unlock (Wrong Password) ---")
        success_wrong = unlock_document(test_zip, "wrongpass")
        print(f"Did it unlock with wrong password? {success_wrong}")
        assert success_wrong is False, f"Unlocked wrong password on {test_zip}"

        # 3. Test Unlocking Success
        print("\n--- Testing Unlock (Correct Password) ---")
        success_right = unlock_document(test_zip, "secret!")
        print(f"Did it unlock with correct password? {success_right}")
        assert success_right is True, f"Could not unlock {test_zip}"

        # 4. Verify Final State
        encrypted_after = is_encrypted(test_zip)
        print(f"Is test_encrypted.zip encrypted after unlock? {encrypted_after}")
        assert encrypted_after is False, f"File {test_zip} still marked as encrypted after unlock"

        print("\n✅ Generic Security utilities are functioning perfectly.")
    finally:
        # Cleanup
        if test_zip.exists():
            test_zip.unlink()


if __name__ == "__main__":
    test_generic_encryption()
