from django import forms


class ContactForm(forms.Form):
    """
    The public contact / feedback form.

    A valid submission is emailed to WEBSITE_CONTACT_FORM_RECIPIENT via the
    existing Resend integration; it is not stored.
    """

    name = forms.CharField(max_length=100, strip=True)
    email = forms.EmailField(max_length=254)
    message = forms.CharField(max_length=5000, strip=True, widget=forms.Textarea)
