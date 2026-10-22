"""Public rendering shared by the live site and the offline export.

Every public query lives here so visibility rules (published direction, published
publication, published figure of a published publication) are applied in one place.
"""
from django.db.models import Prefetch, Q
from django.template.loader import render_to_string
from .models import SiteSettings, Page, ResearchDirection, Project, Member, Publication, Resource, Figure


def public_figures():
    return (Figure.objects.filter(is_published=True)
            .filter(Q(publication__isnull=True) | Q(publication__is_published=True))
            .select_related("publication"))


def public_directions():
    return ResearchDirection.objects.filter(is_published=True)


def public_publications():
    return (Publication.objects.filter(is_published=True)
            .prefetch_related(Prefetch("directions", queryset=public_directions())))


def public_projects():
    return Project.objects.filter(is_published=True).prefetch_related(
        Prefetch("directions", queryset=public_directions()))


def website_context(slug):
    site = SiteSettings.objects.get(pk=1)
    order = [key for key, _ in Page.ROUTES]
    pages = sorted(Page.objects.all(), key=lambda page: order.index(page.slug) if page.slug in order else 99)
    current = next(page for page in pages if page.slug == slug)
    members = list(Member.objects.filter(is_published=True))
    resources = list(Resource.objects.filter(is_published=True))
    directions = list(public_directions())
    figures = list(public_figures().prefetch_related("directions"))
    for direction in directions:
        direction.cover = next((f for f in figures if direction in f.directions.all()), None)
    publications = list(public_publications())
    return {
        "site": site, "pages": pages, "page": current, "route": slug,
        "directions": directions,
        "projects": list(public_projects()),
        "publications": publications,
        "publication_years": sorted({p.year for p in publications}, reverse=True),
        "member_groups": [{"id": key, "title": title, "members": [m for m in members if m.group == key]}
                          for key, title in Member.GROUPS],
        "resources": resources,
        "resource_kinds": sorted({r.kind for r in resources}),
        "resource_diseases": sorted({r.disease for r in resources}),
        "leader_paragraphs": [p.strip() for p in site.leader_bio.split("\n\n") if p.strip()],
    }


def direction_context(shared, direction):
    directions = shared["directions"]
    index = directions.index(direction)
    figures = list(public_figures().filter(directions=direction))
    return {**shared, "page": next(p for p in shared["pages"] if p.slug == "research"), "route": "research",
            "direction": direction, "direction_number": index + 1,
            "direction_figures": figures,
            "direction_projects": [p for p in shared["projects"] if direction in p.directions.all()],
            "direction_publications": [p for p in shared["publications"] if direction in p.directions.all()],
            "previous_direction": directions[index - 1] if index > 0 else None,
            "next_direction": directions[index + 1] if index + 1 < len(directions) else None}


def page_manifest(shared=None):
    """All public pages as (file name, template, context). Used by the export and its link check."""
    shared = shared or website_context("index")
    pages = []
    for page in shared["pages"]:
        pages.append((f"{page.slug}.html", f"public/{page.slug}.html", {**shared, "page": page, "route": page.slug}))
    for direction in shared["directions"]:
        pages.append((direction.page_name, "public/direction_detail.html", direction_context(shared, direction)))
    return pages


def render_website(slug, context=None):
    return render_to_string(f"public/{slug}.html", context or website_context(slug))


def render_direction(slug):
    shared = website_context("research")
    direction = next((d for d in shared["directions"] if d.slug == slug), None)
    if direction is None:
        return None
    return render_to_string("public/direction_detail.html", direction_context(shared, direction))
