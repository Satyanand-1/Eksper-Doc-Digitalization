# Enterprise Electronic Document and Records Management System (EDRMS)
# User & Operator Guide

**Version:** 1.0 (Enterprise Release)  
**Applicability:** EDRMS Web Application & Core Services  
**Target Audience:** End Users, Department Staff, Approvers, Records Officers, Auditors, and System Administrators.

---

## Table of Contents

1. [Introduction & System Overview](#1-introduction--system-overview)
2. [User Roles, Governance & Permission Boundaries](#2-user-roles-governance--permission-boundaries)
3. [Logging In & Account Navigation](#3-logging-in--account-navigation)
4. [Digital Document Management](#4-digital-document-management)
   - 4.1 [Uploading a New Document](#41-uploading-a-new-document)
   - 4.2 [Document Metadata & Classification](#42-document-metadata--classification)
   - 4.3 [Document Versioning & Revisions](#43-document-versioning--revisions)
   - 4.4 [Downloading & Verifying Document Files](#44-downloading--verifying-document-files)
5. [OCR & Intelligent Full-Text Search](#5-ocr--intelligent-full-text-search)
   - 5.1 [Automated Background OCR Processing](#51-automated-background-ocr-processing)
   - 5.2 [Searching Documents & Extracted Content](#52-searching-documents--extracted-content)
6. [Review & Approval Workflows](#6-review--approval-workflows)
   - 6.1 [Submitting Documents for Review](#61-submitting-documents-for-review)
   - 6.2 [Managing the Approver Inbox](#62-managing-the-approver-inbox)
   - 6.3 [Approving, Rejecting, and Tracking Decisions](#63-approving-rejecting-and-tracking-decisions)
7. [Retention Schedules & Legal Holds](#7-retention-schedules--legal-holds)
   - 7.1 [Configuring Retention Policies](#71-configuring-retention-policies)
   - 7.2 [Applying Retention to Documents](#72-applying-retention-to-documents)
   - 7.3 [Placing and Lifting Legal Holds](#73-placing-and-lifting-legal-holds)
8. [Physical File Registry & Storage Locations](#8-physical-file-registry--storage-locations)
   - 8.1 [Physical Storage Location Hierarchy](#81-physical-storage-location-hierarchy)
   - 8.2 [Managing Capacity & Occupancy](#82-managing-capacity--occupancy)
   - 8.3 [Registering Physical Files](#83-registering-physical-files)
9. [Physical File Circulation & Chain of Custody](#9-physical-file-circulation--chain-of-custody)
   - 9.1 [Barcode & QR Code Label Generation](#91-barcode--qr-code-label-generation)
   - 9.2 [Physical File Check-Out](#92-physical-file-check-out)
   - 9.3 [Physical File Check-In](#93-physical-file-check-in)
   - 9.4 [Storage Location Transfers](#94-storage-location-transfers)
   - 9.5 [Overdue Circulation Tracking](#95-overdue-circulation-tracking)
   - 9.6 [Chain-of-Custody Audit & Integrity Diagnostics](#96-chain-of-custody-audit--integrity-diagnostics)
10. [Audit Trail & Compliance Inspection](#10-audit-trail--compliance-inspection)
11. [User Administration & Access Governance](#11-user-administration--access-governance)
12. [Frequently Asked Questions & Troubleshooting](#12-frequently-asked-questions--troubleshooting)

---

## 1. Introduction & System Overview

The **Electronic Document and Records Management System (EDRMS)** provides a unified, highly governed platform for managing an organization's complete document lifecycle. It bridges physical filing cabinets with modern digital records management, ensuring compliance, auditability, tamper-resistance, and seamless operational discovery.

### Key Capabilities
- **Digital Records Repository**: Secure ingestion, metadata classification, immutable versioning, and SHA-256 cryptographic integrity verification.
- **Durable Optical Character Recognition (OCR)**: Asynchronous background text extraction for scanned documents and PDF/image uploads.
- **PostgreSQL Full-Text Search**: Sub-second search across titles, subjects, reference numbers, and OCR-extracted text contents.
- **Review & Approval Workflows**: Structured multi-step reviews with email/inbox notifications and immutable decision justification logs.
- **Records Retention & Legal Holds**: Enforce retention schedules while protecting records under active litigation or inquiry from premature disposal.
- **Physical File Tracking**: Complete custody ledger for paper records, including hierarchical storage location management, QR/barcode generation, check-out/check-in tracking, overdue monitors, and chain-of-custody diagnostics.
- **Tamper-Evident Audit Trail**: Every access, download, status change, and modification is permanently recorded.

---

## 2. User Roles, Governance & Permission Boundaries

EDRMS implements strict **Role-Based Access Control (RBAC)** coupled with **Departmental Data Isolation**. A user's capabilities depend on their assigned system role and department:

| Role Name | System Key | Typical Title | Responsibilities & Permission Boundaries |
| :--- | :--- | :--- | :--- |
| **System Administrator** | `admin` | IT Admin / SysAdmin | Full system control. Can provision and deactivate users, reset passwords, configure storage hierarchies, and inspect system audit logs. |
| **Records Officer** | `records_officer` | Chief Records Manager | Manages organization-wide records compliance. Defines retention policies, places/lifts legal holds, audits chain-of-custody, and oversees physical registry. |
| **Department User** | `department_user` | Action Officer / Staff | Day-to-day creator. Ingests documents, edits drafts, uploads versions, submits documents for review, and checks out physical files within assigned department. |
| **Approver** | `approver` | Team Lead / Director | Reviews pending documents in the Review Inbox. Can approve documents into active status or reject them with mandatory comments. |
| **Auditor** | `auditor` | Compliance Officer | Read-only compliance inspection. Can review documents, verify chain of custody, examine retention schedules, and view immutable audit trails. |
| **Read-Only User** | `read_only` | General Employee | Read-only viewer. Can search and view non-confidential approved documents within permitted scope. Cannot modify or upload data. |

> [!IMPORTANT]
> **Departmental Isolation Policy**: Users with role `department_user` or `approver` only have visibility into records belonging to their assigned department. Cross-department governance roles (`admin`, `records_officer`, `auditor`) have enterprise-wide visibility.

---

## 3. Logging In & Account Navigation

### Accessing the Web Application
Open a supported web browser (Chrome, Firefox, Edge, Safari) and navigate to the application URL:
- **Local Environment:** `http://localhost:3000`
- **Corporate Network:** `https://edrms.yourorganization.internal`

### Logging In
1. Enter your registered corporate **Email Address** and **Password** in the login form.
2. Click **Sign In**.
3. Upon successful authentication, your secure session is initialized, and your personalized role badge and department context will appear in the top-right header navigation.

*(In local/demo development environments, the top bar includes a quick-fill role switcher allowing you to switch between demo profiles for demonstration and testing purposes).*

### Top Navigation Bar
The header provides instant access to core workspaces according to your permissions:
- **Documents**: Browse, search, and upload digital files.
- **Workflows**: Review Inbox and approval tracking.
- **Retention**: Compliance retention rules and legal-hold monitors.
- **Physical Files**: Paper registry, barcode generation, check-outs, and circulation history.
- **Storage Locations**: Hierarchy explorer and shelf/box capacity metrics.
- **Admin**: User directory and tamper-evident audit logs *(Admin only)*.

---

## 4. Digital Document Management

### 4.1 Uploading a New Document
1. Navigate to **Documents** in the navigation menu.
2. Click the **Upload Document** button in the upper right corner.
3. In the upload dialog:
   - **File Selection**: Click **Select File** or drag and drop your document. Supported formats include:
     - PDF documents (`.pdf`)
     - TIFF images (`.tiff`, `.tif`)
     - JPEG / PNG scans (`.jpg`, `.jpeg`, `.png`)
     - Maximum file size: **25 MB**.
   - **Document Title**: Enter a clear, descriptive name (e.g., `FY2026 Procurement Policy Guidelines`).
   - **Subject / Description**: Provide background details or summary context.
   - **Classification**: Select the security classification level:
     - `Public`: Open to all staff.
     - `Internal`: Standard organizational access.
     - `Confidential`: Restricted to department staff and authorized roles.
     - `Restricted`: Strictly limited to designated governance roles.
   - **Department**: Automatically pre-filled with your department.
4. Click **Submit Upload**.
5. The system performs automatic **Magic-Byte File Verification** to guarantee the file matches its declared extension and contains no disguised binaries. Once validated, Version 1.0 is created and queued for automated OCR text extraction.

### 4.2 Document Metadata & Classification
Each uploaded document is assigned a unique, sequential reference number (e.g., `DOC-2026-0001`). 

Metadata fields tracked for every document:
- **Reference Number**: System-generated identifier.
- **Status**: Lifecycle status (`draft`, `under_review`, `active`, `archived`, `disposed`).
- **Owner / Creator**: The user who created the record.
- **Creation Timestamp**: ISO-standard creation record.
- **Cryptographic Hash**: SHA-256 fingerprint of the active version.

### 4.3 Document Versioning & Revisions
EDRMS ensures historical versions are never overwritten or lost.
1. Open the document detail page by clicking on the document title from the document list.
2. In the **Document Versions** section, click **Upload New Version**.
3. Select the updated file and provide a mandatory **Change Summary** describing the revisions made.
4. Click **Save New Version**.
5. The version number increments automatically (e.g., `v1` $\rightarrow$ `v2`), and the new file becomes the active version while all prior revisions remain accessible for historical review.

### 4.4 Downloading & Verifying Document Files
1. On the document detail page or version list, click the **Download** button.
2. The download stream is transmitted securely with sanitized file names.
3. Every download transaction is permanently recorded in the system audit trail.

---

## 5. OCR & Intelligent Full-Text Search

### 5.1 Automated Background OCR Processing
When a PDF or image is uploaded, an asynchronous background worker takes custody of the file:
1. The file is placed in an atomic, crash-resilient queue.
2. The **Tesseract OCR 5.x** engine extracts textual content from images and embedded PDF layers.
3. The extracted text is indexed directly into the PostgreSQL database using native `tsvector` representations.
4. If a document scan is distorted or temporarily unreadable, a Records Officer can inspect the OCR Job status and trigger a controlled retry.

### 5.2 Searching Documents & Extracted Content
1. Navigate to **Documents**.
2. Locate the search bar at the top of the page.
3. Enter keywords, document references, or text phrases from within the file body.
   - Example query: `"procurement vendor requirements"`
   - Reference query: `"DOC-2026-0042"`
4. Use the filter dropdowns to narrow results by:
   - **Department**: Filter to specific operational units.
   - **Classification**: Public, Internal, Confidential, Restricted.
   - **Lifecycle Status**: Active, Draft, Under Review, Archived.
5. Matching documents are ranked by relevance and displayed with highlighted metadata snippets.

---

## 6. Review & Approval Workflows

### 6.1 Submitting Documents for Review
Documents in `draft` status must be approved before becoming officially `active`:
1. Open the document detail view.
2. Click **Submit for Review**.
3. Select the assigned Approver or designate the departmental approval pool.
4. Add any relevant submission remarks or deadlines.
5. Click **Confirm Submission**.
6. The document status transitions to `under_review`, and an alert notification is dispatched to the designated approver's inbox.

### 6.2 Managing the Approver Inbox
1. Approvers navigate to **Workflows** $\rightarrow$ **Review Inbox**.
2. The inbox displays all items awaiting your decision, including submission date, submitter name, department, and priority.
3. Click on any workflow item to open the review inspection drawer.

### 6.3 Approving, Rejecting, and Tracking Decisions
Within the review inspection drawer:
- **To Approve**:
  1. Review the document file, metadata, and version history.
  2. Click **Approve Document**.
  3. Enter optional approval comments.
  4. The document status transitions to `active`, and a confirmation event is logged.
- **To Reject**:
  1. Click **Reject Document**.
  2. Enter a **Mandatory Rejection Reason** explaining what changes or corrections are required.
  3. The document reverts to `draft` status, notifying the submitter to revise and resubmit.

---

## 7. Retention Schedules & Legal Holds

### 7.1 Configuring Retention Policies
*(Records Officer & Admin Roles Only)*
1. Navigate to **Retention** in the top navigation.
2. Click **Create Retention Rule**.
3. Define the policy rules:
   - **Policy Name**: (e.g., `Financial Audits - 7 Year Retain`).
   - **Retention Period**: Number of years (e.g., `7`).
   - **Trigger Event**: Created Date or Last Revised Date.
   - **Terminal Action**: `Archive` or `Disposal Review`.
4. Click **Save Policy**.

### 7.2 Applying Retention to Documents
1. Open any active document's detail view.
2. In the **Governance & Retention** card, click **Assign Policy**.
3. Select the applicable policy from the list.
4. The system automatically computes the **Eligibility Expiration Date**.

### 7.3 Placing and Lifting Legal Holds
If an organization faces litigation, audit inquiry, or regulatory investigation, records must be safeguarded from routine archival or destruction:
- **Placing a Legal Hold**:
  1. Open the document or physical file record.
  2. Click **Place Legal Hold**.
  3. Enter the official legal hold reference / case identifier and justification.
  4. A prominent red **LEGAL HOLD ACTIVE** badge appears on the file. While active, all deletion, purging, and terminal retention disposals are strictly blocked.
- **Lifting a Legal Hold**:
  1. Once the legal proceeding concludes, click **Release Legal Hold**.
  2. Provide the authorization rationale and officer sign-off.
  3. Normal retention schedule evaluation resumes.

---

## 8. Physical File Registry & Storage Locations

### 8.1 Physical Storage Location Hierarchy
EDRMS allows modeling physical storage facilities in a configurable tree structure:
```
Organization
 └── Building (e.g., Headquarters Tower)
      └── Floor (e.g., 3rd Floor Archives)
           └── Room (e.g., Records Room 302)
                └── Cabinet (e.g., Steel Cabinet A)
                     └── Shelf (e.g., Shelf 4)
                          └── Box (e.g., Box B-2026-09)
```
1. Navigate to **Storage Locations**.
2. Use the interactive tree navigator to browse buildings, rooms, and storage containers.
3. Click **Add Location Node** to define a new facility, cabinet, or box.

### 8.2 Managing Capacity & Occupancy
- Every storage node (shelf, box, cabinet) can be configured with a **Maximum File Capacity** (e.g., Box holds 25 files).
- The system automatically counts assigned physical files and computes real-time capacity percentages.
- **Overfill Protection**: Attempting to assign a file to a box that has reached 100% capacity is prevented by the system with an occupancy warning.

### 8.3 Registering Physical Files
1. Navigate to **Physical Files** $\rightarrow$ **Register Physical File**.
2. Enter the record details:
   - **File Title**: Descriptive paper folder title.
   - **Department**: Responsible department.
   - **File Type**: Case file, dossier, voucher bundle, contract binder.
   - **Sensitivity**: Standard, Confidential, or Restricted.
   - **Initial Storage Location**: Assign to an available shelf or box.
3. Click **Register File**.
4. The system assigns a unique reference code (e.g., `PHYS-2026-0001`).

---

## 9. Physical File Circulation & Chain of Custody

### 9.1 Barcode & QR Code Label Generation
Every registered physical file can be labeled with high-contrast, scannable QR and Barcode identifiers:
1. Open the physical file record in **Physical Files**.
2. Click **Print Label** or **Preview Identification Label**.
3. The printable label preview renders:
   - High-density 2D QR Code.
   - Linear Code-128 Barcode.
   - Physical File Reference (`PHYS-2026-XXXX`).
   - Title, Department, and Current Storage Location.
4. Click **Print** to send to any standard thermal or desktop label printer.

### 9.2 Physical File Check-Out
When a staff member requires a physical file from the archives:
1. Navigate to the physical file record (or scan its QR code with the integrated camera scanner).
2. Click **Check Out File**.
3. Fill in the circulation details:
   - **Borrower / Custodian**: Select the user taking physical custody.
   - **Due Date**: Date by which the file must be returned.
   - **Purpose / Reason**: Operational justification (e.g., `Audit review preparation`).
4. Click **Confirm Check-Out**.
5. The file status changes to `Checked Out`, the custody ledger records the handoff, and the borrower assumes recorded custody.

### 9.3 Physical File Check-In
When the paper file is returned:
1. Locate the file record or scan its label.
2. Click **Check In File**.
3. Record:
   - **Receiving Officer**: Verifying clerk.
   - **Condition Verified**: Intact, damaged, or pages noted.
   - **Return Location**: Confirm return to default box or assign new shelf.
4. Click **Confirm Check-In**.
5. The file status returns to `In Storage`, and the custody duration is closed in the ledger.

### 9.4 Storage Location Transfers
To move physical files between locations (e.g., relocating from a departmental desk box to permanent archival vault):
1. Open the file record and click **Transfer Location**.
2. Select the destination facility, room, and box.
3. Provide the reason for movement.
4. Confirm transfer. The historical movement history records the old location, new location, timestamp, and authorizing user.

### 9.5 Overdue Circulation Tracking
- The system automatically monitors active check-outs against their specified due dates.
- Files past their due date display an amber/red **OVERDUE** badge.
- Records Officers can view the dedicated **Overdue Circulation Report** to follow up with custodians and issue reminder notices.

### 9.6 Chain-of-Custody Audit & Integrity Diagnostics
EDRMS maintains a strict, chronological custody log for every paper record.
1. Open any physical file record and click **Custody Timeline**.
2. The view displays every historical custodian, checkout timestamp, check-in timestamp, and condition report.
3. The **Chain-of-Custody Integrity Diagnostic** automatically verifies that there are no unexplained gaps in custody, broken chains, or missing check-in events.

---

## 10. Audit Trail & Compliance Inspection

EDRMS implements an append-only, tamper-evident audit logging engine:
- **Logged Operations**:
  - `LOGIN_SUCCESS` / `LOGIN_FAILURE`
  - `DOCUMENT_CREATED`, `DOCUMENT_UPDATED`, `DOCUMENT_DOWNLOADED`
  - `VERSION_CREATED`
  - `WORKFLOW_SUBMITTED`, `WORKFLOW_APPROVED`, `WORKFLOW_REJECTED`
  - `RETENTION_ASSIGNED`, `LEGAL_HOLD_APPLIED`, `LEGAL_HOLD_RELEASED`
  - `PHYSICAL_FILE_REGISTERED`, `CHECKOUT`, `CHECKIN`, `LOCATION_TRANSFER`
- **Audit Detail View** (Admin & Auditor Roles):
  - Filter by User, Action, Entity Type, or Date Range.
  - Inspect IP address, client user agent, and payload diffs.
  - Export audit logs for external regulatory reporting.

---

## 11. User Administration & Access Governance

*(System Administrator Role Only)*
1. Navigate to **Admin** $\rightarrow$ **Users**.
2. **Create New User**:
   - Provide Full Name, Corporate Email Address, and Initial Password.
   - Assign Role (`admin`, `records_officer`, `department_user`, `approver`, `auditor`, `read_only`).
   - Assign Primary Department.
3. **Account Deactivation**:
   - Deactivating a user immediately revokes access without deleting their historical audit records, past approvals, or document authorship links.
4. **Password Reset**:
   - Administrators can trigger secure password updates hashed using industry-standard **Argon2id**.

---

## 12. Frequently Asked Questions & Troubleshooting

### Q1: I uploaded a document, but its text is not showing up in search results.
**Answer:** Document text extraction is performed asynchronously by the background OCR worker. For large multi-page scans, OCR extraction may take between 5 to 30 seconds. Check the **OCR Status** badge on the document detail page; once marked `Completed`, full-text search is active.

### Q2: Why am I receiving an "Access Denied / Department Mismatch" error?
**Answer:** Standard departmental users can only access records assigned to their own department. If you need access to records in another department, contact your System Administrator to adjust your role or departmental assignment.

### Q3: Why can't I check in a physical file into a specific box?
**Answer:** That storage box has reached its maximum configured capacity. Select another box with available capacity or have a Records Officer increase the capacity limit if the container allows.

### Q4: Can an approved document be deleted?
**Answer:** No. In accordance with records governance principles, active documents cannot be arbitrarily deleted. They must follow established retention schedules and be formally dispositioned by an authorized Records Officer. If a record has an active Legal Hold, it cannot be disposed under any circumstances.

### Q5: How do I verify that an exported document has not been altered?
**Answer:** Every document version displays its cryptographic **SHA-256 Checksum** on the version history tab. You can compute the SHA-256 hash of your downloaded file using standard operating system utilities (`certutil -hashfile <file> SHA256` on Windows, or `sha256sum <file>` on Linux/macOS) and verify that it matches the recorded hash exactly.

---
*End of User & Operator Guide*
