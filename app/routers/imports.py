"""CSV upload page, upload handler, import history, and CSV export.

See docs/03-csv-import.md and docs/05-api-routes.md.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select

from app.core.deps import get_current_user
from app.core.security import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    issue_csrf_cookie,
    verify_csrf,
)
from app.core.templates import render
from app.db.models import ImportBatch, User
from app.db.session import get_session
from app.services.csv_export import export_csv
from app.services.csv_import import import_csv

router = APIRouter()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _history(session: Session, user_id: int) -> list[ImportBatch]:
    return list(
        session.exec(
            select(ImportBatch)
            .where(ImportBatch.user_id == user_id)
            .order_by(ImportBatch.imported_at.desc())
        )
    )


@router.get("/import")
def import_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    csrf_token = generate_csrf_token()
    response = render(
        request,
        "import.html",
        {
            "current_user": current_user,
            "csrf_token": csrf_token,
            "batches": _history(session, current_user.id),
        },
    )
    issue_csrf_cookie(response, csrf_token)
    return response


@router.post("/import")
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    csrf_token: str = Form(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    if not verify_csrf(request.cookies.get(CSRF_COOKIE_NAME), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large")

    assert current_user.id is not None
    batch = import_csv(session, current_user.id, file.filename or "upload.csv", content)

    # Only #import-panel is swapped by HTMX, so the still-visible upload form's CSRF
    # hidden field must stay valid — don't rotate the cookie/token here.
    return render(
        request,
        "partials/import_result.html",
        {"batch": batch, "batches": _history(session, current_user.id)},
    )


@router.get("/export")
def export_data(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    filename = f"spark-export-{date.today().isoformat()}.csv"
    return Response(
        content=export_csv(session, current_user.id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/partials/import/history")
def import_history_partial(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    return render(
        request, "partials/import_history.html", {"batches": _history(session, current_user.id)}
    )
