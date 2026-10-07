"""Shared fixtures for assisted app tests."""

import io

from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from workspace.models import Workspace, WorkspaceMember

from ai.services.artifacts import Clarification
from ai.services.change_set import PlanResult

# Re-exported so test modules only need one import line.
from ai.tests.support import (  # noqa: F401
    RaisingProvider,
    ScriptedProvider,
    approve,
    entity,
    extraction,
    extraction_clarification,
    frame,
    objection,
    plan,
    reject,
    target,
)


# -- Assisted Create: one Planning stage, so each helper is one scripted call --


def clarification_result():
    return PlanResult(clarification=Clarification(needed=True, question="Which widget?"))


def no_change_result():
    return plan([], summary="Nothing to do.")


def unresolved_result():
    """A ChangeSet that can never resolve (it names a type that doesn't exist)."""

    return plan([
        {"kind": "create_object", "action_id": "a1", "token": "w", "type": {"kind": "existing", "key": "no_such_type"},
         "name": "New widget"},
    ])


def create_object_plan(object_type_key, name="New widget", token="tmp:1"):
    """The canonical "AI successfully creates one widget" Create plan."""

    return plan(
        [{"kind": "create_object", "action_id": "a1", "token": token,
          "type": {"kind": "existing", "key": object_type_key}, "name": name,
          "provenance": [{"source_id": "intent", "excerpt": "widgets"}]}],
        summary="Create a widget.",
    )


# -- Assisted Reconcile: Extraction -> (deterministic) -> Verification scripts --
# Tasks built directly in tests carry no evidence files, so provenance cites
# the intent ("Track widgets.").


def _widget_extraction(object_type_key, name="Widget"):
    return extraction(
        frame([target("T1", "widgets", "widgets", hint=object_type_key)]),
        entity("E1", name, "widget", hint=object_type_key, excerpt="widgets", source_id="intent"),
    )


def reconcile_ready_script(object_type_key, name="Widget"):
    return [_widget_extraction(object_type_key, name), approve()]


def reconcile_no_change_script():
    return [extraction(frame()), approve()]


def reconcile_clarification_script():
    return [extraction_clarification("Which widget?")]


def reconcile_unresolved_script(object_type_key="widget"):
    """The reviewer's material objection persists after it was routed back
    once: a completed UNRESOLVED outcome, never a failure."""

    same = objection("decision", "E1", "evidence_misread", "The intent does not describe a new widget.")
    return [_widget_extraction(object_type_key), reject(same), reject(same)]


def build_minimal_pdf(text: str) -> bytes:
    """
    Assembles a minimal, structurally valid one-page PDF containing `text`,
    computing real xref offsets from the bytes actually written instead of
    hand-typing them (hand-typed offsets drift the moment the surrounding
    content changes and are a classic source of flaky PDF fixtures).
    `text` must not contain PDF string-literal special characters ( ) \\.
    """

    buf = io.BytesIO()
    offsets = {}

    def write(chunk: bytes):
        buf.write(chunk)

    def obj(n, body: bytes):
        offsets[n] = buf.tell()
        write(f"{n} 0 obj\n".encode())
        write(body)
        write(b"\nendobj\n")

    write(b"%PDF-1.4\n")
    obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    obj(
        3,
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 300 300] /Contents 5 0 R >>",
    )
    obj(4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    content_stream = f"BT /F1 18 Tf 20 150 Td ({text}) Tj ET".encode("latin-1")
    obj(5, f"<< /Length {len(content_stream)} >>\nstream\n".encode() + content_stream + b"\nendstream")

    xref_offset = buf.tell()
    write(b"xref\n")
    write(f"0 {len(offsets) + 1}\n".encode())
    write(b"0000000000 65535 f \n")
    for n in sorted(offsets):
        write(f"{offsets[n]:010d} 00000 n \n".encode())

    write(b"trailer\n")
    write(f"<< /Size {len(offsets) + 1} /Root 1 0 R >>\n".encode())
    write(b"startxref\n")
    write(f"{xref_offset}\n".encode())
    write(b"%%EOF")

    return buf.getvalue()


def build_minimal_docx(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


class AssistedTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.owner = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        cls.editor = CustomUser.objects.create_user(email="editor@example.com", password="pw")
        cls.other_editor = CustomUser.objects.create_user(email="editor2@example.com", password="pw")
        cls.viewer = CustomUser.objects.create_user(email="viewer@example.com", password="pw")
        cls.stranger = CustomUser.objects.create_user(email="stranger@example.com", password="pw")

        # These are the users every non-entitlement test in this app expects
        # to be able to actually run Assisted operations -- entitlement is a
        # separate concern from role, covered on its own in
        # assisted.tests.test_lifecycle / test_execution.
        for user in (cls.owner, cls.editor, cls.other_editor):
            user.plan = CustomUser.Plan.COLLABORATOR
            user.save(update_fields=["plan"])

        for user, role in (
            (cls.owner, WorkspaceMember.Role.OWNER),
            (cls.editor, WorkspaceMember.Role.EDITOR),
            (cls.other_editor, WorkspaceMember.Role.EDITOR),
            (cls.viewer, WorkspaceMember.Role.VIEWER),
        ):
            WorkspaceMember.objects.create(workspace=cls.workspace, user=user, role=role)

    def make_model(self, **kwargs):
        kwargs.setdefault("name", "Test Model")
        return Model.objects.create(workspace=self.workspace, **kwargs)

    def make_object_type(self, model, key="widget", name=None):
        return ObjectType.objects.create(model=model, key=key, name=name or key.title())
