from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def index(request):
    memberships = request.user.workspace_memberships.select_related(
        "workspace",
    ).prefetch_related(
        "workspace__models",
    )

    return render(
        request,
        "workspace/dashboard.html",
        {
            "memberships": memberships,
        },
    )
