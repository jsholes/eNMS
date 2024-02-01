from sqlalchemy import Boolean, Float, ForeignKey, Integer
from wtforms.widgets import TextArea

from eNMS.database import db
from eNMS.fields import BooleanField, HiddenField, StringField
from eNMS.forms import NetmikoForm
from eNMS.models.automation import ConnectionService


class NetmikoConfigurationService(ConnectionService):
    __tablename__ = "netmiko_configuration_service"
    pretty_name = "Netmiko Configuration"
    parent_type = "connection_service"
    id = db.Column(Integer, ForeignKey("connection_service.id"), primary_key=True)
    content = db.Column(db.LargeString)
    enable_mode = db.Column(Boolean, default=True)
    config_mode = db.Column(Boolean, default=False)
    driver = db.Column(db.SmallString)
    read_timeout = db.Column(Float, default=10.0)
    conn_timeout = db.Column(Float, default=10.0)
    auth_timeout = db.Column(Float, default=0.0)
    banner_timeout = db.Column(Float, default=15.0)
    fast_cli = db.Column(Boolean, default=False)
    global_delay_factor = db.Column(Float, default=1.0)
    commit_configuration = db.Column(Boolean, default=False)
    exit_config_mode = db.Column(Boolean, default=True)
    strip_prompt = db.Column(Boolean, default=False)
    strip_command = db.Column(Boolean, default=False)
    config_mode_command = db.Column(db.SmallString)

    __mapper_args__ = {"polymorphic_identity": "netmiko_configuration_service"}

    def job(self, run, device):
        netmiko_connection = run.netmiko_connection(device)
        config = run.sub(run.content, locals())
        run.log(
            "info",
            "Pushing Configuration with Netmiko",
            device,
            logger="security",
        )
        netmiko_connection.send_config_set(
            config.splitlines(),
            enter_config_mode=run.config_mode,
            exit_config_mode=False,
            read_timeout=run.read_timeout,
            strip_prompt=run.strip_prompt,
            strip_command=run.strip_command,
            config_mode_command=run.config_mode_command,
            cmd_verify=False,
        )
        if run.commit_configuration:
            netmiko_connection.commit()
        if run.exit_config_mode:
            netmiko_connection.exit_config_mode()
        return {"success": True, "result": f"configuration OK {config}"}


class NetmikoConfigurationForm(NetmikoForm):
    form_type = HiddenField(default="netmiko_configuration_service")
    config_mode = BooleanField("Config mode", default=True)
    content = StringField(widget=TextArea(), render_kw={"rows": 5}, substitution=True)
    commit_configuration = BooleanField()
    exit_config_mode = BooleanField(default=True)
    strip_prompt = BooleanField()
    strip_command = BooleanField()
    config_mode_command = StringField(help="netmiko/config_mode_command")
    groups = {
        "Main Parameters": {
            "commands": [
                "content",
                "commit_configuration",
                "exit_config_mode",
                "config_mode_command",
            ],
            "default": "expanded",
        },
        **NetmikoForm.groups,
        "Advanced Netmiko Parameters": {
            "commands": ["strip_prompt", "strip_command"],
            "default": "hidden",
        },
    }
