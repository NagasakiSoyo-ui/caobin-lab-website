"""PubMed candidate import through the official NCBI E-utilities.

Candidates are a review queue only: nothing here publishes content. Accepting a candidate
creates an unpublished Publication draft; the publication and its figures are released
separately in the admin.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from django.db import transaction
from django.utils import timezone
from .identifiers import normalize_doi, normalize_pmid
from .models import Publication, PubMedCandidate, PubMedImportRun

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
SOURCE = "NCBI PubMed E-utilities (esearch/efetch)"
DEFAULT_TERM = ('Cao Bin[Author] AND ("China-Japan Friendship Hospital"[Affiliation] OR '
                '"National Center for Respiratory Medicine"[Affiliation])')
# Affiliation markers of Prof. Cao Bin's group. A "Cao B" author without one of these is
# kept as "unmatched" so namesakes are never treated as group papers automatically.
AFFILIATION_MARKERS = ("china-japan friendship hospital", "national center for respiratory medicine",
                       "national clinical research center for respiratory diseases", "caobin_ben@163.com")
COMPARED_FIELDS = ("title", "journal", "year", "citation", "doi", "authors")


class ImportFailure(Exception):
    pass


def _get(endpoint, params):
    params = {**params, "tool": "caobin_lab_site"}
    if os.environ.get("LAB_NCBI_EMAIL"):
        params["email"] = os.environ["LAB_NCBI_EMAIL"]
    url = EUTILS + endpoint + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read()
    except OSError as exc:
        raise ImportFailure(f"无法连接 NCBI：{exc}") from exc


def search(term, retmax=50):
    data = json.loads(_get("esearch.fcgi", {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json"}))
    if "esearchresult" not in data or "ERROR" in data["esearchresult"]:
        raise ImportFailure(f"PubMed 检索返回错误：{data}")
    return data["esearchresult"].get("idlist", [])


def fetch(pmids):
    time.sleep(0.4)  # NCBI allows three requests per second without an API key.
    return _get("efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})


def _text(node):
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip() if node is not None else ""


def parse(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ImportFailure(f"PubMed 返回的 XML 无法解析：{exc}") from exc
    records = []
    for article in root.findall("PubmedArticle"):
        citation = article.find("MedlineCitation")
        body = citation.find("Article")
        journal = body.find("Journal")
        ids = {node.get("IdType"): (node.text or "").strip() for node in article.findall("PubmedData/ArticleIdList/ArticleId")}
        authors, evidence, matched = [], [], False
        author_nodes = body.findall("AuthorList/Author")
        for index, author in enumerate(author_nodes, 1):
            last, fore = author.findtext("LastName") or "", author.findtext("ForeName") or ""
            initials = author.findtext("Initials") or ""
            name = f"{last} {initials}".strip() if last else (author.findtext("CollectiveName") or "")
            authors.append(name)
            if last == "Cao" and fore in ("Bin", "B"):
                affiliations = [_text(node) for node in author.findall("AffiliationInfo/Affiliation")]
                hit = any(marker in a.lower() for a in affiliations for marker in AFFILIATION_MARKERS)
                matched = matched or hit
                evidence.append(f"作者位置 {index}/{len(author_nodes)}：{last} {fore}；单位{'匹配' if hit else '未匹配'}："
                                + ("；".join(affiliations) or "PubMed 未提供该作者单位"))
        year = journal.findtext("JournalIssue/PubDate/Year") or (journal.findtext("JournalIssue/PubDate/MedlineDate") or "")[:4]
        issue = journal.find("JournalIssue")
        volume, number = issue.findtext("Volume") or "", issue.findtext("Issue") or ""
        pages = body.findtext("Pagination/MedlinePgn") or ""
        if not pages:
            pages = next((_text(n) for n in body.findall("ELocationID") if n.get("EIdType") == "doi"), "")
            pages = "" if pages.lower() == ids.get("doi", "").lower() else pages
        cite = volume + (f"({number})" if number else "") + (f":{pages}" if pages else "")
        records.append({
            "pmid": normalize_pmid(citation.findtext("PMID")),
            "doi": normalize_doi(ids.get("doi")) or "",
            "pmcid": ids.get("pmc", ""),
            "title": _text(body.find("ArticleTitle")).rstrip("."),
            "authors": ", ".join(authors),
            "journal": journal.findtext("ISOAbbreviation") or journal.findtext("Title") or "",
            "year": int(year) if year.isdigit() else None,
            "citation": cite,
            "abstract": " ".join(_text(node) for node in body.findall("Abstract/AbstractText")),
            "publication_types": "; ".join(_text(node) for node in body.findall("PublicationTypeList/PublicationType")),
            "identity_status": "matched" if matched else "unmatched",
            "identity_evidence": "\n".join(evidence) or "作者列表中未找到 Cao Bin。",
        })
    return records


def find_conflict(pmid, doi):
    """Return (publication, conflict message). Never merges two different publications."""
    by_pmid = Publication.objects.filter(pmid=pmid).first() if pmid else None
    by_doi = Publication.objects.filter(doi=normalize_doi(doi)).first() if doi else None
    if by_pmid and by_doi and by_pmid.pk != by_doi.pk:
        return None, (f"冲突：PMID {pmid} 对应成果 #{by_pmid.pk}《{by_pmid.title[:40]}》，"
                      f"DOI {doi} 对应另一成果 #{by_doi.pk}《{by_doi.title[:40]}》。未自动合并，请人工核对。")
    match = by_pmid or by_doi
    if match and pmid and match.pmid and match.pmid != pmid:
        return None, f"冲突：DOI {doi} 已属于 PMID {match.pmid} 的成果 #{match.pk}，与本记录 PMID {pmid} 不一致。"
    if match and doi and match.doi and match.doi != normalize_doi(doi):
        return None, f"冲突：PMID {pmid} 已属于 DOI {match.doi} 的成果 #{match.pk}，与本记录 DOI {doi} 不一致。"
    return match, ""


def _diff(candidate, publication):
    changes = []
    for field in COMPARED_FIELDS:
        new, old = getattr(candidate, field), getattr(publication, field)
        if (str(new or "").strip() != str(old or "").strip()) and new not in ("", None):
            changes.append(f"{field}: 成果为「{old}」，PubMed 现为「{new}」")
    return "\n".join(changes)


@transaction.atomic
def store(records, query):
    """Create or refresh candidates. Review decisions and linked publications stay untouched."""
    created = updated = 0
    now = timezone.now()
    for record in records:
        candidate = PubMedCandidate.objects.filter(pmid=record["pmid"]).first()
        if candidate is None:
            candidate = PubMedCandidate(pmid=record["pmid"])
            created += 1
        else:
            updated += 1
        for field, value in record.items():
            setattr(candidate, field, value)
        candidate.query, candidate.retrieved_at = query, now
        match, candidate.conflict = find_conflict(candidate.pmid, candidate.doi)
        if candidate.publication_id:
            candidate.upstream_changes = _diff(candidate, candidate.publication)
        elif match and candidate.decision == "pending":
            candidate.decision_note = candidate.decision_note or f"已有成果 #{match.pk} 与该记录 PMID/DOI 一致。"
        if candidate.pk:
            candidate.version += 1
        candidate.save()
    return created, updated


def run_import(term=None, pmids=None, retmax=50):
    """Fetch PubMed and store candidates. Every run is logged; failures and empty results raise."""
    query = f"PMID: {','.join(pmids)}" if pmids else (term or DEFAULT_TERM)
    run = PubMedImportRun.objects.create(query=query)
    try:
        ids = [normalize_pmid(p) for p in pmids] if pmids else search(term or DEFAULT_TERM, retmax)
        if not ids:
            run.status, run.message = "empty", "检索结果为空，未创建任何候选。请检查检索式。"
            raise ImportFailure(run.message)
        records = parse(fetch(ids))
        missing = sorted(set(ids) - {r["pmid"] for r in records})
        if not records:
            run.status, run.message = "empty", f"PubMed 未返回任何记录：{','.join(ids)}"
            raise ImportFailure(run.message)
        run.found = len(records)
        run.created, run.updated = store(records, f"{SOURCE}；{query}")
        run.status = "ok"
        run.message = f"未返回的 PMID：{','.join(missing)}" if missing else ""
        return run
    except ImportFailure as exc:
        if run.status != "empty":
            run.status, run.message = "failed", str(exc)
        raise
    except Exception as exc:
        run.status, run.message = "failed", f"{type(exc).__name__}: {exc}"
        raise ImportFailure(run.message) from exc
    finally:
        run.finished_at = timezone.now()
        run.save()


@transaction.atomic
def accept(candidate, user=None):
    """Turn a reviewed candidate into an unpublished Publication draft (or link an existing one)."""
    candidate = PubMedCandidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.decision == "rejected":
        raise ImportFailure(f"PMID {candidate.pmid} 已标记为不纳入，未导入。")
    match, conflict = find_conflict(candidate.pmid, candidate.doi)
    if conflict:
        candidate.conflict = conflict
        candidate.save(update_fields=["conflict"])
        raise ImportFailure(conflict)
    publication = candidate.publication or match
    if publication is None:
        publication = Publication.objects.create(
            kind="paper", title=candidate.title, authors=candidate.authors, year=candidate.year or timezone.now().year,
            journal=candidate.journal, citation=candidate.citation, pmid=candidate.pmid, doi=candidate.doi or None,
            pmcid=candidate.pmcid, url=f"https://pubmed.ncbi.nlm.nih.gov/{candidate.pmid}/", is_published=False,
            source_note=(f"来源：{candidate.query}\n检索时间：{candidate.retrieved_at:%Y-%m-%d %H:%M}\n"
                         f"身份判断：{candidate.get_identity_status_display()}\n{candidate.identity_evidence}"))
    else:
        # Fill identifiers only when empty; manual text, slug and publish state are kept.
        changed = []
        for field in ("pmid", "doi", "pmcid"):
            if not getattr(publication, field) and getattr(candidate, field):
                setattr(publication, field, getattr(candidate, field))
                changed.append(field)
        if changed:
            publication.version += 1
            publication.save()
    candidate.publication, candidate.decision, candidate.conflict = publication, "accepted", ""
    candidate.decided_by, candidate.decided_at = user, timezone.now()
    candidate.version += 1
    candidate.save()
    return publication
