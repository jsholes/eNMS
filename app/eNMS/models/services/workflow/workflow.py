from collections import defaultdict
from heapq import heappop, heappush
from sqlalchemy import Boolean, ForeignKey, Integer
from sqlalchemy.orm import backref, relationship
from sqlalchemy.schema import UniqueConstraint
from wtforms.validators import NumberRange

from eNMS.database import db
from eNMS.models.base import AbstractBase
from eNMS.forms import ServiceForm
from eNMS.fields import (
    BooleanField,
    HiddenField,
    InstanceField,
    IntegerField,
    SelectField,
)
from eNMS.models.automation import Service
from eNMS.runner import Runner
from eNMS.variables import vs


class Workflow(Service):
    __tablename__ = "workflow"
    pretty_name = "Workflow"
    parent_type = "service"
    id = db.Column(Integer, ForeignKey("service.id"), primary_key=True)
    category = db.Column(db.SmallString)
    close_connection = db.Column(Boolean, default=False)
    labels = db.Column(db.Dict, info={"log_change": False})
    man_minutes_type = db.Column(db.TinyString, default="workflow")
    man_minutes = db.Column(Integer, default=0)
    man_minutes_total = db.Column(Integer, default=0)
    services = relationship(
        "Service",
        secondary=db.service_workflow_table,
        back_populates="workflows",
        lazy="joined",
    )
    edges = relationship(
        "WorkflowEdge",
        back_populates="workflow",
        cascade="all, delete-orphan",
        lazy="joined",
    )
    superworkflow_id = db.Column(
        Integer, ForeignKey("workflow.id", ondelete="SET NULL")
    )
    superworkflow = relationship(
        "Workflow", remote_side=[id], foreign_keys="Workflow.superworkflow_id"
    )

    __mapper_args__ = {"polymorphic_identity": "workflow"}

    def __init__(self, **kwargs):
        migration_import = kwargs.get("migration_import", False)
        if not migration_import:
            start = db.fetch("service", scoped_name="Start", rbac=None)
            end = db.fetch("service", scoped_name="End", rbac=None)
            self.services.extend([start, end])
        super().__init__(**kwargs)
        if not migration_import and self.name not in end.positions:
            end.positions[self.name] = (500, 0)

    def recursive_update(self):
        def rec(service):
            service.post_update()
            if service.type == "workflow":
                for subservice in service.services:
                    rec(subservice)

        rec(self)

    def delete(self):
        for service in self.services:
            if not service.shared:
                db.delete_instance(service)
        super().delete()

    def set_name(self, name=None):
        old_name = self.name
        super().set_name(name)
        for service in self.services:
            if not service.shared:
                service.set_name()
            if old_name in service.positions:
                service.positions[self.name] = service.positions[old_name]
        for edge in self.edges:
            edge.name.replace(old_name, self.name)

    def duplicate(self, workflow=None, clone=None):
        if not clone:
            clone = super().duplicate(workflow)
        clone.labels = self.labels
        clone_services = {}
        db.session.commit()
        for service in self.services:
            if service.shared:
                service_clone = service
                if service not in clone.services:
                    clone.services.append(service)
            else:
                service_clone = service.duplicate(clone)
            service_clone.positions[clone.name] = service.positions.get(
                self.name, (0, 0)
            )
            service_clone.skip[clone.name] = service.skip.get(self.name, False)
            clone_services[service.id] = service_clone
        db.session.commit()
        for edge in self.edges:
            clone.edges.append(
                db.factory(
                    "workflow_edge",
                    rbac=None,
                    **{
                        "workflow": clone.id,
                        "subtype": edge.subtype,
                        "source": clone_services[edge.source.id].id,
                        "destination": clone_services[edge.destination.id].id,
                    },
                )
            )
            db.session.commit()
        clone.recursive_update()
        return clone

    @property
    def deep_services(self):
        services = [
            service.deep_services if service.type == "workflow" else [service]
            for service in self.services
        ]
        return [self] + sum(services, [])

    @property
    def deep_edges(self):
        edges = [
            workflow.edges
            for workflow in set(self.deep_services)
            if workflow.type == "workflow"
        ]
        return sum(edges, [])

    def job(self, run, device=None):
        number_of_runs = defaultdict(int)
        start = db.fetch("service", scoped_name="Start", rbac=None)
        end = db.fetch("service", scoped_name="End", rbac=None)
        services, targets = [], defaultdict(set)
        start_targets = [device] if device else run.target_devices
        for service_id in run.start_services or [start.id]:
            service = db.fetch("service", id=service_id, rbac=None)
            targets[service.name] |= {device.name for device in start_targets}
            heappush(services, (1 / service.priority, service))
        visited, restart_run = set(), run.restart_run
        tracking_bfs = run.run_method == "per_service_with_workflow_targets"
        device_store = {device.name: device for device in start_targets}
        while services:
            if run.stop:
                return {"success": False, "result": "Aborted"}
            _, service = heappop(services)
            if number_of_runs[service.name] >= service.maximum_runs:
                continue
            number_of_runs[service.name] += 1
            visited.add(service)
            if service in (start, end) or service.skip.get(self.name, False):
                success = service.skip_value == "success"
                results = {"result": "skipped", "success": success}
                if tracking_bfs or device:
                    results["summary"] = {
                        "success": targets[service.name],
                        "failure": [],
                    }
            else:
                kwargs = {
                    "service": run.placeholder
                    if service.scoped_name == "Placeholder"
                    else service,
                    "workflow": self,
                    "restart_run": restart_run,
                    "parent": run,
                    "parent_runtime": run.parent_runtime,
                    "workflow_run_method": run.run_method,
                }
                if tracking_bfs or device:
                    kwargs["target_devices"] = []
                    for name in targets[service.name]:
                        if name not in device_store:
                            device_store[name] = db.fetch("device", name=name)
                        kwargs["target_devices"].append(device_store[name])
                if run.parent_device:
                    kwargs["parent_device"] = run.parent_device
                results = Runner(run, payload=run.payload, **kwargs).results
                if not results:
                    continue
            status = "success" if results["success"] else "failure"
            summary = results.get("summary", {})
            if not tracking_bfs and not device:
                run.write_state(f"progress/service/{status}", 1, "increment")
            for edge_type in ("success", "failure"):
                if not tracking_bfs and edge_type != status:
                    continue
                if (tracking_bfs or device) and not summary[edge_type]:
                    continue
                for edge in service.neighbors(self, edge_type):
                    successor = edge.destination
                    if tracking_bfs or device:
                        targets[successor.name] |= set(summary[edge_type])
                    heappush(services, ((1 / successor.priority, successor)))
                    if tracking_bfs or device:
                        run.write_state(
                            f"edges/{edge.id}", len(summary[edge_type]), "increment"
                        )
                    else:
                        run.write_state(f"edges/{edge.id}", "DONE")
        if tracking_bfs or device:
            failed = list(targets[start.name] - targets[end.name])
            summary = {"success": list(targets[end.name]), "failure": failed}
            results = {"success": not failed, "summary": summary}
        else:
            results = {"success": end in visited}
        run.restart_run = restart_run
        if run.is_main_run and self.man_minutes:
            self.man_minutes_total += (
                len(summary["success"]) * self.man_minutes
                if self.man_minutes_type == "device"
                else self.man_minutes * results["success"]
            )
        return results


class WorkflowForm(ServiceForm):
    form_type = HiddenField(default="workflow")
    category = SelectField("Category")
    close_connection = BooleanField(default=False)
    run_method = SelectField(
        "Run Method",
        choices=(
            ("per_device", "Run the workflow device by device"),
            (
                "per_service_with_workflow_targets",
                "Run the workflow service by service using workflow targets",
            ),
            (
                "per_service_with_service_targets",
                "Run the workflow service by service using service targets",
            ),
        ),
        no_search=True,
    )
    man_minutes = IntegerField(
        "Minutes to Complete Task Manually", [NumberRange(min=0)], default=0
    )
    man_minutes_type = SelectField(
        "Type of Minutes",
        choices=(
            ("workflow", "For the whole workflow"),
            ("device", "Per Device"),
        ),
    )
    man_minutes_total = IntegerField(
        "Total Number of Minutes", default=0, render_kw={"readonly": True}
    )
    superworkflow = InstanceField(
        "Superworkflow",
        constraints={"children": ["[Shared] Placeholder"], "children_filter": "union"},
    )

    def validate(self, **_):
        valid_form = super().validate()
        invalid_man_minutes_error = (
            vs.automation["workflow"]["mandatory_man_minutes"]
            and not self.workflows.data
            and not self.man_minutes.data
        )
        if invalid_man_minutes_error:
            self.man_minutes.errors.append(
                "The 'Man Minutes' Parameter cannot be set to 0."
            )
        invalid_man_minutes_type_error = (
            self.man_minutes.data
            and self.run_method.data == "per_service_with_service_targets"
            and self.man_minutes_type.data == "device"
        )
        if invalid_man_minutes_type_error:
            self.man_minutes_type.errors.append(
                (
                    "'Per Device' Man Minutes Type is not compatible"
                    " with the 'Service Targets' Run Method."
                )
            )
        invalid_targets_error = (
            self.run_method.data == "per_service_with_service_targets"
            and (
                self.target_devices.data
                or self.target_pools.data
                or self.device_query.data
            )
        )
        if invalid_targets_error:
            self.run_method.errors.append(
                (
                    "The workflow has device targets but the "
                    "run method is set to 'Service by Service'."
                )
            )
        return valid_form and not any(
            [
                invalid_man_minutes_type_error,
                invalid_man_minutes_error,
                invalid_targets_error,
            ]
        )


class WorkflowEdge(AbstractBase):
    __tablename__ = type = class_type = "workflow_edge"
    id = db.Column(Integer, primary_key=True)
    name = db.Column(db.SmallString, unique=True)
    label = db.Column(db.SmallString)
    color = db.Column(db.SmallString)
    subtype = db.Column(db.SmallString)
    source_id = db.Column(Integer, ForeignKey("service.id"))
    source = relationship(
        "Service",
        primaryjoin="Service.id == WorkflowEdge.source_id",
        backref=backref("destinations", cascade="all, delete-orphan"),
        foreign_keys="WorkflowEdge.source_id",
        lazy="joined",
    )
    destination_id = db.Column(Integer, ForeignKey("service.id"))
    destination = relationship(
        "Service",
        primaryjoin="Service.id == WorkflowEdge.destination_id",
        backref=backref("sources", cascade="all, delete-orphan"),
        foreign_keys="WorkflowEdge.destination_id",
        lazy="joined",
    )
    workflow_id = db.Column(Integer, ForeignKey("workflow.id"))
    workflow = relationship(
        "Workflow",
        back_populates="edges",
        foreign_keys="WorkflowEdge.workflow_id",
        lazy="joined",
    )
    __table_args__ = (
        UniqueConstraint(subtype, source_id, destination_id, workflow_id),
    )

    def __init__(self, **kwargs):
        self.label = kwargs["subtype"]
        self.color = "green" if kwargs["subtype"] == "success" else "red"
        super().__init__(**kwargs)

    def update(self, **kwargs):
        super().update(**kwargs)
        self.set_name(kwargs.get("name"))

    def set_name(self, name=None):
        self.name = name or f"[{self.workflow}] {vs.get_time()}"
