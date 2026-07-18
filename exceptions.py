"""Custom exceptions for the Student Information System.

Centralizing these lets any interface (CLI today, maybe a REST API later)
catch SISError broadly for a friendly message, or catch a specific
subclass for tailored handling.
"""


class SISError(Exception):
    """Base class for all business-logic errors raised by the system."""


class NotFoundError(SISError):
    """Raised when a requested record does not exist."""


class ValidationError(SISError):
    """Raised when input fails a business rule (bad format, bad range, etc.)."""


class DuplicateError(SISError):
    """Raised when a uniqueness constraint would be violated."""


class EnrollmentError(SISError):
    """Base class for enrollment-specific failures."""


class CapacityError(EnrollmentError):
    """Raised when a section is already at capacity."""


class PrerequisiteError(EnrollmentError):
    """Raised when a student has not completed a required prerequisite."""


class ScheduleConflictError(EnrollmentError):
    """Raised when two sections overlap in day/time for the same student."""


class DeadlineError(EnrollmentError):
    """Raised when an add/drop deadline for the term has already passed."""


class DuplicateEnrollmentError(EnrollmentError):
    """Raised when a student is already enrolled in a section."""


class PaymentError(SISError):
    """Raised for invalid payment amounts or states."""
