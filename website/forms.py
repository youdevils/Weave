from django import forms


class ContactForm(forms.Form):
    """
    The public contact / feedback form.

    This slice is a stub: a valid submission shows a success state and nothing
    else happens to it. It is never logged, stored or sent anywhere.
    """

    name = forms.CharField(max_length=100, strip=True)
    email = forms.EmailField(max_length=254)
    message = forms.CharField(max_length=5000, strip=True, widget=forms.Textarea)
