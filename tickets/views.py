# IMPORTS
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import IntegrityError
from django.db.models import Q
from datetime import timedelta
from collections import defaultdict
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
import random
import string
from django.http import HttpResponse
import html
import os
import re
import textwrap
import csv
import io
import json
import zipfile
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from .email_service import send_graph_email
from django.utils.http import urlsafe_base64_decode
from django.http import FileResponse, Http404
from django.utils.dateparse import parse_datetime
from django.db import transaction
from django.core import serializers

def forgot_password(request):

    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if request.method != "POST":
        return redirect("login")

    username = (request.POST.get("username") or "").strip()

    if not username:
        msg = "Ingresa tu usuario"

        if is_ajax:
            return JsonResponse({"ok": False, "message": msg}, status=400)

        messages.error(request, msg)
        return redirect("login")

    try:
        user = User.objects.get(username=username)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        reset_url = request.build_absolute_uri(
            reverse("reset_password", kwargs={
                "uidb64": uid,
                "token": token
            })
        )

        _notify(
            user,
            "Restablecimiento de contraseña",
            "Haz clic en el siguiente enlace para restablecer tu contraseña",
            url=reset_url,
            send_email=True
        )

        msg = "Se envió un enlace a tu correo"

        if is_ajax:
            return JsonResponse({"ok": True, "message": msg})

        messages.success(request, msg)

    except User.DoesNotExist:
        msg = "Usuario no encontrado"

        if is_ajax:
            return JsonResponse({"ok": False, "message": msg}, status=404)

        messages.error(request, msg)

    return redirect("login")



def test_email(request):
    return HttpResponse("OK")

def reset_password(request, uidb64, token):

    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):

        if request.method == "POST":
            password = request.POST.get("password")
            confirm = request.POST.get("confirm")

            if password != confirm:
                messages.error(request, "Las contraseñas no coinciden")
                return render(request, "reset_password.html")

            if len(password) < 8:
                messages.error(request, "Debe tener al menos 8 caracteres")
                return render(request, "reset_password.html")

            if not any(c.isupper() for c in password):
                messages.error(request, "Debe tener una mayúscula")
                return render(request, "reset_password.html")

            if not any(c.isdigit() for c in password):
                messages.error(request, "Debe tener un número")
                return render(request, "reset_password.html")

            user.set_password(password)
            user.save()

            user.profile.must_change_password = False
            user.profile.save()

            _notify(
                user,
                "Contraseña restablecida",
                f"""
                Hola {user.first_name or user.username},

                Tu contraseña ha sido restablecida correctamente.

                Si no reconoces esta acción, contacta al soporte.
                """,
                url=request.build_absolute_uri(reverse("login")),
                send_email=True
            )

            messages.success(request, "Contraseña actualizada correctamente")
            return redirect("login")
        
        return render(
            request,
            "reset_password.html"
        )
        
    messages.error(
       request,
       "El enlace ya no es válido."
    )   

    return redirect("login")

from .models import (
    Ticket, Company, Profile, TicketMessage,
    TicketHistory, Notification, TicketAttachment,
    Role, Permission, SLA, Category, SubCategory, Brand
)

from .forms import (
    LoginForm, TicketForm, UpdateTicketForm, RateTicketForm,
    CompanyForm, AdminUserCreateForm, AdminUserRoleForm, MessageForm
)

from django import forms

# =========================
# HELPERS
# =========================

def _role(user):
    if not user:
        return "CLIENTE"

    try:
        if hasattr(user, "profile") and user.profile.role:
            return user.profile.role.name
        return "CLIENTE"
    except AttributeError:
        return "CLIENTE"


def _is_admin(user):
    return _role(user) == "ADMINISTRADOR"


def _is_support(user):
    return _role(user) == "SOPORTE"


def _gen_code():
    last = Ticket.objects.order_by("-id").first()
    n = (last.id + 1) if last else 1
    return f"IN-{n:04d}"


def _generate_captcha():
    icon_bank = [
        {"key": "candado", "label": "Candado", "emoji": "🔒"},
        {"key": "llave", "label": "Llave", "emoji": "🔑"},
        {"key": "escudo", "label": "Escudo", "emoji": "🛡️"},
        {"key": "fuego", "label": "Fuego", "emoji": "🔥"},
        {"key": "rayo", "label": "Rayo", "emoji": "⚡"},
        {"key": "nube", "label": "Nube", "emoji": "☁️"},
        {"key": "estrella", "label": "Estrella", "emoji": "⭐"},
        {"key": "cohete", "label": "Cohete", "emoji": "🚀"},
        {"key": "engranaje", "label": "Engranaje", "emoji": "⚙️"},
        {"key": "campana", "label": "Campana", "emoji": "🔔"},
        {"key": "luna", "label": "Luna", "emoji": "🌙"},
        {"key": "sol", "label": "Sol", "emoji": "☀️"},
    ]

    options = random.sample(icon_bank, 6)
    target = random.choice(options)

    return {
        "question": f"Selecciona el ícono: {target['label']}",
        "answer": target["key"],
        "options": options,
    }


CAPTCHA_TTL_SECONDS = 600


def _set_login_captcha(request):
    captcha = _generate_captcha()
    request.session["login_captcha_question"] = captcha["question"]
    request.session["login_captcha_answer"] = captcha["answer"]
    request.session["login_captcha_options"] = captcha["options"]
    request.session["login_captcha_created_at"] = timezone.now().timestamp()


def _is_captcha_expired(request):
    created_at = request.session.get("login_captcha_created_at")
    if not created_at:
        return True

    try:
        age = timezone.now().timestamp() - float(created_at)
        return age > CAPTCHA_TTL_SECONDS
    except (TypeError, ValueError):
        return True

BUSINESS_START_HOUR = 8
BUSINESS_END_HOUR = 18


def _is_business_day(dt):
    return dt.weekday() < 5


def _business_day_start(dt):
    return dt.replace(
        hour=BUSINESS_START_HOUR,
        minute=0,
        second=0,
        microsecond=0
    )


def _business_day_end(dt):
    return dt.replace(
        hour=BUSINESS_END_HOUR,
        minute=0,
        second=0,
        microsecond=0
    )


def _next_business_start(dt):
    local = timezone.localtime(dt)

    if local.weekday() >= 5:
        days = 7 - local.weekday()
        local = local + timedelta(days=days)
        return _business_day_start(local)

    if local.hour >= BUSINESS_END_HOUR:
        local = local + timedelta(days=1)
        while local.weekday() >= 5:
            local = local + timedelta(days=1)
        return _business_day_start(local)

    if local.hour < BUSINESS_START_HOUR:
        return _business_day_start(local)

    return local


def _add_business_minutes(start, minutes):
    current = timezone.localtime(start)

    if not _is_business_day(current) or current.hour < BUSINESS_START_HOUR or current.hour >= BUSINESS_END_HOUR:
        current = _next_business_start(current)

    while minutes > 0:
        end_of_day = _business_day_end(current)
        available = (end_of_day - current).total_seconds() / 60

        if available >= minutes:
            return current + timedelta(minutes=minutes)

        minutes -= available
        current = _next_business_start(end_of_day + timedelta(seconds=1))

    return current


def _business_minutes_between(start, end):
    start_local = timezone.localtime(start)
    end_local = timezone.localtime(end)

    if end_local <= start_local:
        return 0

    current = start_local
    total_minutes = 0.0

    while current < end_local:
        if not _is_business_day(current):
            current = _next_business_start(current)
            continue

        day_start = _business_day_start(current)
        day_end = _business_day_end(current)

        if current < day_start:
            current = day_start

        if current >= day_end:
            current = _next_business_start(day_end + timedelta(seconds=1))
            continue

        segment_end = min(day_end, end_local)
        total_minutes += (segment_end - current).total_seconds() / 60
        current = segment_end

        if current >= day_end and current < end_local:
            current = _next_business_start(day_end + timedelta(seconds=1))

    return max(0, total_minutes)


def _is_business_hour(dt=None):
    when = timezone.localtime(dt or timezone.now())
    return _is_business_day(when) and BUSINESS_START_HOUR <= when.hour < BUSINESS_END_HOUR


def _pause_sla(ticket, when=None):
    if ticket.sla_paused:
        return

    ticket.sla_paused = True
    ticket.sla_pause_started_at = when or timezone.now()


def _resume_sla(ticket, when=None):
    if not ticket.sla_paused:
        return

    resume_at = when or timezone.now()
    paused_at = ticket.sla_pause_started_at

    if paused_at and resume_at > paused_at:
        paused_delta = resume_at - paused_at

        if ticket.first_response_due_at and not ticket.first_responded_at:
            ticket.first_response_due_at = ticket.first_response_due_at + paused_delta

        if ticket.sla_due_at and ticket.status != "CERRADO":
            ticket.sla_due_at = ticket.sla_due_at + paused_delta

    ticket.sla_paused = False
    ticket.sla_pause_started_at = None


def _fmt_local_dt(dt):
    if not dt:
        return "-"
    return timezone.localtime(dt).strftime("%d/%m/%Y %H:%M")


def _mark_first_response(ticket, user, when=None):
    if ticket.first_responded_at:
        return

    responded_at = when or timezone.now()
    ticket.first_responded_at = responded_at

    _history(
        ticket,
        user,
        "primera_respuesta",
        f"Límite: {_fmt_local_dt(ticket.first_response_due_at)}",
        f"Respondido: {_fmt_local_dt(responded_at)}",
    )


PRIORITY_SEVERITY_MAP = {
    "LOW": "S3",
    "MEDIUM": "S2",
    "HIGH": "S1",
}


def _severity_for_priority(priority):
    return PRIORITY_SEVERITY_MAP.get(priority, "S2")


def _recalculate_open_ticket_deadlines(ticket, sla_obj):
    # Recompute deadlines using latest SLA minutes for open tickets.
    if not sla_obj or ticket.status == "CERRADO":
        return

    if not ticket.first_responded_at:
        first_start = ticket.created_at
        if first_start and not _is_business_hour(first_start):
            first_start = _next_business_start(first_start)
        if first_start:
            ticket.first_response_due_at = _add_business_minutes(
                first_start,
                sla_obj.response_minutes,
            )

    if ticket.resolution_started_at:
        resolution_start = ticket.resolution_started_at
        if resolution_start and not _is_business_hour(resolution_start):
            resolution_start = _next_business_start(resolution_start)
        if resolution_start:
            ticket.sla_due_at = _add_business_minutes(
                resolution_start,
                sla_obj.resolution_minutes,
            )


def _recalculate_running_deadlines(ticket, old_response_minutes, old_resolution_minutes, new_response_minutes, new_resolution_minutes):
    # Keep elapsed business time and only adjust the remaining time to the new SLA.
    now_anchor = ticket.sla_pause_started_at if ticket.sla_paused and ticket.sla_pause_started_at else timezone.now()

    if not ticket.first_responded_at:
        if ticket.first_response_due_at and old_response_minutes is not None:
            remaining_old = _business_minutes_between(now_anchor, ticket.first_response_due_at)
            elapsed = max(0, old_response_minutes - remaining_old)
            remaining_new = max(0, new_response_minutes - elapsed)
            ticket.first_response_due_at = _add_business_minutes(now_anchor, remaining_new)
        else:
            first_start = ticket.created_at
            if first_start and not _is_business_hour(first_start):
                first_start = _next_business_start(first_start)
            if first_start:
                ticket.first_response_due_at = _add_business_minutes(first_start, new_response_minutes)

    if ticket.status != "CERRADO" and ticket.resolution_started_at:
        if ticket.sla_due_at and old_resolution_minutes is not None:
            remaining_old = _business_minutes_between(now_anchor, ticket.sla_due_at)
            elapsed = max(0, old_resolution_minutes - remaining_old)
            remaining_new = max(0, new_resolution_minutes - elapsed)
            ticket.sla_due_at = _add_business_minutes(now_anchor, remaining_new)
        else:
            resolution_start = ticket.resolution_started_at
            if resolution_start and not _is_business_hour(resolution_start):
                resolution_start = _next_business_start(resolution_start)
            if resolution_start:
                ticket.sla_due_at = _add_business_minutes(resolution_start, new_resolution_minutes)


def _save_ticket_with_code(ticket):
    for _ in range(5):
        ticket.code = _gen_code()
        try:
            ticket.save()
            return ticket
        except IntegrityError:
            continue
    ticket.save()


def _notify(user, title, message="", url="", send_email=False, cc_emails=None):

    if not user:
        return

    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        url=url
    )

    
    # Si NO quiero enviar correo, solo se queda como notificación interna
    if not send_email:
        return

    # Si sí quiero enviar correo, pero el usuario no tiene email, no se envía
    if not user.email:
        return

    try:
        raw = textwrap.dedent(message or "").strip()
        escaped = html.escape(raw)

        formatted_message = (
            escaped.replace("Ticket:", "<b>Ticket:</b>")
                .replace("Título:", "<b>Título:</b>")
                .replace("Estado:", "<b>Estado:</b>")
                .replace("Prioridad:", "<b>Prioridad:</b>")
                .replace("Severidad:", "<b>Severidad:</b>")
                .replace("Cliente:", "<b>Cliente:</b>")
                .replace("Asignado a:", "<b>Asignado a:</b>")
                .replace("Calificación:", "<b>Calificación:</b>")
                .replace("Comentario:", "<b>Comentario:</b>")
                .replace("Respuesta:", "<b>Respuesta:</b>")
                .replace("Fue cerrado por:", "<b>Fue cerrado por:</b>")
                .replace("Contraseña:", "<b>Contraseña:</b>")
                .replace("Nueva contraseña temporal:", "<b>Nueva contraseña temporal:</b>")
                .replace("Usuario:", "<b>Usuario:</b>")
                .replace("\n", "<br>")
        )

        absolute_url = ""
        site_link = getattr(settings, "SITE_URL", "https://assist.replica.com.pe/")

        if url and not url.startswith("http"):
            if not url.startswith("/"):
                url = "/" + url

        if url:
            if url.startswith("http"):
                absolute_url = url
            else:
                if site_link:
                    absolute_url = site_link.rstrip("/") + url
                else:
                    absolute_url = "https://assist.replica.com.pe" + url

        button_html = ""
        if absolute_url:
            button_html = f"""
                <a href="{absolute_url}"
                   style="background:#5ab0dd;
                          color:#fff;
                          text-decoration:none;
                          padding:12px 20px;
                          border-radius:8px;
                          display:inline-block;
                          font-weight:700;
                          font-size:15px;">
                    👉 Ingresa aquí
                </a>
            """

        history_html = ""
        try:
            m = re.search(r"Ticket[:\s]*([A-Z0-9-]+)", message or "")
            if m:
                code = m.group(1).strip()
                t = Ticket.objects.filter(code=code).first()

                if t:
                    is_closure_email = "ticket cerrado" in (title or "").lower()

                    if is_closure_email:
                        status_histories = (
                            TicketHistory.objects
                            .filter(ticket=t, field="status")
                            .order_by("id")
                        )

                        if status_histories:
                            lines = []
                            for i, h in enumerate(status_histories, start=1):
                                ts = getattr(h, "created_at", None)
                                when = timezone.localtime(ts).strftime("%d/%m/%Y %H:%M") if ts else ""
                                lines.append(f"{i}. {h.new_value} ({when})")

                            history_html = (
                                "<br><br>"
                                "<div style='background:#eef6ff;border-left:4px solid #5ab0dd;"
                                "padding:12px;border-radius:6px;color:#0f172a;'>"
                                "<b>Historial de estados:</b><br>"
                                + "<br>".join(lines) +
                                "</div>"
                            )
                    else:
                        histories = TicketHistory.objects.filter(ticket=t).order_by("-id")[:5]

                        if histories:
                            lines = []
                            for h in reversed(histories):
                                ts = getattr(h, "created_at", None)
                                when = ts.strftime("%Y-%m-%d %H:%M") if ts else ""
                                lines.append(f"{when} — {h.field}: {h.old_value} → {h.new_value}")

                            history_html = (
                                "<br><br>"
                                "<div style='background:#eef6ff;border-left:4px solid #5ab0dd;"
                                "padding:12px;border-radius:6px;color:#0f172a;'>"
                                "<b>Historial reciente:</b><br>"
                                + "<br>".join(lines) +
                                "</div>"
                            )
        except Exception:
            history_html = ""

        if not site_link:
            site_link = "https://assist.replica.com.pe/"

        html_message = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{
                        margin:0;
                        padding:0;
                        -webkit-text-size-adjust:none;
                        -ms-text-size-adjust:none;
                    }}
                    .email-wrap {{
                        width:100%;
                        background:#f4f6f9;
                        padding:20px 0;
                    }}
                    .container {{
                        width:100%;
                        max-width:700px;
                        margin:0 auto;
                        background:#ffffff;
                        border-radius:12px;
                        overflow:hidden;
                    }}
                    .header {{
                        padding:0;
                        text-aligning:16px;
                        border-radius:8px;
                        color:#334155;
                    }}
                    .footer {{
                        background:#f8f8f8;
                        text-align:center;
                        padding:16px;
                        color:#777;
                        font-size:12px;
                    }}

                    @media only screen and (max-width:600px) {{
                        .content {{
                            padding:16px;
                        }}
                        .panel {{
                            padding:12px;
                        }}
                        img.logo {{
                            max-width:100%;
                            height:auto;
                        }}
                        h2 {{
                            font-size:20px !important;
                        }}
                    }}
                </style>
            </head>
            <body class="email-wrap" style="font-family:Segoe UI, Arial, sans-serif;">
                <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                        <td align="center">
                            <table class="container" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td class="header">
                                        <img class="logo"
                                            src="https://imagenesassist.blob.core.windows.net/static/banners-portal-replica-assist.jpg"
                                            alt="Replica Assist"
                                            style="width:100%; display:block; margin:0; margin-bottom:18px;">
                                    </td>
                                </tr>

                                <tr>
                                    <td class="content" style="padding:20px;">
                                        <h2 style="color:#5ab0dd; margin:0 0 12px 0; font-size:28px; font-weight:700;">
                                            {title}
                                        </h2>

                                        <div class="panel">
                                            {formatted_message}
                                        </div>

                                        {history_html}

                                        <div style="margin-top:18px; text-align:center;">
                                            {button_html}
                                        </div>
                                    </td>
                                </tr>

                                <tr>
                                    <td class="footer">
                                        © 2026 Replica Assist — Soporte Técnico<br>
                                        Plataforma de gestión de tickets y soporte.<br>
                                        <a href="{site_link}" style="color:#777;text-decoration:none;">{site_link}</a><br>
                                        REPLICA SRL - Transformación digital para empresas
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
        """

        send_graph_email(
            user.email,
            title,
            html_message,
            cc_emails=cc_emails,
        )

        print("EMAIL ENVIADO A:", user.email)

    except Exception as e:
        print("ERROR EMAIL:", str(e))

def _history(ticket, user, field, old, new):
    old_s = "" if old is None else str(old)
    new_s = "" if new is None else str(new)

    if old_s == new_s:
        return

    TicketHistory.objects.create(
        ticket=ticket,
        changed_by=user,
        field=field,
        old_value=old_s[:255],
        new_value=new_s[:255],
    )


# =========================
# PERMISSIONS
# =========================

def has_permission(user, perm_code):

    if not hasattr(user, "profile") or not user.profile.role:
        return False

    if "." not in perm_code:
        return user.profile.role.permissions.filter(action=perm_code).exists()

    module, action = perm_code.split(".", 1)

    return user.profile.role.permissions.filter(
        module=module,
        action=action
    ).exists()


def permission_required(perm_code):

    def decorator(view_func):

        @wraps(view_func)
        def wrapper(request, *args, **kwargs):

            if not has_permission(request.user, perm_code):
                messages.error(request, "No tienes permiso para acceder.")
                return redirect("dashboard")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


# =========================
# AUTH
# =========================

def refresh_login_captcha(request):

    if request.method != "GET":
        return JsonResponse({"ok": False, "message": "Método no permitido."}, status=405)

    _set_login_captcha(request)

    return JsonResponse({
        "ok": True,
        "question": request.session.get("login_captcha_question", "Selecciona el ícono indicado"),
        "options": request.session.get("login_captcha_options", []),
        "ttl_seconds": CAPTCHA_TTL_SECONDS,
    })

def login_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    now_ts = timezone.now().timestamp()
    blocked_until = request.session.get("login_blocked_until")
    force_refresh_captcha = (
        request.method == "GET"
        and request.GET.get("refresh_captcha") == "1"
    )
    captcha_rotated = bool(request.session.pop("captcha_rotated_notice", False))

    # Ensure captcha exists; refresh stale captcha proactively only on non-POST requests.
    captcha_options = request.session.get("login_captcha_options")
    has_valid_visual_options = isinstance(captcha_options, list) and len(captcha_options) >= 3
    has_captcha = bool(request.session.get("login_captcha_answer")) and has_valid_visual_options

    if force_refresh_captcha:
        _set_login_captcha(request)
        captcha_rotated = True
    elif not has_captcha:
        _set_login_captcha(request)
    elif request.method != "POST" and _is_captcha_expired(request):
        _set_login_captcha(request)
        captcha_rotated = True

    if blocked_until and now_ts < blocked_until:
        messages.error(
            request,
            "Demasiados intentos. Intenta de nuevo en unos minutos."
        )
        form = LoginForm(request=request)
    else:
        if request.method == "POST":
            form = LoginForm(data=request.POST or None, request=request)
            if form.is_valid():
                user = form.get_user()
                login(request, user)

                request.session.pop("login_failed_attempts", None)
                request.session.pop("login_blocked_until", None)
                request.session.pop("login_captcha_question", None)
                request.session.pop("login_captcha_answer", None)
                request.session.pop("login_captcha_options", None)
                request.session.pop("login_captcha_created_at", None)

                if hasattr(user, "profile") and user.profile.must_change_password:
                    return redirect("change_password")

                return redirect("dashboard")
            else:
                has_captcha_error = bool(form.errors.get("captcha"))
                has_credential_error = bool(form.non_field_errors())

                if has_credential_error:
                    attempts = request.session.get("login_failed_attempts", 0) + 1
                    request.session["login_failed_attempts"] = attempts

                    if attempts >= 5:
                        request.session["login_blocked_until"] = now_ts + 300
                        messages.error(
                            request,
                            "Demasiados intentos. Intenta nuevamente en 5 minutos."
                        )

                if has_captcha_error:
                    messages.error(request, "Captcha incorrecto. Intenta nuevamente.")
                elif has_credential_error:
                    messages.error(request, "Usuario o contraseña incorrectos.")
                else:
                    messages.error(request, "No se pudo iniciar sesión. Intenta nuevamente.")

                # Rotate captcha after each failed login attempt.
                _set_login_captcha(request)
                request.session["captcha_rotated_notice"] = True
                return redirect("login")
        else:
            form = LoginForm(request=request)

    return render(request, "login.html", {
        "form": form,
        "captcha_options": request.session.get("login_captcha_options", []),
        "captcha_rotated": captcha_rotated,
    })


@login_required
@require_POST
def logout_view(request):

    logout(request)

    return redirect("login")


# =========================
# DASHBOARD
# =========================

@login_required
def dashboard(request):

    role = _role(request.user)

    if role == "ADMINISTRADOR":
        tickets = Ticket.objects.all()

    elif role == "SOPORTE":

        tickets = Ticket.objects.filter(
            assigned_to=request.user
        )

    else:
        tickets = Ticket.objects.filter(created_by=request.user)

    search = request.GET.get("search")

    if search:
        tickets = tickets.filter(
            Q(title__icontains=search) |
            Q(code__icontains=search)
        )

    tickets = tickets.order_by("-created_at")

    total = tickets.count()

    nuevos = tickets.filter(status="NUEVO").count()

    en_proceso = tickets.filter(
        status__in=["EN_PROCESO", "ESPERANDO_CLIENTE", "ESPERANDO_SOPORTE"]
    ).count()

    cerrados = tickets.filter(status="CERRADO").count()

    if role == "CLIENTE":
        breached = 0
    else:
        breached = tickets.exclude(status="CERRADO").filter(
            sla_due_at__lt=timezone.now()
        ).count()

    priorities = [
        "LOW",
        "MEDIUM",
        "HIGH"
    ]

    pr_counts = [
        tickets.filter(priority=p).count()
        for p in priorities
    ]

    notifs = Notification.objects.filter(
        user=request.user
    ).order_by("-created_at")[:6]

    unread_count = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).count()

    return render(request, "dashboard.html", {
        "tickets": tickets,
        "role": role,
        "total": total,
        "nuevos": nuevos,
        "en_proceso": en_proceso,
        "cerrados": cerrados,
        "breached": breached,
        "priorities": priorities,
        "pr_counts": pr_counts,
        "notifs": notifs,
        "unread_count": unread_count,
    })


# =========================
# CREATE TICKET
# =========================

@login_required
def create_ticket(request):

    form = TicketForm(request.POST or None, request.FILES or None, user=request.user)
    categories = Category.objects.all()
    subcategories = SubCategory.objects.all()

    if request.method == "POST" and form.is_valid():
        file = form.cleaned_data.get("file")
        
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

        if file and file.size > MAX_FILE_SIZE:
            messages.error(
                request,
                "El archivo supera el tamaño máximo permitido de 10 MB."
            )

            return render(request, "create_ticket.html", {
                "form": form,
                "categories": categories,
                "subcategories": subcategories,
                "role": _role(request.user)
            })

        ticket = form.save(commit=False)

        ticket.created_by = request.user

        if hasattr(request.user, "profile") and request.user.profile.company:
            ticket.company = request.user.profile.company

        # 👇 SI ES CLIENTE, valores por defecto
        if _role(request.user) == "CLIENTE":
            ticket.priority = "MEDIUM"

        # Priority controls severity consistently: LOW->S3, MEDIUM->S2, HIGH->S1
        ticket.severity = _severity_for_priority(ticket.priority)

        _save_ticket_with_code(ticket)
        
        sla = SLA.objects.filter(
            severity=ticket.severity
        ).first()

        if sla:

            start_at = _next_business_start(timezone.now())
            ticket.first_response_due_at = _add_business_minutes(
                start_at,
                sla.response_minutes
            )

            # resolución todavía NO inicia
            ticket.sla_due_at = None

            ticket.save()

            if not _is_business_hour():
                messages.info(
                    request,
                    "Estamos fuera del horario de atención (08:00-18:00). El SLA se contará a partir del próximo horario hábil."
                )

        if file:
            TicketAttachment.objects.create(
                ticket=ticket,
                uploaded_by=request.user,
                file=file
            )
            
        _notify(
            request.user,
            "Ticket creado",
            f"""
        Ticket: {ticket.code}

        Título:
        {ticket.title}

        Estado:
        {ticket.get_status_display()}
        """,
            url=f"/ticket/{ticket.id}/",
            send_email=True,
            cc_emails=["soporte@replica.com.pe"],
        )

        if ticket.assigned_to:
            _notify(
                ticket.assigned_to,
                "Nuevo ticket creado",
                f"""
        Ticket: {ticket.code}

        Título:
        {ticket.title}

        Estado:
        {ticket.get_status_display()}
        """,
                url=f"/ticket/{ticket.id}/",
                send_email=True,
                cc_emails=["soporte@replica.com.pe"],
            )
        
        admins = User.objects.filter(
            profile__role__name="ADMINISTRADOR"
        )

        for admin in admins:

            _notify(
                admin,
                "Nuevo ticket registrado",
                f"""
        Ticket:
        {ticket.code}

        Cliente:
        {request.user.username}
        """,
                url=f"/ticket/{ticket.id}/"
            )
        
        messages.success(
            request,
            "Ticket creado correctamente"
        )

        return redirect(
            "ticket_detail",
            ticket_id=ticket.id
        )


    return render(request, "create_ticket.html", {
        "form": form,
        "categories": categories,
        "subcategories": subcategories,
        "role": _role(request.user)
    })

@login_required
@require_POST
def close_ticket(request, ticket_id):

    ticket = get_object_or_404(Ticket, id=ticket_id)

    if _role(request.user) not in ["ADMINISTRADOR", "SOPORTE"]:
        return redirect("dashboard")

    if ticket.status != "CERRADO":


        comment = request.POST.get("comment")
        customer_confirmation = request.POST.get("customer_confirmation")

        if not comment:

            messages.error(
                request,
                "Debe ingresar comentario de cierre."
            )

            return redirect(
                "ticket_detail",
                ticket_id=ticket.id
            )

        if not customer_confirmation:
            messages.error(
                request,
                "Debe confirmar la conformidad del cliente antes de cerrar el ticket."
            )

            return redirect(
                "ticket_detail",
                ticket_id=ticket.id
            )

        TicketMessage.objects.create(
            ticket=ticket,
            author=request.user,
            message=comment,
            is_internal=False
        )
        
        old_status = ticket.status
        ticket.status = "CERRADO"
        _pause_sla(ticket)
        ticket.resolved_at = timezone.now()
        ticket.save()
        _history(
            ticket,
            request.user,
            "status",
            old_status,
            "CERRADO"
        )

        confirmed_at = timezone.localtime(ticket.resolved_at).strftime("%d/%m/%Y %H:%M")
        _history(
            ticket,
            request.user,
            "conformidad_cliente_cierre",
            "Pendiente",
            f"Confirmada por {request.user.get_full_name() or request.user.username} el {confirmed_at}"
        )

        _notify(
            ticket.created_by,
            "Ticket cerrado",
            f"""
        Ticket: {ticket.code}

        Fue cerrado por: {request.user.get_full_name() or request.user.username}

        Comentario:
        {comment}
        """,
            url=f"/ticket/{ticket.id}/",
            send_email=True,
            cc_emails=["soporte@replica.com.pe"],
        )

        if ticket.assigned_to:
            _notify(
                ticket.assigned_to,
                "Ticket cerrado",
                f"""
        Ticket:
        {ticket.code}

        Fue cerrado por:
        {request.user.username}
        """,
                url=f"/ticket/{ticket.id}/",
            send_email=True,
            cc_emails=["soporte@replica.com.pe"],
            )

        messages.success(request, "Ticket cerrado correctamente")

    return redirect("ticket_detail", ticket_id=ticket.id)


@login_required
def ticket_detail(request, ticket_id):

    ticket = get_object_or_404(Ticket, id=ticket_id)

    role = _role(request.user)

    if role == "SOPORTE" and ticket.assigned_to and ticket.assigned_to != request.user:
        return redirect("dashboard")

    if role == "CLIENTE" and ticket.created_by != request.user:
        return redirect("dashboard")

    msg_form = MessageForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and msg_form.is_valid():

        if ticket.status == "CERRADO":
            messages.error(request, "El ticket está cerrado")
            return redirect("ticket_detail", ticket_id=ticket.id)

        msg = msg_form.save(commit=False)

        msg.ticket = ticket
        msg.author = request.user
        msg.is_internal = False

        msg.save()

        file = msg_form.cleaned_data.get("file")

        if file:
            TicketAttachment.objects.create(
                ticket=ticket,
                message=msg,
                uploaded_by=request.user,
                file=file
            )

        old_status = ticket.status

        if ticket.status != "CERRADO":

            if request.user == ticket.created_by:
                # Cliente escribió
                ticket.status = "ESPERANDO_SOPORTE"
                _pause_sla(ticket)
            else:
                # Soporte/Admin escribió
                _mark_first_response(ticket, request.user)
                ticket.status = "ESPERANDO_CLIENTE"
                _pause_sla(ticket)

        ticket.save()

        _history(ticket, request.user, "status", old_status, ticket.status)

        if request.user == ticket.created_by:

            if ticket.assigned_to:
                _notify(
                    ticket.assigned_to,
                    "Nuevo mensaje del cliente",
                    f"""
                Ticket: {ticket.code}

                El cliente ha enviado un nuevo mensaje:
                {msg.message}
                """,
                    url=f"/ticket/{ticket.id}/"
                )

        else:

            _notify(
                ticket.created_by,
                "Nueva respuesta en tu ticket",
                f"""
            Ticket:
            {ticket.code}

            Respuesta:
            {msg.message}
            """,
                url=f"/ticket/{ticket.id}/"
            )

        messages.success(request, "Mensaje enviado")

        return redirect("ticket_detail", ticket_id=ticket.id)

    notifs = Notification.objects.filter(
        user=request.user
    ).order_by("-created_at")[:6]

    unread_count = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).count()

    first_response_start = ticket.created_at
    if ticket.first_response_due_at and not _is_business_hour(ticket.created_at):
        first_response_start = _next_business_start(ticket.created_at)

    resolution_start = ticket.resolution_started_at
    if resolution_start and not _is_business_hour(resolution_start):
        resolution_start = _next_business_start(resolution_start)

    return render(request, "ticket_detail.html", {
        "ticket": ticket,
        "role": role,
        "msg_form": msg_form,
        "notifs": notifs,
        "unread_count": unread_count,
        "first_response_start_at": first_response_start,
        "resolution_start_at": resolution_start,
        "is_business_hour": _is_business_hour(),
        "business_message": (
            "Estamos fuera del horario de atención (lunes a viernes, 08:00-18:00) o en fin de semana. El SLA se contará a partir del próximo horario hábil."
            if not _is_business_hour() else ""
        )
    })


@login_required
def ticket_status_json(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    role = _role(request.user)

    if role == "SOPORTE" and ticket.assigned_to and ticket.assigned_to != request.user:
        return JsonResponse({"error": "No autorizado."}, status=403)

    if role == "CLIENTE" and ticket.created_by != request.user:
        return JsonResponse({"error": "No autorizado."}, status=403)

    messages = []
    for m in ticket.messages.all().order_by("created_at"):
        if m.is_internal:
            continue

        messages.append({
            "id": m.id,
            "author": m.author.get_full_name() or m.author.username,
            "message": m.message,
            "created_at": m.created_at.strftime("%d/%m/%Y %H:%M"),
            "own": m.author_id == request.user.id,
            "files": [
                {
                    "url": request.build_absolute_uri(file.file.url),
                    "name": os.path.basename(file.file.name)
                }
                for file in m.files.all()
            ]
        })

    assigned_to = ticket.assigned_to.get_full_name() if ticket.assigned_to else "Por asignar (tiempo máximo 20 min)"
    business_message = ""
    if not _is_business_hour():
        business_message = (
            "Estamos fuera del horario de atención (lunes a viernes, 08:00-18:00) o en fin de semana. "
            "El SLA se contará a partir del próximo horario hábil."
        )

    ticket_data = {
        "status": ticket.get_status_display(),
        "status_code": ticket.status,
        "assigned_to": assigned_to,
        "assigned_email": ticket.assigned_to.email if ticket.assigned_to else "",
        "assigned_phone": ticket.assigned_to.profile.phone if ticket.assigned_to and hasattr(ticket.assigned_to, "profile") else "",
        "first_response_due_at": ticket.first_response_due_at.isoformat() if ticket.first_response_due_at else None,
        "sla_due_at": ticket.sla_due_at.isoformat() if ticket.sla_due_at else None,
        "first_response_start_at": ticket.created_at.isoformat() if ticket.first_response_due_at else None,
        "resolution_start_at": ticket.resolution_started_at.isoformat() if ticket.resolution_started_at else None,
        "business_message": business_message,
        "is_business_hour": _is_business_hour(),
        "messages": messages,
        "updated_at": ticket.updated_at.isoformat(),
        "is_closed": ticket.status == "CERRADO",
        "sla_paused": ticket.sla_paused,
    }

    return JsonResponse(ticket_data)


# =========================
# TAKE TICKET
# =========================

@login_required
def take_ticket(request, ticket_id):
    if not has_permission(request.user, "tickets.edit"):
        return redirect("dashboard")

    ticket = get_object_or_404(Ticket, id=ticket_id)

    if ticket.status == "CERRADO":
        messages.error(request, "No se puede tomar un ticket cerrado.")
        return redirect("ticket_detail", ticket_id=ticket.id)

    if ticket.assigned_to:
        messages.error(request, "Este ticket ya está asignado")
        return redirect("ticket_detail", ticket_id=ticket.id)

    if not ticket.severity:
        messages.error(request, "Debe asignarse severidad primero.")
        return redirect("ticket_detail", ticket_id=ticket.id) 
    
        
    ticket.assigned_to = request.user
    ticket.status = "ESPERANDO_CLIENTE"

    _mark_first_response(ticket, request.user)

    if not ticket.resolution_started_at:
        ticket.resolution_started_at = timezone.now()

    _pause_sla(ticket)

    sla = SLA.objects.filter(severity=ticket.severity).first()

    if sla and not ticket.sla_due_at:
            ticket.sla_due_at = _add_business_minutes(
                timezone.now(),
                sla.resolution_minutes
            )
    ticket.save()


    _history(
        ticket,
        request.user,
        "assigned_to",
        "",
        request.user.username
    )

    _history(
        ticket,
        request.user,
        "status",
        "NUEVO",
        "ESPERANDO_CLIENTE"
    )

    _notify(
        ticket.created_by,
        "Ticket asignado",
        f"""
    Ticket: {ticket.code}

    Estado: {ticket.get_status_display()}
    Prioridad: {ticket.get_priority_display()}
    Severidad: {ticket.get_severity_display()}

    Tu ticket ha sido asignado a {request.user.get_full_name() or request.user.username}.
    """,
        url=f"/ticket/{ticket.id}/",
        send_email=True,
        cc_emails=["soporte@replica.com.pe"],
    )

    messages.success(request, "Ticket asignado a ti")

    return redirect("ticket_detail", ticket_id=ticket.id)

@login_required
def update_ticket_admin(request, ticket_id):

    ticket = get_object_or_404(Ticket, id=ticket_id)
    

    role = _role(request.user)

    if role == "CLIENTE":
        return redirect("dashboard")

    if role == "SOPORTE" and ticket.assigned_to != request.user:
        return redirect("dashboard")

    if role == "ADMINISTRADOR":

        class AdminTicketForm(forms.ModelForm):

            class Meta:
                model = Ticket

                fields = [
                    "status",
                    "priority",
                    "severity",
                    "assigned_to"
                ]

                widgets = {
                    "status": forms.Select(attrs={"class":"input"}),
                    "priority": forms.Select(attrs={"class":"input"}),
                    "severity": forms.Select(attrs={"class":"input"}),
                    "assigned_to": forms.Select(attrs={"class":"input"}),
                }
                
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                self.fields["assigned_to"].queryset = User.objects.filter(
                    profile__role__name__in=[
                        "SOPORTE"
                    ]
                )

        form = AdminTicketForm(
            request.POST or None,
            instance=ticket
        )

    else:

        form = UpdateTicketForm(
            request.POST or None,
            instance=ticket
        )

    if request.method == "POST" and form.is_valid():

        if ticket.status == "CERRADO":
            messages.error(
                request,
                "No se puede modificar un ticket cerrado."
            )
            return redirect("ticket_detail", ticket_id=ticket.id)

        old_status = ticket.status
        old_priority = ticket.priority
        old_severity = ticket.severity
        old_assigned = ticket.assigned_to
        old_assigned_id = ticket.assigned_to_id
        updated = form.save(commit=False)
        severity_changed = old_severity != _severity_for_priority(updated.priority)

        assigned_now = (
            updated.assigned_to
            and old_assigned_id != updated.assigned_to_id
        )

        
        from tickets.models import SLA
        
        # Enforce severity from selected priority.
        updated.severity = _severity_for_priority(updated.priority)

        try:

            sla = SLA.objects.get(
                severity=updated.severity
            )

            old_sla = SLA.objects.filter(
                severity=old_severity
            ).first() if old_severity else None

            if severity_changed and old_sla:
                _recalculate_running_deadlines(
                    updated,
                    old_sla.response_minutes,
                    old_sla.resolution_minutes,
                    sla.response_minutes,
                    sla.resolution_minutes,
                )

            if updated.first_response_due_at is None:
                updated.first_response_due_at = _add_business_minutes(
                    timezone.now(),
                    sla.response_minutes
                )

            if updated.assigned_to and not updated.sla_due_at:

                updated.sla_due_at = _add_business_minutes(
                    timezone.now(),
                    sla.resolution_minutes
                )

        except SLA.DoesNotExist:
            pass        
        
        
        if updated.status == "EN_PROCESO":
            
            if not updated.sla_due_at:

                sla = SLA.objects.filter(
                    severity=updated.severity
                ).first()

                if sla:

                    updated.sla_due_at = _add_business_minutes(
                        timezone.now(),
                        sla.resolution_minutes
                    )

            _resume_sla(updated)

        elif updated.status in [
            "ESPERANDO_CLIENTE",
            "ESPERANDO_SOPORTE"
        ]:
            _pause_sla(updated)

        if updated.status == "CERRADO" and ticket.resolved_at is None:
            updated.resolved_at = timezone.now()
            _pause_sla(updated)
            

        
        if updated.assigned_to:
            # Detener contador de primera respuesta al asignar
            _mark_first_response(updated, request.user)

            if not updated.resolution_started_at:
                updated.resolution_started_at = timezone.now()


        updated.save()
        
        
        if assigned_now:

            # Cuando se asigna por primera vez, detener primera respuesta
            _mark_first_response(updated, request.user)

            # Cuando se asigna por primera vez, cambiar a ESPERANDO_CLIENTE
            # El soporte debe manualmente cambiar a EN_PROCESO para reanudar SLA
            updated.status = "ESPERANDO_CLIENTE"
            _pause_sla(updated)


            sla = SLA.objects.filter(
                severity=updated.severity
            ).first()

            if sla:

                updated.sla_due_at = _add_business_minutes(
                    timezone.now(),
                    sla.resolution_minutes
                )

            updated.save()
    
        
        _history(
            ticket,
            request.user,
            "status",
            old_status,
            updated.status
        )

        _history(
            ticket,
            request.user,
            "priority",
            old_priority,
            updated.priority
        )

        _history(
            ticket,
            request.user,
            "severity",
            old_severity,
            updated.severity
        )

        _history(
            ticket,
            request.user,
            "assigned_to",
            old_assigned.username if old_assigned else "",
            updated.assigned_to.username if updated.assigned_to else ""
        )
        
        if not assigned_now:
            _notify(
                ticket.created_by,
                "Ticket actualizado",
                f"""
        Ticket: {ticket.code}

        Estado: {updated.get_status_display()}
        Prioridad: {updated.get_priority_display()}
        Severidad: {updated.get_severity_display()}
        """,
                url=f"/ticket/{ticket.id}/"
            )

        if updated.assigned_to and old_assigned_id != updated.assigned_to_id:

            # NUEVO SOPORTE

            _notify(
                updated.assigned_to,
                "Nuevo ticket asignado",
                f"""
            Ticket: {ticket.code}

            Título: {ticket.title}

            Prioridad: {updated.get_priority_display()}
            Severidad: {updated.get_severity_display()}

            Has sido asignado a este ticket.
            """,
                url=f"/ticket/{ticket.id}/",
                send_email=True,
                cc_emails=["soporte@replica.com.pe"],
            )

            # SOPORTE ANTERIOR

            if old_assigned:

                _notify(
                    old_assigned,
                    "Ticket reasignado",
                    f"""
            El ticket {ticket.code}
            fue reasignado.
                    """,
                    url=f"/ticket/{ticket.id}/",
                    send_email=True,
                    cc_emails=["soporte@replica.com.pe"],
                )

            # CLIENTE

            _notify(
                ticket.created_by,
                "Caso asignado al analista de soporte",
                f"""
        Ticket:
        {ticket.code}

        Estado: {updated.get_status_display()}
        Prioridad: {updated.get_priority_display()}
        Severidad: {updated.get_severity_display()}

        Asignado a:
        {updated.assigned_to.get_full_name() or updated.assigned_to.username}

        Tu caso ya tiene un analista asignado.
                """,
            url=f"/ticket/{ticket.id}/",
            send_email=True,
            cc_emails=["soporte@replica.com.pe"],
            )
        messages.success(request, "Ticket actualizado")

        return redirect("ticket_detail", ticket_id=ticket.id)

    return render(request, "update_status.html", {
        "form": form,
        "ticket": ticket
    })
# =========================
# INBOX
# =========================


@login_required
def inbox(request):

    messages.error(request, "Esta sección está deshabilitada.")
    return redirect("dashboard")


# =========================
# ADMIN: PORTAL
# =========================

@login_required
def admin_portal(request):

    if not has_permission(request.user, "dashboard.view"):
        return redirect("dashboard")

    tickets = Ticket.objects.all().order_by("-created_at")

    total = tickets.count()
    nuevos = tickets.filter(status="NUEVO").count()
    en_proceso = tickets.filter(status__in=["EN_PROCESO", "ESPERANDO_CLIENTE", "ESPERANDO_SOPORTE"]).count()
    cerrados = tickets.filter(status="CERRADO").count()
    breached = tickets.exclude(status="CERRADO").filter(
        sla_due_at__lt=timezone.now()
    ).count()

    return render(request, "admin_portal.html", {
        "tickets": tickets[:10],
        "total": total,
        "nuevos": nuevos,
        "en_proceso": en_proceso,
        "cerrados": cerrados,
        "breached": breached,
    })


# =========================
# ADMIN: COMPANIES
# =========================

@login_required
def admin_companies(request):

    if not has_permission(request.user, "companies.view"):
        return redirect("dashboard")

    companies = Company.objects.all().order_by("name")
    form = CompanyForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Empresa creada ✅")
        return redirect("admin_companies")

    return render(request, "admin_companies.html", {
        "companies": companies,
        "form": form
    })


# =========================
# ADMIN: USERS
# =========================

@login_required
def admin_users(request):

    if not has_permission(request.user, "users.view"):
        return redirect("dashboard")

    users = User.objects.select_related("profile").all().order_by("username")

    create_form = AdminUserCreateForm(request.POST or None)
    edit_user_id = request.GET.get("edit")

    edit_user = None
    edit_form = None

    if edit_user_id:
        edit_user = get_object_or_404(User, id=edit_user_id)

        edit_form = AdminUserRoleForm(
            request.POST or None,
            
            initial={
                "role": edit_user.profile.role if hasattr(edit_user, "profile") else None,
                "company": edit_user.profile.company if hasattr(edit_user, "profile") else None,
                "email": edit_user.email
            }
            
        )

        if request.method == "POST" and request.POST.get("action") == "edit_user":

            if edit_form.is_valid():

                edit_user.profile.role = edit_form.cleaned_data["role"]
                edit_user.profile.company = edit_form.cleaned_data["company"]
                edit_user.email = edit_form.cleaned_data["email"]
                edit_user.save()
                edit_user.profile.save()

                messages.success(request, "Usuario actualizado ✅")
                return redirect("admin_users")  

    if request.method == "POST" and request.POST.get("action") == "create_user":
    
        if create_form.is_valid():

            role = create_form.cleaned_data["role"]
            company = create_form.cleaned_data["company"]
            
            username = (create_form.cleaned_data["login_email"] or "").strip().lower()
            email = username

            if User.objects.filter(username=username).exists():

                messages.error(
                    request,
                    "El usuario/correo ya existe."
                )

                return render(request, "admin_users.html", {
                    "users": users,
                    "create_form": create_form,
                    "edit_user": edit_user,
                    "edit_form": edit_form,
                })

            role_name = role.name.strip().upper()

            # VALIDAR EMPRESA SOLO PARA CLIENTE

            if "CLIENTE" in role_name and not company:

                messages.error(
                    request,
                    "Debe seleccionar una empresa para el usuario."
                )

                return render(request, "admin_users.html", {
                    "users": users,
                    "create_form": create_form,
                    "edit_user": edit_user,
                    "edit_form": edit_form,
                })
                
            # VALIDACIONES GENERALES

            if not create_form.cleaned_data.get("password"):

                messages.error(
                    request,
                    "La contraseña es obligatoria."
                )

                return redirect("admin_users")

            # CLIENTE requiere datos completos

            if "CLIENTE" in role_name:

                if not create_form.cleaned_data.get("first_name"):

                    messages.error(
                        request,
                        "El nombre es obligatorio."
                    )

                    return redirect("admin_users")

                if not create_form.cleaned_data.get("last_name"):

                    messages.error(
                        request,
                        "El apellido es obligatorio."
                    )

                    return redirect("admin_users")

            plain_password = create_form.cleaned_data["password"]
            
            u = User.objects.create_user(
                username=username,
                password= plain_password,
                email=email,
                first_name=create_form.cleaned_data.get("first_name", ""),
                last_name=create_form.cleaned_data.get("last_name", ""),
            )

            profile, created = Profile.objects.get_or_create(user=u)

            profile.role = role
            profile.phone = create_form.cleaned_data.get("phone", "")
            profile.support_level = int(
                request.POST.get("support_level", 1)
            )

            # CLIENTE usa empresa seleccionada
            if "CLIENTE" in role_name:

                profile.company = company

            else:

                # TODOS LOS DEMÁS → REPLICA
                replica_company, created = Company.objects.get_or_create(
                    name="REPLICA",
                    defaults={
                        "email": "soporte@replica.com.pe"
                    }
                )

                profile.company = replica_company

            profile.must_change_password = True
            profile.save()

            _notify(
                u,
                "Usuario creado en Replica Assist",
                f"""
                Hola {u.first_name},

                Tu usuario fue creado correctamente.

                Usuario: {u.username}
                Contraseña: {plain_password}

                Debes cambiar tu contraseña al iniciar sesión.
                                """,
                url=request.build_absolute_uri(reverse("login")),
                send_email=True,
                cc_emails=[]
            )

            messages.success(
                request,
                "Usuario creado correctamente ✅"
            )

            return redirect("admin_users")
        
    return render(request, "admin_users.html", {
        "users": users,
        "create_form": create_form,
        "edit_user": edit_user,
        "edit_form": edit_form,
    })
# =========================
# ADMIN: SUPPORT
# =========================

@login_required
def admin_support(request):

    if not has_permission(request.user, "support.view"):
        return redirect("dashboard")

    supports = User.objects.filter(profile__role__name__icontains="SOPORTE").distinct().order_by("username")

    rows = []
    for s in supports:
        open_count = Ticket.objects.filter(assigned_to=s).exclude(status="CERRADO").count()
        rows.append((s, open_count))

    rows.sort(key=lambda x: x[1])

    return render(request, "admin_support.html", {"rows": rows})


# =========================
# ADMIN: TICKETS
# =========================

@login_required
def admin_tickets(request):

    if not has_permission(request.user, "tickets.view"):
        return redirect("dashboard")

    qs = Ticket.objects.all().order_by("-created_at")

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    priority = request.GET.get("priority")
    if priority:
        qs = qs.filter(priority=priority)

    sla_filter = request.GET.get("sla")
    if sla_filter == "breached":
        qs = qs.exclude(status="CERRADO").filter(
            sla_due_at__lt=timezone.now(),
            sla_paused=False
        )

    return render(request, "admin_tickets.html", {
        "tickets": qs,
        "status_choices": Ticket.STATUS_CHOICES,
    })


@login_required
def admin_backup(request):

    if not _is_admin(request.user):
        return redirect("dashboard")

    media_files, media_bytes = _media_stats()
    backup_stats = {
        "users": User.objects.count(),
        "tickets": Ticket.objects.count(),
        "messages": TicketMessage.objects.count(),
        "attachments": TicketAttachment.objects.count(),
        "media_files": media_files,
        "media_size": _format_bytes(media_bytes),
        "last_exported_at": request.session.get("backup_last_exported_at", ""),
        "last_exported_size": request.session.get("backup_last_exported_size", ""),
        "last_imported_at": request.session.get("backup_last_imported_at", ""),
    }

    return render(request, "admin_backup.html", {
        "backup_stats": backup_stats,
    })


@login_required
def export_tickets_csv(request):

    if not _is_admin(request.user):
        return redirect("dashboard")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="tickets_backup.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "code",
        "title",
        "description",
        "status",
        "priority",
        "severity",
        "created_by",
        "assigned_to",
        "company",
        "category",
        "subcategory",
        "brand",
        "created_at",
        "updated_at",
        "first_response_due_at",
        "sla_due_at",
        "first_responded_at",
        "resolved_at",
        "sla_paused",
        "sla_pause_started_at",
        "rating",
        "rating_comment",
        "escalated",
        "escalated_at",
    ])

    tickets = Ticket.objects.select_related(
        "created_by",
        "assigned_to",
        "company",
        "category",
        "subcategory",
        "brand",
    ).order_by("id")

    for t in tickets:
        writer.writerow([
            t.code,
            t.title,
            t.description,
            t.status,
            t.priority,
            t.severity or "",
            t.created_by.username if t.created_by else "",
            t.assigned_to.username if t.assigned_to else "",
            t.company.name if t.company else "",
            t.category.name if t.category else "",
            t.subcategory.name if t.subcategory else "",
            t.brand.name if t.brand else "",
            t.created_at.isoformat() if t.created_at else "",
            t.updated_at.isoformat() if t.updated_at else "",
            t.first_response_due_at.isoformat() if t.first_response_due_at else "",
            t.sla_due_at.isoformat() if t.sla_due_at else "",
            t.first_responded_at.isoformat() if t.first_responded_at else "",
            t.resolved_at.isoformat() if t.resolved_at else "",
            "1" if t.sla_paused else "0",
            t.sla_pause_started_at.isoformat() if t.sla_pause_started_at else "",
            t.rating if t.rating is not None else "",
            t.rating_comment or "",
            "1" if t.escalated else "0",
            t.escalated_at.isoformat() if t.escalated_at else "",
        ])

    return response


def _parse_bool(value):
    val = (value or "").strip().lower()
    return val in {"1", "true", "t", "si", "sí", "yes", "y"}


def _parse_dt(value):
    raw = (value or "").strip()
    if not raw:
        return None

    dt = parse_datetime(raw)
    if not dt:
        return None

    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())

    return dt


def _format_bytes(size):
    value = float(max(size, 0))
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0

    while value >= 1024 and unit_idx < len(units) - 1:
        value /= 1024
        unit_idx += 1

    if unit_idx == 0:
        return f"{int(value)} {units[unit_idx]}"

    return f"{value:.1f} {units[unit_idx]}"


def _media_stats():
    media_root = getattr(settings, "MEDIA_ROOT", "")
    if not media_root or not os.path.isdir(media_root):
        return 0, 0

    files = 0
    total_bytes = 0
    for current_root, _, filenames in os.walk(media_root):
        for filename in filenames:
            files += 1
            full_path = os.path.join(current_root, filename)
            try:
                total_bytes += os.path.getsize(full_path)
            except OSError:
                pass

    return files, total_bytes


@login_required
def import_tickets_csv(request):

    if not _is_admin(request.user):
        return redirect("dashboard")

    if request.method != "POST":
        return redirect("admin_backup")

    file_obj = request.FILES.get("tickets_file")
    if not file_obj:
        messages.error(request, "Debes seleccionar un archivo CSV.")
        return redirect("admin_backup")

    try:
        decoded = file_obj.read().decode("utf-8-sig")
        rows = csv.DictReader(decoded.splitlines())
    except Exception:
        messages.error(request, "No se pudo leer el archivo. Verifica que sea CSV UTF-8.")
        return redirect("admin_backup")

    valid_status = {k for k, _ in Ticket.STATUS_CHOICES}
    valid_priority = {k for k, _ in Ticket.PRIORITY_CHOICES}
    valid_severity = {k for k, _ in Ticket.SEVERITY_CHOICES}

    created_count = 0
    updated_count = 0
    skipped_count = 0
    errors = []

    for idx, row in enumerate(rows, start=2):
        code = (row.get("code") or "").strip()
        title = (row.get("title") or "").strip()
        description = (row.get("description") or "").strip()

        if not code:
            skipped_count += 1
            continue

        if not title:
            errors.append(f"Fila {idx}: title es obligatorio para {code}.")
            continue

        if not description:
            errors.append(f"Fila {idx}: description es obligatorio para {code}.")
            continue

        created_by_username = (row.get("created_by") or "").strip()
        created_by = User.objects.filter(username=created_by_username).first() if created_by_username else None
        if not created_by:
            created_by = request.user

        ticket, created = Ticket.objects.get_or_create(
            code=code,
            defaults={
                "created_by": created_by,
                "title": title,
                "description": description,
            },
        )

        ticket.title = title
        ticket.description = description
        ticket.created_by = created_by

        status = (row.get("status") or "").strip().upper()
        if status in valid_status:
            ticket.status = status

        priority = (row.get("priority") or "").strip().upper()
        if priority in valid_priority:
            ticket.priority = priority

        severity = (row.get("severity") or "").strip().upper()
        ticket.severity = severity if severity in valid_severity else None

        assigned_username = (row.get("assigned_to") or "").strip()
        ticket.assigned_to = User.objects.filter(username=assigned_username).first() if assigned_username else None

        company_name = (row.get("company") or "").strip()
        ticket.company = Company.objects.filter(name=company_name).first() if company_name else None

        category_name = (row.get("category") or "").strip()
        ticket.category = Category.objects.filter(name=category_name).first() if category_name else None

        subcategory_name = (row.get("subcategory") or "").strip()
        ticket.subcategory = None
        if subcategory_name and ticket.category:
            ticket.subcategory = SubCategory.objects.filter(
                category=ticket.category,
                name=subcategory_name,
            ).first()
        elif subcategory_name:
            ticket.subcategory = SubCategory.objects.filter(name=subcategory_name).first()

        brand_name = (row.get("brand") or "").strip()
        ticket.brand = Brand.objects.filter(name=brand_name).first() if brand_name else None

        ticket.first_response_due_at = _parse_dt(row.get("first_response_due_at"))
        ticket.sla_due_at = _parse_dt(row.get("sla_due_at"))
        ticket.first_responded_at = _parse_dt(row.get("first_responded_at"))
        ticket.resolved_at = _parse_dt(row.get("resolved_at"))
        ticket.sla_pause_started_at = _parse_dt(row.get("sla_pause_started_at"))
        ticket.escalated_at = _parse_dt(row.get("escalated_at"))

        ticket.sla_paused = _parse_bool(row.get("sla_paused"))
        ticket.escalated = _parse_bool(row.get("escalated"))

        rating_raw = (row.get("rating") or "").strip()
        if rating_raw:
            try:
                rating_value = int(rating_raw)
                ticket.rating = rating_value if 1 <= rating_value <= 5 else None
            except ValueError:
                ticket.rating = None
        else:
            ticket.rating = None

        ticket.rating_comment = (row.get("rating_comment") or "").strip()

        created_at = _parse_dt(row.get("created_at"))

        ticket.save()

        if created and created_at:
            Ticket.objects.filter(id=ticket.id).update(created_at=created_at)

        if created:
            created_count += 1
        else:
            updated_count += 1

    if errors:
        max_errors = 5
        for err in errors[:max_errors]:
            messages.error(request, err)
        if len(errors) > max_errors:
            messages.error(request, f"Se omitieron {len(errors) - max_errors} errores adicionales.")

    messages.success(
        request,
        f"Importación completada. Creados: {created_count}, actualizados: {updated_count}, omitidos: {skipped_count}."
    )
    return redirect("admin_backup")


BACKUP_MODEL_ORDER = [
    "tickets.Permission",
    "tickets.Role",
    "tickets.Company",
    "auth.User",
    "tickets.Profile",
    "tickets.Category",
    "tickets.SubCategory",
    "tickets.Brand",
    "tickets.SLA",
    "tickets.Ticket",
    "tickets.TicketMessage",
    "tickets.TicketAttachment",
    "tickets.TicketHistory",
    "tickets.Notification",
]


def _backup_filename(model_label):
    return model_label.replace(".", "_").lower() + ".json"


def _safe_media_target_path(base_dir, member_name):
    rel = member_name.replace("\\", "/")
    if not rel.startswith("media/"):
        return None

    inner = rel[len("media/"):].lstrip("/")
    if not inner:
        return None

    target = os.path.abspath(os.path.join(base_dir, inner))
    base_abs = os.path.abspath(base_dir)

    if os.path.commonpath([base_abs, target]) != base_abs:
        return None

    return target


@login_required
def export_full_backup(request):

    if not _is_admin(request.user):
        return redirect("dashboard")

    querysets = {
        "tickets.Permission": Permission.objects.all().order_by("id"),
        "tickets.Role": Role.objects.all().order_by("id"),
        "tickets.Company": Company.objects.all().order_by("id"),
        "auth.User": User.objects.all().order_by("id"),
        "tickets.Profile": Profile.objects.all().order_by("id"),
        "tickets.Category": Category.objects.all().order_by("id"),
        "tickets.SubCategory": SubCategory.objects.all().order_by("id"),
        "tickets.Brand": Brand.objects.all().order_by("id"),
        "tickets.SLA": SLA.objects.all().order_by("id"),
        "tickets.Ticket": Ticket.objects.all().order_by("id"),
        "tickets.TicketMessage": TicketMessage.objects.all().order_by("id"),
        "tickets.TicketAttachment": TicketAttachment.objects.all().order_by("id"),
        "tickets.TicketHistory": TicketHistory.objects.all().order_by("id"),
        "tickets.Notification": Notification.objects.all().order_by("id"),
    }

    manifest = {
        "generated_at": timezone.now().isoformat(),
        "models": {},
        "media_files": 0,
        "media_total_bytes": 0,
        "notes": [
            "El ZIP incluye datos JSON y archivos de media/.",
            "Si existe gran volumen de adjuntos, la descarga puede tardar.",
        ],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for model_label in BACKUP_MODEL_ORDER:
            qs = querysets[model_label]
            payload = serializers.serialize("json", qs)
            zf.writestr(f"data/{_backup_filename(model_label)}", payload)
            manifest["models"][model_label] = qs.count()

        media_root = getattr(settings, "MEDIA_ROOT", "")
        if media_root and os.path.isdir(media_root):
            for root, _, files in os.walk(media_root):
                for filename in files:
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, media_root).replace("\\", "/")
                    arcname = f"media/{rel_path}"
                    zf.write(full_path, arcname=arcname)
                    manifest["media_files"] += 1
                    try:
                        manifest["media_total_bytes"] += os.path.getsize(full_path)
                    except OSError:
                        pass

        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    buffer.seek(0)

    zip_data = buffer.getvalue()
    request.session["backup_last_exported_at"] = timezone.now().strftime("%Y-%m-%d %H:%M")
    request.session["backup_last_exported_size"] = _format_bytes(len(zip_data))

    response = HttpResponse(zip_data, content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="replicaassist_full_backup.zip"'
    return response


@login_required
def import_full_backup(request):

    if not _is_admin(request.user):
        return redirect("dashboard")

    if request.method != "POST":
        return redirect("admin_backup")

    file_obj = request.FILES.get("backup_file")
    if not file_obj:
        messages.error(request, "Debes seleccionar un archivo .zip de respaldo.")
        return redirect("admin_backup")

    try:
        zip_bytes = io.BytesIO(file_obj.read())
        zf = zipfile.ZipFile(zip_bytes)
    except Exception:
        messages.error(request, "El archivo no es un ZIP válido.")
        return redirect("admin_backup")

    loaded_counts = {}
    restored_media_files = 0

    try:
        with transaction.atomic():
            for model_label in BACKUP_MODEL_ORDER:
                data_file = f"data/{_backup_filename(model_label)}"
                if data_file not in zf.namelist():
                    loaded_counts[model_label] = 0
                    continue

                raw_json = zf.read(data_file).decode("utf-8")
                objects = list(serializers.deserialize("json", raw_json))
                for obj in objects:
                    obj.save()

                loaded_counts[model_label] = len(objects)

            media_root = getattr(settings, "MEDIA_ROOT", "")
            if media_root:
                os.makedirs(media_root, exist_ok=True)

                for member in zf.namelist():
                    if not member.startswith("media/") or member.endswith("/"):
                        continue

                    target = _safe_media_target_path(media_root, member)
                    if not target:
                        continue

                    parent = os.path.dirname(target)
                    if parent:
                        os.makedirs(parent, exist_ok=True)

                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())

                    restored_media_files += 1
    except Exception as exc:
        messages.error(request, f"No se pudo importar el respaldo: {exc}")
        return redirect("admin_backup")

    total = sum(loaded_counts.values())
    request.session["backup_last_imported_at"] = timezone.now().strftime("%Y-%m-%d %H:%M")
    messages.success(
        request,
        f"Respaldo importado correctamente. Registros procesados: {total}. Archivos media restaurados: {restored_media_files}."
    )
    return redirect("admin_backup")


# =========================
# ADMIN: NOTIFICATIONS
# =========================

@login_required
def admin_notifications(request):

    if not has_permission(request.user, "notifications.view"):
        return redirect("dashboard")

    notifs = request.user.notifications.order_by("-created_at")
    return render(request, "admin_notifications.html", {"notifs": notifs})


# =========================
# ADMIN: ROLES & PERMISSIONS
# =========================

@login_required
def admin_roles(request):

    if not has_permission(request.user, "roles.view"):
        return redirect("dashboard")

    roles = Role.objects.all().order_by("name")
    permissions = Permission.objects.all().order_by("module", "action")

    modules = defaultdict(list)
    for p in permissions:
        modules[p.module].append(p)

    return render(request, "admin_roles.html", {
        "roles": roles,
        "modules": dict(modules)
    })


@login_required
def edit_role(request, role_id):

    if not has_permission(request.user, "roles.edit"):
        return redirect("dashboard")

    role = get_object_or_404(Role, id=role_id)
    permissions = Permission.objects.all().order_by("module", "action")

    modules = defaultdict(list)
    for p in permissions:
        modules[p.module].append(p)
        
    if request.method == "POST":

            role_name = request.POST.get("role_name")

            if role_name:
                role.name = role_name.upper()

            selected = Permission.objects.filter(
                id__in=request.POST.getlist("permissions")
            )

            role.permissions.set(selected)

            role.save()

            messages.success(
                request,
                "Permisos actualizados correctamente ✅"
            )

            return redirect("admin_roles")

    return render(request, "edit_role.html", {
        "role": role,
        "modules": dict(modules)
    })


@login_required
def create_role(request):

    if not has_permission(request.user, "roles.create"):
        return redirect("dashboard")

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if name:
            Role.objects.create(name=name.upper())
            messages.success(request, "Rol creado ✅")
        return redirect("admin_roles")

    return render(request, "create_role.html")


@login_required
def delete_role(request, role_id):

    if not has_permission(request.user, "roles.delete"):
        return redirect("dashboard")

    role = get_object_or_404(Role, id=role_id)
    role.delete()
    messages.success(request, "Rol eliminado ✅")
    return redirect("admin_roles")

@login_required
def admin_categories(request):

    if not has_permission(request.user, "categories.view"):
        return redirect("dashboard")

    categories = Category.objects.prefetch_related("subcategories").all()

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "create_category":

            name = (request.POST.get("name") or "").strip()
            description = request.POST.get("description") or ""

            if not name:
                messages.error(request, "El nombre de la categoría es obligatorio.")
                return redirect("admin_categories")

            if Category.objects.filter(name__iexact=name).exists():
                messages.error(request, "Ya existe una categoría con ese nombre.")
                return redirect("admin_categories")

            Category.objects.create(
                name=name,
                description=description
            )

        elif action == "create_subcategory":

            category_id = request.POST.get("category_id")
            name = (request.POST.get("subcategory_name") or "").strip()

            if not category_id or not name:
                messages.error(request, "Debe seleccionar categoría y nombre para la subcategoría.")
                return redirect("admin_categories")

            category = get_object_or_404(Category, id=category_id)

            if SubCategory.objects.filter(category=category, name__iexact=name).exists():
                messages.error(request, "Ya existe una subcategoría con ese nombre en la categoría seleccionada.")
                return redirect("admin_categories")

            SubCategory.objects.create(
                category=category,
                name=name
            )

        return redirect("admin_categories")

    return render(request, "admin_categories.html", {
        "categories": categories
    })

@login_required
def reset_user_password(request, user_id):

    if not has_permission(request.user, "users.edit"):
        return redirect("dashboard")

    user = get_object_or_404(User, id=user_id)

    new_password = _generate_password()

    user.set_password(new_password)
    user.save()

    _notify(
        user,
        "Contraseña restablecida",
        f"""
    Hola {user.first_name},

    Tu contraseña fue restablecida por un administrador.

    Nueva contraseña temporal:
    {new_password}

    Debes cambiarla al iniciar sesión.
    """,
        url=request.build_absolute_uri(reverse("login")),
        send_email=True
    )

    messages.success(request, f"Nueva contraseña: {new_password}")

    return redirect("admin_users")


# =========================
# ADMIN: SLA
# =========================

@login_required
def admin_sla(request):

    if not has_permission(request.user, "sla.view"):
        return redirect("dashboard")

    if SLA.objects.count() == 0:
        SLA.objects.create(severity="S1", response_minutes=5, resolution_minutes=30)
        SLA.objects.create(severity="S2", response_minutes=10, resolution_minutes=60)
        SLA.objects.create(severity="S3", response_minutes=20, resolution_minutes=120)

    slas = SLA.objects.all().order_by("severity")

    if request.method == "POST":

        recalculated_count = 0

        for sla in slas:
            r = request.POST.get(f"response_{sla.id}")
            res = request.POST.get(f"resolution_{sla.id}")

            if r and res:
                try:
                    old_response_minutes = sla.response_minutes
                    old_resolution_minutes = sla.resolution_minutes
                    sla.response_minutes = int(r)
                    sla.resolution_minutes = int(res)
                    sla.save()

                    open_tickets = Ticket.objects.filter(
                        severity=sla.severity
                    ).exclude(status="CERRADO")

                    for ticket in open_tickets:
                        _recalculate_running_deadlines(
                            ticket,
                            old_response_minutes,
                            old_resolution_minutes,
                            sla.response_minutes,
                            sla.resolution_minutes,
                        )

                        if not ticket.first_response_due_at or (ticket.resolution_started_at and not ticket.sla_due_at):
                            _recalculate_open_ticket_deadlines(ticket, sla)

                        ticket.save(update_fields=[
                            "first_response_due_at",
                            "sla_due_at",
                            "updated_at",
                        ])
                        recalculated_count += 1
                except ValueError:
                    continue

        messages.success(
            request,
            f"SLA actualizado ✅ Tickets recalculados: {recalculated_count}"
        )
        return redirect("admin_sla")

    return render(request, "admin_sla.html", {"slas": slas})


# =========================
# NOTIFICATION READ
# =========================

@login_required
def notification_read(request, notif_id):

    notif = get_object_or_404(Notification, id=notif_id, user=request.user)
    notif.is_read = True
    notif.save(update_fields=["is_read"])

    if notif.url:
        return redirect(notif.url)

    return redirect("dashboard")

@login_required
def assign_ticket(request, ticket_id):

    ticket = get_object_or_404(Ticket, id=ticket_id)

    if ticket.status == "CERRADO":
        messages.error(request, "No se puede asignar un ticket cerrado.")
        return redirect("ticket_detail", ticket_id=ticket.id)

    if not has_permission(request.user, "tickets.edit"):
        return redirect("dashboard")

    current_level = request.user.profile.support_level

    supports = User.objects.filter(
        profile__role__name__icontains="SOPORTE",
        profile__support_level__gt=current_level
    ).exclude(id=request.user.id).distinct()

    if not ticket.severity:

        messages.error(
            request,
            "Debe asignar severidad antes de asignar el ticket."
        )

        return redirect(
            "ticket_detail",
            ticket_id=ticket.id
        )

    if ticket.status == "CERRADO":
        messages.error(request, "No se puede asignar un ticket cerrado.")
        return redirect("ticket_detail", ticket_id=ticket.id)

    if request.method == "POST":
        user_id = request.POST.get("user_id")

        support = get_object_or_404(
            User,
            id=user_id,
            profile__role__name__icontains="SOPORTE"
        )
    
        
        ticket.assigned_to = support
        ticket.status = "ESPERANDO_CLIENTE"

        _mark_first_response(ticket, request.user)

        if not ticket.resolution_started_at:
            ticket.resolution_started_at = timezone.now()

        _pause_sla(ticket)

        sla = SLA.objects.filter(
            severity=ticket.severity
        ).first()

        if sla and not ticket.sla_due_at:
            ticket.sla_due_at = _add_business_minutes(
                timezone.now(),
                sla.resolution_minutes
            )

        ticket.save()

        _history(
            ticket,
            request.user,
            "status",
            "NUEVO",
            "ESPERANDO_CLIENTE"
        )

        _notify(
            support,
            "Nuevo ticket asignado",
            f"""
        Ticket: {ticket.code}

        Título: {ticket.title}

        Prioridad: {ticket.get_priority_display()}
        Severidad: {ticket.get_severity_display()}

        Has sido asignado al ticket.
        """,
            url=f"/ticket/{ticket.id}/",
            send_email=True,
            cc_emails=["soporte@replica.com.pe"],
        )

        _notify(
            ticket.created_by,
            "Caso asignado al analista de soporte",
            f"""
        Ticket: {ticket.code}

        Estado: {ticket.get_status_display()}
        Prioridad: {ticket.get_priority_display()}
        Severidad: {ticket.get_severity_display()}

        Asignado a:
        {support.get_full_name() or support.username}

        Tu caso ya tiene un analista asignado.
        """,
            url=request.build_absolute_uri(reverse("ticket_detail", args=[ticket.id])),
            send_email=True,
            cc_emails=["soporte@replica.com.pe"],
        )

        messages.success(
            request,
            "Ticket asignado correctamente"
        )

        return redirect(
            "ticket_detail",
            ticket_id=ticket.id
        )
        
    return render(request, "assign_ticket.html", {
            "ticket": ticket,
            "supports": supports
    })

@login_required
def rate_ticket(request, ticket_id):

    ticket = get_object_or_404(Ticket, id=ticket_id)

    if ticket.rating:

        messages.error(
            request,
            "Este ticket ya fue calificado."
        )

        return redirect(
            "ticket_detail",
            ticket_id=ticket.id
        )

    if ticket.status != "CERRADO":
        return redirect("dashboard")

    form = RateTicketForm(
        request.POST or None,
        instance=ticket
    )

    if request.method == "POST" and form.is_valid():

        ticket = form.save()

        # NOTIFICAR SOPORTE

        if ticket.assigned_to:

            _notify(
                ticket.assigned_to,
                "Ticket calificado",
                f"""
Ticket:
{ticket.code}

Calificación:
{ticket.rating}/5

Comentario:
{ticket.rating_comment}
                """,
                url=f"/ticket/{ticket.id}/"
            )

        # NOTIFICAR ADMINS

        admins = User.objects.filter(
            profile__role__name="ADMINISTRADOR"
        )

        for admin in admins:

            _notify(
                admin,
                "Ticket calificado",
                f"""
Ticket:
{ticket.code}

Calificación:
{ticket.rating}/5

Comentario:
{ticket.rating_comment}
                """,
                url=f"/ticket/{ticket.id}/"
            )

        messages.success(
            request,
            "Gracias por tu calificación ⭐"
        )

        return redirect(
            "ticket_detail",
            ticket_id=ticket.id
        )

    return render(request, "rate_ticket.html", {
        "form": form,
        "ticket": ticket
    })    

@login_required
def get_subcategories(request, category_id):

    subs = SubCategory.objects.filter(category_id=category_id)

    data = [
        {
            "id": s.id,
            "name": s.name,
            "requires_file": s.requires_file
        }
        for s in subs
    ]

    return JsonResponse(data, safe=False)



def _generate_password(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


@login_required
def change_password(request):

    if request.method == "POST":
        password = request.POST.get("password")
        confirm = request.POST.get("confirm")

        if not password or not confirm:
            messages.error(request, "Debes completar ambos campos de contraseña.")
            return render(request, "change_password.html")

        if password != confirm:
            messages.error(request, "Las contraseñas no coinciden")
            return render(request, "change_password.html")

        if len(password) < 8:
            messages.error(request, "Debe tener al menos 8 caracteres")
            return render(request, "change_password.html")

        if not any(c.isupper() for c in password):
            messages.error(request, "Debe tener una mayúscula")
            return render(request, "change_password.html")

        if not any(c.isdigit() for c in password):
            messages.error(request, "Debe tener un número")
            return render(request, "change_password.html")

        request.user.set_password(password)
        request.user.save()

        request.user.profile.must_change_password = False
        request.user.profile.save()

        messages.success(request, "Contraseña actualizada")

        return redirect("login")

    return render(request, "change_password.html")

@login_required
def view_attachment(request, attachment_id):

    attachment = get_object_or_404(
        TicketAttachment,
        id=attachment_id
    )

    ticket = attachment.ticket

    role = _role(request.user)

    # CLIENTE
    if role == "CLIENTE":
        if ticket.created_by != request.user:
            raise Http404()

    # SOPORTE
    elif role == "SOPORTE":
        if (
            ticket.assigned_to
            and ticket.assigned_to != request.user
        ):
            raise Http404()

    # ADMINISTRADOR puede ver todo

    return FileResponse(
        attachment.file.open("rb"),
        content_type="application/octet-stream"
    )
