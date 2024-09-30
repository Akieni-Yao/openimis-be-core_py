import datetime
import logging
from abc import ABC
from typing import Type

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)
from core.models import HistoryModel, ScheduledTask
from core.services.utils import check_authentication as check_authentication, output_exception, \
    model_representation, output_result_success, build_delete_instance_payload
from core.validation.base import BaseModelValidation


class BaseService(ABC):

    @property
    def OBJECT_TYPE(self) -> Type[HistoryModel]:
        """
        Django ORM model. It's expected that it'll be inheriting from HistoryModel.
        """
        raise NotImplementedError("Class has to define OBJECT_TYPE for service.")

    def __init__(self, user, validation_class: BaseModelValidation):
        self.user = user
        self.validation_class = validation_class

    @check_authentication
    def create(self, obj_data):
        try:
            with transaction.atomic():
                obj_data = self._adjust_create_payload(obj_data)
                self.validation_class.validate_create(self.user, **obj_data)
                obj_ = self.OBJECT_TYPE(**obj_data)
                return self.save_instance(obj_)
        except Exception as exc:
            return output_exception(model_name=self.OBJECT_TYPE.__name__, method="create", exception=exc)

    @check_authentication
    def update(self, obj_data):
        try:
            with transaction.atomic():
                obj_data = self._adjust_update_payload(obj_data)
                self.validation_class.validate_update(self.user, **obj_data)
                obj_ = self.OBJECT_TYPE.objects.filter(id=obj_data['id']).first()
                [setattr(obj_, key, obj_data[key]) for key in obj_data]
                return self.save_instance(obj_)
        except Exception as exc:
            return output_exception(model_name=self.OBJECT_TYPE.__name__, method="update", exception=exc)

    @check_authentication
    def delete(self, obj_data):
        try:
            with transaction.atomic():
                self.validation_class.validate_delete(self.user, **obj_data)
                obj_ = self.OBJECT_TYPE.objects.filter(id=obj_data['id']).first()
                return self.delete_instance(obj_)
        except Exception as exc:
            return output_exception(model_name=self.OBJECT_TYPE.__name__, method="delete", exception=exc)

    def save_instance(self, obj_):
        obj_.save(username=self.user.username)
        dict_repr = model_representation(obj_)
        return output_result_success(dict_representation=dict_repr)

    def delete_instance(self, obj_):
        obj_.delete(username=self.user.username)
        return build_delete_instance_payload()

    def _adjust_create_payload(self, payload_data):
        return self._base_payload_adjust(payload_data)

    def _adjust_update_payload(self, payload_data):
        return self._base_payload_adjust(payload_data)

    def _base_payload_adjust(self, obj_data):
        return obj_data


def create_scheduled_task(
        task_name,
        task_path=None,
        module=None,
        reference=None,
        run_at=None,
        frequency="daily",
        day_of_month=None,
        day_of_week=None,
        hour_of_day=None
):
    """
    Creates a new scheduled task with the given parameters.

    :param task_name: Name of the task
    :param task_path: Full dotted path to the function (e.g., 'payment.rights_for_policy.main_enable_rights_policyholder_periodicity_one')
    :param module: Module to import dynamically (e.g., 'payment.rights_for_policy')
    :param reference: Function or method to call from the module (e.g., 'main_enable_rights_policyholder_periodicity_one')
    :param run_at: The initial time to run the task. Defaults to now.
    :param frequency: How often the task should run ('daily', 'weekly', 'monthly'). Default is 'daily'.
    :param day_of_month: For monthly tasks, the day of the month (1-31) the task should run
    :param day_of_week: For weekly tasks, the day of the week (0=Sunday, 6=Saturday) the task should run
    :param hour_of_day: The hour of the day (0-23) when the task should run
    :return: ScheduledTask object or None
    """
    if not run_at:
        run_at = timezone.now()
    # Extract hour from datetime.time if needed
    if isinstance(hour_of_day, datetime.time):
        hour_of_day = hour_of_day.hour

    # Validate inputs based on the frequency of the task
    if frequency == 'monthly' and not day_of_month:
        logger.error("For monthly tasks, 'day_of_month' must be specified.")
        return None
    if frequency == 'weekly' and not day_of_week:
        logger.error("For weekly tasks, 'day_of_week' must be specified.")
        return None
    if hour_of_day is None:
        logger.error("'hour_of_day' must be specified for all tasks.")
        return None

    # Create a new ScheduledTask object
    try:
        task = ScheduledTask.objects.create(
            task_name=task_name,
            task_path=task_path,
            module=module,
            reference=reference,
            run_at=run_at,
            frequency=frequency,
            day_of_month=day_of_month if frequency == 'monthly' else None,
            day_of_week=day_of_week if frequency == 'weekly' else None,
            hour_of_day=hour_of_day,
            is_completed=False
        )
        logger.info(f"Scheduled task '{task_name}' created successfully.")
        return task
    except Exception as e:
        logger.error(f"Error occurred while scheduling task '{task_name}': {str(e)}")
        return None


def reset_erp_op_before_save(erp_operations):
    fields = [
        "name",
        "alt_lang_name",
        "code",
        "erp_id",
        "access_id",
        "accounting_id",
    ]
    for field in fields:
        if hasattr(erp_operations, field):
            setattr(erp_operations, field, None)


def reset_banks_before_save(banks):
    fields = [
        "name",
        "alt_lang_name",
        "code",
        "erp_id",
        "journaux_id",
    ]
    for field in fields:
        if hasattr(banks, field):
            setattr(banks, field, None)
