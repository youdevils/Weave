"""
The Import/Export page (reached from Import/Export in the model sidebar) and its endpoints.

    GET  assets/                     the page (Import, Templates, Export)
    GET  assets/export/              download the complete canonical model as JSON
    GET  assets/templates/.../.../.. download a CSV/XLSX template for one type
    GET  assets/templates/zip/...    download a zip of CSV/XLSX templates for every type
    POST assets/import/upload/       store a file as a staged source; returns its columns
    POST assets/import/preview/      what a mapping would change (read-only)
    POST assets/import/create/       create the one Working Proposal (or report no changes)
    POST assets/import/discard/      drop a staged upload

Views only translate HTTP: access control, JSON in and out. Parsing, mapping,
identity, planning and the Proposal live in ingestion.services; nothing here
touches canonical data.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_POST

from ingestion.access import get_importable_model
from ingestion.models import ImportSource
from ingestion.services import limits, source_file, templates
from ingestion.services.coercion import cell_text
from ingestion.services.errors import ImportBlocked, ImportError_, TargetError
from ingestion.services.model_export import build_export, export_filename
from ingestion.services.proposals import create_import_proposal, preview_import
from ingestion.services.targets import describe_targets, resolve_target
from ingestion.uploads import LimitedUploadHandler
from model.services.proposal.proposal import ProposalLimitReached
from model.views.active_proposal import set_active_proposal_id
from model.views.common_context import get_model_context

SAMPLE_ROWS = 5
SAMPLE_CELL_CHARS = 200

# Multipart framing and form fields add a little to the file itself.
UPLOAD_OVERHEAD_ALLOWANCE = 64 * 1024


def _error(code, message, status=400, **extra):
    return JsonResponse({"success": False, "code": code, "error": message, **extra}, status=status)


def _import_error(error: ImportError_):
    extra = {"messages": error.messages} if hasattr(error, "messages") else {}

    return _error(error.code, error.message, **extra)


def _json_body(request):
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return None

    return body if isinstance(body, dict) else None


def _staged_source(request, model, body):
    """The caller's own staged source named in the body, or None."""

    try:
        return source_file.get_staged_source(model, request.user, body.get("source_id"))
    except ImportSource.DoesNotExist:
        return None


@login_required
@require_GET
def assets(request, model_id):
    model = get_importable_model(request, model_id)

    context = get_model_context(request, model.id)
    target_lists = describe_targets(model)

    context["import_bootstrap"] = {
        "targets": target_lists,
        "limits": {
            "max_file_mb": limits.max_file_bytes() // (1024 * 1024),
            "max_rows": limits.max_rows(),
        },
        "urls": {
            "upload": reverse("ingestion:import_upload", args=[model.id]),
            "preview": reverse("ingestion:import_preview", args=[model.id]),
            "create": reverse("ingestion:import_create", args=[model.id]),
            "discard": reverse("ingestion:import_discard", args=[model.id]),
        },
    }
    context["template_object_types"] = target_lists["object_types"]
    context["template_relationship_types"] = target_lists["relationship_types"]

    return render(request, "ingestion/assets.html", context)


@login_required
@require_GET
def export_model(request, model_id):
    model = get_importable_model(request, model_id)

    payload = json.dumps(build_export(model), indent=2)

    response = HttpResponse(payload, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{export_filename(model)}"'
    return response


@login_required
@require_GET
def download_template(request, model_id, kind, type_id, file_format):
    model = get_importable_model(request, model_id)

    if file_format not in templates.FILE_FORMATS:
        raise Http404

    try:
        target = resolve_target(model, kind, type_id)
    except TargetError:
        raise Http404

    with_data = request.GET.get("data") == "1"

    data = templates.build_template(target, file_format, model=model, with_data=with_data)
    filename = templates.template_filename(model, target, file_format, with_data=with_data)

    response = HttpResponse(data, content_type=templates.CONTENT_TYPES[file_format])
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
def download_templates_zip(request, model_id, file_format):
    model = get_importable_model(request, model_id)

    if file_format not in templates.FILE_FORMATS:
        raise Http404

    data = templates.build_templates_zip(model, file_format)
    filename = templates.templates_zip_filename(model, file_format)

    response = HttpResponse(data, content_type=templates.ZIP_CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@csrf_exempt
def import_upload(request, model_id):
    """
    The handler that enforces the size limit has to be installed before anything
    reads the request body, and Django's CSRF middleware would do exactly that,
    so this thin outer view exempts itself, installs the handler and hands over
    to a csrf-protected view.
    """

    handler = LimitedUploadHandler(request, max_bytes=limits.max_file_bytes())
    request.upload_handlers = [handler]

    return _import_upload(request, model_id, handler=handler)


@csrf_protect
@login_required
@require_POST
def _import_upload(request, model_id, handler):
    model = get_importable_model(request, model_id)

    limit_mb = limits.max_file_bytes() // (1024 * 1024)

    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0

    if declared > limits.max_file_bytes() + UPLOAD_OVERHEAD_ALLOWANCE:
        return _error("file_too_large", f"The file is larger than the {limit_mb} MB limit.", status=413)

    upload = request.FILES.get("file")

    if handler.too_large:
        return _error("file_too_large", f"The file is larger than the {limit_mb} MB limit.", status=413)

    if upload is None:
        return _error("no_file", "Choose a file to upload.")

    try:
        source, table = source_file.store_upload(model, request.user, upload.name, upload.read())
    except ImportError_ as error:
        return _import_error(error)

    return JsonResponse(
        {
            "success": True,
            "source": {
                "id": str(source.id),
                "filename": source.original_filename,
                "format": source.file_format,
                "size_bytes": source.size_bytes,
                "row_count": table.row_count,
                "column_count": table.column_count,
            },
            "columns": [{"index": index, "header": header} for index, header in enumerate(table.headers)],
            "sample_rows": [
                [cell_text(cell)[:SAMPLE_CELL_CHARS] if cell is not None else "" for cell in row]
                for row in table.rows[:SAMPLE_ROWS]
            ],
            "warnings": list(table.warnings),
        }
    )


@login_required
@require_POST
def import_preview(request, model_id):
    model = get_importable_model(request, model_id)

    body = _json_body(request)

    if body is None:
        return _error("invalid", "The request body must be a JSON object.")

    source = _staged_source(request, model, body)

    if source is None:
        return _error("source_not_found", "That upload was not found. Upload the file again.", status=404)

    try:
        plan = preview_import(model, source, body.get("mapping"))
    except ImportError_ as error:
        return _import_error(error)

    return JsonResponse({"success": True, **plan.to_preview()})


@login_required
@require_POST
def import_create(request, model_id):
    model = get_importable_model(request, model_id)

    body = _json_body(request)

    if body is None:
        return _error("invalid", "The request body must be a JSON object.")

    source = _staged_source(request, model, body)

    if source is None:
        return _error("source_not_found", "That upload was not found. Upload the file again.", status=404)

    try:
        result = create_import_proposal(model, request.user, source, body.get("mapping"))
    except ProposalLimitReached as error:
        return _error("proposal_limit", str(error), status=409)
    except ImportBlocked as error:
        shown = limits.problems_shown()
        return _error(
            error.code,
            "This import cannot be turned into a proposal until its problems are fixed.",
            status=422,
            problem_count=len(error.problems),
            problems=[problem.to_dict() for problem in error.problems[:shown]],
        )
    except ImportError_ as error:
        return _import_error(error)

    summary = result.plan.summary.to_dict()

    if result.no_changes:
        return JsonResponse({"success": True, "no_changes": True, "summary": summary})

    set_active_proposal_id(request, model.id, result.proposal.id)

    return JsonResponse(
        {
            "success": True,
            "no_changes": False,
            "summary": summary,
            "proposal_url": reverse("model:proposal", args=[model.id, result.proposal.id]),
        }
    )


@login_required
@require_POST
def import_discard(request, model_id):
    model = get_importable_model(request, model_id)

    body = _json_body(request)

    if body is None:
        return _error("invalid", "The request body must be a JSON object.")

    source = _staged_source(request, model, body)

    if source is not None:
        source_file.discard(source)

    return JsonResponse({"success": True})
