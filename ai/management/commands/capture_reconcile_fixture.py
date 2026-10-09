"""
Turn a raw Reconcile trace (AI_TRACE_DIR/<execution id>/) into a replay
regression fixture: one file per provider step, keeping the output and -- for
the stages replayed by the work they ask for -- the distilled `request`;
payloads, snapshots and timings are dropped (ai.services.tracing.capture_fixture).

    python manage.py capture_reconcile_fixture .ai-traces/<execution id> ai/tests/fixtures/traces/<name>
"""

from django.core.management.base import BaseCommand, CommandError

from ai.services.tracing import capture_fixture


class Command(BaseCommand):
    help = "Turn a raw Reconcile trace directory into a replay fixture directory."

    def add_arguments(self, parser):
        parser.add_argument("trace_dir")
        parser.add_argument("out_dir")

    def handle(self, *args, trace_dir, out_dir, **options):
        written = capture_fixture(trace_dir, out_dir)
        if not written:
            raise CommandError(f"No provider steps found in {trace_dir}.")
        for path in written:
            self.stdout.write(str(path))
        self.stdout.write(self.style.SUCCESS(f"{len(written)} fixture steps written to {out_dir}."))
