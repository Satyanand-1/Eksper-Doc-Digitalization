import html
import math
import logging
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentStatus
from app.models.audit import AuditOutcome
from app.schemas.search import PaginatedSearchResponse, SearchItemMatch
from app.services.authorization import DocumentAuthorizationService
from app.services.audit import audit_service, AuditWriteError

logger = logging.getLogger("edrms.search")

router = APIRouter(prefix="/api/v1/search", tags=["Search"])

MAX_QUERY_LENGTH = 200

def sanitize_snippet(raw_snippet: str | None) -> str | None:
    """
    Sanitizes ts_headline output.
    HTML-escapes all text, but allows safe bold tags for highlighted matches.
    Ensures bounded length to prevent client payload bloat.
    """
    if not raw_snippet:
        return None
    escaped = html.escape(raw_snippet, quote=True)
    safe_highlighted = (
        escaped.replace("[[HL_START]]", "<b>")
        .replace("[[HL_STOP]]", "</b>")
    )
    if len(safe_highlighted) > 500:
        safe_highlighted = safe_highlighted[:497] + "..."
    return safe_highlighted


def build_raw_sql_auth_clause(user: User, params: dict) -> str:
    """
    Constructs an explicit raw SQL WHERE clause corresponding directly to
    DocumentAuthorizationService policies, referencing alias 'd' (digital_documents).
    """
    if not user or not user.is_active:
        return "1=0"

    role = user.role
    user_dept = (user.department or "").strip()

    # 1. Admin: unrestricted
    if role == UserRole.ADMIN:
        return "1=1"

    # 2. Records Officer: unrestricted cross-department
    if role == UserRole.RECORDS_OFFICER:
        return "1=1"

    # 3. Department User: strictly own department
    if role == UserRole.DEPARTMENT_USER:
        if not user_dept:
            return "1=0"
        params["auth_user_dept"] = user_dept
        return "lower(d.department) = lower(:auth_user_dept)"

    # 4. Approver: own department OR created by user
    if role == UserRole.APPROVER:
        params["auth_user_id"] = str(user.id)
        if user_dept:
            params["auth_user_dept"] = user_dept
            return "(d.created_by_id = CAST(:auth_user_id AS uuid) OR lower(d.department) = lower(:auth_user_dept))"
        return "d.created_by_id = CAST(:auth_user_id AS uuid)"

    # 5. Auditor: strictly assigned audit department
    if role == UserRole.AUDITOR:
        if not user_dept:
            return "1=0"
        params["auth_user_dept"] = user_dept
        return "lower(d.department) = lower(:auth_user_dept)"

    # 6. Read-Only: non-confidential AND (own department OR created by user)
    if role == UserRole.READ_ONLY:
        confidential_list = list(DocumentAuthorizationService.CONFIDENTIAL_CLASSIFICATIONS)
        params["auth_user_id"] = str(user.id)
        # Construct tuples or string literals for classifications
        conf_placeholders = []
        for idx, conf_val in enumerate(confidential_list):
            key = f"auth_conf_{idx}"
            params[key] = conf_val.upper()
            conf_placeholders.append(f":{key}")
        in_conf_clause = f"upper(d.classification) NOT IN ({', '.join(conf_placeholders)})"

        if user_dept:
            params["auth_user_dept"] = user_dept
            return f"({in_conf_clause} AND (lower(d.department) = lower(:auth_user_dept) OR d.created_by_id = CAST(:auth_user_id AS uuid)))"
        return f"({in_conf_clause} AND d.created_by_id = CAST(:auth_user_id AS uuid))"

    return "1=0"


@router.get(
    "",
    response_model=PaginatedSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Secure full-text document search",
    description="Performs secure, paginated full-text search across document metadata and extracted version text using PostgreSQL full-text search.",
)
def search_documents(
    request: Request,
    query: Annotated[str, Query(description="Search text query (natural multiword or quoted phrases)")],
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    department: Annotated[str | None, Query(max_length=100, description="Department exact filter")] = None,
    classification: Annotated[str | None, Query(max_length=100, description="Classification filter")] = None,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status", description="Document lifecycle status filter")] = None,
    sort_order: Annotated[Literal["relevance", "created_desc", "created_asc"], Query(description="Sort order strategy")] = "relevance",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Full-text search endpoint:
    - Validates query length and whitespace
    - Enforces DocumentAuthorizationService scope at the SQL level before calculation/ranking
    - Combines weighted metadata search (Title, Reference, Subject) with extracted text search (DocumentVersion)
    - Employs PostgreSQL GIN indexes with websearch_to_tsquery('english', ...)
    - Ranks results by ts_rank relevance with deterministic secondary sort
    - Returns sanitized, bounded snippet excerpts and matching version numbers
    - Records audited search activity adhering to mandatory audit policies
    """
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Search query cannot be empty or only whitespace.",
        )

    if len(clean_query) > MAX_QUERY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Search query exceeds maximum length of {MAX_QUERY_LENGTH} characters.",
        )

    # 1. Determine if the query produces any lexemes in PostgreSQL websearch_to_tsquery
    # Stop-word-only or punctuation-only queries (e.g., '...', 'the', '???') yield an empty tsquery
    try:
        check_tsquery = db.execute(
            text("SELECT length(websearch_to_tsquery('english', :q)::text) AS q_len"),
            {"q": clean_query},
        ).mappings().first()
        tsquery_len = check_tsquery["q_len"] if check_tsquery else 0
    except Exception as exc:
        logger.error(f"Error parsing search query: {exc}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid search query syntax.",
        )

    # If the query contains only punctuation or stop-words, it matches 0 documents
    if tsquery_len == 0:
        try:
            audit_service.log_from_request(
                db=db,
                request=request,
                action="document.search",
                resource_type="document",
                outcome=AuditOutcome.SUCCESS,
                actor_id=current_user.id,
                resource_id=None,
                details={
                    "result_count": 0,
                    "page": page,
                    "page_size": page_size,
                    "filtered_department": bool(department),
                    "filtered_classification": bool(classification),
                    "filtered_status": bool(status_filter),
                },
                raise_on_failure=True,
            )
        except AuditWriteError as a_err:
            logger.error(f"Mandatory audit write failure on empty search: {a_err}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security audit recording failed.",
            )
        return PaginatedSearchResponse(
            items=[],
            page=page,
            page_size=page_size,
            total=0,
            total_pages=0,
        )

    # 2. Build authorization filter and query parameters
    sql_params = {"search_query": clean_query}
    auth_sql_clause = build_raw_sql_auth_clause(current_user, sql_params)

    filter_conditions = [auth_sql_clause]

    if department:
        clean_dept = department.strip()
        filter_conditions.append("lower(d.department) = lower(:dept_filter)")
        sql_params["dept_filter"] = clean_dept

    if classification:
        clean_class = classification.strip()
        filter_conditions.append("lower(d.classification) = lower(:class_filter)")
        sql_params["class_filter"] = clean_class

    if status_filter:
        status_val = status_filter.value if isinstance(status_filter, DocumentStatus) else str(status_filter)
        filter_conditions.append("d.status = :status_filter")
        sql_params["status_filter"] = status_val

    # FTS Matching condition: metadata vector matches OR extracted_text matches
    fts_match_condition = """(
        (
            setweight(to_tsvector('english', coalesce(d.title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(d.document_reference, '') || ' ' || replace(coalesce(d.document_reference, ''), '-', ' ')), 'A') ||
            setweight(to_tsvector('english', coalesce(d.subject, '')), 'B')
        ) @@ q.query
        OR v_match.document_id IS NOT NULL
    )"""
    filter_conditions.append(fts_match_condition)

    where_clause = " AND ".join(f"({cond})" for cond in filter_conditions)

    # 3. Count total matching authorized documents
    count_sql = f"""
    WITH q AS (
        SELECT websearch_to_tsquery('english', :search_query) AS query
    ),
    v_match AS (
        SELECT 
            v.document_id
        FROM document_versions v
        CROSS JOIN q
        WHERE to_tsvector('english', coalesce(v.extracted_text, '')) @@ q.query
        GROUP BY v.document_id
    )
    SELECT COUNT(d.id) AS total_count
    FROM digital_documents d
    CROSS JOIN q
    LEFT JOIN v_match ON v_match.document_id = d.id
    WHERE {where_clause}
    """

    try:
        count_row = db.execute(text(count_sql), sql_params).mappings().first()
        total_count = count_row["total_count"] if count_row else 0
    except Exception as exc:
        logger.error(f"Error executing search count query: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while executing the search query.",
        )

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    # 4. Determine order by clause
    if sort_order == "created_asc":
        order_by_clause = "d.created_at ASC, d.id ASC"
    elif sort_order == "created_desc":
        order_by_clause = "d.created_at DESC, d.id DESC"
    else:  # "relevance" (default)
        order_by_clause = "relevance_score DESC, d.created_at DESC, d.id DESC"

    # 5. Fetch paginated search items
    offset = (page - 1) * page_size
    sql_params["limit"] = page_size
    sql_params["offset"] = offset

    items_sql = f"""
    WITH q AS (
        SELECT websearch_to_tsquery('english', :search_query) AS query
    ),
    v_match AS (
        SELECT 
            v.document_id,
            array_agg(v.version_number ORDER BY v.version_number ASC) AS matching_versions,
            max(ts_rank(to_tsvector('english', coalesce(v.extracted_text, '')), q.query)) AS max_version_rank,
            (array_agg(v.extracted_text ORDER BY ts_rank(to_tsvector('english', coalesce(v.extracted_text, '')), q.query) DESC))[1] AS top_version_text
        FROM document_versions v
        CROSS JOIN q
        WHERE to_tsvector('english', coalesce(v.extracted_text, '')) @@ q.query
        GROUP BY v.document_id
    )
    SELECT 
        d.id,
        d.document_reference,
        d.title,
        d.subject,
        d.department,
        d.classification,
        d.mime_type,
        d.status,
        d.created_at,
        d.updated_at,
        COALESCE(v_match.matching_versions, ARRAY[]::integer[]) AS matching_version_numbers,
        ROUND((
            ts_rank(
                (
                    setweight(to_tsvector('english', coalesce(d.title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(d.document_reference, '') || ' ' || replace(coalesce(d.document_reference, ''), '-', ' ')), 'A') ||
                    setweight(to_tsvector('english', coalesce(d.subject, '')), 'B')
                ),
                q.query
            ) + COALESCE(v_match.max_version_rank, 0.0)
        )::numeric, 4) AS relevance_score,
        CASE 
            WHEN v_match.top_version_text IS NOT NULL THEN
                ts_headline('english', v_match.top_version_text, q.query, 'StartSel=[[HL_START]], StopSel=[[HL_STOP]], MaxWords=35, MinWords=15')
            WHEN d.subject IS NOT NULL AND d.subject != '' AND to_tsvector('english', d.subject) @@ q.query THEN
                ts_headline('english', d.subject, q.query, 'StartSel=[[HL_START]], StopSel=[[HL_STOP]], MaxWords=35, MinWords=15')
            ELSE
                ts_headline('english', d.title, q.query, 'StartSel=[[HL_START]], StopSel=[[HL_STOP]], MaxWords=35, MinWords=15')
        END AS raw_snippet
    FROM digital_documents d
    CROSS JOIN q
    LEFT JOIN v_match ON v_match.document_id = d.id
    WHERE {where_clause}
    ORDER BY {order_by_clause}
    LIMIT :limit OFFSET :offset
    """

    try:
        rows = db.execute(text(items_sql), sql_params).mappings().all()
    except Exception as exc:
        logger.error(f"Error executing search items query: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving search results.",
        )

    # 6. Format items into response schema
    items = []
    for r in rows:
        status_val = DocumentStatus(r["status"]) if isinstance(r["status"], str) else r["status"]
        snippet = sanitize_snippet(r["raw_snippet"])
        items.append(
            SearchItemMatch(
                id=r["id"],
                document_reference=r["document_reference"],
                title=r["title"],
                subject=r["subject"],
                department=r["department"],
                classification=r["classification"],
                mime_type=r["mime_type"],
                status=status_val,
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                matching_version_numbers=list(r["matching_version_numbers"] or []),
                snippet=snippet,
                relevance_score=float(r["relevance_score"] or 0.0),
            )
        )

    # 7. Record audit log according to mandatory policy
    try:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.search",
            resource_type="document",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=None,
            details={
                "result_count": total_count,
                "page": page,
                "page_size": page_size,
                "filtered_department": bool(department),
                "filtered_classification": bool(classification),
                "filtered_status": bool(status_filter),
            },
            raise_on_failure=True,  # Mandatory audit enforcement
        )
    except AuditWriteError as a_err:
        logger.error(f"Mandatory audit write failure on search: {a_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit recording failed.",
        )

    return PaginatedSearchResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total_count,
        total_pages=total_pages,
    )
