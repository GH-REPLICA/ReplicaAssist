import os
import time

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import Ticket, Company, Profile, TicketMessage, Role, SubCategory

BLOCKED_FILE_EXTENSIONS = [
    ".exe", ".bat", ".cmd", ".js", ".msi", ".scr",
    ".pif", ".sh", ".php", ".jar"
]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def validate_attachment(file):
    if not file:
        return file

    if file.size > MAX_FILE_SIZE:
        raise forms.ValidationError(
            "El archivo supera el tamaño máximo permitido de 10 MB."
        )

    ext = os.path.splitext(file.name)[1].lower()
    if ext in BLOCKED_FILE_EXTENSIONS:
        raise forms.ValidationError(
            "Tipo de archivo no permitido. Por seguridad no se aceptan archivos ejecutables ni scripts."
        )

    return file


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "Usuario"
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "input",
            "placeholder": "Contraseña"
        })
    )

    captcha = forms.CharField(
        required=True,
        widget=forms.HiddenInput()
    )

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        self.request = request
        super().__init__(request=request, *args, **kwargs)

        if self.request is not None:
            question = self.request.session.get(
                "login_captcha_question",
                "Selecciona el ícono indicado"
            )
            self.fields["captcha"].label = question

    def clean_captcha(self):
        value = self.cleaned_data.get("captcha", "").strip()

        if not value:
            raise forms.ValidationError(
                "Selecciona un ícono para validar el acceso."
            )

        if not self.request:
            raise forms.ValidationError(
                "Error interno de validación. Intenta de nuevo."
            )

        created_at = self.request.session.get("login_captcha_created_at")
        try:
            if not created_at or (time.time() - float(created_at)) > 600:
                raise forms.ValidationError(
                    "La verificación expiró. Selecciona un nuevo ícono e inténtalo otra vez."
                )
        except (TypeError, ValueError):
            raise forms.ValidationError(
                "La verificación expiró. Selecciona un nuevo ícono e inténtalo otra vez."
            )

        answer = str(self.request.session.get("login_captcha_answer", ""))
        if not answer or value != answer:
            raise forms.ValidationError(
                "La verificación de seguridad no es correcta. Intenta de nuevo."
            )

        return value

    def clean(self):
        # Do not run credential authentication while captcha is invalid.
        if self.errors.get("captcha"):
            return self.cleaned_data

        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password
            )

            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages["invalid_login"],
                    code="invalid_login",
                    params={"username": self.username_field.verbose_name},
                )

            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data
    
class TicketForm(forms.ModelForm):
    file = forms.FileField(
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "input"})
    )

    class Meta:
        model = Ticket
        fields = ["title", "description", "category", "subcategory", "priority", "severity"]

        widgets = {
            "title": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 5}),
            "priority": forms.Select(attrs={"class": "input"}),
            "severity": forms.Select(attrs={"class": "input"}),
            "category": forms.Select(attrs={"class": "input"}),
            "subcategory": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)   

        # Enforce required fields explicitly for create-ticket UX and backend consistency.
        self.fields["title"].required = True
        self.fields["description"].required = True
        self.fields["category"].required = True


        self.fields["subcategory"].queryset = SubCategory.objects.none()
        self.fields["subcategory"].required = True



        if "category" in self.data:
            try:
                category_id = int(self.data.get("category"))
                self.fields["subcategory"].queryset = SubCategory.objects.filter(category_id=category_id)
            except ValueError:
                pass
        elif self.instance.pk and self.instance.category:
            self.fields["subcategory"].queryset = self.instance.category.subcategories.all()

        if self.user:
            role_name = getattr(getattr(self.user, "profile", None), "role", None)
            role_name = getattr(role_name, "name", "")

            if role_name == "CLIENTE":
                self.fields.pop("priority", None)
                self.fields.pop("severity", None)
            else:
                if "priority" in self.fields:
                    self.fields["priority"].required = True
                if "severity" in self.fields:
                    self.fields["severity"].required = True

    def clean_title(self):
        value = (self.cleaned_data.get("title") or "").strip()
        if not value:
            raise forms.ValidationError("Debe ingresar un título.")
        return value

    def clean_description(self):
        value = (self.cleaned_data.get("description") or "").strip()
        if not value:
            raise forms.ValidationError("Debe ingresar una descripción.")
        return value

    def clean(self):
        cleaned_data = super().clean()

        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")

        if not category:
            raise forms.ValidationError("Debe seleccionar una categoría")

        if not subcategory:
            raise forms.ValidationError("Debe seleccionar una subcategoría")

        if subcategory and category and subcategory.category != category:
            raise forms.ValidationError("La subcategoría no pertenece a la categoría seleccionada")

        file = cleaned_data.get("file")
        if not file:
            raise forms.ValidationError("Debe adjuntar evidencia.")

        validate_attachment(file)

        return cleaned_data


class UpdateTicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["status"]

        widgets = {
            "status": forms.Select(attrs={"class": "input"}),
        }


class RateTicketForm(forms.ModelForm):

    def clean_rating_comment(self):

                value = self.cleaned_data.get(
                    "rating_comment"
                )

                if not value or not value.strip():

                    raise forms.ValidationError(
                        "Debe ingresar un comentario."
                    )

                return value

    class Meta:

        model = Ticket

        fields = [
            "rating",
            "rating_comment"
        ]

        widgets = {

            "rating": forms.Select(
                choices=[
                    (5,"⭐⭐⭐⭐⭐ Excelente"),
                    (4,"⭐⭐⭐⭐ Bueno"),
                    (3,"⭐⭐⭐ Regular"),
                    (2,"⭐⭐ Malo"),
                    (1,"⭐ Muy malo"),
                ],
                attrs={"class":"input"}
            ),

            "rating_comment": forms.Textarea(
                attrs={
                    "class":"input",
                    "placeholder":"Cuéntanos cómo fue la atención...",
                    "required":True,
                    "rows":5
                }
            )
        }

class CompanyForm(forms.ModelForm):
        class Meta:
            model = Company
            fields = [
                "name",
                "ruc",
                "email",
                "phone",
                "address",
            ]

            widgets = {
                "name": forms.TextInput(attrs={"class": "input", "placeholder": "Nombre de empresa"}),
                "ruc": forms.TextInput(attrs={"class": "input", "placeholder": "RUC"}),
                "email": forms.EmailInput(attrs={"class": "input", "placeholder": "Email"}),
                "phone": forms.TextInput(attrs={"class": "input", "placeholder": "Teléfono"}),
                "address": forms.TextInput(attrs={"class": "input", "placeholder": "Dirección"}),
            }
        
        def clean_name(self):

            value = self.cleaned_data["name"]

            if not value.strip():
                raise forms.ValidationError(
                    "El nombre es obligatorio."
                )
    
            return value


        def clean_ruc(self):

            value = self.cleaned_data["ruc"]

            if not value.strip():
                raise forms.ValidationError(
                    "El RUC es obligatorio."
                )

            if len(value) != 11:
                raise forms.ValidationError(
                    "El RUC debe tener 11 dígitos."
                )

            if not value.isdigit():
                raise forms.ValidationError(
                    "El RUC solo debe contener números."
                )

            return value


        def clean_email(self):

            value = self.cleaned_data["email"]

            if not value.strip():
                raise forms.ValidationError(
                    "El correo es obligatorio."
                )

            return value


        def clean_phone(self):

            value = self.cleaned_data["phone"]

            if not value.strip():
                raise forms.ValidationError(
                    "El teléfono es obligatorio."
                )

            return value


        def clean_address(self):

            value = self.cleaned_data["address"]

            if not value.strip():
                raise forms.ValidationError(
                    "La dirección es obligatoria."
                )

            return value


class AdminUserCreateForm(forms.Form):

    login_email = forms.EmailField(
    widget=forms.EmailInput(attrs={"class": "input", "placeholder": "Correo (será también usuario)"})
    )
    
    first_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Nombres"})
    )
    last_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "Apellidos"})
    )
    phone = forms.CharField(
        required=False,
        label="Celular",
        widget=forms.TextInput(attrs={
            "class": "input",
            "placeholder": "Ej. 999999999"
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Contraseña"})
    )

    # 👇 IMPORTANTÍSIMO: no uses Role.objects.all() directo aquí (rompe migraciones si tabla no existe)
    role = forms.ModelChoiceField(
        queryset=Role.objects.none(),
        widget=forms.Select(attrs={"class": "input"})
    )

    company = forms.ModelChoiceField(
        queryset=Company.objects.none(),
        required=False,
        empty_label="---------",
        widget=forms.Select(attrs={"class": "input"})
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.all().order_by("name")
        self.fields["company"].queryset = (
            Company.objects
            .all()
            .order_by("name")
        )


class AdminUserRoleForm(forms.Form):
    role = forms.ModelChoiceField(
        queryset=Role.objects.none(),
        widget=forms.Select(attrs={"class": "input"})
    )

    company = forms.ModelChoiceField(
        queryset=Company.objects.none(),
        required=False,
        empty_label="---------",
        widget=forms.Select(attrs={"class": "input"})
    )
    
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "input"
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = Role.objects.all().order_by("name")
        self.fields["company"].queryset = Company.objects.all().order_by("name")


class MessageForm(forms.ModelForm):
    # ✅ Adjuntar archivo como parte del envío (estilo chat)
    file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "input"}),
    )

    def clean_file(self):
        file = self.cleaned_data.get("file")
        return validate_attachment(file)

    def clean(self):

        cleaned_data = super().clean()

        message = cleaned_data.get("message")
        file = cleaned_data.get("file")

        if not message and not file:
            raise forms.ValidationError(
                "Debe escribir un mensaje o adjuntar un archivo."
            )

        return cleaned_data

    class Meta:
        model = TicketMessage
        fields = ["message"]

        widgets = {
            "message": forms.Textarea(attrs={
                "class": "input",
                "placeholder": "Escribe un mensaje...",
                "rows": 4
            }),
        }