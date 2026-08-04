from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/captcha-refresh/", views.refresh_login_captcha, name="refresh_login_captcha"),
    path("logout/", views.logout_view, name="logout"),

    path("", views.dashboard, name="dashboard"),
    path("create-ticket/", views.create_ticket, name="create_ticket"),

    path("ticket/<int:ticket_id>/", views.ticket_detail, name="ticket_detail"),
    path("ticket/<int:ticket_id>/status-json/", views.ticket_status_json, name="ticket_status_json"),
    path("update-ticket/<int:ticket_id>/", views.update_ticket_admin, name="update_status"),
    path("rate-ticket/<int:ticket_id>/", views.rate_ticket, name="rate_ticket"),

    # ADMIN
    path("admin-portal/", views.admin_portal, name="admin_portal"),
    path("admin-users/", views.admin_users, name="admin_users"),
    path("admin-companies/", views.admin_companies, name="admin_companies"),
    path("admin-support/", views.admin_support, name="admin_support"),
    path("admin-tickets/", views.admin_tickets, name="admin_tickets"),
    path("admin-backup/", views.admin_backup, name="admin_backup"),
    path("admin-tickets/export/", views.export_tickets_csv, name="export_tickets_csv"),
    path("admin-tickets/import/", views.import_tickets_csv, name="import_tickets_csv"),
    path("admin-backup/export/", views.export_full_backup, name="export_full_backup"),
    path("admin-backup/import/", views.import_full_backup, name="import_full_backup"),
    path("admin/categories/", views.admin_categories, name="admin_categories"),
    path("admin-notifications/", views.admin_notifications, name="admin_notifications"),
    path("admin-roles/", views.admin_roles, name="admin_roles"),
    path("admin-roles/create/", views.create_role, name="create_role"),
    path("admin-roles/<int:role_id>/edit/", views.edit_role, name="edit_role"),
    path("admin-roles/<int:role_id>/delete/", views.delete_role, name="delete_role"),
    path("ticket/<int:ticket_id>/assign/", views.assign_ticket, name="assign_ticket"),
    path("admin-sla/", views.admin_sla, name="admin_sla"),

    path("notif/read/<int:notif_id>/", views.notification_read, name="notification_read"),

    path("inbox/", views.inbox, name="inbox"),
    path("ticket/<int:ticket_id>/take/", views.take_ticket, name="take_ticket"),
    path("admin/users/reset/<int:user_id>/", views.reset_user_password, name="reset_user_password"),
    path("ticket/<int:ticket_id>/close/", views.close_ticket, name="close_ticket"),
    path(
        "get-subcategories/<int:category_id>/",
        views.get_subcategories,
        name="get_subcategories"
    ),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("change-password/", views.change_password, name="change_password"),
    path("reset-password/<uidb64>/<token>/", views.reset_password, name="reset_password"),
    path(
        "attachment/<int:attachment_id>/",
        views.view_attachment,
        name="view_attachment"
    )
]