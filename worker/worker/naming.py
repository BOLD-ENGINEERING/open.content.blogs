import re

SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def validate_slug(slug: str) -> None:
    if len(slug) > 58 or not SLUG_PATTERN.fullmatch(slug):
        raise ValueError(
            "slug must be 1-58 lowercase letters, digits or hyphens, without edge hyphens"
        )


def sanitize_branch(branch: str) -> str:
    sanitized = re.sub(r"[^a-z0-9-]", "-", branch.lower()).strip("-")
    if not sanitized:
        raise ValueError("branch must contain at least one letter or digit")
    return sanitized
