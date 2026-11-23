"""Indian mobile numbers, one rule for customer phones and for people's profiles."""
import re


class InvalidPhone(ValueError):
    pass


def normalize(value: str) -> str:
    """'+91XXXXXXXXXX' for any common way of writing a 10-digit Indian mobile number."""
    digits = re.sub(r"[\s\-()]", "", value)
    if digits.startswith("+91"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise InvalidPhone("Enter a 10-digit Indian mobile number.")
    return "+91" + digits
