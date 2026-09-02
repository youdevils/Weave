from django.shortcuts import render


def index(request):
    memberships = request.user.workspace_memberships.select_related(
        "workspace",
        "workspace__model",
    )

    return render(
        request,
        "workspace/index.html",
        {
            "memberships": memberships,
        },
    )
