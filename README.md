# Electronic Document and Records Management System (EDRMS)

An enterprise-ready prototype for digitizing, storing, searching, tracking, and governing physical and digital records.

## Architecture Overview

- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind CSS
- **Backend**: Python 3.11 + FastAPI + SQLAlchemy 2.x + Alembic + Argon2id + PyJWT + Uvicorn
- **Database**: PostgreSQL 16 (with native `tsvector` full-text search)
- **File Storage**: Dedicated persistent volume (`/var/edrms/storage`) strictly outside public web roots
- **Orchestration**: Docker Compose with health checks and persistent named volumes

---

## Directory Structure

```text
EDRMS/
├── .env.example             # Safe template for environment variables
├── .env                     # Local active environment variables (git-ignored)
├── .gitignore               # Ignored files, secrets, local storage, dependencies
├── docker-compose.yml       # Service orchestration (db, backend, frontend)
├── README.md                # Project documentation and operational guide
│
├── backend/
│   ├── Dockerfile           # Python 3.11 slim image
│   ├── requirements.txt     # Pinned Python dependencies (FastAPI, SQLAlchemy, Alembic, argon2-cffi, pyjwt, etc.)
│   ├── alembic.ini          # Alembic migration configuration
│   ├── migrations/          # Alembic migration environment and version files
│   │   ├── env.py           # Migration runtime wiring to app.config and Base.metadata
│   │   ├── script.py.mako   # Migration revision template
│   │   └── versions/        # Applied migration versions
│   │       ├── 37c512bc7e24_create_users_table.py  # User model migration
│   │       ├── e15b5392be5e_create_document_and_version_tables.py # Documents & versions migration
│   │       ├── a8df59e211be_create_audit_logs_table.py # Tamper-evident audit logging
│   │       ├── 47712cf518ca_add_extraction_status_to_document_versions.py # OCR extraction tracking
│   │       ├── d9f158d91b0f_add_full_text_search_indexes.py # PostgreSQL GIN FTS indexes
│   │       ├── 26af65844cc3_create_ocr_jobs_table.py # Durable OCR job queue table
│   │       └── 9b73ade31935_create_review_workflow_tables.py # Review workflows and assignments tables
│   ├── app/
│   │   ├── main.py          # FastAPI application & liveness/readiness probes
│   │   ├── worker.py        # Dedicated OCR daemon entrypoint with signal handling
│   │   ├── config.py        # Pydantic Settings configuration (with JWT, pooling & worker settings)
│   │   ├── database.py      # SQLAlchemy 2.x engine, SessionLocal, Base, get_db
│   │   ├── security.py      # Argon2id password hashing and constant-time verification
│   │   ├── jwt.py           # JWT token generation (HS256) and decoding/validation
│   │   ├── dependencies.py  # get_current_user Bearer authentication dependency
│   │   ├── seed.py          # Development-only test user provisioning & cleanup CLI
│   │   ├── services/
│   │   │   ├── storage.py   # Local disk storage service (staging, SHA-256, path boundary enforcement)
│   │   │   ├── authorization.py # Role-based & department document access policy engine
│   │   │   ├── file_validator.py # Magic bytes file signature & extension verification
│   │   │   ├── audit.py     # Tamper-evident audit logging service
│   │   │   ├── ocr.py       # Tesseract OCR and PyPDF extraction engine
│   │   │   └── ocr_worker.py # Durable queue manager, atomic lease locking & crash recovery
│   │   ├── schemas/         # Pydantic schemas (auth, document, audit, search, ocr)
│   │   ├── api/             # API routers (auth, documents, search, ocr)
│   │   └── models/          # Declarative models package
│   │       ├── __init__.py  # Exposes Base, User, DigitalDocument, DocumentVersion, AuditLog, OCRJob
│   │       ├── user.py      # User model with UUID, normalized email, Argon2 hash, roles
│   │       ├── document.py  # DigitalDocument and DocumentVersion models
│   │       ├── audit.py     # Immutable AuditLog model
│   │       └── ocr_job.py   # Durable OCRJob model with lease & retry tracking
│   └── tests/               # Pytest automated test suite (204 tests)
│       ├── test_ocr_monitoring.py # OCR job listing, detail, and controlled retry tests
│       ├── test_durable_ocr.py # Durable queue, retry, lease recovery, and restart tests
│       ├── test_search.py   # Full-text search and relevance tests
│       ├── test_ocr_integration.py # Automated OCR triggering and extraction status tests
│       ├── test_ocr.py      # OCR engine unit tests across PDF and image formats
│       └── ...              # Authentication, document, and security tests
│
├── frontend/
│   ├── Dockerfile           # Multi-stage standalone Next.js image
│   ├── package.json         # Pinned Node.js dependencies
│   ├── tsconfig.json        # TypeScript configuration
│   └── src/
│       └── app/             # App router pages, layouts and health/readiness probe UI
│
└── storage/                 # Local directory for persistent uploads
    ├── uploads/             # Digitized files and version revisions
    └── temp/                # Temporary processing staging (OCR)
```

---

## Digital Document & Version Model Architecture

### Distinction: `DigitalDocument` vs. `DocumentVersion`

- **`DigitalDocument`**: Represents the **logical record** in the repository. Holds business and governance metadata:
  - Unique human-readable reference number (e.g., `DOC-2026-0001`).
  - Title, Subject, Department, and Classification.
  - Lifecycle status (`draft`, `under_review`, `active`, `archived`, `disposed`).
  - Creator reference (`created_by_id` with `RESTRICT` deletion protection).
  - Creation, update, and archival timestamps.
  - *File binaries are never stored inside this table.*

- **`DocumentVersion`**: Represents a **concrete, immutable file revision** attached to a parent `DigitalDocument`:
  - `version_number`: Strictly unique sequence within its parent document (`uq_document_version_number`).
  - `storage_key`: Server-generated, date-partitioned relative path on disk (e.g. `uploads/2026/10/<uuid>.pdf`). Client-supplied filenames are never used for disk layout.
  - `original_filename`: Retained solely as presentation metadata for download headers.
  - `file_size_bytes`: Byte length calculated during upload staging.
  - `file_hash_sha256`: Cryptographic SHA-256 checksum calculated on ingest.
  - `extracted_text`: Text buffer reserved for OCR processing.
  - `CASCADE` deletion rule: Deleting a document record cleans up its version metadata rows, but does not purge stored files from disk until explicit archival/disposal policies execute.

---

## Local Disk Storage Service

Files are managed on disk by `LocalStorageService` (`app.services.storage`):

### Security & Path Boundary Enforcement
1. **Isolated Root**: Files are stored exclusively under `/var/edrms/storage/` (mapped to named volume `edrms_storage_data`), completely inaccessible to the frontend or web server roots.
2. **Path Traversal Rejection**: Any storage key containing directory traversal elements (`../`, `..\\`, leading `/`, drive letters) is rejected with `StorageSecurityError`.
3. **Boundary Check**: All operations verify `resolved_path.relative_to(storage_root)`.
4. **Staging & Finalization**:
   - Files are initially streamed to `temp/stage_<uuid>.tmp` while computing SHA-256 and byte count.
   - Finalization atomically moves the temporary file to `uploads/YYYY/MM/<uuid>.<ext>`.
   - Temporary files are immediately deleted if an ingest error occurs.
   - Destination duplicate check ensures files are never overwritten silently.

### Storage Paths
- **Docker Backend Container**: `/var/edrms/storage` (`/var/edrms/storage/uploads` and `/var/edrms/storage/temp`)
- **Docker Named Volume**: `edrms_storage_data`
- **Host Workspace Path**: `d:\EDRMS\storage\` (git-ignored, retains `.gitkeep`)

---

## Development Test Users (Local Development Only)

> [!CAUTION]
> **Production Safety Notice**: Test user provisioning is strictly blocked from running in production environments. Attempting to run the seed script with `ENVIRONMENT=production` fails immediately with a fatal error. Never run seed commands in production.

For testing and local development, a dedicated provisioning command creates non-destructive test accounts for all six EDRMS roles. The command is fully **idempotent** (safe to run repeatedly without creating duplicates or modifying existing accounts).

### Default Test Account Credentials

| Role | Email | Default Password | Department |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin@example.com` | `DevAdminPassword123!` | System Administration |
| **Records Officer** | `records.officer@example.com` | `DevRecordsPassword123!` | Records & Compliance |
| **Department User** | `dept.user@example.com` | `DevDeptPassword123!` | Finance |
| **Approver** | `approver@example.com` | `DevApproverPassword123!` | Operations |
| **Auditor** | `auditor@example.com` | `DevAuditorPassword123!` | Internal Audit |
| **Read-Only User** | `readonly.user@example.com` | `DevReadOnlyPassword123!` | Public Information |

*Customizing test credentials*: Any test user's email or password can be overridden by setting environment variables in `.env` (e.g. `SEED_ADMIN_EMAIL=custom_admin@example.com` and `SEED_ADMIN_PASSWORD=CustomPass123!`).

### Running the Seed Command

To provision the six development accounts:
```bash
docker exec edrms-backend python -m app.seed
```

### Verifying Account Roles via API
Login as any test user and inspect their role:
```powershell
$token = (Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" -Method Post -Body '{"email":"records.officer@example.com","password":"DevRecordsPassword123!"}' -ContentType "application/json").access_token
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/me" -Headers @{ Authorization = "Bearer $token" }
```

### Removing Development Test Accounts Safely
To purge only the test accounts without affecting other records:
```bash
docker exec edrms-backend python -m app.seed --clean
```

---

## Authentication & JWT Security

EDRMS enforces stateless, cryptographically signed Bearer tokens using **PyJWT** signed with **HS256**.

### Authentication Endpoints Contract

#### 1. `POST /api/v1/auth/login`
- **Request Body**:
  ```json
  {
    "email": "admin@example.com",
    "password": "DevAdminPassword123!"
  }
  ```
- **Success Response (`200 OK`)**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```
- **Error Responses**:
  - `401 Unauthorized` (`{"detail": "Incorrect email or password"}`): Generic error returned for non-existent emails and wrong passwords to eliminate account enumeration attacks.
  - `401 Unauthorized` (`{"detail": "User account is inactive"}`): Inactive/disabled accounts are rejected from logging in.
  - `422 Unprocessable Entity`: Malformed email format or missing fields.

#### 2. `GET /api/v1/auth/me`
- **Headers**:
  ```http
  Authorization: Bearer <access_token>
  ```
- **Success Response (`200 OK`)**:
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "email": "records.officer@example.com",
    "full_name": "Development Records Officer",
    "department": "Records & Compliance",
    "role": "records_officer",
    "is_active": true,
    "created_at": "2026-10-10T11:33:30.269883Z",
    "updated_at": "2026-10-10T11:33:30.269883Z"
  }
  ```
- **Error Responses**:
  - `401 Unauthorized` (`{"detail": "Could not validate credentials"}`): Returned if Authorization header is missing, token is expired, malformed, or has an invalid signature.
  - `401 Unauthorized` (`{"detail": "User account is inactive"}`): Returned if the user account was deactivated after token generation.

---

### Document Upload Endpoint Contract

#### `POST /api/v1/documents/upload`
Requires standard Bearer authentication. Any active authenticated user can upload documents.

- **Request Format**: `multipart/form-data`
- **Headers**:
  ```http
  Authorization: Bearer <access_token>
  ```
- **Form Fields**:
  - `file` (*required*): Uploaded file binary (PDF, JPEG, PNG, TIFF up to 25 MB).
  - `title` (*required*): Non-empty title (max 255 chars).
  - `subject` (*optional*): Document subject / topic (max 255 chars).
  - `department` (*optional*): Submitting or owning department (max 100 chars).
  - `classification` (*optional*): Security or category tag (max 50 chars).

- **Document Reference Format**:
  - Format: `DOC-YYYY-XXXXXXXX` (e.g. `DOC-2026-793ECA3D`)
  - Guaranteed uppercase 8-character hex token with database uniqueness constraint.

- **File Validation & Safety**:
  - **Magic-Byte Sniffing**: Inspects the first 16 bytes of the stream independently of client-provided `Content-Type`. Rejecting spoofed extensions (`.pdf` containing executable or script text).
  - **Sanitization**: Filenames are sanitized, stripped of path separators, null bytes, and limited to 255 chars.
  - **Two-Phase Staged Persistence**: Staged first in `/var/edrms/storage/temp/stage_<uuid>.tmp`. On database or validation errors, compensatory cleanup immediately unlinks temporary and finalized files.

- **Success Response (`201 Created`)**:
  ```json
  {
    "document_id": "288870d0-e7de-486a-a208-9e0b7ab97078",
    "document_reference": "DOC-2026-793ECA3D",
    "version_id": "51bad228-7f89-438b-b19c-806bba23f159",
    "version_number": 1,
    "title": "FY2026 Audit Report",
    "subject": "Internal Audit Findings",
    "department": "Finance",
    "classification": "CONFIDENTIAL",
    "original_filename": "test_audit_report.pdf",
    "mime_type": "application/pdf",
    "file_size_bytes": 55,
    "file_hash_sha256": "b3b26c39987af5e98d6d79bfd61894d03781d4ca720c21b2d51f8acb422976ce",
    "created_at": "2026-10-10T12:00:21.689177Z",
    "status": "active"
  }
  ```

- **Error Responses**:
  - `400 Bad Request`: Empty files, missing title, file exceeds 25 MB limit, or file fails magic-byte validation (`Unsupported or invalid file content`).
  - `401 Unauthorized`: Missing or invalid Bearer token.
  - `422 Unprocessable Entity`: Missing required form fields.

- **cURL Example**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/documents/upload" \
    -H "Authorization: Bearer <access_token>" \
    -F "file=@/path/to/invoice.pdf" \
    -F "title=Vendor Invoice INV-9002" \
    -F "department=Procurement" \
    -F "classification=CONFIDENTIAL"
  ```

---

### Secure Document Download Endpoint Contract

#### `GET /api/v1/documents/{document_id}/versions/{version_number}/download`
Securely streams document binary content after multi-dimensional role, department, and classification authorization checks.

- **Headers**:
  ```http
  Authorization: Bearer <access_token>
  X-Correlation-ID: <optional-correlation-id>
  ```
- **Path Parameters**:
  - `document_id`: UUID of the parent document.
  - `version_number`: Integer version sequence (e.g. `1`, `2`).

- **Uniform Role and Classification Access Control Matrix (All 4 Document APIs)**:
*Applies identically across `GET /api/v1/documents`, `GET /api/v1/documents/{id}`, `GET /api/v1/documents/{id}/versions`, and `GET /api/v1/documents/{id}/versions/{ver}/download`.*

| Role | Department Scope | Non-Confidential (`General`, etc.) | Classified (`CONFIDENTIAL`, `SECRET`, `RESTRICTED`, `TOP_SECRET`) |
| :--- | :--- | :--- | :--- |
| **Administrator** (`admin`) | All departments | Allowed | Allowed |
| **Records Officer** (`records_officer`) | All departments | Allowed | Allowed |
| **Department User** (`department_user`) | Own department only | Allowed | Allowed (within own department only; cross-department strictly denied) |
| **Approver** (`approver`) | Own department OR records authored by user | Allowed | Allowed (within own department or authored; cross-department strictly denied) |
| **Auditor** (`auditor`) | Assigned audit department only | Allowed | Allowed (strictly within assigned department; cross-department access denied) |
| **Read-Only User** (`read_only`) | Own department OR records authored by user | Allowed | **Denied** (Read-only users cannot access classified documents anywhere) |

> [!IMPORTANT]
> **Default Deny Policy**: Missing user departments, unassigned audit scopes, or unauthenticated/inactive requests are denied by default. Unauthorized listing requests exclude records from both `items` and `total` count; unauthorized metadata/version queries return non-disclosing `404 Not Found`.

- **Security & Storage Protection**:

  - **Path Confinement**: Resolves server-controlled relative keys through `LocalStorageService`. Direct client storage paths are rejected.
  - **Path Traversal Rejection**: Traversal strings (`../`, absolute drive paths) return HTTP `400 Bad Request`.
  - **Binary Streaming**: Streams chunks (64 KB) using FastAPI `StreamingResponse` without reading whole files into RAM.
  - **Security Headers**: Returns `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-cache, no-store, must-revalidate`, and sanitized `Content-Disposition`.
  - **No Path Leakage**: Missing files or database errors never expose internal directory roots or absolute filesystem paths.

- **Audit Logging Behavior**:
  - Every download attempt records an entry in the PostgreSQL `audit_logs` table (`actor_id`, `action="document.download"`, `resource_id`, `outcome="success"|"denied"|"failed"`, `client_ip`, `correlation_id`, `details`).
  - Passwords, authorization tokens, and binary bytes are strictly excluded from audit logs.
  - Mandatory audit enforcement: Audit-write failures raise an error to prevent silent, unaudited downloads.

- **Success Response (`200 OK`)**:
  - Headers:
    ```http
    Content-Type: application/pdf
    Content-Disposition: attachment; filename="Vendor_Invoice_INV-9002.pdf"
    Content-Length: 1048576
    X-Content-Type-Options: nosniff
    Cache-Control: private, no-cache, no-store, must-revalidate
    ```
  - Body: Binary stream.

- **Error Responses**:
  - `401 Unauthorized`: Missing, expired, or malformed JWT token.
  - `403 Forbidden`: Access denied by authorization policy (e.g. cross-department access attempt or confidential file restriction).
  - `404 Not Found`: Document ID does not exist, version number does not exist, or stored binary is missing on disk.
  - `400 Bad Request`: Malicious storage key or path traversal attempt.

- **cURL Example**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/documents/ce243f7b-22f7-4b2c-885d-0f1bd0fd2dcc/versions/1/download" \
    -H "Authorization: Bearer <access_token>" \
    -H "X-Correlation-ID: audit-req-9001" \
    --output downloaded_document.pdf
  ```

---

### Document Repository Listing & Metadata Retrieval APIs

#### 1. `GET /api/v1/documents`
Returns paginated repository documents. Enforces department and classification access boundaries strictly at the database level before counting and pagination.

- **Headers**:
  ```http
  Authorization: Bearer <access_token>
  ```
- **Query Parameters**:
  - `page` (*optional*, integer, default `1`, min `1`): Current page number.
  - `page_size` (*optional*, integer, default `20`, min `1`, max `100`): Items per page.
  - `search` (*optional*, string, max `100`): Case-insensitive match on document reference, title, or subject.
  - `department` (*optional*, string): Department filter.
  - `classification` (*optional*, string): Classification filter (e.g. `General`, `CONFIDENTIAL`).
  - `status` (*optional*, enum: `draft`, `under_review`, `active`, `archived`, `disposed`).
  - `sort_by` (*optional*, enum: `created_at`, `updated_at`, `title`, `document_reference`, default `created_at`).
  - `sort_order` (*optional*, enum: `asc`, `desc`, default `desc`).

- **Success Response (`200 OK`)**:
  ```json
  {
    "items": [
      {
        "id": "288870d0-e7de-486a-a208-9e0b7ab97078",
        "document_reference": "DOC-2026-793ECA3D",
        "title": "FY2026 Audit Report",
        "subject": "Internal Audit Findings",
        "department": "Finance",
        "classification": "CONFIDENTIAL",
        "mime_type": "application/pdf",
        "status": "active",
        "created_at": "2026-10-10T12:00:21.689177Z",
        "updated_at": "2026-10-10T12:00:21.689177Z",
        "version_count": 1
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1,
    "total_pages": 1
  }
  ```

#### 2. `GET /api/v1/documents/{document_id}`
Returns complete metadata and available version numbers for a specific document. Non-disclosing 404 is returned if the document does not exist or user lacks view permission.

- **Success Response (`200 OK`)**:
  ```json
  {
    "id": "288870d0-e7de-486a-a208-9e0b7ab97078",
    "document_reference": "DOC-2026-793ECA3D",
    "title": "FY2026 Audit Report",
    "subject": "Internal Audit Findings",
    "department": "Finance",
    "classification": "CONFIDENTIAL",
    "mime_type": "application/pdf",
    "status": "active",
    "created_by_id": "3c7a8550-432a-471f-a900-ed29952d3f1e",
    "creator": {
      "id": "3c7a8550-432a-471f-a900-ed29952d3f1e",
      "email": "dept.user@example.com",
      "full_name": "Development Department User",
      "department": "Finance"
    },
    "created_at": "2026-10-10T12:00:21.689177Z",
    "updated_at": "2026-10-10T12:00:21.689177Z",
    "archived_at": null,
    "available_versions": [1],
    "version_count": 1
  }
  ```

#### 3. `GET /api/v1/documents/{document_id}/versions`
Lists all revisions of a document sorted newest first (`version_number` descending). Never exposes internal disk storage paths or binary content.

- **Success Response (`200 OK`)**:
  ```json
  [
    {
      "id": "51bad228-7f89-438b-b19c-806bba23f159",
      "document_id": "288870d0-e7de-486a-a208-9e0b7ab97078",
      "version_number": 1,
      "original_filename": "test_audit_report.pdf",
      "mime_type": "application/pdf",
      "file_size_bytes": 55,
      "file_hash_sha256": "b3b26c39987af5e98d6d79bfd61894d03781d4ca720c21b2d51f8acb422976ce",
      "created_by_id": "3c7a8550-432a-471f-a900-ed29952d3f1e",
      "creator": {
        "id": "3c7a8550-432a-471f-a900-ed29952d3f1e",
        "email": "dept.user@example.com",
        "full_name": "Development Department User",
        "department": "Finance"
      },
      "created_at": "2026-10-10T12:00:21.689177Z"
    }
  ]
  ```

- **Error Responses**:
  - `401 Unauthorized`: Missing or invalid Bearer JWT.
  - `404 Not Found`: Returned when document does not exist OR when the user is unauthorized to view it (non-disclosing behavior).
  - `422 Unprocessable Entity`: Invalid pagination bounds (`page < 1`, `page_size > 100`), invalid enum, or invalid sort field.

#### 4. `POST /api/v1/documents/{document_id}/versions`
Uploads a new file version to an existing document. Requires the document to be in `draft` status. Preserves document identity and increments `version_number`.

- **Headers**:
  ```http
  Authorization: Bearer <access_token>
  X-Correlation-ID: <optional-correlation-id>
  ```
- **Form Data**:
  - `file` (*required*): Uploaded file binary (PDF, JPEG, PNG, TIFF up to 25 MB).

- **Role-Based Write-Access Matrix**:

| Role | Permitted Document Status | Department Scope | Permission |
| :--- | :--- | :--- | :--- |
| **Administrator** (`admin`) | `draft` only | All departments | Allowed |
| **Records Officer** (`records_officer`) | `draft` only | All departments | Allowed |
| **Department User** (`department_user`) | `draft` only | Assigned department only | Allowed (cross-department denied) |
| **Approver** (`approver`) | Any | Any | **Denied** (Approvers lack version write permissions) |
| **Auditor** (`auditor`) | Any | Any | **Denied** (Auditors are read-only) |
| **Read-Only User** (`read_only`) | Any | Any | **Denied** (Read-only users lack write permissions) |

- **Success Response (`201 Created`)**:
  ```json
  {
    "document_id": "288870d0-e7de-486a-a208-9e0b7ab97078",
    "document_reference": "DOC-2026-793ECA3D",
    "version_id": "8f3900a1-2b4c-4e5a-9090-1c3e5a7b9d10",
    "version_number": 2,
    "original_filename": "FY2026_Audit_Report_revised.pdf",
    "mime_type": "application/pdf",
    "file_size_bytes": 102400,
    "file_hash_sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "created_at": "2026-10-10T12:20:00.000000Z"
  }
  ```

- **Error Responses**:
  - `400 Bad Request`: Document is not in `draft` status, empty file, oversized file, or unsupported file magic bytes.
  - `401 Unauthorized`: Missing or invalid Bearer JWT.
  - `403 Forbidden`: User role or department lacks write authorization for this document.
  - `404 Not Found`: Document ID does not exist.
  - `409 Conflict`: Concurrent version conflict (`uq_document_version_number`).

- **cURL Example**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/documents/288870d0-e7de-486a-a208-9e0b7ab97078/versions" \
    -H "Authorization: Bearer <access_token>" \
    -F "file=@/path/to/updated_contract.pdf"
#### 5. `GET /api/v1/documents/{document_id}/versions/{version_number}/preview`
Streams the binary content of the requested document version inline for browser rendering.

- **Headers**:
  ```http
  Authorization: Bearer <access_token>
  ```
- **Supported Preview Formats**:
  - `application/pdf` (Adobe PDF)
  - `image/jpeg` (JPEG image)
  - `image/png` (PNG image)
  - `image/tiff` (TIFF image)
- **Security Headers & Inline Streaming**:
  - `Content-Disposition: inline; filename="<sanitized_filename>"`
  - `Content-Type: <media_type>`
  - `Content-Length: <size_in_bytes>`
  - `X-Content-Type-Options: nosniff` (mitigates MIME-sniffing exploits)
  - `Cache-Control: private, no-store` (prevents browser/proxy disk persistence)
  - `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox` (prevents script execution in document context)
  - `X-Frame-Options: SAMEORIGIN` (mitigates clickjacking while permitting application iframe previews)
- **Browser Compatibility Note for TIFF**:
  While TIFF (`image/tiff`) is a compliant archival format streamed by the API, modern browsers (Chrome, Firefox, Safari, Edge) do not natively render TIFF images within HTML `<img>` tags or iframes without third-party canvas or WebAssembly decoders (such as UTIF.js).
- **Error Responses**:
  - `401 Unauthorized`: Missing or invalid Bearer JWT.
  - `404 Not Found`: Document not found, version number not found, or user lacks view permission (non-disclosing 404).
  - `415 Unsupported Media Type`: Version format is not supported for inline preview (e.g. `text/plain`, `application/zip`).
- **cURL Example**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/documents/288870d0-e7de-486a-a208-9e0b7ab97078/versions/1/preview" \
    -H "Authorization: Bearer <access_token>" \
    -o "preview_document.pdf"
  ```

---

## OCR Engine & Text Extraction Service

The EDRMS text extraction service (`app.services.ocr.ocr_service`) provides modular, secure, and resource-bounded text extraction across archival document formats.

### OCR Engine & System Dependencies
- **Tesseract OCR (`5.5.0`)**: Open-source optical character recognition engine installed directly in the Docker container (`tesseract-ocr`, `tesseract-ocr-eng`).
- **Poppler Utilities (`poppler-utils` / `pdftoppm`)**: High-performance PDF rasterization library used to render scanned PDF pages into images for OCR.
- **Python Libraries**:
  - `pypdf`: Extracts embedded text streams directly from text-based PDFs without OCR overhead.
  - `pdf2image`: Renders PDF pages to in-memory PIL images via Poppler.
  - `pillow`: Image processing and multi-frame TIFF parsing.
  - `pytesseract`: Python binding to the system Tesseract binary.

### Supported Document Formats
| Format | MIME Type | Strategy | Behavior |
| :--- | :--- | :--- | :--- |
| **Text-Based PDF** | `application/pdf` | `embedded_pdf` | Extracts native text streams directly with zero OCR overhead. |
| **Scanned PDF** | `application/pdf` | `ocr_pdf` | Automatically falls back to page rendering + Tesseract OCR when embedded text is absent. |
| **JPEG** | `image/jpeg` | `ocr_image` | Extracts text via Tesseract OCR. |
| **PNG** | `image/png` | `ocr_image` | Extracts text via Tesseract OCR. |
| **TIFF** | `image/tiff` | `ocr_image` | Extracts text across all frames/pages via Tesseract OCR. |

### How Text Extraction is Invoked
The service is invoked programmatically via its Python interface:
```python
from app.database import SessionLocal
from app.models.document import DocumentVersion
from app.services.ocr import ocr_service

db = SessionLocal()
version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()

# Extracts text safely and updates version.extracted_text in PostgreSQL
result = ocr_service.process_and_persist_version(db=db, version=version)
print(f"Extracted {result.char_count} chars via {result.strategy.value}")
```

### Resource & Processing Limits
- **Page Limit (`OCR_MAX_PAGES`)**: Defaults to **50 pages** per document to prevent memory exhaustion from massive files.
- **File Size Limit (`OCR_MAX_FILE_SIZE_BYTES`)**: Defaults to **25 MB**.
- **Execution Timeout (`OCR_TIMEOUT_SECONDS`)**: Defaults to **30 seconds** per document.
- **Temp Storage Cleanup**: All rasterized page buffers and intermediate files are created in isolated temporary directories and cleaned up immediately upon completion or failure.

### Error Handling & Safety
- **No Content Logging**: Sensitive extracted text is never printed to logs.
- **Encrypted / Password-Protected PDFs**: Detected gracefully via `EncryptedFileError`.
- **Corrupt Binaries**: Detected and raised via `CorruptFileError`.
- **Preservation on Failure**: If OCR fails or raises an error, existing valid `extracted_text` in the database is never overwritten or nulled out.
- **Storage Containment**: Only reads files via `storage_service.resolve_storage_path` to guarantee sandbox containment and prevent directory traversal.

### Automatic OCR Lifecycle & Durable Extraction Queue

Text extraction is automatically registered in a persistent PostgreSQL queue (`ocr_jobs`) upon every new document upload (`POST /api/v1/documents/upload`) and every new version upload (`POST /api/v1/documents/{document_id}/versions`).

#### 1. Processing Lifecycle
- **Step 1: Ingestion & Transactional Enqueueing**: The uploaded binary is staged, validated, hashed (SHA-256), and finalized to private disk storage (`/var/edrms/storage/uploads/`). In the **exact same database transaction**, the document, the `DocumentVersion` (`extraction_status = 'pending'`), and the durable `OCRJob` (`status = 'queued'`) are committed to PostgreSQL. If upload fails or is aborted, no orphaned job is enqueued.
- **Step 2: Immediate Response**: Upload endpoints return HTTP 201 immediately with `extraction_status: "pending"`, preventing slow OCR processing from blocking the client or holding request threads.
- **Step 3: Durable Worker Processing**: The dedicated worker daemon (`edrms-worker`) atomically claims queued jobs using PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`, sets the lease expiration, runs the extraction pipeline, and updates both job and version records.
- **Step 4: Completion / Error Recording**:
  - **Success**: Version status transitions to `'completed'`, `extracted_text` is populated, `extraction_completed_at` is stamped, `extraction_error` is set to `None`, and the `OCRJob` status transitions to `'completed'`.
  - **Transient Failure**: If a recoverable error occurs (e.g. temporary I/O delay), `attempt_count` is incremented and `next_retry_at` is scheduled using exponential backoff (`delay = base_delay * 2^(attempt - 1)`).
  - **Permanent Failure / Exhaustion**: When maximum retry attempts are exhausted or a non-retryable format error occurs (`UnsupportedFormatError`, `CorruptFileError`, `EncryptedFileError`), the job and version status transition to `'failed'`, `last_error` is recorded, and any existing `extracted_text` remains untouched.

#### 2. Extraction Status States
| Status | Meaning |
| :--- | :--- |
| `pending` | Upload succeeded and committed; document version is queued for text extraction. |
| `processing` | Worker has claimed the version lease and extraction is currently in progress. |
| `completed` | Text extraction completed successfully; extracted text is stored in `extracted_text`. |
| `failed` | Extraction failed or file was invalid/corrupt/encrypted; reason stored in `extraction_error`. |

#### 3. Client Status Visibility
Clients can monitor extraction progress by querying the document versions metadata endpoint:
`GET /api/v1/documents/{document_id}/versions`

Each version object in the response includes:
- `extraction_status`: `"pending" | "processing" | "completed" | "failed"`
- `extraction_completed_at`: ISO 8601 UTC timestamp of completion (or `null`)
- `extraction_error`: Sanitized error description if failed (or `null`)

---

## Durable OCR Job Queue & Worker Daemon

To guarantee that OCR operations survive backend process restarts and container deployments, EDRMS implements a persistent database queue pattern backed by PostgreSQL row-level locking.

### 1. `ocr_jobs` Database Schema
Managed by Alembic revision `26af65844cc3`:
- `id` (UUID): Unique job identifier.
- `document_version_id` (UUID, Foreign Key to `document_versions.id`, Unique): Enforces at most one active job pipeline per version.
- `status` (Enum): `queued`, `running`, `completed`, `failed`.
- `attempt_count` (Integer): Number of attempted executions (defaults to 0).
- `max_attempts` (Integer): Maximum allowed retries (defaults to `OCR_WORKER_MAX_ATTEMPTS`, default: 3).
- `next_retry_at` (DateTime UTC): Earliest timestamp when the job may be claimed for another attempt.
- `lease_expires_at` (DateTime UTC): Active lease deadline for the claiming worker.
- `worker_id` (String): Identifier of the worker holding the lease.
- `started_at` / `completed_at` / `last_error`: Observability and audit timestamps.
- **Indexes**: Compound index on `(status, next_retry_at)` and single index on `lease_expires_at`.

### 2. Concurrency & Atomic Claiming
- Jobs are selected and transitioned to `running` using `SELECT ... FOR UPDATE SKIP LOCKED`.
- Multiple concurrent worker containers can process the queue simultaneously without collisions, duplicate executions, or distributed lock overhead.

### 3. Lease Expiration & Crash Recovery
- Workers acquire a time-bounded lease (`OCR_WORKER_LEASE_SECONDS`, default: 60s).
- If a worker crashes or is abruptly killed (`SIGKILL`) while holding a job:
  - The lease expires (`lease_expires_at < utc_now()`).
  - Active workers automatically scan and reclaim expired leases during each poll cycle.
  - If attempts remain, the job is reset to `queued` with backoff; if exhausted, marked `failed`.

### 4. Exponential Backoff & Permanent Failure Handling
- **Transient Failures**: Retried with exponential delay:
  $$\text{delay} = \text{OCR\_WORKER\_BASE\_RETRY\_DELAY\_SECONDS} \times 2^{(\text{attempt} - 1)}$$
- **Permanent Failures**: Non-retryable errors (`CorruptFileError`, `EncryptedFileError`, `UnsupportedFormatError`) immediately transition to `failed` without wasting retry attempts.

### 5. Worker Service Operation
- The worker daemon runs as a dedicated Docker Compose service (`edrms-worker`):
  ```bash
  docker compose logs -f worker
  ```
- Standalone CLI invocation:
  ```bash
  docker exec edrms-worker python -m app.worker
  ```
- Configuration options in `.env`:
  - `OCR_WORKER_POLL_INTERVAL_SECONDS`: Polling interval when queue is idle (default: `2.0`).
  - `OCR_WORKER_LEASE_SECONDS`: Lease duration per claimed job (default: `60`).
  - `OCR_WORKER_MAX_ATTEMPTS`: Maximum retry attempts before permanent failure (default: `3`).
  - `OCR_WORKER_BASE_RETRY_DELAY_SECONDS`: Base retry backoff interval in seconds (default: `5.0`).

---

## OCR Job Monitoring and Controlled Retry APIs

EDRMS provides dedicated operational endpoints for systems administrators to monitor asynchronous OCR queue health, inspect job execution history, and safely requeue failed extraction tasks.

### Access Control & Security Policies
- **Role Restriction**: Access is restricted strictly to the **Administrator** (`admin`) role.
- **Unauthorized Roles**: Requests by `records_officer`, `department_user`, `approver`, `auditor`, or `read_only` users are immediately rejected with **403 Forbidden** (`"Operation restricted to administrator role."`) and audited with `outcome = DENIED`.
- **Zero Information Leakage**: Endpoints expose operational timestamps, statuses, and sanitized failure reasons only. File contents, binary storage keys, server absolute paths, extracted text, and stack traces are never exposed.

---

### Endpoints Specification

#### 1. `GET /api/v1/ocr/jobs`
Returns paginated operational metadata for OCR jobs. Filtering and pagination are executed entirely in PostgreSQL.

**Query Parameters**:
| Parameter | Type | Required | Default | Validation / Description |
| :--- | :--- | :--- | :--- | :--- |
| `page` | integer | No | `1` | `ge=1` (1-indexed page number). |
| `page_size` | integer | No | `20` | `ge=1, le=100` (Items per page). |
| `status` | string | No | `None` | Filter by `queued`, `running`, `completed`, or `failed`. |
| `document_version_id` | UUID | No | `None` | Filter by specific document version identifier. |
| `created_from` | datetime | No | `None` | Filter jobs created at or after UTC timestamp (ISO 8601). |
| `created_to` | datetime | No | `None` | Filter jobs created at or before UTC timestamp (ISO 8601). Validates `created_from <= created_to`. |

**Example Request**:
```http
GET /api/v1/ocr/jobs?status=failed&page=1&page_size=20 HTTP/1.1
Host: localhost:8000
Authorization: Bearer <admin_token>
```

**Example Response (`200 OK`)**:
```json
{
  "items": [
    {
      "id": "e4b2d354-9d10-410a-8dcf-3f2b6045d221",
      "document_version_id": "c1f7a630-18e4-41d3-bc8e-20d3f820ae3b",
      "status": "failed",
      "attempt_count": 3,
      "max_attempts": 3,
      "created_at": "2026-10-10T13:40:00Z",
      "updated_at": "2026-10-10T13:42:15Z",
      "next_retry_at": "2026-10-10T13:42:15Z",
      "started_at": "2026-10-10T13:42:00Z",
      "completed_at": "2026-10-10T13:42:15Z",
      "last_error": "Worker lease expired and retry budget exhausted"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "total_pages": 1
}
```

---

#### 2. `GET /api/v1/ocr/jobs/{job_id}`
Returns operational metadata for a single OCR job.

**Example Request**:
```http
GET /api/v1/ocr/jobs/e4b2d354-9d10-410a-8dcf-3f2b6045d221 HTTP/1.1
Host: localhost:8000
Authorization: Bearer <admin_token>
```

**Example Response (`200 OK`)**:
```json
{
  "id": "e4b2d354-9d10-410a-8dcf-3f2b6045d221",
  "document_version_id": "c1f7a630-18e4-41d3-bc8e-20d3f820ae3b",
  "status": "failed",
  "attempt_count": 3,
  "max_attempts": 3,
  "created_at": "2026-10-10T13:40:00Z",
  "updated_at": "2026-10-10T13:42:15Z",
  "next_retry_at": "2026-10-10T13:42:15Z",
  "started_at": "2026-10-10T13:42:00Z",
  "completed_at": "2026-10-10T13:42:15Z",
  "last_error": "Worker lease expired and retry budget exhausted"
}
```

---

#### 3. `POST /api/v1/ocr/jobs/{job_id}/retry`
Requeues an existing failed job for execution by the worker pool.

**Controlled Retry Policy**:
1. **Terminal State Gate**: Only jobs in the `failed` state may be retried. Requeuing `queued`, `running`, or `completed` jobs is rejected with **409 Conflict** (`"Cannot retry job in '<status>' status. Only failed jobs can be retried."`).
2. **Retry Limit Policy**:
   - If `attempt_count < max_attempts`, the administrator can requeue the job directly.
   - If `attempt_count >= max_attempts`, the configured retry limit is enforced and the request is rejected with **400 Bad Request** (`"Retry limit reached: job has reached maximum attempts (3/3). Explicit administrator authorization is required via reset_attempts=true."`).
   - Supplying `?reset_attempts=true` explicitly resets `attempt_count = 0`, authorizing a fresh retry cycle. This override is permanently recorded in the audit log.
3. **Resource Verification**: Verifies that both the database `DocumentVersion` row and the physical binary on disk exist. Missing resources return **404 Not Found**.
4. **Preservation of Existing Text**: Any previously extracted text on the document version is untouched until new extraction successfully succeeds.
5. **Concurrency Safety**: Uses PostgreSQL `SELECT ... FOR UPDATE` row locking to eliminate race conditions between concurrent admin retry requests.
6. **Mandatory Audit & Atomic Rollback**: If the mandatory audit event cannot be recorded, the entire database transaction is safely rolled back, guaranteeing the job is not requeued while the client receives an error.

**Example Request**:
```http
POST /api/v1/ocr/jobs/e4b2d354-9d10-410a-8dcf-3f2b6045d221/retry?reset_attempts=true HTTP/1.1
Host: localhost:8000
Authorization: Bearer <admin_token>
```

**Example Response (`200 OK`)**:
```json
{
  "id": "e4b2d354-9d10-410a-8dcf-3f2b6045d221",
  "document_version_id": "c1f7a630-18e4-41d3-bc8e-20d3f820ae3b",
  "status": "queued",
  "attempt_count": 0,
  "max_attempts": 3,
  "created_at": "2026-10-10T13:40:00Z",
  "updated_at": "2026-10-10T14:00:00Z",
  "next_retry_at": "2026-10-10T14:00:00Z",
  "started_at": null,
  "completed_at": null,
  "last_error": null
}
```

---

### Operational Troubleshooting Guide

| Issue / Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| Job stuck in `failed` with `"Worker lease expired and retry budget exhausted"` | A worker claimed the job and crashed, or execution exceeded the lease timeout, and maximum retries were exhausted. | Inspect worker logs (`docker compose logs worker`), confirm system resources, and issue `POST /api/v1/ocr/jobs/{id}/retry?reset_attempts=true`. |
| Job failed with `"Encrypted PDFs are not supported"` | The uploaded PDF has password protection or certificate encryption. | Permanent failure. Re-upload an unencrypted PDF revision. |
| Job failed with `"Corrupt or unreadable file"` | Uploaded binary has invalid format structure or truncated bytes. | Permanent failure. Verify source file and re-upload valid revision. |
| Retry returns `404 Associated document file not found in storage` | Stored binary was deleted or storage volume was disconnected. | Restore binary to `/var/edrms/storage/` or upload a new version. |
| Non-admin receives `403 Forbidden` | Operational endpoints are restricted to `admin`. | Use Administrator credentials (`admin@example.com`). |

---

## Full-Text Document Search

The platform includes a dedicated, secure full-text search endpoint powered by PostgreSQL native full-text indexing and the text extracted from documents (`DocumentVersion.extracted_text`).

### Endpoint Specification
`GET /api/v1/search`

**Headers**:
- `Authorization: Bearer <jwt_access_token>` (Required)

### Query Parameters
| Parameter | Type | Required | Default | Validation / Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `query` | string | **Yes** | — | Min 1 char, max 200 chars (trimmed). Non-empty. | Search query. Supports natural words and `"exact phrases"`. |
| `page` | integer | No | `1` | `ge=1` | 1-indexed page number. |
| `page_size` | integer | No | `20` | `ge=1`, `le=100` | Number of results per page. |
| `department` | string | No | `None` | Max 100 chars | Exact case-insensitive department filter. |
| `classification` | string | No | `None` | Max 100 chars | Exact case-insensitive classification filter. |
| `status` | string | No | `None` | `draft`, `under_review`, `active`, `archived`, `disposed` | Lifecycle status filter. |
| `sort_order` | string | No | `relevance` | `relevance`, `created_desc`, `created_asc` | Ordering strategy. Defaults to relevance rank (`ts_rank`). |

### Searchable Fields & PostgreSQL Indexing Strategy
Search operates concurrently across document metadata and extracted version contents:
- **Metadata Weight A (High)**: `title` and `document_reference` (indexed raw and space-separated).
- **Metadata Weight B (Medium)**: `subject` (abstract/description).
- **Extracted Content (Version)**: `DocumentVersion.extracted_text` across all versions.

#### PostgreSQL Indexing
Accelerated by two targeted GIN expression indexes (Alembic migration `d9f158d91b0f`):
1. `ix_digital_documents_fts`:
   ```sql
   CREATE INDEX ix_digital_documents_fts ON digital_documents USING gin(
       (
           setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
           setweight(to_tsvector('english', coalesce(document_reference, '') || ' ' || replace(coalesce(document_reference, ''), '-', ' ')), 'A') ||
           setweight(to_tsvector('english', coalesce(subject, '')), 'B')
       )
   );
   ```
2. `ix_document_versions_extracted_text_fts`:
   ```sql
   CREATE INDEX ix_document_versions_extracted_text_fts ON document_versions USING gin(
       (to_tsvector('english', coalesce(extracted_text, '')))
   );
   ```

### Query Parser & Stop-Word / Punctuation Handling
- Parses search text using PostgreSQL `websearch_to_tsquery('english', query)`. Supports natural terms (`cyber security`), boolean operators, and quoted phrases (`"liquidated damages"`).
- **Stop-words & Punctuation**: If a query consists only of punctuation (`...`, `???`) or English stop-words (`the and or of`), the query is handled safely and returns `200 OK` with `0` results without raising SQL errors or leaking internal exceptions.

### Authorization & Information Disclosure Prevention
Search enforces the identical multi-dimensional access policies defined in `DocumentAuthorizationService` (Task 3.5):
- Scopes results strictly at the database level (`WHERE` clause) before computing counts, rankings, snippets, or pagination.
- **Role Scopes**:
  - `admin` & `records_officer`: Cross-department access.
  - `department_user`: Restricted strictly to documents in own department.
  - `approver`: Restricted to documents in own department or documents created by the user.
  - `auditor`: Restricted to documents in assigned audit department.
  - `read_only`: Restricted to non-confidential documents in own department or created by user.
- Inaccessible documents are excluded entirely from `total` counts, snippets, and rankings, preventing discovery of classified records by guessing terms.

### Relevance Ranking & Excerpt Snippets
- **Relevance Scoring**: Combines metadata `ts_rank` and highest version `ts_rank` rounded to 4 decimals, with secondary deterministic sort (`d.created_at DESC, d.id DESC`).
- **Snippet Excerpts**: Generated via `ts_headline` on the best matching version content (or matching metadata). Fully HTML-escaped with safe bold tags (`<b>...</b>`) and capped at 500 characters.

### Mandatory Audit Logging
- Every search request is recorded in `audit_logs` (`action = 'document.search'`).
- Logs actor ID, result count, pagination parameters, and filter flags.
- **Privacy Guarantee**: Raw query strings and document contents are strictly excluded from audit details.
- If mandatory audit logging fails, the search request fails with HTTP 500.

### Example Request and Response
#### Request
```http
GET /api/v1/search?query=liquidated+damages&department=Legal&page=1&page_size=20 HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

#### Response (200 OK)
```json
{
  "items": [
    {
      "id": "e283be31-1634-4b55-a550-ee94ec463c20",
      "document_reference": "DOC-2026-0042",
      "title": "Vendor Service Level Agreement",
      "subject": "Supply and maintenance contract",
      "department": "Legal",
      "classification": "General",
      "mime_type": "application/pdf",
      "status": "active",
      "created_at": "2026-10-10T11:20:00Z",
      "updated_at": "2026-10-10T11:25:00Z",
      "matching_version_numbers": [1],
      "snippet": "Original legacy clause regarding <b>liquidated</b> <b>damages</b> of five percent per month.",
      "relevance_score": 0.0892
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "total_pages": 1
}
```

### Expected Error Responses
- `401 Unauthorized`: Missing, expired, or invalid Bearer JWT.
- `422 Unprocessable Entity`: Empty/whitespace query, query exceeding 200 characters, invalid pagination parameters (`page < 1`, `page_size > 100`), or invalid status enum value.
- `500 Internal Server Error`: Audit logging failure or unexpected database exception. Raw database error messages are never exposed.

---

## Document Review and Approval Workflow (Task 5.1 Foundation)

EDRMS includes a secure, state-governed document review lifecycle enabling document creators to submit draft documents for formal review.

### 1. Workflow Data Models
- **`review_workflows`**: Durable record tracking review lifecycle for a document.
  - Fields: `id` (UUID PK), `document_id` (FK to `digital_documents.id`), `state` (`pending`, `approved`, `rejected`, `cancelled`), `submitter_id` (FK to `users.id`), `submission_comments` (Text), `submitted_at`, `created_at`, `updated_at`.
  - Enforces partial unique constraint: At most one active (`pending`) workflow per document (`uq_active_review_workflow_per_document` where `state = 'pending'`).
- **`review_assignments`**: Explicit approver assignment linked to a review workflow.
  - Fields: `id` (UUID PK), `workflow_id` (FK to `review_workflows.id`), `assigned_approver_id` (FK to `users.id`), `assigned_at`, `decision` (reserved for Task 5.2), `decided_at`, `decision_comments`.

### 2. Submission Endpoint
`POST /api/v1/documents/{document_id}/submit-for-review`

#### Business and Authorization Rules:
- **Authentication**: Requires a valid Bearer JWT.
- **Allowed Submitter Roles**:
  - `admin` and `records_officer`: Can submit draft documents across departments.
  - `department_user`: Can submit draft documents belonging to their own department.
  - `approver`, `auditor`, `read_only`: Strictly denied (HTTP 403 Forbidden).
- **Document Status**:
  - Only documents in `draft` status may be submitted. Submitting documents in other lifecycle states (`under_review`, `active`, `archived`) returns HTTP 409 Conflict.
  - Upon submission, document status transitions atomically from `draft` to `under_review`.
- **Approver Eligibility**:
  - Assigned user must be active and hold the `approver` role (HTTP 400 Bad Request otherwise).
  - Approver must belong to the document's owning department (no cross-department review).
  - Submitter cannot assign themselves as approver.
  - Missing or ambiguous department configurations are rejected by default.
- **Concurrency & Idempotence**:
  - Acquires row-level exclusive lock (`SELECT ... FOR UPDATE`) on the document row during the submission transaction.
  - Partial unique index and database check reject duplicate or overlapping active workflows (HTTP 409 Conflict).
- **Mandatory Audit Logging**:
  - Success event `workflow.submit_for_review` records workflow ID, assignment ID, approver details, and comments.
  - Access denial event `workflow.submit_for_review.denied` records failure reason.
  - Atomic rollback: If the mandatory audit log write fails, the entire transaction is rolled back and returns HTTP 500.

#### Request Example
```http
POST /api/v1/documents/4c735d01-556a-46be-926e-d146ec6d0ac1/submit-for-review HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "approver_id": "33c67387-3014-4f34-8dde-ba606b688212",
  "comments": "Please review the updated service agreement contract."
}
```

#### Response Example (201 Created)
```json
{
  "workflow_id": "7832bc42-6e54-4a21-9d10-85fb32b8cd90",
  "document_id": "4c735d01-556a-46be-926e-d146ec6d0ac1",
  "document_reference": "DOC-2026-0042",
  "document_status": "under_review",
  "workflow_state": "pending",
  "submitter_id": "94344d50-f3e3-452e-b3d5-a6425df24e68",
  "submitted_at": "2026-10-10T14:25:00Z",
  "comments": "Please review the updated service agreement contract.",
  "assignment": {
    "id": "a90df214-7221-419b-a3be-bc287f329cb1",
    "workflow_id": "7832bc42-6e54-4a21-9d10-85fb32b8cd90",
    "assigned_approver_id": "33c67387-3014-4f34-8dde-ba606b688212",
    "assigned_at": "2026-10-10T14:25:00Z",
    "decision": null,
    "decided_at": null,
    "decision_comments": null
  }
}
```

### 3. Approver Review Inbox (Task 5.2)
`GET /api/v1/workflows/my-assignments`

- **Role Requirement**: Strictly restricted to users with the `approver` role.
- **SQL-Level Filtering**: Evaluates assignments directly in PostgreSQL, returning only assignments explicitly assigned to the authenticated approver. Approvers cannot view other approvers' assignments even within the same department.
- **Department Alignment**: Applies document department matching to verify the approver is in the document's owning department.
- **Safe Metadata**: Returns workflow state, submission timestamp, submitter display info, and safe document summary (no file binaries, raw storage keys, or OCR text).

#### Example Request
```http
GET /api/v1/workflows/my-assignments?page=1&page_size=20 HTTP/1.1
Host: localhost:8000
Authorization: Bearer <approver_jwt>
```

#### Example Response (200 OK)
```json
{
  "items": [
    {
      "assignment_id": "a90df214-7221-419b-a3be-bc287f329cb1",
      "workflow_id": "7832bc42-6e54-4a21-9d10-85fb32b8cd90",
      "workflow_state": "pending",
      "submitted_at": "2026-10-10T14:25:00Z",
      "submission_comments": "Please review the updated service agreement contract.",
      "submitter": {
        "id": "94344d50-f3e3-452e-b3d5-a6425df24e68",
        "email": "analyst@example.com",
        "full_name": "Jane Analyst",
        "department": "Legal"
      },
      "document": {
        "id": "4c735d01-556a-46be-926e-d146ec6d0ac1",
        "document_reference": "DOC-2026-0042",
        "title": "Vendor Service Level Agreement",
        "department": "Legal",
        "classification": "Internal",
        "status": "under_review",
        "created_at": "2026-10-10T14:20:00Z"
      }
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### 4. Workflow Detail Retrieval (Task 5.2)
`GET /api/v1/workflows/{workflow_id}`

- **Access Rules**: Permitted for the explicitly assigned approver, or administrative roles (`admin`, `records_officer`) for governance oversight.
- **Non-Disclosing 404**: Unassigned approvers and unauthorized roles (Department User, Auditor, Read-Only) receive `404 Not Found` to prevent workflow ID enumeration.
- **Metadata**: Returns full review history, assignments, submitter details, and latest document version metadata.

### 5. Review Decision: Approval, Rejection, and Activation (Task 5.2)
`POST /api/v1/workflows/{workflow_id}/decision`

Accepts a decision from the assigned approver:
- `decision`: `"approved"` or `"rejected"`.
- `comments`: Optional text for approval; strictly required (non-empty) for rejection (HTTP 422 if omitted or blank).

#### Approval Rules and Lifecycle:
- Workflow must be `pending` and document must be `under_review`.
- Document must have at least one valid registered version.
- Transitions workflow state to `approved`.
- Transitions document lifecycle status to `active` in the same database transaction.
- Audit event `workflow.approved` recorded with full metadata.

#### Rejection Rules and Lifecycle:
- Rejection requires an explicit, non-empty comment explaining why the document was returned.
- Transitions workflow state to `rejected`.
- Returns document lifecycle status to `draft` in the same database transaction, enabling authoring correction and re-upload.
- Audit event `workflow.rejected` recorded with full metadata.

#### Concurrency and Atomic Guarantees:
- Uses `SELECT ... FOR UPDATE` row locks on both `ReviewWorkflow` and `DigitalDocument`.
- Concurrent or duplicate decision attempts deterministically resolve to 1 successful decision and 1 `409 Conflict`.
- Mandatory audit logging guarantees atomic rollback if audit write fails (`AuditWriteError` -> HTTP 500).

#### Example Request (Rejection)
```http
POST /api/v1/workflows/7832bc42-6e54-4a21-9d10-85fb32b8cd90/decision HTTP/1.1
Host: localhost:8000
Authorization: Bearer <approver_jwt>
Content-Type: application/json

{
  "decision": "rejected",
  "comments": "Clause 4.2 requires indemnity cap clarification."
}
```

#### Example Response (200 OK)
```json
{
  "workflow_id": "7832bc42-6e54-4a21-9d10-85fb32b8cd90",
  "document_id": "4c735d01-556a-46be-926e-d146ec6d0ac1",
  "document_reference": "DOC-2026-0042",
  "document_status": "draft",
  "workflow_state": "rejected",
  "decision": "rejected",
  "decided_by_id": "33c67387-3014-4f34-8dde-ba606b688212",
  "decided_at": "2026-10-10T14:30:00Z",
  "comments": "Clause 4.2 requires indemnity cap clarification."
}
```

### 6. Workflow History and Decision Traceability (Task 5.3)
`GET /api/v1/documents/{document_id}/workflow-history`

Provides a complete, chronological audit trail of all review attempts, approver assignments, and decisions for a document.

#### Requirements and Behavior:
- **Authentication**: Requires a valid Bearer JWT.
- **Authorization Scoping**:
  - `admin` and `records_officer`: Can view workflow history across all documents.
  - `department_user`: Can view workflow history for documents in their assigned department or documents they created.
  - `approver`: Can view history only for documents within their department where they have at least one explicit assignment. Only reveals workflow attempts to which that approver was explicitly assigned (preventing enumeration or visibility into other approvers' private assignments).
  - Unauthorized roles or unassigned approvers receive a non-disclosing `404 Not Found`.
- **Chronological Ordering**: Returned oldest first (`submitted_at ASC`, `id ASC`), preserving the full provenance chain.
- **Resubmission Lifecycle**:
  - When a document is rejected and returned to `draft`, a subsequent submission creates a distinct review workflow attempt.
  - The history endpoint displays both attempts, retaining the original rejection comments alongside the new workflow attempt.
- **Empty State**: If an authorized document has never been submitted for review, returns HTTP 200 with `total_attempts: 0` and `attempts: []`.
- **Sensitive Data Isolation**: Never exposes password hashes, internal storage paths, file contents, or OCR extracted text.

#### Example Request
```http
GET /api/v1/documents/4c735d01-556a-46be-926e-d146ec6d0ac1/workflow-history HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
```

#### Example Response (200 OK)
```json
{
  "document_id": "4c735d01-556a-46be-926e-d146ec6d0ac1",
  "document_reference": "DOC-2026-0042",
  "document_status": "active",
  "total_attempts": 2,
  "attempts": [
    {
      "workflow_id": "19a2e612-4a11-4cb5-87d9-c081e74f1b20",
      "state": "rejected",
      "submitted_at": "2026-10-10T12:00:00Z",
      "submission_comments": "Initial contract submission for review",
      "submitter": {
        "id": "94344d50-f3e3-452e-b3d5-a6425df24e68",
        "email": "analyst@example.com",
        "full_name": "Jane Analyst",
        "department": "Legal"
      },
      "assignments": [
        {
          "id": "e210ac45-1234-45aa-98bb-a1b2c3d4e5f6",
          "workflow_id": "19a2e612-4a11-4cb5-87d9-c081e74f1b20",
          "assigned_approver": {
            "id": "33c67387-3014-4f34-8dde-ba606b688212",
            "email": "approver@example.com",
            "full_name": "Senior Legal Approver",
            "department": "Legal"
          },
          "assigned_at": "2026-10-10T12:00:00Z",
          "decision": "rejected",
          "decided_at": "2026-10-10T12:30:00Z",
          "decision_comments": "Missing clause 4.2 indemnity specification."
        }
      ]
    },
    {
      "workflow_id": "7832bc42-6e54-4a21-9d10-85fb32b8cd90",
      "state": "approved",
      "submitted_at": "2026-10-10T14:00:00Z",
      "submission_comments": "Resubmitted with clause 4.2 added",
      "submitter": {
        "id": "94344d50-f3e3-452e-b3d5-a6425df24e68",
        "email": "analyst@example.com",
        "full_name": "Jane Analyst",
        "department": "Legal"
      },
      "assignments": [
        {
          "id": "a90df214-7221-419b-a3be-bc287f329cb1",
          "workflow_id": "7832bc42-6e54-4a21-9d10-85fb32b8cd90",
          "assigned_approver": {
            "id": "33c67387-3014-4f34-8dde-ba606b688212",
            "email": "approver@example.com",
            "full_name": "Senior Legal Approver",
            "department": "Legal"
          },
          "assigned_at": "2026-10-10T14:00:00Z",
          "decision": "approved",
          "decided_at": "2026-10-10T14:30:00Z",
          "decision_comments": "Clause 4.2 verified. Approved."
        }
      ]
    }
  ]
}
```

### 7. Workflow Cancellation and Submission Withdrawal (Task 5.4)

#### `POST /api/v1/workflows/{workflow_id}/cancel`
Allows an authorized user (the original submitter, an Administrator, or a Records Officer) to withdraw a pending review workflow and return the associated document to `draft` status.

- **Authentication**: Requires a valid Bearer JWT.
- **Role Permissions**:
  - `admin` and `records_officer`: May cancel pending workflows across all departments.
  - `department_user`: May cancel ONLY if they are the original submitter (`workflow.submitter_id == user.id`) and belong to the document's owning department. Other department users receive a non-disclosing `404 Not Found`.
  - `approver`: Cannot cancel or withdraw review workflows (restricted strictly to decision-making).
  - `auditor` and `read_only`: Denied cancellation access (non-disclosing `404 Not Found`).
- **Preconditions**:
  - Workflow `state` must be `pending`. If already `approved`, `rejected`, or `cancelled`, returns `409 Conflict`.
  - Document `status` must be `under_review`. If not, returns `409 Conflict`.
- **Payload Requirements**:
  - `comments` (*required*): Non-empty string explaining the reason for cancellation or withdrawal (1 to 1000 characters). Whitespace-only strings are rejected with `422 Unprocessable Entity`.
- **Concurrency & Transaction Safety**:
  - Evaluated with row-level locks (`SELECT FOR UPDATE`) on `review_workflows` and `digital_documents`.
  - If a concurrent approval/rejection decision is in flight, row locking ensures one transaction succeeds and the other receives `409 Conflict`.
  - Atomically records cancellation metadata:
    - `review_workflows.state` = `cancelled`
    - `review_workflows.cancelled_by_id` = `<current_user.id>`
    - `review_workflows.cancelled_at` = UTC timestamp
    - `review_workflows.cancellation_comments` = `<comments>`
    - `digital_documents.status` = `draft`
  - Mandatory audit event `workflow.cancelled` logged via `AuditService.log_from_request` with `raise_on_failure=True`. Failure rolls back all database modifications and returns `500 Internal Server Error`.

##### Request Example:
```http
POST /api/v1/workflows/19a2e612-4a11-4cb5-87d9-c081e74f1b20/cancel HTTP/1.1
Host: localhost:8000
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "comments": "Withdrawing document submission to revise liability clauses before final review."
}
```

##### Response Example (`200 OK`):
```json
{
  "workflow_id": "19a2e612-4a11-4cb5-87d9-c081e74f1b20",
  "document_id": "7832bc42-6e54-4a21-9d10-85fb32b8cd90",
  "document_reference": "DOC-2026-9F81E32A",
  "document_status": "draft",
  "workflow_state": "cancelled",
  "cancelled_by_id": "94344d50-f3e3-452e-b3d5-a6425df24e68",
  "cancelled_at": "2026-10-10T14:45:00.123456Z",
  "comments": "Withdrawing document submission to revise liability clauses before final review."
}
```

##### Cancellation Metadata in Workflow History:
When `GET /api/v1/documents/{document_id}/workflow-history` is invoked, cancelled workflow attempts include:
```json
{
  "workflow_id": "19a2e612-4a11-4cb5-87d9-c081e74f1b20",
  "state": "cancelled",
  "submitted_at": "2026-10-10T12:00:00Z",
  "submission_comments": "Initial review request",
  "submitter": {
    "id": "94344d50-f3e3-452e-b3d5-a6425df24e68",
    "email": "analyst@example.com",
    "full_name": "Jane Analyst",
    "department": "Legal"
  },
  "cancelled_by": {
    "id": "94344d50-f3e3-452e-b3d5-a6425df24e68",
    "email": "analyst@example.com",
    "full_name": "Jane Analyst",
    "department": "Legal"
  },
  "cancelled_at": "2026-10-10T14:45:00.123456Z",
  "cancellation_comments": "Withdrawing document submission to revise liability clauses before final review.",
  "assignments": [...]
}
```

### 8. In-App Workflow Notifications (Task 5.5)

Database-backed in-app notification system delivering timely, secure updates when document workflow lifecycle transitions occur.

#### 1. Notification Types & Triggering Workflow Events
- `workflow_submitted`:
  - **Trigger**: Document is submitted for review via `POST /api/v1/documents/{document_id}/submit-for-review`.
  - **Recipient**: The explicitly assigned approver.
  - **Payload**: Title and message contain the document reference (`DOC-YYYY-XXXXXXXX`) and title, with navigable IDs (`document_id`, `workflow_id`). No storage keys or raw file contents.
- `workflow_approved`:
  - **Trigger**: Workflow is approved via `POST /api/v1/workflows/{workflow_id}/decision` (`decision: "approved"`).
  - **Recipient**: The original workflow submitter.
  - **Payload**: Informs submitter that the document has been approved and activated.
- `workflow_rejected`:
  - **Trigger**: Workflow is rejected via `POST /api/v1/workflows/{workflow_id}/decision` (`decision: "rejected"`).
  - **Recipient**: The original workflow submitter.
  - **Payload**: Safe notification indicating review feedback is available in the workflow history. Confidential decision comments are not duplicated into the notification message.
- `workflow_cancelled`:
  - **Trigger**: Pending workflow is withdrawn/cancelled via `POST /api/v1/workflows/{workflow_id}/cancel`.
  - **Recipient**: The assigned review approvers.
  - **Payload**: Informs approver that the review request has been withdrawn.

#### 2. Notification API Endpoints

##### `GET /api/v1/notifications`
Retrieves a paginated list of notifications belonging exclusively to the authenticated user.
- **Authentication**: Requires a valid Bearer JWT.
- **Query Parameters**:
  - `page` (*optional*, integer, default: 1): Page number (1-indexed).
  - `page_size` (*optional*, integer, default: 20, max: 100): Page size limit.
  - `unread_only` (*optional*, boolean, default: false): When `true`, filters results strictly to unread notifications (`is_read = false`).
- **Ordering**: Deterministic newest-first ordering (`created_at DESC, id DESC`).
- **Response Format (`200 OK`)**:
  ```json
  {
    "items": [
      {
        "id": "e6a0d241-7bc1-447a-8b1e-61c02459b720",
        "recipient_id": "33c67387-3014-4f34-8dde-ba606b688212",
        "notification_type": "workflow_submitted",
        "title": "Document review required: DOC-2026-9F81E32A",
        "message": "Document 'Annual Compliance Audit Report' (DOC-2026-9F81E32A) has been submitted for your review.",
        "document_id": "7832bc42-6e54-4a21-9d10-85fb32b8cd90",
        "workflow_id": "19a2e612-4a11-4cb5-87d9-c081e74f1b20",
        "is_read": false,
        "read_at": null,
        "created_at": "2026-10-10T15:00:00Z"
      }
    ],
    "total": 1,
    "unread_count": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
  ```

##### `GET /api/v1/notifications/unread-count`
Lightweight counter for polling badge indicators and UI headers.
- **Response Format (`200 OK`)**:
  ```json
  {
    "unread_count": 1
  }
  ```

##### `POST /api/v1/notifications/{notification_id}/read`
Marks a specific notification as read.
- **Ownership & Privacy**: Users can only mark their own notifications as read. If a notification ID belongs to another user or does not exist, returns a non-disclosing `404 Not Found`.
- **Idempotency**: Repeated requests succeed safely without altering the original `read_at` timestamp.
- **Response Format (`200 OK`)**:
  ```json
  {
    "id": "e6a0d241-7bc1-447a-8b1e-61c02459b720",
    "is_read": true,
    "read_at": "2026-10-10T15:05:00Z"
  }
  ```

#### 3. Transactional Consistency & Privacy Guarantees
- **Atomic Transaction Integration**: Notifications are created within the same database transaction as the workflow event (`submit_for_review`, `decision`, or `cancel`).
- **No Orphan Notifications**: If a workflow operation fails, is conflicted, or audit logging fails (`raise_on_failure=True`), the entire transaction rolls back atomically, guaranteeing no orphan notification records remain.
- **Recipient Ownership & Isolation**: Filtering is strictly applied at the SQL query level (`recipient_id == current_user.id`). One user cannot view, query, or enumerate another user's notifications.
- **Information Leakage Prevention**: Notifications never store file paths, internal storage keys, password hashes, JWTs, or OCR extracted text.

### 9. Known Limitations
- External messaging channels (Email SMTP, SMS, Slack, Webhooks) are intentionally omitted; notifications are strictly persistent in-app database records.
- Real-time WebSocket or Server-Sent Events (SSE) streaming connections are not included; clients retrieve notifications via REST polling.
- Bulk "mark all as read" operations are reserved for future workflow phases.

### 10. Frontend Notification Center (Task 5.6)

A responsive in-app Notification Center integrated into the Next.js and TypeScript frontend.

#### 1. Components and Architecture
- **Header Bell Component (`src/components/NotificationBell.tsx`)**:
  - Positioned in the persistent application header.
  - Fetches and displays unread counts (`GET /api/v1/notifications/unread-count`).
  - Automatically hides badge when unread count is `0`; displays compact `99+` badge when count exceeds 99.
  - Interactive dropdown showing the latest 5 notifications with quick "Mark as read" actions.
  - Keyboard accessible, focus ring indicators, and descriptive aria labels (e.g. `Notifications, 3 unread`).
- **Notification Center Page (`src/app/notifications/page.tsx`)**:
  - Route: `/notifications`.
  - Comprehensive view supporting pagination (`page`, `page_size`), deterministic newest-first ordering, and unread-only filtering (`unread_only=true`).
  - Displays total count, unread badge, empty states, loading skeletons, and feedback banners.
- **Notification Card Component (`src/components/NotificationCard.tsx`)**:
  - Formats date and timestamps.
  - Renders distinct visual type badges and icons:
    - `workflow_submitted`: Amber clock, "Review Required".
    - `workflow_approved`: Emerald check circle, "Approved & Active".
    - `workflow_rejected`: Rose X-circle, "Review Rejected".
    - `workflow_cancelled`: Slate alert triangle, "Review Withdrawn".
  - Interactive "Mark as read" button for unread notifications (`POST /api/v1/notifications/{id}/read`).
  - "View details" button passing document and workflow IDs with non-sensitive reference display.
- **Authentication & Global State (`src/context/AuthContext.tsx` & `src/context/NotificationContext.tsx`)**:
  - Secure Bearer JWT token management in `localStorage`.
  - Isolated state: notifications are automatically cleared on logout.
  - Idempotent and optimistic unread count synchronization between bell and center.

#### 2. Verification
- **Jest & React Testing Library**:
  - `src/__tests__/NotificationComponents.test.tsx`: 7 tests covering badge display, dropdown interactions, card rendering, and mark-as-read callbacks.
  - `src/__tests__/NotificationCenterPage.test.tsx`: 5 tests covering page rendering, unread-only filter toggling, mark-as-read updates, empty states, and API error states.
- **Type Checking & Production Build**:
  - `npx tsc --noEmit`: 0 TypeScript errors.
  - `next build`: Optimized production bundle generated cleanly (`/notifications` static page at 5.18 kB).
  - `next lint`: 0 ESLint warnings or errors.

### Task 5.7: Approver Review Inbox and Decision Interface

#### 1. Implementation Overview
- **Approver Review Inbox (`/workflows/inbox`)**:
  - Restricts access strictly to authenticated users with the `approver` role (with clear role-restriction notice and unauthenticated login prompt).
  - Fetches pending reviews explicitly assigned to the current approver via `GET /api/v1/workflows/my-assignments`.
  - Displays document reference code badge, document title, department, classification, submitter details (name, email), submission timestamp, submitter comments, and "Open Review" action link.
  - Supports 1-indexed pagination controls, loading skeleton states, error banners, and empty inbox states.
- **Workflow Review Page (`/workflows/[workflowId]`)**:
  - Fetches comprehensive safe workflow details via `GET /api/v1/workflows/{workflow_id}`.
  - Renders document metadata, department, classification, latest version summary (filename, size, MIME type, OCR extraction status), and submitter notes.
  - Decision interface: renders "Approve Document" and "Reject Document" action buttons when workflow state is `pending` and assigned to the approver.
  - **Approval Modal**: confirmation dialog with optional review comments input (max 1000 characters). Submits `POST /api/v1/workflows/{workflow_id}/decision` with `{"decision": "approved"}` and activates the document.
  - **Rejection Modal**: confirmation dialog enforcing mandatory, non-empty comments via client-side validation. Submits `POST /api/v1/workflows/{workflow_id}/decision` with `{"decision": "rejected"}` and returns document to draft for revision.
  - **Concurrency & Error Resilience**: in-flight button disabling prevents duplicate submissions; cleanly surfaces HTTP 409 Conflict (workflow already decided), HTTP 404 (non-disclosing unauthorized or missing records), HTTP 403, and HTTP 422 errors.
  - Refreshes application unread notification count upon decision submission.
- **Role-Aware Navigation & Deep Linking**:
  - Global `Header`: conditionally displays the "Review Inbox" navigation link exclusively for users with `role === "approver"`.
  - `NotificationBell` & `NotificationCard`: notification cards with an associated `workflow_id` navigate directly to `/workflows/{workflow_id}`.

#### 2. Verification
- **Jest & React Testing Library**:
  - `src/__tests__/WorkflowInbox.test.tsx`: 6 test cases verifying role enforcement, pending assignment listing, empty state, error state, pagination, and refresh.
  - `src/__tests__/WorkflowReviewPage.test.tsx`: 7 test cases verifying metadata rendering, approve flow, rejection mandatory comment validation, 409 conflict handling, 404 handling, and decided-workflow presentation.
  - `src/__tests__/NotificationComponents.test.tsx`: 7 test cases passing.
  - `src/__tests__/NotificationCenterPage.test.tsx`: 5 test cases passing.
  - Overall frontend: 4 test suites, 25 tests passing.
- **Type Checking, Linting, & Production Build**:
  - `npx tsc --noEmit`: 0 TypeScript errors.
  - `next lint`: 0 ESLint warnings or errors.
  - `next build`: Optimized production bundle built cleanly with dynamic `/workflows/[workflowId]` and static `/workflows/inbox`.
- **Backend Integrity**:
  - `docker compose exec backend pytest -q`: 274 passed in 95.71s.

### Task 5.8: Document Submission for Review Interface

#### 1. Implementation Overview
- **Document Detail Page & Submission (`/documents/[documentId]`)**:
  - Displays document metadata (reference, title, subject, department, classification, status, creation/update timestamps) and latest version information.
  - Implements the **Submit for Review** action:
    - Visible and active when the document is in `draft` status and the user has submission rights (`admin`, `records_officer`, or `department_user` matching the document's department).
    - If document status is not `draft` (e.g. `under_review`, `active`), renders an explicit explanation badge (`Document is in '{status}' status. Only draft documents can be submitted for review.`).
    - If user lacks permission (e.g. `approver`, `auditor`, `read_only`), displays a clear access explanation.
  - Embeds `WorkflowHistoryList` to display review attempts and decision history directly on the document detail page.
- **Documents Repository Listing (`/documents`)**:
  - Provides a filterable and searchable repository overview (`draft`, `under_review`, `active`, `archived`).
  - Offers a quick "Submit for Review" button on eligible draft document cards for streamlined workflows.
- **Submission Confirmation Modal (`SubmitForReviewModal`)**:
  - Displays document reference code, title, department, classification, current status (`draft`), and latest version summary.
  - Form fields:
    - **Assigned Approver User ID**: Requires a valid UUID format (`/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`).
    - **Submission Comments**: Optional, up to 1,000 characters, whitespace-trimmed.
  - Submits payload to `POST /api/v1/documents/{document_id}/submit-for-review`.
  - Disables form inputs and button during flight to prevent duplicate submissions.
  - Surfaces API errors cleanly (400 invalid approver, 403 unauthorized, 404 not found, 409 conflict, 422 format, 500 server error).
  - On success: updates document status to `under_review`, shows a success banner, refreshes the document details, increments the history refresh key, and refreshes notification unread counts.
- **Workflow History Integration (`WorkflowHistoryList`)**:
  - Connects to `GET /api/v1/documents/{document_id}/workflow-history`.
  - Displays sequential review attempts (Attempt #1, Attempt #2, ...), state badges (`pending`, `approved`, `rejected`, `cancelled`), submission notes, approver assignments, decision dates, decision comments, and cancellation reasons.
  - Preserves prior rejected and cancelled attempts across multiple document resubmissions.
- **Navigation Updates**:
  - Global `Header`: added "Documents" link for seamless navigation across Dashboard, Documents, Review Inbox, and Notification Center.
  - Dashboard (`/`): linked "Digital Documents" card to `/documents`.

#### 2. Role and Lifecycle Behavior
- **Submitter Rights**:
  - Admin & Records Officer: Allowed across all departments.
  - Department User: Allowed only for draft documents belonging to their assigned department.
  - Approver, Auditor, Read-Only: Denied submission rights.
- **Approver Eligibility**:
  - Approver must hold the active `approver` role.
  - Approver must belong to the document's owning department (no cross-department approval).
  - Submitter cannot assign themselves as approver.
- **Lifecycle Guarantees**:
  - Only `draft` documents can be submitted for review.
  - Resubmission of previously rejected or cancelled documents is supported once returned to `draft`.
  - Concurrency protected by database exclusive row locks (`SELECT FOR UPDATE`).

#### 3. Verification
- **Jest & React Testing Library**:
  - `src/__tests__/DocumentSubmission.test.tsx`: 14 tests covering all Task 5.8 requirements (draft eligibility, ineligible notice, unauthorized roles, modal validation, payload transmission, status transition, duplicate prevention, error handling, unread notification refresh, history preservation, and empty states).
  - Overall frontend: 5 test suites, 38 tests passing.
- **Type Checking, Linting, & Production Build**:
  - `npx tsc --noEmit`: 0 TypeScript errors.
  - `next lint`: 0 ESLint warnings or errors.
  - `next build`: Static `/documents` (5.36 kB) and dynamic `/documents/[documentId]` (6.88 kB) built cleanly.
- **Docker & Endpoint Probes**:
  - Rebuilt and restarted `edrms-frontend` container.
  - `curl.exe -I http://127.0.0.1:3000/documents` -> `HTTP/1.1 200 OK`
  - `curl.exe -I http://127.0.0.1:3000/documents/test-doc-id` -> `HTTP/1.1 200 OK`
- **Backend Integrity**:
  - `docker compose exec backend pytest -q`: 274 passed in 97.69s.

---

### Task 5.9: Secure Approver Directory and Selection

Task 5.9 replaces manual approver UUID entry during document review submission with an authenticated, searchable, and departmental-scoped approver directory.

#### 1. Backend Endpoint & Security Scoping
- **Endpoint**: `GET /api/v1/users/eligible-approvers`
- **Authentication**: Strict Bearer token validation required (`HTTP 401 Unauthorized` if unauthenticated).
- **Default-Deny Access Control**:
  - Allowed roles: `admin`, `records_officer`, `department_user`.
  - Disallowed roles: `approver`, `auditor`, `read_only` (`HTTP 403 Forbidden`).
- **Departmental Scoping & Privacy Enforcement**:
  - Active users only: `User.is_active == True` and `User.role == UserRole.APPROVER`.
  - Submitter exclusion: `User.id != current_user.id` to prevent self-approval.
  - `department_user`: Automatically scoped to their own department (`User.department == current_user.department`).
  - `admin` and `records_officer`: Can query all approvers or provide optional `department` filter.
- **Document-Aware Scoping (`document_id` query param)**:
  - Validates document existence (`HTTP 404 Not Found` if missing).
  - For `department_user`, enforces that the document belongs to their own department (`HTTP 403 Forbidden` if cross-department).
  - Automatically filters approvers to the document's owning department (`User.department == document.department`).
- **SQL-Level Search & Pagination**:
  - Query parameter `q`: Bounded between 1 and 50 characters, filters `full_name` or `email` using case-insensitive `ILIKE`.
  - Query parameter `limit`: Bounded between 1 and 50 (default: 20).
  - Deterministic ordering: `ORDER BY full_name ASC, email ASC, id ASC`.
- **Safe Schema (`EligibleApproverResponse`)**:
  - Exposes only safe fields: `id` (UUID), `email` (string), `full_name` (string), `department` (string).
  - Passwords, internal flags, and sensitive audit hashes are strictly excluded.

#### 2. Frontend Approver Selector Integration
- **`SubmitForReviewModal` (`frontend/src/components/SubmitForReviewModal.tsx`)**:
  - Replaces raw UUID text input with a dedicated, searchable approver directory selector.
  - Automatically queries `api.getEligibleApprovers({ document_id: document.id, q: searchQuery })`.
  - **Debounced Search**: 300ms debounce prevents unnecessary API requests while typing.
  - **User Experience States**:
    - Loading spinner during directory queries.
    - Error banner with retry button if directory fetch fails.
    - Informative empty state when no approvers match criteria.
    - Selection confirmation with checkmark, highlighted borders, and clear button.
  - **Accessibility**:
    - Full keyboard navigation and ARIA attributes (`role="listbox"`, `role="option"`, `aria-selected`, `aria-expanded`).
  - **Validation**:
    - Disables submit button until an eligible approver is selected.
    - Preserves submission comments and locks form inputs during submission.

#### 3. Verification & Regressions
- **Backend Tests (`backend/tests/test_approver_directory.py`)**:
  - 7 integration tests covering:
    - Scoping approvers to submitter's department.
    - Self-exclusion of submitter.
    - Unauthenticated request rejection (`401`).
    - Auditor and read-only role denial (`403`).
    - Name and email search filtering with result limits.
    - Document-aware departmental scoping.
    - Denial of cross-department document access.
  - Result: 7/7 passed.
- **Frontend Tests (`frontend/src/__tests__/DocumentSubmission.test.tsx`)**:
  - 14 tests covering the full submission flow, searchable approver selector, debounced search, empty states, error handling, payload transmission, and state updates.
  - Total frontend: 5 test suites, 38 tests passing.
- **TypeScript, Linting, & Build**:
  - `npx tsc --noEmit`: 0 errors.
  - `npm run lint`: 0 warnings or errors.
  - `npm run build`: Production build succeeded.
- **Full Backend Regression**:
  - `docker compose exec backend pytest -q`: 281 passed, 0 failures.

---

### Task 5.10: User Administration and Role Management

Task 5.10 implements a complete, secure User Administration module enabling authorized system administrators to manage EDRMS user accounts, roles, departmental assignments, and account activation.

#### 1. Administrator-Only Backend APIs
- **List Users**: `GET /api/v1/users`
  - Strict administrator-only authorization via `require_admin` dependency. Non-admin roles receive `HTTP 403 Forbidden`.
  - SQL-level pagination: `page` (default 1) and `page_size` (1–100, default 20).
  - Multi-attribute filtering: `search` (matching full name or email), `role`, `department`, and `is_active`.
  - Deterministic ordering: `ORDER BY full_name ASC, email ASC, id ASC`.
  - Safe response schema: `AdminUserResponse` completely omits passwords, hashes, and internal tokens.
- **Create User**: `POST /api/v1/users`
  - Validates full name, email uniqueness (rejects duplicates with `HTTP 409 Conflict`), and role.
  - Enforces mandatory departmental assignment for departmental roles (`department_user`, `approver`, `auditor`, `read_only`).
  - Hashes initial passwords using Argon2id (`time_cost=3, memory_cost=65536, parallelism=4`).
  - Emits mandatory audit log (`action="user.create"`).
  - Never returns password or password hash.
- **Update User Profile**: `PATCH /api/v1/users/{user_id}`
  - Updates approved profile fields: `full_name`, `department`, and `role`.
  - Validates role-department compatibility (fails with `HTTP 422` if departmental role lacks a department).
  - Prohibits updates to immutable IDs, emails, passwords, or hashes through arbitrary payloads.
  - **Last Active Administrator Safeguard**: Uses PostgreSQL row-level locks (`SELECT FOR UPDATE`) to ensure the last active administrator cannot be demoted to another role.
  - Emits mandatory audit log (`action="user.update"`).
- **Activate / Deactivate User**: `PATCH /api/v1/users/{user_id}/status`
  - Updates account active status (`is_active`).
  - **Self-Lockout Safeguard**: Administrators are strictly prevented from deactivating their own account (`HTTP 400 Bad Request`).
  - **Last Active Administrator Safeguard**: Uses row locks to ensure the sole remaining active administrator cannot be deactivated.
  - Deactivation immediately terminates authentication rights: deactivated users cannot log in, and already-issued JWT access tokens are immediately rejected on all endpoints.
  - Deactivation strictly preserves documents, versions, workflow history, assignments, and audit logs.
  - Emits mandatory audit log (`action="user.activate"` / `"user.deactivate"`).

#### 2. User Administration UI (`/admin/users`)
- Next.js 14 App Router administration dashboard accessible strictly by `admin` users.
- Non-admin users attempting direct navigation are presented with an explicit access-denied screen.
- Features:
  - Search by name or email with responsive inputs.
  - Dropdown filters for role, department, and active/inactive status.
  - Paginated user table with role pills, department indicators, and status badges.
  - Modal form for creating accounts with client-side role-department validation and Argon2id notice.
  - Modal form for editing user profile and role details.
  - Confirmation dialog for activating/deactivating accounts explaining the immediate security impact.
  - Responsive header integration: adds "User Management" navigation link for administrators.

#### 3. Verification & Regressions
- **Backend User Admin Tests (`backend/tests/test_user_admin.py`)**:
  - 13 comprehensive unit and integration tests covering:
    - Paginated listing and filtering.
    - Role denial across all non-admin roles (records officer, department user, approver, auditor, read-only).
    - User creation and Argon2id verification.
    - Duplicate email conflict rejection (`409`).
    - Department requirement validation (`422`).
    - Profile update and unauthorized field immutability.
    - Deactivation and immediate token invalidation (`401`).
    - Self-deactivation prevention (`400`).
    - Last-administrator demotion and deactivation safeguards (`400`).
    - Mandatory audit logging and transactional rollback on audit write failure.
    - Document, workflow, and notification data preservation after deactivation.
  - Result: 13/13 passed.
- **Frontend Jest Tests (`frontend/src/__tests__/UserAdmin.test.tsx`)**:
  - 7 tests covering access control, listing, search/filter dispatch, create validation, edit submission, and confirmation dialogs.
  - Overall frontend test suite: 6 test suites, 45 tests passing.
- **Frontend Build & Linter**:
  - `npx tsc --noEmit`: 0 errors.
  - `npm run lint`: 0 warnings or errors.
  - `npm run build`: Production standalone build succeeded (`/admin/users` generated at 8.82 kB).
- **Docker Production Deployment**:
  - Rebuilt and started `edrms-frontend` container.
  - Probed `http://127.0.0.1:3000/admin/users`: `HTTP 200 OK`.
- **Full Backend Regression Suite**:
  - `docker compose exec backend pytest -q`: 294 passed, 0 failures.

---

### Task 5.11: Audit Log Viewer and Administrative Reports

#### 1. Backend Read-Only Audit Log Viewer APIs
- **Router Prefix**: `/api/v1/audit-logs`
- **Role-Based Access Policy**: Strictly restricted to `admin` and `records_officer` roles (`require_audit_viewer_role` dependency). All other roles (`department_user`, `approver`, `auditor`, `read_only`) receive `HTTP 403 Forbidden`. Unauthenticated requests receive `HTTP 401 Unauthorized`.
- **Query & Paginated Audit Logs**: `GET /api/v1/audit-logs`
  - SQL-level pagination with `page` (default: 1) and `page_size` (default: 25, max: 100).
  - Search query (`q`): Substring matching across `action`, `resource_type`, and `ip_address`.
  - Filters:
    - `action`: Exact action matching (e.g. `document.upload`, `workflow.submit`, `user.create`).
    - `resource_type`: Target entity type (e.g. `document`, `workflow`, `user`).
    - `resource_id`: Target resource UUID.
    - `actor_id`: Actor UUID.
    - `outcome`: `SUCCESS` or `FAILURE`.
    - `start_date` and `end_date`: ISO datetime range filtering.
  - Validation: Query parameter validation ensures `start_date <= end_date` (returns `HTTP 422 Unprocessable Entity` on invalid ranges).
  - Deterministic ordering: Strict newest-first ordering (`ORDER BY created_at DESC, id DESC`).
- **Audit Event Detail**: `GET /api/v1/audit-logs/{audit_log_id}`
  - Fetches complete event metadata and context payload.
  - Field-level data sanitization: Strips sensitive fields (`password`, `hash`, `token`, `secret`, `bearer`, `auth`, `storage_key`) from `details` and `previous_state` before serialization.
  - Returns `HTTP 404 Not Found` for non-existent event IDs.
- **Audit Aggregate Reports**: `GET /api/v1/audit-logs/reports/summary`
  - Total event count, success/failure counts.
  - Grouped metrics: Event counts grouped by action and outcome.
  - Security summary: Recent admin user management operations, authentication events, and workflow decisions.
  - Fully read-only: No audit records can be edited, mutated, or deleted through any endpoint.

#### 2. Audit Event Coverage
- Complete tamper-evident audit logging coverage verified across all system subsystems:
  - **Documents**: `document.upload`, `document.new_version`, `document.preview`, `document.download`.
  - **Workflows**: `workflow.submit`, `workflow.approve`, `workflow.reject`, `workflow.cancel`.
  - **User Administration**: `user.create`, `user.update`, `user.activate`, `user.deactivate`.
  - **Authentication**: `auth.login`, `auth.refresh`.

#### 3. Frontend Audit Log Viewer (`/admin/audit-logs`)
- Next.js 14 App Router administration dashboard accessible strictly by `admin` and `records_officer` roles.
- Features:
  - Metric summary cards: Total events, successful operations, failure counts, and distinct active action types.
  - Search & filter bar: Free-text search, action type filter, resource type filter, outcome selector, and ISO date range pickers.
  - Paginated audit log table: Displays timestamp (in user's local timezone), actor name and email, action badge, resource type and ID, outcome badge (`SUCCESS` / `FAILURE`), and client IP address.
  - Safe detail modal: Displays structured metadata, actor identity, request context, and sanitized JSON event payload.
  - Access control: Non-authorized users attempting direct navigation are presented with an explicit access-denied screen.
  - Header integration: Adds "Audit Logs" navigation link for administrators and records officers.

#### 4. Verification & Regressions
- **Backend Audit Viewer Tests (`backend/tests/test_audit_viewer.py`)**:
  - 10 tests covering role enforcement, pagination, multi-field filtering, date range validation, single-event detail sanitization, summary reports, and read-only integrity. All 10 passed.
- **Frontend Jest Tests (`frontend/src/__tests__/AuditLogs.test.tsx`)**:
  - 6 tests covering role guard, metric cards, log table rendering, filter dispatch, detail inspection modal, and API error states. All 6 passed.
- **Frontend Test Suite**: 7 test suites, 51 tests passed.
- **Frontend Linter & TypeScript**:
  - `npx tsc --noEmit`: 0 errors.
  - `npm run lint`: 0 warnings or errors.
  - `npm run build`: Production build succeeded (`/admin/audit-logs` generated cleanly).
- **Docker Production Deployment**:
  - Rebuilt and started `edrms-frontend` container.
  - Probed `http://127.0.0.1:3000/admin/audit-logs`: `HTTP 200 OK`.
- **Full Backend Regression Suite**:
  - `docker compose exec backend pytest -q`: 304 passed, 0 failures.

---

### Task 5.12: Records Retention Rules and Disposal Eligibility

#### 1. Backend Retention Schedule & Governance Architecture
- **Router Prefix**: `/api/v1/retention`
- **Models & Migration**:
  - `RetentionRule`: Unique `name`, `description`, target `classification`, `retention_period_unit` (`days`, `months`, `years`), `retention_period_value`, `trigger_event` (`creation`, `approval`), `is_active`, and audit timestamps.
  - `DigitalDocument` Extensions: `retention_rule_id`, `retention_trigger_date`, `retention_start_date`, `retention_end_date`, `retention_assigned_at`, `retention_assigned_by_id`.
  - `LegalHold`: Document evidentiary hold model storing `document_id`, `hold_reason`, `status` (`active`, `released`), `placed_by_id`, `placed_at`, `released_by_id`, `released_at`, and `release_reason`.
  - Alembic Migration: `e3f1248ab901_create_retention_and_legal_hold_tables.py` applied cleanly on top of `ddff27e85a0b`.
- **Retention Rule Management Endpoints**:
  - `GET /api/v1/retention/rules`: Paginated listing with search, classification filter, and active status filter.
  - `POST /api/v1/retention/rules`: Administrator & Records Officer rule creation with name uniqueness validation.
  - `GET /api/v1/retention/rules/{rule_id}`: Single rule retrieval.
  - `PATCH /api/v1/retention/rules/{rule_id}`: Rule update with uniqueness check.
  - `PATCH /api/v1/retention/rules/{rule_id}/status`: Activate or deactivate retention schedule.
- **Document Retention Assignment**:
  - `GET /api/v1/retention/documents/{document_id}`: Exposes document retention schedule, trigger dates, end date, active hold count, and eligibility explanation.
  - `POST /api/v1/retention/documents/{document_id}/assign-rule`: Assigns retention rule. Prohibits inactive rule assignment and strictly blocks any rule change that would silently shorten an existing retention end date (`HTTP 400 Bad Request`).
- **Legal Hold Management**:
  - `GET /api/v1/retention/documents/{document_id}/legal-holds`: Full chronological audit history of active and released legal holds.
  - `POST /api/v1/retention/documents/{document_id}/legal-holds`: Administrative hold placement.
  - `POST /api/v1/retention/legal-holds/{hold_id}/release`: Hold release with mandatory release reason comment.
  - **Evidentiary Hold Invariant**: A document with an active legal hold is always classified as `on_hold` and is strictly prevented from being reported as `eligible_for_review`.
- **Disposal Eligibility Assessment**:
  - `GET /api/v1/retention/disposal-eligibility`: Read-only assessment query supporting SQL pagination, department scoping, retention rule filtering, and status filtering (`retained`, `eligible_for_review`, `on_hold`, `needs_attention`).
  - **No Permanent Deletion**: Retention module strictly governs eligibility; permanent destruction endpoints are prohibited.

#### 2. Frontend Interface (`/retention`)
- Unified administration and compliance console at `/retention` with dual-view tabs:
  - **Disposal Eligibility**: Search & filter bar, KPI indicators, paginated assessment table with color-coded eligibility badges (`Retained`, `Eligible for Review`, `Legal Hold`, `Needs Attention`), and plain-language explanations.
  - **Retention Schedules**: Paginated table of configurable retention policies with active/inactive toggles and rule creation modal.
  - **Legal Holds Modal**: Integrated document-level hold management drawer allowing authorized officers to view full evidentiary hold histories, place new holds, or submit required release comments.
- Global Header Integration: Adds "Retention" navigation link for administrators, records officers, auditors, and department compliance staff.

#### 3. Verification & Automated Test Suites
- **Backend Retention Tests (`backend/tests/test_retention.py`)**:
  - 8 unit and integration tests covering CRUD operations, role authorization, date calculations, silent shortening prevention, inactive rule assignment prevention, legal hold suspension invariants, department scoping, and mandatory audit logging.
- **Full Backend Regression Suite**:
  - `pytest -q`: **312 passed, 0 failures in 100.75s**.
- **Frontend Jest Tests (`frontend/src/__tests__/Retention.test.tsx`)**:
  - 4 tests covering unauthorized role guards, eligibility table rendering, tab switching, and legal hold modal flows.
- **Full Frontend Jest Suite**:
  - **8 test suites, 55 tests passed**.
- **TypeScript & Linter**:
  - `npx tsc --noEmit`: 0 errors.
  - `npm run lint`: 0 warnings or errors.
- **Production Build & Docker Deployment**:
  - Next.js standalone build compiled successfully (`/retention` generated at 7.02 kB).
  - Production container `edrms-frontend` running healthy; probed `http://frontend:3000/retention`: `HTTP 200 OK`.

---

### Task 5.13: Governance Review, Access-Control Verification and Security Hardening

#### 1. Security Baseline & Vulnerability Remediation
- **Date Range Query Validation**:
  - Hardened `GET /api/v1/retention/disposal-eligibility` against inverted date ranges (`start_date > end_date`), returning strict `422 Unprocessable Entity`.
  - Added SQL filtering on `DigitalDocument.retention_end_date` within bounds `[start_date, end_date]`.
- **Retention Classification Mismatch Prevention**:
  - Hardened `POST /api/v1/retention/documents/{document_id}/assign-rule` to enforce classification integrity. Assigning a retention rule targeted to a specific classification (e.g., `Confidential`) to a document with a mismatched classification (e.g., `Restricted`) is rejected with `HTTP 400 Bad Request`.
- **Department Boundary Enforcement**:
  - Non-disclosing `404 Not Found` returned on document metadata and preview requests across department boundaries to prevent enumeration or existence discovery of confidential files.
  - Strict `403 Forbidden` returned on download requests for cross-department or unauthorized records.
- **Account State & Token Verification**:
  - Immediate token rejection (`401 Unauthorized - User account is inactive`) for deactivated accounts across all protected endpoints, preventing inactive user access via existing JWTs.
  - Expired and malformed tokens cleanly rejected with `401 Unauthorized`.
- **Notification Ownership**:
  - Restricted `POST /api/v1/notifications/{id}/read` to notification recipient; non-owners receive `404 Not Found`.
- **Administrative Endpoint Protection**:
  - User administration (`/api/v1/users`) and OCR job retry (`/api/v1/ocr/jobs/{id}/retry`) strictly restricted to `admin` role with `403 Forbidden` returned for other roles.

#### 2. Verification & Automated Test Suites
- **Security Hardening Regression Suite (`backend/tests/test_security_hardening.py`)**:
  - 7 comprehensive regression tests covering inactive user token rejection, expired/malformed JWT handling, department isolation on metadata/download/preview, retention classification mismatch prevention, disposal date range validation, notification recipient ownership verification, and user admin/OCR role enforcement.
  - All 7 tests pass in 0.72s.
- **Full Backend Regression Suite**:
  - `pytest -q`: **319 passed, 0 failures in 108.98s**.
- **Full Frontend Jest Suite**:
  - `npm test`: **8 test suites, 55 tests passed**.
- **TypeScript & Linter**:
  - `npx tsc --noEmit`: 0 errors.
  - `npm run lint`: 0 warnings or errors.
- **Service Health**:
  - Docker Compose services (`edrms-db`, `edrms-backend`, `edrms-frontend`, `edrms-worker`) healthy. Current Alembic head: `e3f1248ab901`.

---

### Task 6.1: Physical File Registry

#### 1. Backend Data Architecture & API
- **Model**: `PhysicalFile` model in [`backend/app/models/physical_file.py`](file:///d:/EDRMS/backend/app/models/physical_file.py) tracking physical paper records, contracts, and archives.
- **Unique Reference Generation**: Concurrency-safe, cryptographic 8-hex suffix generation (`PHY-YYYY-XXXXXXXX`) via `generate_physical_file_reference` in [`backend/app/services/reference_generator.py`](file:///d:/EDRMS/backend/app/services/reference_generator.py).
- **Alembic Migration**: `cb9307f34aba_create_physical_files_table.py` establishing `physical_files` table with single migration head `cb9307f34aba (head)`.
- **API Router**: [`backend/app/api/v1/physical_files.py`](file:///d:/EDRMS/backend/app/api/v1/physical_files.py) with 5 governed REST endpoints:
  - `POST /api/v1/physical-files`: Register physical file with mandatory audit logging.
  - `GET /api/v1/physical-files`: List and search with SQL pagination and department-scoping.
  - `GET /api/v1/physical-files/{id}`: Detailed metadata retrieval; non-disclosing 404 for unauthorized users.
  - `PATCH /api/v1/physical-files/{id}`: Permitted metadata updates; department reassignment restricted to `admin` and `records_officer`.
  - `PATCH /api/v1/physical-files/{id}/status`: Lifecycle transitions (`active` -> `archived`/`inactive`) with reason notes.
- **Authorization Service**: `PhysicalFileAuthorizationService` in [`backend/app/services/authorization.py`](file:///d:/EDRMS/backend/app/services/authorization.py) enforcing role and department policies.

#### 2. Frontend Interface (`/physical-files`)
- Unified physical records console at `/physical-files`:
  - **Registry List**: Paginated table with status badges (`active`, `archived`, `inactive`), record types, and linked digital indicators.
  - **Search & Filters**: Multi-attribute filtering across keywords, department, record type, and status.
  - **Registration Form**: Controlled modal with role-based department restrictions and optional digital document UUID linkage.
  - **Detail & Status Management Drawer**: Metadata inspector, editing modal, and state transition confirmations.
- Global Header Integration: Added "Physical Files" navigation link in [`frontend/src/components/Header.tsx`](file:///d:/EDRMS/frontend/src/components/Header.tsx).

#### 3. Verification & Automated Test Suites
- **Backend Integration Tests (`backend/tests/test_physical_files.py`)**:
  - 9 tests covering registration, reference generation, search & pagination, department isolation, unauthorized reassignment prevention, digital document relationship scoping, lifecycle status transitions, mandatory audit logging, and inactive user rejection.
- **Full Backend Regression Suite**:
  - `pytest -q`: **328 passed, 0 failures in 103.06s**.
- **Frontend Jest Tests (`frontend/src/__tests__/PhysicalFiles.test.tsx`)**:
  - 4 tests covering registry list rendering, registration modal validation, detail drawer display, and empty states.
- **Full Frontend Jest Suite**:
  - `npm test`: **9 test suites, 59 tests passed in 9.45s**.
- **TypeScript & Linter**:
  - `npx tsc --noEmit`: 0 errors.
  - `npm run lint`: 0 warnings or errors.
- **Next.js Production Build**:
  - Standalone build compiled successfully (`/physical-files` route at 7.65 kB).
- **Service Health**:
  - All Docker Compose services healthy (`edrms-db`, `edrms-backend`, `edrms-frontend`, `edrms-worker`). Single Alembic head `cb9307f34aba (head)`.

---

### Task 6.2 — Storage Locations Management

Governed physical storage facilities and hierarchy management module enabling organizations to define, organize, search, and manage recursive containment locations (buildings, floors, rooms, cabinets, shelves, bays, boxes) and assign physical files to specific locations.

#### 1. Backend Architecture & Hierarchy Model
- **`StorageLocation` Model**: Created in [`backend/app/models/storage_location.py`](file:///d:/EDRMS/backend/app/models/storage_location.py):
  - Fields: `id` (UUID), `location_code` (unique uppercase code, e.g. `HQ-BLD-01`), `name`, `location_type` (`building`, `floor`, `room`, `cabinet`, `shelf`, `bay`, `box`, `other`), `description`, `department`, `parent_id` (foreign key to self, `ondelete="RESTRICT"`), `is_active`, `max_capacity` (optional file count limit), `created_by_id`, `updated_by_id`, timestamps.
  - Indexes & Constraints: Unique `location_code`, indexed `department`, `location_type`, `parent_id`, and `is_active`.
- **`PhysicalFile` Extension**: Extended [`backend/app/models/physical_file.py`](file:///d:/EDRMS/backend/app/models/physical_file.py) with `storage_location_id` foreign key (`ondelete="SET NULL"`).
- **Alembic Migration**: `e3292cf4fca4_create_storage_locations_table.py` applied cleanly. Single head verified at `e3292cf4fca4 (head)`.
- **Hierarchy Validation Service**: [`backend/app/services/location_service.py`](file:///d:/EDRMS/backend/app/services/location_service.py):
  - Prevents circular parenting and self-parenting via recursive ancestor traversal.
  - Enforces logical containment rules via `PERMITTED_PARENT_TYPES` (e.g. shelves in cabinets/rooms, boxes on shelves/cabinets).
  - Breadcrumb and path resolution (`get_location_path`, `get_location_breadcrumbs`).
- **Authorization Service**: `StorageLocationAuthorizationService` in [`backend/app/services/authorization.py`](file:///d:/EDRMS/backend/app/services/authorization.py):
  - Role-based permissions: `admin` and `records_officer` have global management; `department_user` is restricted to their own department's locations.
  - Cross-department assignment and view protections.
- **REST Endpoints**:
  - `POST /api/v1/storage-locations`: Create location with hierarchy and code uniqueness checks.
  - `GET /api/v1/storage-locations`: List and search with SQL pagination, scoping, and direct counts.
  - `GET /api/v1/storage-locations/{id}`: Detailed metadata with full breadcrumb hierarchy and capacity usage.
  - `PATCH /api/v1/storage-locations/{id}`: Update metadata, department, capacity, or parent with cycle prevention.
  - `PATCH /api/v1/storage-locations/{id}/status`: Activate or deactivate with safe invariant checks (rejects deactivation if containing files or active children).
  - `GET /api/v1/storage-locations/{id}/children`: Direct child sub-locations.
  - `GET /api/v1/storage-locations/{id}/contents`: Paginated physical files stored directly in this location.
  - `POST /api/v1/physical-files/{id}/assign-location`: Assign or reassign a physical file to an active storage location with capacity limit enforcement.
- **Audit Logging**: Mandatory audit logging with atomic rollback on creation, updates, status transitions, and location assignments.

#### 2. Frontend Implementation
- **`/storage-locations` Route**: Comprehensive dual-panel location explorer:
  - Left panel: Paginated table with code badges, location types, department scoping, direct file counts / max capacity, and status indicators.
  - Right drawer: Inspector displaying hierarchical breadcrumb path, facility notes, capacity bar, sub-locations, and paginated direct physical files listing.
  - Modals: Create Storage Location modal, Edit Location modal, and Lifecycle Status toggle modal.
- **`/physical-files` Route Extension**:
  - Table column showing assigned storage location name and code with quick link.
  - Registration modal supporting optional initial storage location UUID assignment.
  - Detail drawer displaying storage location info, full hierarchical breadcrumbs, and "Assign / Change Location" action modal.
  - Edit modal allowing location updates or unlinking from current location.
- **Header Navigation**: Added "Storage Locations" link to the primary navbar in [`frontend/src/components/Header.tsx`](file:///d:/EDRMS/frontend/src/components/Header.tsx).

#### 3. Verification & Automated Test Suites
- **Backend Integration Tests (`backend/tests/test_storage_locations.py`)**:
  - 7 comprehensive tests passing: location creation, code uniqueness, hierarchy nesting & breadcrumbs, cycle/self-parenting rejection, department scoping, safe deactivation validation, and location assignment with capacity limits.
- **Full Backend Regression Suite**:
  - `pytest -q`: **335 passed, 0 failures in 99.55s**.
- **Frontend Jest Tests (`frontend/src/__tests__/StorageLocations.test.tsx`)**:
  - 4 tests covering header rendering, creation modal, location selection with details & contents drawer, and empty state.
- **Full Frontend Jest Suite**:
  - `npm test`: **10 test suites, 63 tests passed in 8.71s**.
- **TypeScript & Next.js Production Build**:
  - `npm run build`: Compiled successfully; 12 static/dynamic routes generated.
- **Service Health**:
  - All Docker Compose services healthy (`edrms-db`, `edrms-backend`, `edrms-frontend`, `edrms-worker`). Single Alembic head `e3292cf4fca4 (head)`.

---

### Task 6.3 — Physical File Check-In, Check-Out and Transfers

Implements governed circulation and custody management for physical records in the EDRMS application:
- **Custody Records & Movement History**:
  - `FileCustodyRecord` tracks active and historical physical file custody, including custodian identity, contact details, issue timestamp, expected return date, check-in return timestamp, and check-in condition notes.
  - `FileMovementHistory` provides an immutable audit trail capturing initial storage, checkout, check-in, transfer, and relocation events with source/destination storage locations and actor references.
  - `PhysicalFile.is_checked_out` indicator with row-level locks (`with_for_update()`) preventing duplicate checkouts, concurrent conflicting transfers, or race conditions.
- **Circulation Rules & Enforcement**:
  - Check-out requires file to be in `active` lifecycle status and assigned to a storage location.
  - Destination location capacity (`max_capacity`) and active status verified on transfers and check-ins.
  - Transfers rejected if file is currently checked out (must be returned first).
  - Department scoping enforced across check-outs, returns, transfers, and overdue reporting.
- **Overdue Reporting**:
  - Dedicated endpoint `GET /api/v1/physical-files/overdue` flags records where `expected_return_at < now` and file remains checked out.
  - Scoped by user department (Department Users and Auditors strictly see their department; Administrators and Records Officers view all).
- **Mandatory Audit Logging**:
  - All circulation actions (`physical_file.checkout`, `physical_file.checkin`, `physical_file.transfer`) log structured audit entries with actor, timestamp, outcome, and resource IDs.
- **Alembic Database Migration**:
  - Migration revision `2c7dcaca1ec2_create_file_custody_and_movement_.py` creates `file_custody_records` and `file_movement_history` tables with composite foreign keys and indexes. Single migration head: `2c7dcaca1ec2 (head)`.
- **API Endpoints Added**:
  - `GET /api/v1/physical-files/overdue`: Paginated overdue physical files report.
  - `POST /api/v1/physical-files/{id}/checkout`: Check out physical file to custodian.
  - `POST /api/v1/physical-files/{id}/checkin`: Check in physical file and close active custody.
  - `POST /api/v1/physical-files/{id}/transfer`: Transfer physical file to new storage location.
  - `GET /api/v1/physical-files/{id}/custody`: Active custody record inspection.
  - `GET /api/v1/physical-files/{id}/custody-history`: Historical custody records.
  - `GET /api/v1/physical-files/{id}/movement-history`: Chronological movement audit timeline.
- **Frontend Integration (`/physical-files`)**:
  - Custody and Overdue badges displayed in Physical File Registry table.
  - Tab navigation switching between Registry and Overdue Circulation report.
  - Drawer detail view integrates current custody box with custodian information and expected return schedule.
  - Dedicated Check Out, Check In, and Transfer modals with live validation.
  - Interactive Movement History timeline modal with color-coded event markers.
- **Test Verification**:
  - Backend pytest suite: **10/10 tests passed** in [`tests/test_custody_and_transfers.py`](file:///d:/EDRMS/backend/tests/test_custody_and_transfers.py); **345/345 passed** across full backend test suite.
  - Frontend Jest suite: **9/9 tests passed** across physical file suites (`PhysicalFiles.test.tsx` and `PhysicalFilesCustody.test.tsx`).
  - Next.js production build (`npm run build`): Successfully compiled all 12 routes.

---

### Task 6.4: Barcode/QR Identification and Physical File Search

- **Barcode & QR Symbologies**:
  - **QR Code**: Standard 2D QR encoding clean references (e.g. `PHY-YYYY-XXXXXXXX`) or deep-link navigation URLs for fast camera capture on mobile/tablet devices.
  - **Barcode**: Code 128 1D barcode format rendered as SVG via `jsbarcode`, providing reliable scanning support for laser/CCD handheld readers.
- **Physical File Label Preview & Printing**:
  - Component [`PrintLabelModal.tsx`](file:///d:/EDRMS/frontend/src/components/PrintLabelModal.tsx) provides a standard index/badge card layout displaying file reference, title, department, classification, Code 128 barcode, and 2D QR code.
  - CSS `@media print` rules ensure only the label card prints cleanly without navigation bars, headers, or backgrounds.
  - Printing generates an audited event via `POST /api/v1/physical-files/print-label` without disclosing secret tokens or sensitive payloads.
- **Identification & Scanning Interface**:
  - Component [`ScanLookupModal.tsx`](file:///d:/EDRMS/frontend/src/components/ScanLookupModal.tsx) provides dual identification modes:
    - **Camera QR Scanner**: In-browser real-time video capture via `html5-qrcode` with device selection, permission fallback prompts, and automatic camera teardown on close.
    - **Manual / USB Barcode Input**: Text input supporting handheld USB barcode wedge scanners (auto-submitting on carriage return) or manual entry.
  - Scanned inputs (raw codes, URLs with `ref=...`, or path routes) are cleaned and resolved via `GET /api/v1/physical-files/lookup`.
- **Search & Filter Extensions**:
  - Added filter dropdowns for Circulation / Custody State (`stored`, `checked_out`, `overdue`) and Classification (`Public`, `Internal`, `Confidential`, `Restricted`).
  - Lookup endpoint returns non-disclosing 404 for inaccessible or nonexistent files to preserve cross-department confidentiality.
- **Test Verification**:
  - Backend pytest suite: **8/8 tests passed** in [`tests/test_physical_file_lookup.py`](file:///d:/EDRMS/backend/tests/test_physical_file_lookup.py); **353/353 passed** across full backend regression suite.
  - Frontend Jest suite: **14/14 tests passed** across physical file suites; **73/73 passed** across the complete frontend application test suite.
  - Next.js production build: **Compiled successfully** without errors.

---

### Task 6.5: Chain-of-Custody Integrity and Overdue Reporting

- **Database-Level Invariants**:
  - Migration revision `851619ad95bc_enforce_single_active_custody_per_file.py` creates a partial unique index `uq_file_custody_single_active` on `file_custody_records(physical_file_id) WHERE status = 'active'`.
  - Guarantees at the database level that no physical file can concurrently hold more than one active custody record, preventing checkout race conditions.
  - Model `FileCustodyRecord` in `backend/app/models/custody.py` updated with matching `__table_args__`.
- **Diagnostic Custody Integrity Verification**:
  - Endpoint `GET /api/v1/physical-files/custody-integrity` scans registered files and validates 6 core chain-of-custody invariants:
    1. `MISSING_ACTIVE_CUSTODY`: File marked checked-out but has no active custody record.
    2. `UNEXPECTED_ACTIVE_CUSTODY`: File marked stored but has an active custody record.
    3. `MULTIPLE_ACTIVE_CUSTODY`: More than one active custody record found for a physical file.
    4. `LOCATION_MISMATCH_WITH_CHECKIN`: Stored file location does not match destination of latest check-in.
    5. `LOCATION_MISMATCH_WITH_TRANSFER`: Stored file location does not match destination of latest transfer.
    6. `CHECKOUT_WITHOUT_MOVEMENT`: Active custody record lacks a corresponding checkout movement history event.
  - Scoped by user department (administrators and records officers view all; department users and auditors strictly view their department).
- **Enhanced Overdue Circulation Reporting**:
  - Endpoint `GET /api/v1/physical-files/overdue` enhanced with:
    - Timezone-aware date calculations and integer `days_overdue`.
    - Custodian filter parameter `custodian`.
    - Threshold filter parameter `min_days_overdue`.
    - Embedded current storage location details (`storage_location_name`, `storage_location_code`).
    - Explicit exclusion of returned and closed custody records.
- **Storage Location Transfers Governance Reporting**:
  - Endpoint `GET /api/v1/physical-files/transfers` provides chronological reporting of physical file relocations.
  - Supports date range filtering (`from_date`, `to_date`) and department scoping.
  - Returns source and destination location names/codes, transfer timestamps, reasons, and performer details.
- **Governed CSV Export**:
  - Endpoint `GET /api/v1/physical-files/export-csv` supports governed export for `overdue`, `checked_out`, and `transfers` reports.
  - Formula Injection Protection: Sanitizes cells starting with `=`, `+`, `-`, `@`, `\t`, or `\r` by prefixing with `'`.
  - Privacy Guard: Redacts custodian contact details (phone, email) unless caller holds administrative or records officer roles.
  - Audits export operations via `physical_file.export_csv`.
- **Frontend Governance Reporting & Diagnostic UI (`/physical-files`)**:
  - Tab Switcher extended with **Location Transfers** and **Custody Integrity Diagnostic** tabs alongside Registry and Overdue Circulation.
  - Overdue tab enhanced with live custodian search, minimum days overdue filter, storage location display, and CSV export action.
  - Location Transfers tab renders date range pickers, source/destination badges, transfer reasons, and pagination.
  - Custody Integrity Diagnostic tab displays summary banners, issue severity badges (`error`, `warning`), safe diagnostics, severity filter, and direct "Investigate / View File" actions.
- **Test Verification**:
  - Backend pytest suite: **8/8 tests passed** in `backend/tests/test_custody_integrity.py`; **361/361 passed** across the complete backend test suite.
  - Frontend Jest suite: **4/4 tests passed** in `PhysicalFilesIntegrity.test.tsx`; **77/77 passed** across all 13 frontend test suites.
  - Next.js production build (`npm run build`): Successfully compiled all 12 routes without type or linting errors.

---

### Task 7.1: End-to-End System Testing and Regression Acceptance

- **Full Lifecycle Integration Testing**:
  - Implemented comprehensive end-to-end regression acceptance test suite in `backend/tests/test_e2e_full_system.py`.
  - Validates cross-module workflows across Authentication, User & Department Administration, Document Upload & Versioning, Magic-byte Validation, Quarantining, Background OCR Extraction, PostgreSQL Full-Text Search, Legal Hold Blocking & Releases, Records Retention Schedules, Physical File Registration, Storage Location Capacity Enforcement, Check-In/Check-Out Circulation, Chain-of-Custody Integrity Diagnostics, and Append-Only Audit Logging.
- **Verification Results**:
  - Backend pytest suite: **367/367 passed**.
  - Frontend Jest suite: **77/77 passed** across 13 test suites.
  - Next.js production build: **Compiled successfully** without type or linting errors.

---

### Task 7.2: Security Hardening and Production Preparation

- **Security Hardening Implemented**:
  - **Production Environment Settings Safeguards**: `backend/app/config.py` enforces via Pydantic validator that when `ENVIRONMENT=production`, the application refuses to start if `JWT_SECRET_KEY` uses insecure development defaults (< 32 characters or begins with `dev_insecure_`), or if `ALLOWED_ORIGINS` is configured as a wildcard (`*`).
  - **Global Defense-in-Depth HTTP Response Headers**: `backend/app/main.py` middleware injects security headers across all responses (`X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`). Preserves same-origin iframe previewing while blocking cross-origin clickjacking.
  - **CORS Credentials Safety**: Wildcard origins are rejected from exchanging credentials (`allow_credentials = "*" not in origins_list`), preventing cross-origin credential leaks.
  - **Automated Regression Tests**: Added `backend/tests/test_security_hardening.py` testing global security header injection and production settings validation safeguards.
- **Verification Results**:
  - Backend pytest suite: **369/369 passed** (including security hardening regression tests).
  - Frontend Jest suite: **77/77 passed** across all 13 suites.
  - Next.js production build: **Compiled successfully** across all 12 routes.
  - Container health: All 4 Docker services healthy (`edrms-frontend`, `edrms-backend`, `edrms-worker`, `edrms-db`).

---

### Task 7.3: Performance, Reliability, Backup and Recovery Verification

- **Automated Backup & Disaster Recovery Framework**:
  - Implemented non-destructive host & container backup orchestrator in `scripts/run_backup.py` and `scripts/backup.sh`.
  - Captures PostgreSQL schema and data using `pg_dump -F c -b`, creates gzip tar archive of `/var/edrms/storage`, dumps deployment metadata (Alembic head, timestamps), and produces cryptographic SHA-256 manifests (`manifest.sha256`).
  - Implemented disaster recovery verification harness in `scripts/run_restore_test.py` and `scripts/restore_test.sh`.
  - **Actual Disaster Recovery Test Executed**:
    - Restores PostgreSQL dump into an isolated database (`edrms_restore_test_db`).
    - Extracts document storage archive into an isolated filesystem path (`/tmp/edrms_restore_test_storage`).
    - Validates manifest cryptographic integrity, confirms table record counts across 10 core tables, and verifies exact bit-for-bit SHA-256 checksums of stored document files against database version records.
    - Result: **100% verified (5/5 persistent documents passed SHA-256 integrity validation; all 10 core tables verified)**.
- **Performance Baseline Workload Measurements**:
  - Measured 11 core endpoints under sequential (N=30) and concurrent load (Concurrency=10, N=100 per workload):
    - Auth Login (Argon2id): **~139.8 ms**
    - Auth Current User (`/auth/me`): **avg 8.8 ms** | p50 8.8 ms | p95 10.5 ms
    - Document Listing (`/documents`): **avg 17.2 ms** | p50 17.0 ms | p95 21.9 ms (Throughput: **68.7 req/s**)
    - Full-Text Search (`/search?query=contract`): **avg 29.0 ms** | p50 28.7 ms | p95 32.8 ms (Throughput: **58.3 req/s**)
    - Audit Logs Listing (`/audit-logs`): **avg 16.7 ms** | p50 16.6 ms | p95 18.9 ms (Throughput: **69.5 req/s**)
    - Custody Integrity Diagnostic (`/physical-files/custody-integrity`): **avg 155.1 ms** | p50 144.0 ms | p95 216.7 ms
    - Error rate: **0.0%** across all tested workloads.
- **OCR Worker & Container Resilience**:
  - Worker restart and lease recovery verified: Expired leases automatically detected and safely reset to `queued` budget.
  - Multi-worker protection verified: Atomic queue claims using `SELECT ... FOR UPDATE SKIP LOCKED` prevent duplicate processing.
  - Container healthchecks active across all 4 services (`edrms-frontend`, `edrms-backend`, `edrms-worker`, `edrms-db`).
- **Proposed RPO / RTO Targets (Requiring Business Approval)**:
  - **Proposed RPO (Recovery Point Objective)**: **≤ 1 hour** (hourly differential/snapshot, daily full backup).
  - **Proposed RTO (Recovery Time Objective)**: **≤ 15 minutes** (tested automated restoration runtime: ~6.2 seconds for baseline dataset).

---

### Task 7.4: UI Polish, Usability and Demo Readiness

- **Enterprise Design System & Usability Polish**:
  - Implemented professional light-theme design system refinements in `frontend/src/app/globals.css`:
    - Global accessible `:focus-visible` ring indicators (`outline: 2px solid #2563eb`).
    - Standardized modern system font stack with subpixel antialiasing.
    - Native `prefers-reduced-motion: reduce` support disabling unnecessary transitions for accessibility.
    - Sleek custom scrollbars for data tables and multi-row panels.
  - Added dedicated custom 404 handler (`frontend/src/app/not-found.tsx`) with contextual return navigation.
- **Stakeholder Demo Authentication & Role Switcher**:
  - Enhanced Header sign-in modal (`frontend/src/components/Header.tsx` and `AuthContext.tsx`):
    - Added 1-click demo role fill for all 5 operational roles:
      - **System Admin**: `admin@example.com`
      - **Records Officer**: `records.officer@example.com`
      - **Department User**: `dept.user@example.com`
      - **Approver**: `approver@example.com`
      - **Auditor**: `auditor@example.com`
    - Dual authentication mode: Seamless email/password credentials or raw JWT Bearer token authentication.
- **Operational Dashboard Overhaul**:
  - Replaced static phase placeholders in `frontend/src/app/page.tsx` with live enterprise governance overview:
    - Real-time authorized operational metrics (Total Digital Documents, Physical File Registry, Storage Locations, Approver Review Inbox, Overdue Circulation Items).
    - Live container health and connectivity probe badges (FastAPI, PostgreSQL connection pool, Durable OCR Worker).
    - Role-aware card routing and department isolation context.
- **Document Upload & Workflow Discoverability**:
  - Added native Document Upload modal in `frontend/src/app/documents/page.tsx` supporting PDF, PNG, JPG, and TIFF (≤25MB) with magic-byte validation and immediate Version 1 staging.
  - Clear plain-language status badges, empty states, and error handling.
- **Verification Results**:
  - Frontend Jest suite: **77/77 passed** across all 13 test suites.
  - Next.js production build (`npm run build`): **12/12 routes compiled with 0 errors**.
  - All 4 Docker services healthy and active.

---

### Task 7.5: Production Deployment, Verification and Final Handover

- **Production Readiness & Gate Verification**:
  - Gated demo-role quick-fill buttons in `frontend/src/components/Header.tsx` strictly behind non-production environment checks (`process.env.NEXT_PUBLIC_ENVIRONMENT !== "production"` and `process.env.NODE_ENV !== "production"`).
  - Authored `.env.production.example` safe production environment template with clear security constraints.
  - Authored `docker/nginx/edrms.conf` production reverse proxy configuration template featuring TLS 1.3 termination, HSTS (`max-age=63072000`), secure proxy headers, and private container isolation.
  - Verified linear Alembic migration history ending at head revision `851619ad95bc`.
  - Deployment Authorization Gate Assessment: Local Docker environment is verified and operational; live production deployment is held in **Ready for Deployment** state awaiting explicit target infrastructure details and authorized domain credentials.
- **Verification Results**:
  - Backend pytest suite: **369/369 passed** (100% pass rate).
  - Frontend Jest suite: **77/77 passed** across all 13 suites.
  - Next.js production build (`npm run build`): **12/12 routes compiled with 0 errors**.
  - Docker Compose: All 4 services healthy (`edrms-frontend`, `edrms-backend`, `edrms-worker`, `edrms-db`).
  - Automated Backup & Disaster Recovery: Confirmed functional with bit-for-bit cryptographic SHA-256 integrity verification.

---

## Database Migrations (Alembic)

Alembic uses the application's SQLAlchemy declarative metadata (`app.models.Base.metadata`) and connection settings from `app.config.settings.DATABASE_URL`.

### Running Migrations in Docker

To check current migration revision:
```bash
docker exec edrms-backend alembic current
```

To view migration history:
```bash
docker exec edrms-backend alembic history --verbose
```

To apply all pending migrations up to the latest head:
```bash
docker exec edrms-backend alembic upgrade head
```

To rollback the last migration:
```bash
docker exec edrms-backend alembic downgrade -1
```

---

## Running Automated Tests

Run the complete test suite inside the container:
```bash
docker exec edrms-backend pytest -v
```

---

---

## Documentation & User Guides

Comprehensive system manuals and guides are located in the [`docs/`](docs/) directory:

- 📖 **[User & Operator Guide](docs/USER_GUIDE.md)**: Complete end-user, records officer, approver, and system administrator reference manual covering all digital and physical records workflows, permissions, and troubleshooting.
- 🛡️ **[Security Hardening Report](task_7_2_security_hardening_report.md)**: Security controls, JWT validation, Argon2id, and vulnerability remediations.
- ⚡ **[Performance & Disaster Recovery Manual](task_7_3_performance_and_recovery_report.md)**: Backup benchmarks, database dumps, and SHA-256 storage restoration procedures.
- 🚀 **[Final Handover & Deployment Report](task_7_5_final_handover_report.md)**: Architecture topologies, operational runbooks, and production readiness checks.

---

## Stopping the Application

To stop all services:
```bash
docker compose down
```
To stop services and remove volumes (Warning: resets database and storage data):
```bash
docker compose down -v
```

