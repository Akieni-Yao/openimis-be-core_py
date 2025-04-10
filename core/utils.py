import os

import core
import graphene
import qrcode
import requests
import time
import base64
from io import BytesIO
from PIL import Image
from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext as _
import logging
from django.apps import apps
from django.core.exceptions import PermissionDenied



logger = logging.getLogger(__file__)

__all__ = [
    "TimeUtils",
    "full_class_name",
    "comparable",
    "filter_validity",
    "prefix_filterset",
    "assert_string_length",
    "PATIENT_CATEGORY_MASK_MALE",
    "PATIENT_CATEGORY_MASK_FEMALE",
    "PATIENT_CATEGORY_MASK_ADULT",
    "PATIENT_CATEGORY_MASK_MINOR",
    "patient_category_mask",
    "ExtendedConnection",
    "get_scheduler_method_ref",
    "ExtendedRelayConnection",
]


class TimeUtils(object):

    @classmethod
    def now(cls):
        return core.datetime.datetime.now()

    @classmethod
    def date(cls):
        return core.datetime.datetime.date(cls.now())


def full_class_name(o):
    module = o.__class__.__module__
    if module is None or module == str.__class__.__module__:
        return o.__class__.__name__
    return module + '.' + o.__class__.__name__


def comparable(cls):
    """ Class decorator providing generic comparison functionality """

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)

    cls.__eq__ = __eq__
    cls.__ne__ = __ne__
    return cls


def filter_validity(arg="validity", **kwargs):
    validity = kwargs.get(arg)
    if validity is None:
        return (
            Q(legacy_id__isnull=True),
            Q(validity_to__isnull=True),
        )
    return (
        Q(validity_from__lte=validity),
        Q(validity_to__isnull=True) | Q(validity_to__gte=validity),
    )


def filter_validity_business_model(arg='dateValidFrom__Gte', arg2='dateValidTo__Lte', **kwargs):
    date_valid_from = kwargs.get(arg)
    date_valid_to = kwargs.get(arg2)
    # default scenario
    if not date_valid_from and not date_valid_to:
        today = core.datetime.datetime.now()
        return __place_the_filters(date_start=today, date_end=None)

    # scenario - only date valid to set
    if not date_valid_from and date_valid_to:
        today = core.datetime.datetime.now()
        oldest = min([today, date_valid_to])
        return __place_the_filters(date_start=oldest, date_end=date_valid_to)

    # scenario - only date valid from
    if date_valid_from and not date_valid_to:
        return __place_the_filters(date_start=date_valid_from, date_end=None)

    # scenario - both filters set
    if date_valid_from and date_valid_to:
        return __place_the_filters(date_start=date_valid_from, date_end=date_valid_to)


def __place_the_filters(date_start, date_end):
    """funtion related to 'filter_validity_business_model'
    function so as to set up the chosen filters
    to filter the validity of the entity
    """
    if not date_end:
        return (
            Q(date_valid_from__isnull=False),
            Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=date_start)
        )
    return (
        Q(date_valid_from__lte=date_end),
        Q(date_valid_to__isnull=True) | Q(date_valid_to__gte=date_start)
    )


def append_validity_filter(**kwargs):
    default_filter = kwargs.get('applyDefaultValidityFilter', False)
    date_valid_from = kwargs.get('dateValidFrom__Gte', None)
    date_valid_to = kwargs.get('dateValidTo__Lte', None)
    filters = []
    # check if we can use default filter validity
    if date_valid_from is None and date_valid_to is None:
        if default_filter:
            filters = [*filter_validity_business_model(**kwargs)]
        else:
            filters = []
    else:
        filters = [*filter_validity_business_model(**kwargs)]
    return filters


def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def filter_is_deleted(arg='is_deleted', **kwargs):
    is_deleted = kwargs.get(arg)
    if is_deleted is None:
        is_deleted = False
    return (
        Q(is_deleted=is_deleted)
    )


def prefix_filterset(prefix, filterset):
    if type(filterset) is dict:
        return {(prefix + k): v for k, v in filterset.items()}
    elif type(filterset) is list:
        return [(prefix + x) for x in filterset]
    else:
        return filterset


def assert_string_length(str_value, length):
    if length and len(str_value) > length:
        raise Exception(
            _("core.string.over_max_length") % {
                'value': str_value, 'max_length': length})


PATIENT_CATEGORY_MASK_MALE = 1
PATIENT_CATEGORY_MASK_FEMALE = 2
PATIENT_CATEGORY_MASK_ADULT = 4
PATIENT_CATEGORY_MASK_MINOR = 8


def patient_category_mask(insuree, target_date):
    if type(target_date) is str:
        from core import datetime
        # TODO: this should be nicer
        target_date = datetime.date(*[int(x) for x in target_date.split("-")])
    mask = 0
    if not insuree.gender:
        raise NotImplementedError(_("core.insuree.unknown_gender"))
    if not insuree.dob:
        raise NotImplementedError(_("core.insuree.unknown_dob"))

    if insuree.gender.code in ('M', 'O'):
        mask = mask | PATIENT_CATEGORY_MASK_MALE
    else:
        mask = mask | PATIENT_CATEGORY_MASK_FEMALE

    if insuree.is_adult(target_date):
        mask = mask | PATIENT_CATEGORY_MASK_ADULT
    else:
        mask = mask | PATIENT_CATEGORY_MASK_MINOR
    return mask


class ExtendedConnection(graphene.Connection):
    """
    Adds total_count and edge_count to Graphene connections. To use, simply add to the
    Graphene object definition Meta:
    `connection_class = ExtendedConnection`
    """

    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            raise PermissionDenied(_("unauthorized"))
        return self.length

    def resolve_edge_count(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            raise PermissionDenied(_("unauthorized"))
        return len(self.edges)


def get_scheduler_method_ref(name):
    """
    Use to retrieve the method reference from a str name. This is necessary when the module cannot be imported from
    that location.
    :param name: claim.module.submodule.method or similar name
    :return: reference to the method
    """
    split_name = name.split(".")
    module = __import__(".".join(split_name[:-1]))
    for subitem in split_name[1:]:
        module = getattr(module, subitem)
    return module


class ExtendedRelayConnection(graphene.relay.Connection):
    """
    Adds total_count and edge_count to Graphene Relay connections.
    """

    class Meta:
        abstract = True

    total_count = graphene.Int()
    edge_count = graphene.Int()

    def resolve_total_count(self, info, **kwargs):
        return len(self.iterable)

    def resolve_edge_count(self, info, **kwargs):
        return len(self.edges)


def get_first_or_default_language():
    from core.models import Language
    sorted_languages = Language.objects.filter(sort_order__isnull=False)
    if sorted_languages.exists():
        return sorted_languages.order_by('sort_order').first()
    else:
        return Language.objects.first()


def insert_role_right_for_system(system_role, right_id):
    RoleRight = apps.get_model("core", "RoleRight")
    Role = apps.get_model("core", "Role")
    existing_role = Role.objects.filter(is_system=system_role).first()
    if not existing_role:
        logger.warning("Migration requested a role_right for system role %s but couldn't find that role", system_role)
    role_right = RoleRight.objects.filter(role=existing_role, right_id=right_id).first()
    if not role_right:
        role_right = RoleRight.objects.create(role=existing_role, right_id=right_id)

    return role_right


def generate_qr(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return img_str


def create_notification(user_id, message, redirect_url):
    from core.models import CamuNotification, User
    user = User.objects.get(id=user_id)
    notification = CamuNotification.objects.create(user=user, message=message, redirect_url=redirect_url)
    return notification


def mark_notification_as_read(notification_id):
    from core.models import CamuNotification
    notification = CamuNotification.objects.get(id=notification_id)
    notification.is_read = True
    notification.save()
    return notification


def mark_all_notifications_as_read(user_id):
    from core.models import CamuNotification
    notifications = CamuNotification.objects.filter(user_id=user_id, is_read=False)
    notifications.update(is_read=True)
    return notifications


def update_or_create_resync(id, user):
    from core.models import ErpApiFailedLogs
    from policyholder.models import PolicyHolder
    from datetime import datetime
    import json
    headers = {
        'Content-Type': 'application/json',
        'Tmr-Api-Key': os.environ.get("TMR_API_KEY", "1234"),
        'Cookie': 'frontend_lang=en_US'
    }

    if id:
        # Find the object using find_object_without_resync with status 0
        erp_logs_to_resync = find_object_without_resync(id)
        if not erp_logs_to_resync:
            logger.error(f"ERP API Failed logs with ID {id} not found or already resynced")
            raise ValueError("Data not found or already resynced.")

        if erp_logs_to_resync.module == 'policyholder':
            policyholder_data = PolicyHolder.objects.filter(id=erp_logs_to_resync.policy_holder.id, is_deleted=False).first()
            if policyholder_data and policyholder_data.erp_partner_access_id:
                erp_logs_to_resync.resync_status = 1
                erp_logs_to_resync.message = json.dumps({"message": "Already resynced"})
                erp_logs_to_resync.resync_at = datetime.now()
                erp_logs_to_resync.resync_by = user
                erp_logs_to_resync.save()
                logger.info(f"Successfully resynced ERP failed logs with ID {id} for policyholder.")
                return erp_logs_to_resync
            else:
                logger.info(f"No valid erp_partner_access_id found for policyholder with ID {erp_logs_to_resync.policy_holder.id}. Proceeding with the original resync logic.")

        logger.info(f"Updating ERP Failed logs with ID {id}")
        url = erp_logs_to_resync.request_url
        json_data = erp_logs_to_resync.request_data

        response = requests.post(url, headers=headers, json=json_data, verify=False)

        if response.status_code in [200, 201]:
            # Update the original entry with resync_status = 1
            erp_logs_to_resync.resync_status = 1
            erp_logs_to_resync.resync_at = datetime.now()
            erp_logs_to_resync.resync_by = user
            erp_logs_to_resync.save()
            logger.info(f"Successfully resynced ERP failed logs with ID {id}")
            return erp_logs_to_resync
        else:
            # Update the original entry with resync_status = -1
            erp_logs_to_resync.resync_status = -1
            erp_logs_to_resync.resync_at = datetime.now()
            erp_logs_to_resync.resync_by = user
            erp_logs_to_resync.save()

            # Create a new entry with resync_status = 0
            resynced_erp_logs = ErpApiFailedLogs(
                module=erp_logs_to_resync.module,
                action=erp_logs_to_resync.action,
                response_status_code=response.status_code,
                response_json=response.json(),
                request_url=erp_logs_to_resync.request_url,
                message=response.text,
                request_data=erp_logs_to_resync.request_data,
                resync_status=0,  # Indicating the new entry is awaiting resync
                resync_at=None,  # No resync yet for this new entry
                resync_by=None,
                policy_holder=erp_logs_to_resync.policy_holder,
                claim=erp_logs_to_resync.claim,
                contract=erp_logs_to_resync.contract,
                health_facility=erp_logs_to_resync.health_facility,
                payment_penalty=erp_logs_to_resync.payment_penalty,
                payment=erp_logs_to_resync.payment,
                service=erp_logs_to_resync.service,
                item=erp_logs_to_resync.item
            )

            # Save the new object and set the parent
            resynced_erp_logs.save()
            resynced_erp_logs.parent = erp_logs_to_resync
            resynced_erp_logs.save()

            logger.info(f"Created new ERP failed logs entry due to failed resync with ID {id}")
            return erp_logs_to_resync.resync_status

    else:
        # Handle case where no ID is provided (if applicable)
        raise ValueError("ID argument is required for resync operation.")



def find_object_without_resync(id):
    from core.models import ErpApiFailedLogs
    try:
        obj = ErpApiFailedLogs.objects.get(pk=id, resync_status=0)  # Fetch object with status 0
    except ErpApiFailedLogs.DoesNotExist:
        return None

    if ErpApiFailedLogs.objects.filter(parent=id, resync_by__isnull=False, resync_at__isnull=False).exists():
        return None

    return obj
