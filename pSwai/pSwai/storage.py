from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class VersionedStaticFilesStorage(ManifestStaticFilesStorage):
    """ManifestStaticFilesStorage that uses the versioned names (styles.3f2a9c1d.css) also with DEBUG on.

    Django's own class falls back to the plain names while DEBUG is on, so a browser could keep an old css
    in development, which is where the files change. Docker runs collectstatic on every start.
    """

    def url(self, name, force=False):
        return super().url(name, force=True)
