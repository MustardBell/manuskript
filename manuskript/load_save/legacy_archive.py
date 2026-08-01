import os
import tempfile
import zipfile


class LegacyArchiveError(OSError):
    pass


class LegacyArchiveReadError(LegacyArchiveError):
    pass


class LegacyArchiveWriteError(LegacyArchiveError):
    pass


class Version0ProjectArchive:
    """Read and atomically replace legacy single-file zip projects."""

    COMPRESSION = (
        zipfile.ZIP_DEFLATED
        if getattr(zipfile, "zlib", None) is not None
        else zipfile.ZIP_STORED
    )

    def read(self, project_file):
        files = {}
        try:
            with zipfile.ZipFile(project_file) as archive:
                for member in archive.namelist():
                    if member.endswith("/"):
                        continue
                    files[os.path.normpath(member)] = archive.read(
                        member
                    )
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            raise LegacyArchiveReadError(
                "Cannot read legacy project {}: {}".format(
                    project_file,
                    error,
                )
            ) from error
        return files

    def write(self, project_file, files):
        parent = os.path.dirname(os.path.abspath(project_file))
        temporary_file = None
        try:
            file_descriptor, temporary_file = tempfile.mkstemp(
                prefix=".manuskript-legacy-",
                suffix=".tmp",
                dir=parent,
            )
            os.close(file_descriptor)
            with zipfile.ZipFile(temporary_file, mode="w") as archive:
                for content, filename in files:
                    archive.writestr(
                        filename,
                        content,
                        compress_type=self.COMPRESSION,
                    )
            os.replace(temporary_file, project_file)
            temporary_file = None
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            raise LegacyArchiveWriteError(
                "Cannot save legacy project {}: {}".format(
                    project_file,
                    error,
                )
            ) from error
        finally:
            if temporary_file is not None:
                try:
                    os.remove(temporary_file)
                except FileNotFoundError:
                    pass
