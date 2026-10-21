from django.core.management.base import BaseCommand, CommandError
from catalog.pubmed import DEFAULT_TERM, ImportFailure, run_import


class Command(BaseCommand):
    help = "从 PubMed 检索论文，写入后台「PubMed 候选」待人工审核。不会自动发布，也不覆盖已有成果。"

    def add_arguments(self, parser):
        parser.add_argument("--pmid", nargs="+", help="按 PMID 导入，例如 --pmid 38231624 40858544")
        parser.add_argument("--term", help=f"PubMed 检索式，默认：{DEFAULT_TERM}")
        parser.add_argument("--retmax", type=int, default=50, help="检索式最多返回条数，默认 50。")

    def handle(self, *args, **options):
        try:
            run = run_import(term=options["term"], pmids=options["pmid"], retmax=options["retmax"])
        except (ImportFailure, ValueError) as exc:
            raise CommandError(f"PubMed 导入未完成：{exc}（已记录在后台「PubMed 导入记录」）")
        self.stdout.write(self.style.SUCCESS(
            f"PubMed 返回 {run.found} 条：新增候选 {run.created}，刷新 {run.updated}。请在后台「PubMed 候选」审核。"))
        if run.message:
            self.stdout.write(self.style.WARNING(run.message))
