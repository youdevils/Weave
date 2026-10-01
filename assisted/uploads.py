"""
Upload handling that enforces a per-file size limit on the bytes actually
received. Duplicated from ingestion.uploads.LimitedUploadHandler (not
imported) to keep assisted/workspace from taking on a new cross-app
dependency on ingestion for a stateless, self-contained utility class.

A declared Content-Length is only a hint (a request can be chunked, omit it
or misstate it), so the limit is applied as the body streams in: once the
running total for the file currently being read passes the limit, that file
is discarded and never buffered, no matter what the client claimed.
"""

from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.uploadhandler import FileUploadHandler, SkipFile


class LimitedUploadHandler(FileUploadHandler):
    """
    Buffers each uploaded file in memory, up to ``max_bytes`` per file. If a
    file is bigger the remainder is read and thrown away and ``too_large`` is
    set; that file is not produced. ``new_file`` resets the per-file counter,
    so one handler instance correctly enforces the limit across multiple
    files in the same multipart request.
    """

    def __init__(self, request=None, *, max_bytes):
        super().__init__(request)
        self.max_bytes = max_bytes
        self.too_large = False
        self._buffer = None
        self._received = 0

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self._buffer = BytesIO()
        self._received = 0

    def receive_data_chunk(self, raw_data, start):
        self._received += len(raw_data)

        if self._received > self.max_bytes:
            self.too_large = True
            self._buffer = None
            raise SkipFile()

        self._buffer.write(raw_data)

        # Consumed: nothing later in the handler chain should see this chunk.
        return None

    def file_complete(self, file_size):
        if self.too_large or self._buffer is None:
            return None

        self._buffer.seek(0)

        return InMemoryUploadedFile(
            file=self._buffer,
            field_name=self.field_name,
            name=self.file_name,
            content_type=self.content_type,
            size=file_size,
            charset=self.charset,
            content_type_extra=self.content_type_extra,
        )
