"""Shared identifier rules: DOI/PMID normalization and stable page slugs."""
import re
from django.utils.text import slugify

DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)


def normalize_doi(value):
    value = DOI_PREFIX.sub("", (value or "").strip()).strip().rstrip(".")
    return value.lower() or None


def normalize_pmid(value):
    value = (value or "").strip()
    if not value:
        return None
    if not value.isdigit():
        raise ValueError(f"PMID 只能是数字：{value}")
    return str(int(value))


def unique_slug(model, base, instance_pk=None, max_length=80):
    base = (slugify(base)[:max_length - 8].strip("-") or "item")
    candidate, number = base, 2
    while model.objects.filter(slug=candidate).exclude(pk=instance_pk).exists():
        candidate, number = f"{base}-{number}", number + 1
    return candidate
