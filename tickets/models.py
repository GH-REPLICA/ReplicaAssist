from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

# =====================================================
# EMPRESAS (multiempresa)
# =====================================================

class Company(models.Model):

    name = models.CharField(max_length=200, unique=True)

    ruc = models.CharField(max_length=20, unique=True)

    email = models.EmailField(blank=True, default="")

    phone = models.CharField(max_length=20, blank=True, default="")

    address = models.CharField(max_length=255, blank=True, default="")

    # SLA por empresa
    sla_hours_response = models.IntegerField(default=8)

    sla_hours_resolution = models.IntegerField(default=48)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# =====================================================
# PERMISOS
# =====================================================

class Permission(models.Model):

    MODULES = [
        ("dashboard","Dashboard"),
        ("tickets","Tickets"),
        ("users","Usuarios"),
        ("companies","Empresas"),
        ("support","Soporte"),
        ("notifications","Notificaciones"),
        ("categories","Categorías"),
        ("sla","SLA"),
        ("roles","Roles"),
    ]

    ACTIONS = [
        ("view","Ver"),
        ("view_all","Ver todos"),
        ("create","Crear"),
        ("edit","Editar"),
        ("delete","Eliminar"),
    ]

    module = models.CharField(max_length=50, choices=MODULES)
    action = models.CharField(max_length=50, choices=ACTIONS)

    def __str__(self):
        return f"{self.module}:{self.action}"


# =====================================================
# ROLES
# =====================================================

class Role(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    permissions = models.ManyToManyField(
        Permission,
        blank=True
    )

    def __str__(self):
        return self.name

# =====================================================
# PERFIL DE USUARIO
# =====================================================

class Profile(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    
    phone = models.CharField(
        max_length=20,
        blank=True,
        default=""
    )

    support_level = models.PositiveSmallIntegerField(
        default=1
    )

    must_change_password = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username}"


# =====================================================
# CATEGORÍAS DE TICKETS
# =====================================================

class Category(models.Model):

    name = models.CharField(max_length=100, unique=True)

    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

# =====================================================
# TICKETS
# =====================================================

class Ticket(models.Model):


    STATUS_CHOICES = [
    ("NUEVO", "Nuevo"),
    ("EN_PROCESO", "En proceso"),
    ("ESPERANDO_CLIENTE", "Esperando cliente"),
    ("ESPERANDO_SOPORTE", "Esperando soporte"),
    ("CERRADO", "Cerrado"),
    ]

    PRIORITY_CHOICES = [
        ("LOW", "Baja"),
        ("MEDIUM", "Media"),
        ("HIGH", "Alta"),
    ]

    SEVERITY_CHOICES = [
        ("S1", "Crítico"),
        ("S2", "Alto"),
        ("S3", "Medio"),
    ]

    code = models.CharField(max_length=20, unique=True)

    title = models.CharField(max_length=200)

    description = models.TextField()

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    
    subcategory = models.ForeignKey('SubCategory', on_delete=models.SET_NULL, null=True, blank=True)

    brand = models.ForeignKey('Brand', on_delete=models.SET_NULL, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="NUEVO")

    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="MEDIUM")

    severity = models.CharField(max_length=2, choices=SEVERITY_CHOICES,null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tickets_created")

    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets_assigned")

    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    
    updated_at = models.DateTimeField(
        auto_now=True
    )

    # SLA
    first_response_due_at = models.DateTimeField(null=True, blank=True)

    sla_due_at = models.DateTimeField(null=True, blank=True)

    first_responded_at = models.DateTimeField(null=True, blank=True)

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_started_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    sla_paused = models.BooleanField(default=False)
    sla_pause_started_at = models.DateTimeField(null=True, blank=True)

    rating = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5)
        ]
    )
    
    rating_comment = models.TextField(
        blank=True,
        default=""
    )
    
    escalated = models.BooleanField(default=False)

    escalated_at = models.DateTimeField(
        null=True,
        blank=True
    )

    escalated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets_escalated"
    ) 
    def __str__(self):
        return self.code

    @property
    def is_sla_breached(self):

        if self.status == "CERRADO":
            return False

        if not self.sla_due_at:
            return False

        check_time = timezone.now()
        if self.sla_paused and self.sla_pause_started_at:
            check_time = self.sla_pause_started_at

        if check_time > self.sla_due_at:
            return True

        return False


    @property
    def is_first_response_breached(self):

        if self.first_responded_at:
            if self.first_response_due_at and self.first_responded_at > self.first_response_due_at:
                return True
            return False

        if not self.first_response_due_at:
            return False

        check_time = timezone.now()
        if self.sla_paused and self.sla_pause_started_at:
            check_time = self.sla_pause_started_at

        if check_time > self.first_response_due_at:
            return True

        return False
    
    def first_response_status(self):

        if self.first_responded_at:
            if self.first_response_due_at and self.first_responded_at > self.first_response_due_at:
                return "VENCIDO"
            return "OK"

        if not self.first_response_due_at:
            return "PENDIENTE"

        check_time = timezone.now()
        if self.sla_paused and self.sla_pause_started_at:
            check_time = self.sla_pause_started_at

        if check_time > self.first_response_due_at:
            return "VENCIDO"

        if self.sla_paused:
            return "PAUSADO"

        return "PENDIENTE"

    class Meta:
            ordering = ["-created_at"]
            
            indexes = [
                models.Index(fields=["status"]),
                models.Index(fields=["priority"]),
                models.Index(fields=["severity"]),
                models.Index(fields=["created_at"]),
            ]

# =====================================================
# MENSAJES DEL TICKET
# =====================================================

class TicketMessage(models.Model):

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")

    author = models.ForeignKey(User, on_delete=models.CASCADE)

    message = models.TextField(blank=True)

    is_internal = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Mensaje {self.id} - {self.ticket.code}"


# =====================================================
# ARCHIVOS ADJUNTOS
# =====================================================

class TicketAttachment(models.Model):

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="attachments"
    )

    message = models.ForeignKey(
        TicketMessage,
        on_delete=models.CASCADE,
        related_name="files",
        null=True,
        blank=True
    )

    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)

    file = models.FileField(upload_to="ticket_files/")

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Archivo {self.id} - {self.ticket.code}"


# =====================================================
# HISTORIAL DE CAMBIOS
# =====================================================

class TicketHistory(models.Model):

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="history")

    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    field = models.CharField(max_length=100)
    
    old_value = models.CharField(max_length=255, blank=True, default="")

    new_value = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.ticket.code} {self.field}"


# =====================================================
# NOTIFICACIONES
# =====================================================

class Notification(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    title = models.CharField(max_length=120)

    message = models.CharField(max_length=255, blank=True, default="")

    url = models.CharField(max_length=255, blank=True, default="")

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notif {self.user.username}"
# =====================================================
# SLA
# =====================================================

class SLA(models.Model):

    severity = models.CharField(
        max_length=2,
        choices=Ticket.SEVERITY_CHOICES,
        unique=True
    )
    
    response_minutes = models.IntegerField()

    resolution_minutes = models.IntegerField()

    def __str__(self):
        return f"SLA {self.severity}"
    

class SubCategory(models.Model):

    class Meta:
        unique_together = ("category", "name")
    
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="subcategories"
    )

    name = models.CharField(max_length=100)

    description = models.TextField(blank=True)

    requires_file = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.category.name} - {self.name}"

    
class Brand(models.Model):

    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name