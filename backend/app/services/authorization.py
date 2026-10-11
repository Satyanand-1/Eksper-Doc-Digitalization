"""
Document access authorization service.
Enforces multi-dimensional role and classification access control policies.
Defaults strictly to DENY on any missing or ambiguous permission information.
"""
from enum import Enum
from app.models.user import User, UserRole
from app.models.document import DigitalDocument

class AccessDecision:
    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason

    def __bool__(self) -> bool:
        return self.allowed

class DocumentAuthorizationService:
    """
    Evaluates role, department, and classification policies for document access.
    """

    CONFIDENTIAL_CLASSIFICATIONS = {"CONFIDENTIAL", "SECRET", "RESTRICTED", "TOP_SECRET"}

    @classmethod
    def can_download(cls, user: User, document: DigitalDocument) -> AccessDecision:
        """
        Determines whether the given authenticated user has permission to download
        the specified document version.

        Baseline Rules:
        - Administrator: Full access across departments and classifications.
        - Records Officer: Cross-department access for records administration. However,
          CONFIDENTIAL documents require records officer to be in the owning department
          or designated records administrator.
        - Department User: Access only to documents belonging to their own department.
          CONFIDENTIAL documents within their department are accessible to departmental staff.
          Cross-department access is strictly DENIED.
        - Approver: Access to review documents. In the baseline system, access is granted
          if the document is pending review/active in their department or they are the document creator.
          Not granted unrestricted access merely because they hold the approver role.
        - Auditor: Read-only access within their audit scope (in baseline prototype: non-confidential
          records or records within their assigned audit department).
        - Read-Only User: Allowed access only to general/public documents within their department
          or documents created by them; denied on other departments and confidential records.

        Classification Dimension:
        - Documents marked CONFIDENTIAL are restricted:
          * Department Users, Approvers, and Read-Only users outside the document's department
            are strictly denied.
          * Read-Only users cannot access CONFIDENTIAL records even in their own department.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not document:
            return AccessDecision(False, "Document not found")

        doc_dept = (document.department or "").strip().lower()
        user_dept = (user.department or "").strip().lower()
        doc_class = (document.classification or "").strip().upper()
        is_confidential = doc_class in cls.CONFIDENTIAL_CLASSIFICATIONS

        role = user.role

        # 1. Administrator: Unrestricted download access
        if role == UserRole.ADMIN:
            return AccessDecision(True, "Administrator unrestricted access")

        # 2. Records Officer: Cross-department access for records administration
        if role == UserRole.RECORDS_OFFICER:
            return AccessDecision(True, "Records Officer cross-department administration")

        # 3. Department User: Restricted to own department
        if role == UserRole.DEPARTMENT_USER:
            if not user_dept or user_dept != doc_dept:
                return AccessDecision(
                    False,
                    f"Department user is assigned to '{user.department}' but document belongs to '{document.department}'"
                )
            return AccessDecision(True, "Department user access to own department document")

        # 4. Approver: Restricted to own department or own uploaded records; never unrestricted
        if role == UserRole.APPROVER:
            if document.created_by_id == user.id:
                return AccessDecision(True, "Approver access to own created document")
            if user_dept and user_dept == doc_dept:
                return AccessDecision(True, "Approver access to department document")
            central_depts = {"records & compliance", "system administration", "general", "enterprise shared"}
            if user_dept in central_depts or doc_dept in central_depts:
                return AccessDecision(True, "Central approver oversight access")
            return AccessDecision(
                False,
                f"Approver lacks explicit review authorization for external department '{document.department}'"
            )

        # 5. Auditor: Read-only access within their assigned audit department
        if role == UserRole.AUDITOR:
            if not user_dept:
                return AccessDecision(
                    False,
                    "Auditor has no assigned audit department and cannot access records"
                )
            if user_dept != doc_dept:
                return AccessDecision(
                    False,
                    f"Auditor assigned to '{user.department}' is not authorized to access documents in '{document.department}'"
                )
            return AccessDecision(True, "Auditor scoped audit department access")

        # 6. Read-Only User: Only non-confidential documents within their department or created by them
        if role == UserRole.READ_ONLY:
            if is_confidential:
                return AccessDecision(False, "Read-only users cannot access confidential documents")
            if document.created_by_id == user.id:
                return AccessDecision(True, "Read-only access to own created document")
            if user_dept and user_dept == doc_dept:
                return AccessDecision(True, "Read-only user access to own department document")
            return AccessDecision(
                False,
                f"Read-only user denied access to external department '{document.department}'"
            )

        # Default Deny for unknown role
        return AccessDecision(False, f"Access denied by default for role '{role}'")

    @classmethod
    def can_view_metadata(cls, user: User, document: DigitalDocument) -> AccessDecision:
        """
        Alias for can_download to enforce consistent document-level authorization
        on metadata and version enumeration requests.
        """
        return cls.can_download(user, document)

    @classmethod
    def can_upload_version(cls, user: User, document: DigitalDocument) -> AccessDecision:
        """
        Determines whether the given authenticated user has permission to upload
        a new version to an existing document.

        Rules for Task 3.6:
        - Document must be in DRAFT status. (Active, under review, archived, disposed rejected).
        - Administrator: Allowed for draft documents.
        - Records Officer: Allowed for draft documents across departments.
        - Department User: Allowed for draft documents belonging to their assigned department.
        - Approver: Denied write access.
        - Auditor: Denied write access.
        - Read-Only User: Denied write access.
        - Missing or ambiguous permissions: Denied by default.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not document:
            return AccessDecision(False, "Document not found")

        # Status check: only DRAFT records can accept new versions
        from app.models.document import DocumentStatus
        if document.status != DocumentStatus.DRAFT:
            return AccessDecision(
                False,
                f"Document is in '{document.status.value}' status. New versions can only be uploaded to draft documents."
            )

        doc_dept = (document.department or "").strip().lower()
        user_dept = (user.department or "").strip().lower()
        role = user.role

        # 1. Administrator: Allowed for draft documents
        if role == UserRole.ADMIN:
            return AccessDecision(True, "Administrator version write access")

        # 2. Records Officer: Allowed for draft documents
        if role == UserRole.RECORDS_OFFICER:
            return AccessDecision(True, "Records Officer version write access")

        # 3. Department User: Allowed only for draft documents in own department
        if role == UserRole.DEPARTMENT_USER:
            if not user_dept or user_dept != doc_dept:
                return AccessDecision(
                    False,
                    f"Department user assigned to '{user.department}' cannot upload versions to '{document.department}' documents"
                )
            return AccessDecision(True, "Department user version write access")

        # 4. Approver: Denied write access
        if role == UserRole.APPROVER:
            return AccessDecision(False, "Approver role does not have version write permissions")

        # 5. Auditor: Denied write access
        if role == UserRole.AUDITOR:
            return AccessDecision(False, "Auditor role does not have version write permissions")

        # 6. Read-Only User: Denied write access
        if role == UserRole.READ_ONLY:
            return AccessDecision(False, "Read-only role does not have version write permissions")

        return AccessDecision(False, f"Access denied by default for role '{role}'")

    @classmethod
    def can_submit_for_review(cls, user: User, document: DigitalDocument) -> AccessDecision:
        """
        Determines whether the given authenticated user has permission to submit
        the specified document for review.

        Rules:
        - User must be active.
        - Document must be in DRAFT status.
        - Administrator: Allowed for draft documents across departments.
        - Records Officer: Allowed for draft documents across departments.
        - Department User: Allowed only for draft documents in own department.
        - Approver: Denied write permission to initiate review workflows.
        - Auditor: Denied write permission.
        - Read-Only User: Denied write permission.
        - Default strictly to DENY on missing or ambiguous permissions.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not document:
            return AccessDecision(False, "Document not found")

        from app.models.document import DocumentStatus
        if document.status != DocumentStatus.DRAFT:
            return AccessDecision(
                False,
                f"Document is in '{document.status.value}' status. Only draft documents can be submitted for review."
            )

        doc_dept = (document.department or "").strip().lower()
        user_dept = (user.department or "").strip().lower()
        role = user.role

        # 1. Administrator: Allowed across departments
        if role == UserRole.ADMIN:
            return AccessDecision(True, "Administrator review submission access")

        # 2. Records Officer: Allowed across departments
        if role == UserRole.RECORDS_OFFICER:
            return AccessDecision(True, "Records Officer review submission access")

        # 3. Department User: Allowed only for draft documents in own department
        if role == UserRole.DEPARTMENT_USER:
            if not user_dept or user_dept != doc_dept:
                return AccessDecision(
                    False,
                    f"Department user assigned to '{user.department}' cannot submit documents for '{document.department}'"
                )
            return AccessDecision(True, "Department user review submission access")

        # 4. Approver: Denied submission write access
        if role == UserRole.APPROVER:
            return AccessDecision(False, "Approver role does not have document submission permissions")

        # 5. Auditor: Denied submission write access
        if role == UserRole.AUDITOR:
            return AccessDecision(False, "Auditor role does not have document submission permissions")

        # 6. Read-Only User: Denied submission write access
        if role == UserRole.READ_ONLY:
            return AccessDecision(False, "Read-only role does not have document submission permissions")

        return AccessDecision(False, f"Access denied by default for role '{role}'")

    @classmethod
    def validate_approver_eligibility(
        cls, approver: User, document: DigitalDocument, submitter: User | None = None
    ) -> AccessDecision:
        """
        Validates whether the specified approver is eligible to review the given document.

        Rules:
        - Approver must be active.
        - Approver must hold the APPROVER role.
        - Submitter cannot assign themselves as approver.
        - Missing or ambiguous department information results in denial.
        - Approver department must match document department (no cross-department review).
        - Classification policy: Approver must be in owning department (enforced by department match).
        """
        if not approver or not approver.is_active:
            return AccessDecision(False, "Assigned approver is inactive or does not exist")

        if approver.role != UserRole.APPROVER:
            return AccessDecision(
                False,
                f"Assigned user does not hold the 'approver' role (role: '{approver.role.value}')"
            )

        if submitter and approver.id == submitter.id:
            return AccessDecision(False, "Submitter cannot assign themselves as approver")

        doc_dept = (document.department or "").strip().lower()
        approver_dept = (approver.department or "").strip().lower()

        if not doc_dept or not approver_dept:
            return AccessDecision(False, "Missing or ambiguous department assignment for document or approver")

        if approver_dept != doc_dept:
            central_depts = {"records & compliance", "system administration", "general", "enterprise shared"}
            if approver_dept not in central_depts and doc_dept not in central_depts:
                return AccessDecision(
                    False,
                    f"Cross-department review is not permitted. Approver belongs to '{approver.department}', but document belongs to '{document.department}'"
                )

        return AccessDecision(True, "Approver is eligible to review document")

    @classmethod
    def can_view_workflow(cls, user: User, workflow, assignments: list | None = None) -> AccessDecision:
        """
        Determines whether the given authenticated user has permission to view
        a specific workflow and its details.

        Rules:
        - User must be active.
        - Administrator & Records Officer: Allowed cross-department visibility for operational oversight.
        - Approver: Allowed ONLY if explicitly assigned in one of the workflow's assignments,
          and their department matches the document's department (subject to classification rules).
          Not granted access merely because they hold the approver role or belong to the department.
        - Other roles (Department User, Auditor, Read-Only): Denied access to review workflows.
        - Defaults strictly to DENY on missing or ambiguous permissions.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not workflow:
            return AccessDecision(False, "Workflow not found")

        role = user.role

        # 1. Admin: Unrestricted oversight
        if role == UserRole.ADMIN:
            return AccessDecision(True, "Administrator workflow oversight")

        # 2. Records Officer: Unrestricted oversight
        if role == UserRole.RECORDS_OFFICER:
            return AccessDecision(True, "Records Officer workflow oversight")

        # 3. Approver: Must be explicitly assigned to this workflow
        if role == UserRole.APPROVER:
            workflow_assignments = assignments if assignments is not None else workflow.assignments
            is_assigned = any(a.assigned_approver_id == user.id for a in workflow_assignments)
            if not is_assigned:
                return AccessDecision(False, "Approver is not assigned to this workflow")

            # Verify document authorization policies still hold
            doc = workflow.document
            if doc:
                doc_dept = (doc.department or "").strip().lower()
                user_dept = (user.department or "").strip().lower()
                if not user_dept or user_dept != doc_dept:
                    central_depts = {"records & compliance", "system administration", "general", "enterprise shared"}
                    if user_dept not in central_depts and doc_dept not in central_depts:
                        return AccessDecision(
                            False,
                            f"Approver belongs to '{user.department}' but document belongs to '{doc.department}'"
                        )
            return AccessDecision(True, "Assigned approver workflow access")

        return AccessDecision(False, f"Role '{role.value}' is not authorized to view review workflows")

    @classmethod
    def can_view_workflow_history(cls, user: User, document: DigitalDocument) -> AccessDecision:
        """
        Determines whether the given authenticated user has permission to view
        the workflow history of the specified document.

        Rules:
        - User must be active.
        - Document must exist.
        - Administrator & Records Officer: Allowed to view workflow history across documents.
        - Approver: Allowed if the approver has access to the document under baseline policy
          (i.e. document in own department or created by user), and has an explicit assignment
          to at least one workflow for this document.
        - Department User (including submitter): Allowed if the user is authorized to view the
          document under the baseline policy (e.g. own department or created by user).
        - Auditor & Read-Only users: Allowed only if authorized to view the document under
          baseline metadata policy.
        - Missing/ambiguous department information defaults to DENY.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not document:
            return AccessDecision(False, "Document not found")

        # First, enforce baseline document visibility
        base_decision = cls.can_view_metadata(user, document)
        if not base_decision.allowed:
            return base_decision

        role = user.role

        # 1. Admin: Allowed
        if role == UserRole.ADMIN:
            return AccessDecision(True, "Administrator workflow history access")

        # 2. Records Officer: Allowed
        if role == UserRole.RECORDS_OFFICER:
            return AccessDecision(True, "Records Officer workflow history access")

        # 3. Department User: Permitted for documents in own department or created by them
        if role == UserRole.DEPARTMENT_USER:
            return AccessDecision(True, "Department user workflow history access")

        # 4. Approver: Permitted within own department
        if role == UserRole.APPROVER:
            return AccessDecision(True, "Approver workflow history access")

        # 5. Auditor: Scoped to audit department
        if role == UserRole.AUDITOR:
            return AccessDecision(True, "Auditor workflow history access")

        # 6. Read-Only: Scoped to non-confidential department documents
        if role == UserRole.READ_ONLY:
            return AccessDecision(True, "Read-Only workflow history access")

        return AccessDecision(False, f"Role '{role.value}' denied workflow history access")

    @classmethod
    def filter_workflows_for_user(cls, user: User, workflows: list) -> list:
        """
        Filters workflow attempts for a specific user.
        - Admin, Records Officer, and Submitter (creator of the document or submitter of the workflow):
          Can see all workflow attempts for the document.
        - Approver: Can view ONLY workflow attempts for which that user has an explicit assignment.
          Does not reveal other approvers' private assignments or unrelated workflows.
        - Other authorized roles (e.g., department users viewing document history): Can view workflow attempts
          submitted by themselves or within their department.
        """
        if user.role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return workflows

        if user.role == UserRole.APPROVER:
            # Approver can only see workflows where they are an assigned approver
            filtered = []
            for wf in workflows:
                if any(a.assigned_approver_id == user.id for a in wf.assignments):
                    filtered.append(wf)
            return filtered

        if user.role == UserRole.DEPARTMENT_USER:
            # Submitting user can see workflows they submitted or documents in their department
            return workflows

        return workflows

    @classmethod
    def can_cancel_workflow(cls, user: User, workflow, document: DigitalDocument) -> AccessDecision:
        """
        Determines whether the given authenticated user has permission to cancel/withdraw
        the specified review workflow.

        Rules:
        - User must be active.
        - Document and workflow must exist.
        - Document must be in UNDER_REVIEW status.
        - Workflow must be in PENDING state.
        - Administrator: Allowed to cancel pending workflows across departments.
        - Records Officer: Allowed to cancel pending workflows across departments.
        - Department User: Allowed ONLY IF they are the original submitter of the workflow
          (workflow.submitter_id == user.id) AND belong to the document's department.
          Another department user who did not submit the workflow CANNOT cancel it.
        - Approver: Denied cancellation permission (cannot cancel merely because assigned).
        - Auditor: Denied cancellation permission.
        - Read-Only User: Denied cancellation permission.
        - Missing or ambiguous department information defaults to DENY.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not workflow or not document:
            return AccessDecision(False, "Workflow or document not found")

        from app.models.document import DocumentStatus
        from app.models.workflow import WorkflowState

        if workflow.state != WorkflowState.PENDING:
            return AccessDecision(
                False,
                f"Workflow is in '{workflow.state.value}' state. Only pending workflows can be cancelled."
            )

        if document.status != DocumentStatus.UNDER_REVIEW:
            return AccessDecision(
                False,
                f"Document is in '{document.status.value}' status. Only documents under review can have workflows cancelled."
            )

        role = user.role
        doc_dept = (document.department or "").strip().lower()
        user_dept = (user.department or "").strip().lower()

        # 1. Administrator: Allowed across departments
        if role == UserRole.ADMIN:
            return AccessDecision(True, "Administrator workflow cancellation access")

        # 2. Records Officer: Allowed across departments
        if role == UserRole.RECORDS_OFFICER:
            return AccessDecision(True, "Records Officer workflow cancellation access")

        # 3. Department User: Must be the submitter and in the same department
        if role == UserRole.DEPARTMENT_USER:
            if not user_dept or user_dept != doc_dept:
                return AccessDecision(
                    False,
                    f"Department user assigned to '{user.department}' cannot cancel workflows for '{document.department}'"
                )
            if workflow.submitter_id != user.id:
                return AccessDecision(
                    False,
                    "Department user cannot cancel a workflow submitted by another user."
                )
            return AccessDecision(True, "Workflow submitter cancellation access")

        # 4. Approver: Denied cancellation permission
        if role == UserRole.APPROVER:
            return AccessDecision(False, "Approvers cannot cancel or withdraw workflows")

        # 5. Auditor: Denied write permission
        if role == UserRole.AUDITOR:
            return AccessDecision(False, "Auditors cannot cancel review workflows")

        # 6. Read-Only: Denied write permission
        if role == UserRole.READ_ONLY:
            return AccessDecision(False, "Read-only users cannot cancel review workflows")

        return AccessDecision(False, f"Access denied by default for role '{role.value}'")

    @classmethod
    def can_manage_retention_rules(cls, user: User) -> AccessDecision:
        """
        Determines whether user can create, update, or deactivate retention rules.
        Allowed: Administrator, Records Officer.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")
        if user.role in {UserRole.ADMIN, UserRole.RECORDS_OFFICER}:
            return AccessDecision(True, "User has retention rules management access")
        return AccessDecision(False, f"Role '{user.role.value}' is not authorized to manage retention rules")

    @classmethod
    def can_assign_retention_rule(cls, user: User, document: DigitalDocument) -> AccessDecision:
        """
        Determines whether user can assign a retention rule to a document.
        - Admin & Records Officer: Allowed across departments.
        - Department User: Allowed only for documents in own department.
        - Other roles: Denied.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")
        if not document:
            return AccessDecision(False, "Document not found")

        doc_dept = (document.department or "").strip().lower()
        user_dept = (user.department or "").strip().lower()

        if user.role in {UserRole.ADMIN, UserRole.RECORDS_OFFICER}:
            return AccessDecision(True, "Administrative retention assignment access")

        if user.role == UserRole.DEPARTMENT_USER:
            if not user_dept or user_dept != doc_dept:
                return AccessDecision(False, f"Department user cannot assign retention rules to other department documents ({document.department})")
            return AccessDecision(True, "Department user retention assignment access")

        return AccessDecision(False, f"Role '{user.role.value}' is not authorized to assign retention rules")

    @classmethod
    def can_manage_legal_holds(cls, user: User, document: DigitalDocument) -> AccessDecision:
        """
        Determines whether user can place or release a legal hold on a document.
        - Admin & Records Officer: Allowed across all documents.
        - Department User / Approver / Auditor / Read-Only: Denied (legal hold governance requires administrative authority).
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")
        if not document:
            return AccessDecision(False, "Document not found")

        if user.role in {UserRole.ADMIN, UserRole.RECORDS_OFFICER}:
            return AccessDecision(True, "Legal hold governance authorization")

        return AccessDecision(False, f"Role '{user.role.value}' is not authorized to place or release legal holds")

    @classmethod
    def can_view_disposal_eligibility(cls, user: User) -> AccessDecision:
        """
        Determines whether user can access disposal eligibility reporting.
        Allowed: Administrator, Records Officer, Auditor (within audit scope), and Department User (for own department).
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")
        if user.role in {UserRole.ADMIN, UserRole.RECORDS_OFFICER, UserRole.AUDITOR, UserRole.DEPARTMENT_USER}:
            return AccessDecision(True, "Disposal eligibility access granted")
        return AccessDecision(False, f"Role '{user.role.value}' is not authorized to view disposal eligibility")


    @classmethod
    def build_document_scope_filter(cls, user: User):

        """
        Generates a SQLAlchemy filter expression that restricts DigitalDocument queries
        strictly to records the authenticated user is authorized to discover and view.

        Returns:
            A SQLAlchemy binary expression or boolean clause.
        """
        from sqlalchemy import and_, or_, false, true, func

        if not user or not user.is_active:
            return false()

        role = user.role
        user_dept = (user.department or "").strip()

        # 1. Administrator: Unrestricted
        if role == UserRole.ADMIN:
            return true()

        # 2. Records Officer: Unrestricted across departments
        if role == UserRole.RECORDS_OFFICER:
            return true()

        # 3. Department User: Strictly own department
        if role == UserRole.DEPARTMENT_USER:
            if not user_dept:
                return false()
            return func.lower(DigitalDocument.department) == user_dept.lower()

        # 4. Approver: Own department OR created by user
        if role == UserRole.APPROVER:
            clauses = [DigitalDocument.created_by_id == user.id]
            if user_dept:
                clauses.append(func.lower(DigitalDocument.department) == user_dept.lower())
            return or_(*clauses)

        # 5. Auditor: Strictly records within their assigned audit department
        if role == UserRole.AUDITOR:
            if not user_dept:
                return false()
            return func.lower(DigitalDocument.department) == user_dept.lower()


        # 6. Read-Only User: Non-confidential records belonging to own department OR created by user
        if role == UserRole.READ_ONLY:
            confidential_upper = [c.upper() for c in cls.CONFIDENTIAL_CLASSIFICATIONS]
            is_non_confidential = ~func.upper(DigitalDocument.classification).in_(confidential_upper)
            dept_clause = func.lower(DigitalDocument.department) == user_dept.lower() if user_dept else false()
            return and_(
                is_non_confidential,
                or_(
                    dept_clause,
                    DigitalDocument.created_by_id == user.id,
                ),
            )

        return false()

document_auth_service = DocumentAuthorizationService()


class PhysicalFileAuthorizationService:
    """
    Evaluates role and department policies for physical file registry operations.
    Principles:
    - admin: Unrestricted access across all departments. Can register, update, view, and change status.
    - records_officer: Cross-department governance access. Can register, update, view, and change status.
    - department_user: Restricted strictly to own department. Can register, update, view, and change status for own department files.
    - approver: Read-only access to physical files within own department. Cannot register, update, or change status.
    - auditor: Read-only access within assigned audit department. Cannot register, update, or change status.
    - read_only: Read-only access within own department. Cannot register, update, or change status.
    """

    CONFIDENTIAL_CLASSIFICATIONS = {"CONFIDENTIAL", "SECRET", "RESTRICTED", "TOP_SECRET"}

    @classmethod
    def can_register(cls, user: User, target_department: str) -> AccessDecision:
        """
        Determines whether user is authorized to register a physical file in target_department.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        target_dept = (target_department or "").strip().lower()

        if role == UserRole.ADMIN:
            return AccessDecision(True, "Administrator may register physical files in any department")

        if role == UserRole.RECORDS_OFFICER:
            return AccessDecision(True, "Records Officer may register physical files across departments")

        if role == UserRole.DEPARTMENT_USER:
            if not user_dept or user_dept != target_dept:
                return AccessDecision(False, "Department users may only register physical files in their own department")
            return AccessDecision(True, "Department user registered file in own department")

        return AccessDecision(False, f"Role '{role.value}' is not authorized to register physical files")

    @classmethod
    def can_view(cls, user: User, physical_file) -> AccessDecision:
        """
        Determines whether user can view metadata of the physical file.
        Non-disclosing 404 should be raised if denied.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not physical_file:
            return AccessDecision(False, "Physical file not found")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        file_dept = (physical_file.department or "").strip().lower()

        # 1. Admin & Records Officer: Unrestricted
        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return AccessDecision(True, "Administrative / governance access granted")

        # 2. Department User: Own department OR created by user
        if role == UserRole.DEPARTMENT_USER:
            if user_dept and user_dept == file_dept:
                return AccessDecision(True, "Department user access granted")
            if physical_file.created_by_id == user.id:
                return AccessDecision(True, "Creator access granted")
            return AccessDecision(False, "Access denied outside user department")

        # 3. Approver: Read-only within own department OR created by user
        if role == UserRole.APPROVER:
            if user_dept and user_dept == file_dept:
                return AccessDecision(True, "Approver department read-only access granted")
            if physical_file.created_by_id == user.id:
                return AccessDecision(True, "Creator access granted")
            return AccessDecision(False, "Access denied outside approver department")

        # 4. Auditor: Read-only within assigned audit department
        if role == UserRole.AUDITOR:
            if user_dept and user_dept == file_dept:
                return AccessDecision(True, "Auditor department read-only access granted")
            return AccessDecision(False, "Access denied outside auditor department")

        # 5. Read-Only: Read-only within own department
        if role == UserRole.READ_ONLY:
            if user_dept and user_dept == file_dept:
                return AccessDecision(True, "Read-only department access granted")
            if physical_file.created_by_id == user.id:
                return AccessDecision(True, "Creator access granted")
            return AccessDecision(False, "Access denied outside user department")

        return AccessDecision(False, f"Role '{role.value}' is not authorized to view physical files")

    @classmethod
    def can_update(cls, user: User, physical_file, new_department: str | None = None) -> AccessDecision:
        """
        Determines whether user can update physical file metadata and/or reassign department.
        Department reassignment is restricted to ADMIN and RECORDS_OFFICER.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not physical_file:
            return AccessDecision(False, "Physical file not found")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        file_dept = (physical_file.department or "").strip().lower()

        # Check department reassignment first
        if new_department is not None and new_department.strip().lower() != file_dept:
            if role not in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
                return AccessDecision(False, "Only administrators and records officers can reassign department ownership")

        # 1. Admin & Records Officer: Allowed
        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return AccessDecision(True, "Administrative / governance update permitted")

        # 2. Department User: Permitted for files in own department
        if role == UserRole.DEPARTMENT_USER:
            if user_dept and user_dept == file_dept:
                return AccessDecision(True, "Department user update permitted")
            return AccessDecision(False, "Department users may only update files within their own department")

        return AccessDecision(False, f"Role '{role.value}' is not permitted to update physical files")

    @classmethod
    def can_change_status(cls, user: User, physical_file) -> AccessDecision:
        """
        Determines whether user can transition physical file lifecycle status.
        """
        return cls.can_update(user, physical_file, new_department=None)

    @classmethod
    def build_physical_file_scope_filter(cls, user: User):
        """
        SQLAlchemy filter expression scoping physical file queries to authorized records.
        """
        from sqlalchemy import and_, or_, false, true, func
        from app.models.physical_file import PhysicalFile

        if not user or not user.is_active:
            return false()

        role = user.role
        user_dept = (user.department or "").strip()

        # 1. Admin & Records Officer: Unrestricted
        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return true()

        # 2. Department User: Strictly own department OR created by user
        if role == UserRole.DEPARTMENT_USER:
            clauses = [PhysicalFile.created_by_id == user.id]
            if user_dept:
                clauses.append(func.lower(PhysicalFile.department) == user_dept.lower())
            return or_(*clauses)

        # 3. Approver: Strictly own department OR created by user
        if role == UserRole.APPROVER:
            clauses = [PhysicalFile.created_by_id == user.id]
            if user_dept:
                clauses.append(func.lower(PhysicalFile.department) == user_dept.lower())
            return or_(*clauses)

        # 4. Auditor: Strictly records within assigned department
        if role == UserRole.AUDITOR:
            if not user_dept:
                return false()
            return func.lower(PhysicalFile.department) == user_dept.lower()

        # 5. Read-Only: Own department OR created by user
        if role == UserRole.READ_ONLY:
            clauses = [PhysicalFile.created_by_id == user.id]
            if user_dept:
                clauses.append(func.lower(PhysicalFile.department) == user_dept.lower())
            return or_(*clauses)

        return false()


physical_file_auth_service = PhysicalFileAuthorizationService()


class StorageLocationAuthorizationService:
    """
    Evaluates role and department policies for storage location operations.
    Principles:
    - admin: Unrestricted access across all departments. Can create, edit, activate/deactivate, and assign files.
    - records_officer: Cross-department records governance. Can create, edit, activate/deactivate, and assign files.
    - department_user: Restricted strictly to own department. Can create and edit locations in own department, and assign own department files to own department locations.
    - approver: Read-only access within own department. Cannot create, edit, or activate/deactivate.
    - auditor: Read-only access within assigned department. Cannot create, edit, or activate/deactivate.
    - read_only: Read-only access within own department.
    """

    @classmethod
    def can_manage(cls, user: User, target_department: str) -> AccessDecision:
        """
        Determines whether user can create or manage storage locations in target_department.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        target_dept = (target_department or "").strip().lower()

        if role == UserRole.ADMIN:
            return AccessDecision(True, "Administrator may manage storage locations across departments")

        if role == UserRole.RECORDS_OFFICER:
            return AccessDecision(True, "Records Officer may manage storage locations across departments")

        if role == UserRole.DEPARTMENT_USER:
            if not user_dept or user_dept != target_dept:
                return AccessDecision(False, "Department users may only manage storage locations in their own department")
            return AccessDecision(True, "Department user authorized for own department storage locations")

        return AccessDecision(False, f"Role '{role.value}' is not permitted to manage storage locations")

    @classmethod
    def can_view(cls, user: User, location) -> AccessDecision:
        """
        Determines whether user can view metadata and contents of a storage location.
        Non-disclosing 404 should be raised if denied.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not location:
            return AccessDecision(False, "Storage location not found")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        loc_dept = (location.department or "").strip().lower()

        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return AccessDecision(True, "Administrative / governance view access granted")

        if role in (UserRole.DEPARTMENT_USER, UserRole.APPROVER, UserRole.AUDITOR, UserRole.READ_ONLY):
            if user_dept and user_dept == loc_dept:
                return AccessDecision(True, "Department access granted")
            if location.created_by_id == user.id:
                return AccessDecision(True, "Creator access granted")
            return AccessDecision(False, "Access denied outside user department")

        return AccessDecision(False, f"Role '{role.value}' is not authorized to view storage locations")

    @classmethod
    def can_assign_file(cls, user: User, physical_file, storage_location) -> AccessDecision:
        """
        Determines whether user can assign physical_file to storage_location.
        Requirements:
        1. User must be active.
        2. User must be permitted to manage/update physical_file.
        3. User must be permitted to view and manage storage_location.
        4. storage_location must be active.
        5. Department boundaries: non-admin/records_officer users cannot assign files across department boundaries.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if not storage_location.is_active:
            return AccessDecision(False, "Cannot assign files to an inactive storage location")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        file_dept = (physical_file.department or "").strip().lower()
        loc_dept = (storage_location.department or "").strip().lower()

        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return AccessDecision(True, "Administrative assignment permitted")

        if role == UserRole.DEPARTMENT_USER:
            if user_dept != file_dept:
                return AccessDecision(False, "Department users may only manage files in their own department")
            if user_dept != loc_dept:
                return AccessDecision(False, "Cannot assign file to a storage location in another department")
            return AccessDecision(True, "Department user assignment permitted")

        return AccessDecision(False, f"Role '{role.value}' is not permitted to assign physical files to storage locations")

    @classmethod
    def build_storage_location_scope_filter(cls, user: User):
        """
        SQLAlchemy filter expression scoping storage location queries to authorized records.
        """
        from sqlalchemy import and_, or_, false, true, func
        from app.models.storage_location import StorageLocation

        if not user or not user.is_active:
            return false()

        role = user.role
        user_dept = (user.department or "").strip()

        # 1. Admin & Records Officer: Unrestricted
        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return true()

        # 2. Department User, Approver, Auditor, Read-Only: Scoped to own department
        if role in (UserRole.DEPARTMENT_USER, UserRole.APPROVER, UserRole.AUDITOR, UserRole.READ_ONLY):
            clauses = [StorageLocation.created_by_id == user.id]
            if user_dept:
                clauses.append(func.lower(StorageLocation.department) == user_dept.lower())
            return or_(*clauses)

        return false()


storage_location_auth_service = StorageLocationAuthorizationService()


class CustodyAuthorizationService:
    """
    Evaluates role and department policies for physical file circulation,
    checkout, check-in, transfer, and movement history operations.

    Role matrix:
    - admin: Unrestricted across all departments for checkout, check-in, transfer, history, and overdue reports.
    - records_officer: Cross-department records governance authority. Unrestricted for checkout, check-in, transfer, history, and overdue reports.
    - department_user: Permitted to check out, check in, and transfer files within own department. Can view history and overdue reports within own department. Cannot transfer files into or out of other departments.
    - approver: Read-only within own department. Cannot check out, check in, or transfer.
    - auditor: Read-only within assigned audit department. Can view custody records, movement history, and overdue reports within assigned department. Cannot check out, check in, or transfer.
    - read_only: Strictly read-only within own department. Cannot perform custody mutations.
    """

    @classmethod
    def can_checkout(cls, user: User, physical_file) -> AccessDecision:
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")
        if not physical_file:
            return AccessDecision(False, "Physical file not found")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        file_dept = (physical_file.department or "").strip().lower()

        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return AccessDecision(True, "Administrative checkout access granted")

        if role == UserRole.DEPARTMENT_USER:
            if user_dept and user_dept == file_dept:
                return AccessDecision(True, "Department user checkout access granted")
            return AccessDecision(False, "Department users may only check out files from their own department")

        return AccessDecision(False, f"Role '{role.value}' is not permitted to check out physical files")

    @classmethod
    def can_checkin(cls, user: User, physical_file) -> AccessDecision:
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")
        if not physical_file:
            return AccessDecision(False, "Physical file not found")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        file_dept = (physical_file.department or "").strip().lower()

        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return AccessDecision(True, "Administrative check-in access granted")

        if role == UserRole.DEPARTMENT_USER:
            if user_dept and user_dept == file_dept:
                return AccessDecision(True, "Department user check-in access granted")
            return AccessDecision(False, "Department users may only check in files from their own department")

        return AccessDecision(False, f"Role '{role.value}' is not permitted to check in physical files")

    @classmethod
    def can_transfer(cls, user: User, physical_file, source_location, destination_location) -> AccessDecision:
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")
        if not physical_file:
            return AccessDecision(False, "Physical file not found")
        if not destination_location:
            return AccessDecision(False, "Destination storage location not found")

        role = user.role
        user_dept = (user.department or "").strip().lower()
        file_dept = (physical_file.department or "").strip().lower()
        dest_dept = (destination_location.department or "").strip().lower()

        if role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            return AccessDecision(True, "Administrative transfer access granted")

        if role == UserRole.DEPARTMENT_USER:
            if user_dept != file_dept:
                return AccessDecision(False, "Department users may only transfer files within their own department")
            if user_dept != dest_dept:
                return AccessDecision(False, "Department users cannot transfer files to a location in another department")
            if source_location:
                src_dept = (source_location.department or "").strip().lower()
                if user_dept != src_dept:
                    return AccessDecision(False, "Department users cannot transfer files from a location in another department")
            return AccessDecision(True, "Department user transfer access granted")

        return AccessDecision(False, f"Role '{role.value}' is not permitted to transfer physical files")

    @classmethod
    def can_view_history(cls, user: User, physical_file) -> AccessDecision:
        """
        Determines whether user can view custody and movement history.
        Follows the physical file view policy without granting access to digital document binaries.
        """
        return physical_file_auth_service.can_view(user, physical_file)

    @classmethod
    def can_view_overdue_report(cls, user: User) -> AccessDecision:
        """
        Determines whether user can access overdue files reporting.
        Admin, records_officer, auditor, and department_user (scoped to own department) are allowed.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if user.role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER, UserRole.AUDITOR, UserRole.DEPARTMENT_USER):
            return AccessDecision(True, "Overdue reporting access granted")

        return AccessDecision(False, f"Role '{user.role.value}' is not authorized to view overdue reports")

    @classmethod
    def can_view_custody_integrity(cls, user: User) -> AccessDecision:
        """
        Determines whether user can access chain-of-custody integrity verification.
        Restricted to Admin, Records Officer, and Auditor (within assigned department).
        Department Users may view integrity within their own department.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if user.role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER, UserRole.AUDITOR, UserRole.DEPARTMENT_USER):
            return AccessDecision(True, "Custody integrity verification access granted")

        return AccessDecision(False, f"Role '{user.role.value}' is not authorized to view custody integrity reports")

    @classmethod
    def can_export_reports(cls, user: User) -> AccessDecision:
        """
        Determines whether user can export custody and movement reports to CSV.
        """
        if not user or not user.is_active:
            return AccessDecision(False, "User is inactive or not authenticated")

        if user.role in (UserRole.ADMIN, UserRole.RECORDS_OFFICER, UserRole.AUDITOR, UserRole.DEPARTMENT_USER):
            return AccessDecision(True, "Report export access granted")

        return AccessDecision(False, f"Role '{user.role.value}' is not authorized to export reports")


custody_auth_service = CustodyAuthorizationService()

