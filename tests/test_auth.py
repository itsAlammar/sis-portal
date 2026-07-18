"""Authentication, authorization, and password-hashing tests."""

from auth_service import AuthService, hash_password, verify_password


def test_password_hash_roundtrip():
    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong password!", stored)
    assert stored != hash_password("correct horse battery")  # unique salts


def test_authenticate_staff(conn):
    auth = AuthService(conn)
    auth.create_user("alice", "sturdy-password", "registrar")

    assert auth.authenticate("alice", "sturdy-password") is not None
    assert auth.authenticate("ALICE", "sturdy-password") is not None  # case-insensitive name
    assert auth.authenticate("alice", "nope-nope-nope") is None
    assert auth.authenticate("ghost", "sturdy-password") is None


def test_disabled_user_cannot_authenticate(conn):
    auth = AuthService(conn)
    user = auth.create_user("bob", "sturdy-password", "registrar")
    auth.set_user_status(user.user_id, "disabled")
    assert auth.authenticate("bob", "sturdy-password") is None


def test_student_activation_flow(seeded):
    auth = AuthService(seeded["conn"])
    alice = seeded["alice"]

    # No password yet: login fails, activation with the right email works.
    assert auth.authenticate_student(alice.student_number, "anything-here") is None
    assert auth.activate_student(alice.student_number, "wrong@test.edu", "portal-pass-1") is None
    activated = auth.activate_student(alice.student_number, alice.email, "portal-pass-1")
    assert activated is not None

    # Now login works and re-activation is refused.
    assert auth.authenticate_student(alice.student_number, "portal-pass-1") is not None
    assert auth.activate_student(alice.student_number, alice.email, "hijack-attempt") is None

    # Registrar reset clears the password so activation works again.
    auth.set_student_password(alice.student_id, None)
    assert auth.authenticate_student(alice.student_number, "portal-pass-1") is None
    assert auth.activate_student(alice.student_number, alice.email, "new-portal-pw") is not None
