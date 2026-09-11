from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from model.models.object_type import ObjectType
from model.views.common_context import get_model_context


@login_required
def object_types(request, model_id):
    context = get_model_context(request, model_id)

    model = context["model"]

    object_types = ObjectType.objects.filter(model=model).order_by("sort_order", "name")

    context.update(
        {
            "object_types": object_types,
        }
    )

    return render(
        request,
        "model/object_types.html",
        context,
    )
