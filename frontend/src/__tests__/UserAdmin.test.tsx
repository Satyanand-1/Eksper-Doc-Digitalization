import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AdminUsersPage from "@/app/admin/users/page";
import { AuthProvider } from "@/context/AuthContext";
import { PaginatedUsersResponse, AdminUser } from "@/types/user";
import { api, ApiError } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getUsers: jest.fn(),
      createUser: jest.fn(),
      updateUser: jest.fn(),
      updateUserStatus: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

const mockAdminUser = {
  id: "admin-123",
  email: "admin@example.com",
  full_name: "Super Admin",
  department: "System Administration",
  role: "admin",
  is_active: true,
};

const mockNonAdminUser = {
  id: "user-456",
  email: "user@example.com",
  full_name: "Regular User",
  department: "Finance",
  role: "department_user",
  is_active: true,
};

const mockUsersList: AdminUser[] = [
  {
    id: "admin-123",
    email: "admin@example.com",
    full_name: "Super Admin",
    department: "System Administration",
    role: "admin",
    is_active: true,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
  },
  {
    id: "user-456",
    email: "user@example.com",
    full_name: "Regular User",
    department: "Finance",
    role: "department_user",
    is_active: true,
    created_at: "2026-10-02T10:00:00Z",
    updated_at: "2026-10-02T10:00:00Z",
  },
  {
    id: "appr-789",
    email: "appr@example.com",
    full_name: "Alice Approver",
    department: "Operations",
    role: "approver",
    is_active: false,
    created_at: "2026-10-03T10:00:00Z",
    updated_at: "2026-10-03T10:00:00Z",
  },
];

const mockPaginatedResponse: PaginatedUsersResponse = {
  items: mockUsersList,
  page: 1,
  page_size: 10,
  total: 3,
  total_pages: 1,
};

describe("Task 5.10: User Administration Frontend Interface", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("1. Non-admin users see access denied view and cannot access directory", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockNonAdminUser);

    render(
      <AuthProvider>
        <AdminUsersPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Administrator Access Required")).toBeInTheDocument();
    });
    expect(screen.queryByText("User Administration")).not.toBeInTheDocument();
    expect(api.getUsers).not.toHaveBeenCalled();
  });

  test("2. Admin can access user management page and view user directory", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getUsers as jest.Mock).mockResolvedValue(mockPaginatedResponse);

    render(
      <AuthProvider>
        <AdminUsersPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("User Administration")).toBeInTheDocument();
      expect(screen.getByText("Super Admin")).toBeInTheDocument();
      expect(screen.getByText("Regular User")).toBeInTheDocument();
      expect(screen.getByText("Alice Approver")).toBeInTheDocument();
    });

    expect(api.getUsers).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
      search: undefined,
      role: undefined,
      department: undefined,
      is_active: undefined,
    });
  });

  test("3. Search input and filters trigger directory queries", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getUsers as jest.Mock).mockResolvedValue(mockPaginatedResponse);

    render(
      <AuthProvider>
        <AdminUsersPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Search name or email...")).toBeInTheDocument();
    });

    // Enter search term and submit form
    const searchInput = screen.getByPlaceholderText("Search name or email...");
    fireEvent.change(searchInput, { target: { value: "Alice" } });
    const searchButton = screen.getByRole("button", { name: "Search" });
    fireEvent.click(searchButton);

    await waitFor(() => {
      expect(api.getUsers).toHaveBeenCalledWith(
        expect.objectContaining({
          search: "Alice",
        })
      );
    });

    // Filter by role
    const roleSelect = screen.getByDisplayValue("All Roles");
    fireEvent.change(roleSelect, { target: { value: "approver" } });

    await waitFor(() => {
      expect(api.getUsers).toHaveBeenCalledWith(
        expect.objectContaining({
          role: "approver",
        })
      );
    });
  });

  test("4. Create user form validates required department and submits correctly", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getUsers as jest.Mock).mockResolvedValue(mockPaginatedResponse);
    (api.createUser as jest.Mock).mockResolvedValue({
      id: "new-user-1",
      email: "new.user@example.com",
      full_name: "New User",
      role: "department_user",
      department: "Legal",
      is_active: true,
      created_at: "2026-10-10T12:00:00Z",
      updated_at: "2026-10-10T12:00:00Z",
    });

    render(
      <AuthProvider>
        <AdminUsersPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Add User")).toBeInTheDocument();
    });

    // Open create user modal
    fireEvent.click(screen.getByText("Add User"));
    expect(screen.getByText("Create New User Account")).toBeInTheDocument();

    // Fill in form with missing department for department_user
    fireEvent.change(screen.getByPlaceholderText("e.g. Jane Doe"), { target: { value: "New User" } });
    fireEvent.change(screen.getByPlaceholderText("e.g. jane.doe@example.com"), { target: { value: "new.user@example.com" } });
    fireEvent.change(screen.getByPlaceholderText("Minimum 8 characters"), { target: { value: "Password123!" } });

    // Click submit without department -> should show validation error
    fireEvent.click(screen.getByText("Create Account"));
    expect(screen.getByText("Department is required for role 'Department User'.")).toBeInTheDocument();

    // Fill in department and submit
    fireEvent.change(screen.getByPlaceholderText("e.g. Legal, Finance, Operations"), { target: { value: "Legal" } });
    fireEvent.click(screen.getByText("Create Account"));

    await waitFor(() => {
      expect(api.createUser).toHaveBeenCalledWith({
        full_name: "New User",
        email: "new.user@example.com",
        role: "department_user",
        department: "Legal",
        password: "Password123!",
      });
    });
  });

  test("5. Edit user profile modal updates full name and role", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getUsers as jest.Mock).mockResolvedValue(mockPaginatedResponse);
    (api.updateUser as jest.Mock).mockResolvedValue({
      ...mockUsersList[1],
      full_name: "Updated Regular User",
      role: "records_officer",
    });

    render(
      <AuthProvider>
        <AdminUsersPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getAllByTitle("Edit User Profile").length).toBeGreaterThan(0);
    });

    // Click edit for second user (Regular User)
    const editButtons = screen.getAllByTitle("Edit User Profile");
    fireEvent.click(editButtons[1]);

    expect(screen.getByText("Edit User Profile")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Regular User")).toBeInTheDocument();

    // Update full name
    const nameInput = screen.getByDisplayValue("Regular User");
    fireEvent.change(nameInput, { target: { value: "Updated Regular User" } });

    // Submit edit
    fireEvent.click(screen.getByText("Save Changes"));

    await waitFor(() => {
      expect(api.updateUser).toHaveBeenCalledWith("user-456", {
        full_name: "Updated Regular User",
        department: "Finance",
        role: "department_user",
      });
    });
  });

  test("6. User activation / deactivation requires confirmation modal", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getUsers as jest.Mock).mockResolvedValue(mockPaginatedResponse);
    (api.updateUserStatus as jest.Mock).mockResolvedValue({
      ...mockUsersList[1],
      is_active: false,
    });

    render(
      <AuthProvider>
        <AdminUsersPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getAllByTitle("Deactivate User").length).toBeGreaterThan(0);
    });

    // Click Deactivate for user
    const deactButtons = screen.getAllByTitle("Deactivate User");
    fireEvent.click(deactButtons[0]);

    // Confirmation modal should open
    expect(screen.getByText("Deactivate User Account?")).toBeInTheDocument();

    // Click Yes, Deactivate
    fireEvent.click(screen.getByText("Yes, Deactivate"));

    await waitFor(() => {
      expect(api.updateUserStatus).toHaveBeenCalledWith("admin-123", {
        is_active: false,
      });
    });
  });

  test("7. API error in status toggle displays user-friendly message", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getUsers as jest.Mock).mockResolvedValue(mockPaginatedResponse);
    (api.updateUserStatus as jest.Mock).mockRejectedValue(
      new Error("Cannot deactivate the last active administrator.")
    );

    render(
      <AuthProvider>
        <AdminUsersPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getAllByTitle("Deactivate User").length).toBeGreaterThan(0);
    });

    // Click Deactivate
    const deactButtons = screen.getAllByTitle("Deactivate User");
    fireEvent.click(deactButtons[0]);

    // Click Yes, Deactivate
    fireEvent.click(screen.getByText("Yes, Deactivate"));

    await waitFor(() => {
      expect(screen.getByText("Cannot deactivate the last active administrator.")).toBeInTheDocument();
    });
  });
});
