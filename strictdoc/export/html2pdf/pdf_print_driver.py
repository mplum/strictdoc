# mypy: disable-error-code="no-untyped-call"
import sys
from subprocess import CompletedProcess, TimeoutExpired, run

from strictdoc import environment
from strictdoc.helpers.timing import measure_performance


class PDFPrintDriver:
    @staticmethod
    def get_pdf_from_html(paths_to_print: str):
        assert isinstance(paths_to_print, str)
        with measure_performance(
            "PDFPrintDriver: printing HTML to PDF using HTML2PDF and Chrome Driver"
        ):
            try:
                _: CompletedProcess = run(
                    [
                        # Using sys.executable instead of "python" is important because
                        # venv subprocess call to python resolves to wrong interpreter,
                        # https://github.com/python/cpython/issues/86207
                        sys.executable,
                        environment.get_path_to_html2pdf(),
                        paths_to_print,
                    ],
                    capture_output=False,
                    check=False,
                )
            except TimeoutExpired:
                raise TimeoutError from None
