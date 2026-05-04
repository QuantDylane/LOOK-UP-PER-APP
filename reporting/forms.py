from django import forms
from django.contrib.auth import get_user_model


class ProfileForm(forms.ModelForm):
    """Edition des informations de profil du compte connecte."""

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Prenom",
            "last_name": "Nom",
            "email": "E-mail",
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("L'adresse e-mail est obligatoire.")

        qs = get_user_model().objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Cette adresse e-mail est deja utilisee par un autre compte.")
        return email
