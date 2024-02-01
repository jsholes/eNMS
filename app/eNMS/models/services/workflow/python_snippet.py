from sqlalchemy import ForeignKey, Integer
from traceback import extract_tb, format_exc
from wtforms.widgets import TextArea

from eNMS.database import db
from eNMS.forms import ServiceForm
from eNMS.fields import HiddenField, StringField
from eNMS.models.automation import Service


class PythonSnippetService(Service):
    __tablename__ = "python_snippet_service"
    pretty_name = "Python Snippet"

    id = db.Column(Integer, ForeignKey("service.id"), primary_key=True)
    source_code = db.Column(db.LargeString)

    __mapper_args__ = {"polymorphic_identity": "python_snippet_service"}

    def job(self, run, device=None):
        try:
            code_object = compile(run.source_code, "user_python_code", "exec")
        except Exception as exc:
            run.log("info", f"Compile error: {str(exc)}")
            return {"success": False, "result": {"step": "compile", "error": str(exc)}}
        results = {}

        def save_result(success, result, **kwargs):
            results.update({"success": success, "result": result, **kwargs})
            if kwargs.get("exit"):
                raise SystemExit()

        globals = {
            "results": results,
            "save_result": save_result,
            **run.global_variables(**locals()),
        }

        try:
            exec(code_object, globals)
        except SystemExit:
            pass
        except Exception as exc:
            line_number = extract_tb(exc.__traceback__)[-1][1]
            run.log("info", f"Execution error(line {line_number}): {str(exc)}")
            return {
                "success": False,
                "result": {
                    "step": "execute",
                    "error": str(exc),
                    "result": results,
                    "traceback": format_exc(),
                },
            }

        if not results:
            run.log("info", "Error: Result not set by user code on service instance")
            results = {
                "success": False,
                "result": {"error": "Result not set by user code on service instance"},
            }

        return results


class PythonSnippetForm(ServiceForm):
    form_type = HiddenField(default="python_snippet_service")
    source_code = StringField(
        type="code",
        python=True,
        widget=TextArea(),
        render_kw={"rows": 15, "help": "python_snippet/source_code"},
        default="""
# Click on "i" to right of "Source Code" for examples.

result = {}
results["success"] = True
results["result"] = result""",
    )
