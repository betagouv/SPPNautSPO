from django import forms


class UploadFileForm(forms.Form):
    file = forms.FileField()


class UploadDirectoryFileForm(forms.Form):
    file = forms.FileField()
    webkitRelativePath = forms.CharField()
