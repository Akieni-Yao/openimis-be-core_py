import decimal
import json
import logging
import re
import sys
import uuid
import threading

import graphene
from django.utils.translation import gettext as _
from copy import copy
from datetime import datetime as py_datetime
from functools import reduce
from django.utils.translation import gettext_lazy
from graphene.types.generic import GenericScalar
from graphql import GraphQLError
from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.mutations import JSONWebTokenMutation, mixins
import graphene_django_optimizer as gql_optimizer
from core.services import (
    create_or_update_interactive_user,
    create_or_update_core_user,
    create_or_update_officer,
    create_or_update_claim_admin,
    change_user_password,
    reset_user_password,
    set_user_password,
)
from core.tasks import openimis_mutation_async
from django import dispatch
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError, PermissionDenied, ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, Count
from django.db.models.expressions import RawSQL
from django.http import HttpRequest
from django.utils import translation
from graphene.utils.str_converters import to_snake_case, to_camel_case
from graphene_django.filter import DjangoFilterConnectionField
import graphql_jwt
from typing import Optional, List, Dict, Any

from workflow.models import WF_Profile_Queue
from workflow.constants import STATUS_WAITING_FOR_APPROVAL, STATUS_WAITING_FOR_QUEUE
from insuree.models import Insuree, Family
from .apps import CoreConfig
from .constants import APPROVER_ROLE
from .gql_queries import *
from .services.base import reset_erp_op_before_save, reset_banks_before_save
from .utils import flatten_dict, update_or_create_resync
from .models import (
    ModuleConfiguration,
    FieldControl,
    MutationLog,
    Language,
    RoleMutation,
    UserAuditLog,
    UserMutation,
    GenericConfig,
    AuditLogs,
    ErpApiFailedLogs,
    ErpOperations,
    Banks,
)
from .services.roleServices import check_role_unique_name
from .services.userServices import check_user_unique_email, create_audit_user_service
from .validation.obligatoryFieldValidation import validate_payload_for_obligatory_fields
from location.models import HealthFacility

MAX_SMALLINT = 32767
MIN_SMALLINT = -32768

core = sys.modules["core"]

logger = logging.getLogger(__name__)


class SmallInt(graphene.Int):
    """
    This represents a small Integer, with values ranging from -32768 to +32767
    """

    @staticmethod
    def coerce_int(value):
        res = super().coerce_int(value)
        if MIN_SMALLINT <= res <= MAX_SMALLINT:
            return res
        else:
            return None

    serialize = coerce_int
    parse_value = coerce_int

    @staticmethod
    def parse_literal(ast):
        result = graphene.Int.parse_literal(ast)
        if result is not None and MIN_SMALLINT <= result <= MAX_SMALLINT:
            return result
        else:
            return None


MAX_TINYINT = 255
MIN_TINYINT = 0


class TinyInt(graphene.Int):
    """
    This represents a tiny Integer (8 bit), with values ranging from 0 to 255
    """

    @staticmethod
    def coerce_int(value):
        res = super().coerce_int(value)
        if MIN_TINYINT <= res <= MAX_TINYINT:
            return res
        else:
            return None

    serialize = coerce_int
    parse_value = coerce_int

    @staticmethod
    def parse_literal(ast):
        result = graphene.Int.parse_literal(ast)
        if result is not None and MIN_TINYINT <= result <= MAX_TINYINT:
            return result
        else:
            return None


class ParsedJSONString(graphene.JSONString):
    """
    This type automatically converts keys of json object between camel case (to be used in serialized strings)
    and snake case (to fit Python objects).
    """

    @staticmethod
    def parse_keys(input_dict, key_parser):
        if isinstance(input_dict, dict):
            return {
                key_parser(k): ParsedJSONString.parse_keys(v, key_parser)
                if isinstance(v, dict)
                else v
                for k, v in input_dict.items()
            }

    @staticmethod
    def serialize(dt):
        return ParsedJSONString.parse_keys(
            graphene.JSONString.serialize(dt), to_camel_case
        )

    @staticmethod
    def parse_literal(node):
        return ParsedJSONString.parse_keys(
            graphene.JSONString.parse_literal(node), to_snake_case
        )

    @staticmethod
    def parse_value(value):
        return ParsedJSONString.parse_keys(
            graphene.JSONString.parse_value(value), to_snake_case
        )


class OpenIMISJSONEncoder(DjangoJSONEncoder):
    def default(self, o):
        if isinstance(o, HttpRequest):
            if o.user:
                return f"HTTP_user: {o.user.id}"
            else:
                return None
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)


_mutation_signal_params = [
    "user",
    "mutation_module",
    "mutation_class",
    "mutation_log_id",
    "data",
]
signal_mutation = dispatch.Signal(providing_args=_mutation_signal_params)
signal_mutation_module_validate = {}
signal_mutation_module_before_mutating = {}
signal_mutation_module_after_mutating = {}

for module in sys.modules:
    signal_mutation_module_validate[module] = dispatch.Signal(
        providing_args=_mutation_signal_params
    )
    signal_mutation_module_before_mutating[module] = dispatch.Signal(
        providing_args=_mutation_signal_params
    )
    signal_mutation_module_after_mutating[module] = dispatch.Signal(
        providing_args=_mutation_signal_params + ["error_messages"]
    )


class OpenIMISMutation(graphene.relay.ClientIDMutation):
    """
    This class is the generic Mutation for openIMIS. It will save the mutation content into the MutationLog,
    submit it to validation, perform the potentially asynchronous mutation itself and update the MutationLog status.
    """

    class Meta:
        abstract = True

    internal_id = graphene.Field(graphene.String)

    class Input:
        client_mutation_label = graphene.String(max_length=255, required=False)
        client_mutation_details = graphene.List(graphene.String)
        mutation_extensions = ParsedJSONString(
            description="Extension data to be used by signals. Will not be pushed to mutation implementation."
        )

    @classmethod
    def async_mutate(cls, user, **data) -> List[Dict[str, Any]]:
        """
        This method has to be overridden in the subclasses to implement the actual mutation.
        The response should contain a boolean for success and an error message that will be saved into the DB
        :param user: contains the logged user or None
        :param data: all parameters passed to the mutation
        :return: error_message if None is returned, the response is considered to be a success
        """
        pass

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        mutation_log = MutationLog.objects.create(
            json_content=json.dumps(data, cls=OpenIMISJSONEncoder),
            user_id=info.context.user.id if info.context.user else None,
            client_mutation_id=data.get("client_mutation_id"),
            client_mutation_label=data.get("client_mutation_label"),
            client_mutation_details=json.dumps(
                data.get("client_mutation_details"), cls=OpenIMISJSONEncoder
            )
            if data.get("client_mutation_details")
            else None,
        )
        logger.debug(
            "OpenIMISMutation: saved as %s, label: %s",
            mutation_log.id,
            mutation_log.client_mutation_label,
        )
        if (
            info
            and info.context
            and info.context.user
            and not info.context.user.is_anonymous
        ):
            lang = info.context.user.language
            if isinstance(lang, Language):
                translation.activate(lang.code)
            else:
                translation.activate(lang)

        try:
            logger.debug("[OpenIMISMutation %s] Sending signals", mutation_log.id)
            results = signal_mutation.send(
                sender=cls,
                mutation_log_id=mutation_log.id,
                data=data,
                user=info.context.user,
                mutation_module=cls._mutation_module,
                mutation_class=cls._mutation_class,
            )
            results.extend(
                signal_mutation_module_validate[cls._mutation_module].send(
                    sender=cls,
                    mutation_log_id=mutation_log.id,
                    data=data,
                    user=info.context.user,
                    mutation_module=cls._mutation_module,
                    mutation_class=cls._mutation_class,
                )
            )
            errors = [err for r in results for err in r[1]]
            logger.debug(
                "[OpenIMISMutation %s] signals sent, got errors back: %d",
                mutation_log.id,
                len(errors),
            )
            if errors:
                mutation_log.mark_as_failed(json.dumps(errors))
                return cls(internal_id=mutation_log.id)

            signal_mutation_module_before_mutating[cls._mutation_module].send(
                sender=cls,
                mutation_log_id=mutation_log.id,
                data=data,
                user=info.context.user,
                mutation_module=cls._mutation_module,
                mutation_class=cls._mutation_class,
            )
            logger.debug(
                "[OpenIMISMutation %s] before mutate signal sent", mutation_log.id
            )
            if core.async_mutations:
                logger.debug(
                    "[OpenIMISMutation %s] Sending async mutation", mutation_log.id
                )
                openimis_mutation_async.delay(
                    mutation_log.id, cls._mutation_module, cls._mutation_class
                )
            else:
                logger.debug("[OpenIMISMutation %s] mutating...", mutation_log.id)
                try:
                    mutation_data = data.copy()
                    mutation_data.pop("mutation_extensions", None)
                    error_messages = cls.async_mutate(
                        info.context.user
                        if info.context and info.context.user
                        else None,
                        **mutation_data,
                    )
                    if not error_messages:
                        logger.debug(
                            "[OpenIMISMutation %s] marked as successful",
                            mutation_log.id,
                        )
                        mutation_log.mark_as_successful()
                    else:
                        exceptions = [
                            message.pop("exc")
                            for message in error_messages
                            if "exc" in message
                        ]
                        errors_json = json.dumps(error_messages)
                        logger.error(
                            "[OpenIMISMutation %s] marked as failed: %s",
                            mutation_log.id,
                            errors_json,
                        )
                        for exc in exceptions:
                            logger.error(
                                "[OpenIMISMutation %s] Exception:",
                                mutation_log.id,
                                exc_info=exc,
                            )
                        mutation_log.mark_as_failed(errors_json)
                except BaseException as exc:
                    error_messages = exc
                    logger.error(
                        "async_mutate threw an exception. It should have gotten this far.",
                        exc_info=exc,
                    )
                    # Record the failure of the mutation but don't include details for security reasons
                    mutation_log.mark_as_failed(
                        f"The mutation threw a {type(exc)}, check logs for details"
                    )
                logger.debug(
                    "[OpenIMISMutation %s] send post mutation signal", mutation_log.id
                )
                signal_mutation_module_after_mutating[cls._mutation_module].send(
                    sender=cls,
                    mutation_log_id=mutation_log.id,
                    data=data,
                    user=info.context.user,
                    mutation_module=cls._mutation_module,
                    mutation_class=cls._mutation_class,
                    error_messages=error_messages,
                )
        except Exception as exc:
            logger.error(
                f"Exception while processing mutation id {mutation_log.id}",
                exc_info=exc,
            )
            mutation_log.mark_as_failed(exc)

        return cls(internal_id=mutation_log.id)


class FieldControlGQLType(DjangoObjectType):
    class Meta:
        model = FieldControl


class ModuleConfigurationGQLType(DjangoObjectType):
    class Meta:
        model = ModuleConfiguration


class OrderedDjangoFilterConnectionField(DjangoFilterConnectionField):
    """
    Adapted from https://github.com/graphql-python/graphene/issues/251
    And then adapted by Alok Ramteke on my (Eric Darchis)' stackoverflow question:
    https://stackoverflow.com/questions/57478464/django-graphene-relay-order-by-orderingfilter/61543302
    Substituting:
    `mutation_logs = DjangoFilterConnectionField(MutationLogGQLType)`
    with:
    ```
    mutation_logs = OrderedDjangoFilterConnectionField(MutationLogGQLType,
        orderBy=graphene.List(of_type=graphene.String))
    ```
    """

    @classmethod
    def _filter_order_by(cls, order_by: str) -> str:
        if order_by:
            return re.sub("[^\\w\\-,+]", "", order_by)
        else:
            return order_by

    @classmethod
    def orderBy(cls, qs, args):
        order = args.get("orderBy", None)
        if order:
            random_expression = (
                RawSQL("NEWID()", params=[])
                if settings.MSSQL
                else RawSQL("RANDOM()", params=[])
            )
            if type(order) is str:
                if order == "?":
                    snake_order = random_expression
                else:
                    # due to https://github.com/advisories/GHSA-xpfp-f569-q3p2 we are aggressively filtering the orderBy
                    snake_order = to_snake_case(cls._filter_order_by(order))
            else:
                snake_order = [
                    to_snake_case(cls._filter_order_by(o))
                    if o != "?"
                    else random_expression
                    for o in order
                ]
            qs = qs.order_by(*snake_order)
        return qs

    @classmethod
    def resolve_queryset(
        cls, connection, iterable, info, args, filtering_args, filterset_class
    ):
        if not info.context.user.is_authenticated:
            raise PermissionDenied(_("unauthorized"))
        qs = super(DjangoFilterConnectionField, cls).resolve_queryset(
            connection, iterable, info, args
        )
        filter_kwargs = {k: v for k, v in args.items() if k in filtering_args}
        qs = filterset_class(data=filter_kwargs, queryset=qs, request=info.context).qs

        return OrderedDjangoFilterConnectionField.orderBy(qs, args)


class MutationLogGQLType(DjangoObjectType):
    """
    This represents a requested mutation and its status.
    The "user" search filter is only available for super-users. Otherwise, the user is automatically set to the
    currently logged user.
    """

    class Meta:
        model = MutationLog
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "client_mutation_id": ["exact"],
            "client_mutation_label": ["exact"],
            "request_date_time": ["exact", "gte", "lte"],
            "status": ["exact", "gte"],
            "user": ["exact"],
        }
        connection_class = ExtendedConnection

    status = graphene.Field(
        graphene.Int,
        description=", ".join(
            [f"{pair[0]}: {pair[1]}" for pair in MutationLog.STATUS_CHOICES]
        ),
    )

    @classmethod
    def get_queryset(cls, queryset, info):
        if info.context.user.is_anonymous:
            return queryset.none()
        elif info.context.user.is_superuser:
            return queryset
        else:
            queryset = queryset.filter(user=info.context.user)
        return queryset


UT_INTERACTIVE = "INTERACTIVE"
UT_TECHNICAL = "TECHNICAL"
UT_OFFICER = "OFFICER"
UT_CLAIM_ADMIN = "CLAIM_ADMIN"

UserTypeEnum = graphene.Enum(
    "UserTypes",
    [
        (UT_INTERACTIVE, UT_INTERACTIVE),
        (UT_OFFICER, UT_OFFICER),
        (UT_TECHNICAL, UT_TECHNICAL),
        (UT_CLAIM_ADMIN, UT_CLAIM_ADMIN),
    ],
)


class GenericConfigType(DjangoObjectType):
    class Meta:
        model = GenericConfig


class ERPFailedLogsType(DjangoObjectType):
    class Meta:
        model = ErpApiFailedLogs
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "module": ["exact"],
            "parent_id__id": ["exact"],
            "resync_status": ["exact"],
            "claim__code": ["exact", "istartswith", "icontains", "iexact"],
            "claim__date_claimed": ["exact", "lt", "lte", "gt", "gte"],
            "policy_holder__code": ["exact", "istartswith", "icontains", "iexact"],
            "policy_holder__trade_name": [
                "exact",
                "istartswith",
                "icontains",
                "iexact",
            ],
            "policy_holder__date_created": ["exact", "lt", "lte", "gt", "gte"],
            "health_facility__fosa_code": [
                "exact",
                "istartswith",
                "icontains",
                "iexact",
            ],
            "health_facility__name": ["exact", "istartswith", "icontains", "iexact"],
            "contract__code": ["exact", "istartswith", "icontains", "iexact"],
            "contract__date_valid_from": ["exact", "lt", "lte", "gt", "gte", "isnull"],
            "payment__payment_code": ["exact", "istartswith", "icontains", "iexact"],
            "payment__payment_date": ["exact", "lt", "lte", "gt", "gte", "isnull"],
            "payment__request_date": ["exact", "lt", "lte", "gt", "gte", "isnull"],
            "payment_penalty__code": ["exact", "istartswith", "icontains", "iexact"],
            "payment_penalty__date_valid_from": ["exact", "gt", "gte", "isnull"],
            "service__code": ["exact", "istartswith", "icontains", "iexact"],
            "service__name": ["exact", "istartswith", "icontains", "iexact"],
            "item__code": ["exact", "istartswith", "icontains", "iexact"],
            "item__name": ["exact", "istartswith", "icontains", "iexact"],
        }
        connection_class = ExtendedConnection

    def resolve_message(self, info):
        msg = self.message
        data = json.loads(msg)
        message = data["message"]

        if message == "Missing required field.":
            # Check if data["field_name"] is a list
            if isinstance(data["field_name"], list):
                field_names = ",".join(data["field_name"])
            else:
                field_names = data["field_name"]
            self.message = field_names + "," + message
        elif message == "Invoice not found.":
            self.message = message
        else:
            self.message = message

        return self.message


class CamuNotificationType(DjangoObjectType):
    class Meta:
        model = CamuNotification
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            **prefix_filterset("user__", UserGQLType._meta.filter_fields),
        }
        connection_class = ExtendedConnection


class ErpOperationsType(DjangoObjectType):
    class Meta:
        model = ErpOperations
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "name": ["exact", "istartswith", "icontains", "iexact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "erp_id": ["exact", "istartswith", "icontains", "iexact"],
            "access_id": ["exact", "istartswith", "icontains", "iexact"],
            "accounting_id": ["exact"],
        }
        connection_class = ExtendedConnection


class BanksType(DjangoObjectType):
    class Meta:
        model = Banks
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "name": ["exact", "istartswith", "icontains", "iexact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "erp_id": ["exact", "istartswith", "icontains", "iexact"],
            "journaux_id": ["exact", "istartswith", "icontains", "iexact"],
        }
        connection_class = ExtendedConnection


class UserAuditLogGQLType(DjangoObjectType):
    class Meta:
        model = UserAuditLog
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "policy_holder__code": ["exact"],
            "fosa__fosa_code": ["exact"],
            "user__username": ["exact", "istartswith", "icontains", "iexact"],
            "action": ["exact", "istartswith", "icontains", "iexact"],
        }
        connection_class = ExtendedConnection


class Query(graphene.ObjectType):
    module_configurations = graphene.List(
        ModuleConfigurationGQLType, validity=graphene.String(), layer=graphene.String()
    )

    user_obligatory_fields = GenericScalar()
    eo_obligatory_fields = GenericScalar()

    mutation_logs = OrderedDjangoFilterConnectionField(
        MutationLogGQLType, orderBy=graphene.List(of_type=graphene.String)
    )

    role = OrderedDjangoFilterConnectionField(
        RoleGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        is_system=graphene.Boolean(),
        system_role_id=graphene.Int(),
        show_history=graphene.Boolean(),
        client_mutation_id=graphene.String(),
        str=graphene.String(description="Text search on any field"),
    )

    station = OrderedDjangoFilterConnectionField(
        StationGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    role_right = OrderedDjangoFilterConnectionField(
        RoleRightGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        validity=graphene.Date(),
        max_limit=None,
    )

    interactiveUsers = OrderedDjangoFilterConnectionField(
        InteractiveUserGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        validity=graphene.Date(),
        show_history=graphene.Boolean(),
        client_mutation_id=graphene.String(),
    )

    users = OrderedDjangoFilterConnectionField(
        UserGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        validity=graphene.Date(),
        client_mutation_id=graphene.String(),
        last_name=graphene.String(description="partial match, case insensitive"),
        other_names=graphene.String(description="partial match, case insensitive"),
        phone=graphene.String(description="exact match on phone number"),
        email=graphene.String(description="exact match on email address"),
        role_id=graphene.Int(),
        roles=graphene.List(of_type=graphene.Int),
        health_facility_id=graphene.Int(
            description="Base health facility ID (not UUID!)"
        ),
        health_facility_uuid=graphene.String(description="Base health facility UUID"),
        region_id=graphene.Int(),
        region_ids=graphene.List(of_type=graphene.Int),
        district_id=graphene.Int(),
        municipality_id=graphene.Int(),
        village_id=graphene.Int(),
        birth_date_from=graphene.Date(),
        birth_date_to=graphene.Date(),
        user_types=graphene.List(of_type=UserTypeEnum),
        language=graphene.String(),
        showHistory=graphene.Boolean(),
        is_fosa_user=graphene.Boolean(),
        is_portal_user=graphene.Boolean(),
        str=graphene.String(
            description="text search that will check username, last name, other names and email"
        ),
        description="This interface provides access to the various types of users in openIMIS. The main resource"
        "is limited to a username and refers either to a TechnicalUser or InteractiveUser. Only the latter"
        "is exposed in GraphQL. There are also optional links to ClaimAdministrator and Officer depending"
        "on the setup. BEWARE, fetching these links is costly as there is no direct database link between"
        "these entities and there are retrieved one by one. Do not fetch them for large lists if you can"
        "avoid it. The showHistory is acting on the InteractiveUser, avoid mixing with Officer or "
        "ClaimAdmin.",
    )

    user = graphene.Field(UserGQLType)

    enrolment_officers = OrderedDjangoFilterConnectionField(
        OfficerGQLType,
        str=graphene.String(
            description="text search that will check username, last name, other names and email"
        ),
    )

    substitution_enrolment_officers = OrderedDjangoFilterConnectionField(
        OfficerGQLType,
        villages_uuids=graphene.List(
            graphene.NonNull(graphene.String),
            description="List of villages to be required for substituion officers",
        ),
        officer_uuid=graphene.String(
            required=False,
            description="Current officer uuid to be excluded from substitution list.",
        ),
        str=graphene.String(
            required=False,
            description="Query that will return possible EO replacements.",
        ),
    )

    modules_permissions = graphene.Field(
        ModulePermissionsListGQLType,
    )

    languages = graphene.List(LanguageGQLType)

    validate_username = graphene.Field(
        graphene.Boolean,
        username=graphene.String(required=True),
        description="Checks that the specified username is unique.",
    )

    validate_user_email = graphene.Field(
        graphene.Boolean,
        user_email=graphene.String(required=True),
        description="Checks that the specified user email is unique.",
    )

    validate_role_name = graphene.Field(
        graphene.Boolean,
        role_name=graphene.String(required=True),
        description="Checks that the specified role name is unique.",
    )

    username_length = graphene.Int()
    all_configs = graphene.List(GenericConfigType)
    generic_config = graphene.Field(GenericConfigType, model_id=graphene.String())

    get_audit_logs = OrderedDjangoFilterConnectionField(
        AuditLogsGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    notifications = graphene.List(NotificationType, user_id=graphene.Int())

    erp_api_failed_logs = OrderedDjangoFilterConnectionField(
        ERPFailedLogsType,
        history=graphene.Boolean(required=False),
        orderBy=graphene.List(of_type=graphene.String),
    )
    camu_notifications = OrderedDjangoFilterConnectionField(
        CamuNotificationType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    erp_operations = OrderedDjangoFilterConnectionField(
        ErpOperationsType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    banks = OrderedDjangoFilterConnectionField(
        BanksType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    user_audit_logs = OrderedDjangoFilterConnectionField(
        UserAuditLogGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        policy_holder_id=graphene.UUID(),
        fosa_id=graphene.UUID(),
    )

    def resolve_user_audit_logs(self, info, **kwargs):
        policy_holder_id = kwargs.get("policy_holder_id", None)
        fosa_id = kwargs.get("fosa_id", None)
        user_id = kwargs.get("user_id", None)
        query = UserAuditLog.objects.all()
        if policy_holder_id:
            query = query.filter(policy_holder__id=policy_holder_id)
        if fosa_id:
            query = query.filter(fosa__id=fosa_id)
        if user_id:
            query = query.filter(user__id=user_id)
        return gql_optimizer.query(query, info)

    def resolve_banks(self, info, **kwargs):
        id = kwargs.get("id", None)
        query = Banks.objects.filter(is_deleted=False)
        if id:
            query = query.filter(id=id)
        return gql_optimizer.query(query, info)

    def resolve_erp_operations(self, info, **kwargs):
        id = kwargs.get("id", None)
        query = ErpOperations.objects.filter(is_deleted=False)
        if id:
            query = query.filter(id=id)
        return gql_optimizer.query(query, info)

    def resolve_camu_notifications(self, info, **kwargs):
        id = kwargs.get("id", None)
        query = CamuNotification.objects.filter(is_read=False)
        if id:
            query = query.filter(id=id)
        return gql_optimizer.query(query, info)

    def resolve_erp_api_failed_logs(self, info, **kwargs):
        history = kwargs.get("history", False)
        id = kwargs.get("id", None)

        query = ErpApiFailedLogs.objects.all()

        if id:
            if history:
                query = query.filter(parent_id=id)
            else:
                query = query.filter(id=id)

        return gql_optimizer.query(query, info)

    def resolve_notifications(self, info, user_id):
        return CamuNotification.objects.filter(user_id=user_id).order_by("-created_at")

    def resolve_get_audit_logs(self, info, **kwargs):
        return gql_optimizer.query(AuditLogs.objects.all(), info)

    def resolve_username_length(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_users_perms):
            raise PermissionDenied(_("unauthorized"))
        return CoreConfig.username_code_length

    def resolve_validate_role_name(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_roles_perms):
            raise PermissionDenied(_("unauthorized"))
        errors = check_role_unique_name(name=kwargs["role_name"])
        return False if errors else True

    def resolve_validate_username(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_users_perms):
            raise PermissionDenied(_("unauthorized"))
        if User.objects.filter(username=kwargs["username"]).exists():
            return False
        else:
            return True

    def resolve_validate_user_email(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_users_perms):
            raise PermissionDenied(_("unauthorized"))
        errors = check_user_unique_email(user_email=kwargs["user_email"])
        return False if errors else True

    def resolve_enrolment_officers(self, info, **kwargs):
        from .models import Officer

        if not info.context.user.has_perms(
            CoreConfig.gql_query_enrolment_officers_perms
        ):
            raise PermissionError("Unauthorized")

        search = kwargs.get("str")

        if search is not None:
            return gql_optimizer.query(
                Officer.objects.filter(
                    Q(code__icontains=search)
                    | Q(last_name__icontains=search)
                    | Q(other_names__icontains=search)
                ),
                info,
            )

    def resolve_substitution_enrolment_officers(self, info, **kwargs):
        from .models import Officer

        if not info.context.user.has_perms(
            CoreConfig.gql_query_enrolment_officers_perms
        ):
            raise PermissionError("Unauthorized")

        queryset = Officer.objects

        villages_uuids = kwargs.get("villages_uuids", None)
        if not villages_uuids:
            return []

        officer_uuid = kwargs.get("officer_uuid", None)
        if officer_uuid:
            queryset = queryset.exclude(uuid=officer_uuid)

        query_str = kwargs.get("str", None)
        if query_str:
            queryset = queryset.filter(
                Q(code__istartswith=query_str)
                | Q(last_name__istartswith=query_str)
                | Q(other_names__istartswith=query_str)
                | Q(email__istartswith=query_str)
            )

        return (
            queryset.prefetch_related("officer_villages")
            .annotate(nb_village=Count("officer_villages"))
            .filter(
                nb_village__gte=len(villages_uuids),
                officer_villages__location__uuid__in=villages_uuids,
                validity_to__isnull=True,
                officer_villages__validity_to__isnull=True,
                officer_villages__location__validity_to__isnull=True,
            )
        )

    def resolve_interactive_users(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_users_perms):
            raise PermissionError("Unauthorized")
        filters = []
        query = InteractiveUser.objects

        client_mutation_id = kwargs.get("client_mutation_id", None)
        if client_mutation_id:
            filters.append(
                Q(mutations__mutation__client_mutation_id=client_mutation_id)
            )

        show_history = kwargs.get("show_history", False)
        if not show_history and not kwargs.get("uuid", None):
            filters += filter_validity(**kwargs)

        return gql_optimizer.query(query.filter(*filters), info)

    def resolve_user(self, info):
        if info.context.user.is_authenticated:
            return info.context.user
        return None

    def resolve_user_obligatory_fields(self, info):
        if info.context.user.is_authenticated:
            return CoreConfig.fields_controls_user
        return None

    def resolve_eo_obligatory_fields(self, info):
        if info.context.user.is_authenticated:
            return CoreConfig.fields_controls_eo
        return None

    def resolve_users(
        self,
        info,
        email=None,
        last_name=None,
        other_names=None,
        phone=None,
        role_id=None,
        roles=None,
        health_facility_id=None,
        region_id=None,
        district_id=None,
        municipality_id=None,
        birth_date_from=None,
        birth_date_to=None,
        user_types=None,
        language=None,
        village_id=None,
        region_ids=None,
        is_portal_user=None,
        is_fosa_user=None,
        health_facility_uuid=None,
        **kwargs,
    ):
        # if not info.context.user.has_perms(CoreConfig.gql_query_users_perms):
        #     raise PermissionError("Unauthorized")

        user_filters = []
        user_query = User.objects.exclude(t_user__isnull=False)

        show_history = kwargs.get("showHistory", False)
        if not show_history and not kwargs.get("uuid", None):
            active_users_ids = [user.id for user in user_query if user.is_active]
            user_filters.append(Q(id__in=active_users_ids))

        text_search = kwargs.get("str")  # Poorly chosen name, avoid of shadowing "str"
        if text_search:
            user_filters.append(
                Q(username__icontains=text_search)
                | Q(i_user__last_name__icontains=text_search)
                | Q(officer__last_name__icontains=text_search)
                | Q(claim_admin__last_name__icontains=text_search)
                | Q(i_user__other_names__icontains=text_search)
                | Q(officer__other_names__icontains=text_search)
                | Q(claim_admin__other_names__icontains=text_search)
                | Q(i_user__email=text_search)
                | Q(officer__email=text_search)
                | Q(claim_admin__email_id=text_search)
            )

        client_mutation_id = kwargs.get("client_mutation_id", None)
        if client_mutation_id:
            user_filters.append(
                Q(mutations__mutation__client_mutation_id=client_mutation_id)
            )

        if email:
            user_filters.append(
                Q(i_user__email=email)
                | Q(officer__email=email)
                | Q(claim_admin__email_id=email)
            )
        if phone:
            user_filters.append(
                Q(i_user__phone=phone)
                | Q(officer__phone=phone)
                | Q(claim_admin__phone=phone)
            )
        if last_name:
            user_filters.append(
                Q(i_user__last_name__icontains=last_name)
                | Q(officer__last_name__icontains=last_name)
                | Q(claim_admin__last_name__icontains=last_name)
            )
        if other_names:
            user_filters.append(
                Q(i_user__other_names__icontains=other_names)
                | Q(officer__other_names__icontains=other_names)
                | Q(claim_admin__other_names__icontains=other_names)
            )
        if language:
            user_filters.append(Q(i_user__language=language))
            # Language is not applicable to Office/ClaimAdmin
        if health_facility_id:
            user_filters.append(
                Q(i_user__health_facility_id=health_facility_id)
                | Q(officer__location_id=health_facility_id)
                | Q(claim_admin__health_facility_id=health_facility_id)
            )

        if health_facility_uuid:
            health_facility_ids = HealthFacility.objects.filter(
                uuid=health_facility_uuid
            ).values_list("id", flat=True)
            user_filters.append(Q(i_user__health_facility_id__in=health_facility_ids))

        if birth_date_from:
            user_filters.append(
                Q(officer__dob__gte=birth_date_from)
                | Q(officer__veo_dob__gte=birth_date_from)
                | Q(claim_admin__dob__gte=birth_date_from)
            )
        if birth_date_to:
            user_filters.append(
                Q(officer__dob__lte=birth_date_to)
                | Q(officer__veo_dob__lte=birth_date_to)
                | Q(claim_admin__dob__lte=birth_date_to)
            )
        if role_id:
            user_filters.append(
                Q(i_user__user_roles__role_id=role_id)
                & Q(i_user__user_roles__validity_to__isnull=True)
            )
        if roles:
            user_filters.append(
                Q(i_user__user_roles__role_id__in=roles)
                & Q(i_user__user_roles__validity_to__isnull=True)
            )

        if region_id:
            user_filters.append(Q(i_user__userdistrict__location__parent_id=region_id))
        elif region_ids:
            user_filters.append(
                Q(i_user__userdistrict__location__parent_id__in=region_ids)
            )

        if district_id:
            user_filters.append(Q(i_user__userdistrict__location_id=district_id))
        if municipality_id:
            user_filters.append(
                Q(officer__officer_villages__location__parent_id=municipality_id)
            )
        if village_id:
            user_filters.append(Q(officer__officer_villages__location_id=village_id))

        if is_fosa_user is not None:
            user_filters.append(Q(is_fosa_user=is_fosa_user))

        if is_portal_user is not None:
            user_filters.append(Q(is_portal_user=is_portal_user))

        if user_types:
            ut_conditions = {
                UT_INTERACTIVE: Q(i_user__isnull=False),
                UT_OFFICER: Q(officer__isnull=False),
                UT_TECHNICAL: Q(t_user__isnull=False),
                UT_CLAIM_ADMIN: Q(claim_admin__isnull=False),
            }
            user_filters.append(
                reduce(lambda a, b: a | b, [ut_conditions[x] for x in user_types])
            )

        # Do NOT use the query optimizer here ! It would make the t_user, officer etc as deferred fields if they are not
        # explicitly requested in the GraphQL response. However, this prevents the dynamic remapping of the User object.
        return user_query.filter(*user_filters).distinct()

    def resolve_role(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_roles_perms):
            raise PermissionError("Unauthorized")
        filters = []
        query = Role.objects

        text_search = kwargs.get("str")
        if text_search:
            filters.append(Q(name__icontains=text_search))

        client_mutation_id = kwargs.get("client_mutation_id", None)
        if client_mutation_id:
            filters.append(
                Q(mutations__mutation__client_mutation_id=client_mutation_id)
            )

        show_history = kwargs.get("show_history", False)
        if not show_history and not kwargs.get("uuid", None):
            filters += filter_validity(**kwargs)

        is_system_role = kwargs.get("is_system", None)
        # check if we can use default filter validity
        if is_system_role is not None:
            if is_system_role:
                query = query.filter(is_system__gte=1)
            else:
                query = query.filter(is_system=0)

        if system_role_id := kwargs.get("system_role_id", None):
            query = query.filter(is_system=system_role_id)

        return gql_optimizer.query(query.filter(*filters), info)

    def resolve_role_right(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_roles_perms):
            raise PermissionError("Unauthorized")
        filters = []
        if "validity" in kwargs:
            filters += filter_validity(**kwargs)
            return gql_optimizer.query(RoleRight.objects.filter(*filters), info)
        else:
            return gql_optimizer.query(
                RoleRight.objects.filter(validity_to__isnull=True), info
            )

    def resolve_modules_permissions(self, info, **kwargs):
        if not info.context.user.has_perms(CoreConfig.gql_query_roles_perms):
            raise PermissionError("Unauthorized")
        excluded_app = [
            "health_check.cache",
            "health_check",
            "health_check.db",
            "test_without_migrations",
            "test_without_migrations",
            "rules",
            "graphene_django",
            "rest_framework",
            "health_check.storage",
            "channels",
            "graphql_jwt.refresh_token.apps.RefreshTokenConfig",
        ]
        all_apps = [
            app
            for app in settings.INSTALLED_APPS
            if not app.startswith("django") and app not in excluded_app
        ]
        config = []
        for app in all_apps:
            apps = __import__(f"{app}.apps")
            is_default_cfg = hasattr(apps.apps, "DEFAULT_CFG")
            is_defaulf_config = hasattr(apps.apps, "DEFAULT_CONFIG")
            if is_default_cfg or is_defaulf_config:
                if is_defaulf_config:
                    config_dict = ModuleConfiguration.get_or_default(
                        f"{app}", apps.apps.DEFAULT_CONFIG
                    )
                else:
                    config_dict = ModuleConfiguration.get_or_default(
                        f"{app}", apps.apps.DEFAULT_CFG
                    )
                permission = []
                config_dict = flatten_dict(config_dict)
                for key, value in config_dict.items():
                    if key.endswith("_perms"):
                        if isinstance(value, list):
                            for val in value:
                                permission.append(
                                    PermissionOpenImisGQLType(
                                        perms_name=key,
                                        perms_value=val,
                                    )
                                )
                config.append(
                    ModulePermissionGQLType(
                        module_name=app,
                        permissions=permission,
                    )
                )
        return ModulePermissionsListGQLType(list(config))

    def resolve_module_configurations(self, info, **kwargs):
        validity = kwargs.get("validity")
        # configuration is loaded before even the core module
        # the datetime is ALWAYS a Gregorian one
        # (whatever datetime is used in business modules)
        if validity is None:
            validity = py_datetime.now()
        else:
            d = re.split("\D", validity)
            validity = py_datetime(*[int("0" + x) for x in d][:6])
        # is_exposed indicates wherever a configuration
        # is safe to be accessible from api
        # DON'T EXPOSE (backend) configurations that contain credentials,...
        crits = (
            Q(is_disabled_until=None) | Q(is_disabled_until__lt=validity),
            Q(is_exposed=True),
        )
        layer = kwargs.get("layer")
        if layer is not None:
            crits = (*crits, Q(layer=layer))
        return ModuleConfiguration.objects.prefetch_related("controls").filter(*crits)

    def resolve_languages(self, info, **kwargs):
        if not info.context.user.is_authenticated:
            raise PermissionDenied(_("unauthorized"))
        return Language.objects.order_by("sort_order").all()

    def resolve_all_generic_configs(self, info):
        return GenericConfig.objects.all()

    def resolve_generic_config(self, info, model_id):
        return GenericConfig.objects.get(model_id=model_id)


class RoleBase:
    id = graphene.Int(required=False, read_only=True)
    uuid = graphene.String(required=False)
    name = graphene.String(required=True, max_length=50)
    alt_language = graphene.String(required=False, max_length=50)
    is_system = graphene.Boolean(required=True)
    is_blocked = graphene.Boolean(required=True)
    # field to save all chosen rights to the role
    rights_id = graphene.List(graphene.Int, required=False)

    system_role_id = graphene.Int(required=False)


def update_or_create_role(data, user):
    client_mutation_id = data.get("client_mutation_id", None)
    # client_mutation_label = data.get("client_mutation_label", None)

    if "client_mutation_id" in data:
        data.pop("client_mutation_id")
    if "client_mutation_label" in data:
        data.pop("client_mutation_label")
    role_uuid = data.pop("uuid") if "uuid" in data else None
    rights_id = data.pop("rights_id") if "rights_id" in data else None
    if role_uuid:
        role = Role.objects.get(uuid=role_uuid)
        role.save_history()
        [setattr(role, k, v) for k, v in data.items()]
        role.save()
        if rights_id is not None:
            # reset all role rights assigned to the chosen role
            from core import datetime

            now = datetime.datetime.now()
            role_rights_currently_assigned = RoleRight.objects.filter(role_id=role.id)
            role_rights_currently_assigned.update(validity_to=now)
            role_rights_currently_assigned = role_rights_currently_assigned.values_list(
                "right_id", flat=True
            )
            for right_id in rights_id:
                if right_id not in role_rights_currently_assigned:
                    # create role right because it is a new role right
                    RoleRight.objects.create(
                        role_id=role.id,
                        right_id=right_id,
                        audit_user_id=role.audit_user_id,
                        validity_from=now,
                    )
                else:
                    # set date valid to - None
                    role_right = RoleRight.objects.get(
                        Q(role_id=role.id, right_id=right_id)
                    )
                    role_right.validity_to = None
                    role_right.save()
    else:
        role = Role.objects.create(**data)
        # create role rights for that role if they were passed to mutation
        if rights_id:
            [
                RoleRight.objects.create(
                    **{
                        "role_id": role.id,
                        "right_id": right_id,
                        "audit_user_id": role.audit_user_id,
                        "validity_from": data["validity_from"],
                    }
                )
                for right_id in rights_id
            ]
        if client_mutation_id:
            RoleMutation.object_mutated(
                user, role=role, client_mutation_id=client_mutation_id
            )
        return role
    return role


def duplicate_role(data, user):
    client_mutation_id = data.get("client_mutation_id", None)
    # client_mutation_label = data.get("client_mutation_label", None)

    if "client_mutation_id" in data:
        data.pop("client_mutation_id")
    if "client_mutation_label" in data:
        data.pop("client_mutation_label")
    role_uuid = data.pop("uuid") if "uuid" in data else None
    rights_id = data.pop("rights_id") if "rights_id" in data else None
    # get the current Role object to be duplicated
    role = Role.objects.get(uuid=role_uuid)
    # copy Role to be dupliacated
    from core import datetime

    now = datetime.datetime.now()
    duplicated_role = copy(role)
    duplicated_role.id = None
    duplicated_role.uuid = uuid.uuid4()
    duplicated_role.validity_from = now
    [setattr(duplicated_role, k, v) for k, v in data.items()]
    duplicated_role.save()
    if rights_id:
        # reset all role rights assigned to the chosen role
        role_rights_currently_assigned = RoleRight.objects.filter(role_id=role.id)
        role_rights_currently_assigned = role_rights_currently_assigned.values_list(
            "right_id", flat=True
        )
        for right_id in rights_id:
            validity_from = now
            if right_id in role_rights_currently_assigned:
                # role right exist - we can assign validity_from from old entity
                validity_from = role.validity_from
            # create role right for duplicate role
            RoleRight.objects.create(
                **{
                    "role_id": duplicated_role.id,
                    "right_id": right_id,
                    "audit_user_id": duplicated_role.audit_user_id,
                    "validity_from": validity_from,
                }
            )
    else:
        role_rights_currently_assigned = RoleRight.objects.filter(role_id=role.id)
        [
            RoleRight.objects.create(
                **{
                    "role_id": duplicated_role.id,
                    "right_id": role_right.right_id,
                    "audit_user_id": duplicated_role.audit_user_id,
                    "validity_from": now,
                }
            )
            for role_right in role_rights_currently_assigned
        ]

    if client_mutation_id:
        RoleMutation.object_mutated(
            user, role=duplicated_role, client_mutation_id=client_mutation_id
        )

    return duplicated_role


class CreateRoleMutation(OpenIMISMutation):
    """
    Create a new role, with its chosen role right
    """

    _mutation_module = "core"
    _mutation_class = "CreateRoleMutation"

    class Input(RoleBase, OpenIMISMutation.Input):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError("mutation.authentication_required")
            if not user.has_perms(CoreConfig.gql_mutation_create_roles_perms):
                raise PermissionDenied("unauthorized")
            if check_role_unique_name(data.get("name", None)):
                raise ValidationError("mutation.duplicate_of_role_name")
            from core.utils import TimeUtils

            data["validity_from"] = TimeUtils.now()
            data["audit_user_id"] = user.id_for_audit
            update_or_create_role(data, user)
            return None
        except Exception as exc:
            return [
                {"message": "core.mutation.failed_to_create_role", "detail": str(exc)}
            ]


class UpdateRoleMutation(OpenIMISMutation):
    """
    Update a chosen role, with its chosen role right
    """

    _mutation_module = "core"
    _mutation_class = "UpdateRoleMutation"

    class Input(RoleBase, OpenIMISMutation.Input):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError("mutation.authentication_required")
            if not user.has_perms(CoreConfig.gql_mutation_update_roles_perms):
                raise PermissionDenied("unauthorized")
            if "uuid" not in data:
                raise ValidationError("There is no uuid in updateMutation input!")
            if check_role_unique_name(data.get("name", None), data["uuid"]):
                raise ValidationError("mutation.duplicate_of_role_name")
            data["audit_user_id"] = user.id_for_audit
            update_or_create_role(data, user)
            return None
        except Exception as exc:
            return [
                {"message": "core.mutation.failed_to_update_role", "detail": str(exc)}
            ]


def set_role_deleted(role):
    try:
        role.delete_history()
        return []
    except Exception as exc:
        return {
            "title": role.uuid,
            "list": [
                {
                    "message": "role.mutation.failed_to_change_status_of_role"
                    % {"role": str(role)},
                    "detail": role.uuid,
                }
            ],
        }


class DeleteRoleMutation(OpenIMISMutation):
    """
    Delete a chosen role
    """

    _mutation_module = "core"
    _mutation_class = "DeleteRoleMutation"

    class Input(OpenIMISMutation.Input):
        uuids = graphene.List(graphene.String)

    @classmethod
    def async_mutate(cls, user, **data):
        if not user.has_perms(CoreConfig.gql_mutation_delete_roles_perms):
            raise PermissionDenied("unauthorized")
        errors = []
        for role_uuid in data["uuids"]:
            role = Role.objects.filter(uuid=role_uuid).first()
            if role is None:
                errors.append(
                    {
                        "title": role,
                        "list": [
                            {
                                "message": "role.validation.id_does_not_exist"
                                % {"id": role_uuid}
                            }
                        ],
                    }
                )
                continue
            errors += set_role_deleted(role)
        if len(errors) == 1:
            errors = errors[0]["list"]
        return errors


class DuplicateRoleMutation(OpenIMISMutation):
    """
    Duplicate a chosen role
    """

    _mutation_module = "core"
    _mutation_class = "DuplicateRoleMutation"

    class Input(OpenIMISMutation.Input):
        uuid = graphene.String(required=True)
        name = graphene.String(required=True, max_length=50)
        alt_language = graphene.String(required=False, max_length=50)
        is_system = graphene.Boolean(required=True)
        is_blocked = graphene.Boolean(required=True)
        # field to save all chosen rights to the role
        rights_id = graphene.List(graphene.Int, required=False)

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError("mutation.authentication_required")
            if not user.has_perms(CoreConfig.gql_mutation_duplicate_roles_perms):
                raise PermissionDenied("unauthorized")
            data["audit_user_id"] = user.id_for_audit
            duplicate_role(data, user)
            return None
        except Exception as exc:
            return [
                {
                    "message": "core.mutation.failed_to_duplicate_role",
                    "detail": str(exc),
                }
            ]


class UserBase:
    uuid = graphene.String(
        required=False,
        read_only=True,
        description="UUID of the core User, one can leave this blank and specify the username instead",
    )
    user_id = graphene.String(required=False)
    other_names = graphene.String(required=True, max_length=50)
    last_name = graphene.String(required=True, max_length=50)
    username = graphene.String(required=True, max_length=8)
    phone = graphene.String(required=False)
    email = graphene.String(required=False)
    password = graphene.String(required=False)
    current_password = graphene.String(required=False)
    health_facility_id = graphene.Int(required=False)
    policy_holder_id = graphene.String(required=False)
    insuree_id = graphene.Int(required=False)
    date_valid_from = graphene.String(required=False)
    districts = graphene.List(graphene.Int, required=False)
    language = graphene.String(required=True, description="Language code for the user")
    # Interactive User only
    roles = graphene.List(
        graphene.Int,
        required=False,
        description="List of role_ids, required for interactive users",
    )

    # Enrolment Officer / Feedback / Claim Admin specific
    birth_date = graphene.Date(required=False)
    address = graphene.String(required=False)  # multi-line
    works_to = graphene.DateTime(required=False)
    substitution_officer_id = graphene.Int(required=False)
    station_id = graphene.Int(required=False)
    # TODO VEO_code, last_name, other names, dob, phone
    phone_communication = graphene.Boolean(required=False)
    location_id = graphene.Int(
        required=False, description="Location for the Enrolment Officer"
    )
    village_ids = graphene.List(graphene.Int, required=False)

    user_types = graphene.List(UserTypeEnum, required=True)


class CreateUserMutation(OpenIMISMutation):
    """
    Create a new user, the "core" one but also Interactive, Technical, Officer or Admin
    """

    _mutation_module = "core"
    _mutation_class = "CreateUserMutation"

    class Input(UserBase, OpenIMISMutation.Input):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError("mutation.authentication_required")
            if User.objects.filter(username=data["username"]).exists():
                raise ValidationError("User with this user name already exists.")
            if not user.has_perms(CoreConfig.gql_mutation_create_users_perms):
                raise PermissionDenied("unauthorized")
            from core.utils import TimeUtils

            data["validity_from"] = TimeUtils.now()
            data["audit_user_id"] = user.id_for_audit
            data["current_user_id"] = user.id
            update_or_create_user(data, user)
            return None
        except Exception as exc:
            return [
                {"message": "core.mutation.failed_to_create_user", "detail": str(exc)}
            ]


class UpdateUserMutation(OpenIMISMutation):
    """
    Update an existing User and sub-user types
    """

    _mutation_module = "core"
    _mutation_class = "UpdateUserMutation"

    class Input(UserBase, OpenIMISMutation.Input):
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError("mutation.authentication_required")
            if not user.has_perms(CoreConfig.gql_mutation_update_users_perms):
                raise PermissionDenied("unauthorized")
            from core.utils import TimeUtils

            data["validity_from"] = TimeUtils.now()
            data["audit_user_id"] = user.id_for_audit
            data["current_user_id"] = user.id
            update_or_create_user(data, user)
            return None
        except Exception as exc:
            return [
                {"message": "core.mutation.failed_to_update_user", "detail": str(exc)}
            ]


class DeleteUserMutation(OpenIMISMutation):
    """
    Delete a chosen user
    """

    _mutation_module = "core"
    _mutation_class = "DeleteUserMutation"

    class Input(OpenIMISMutation.Input):
        uuids = graphene.List(graphene.String)

    @classmethod
    def async_mutate(cls, user, **data):
        if not user.has_perms(CoreConfig.gql_mutation_delete_users_perms):
            raise PermissionDenied("unauthorized")
        errors = []
        for user_uuid in data["uuids"]:
            user = User.objects.filter(id=user_uuid).first()
            if user is None:
                errors.append(
                    {
                        "title": user,
                        "list": [
                            {
                                "message": "user.validation.id_does_not_exist"
                                % {"id": user_uuid}
                            }
                        ],
                    }
                )
                continue
            errors += set_user_deleted(user)
        if len(errors) == 1:
            errors = errors[0]["list"]
        return errors


@transaction.atomic
@validate_payload_for_obligatory_fields(CoreConfig.fields_controls_user, "data")
def update_or_create_user(data, user):
    from policyholder.models import PolicyHolderUser, PolicyHolder
    from core.models import InteractiveUser

    client_mutation_id = data.get("client_mutation_id", None)
    # client_mutation_label = data.get("client_mutation_label", None)

    # FOSA USER ACTIVE IS TRUE FOR IS_FOSA_USER AND VERIFY TRUE
    data["is_fosa_user"] = True if data.get("health_facility_id") is not None else False
    data["is_portal_user"] = True if data.get("policy_holder_id") is not None else False

    policy_holder_id = (
        data.pop("policy_holder_id") if data.get("policy_holder_id") else None
    )
    date_valid_from = (
        data.pop("date_valid_from") if data.get("date_valid_from") else None
    )

    incoming_email = data.get("email")
    current_user = None
    if "uuid" in data and data["uuid"]:
        current_user = InteractiveUser.objects.filter(user__id=data["uuid"]).first()
    station_id = data.get("station_id") if "station_id" in data.keys() else None
    if station_id:
        station = Station.objects.get(pk=station_id)
    else:
        station = None
    current_email = current_user.email if current_user else None

    if incoming_email:
        if not check_email_validity(incoming_email):
            raise ValidationError(_("mutation.user_email_invalid"))
        if current_email != incoming_email:
            if check_user_unique_email(user_email=data["email"]):
                raise ValidationError(_("mutation.user_email_duplicated"))
    else:
        raise ValidationError(_("mutation.user_no_email_provided"))

    username = data.get("username")

    if len(username) > CoreConfig.username_code_length:
        raise ValidationError(_("mutation.user_username_too_long"))

    if "client_mutation_id" in data:
        data.pop("client_mutation_id")
    if "client_mutation_label" in data:
        data.pop("client_mutation_label")
    user_uuid = data.pop("uuid") if "uuid" in data else None

    if UT_INTERACTIVE in data["user_types"]:
        if type(user) is AnonymousUser or not user.id:
            i_user, i_user_created = create_or_update_interactive_user(
                user_uuid, data, -1, len(data["user_types"]) > 1
            )
        else:
            i_user, i_user_created = create_or_update_interactive_user(
                user_uuid, data, user.id_for_audit, len(data["user_types"]) > 1
            )
    else:
        i_user, i_user_created = None, False
    if UT_OFFICER in data["user_types"]:
        officer, officer_created = create_or_update_officer(
            user_uuid, data, user.id_for_audit, UT_INTERACTIVE in data["user_types"]
        )
    else:
        officer, officer_created = None, False
    if UT_CLAIM_ADMIN in data["user_types"]:
        claim_admin, claim_admin_created = create_or_update_claim_admin(
            user_uuid, data, user.id_for_audit, UT_INTERACTIVE in data["user_types"]
        )
    else:
        claim_admin, claim_admin_created = None, False

    core_user, core_user_created = create_or_update_core_user(
        user_uuid=user_uuid,
        username=username,
        i_user=i_user,
        officer=officer,
        claim_admin=claim_admin,
        station=station,
        is_fosa_user=data["is_fosa_user"],
        is_portal_user=data["is_portal_user"],
    )

    # create policy holder user
    print("======> create policy holder user")
    if policy_holder_id:
        policy_holder = PolicyHolder.objects.filter(id=policy_holder_id).first()
        if not policy_holder:
            raise ValidationError(_("mutation.policy_holder_not_found"))

        object_data = {
            "user": core_user,
            "policy_holder": policy_holder,
            "date_valid_from": date_valid_from,
        }

        print(f"======> create policy holder user object_data: {object_data}")

        info_user = InteractiveUser.objects.filter(
            validity_to__isnull=True, user__id=user.id
        ).first()

        print(f"======> create policy holder user info_user: {info_user}")

        check_policy_holder_user = PolicyHolderUser.objects.filter(
            user=core_user, policy_holder=policy_holder
        ).first()

        i_user = InteractiveUser.objects.filter(
            validity_to__isnull=True, user__id=user.id
        ).first()

        if check_policy_holder_user is None:
            print("======> create policy holder user")
            obj = PolicyHolderUser(**object_data)
            obj.save(username=info_user.username)

        create_audit_user_service(
            i_user,
            core_user_created,
            core_user.id,
            data["current_user_id"],
            data,
        )
    # create policy holder user

    if client_mutation_id:
        UserMutation.object_mutated(
            user, core_user=core_user, client_mutation_id=client_mutation_id
        )
    return core_user


def check_email_validity(email):
    # checks if string is a valid email address
    # using regex provided in the HTML5 standard
    # it omits some RFC recommendations by design
    # https://html.spec.whatwg.org/multipage/input.html#valid-e-mail-address
    import re

    regex = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9]"
        r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
    )
    if not re.fullmatch(regex, email):
        return False
    return True


def set_user_deleted(user):
    try:
        if user.i_user:
            user.i_user.delete_history()
            try:
                from workflow.models import WF_Profile_Queue

                WF_Profile_Queue.objects.filter(
                    is_action_taken=False, user_id=user
                ).update(user_id=None, is_assigned=False)
            except Exception as e:
                logger.info(
                    "failed to delete dependency from WF_Profile_Queue for"
                    % {"user": str(user)}
                )
        if user.t_user:
            user.t_user.delete_history()
        if user.officer:
            user.officer.delete_history()
        if user.claim_admin:
            user.claim_admin.delete_history()
        user.delete()  # TODO: we might consider disabling Users instead of deleting entirely.
        return []
    except Exception as exc:
        logger.info(
            "role.mutation.failed_to_change_status_of_user" % {"user": str(user)}
        )
        return {
            "title": user.id,
            "list": [
                {
                    "message": "role.mutation.failed_to_change_status_of_user"
                    % {"user": str(user)},
                    "detail": user.id,
                }
            ],
        }


class CheckAssignedProfiles(graphene.Mutation):
    status = graphene.Boolean()

    class Arguments:
        user_id = graphene.UUID(required=True)

    def mutate(self, info, user_id):
        user = User.objects.filter(id=user_id).first()

        try:
            i_user = user.i_user
            logger.info(f"i_user retrieved: {i_user}")

            approver_role = Role.objects.filter(
                name__iexact=APPROVER_ROLE, legacy_id__isnull=True
            ).first()
            logger.info(f"Approver roles retrieved: {approver_role}")
            print("approver_role : ", approver_role)
            # for approver_role in approver_roles:
            has_approver_role = UserRole.objects.filter(
                user=i_user, role=approver_role
            ).exists()
            logger.info(f"User has approver role: {has_approver_role}")
            print("has_approver_role : ", has_approver_role)
            if has_approver_role:
                user_profile_queues = WF_Profile_Queue.objects.filter(
                    user_id_id=user.id, is_assigned=True, is_action_taken=False
                ).first()
                logger.info(f"User profile queues found: {user_profile_queues}")

                if user_profile_queues:
                    WF_Profile_Queue.objects.filter(id=user_profile_queues.id).update(
                        user_id=None, is_assigned=False
                    )

                    Insuree.objects.filter(
                        family_id=user_profile_queues.family.id,
                        legacy_id__isnull=True,
                        status=STATUS_WAITING_FOR_APPROVAL,
                    ).update(status=STATUS_WAITING_FOR_QUEUE)
                    head_insuree = Insuree.objects.filter(
                        family_id=user_profile_queues.family.id,
                        legacy_id__isnull=True,
                        head=True,
                    ).first()

                    if head_insuree and head_insuree.status == STATUS_WAITING_FOR_QUEUE:
                        Family.objects.filter(id=user_profile_queues.family.id).update(
                            status=STATUS_WAITING_FOR_QUEUE
                        )
                    # user_profile_queues.update(user_id=None, is_assigned=False)
                    print("=============  unassigned profile  ==============")
                    logger.info("User profile queues updated")

        except UserRole.DoesNotExist:
            logger.error("User role does not exist.")
        except Role.DoesNotExist:
            logger.error("Role 'approver' does not exist.")

        return CheckAssignedProfiles(status=True)


class CreateGenericConfig(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        model_name = graphene.String(required=True)
        model_id = graphene.String(required=True)
        json_ext = graphene.String(required=True)

    generic_config = graphene.Field(GenericConfigType)

    @staticmethod
    def mutate(root, info, name, model_name, model_id, json_ext):
        generic_config = GenericConfig(
            name=name, model_name=model_name, model_id=model_id, json_ext=json_ext
        )
        generic_config.save()
        return CreateGenericConfig(generic_config=generic_config)


class UpdateGenericConfig(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        model_id = graphene.String(required=True)
        model_name = graphene.String()
        json_ext = graphene.String(required=True)

    generic_config = graphene.Field(GenericConfigType)

    @staticmethod
    def mutate(root, info, model_id, **kwargs):
        generic_config = GenericConfig.objects.get(model_id=model_id)
        for key, value in kwargs.items():
            setattr(generic_config, key, value)
        generic_config.save()
        return UpdateGenericConfig(generic_config=generic_config)


class DeleteGenericConfig(graphene.Mutation):
    success = graphene.Boolean()

    class Arguments:
        config_id = graphene.UUID()

    def mutate(self, info, config_id):
        config = GenericConfig.objects.get(id=config_id)
        if config:
            config.delete()
            return DeleteGenericConfig(success=True)
        return DeleteGenericConfig(success=False)


class ChangePasswordMutation(graphene.relay.ClientIDMutation):
    """
    Change a user's password. Either the user can update his own by providing the old password, or an administrator
    (actually someone with the rights to update users) can force it for anyone without providing the old password.
    """

    class Input:
        username = graphene.String(
            required=False,
            description="By default, this operation works on the logged user,"
            "only administrators can run it on any user",
        )
        old_password = graphene.String(
            required=False,
            description="Mandatory to change the current user password, administrators can leave this blank",
        )
        new_password = graphene.String(required=True, description="New password to set")

    success = graphene.Boolean()
    error = graphene.String()

    @classmethod
    def mutate_and_get_payload(
        cls, root, info, new_password, old_password=None, username=None, **input
    ):
        try:
            user = info.context.user
            if type(user) is AnonymousUser or not user.id:
                raise ValidationError("mutation.authentication_required")
            change_user_password(
                user,
                username_to_update=username,
                old_password=old_password if not username else None,
                new_password=new_password,
            )
            return ChangePasswordMutation(success=True)
        except Exception as exc:
            logger.exception(exc)
            return ChangePasswordMutation(
                success=False,
                error=gettext_lazy("Failed to change user password"),
            )


class ResetPasswordMutation(graphene.relay.ClientIDMutation):
    """
    Recover a user' account using its username or e-mail address.
    """

    class Input:
        username = graphene.String(
            required=True,
            description=gettext_lazy("Username of the account to recover"),
        )
        is_portal = graphene.Boolean(required=False)

    success = graphene.Boolean()
    error = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, root, info, username, is_portal=False, **input):
        try:
            reset_user_password(info.context, username, is_portal)
            return ResetPasswordMutation(success=True)
        except Exception as exc:
            logger.exception(exc)
            return ResetPasswordMutation(
                success=False,
                error=gettext_lazy("Failed to reset password."),
            )


class SetPasswordMutation(graphene.relay.ClientIDMutation):
    """
    Set a password using a pre-generated token received by email
    """

    class Input:
        username = graphene.String(
            required=True, description=gettext_lazy("Username of the user")
        )
        token = graphene.String(
            required=False, description=gettext_lazy("Token used to validate the user")
        )
        new_password = graphene.String(
            required=True, description=gettext_lazy("New password for the user")
        )
        is_portal = graphene.Boolean(required=False)

    success = graphene.Boolean()
    error = graphene.String()

    @classmethod
    def mutate_and_get_payload(
        cls,
        root,
        info,
        username,
        token=None,
        new_password=None,
        is_portal=False,
        **input,
    ):
        try:
            set_user_password(info.context, username, token, new_password, is_portal)
            return SetPasswordMutation(success=True)
        except Exception as exc:
            logger.exception(exc)
            return SetPasswordMutation(
                success=False,
                error=gettext_lazy("Failed to set password."),
            )


class OpenimisObtainJSONWebToken(mixins.ResolveMixin, JSONWebTokenMutation):
    """Obtain JSON Web Token mutation, with auto-provisioning from tblUsers"""

    class Arguments:
        is_portal = graphene.Boolean(required=False)
        is_fosa_user = graphene.Boolean(required=False)

    @classmethod
    def mutate(cls, root, info, is_portal=False, is_fosa_user=False, **kwargs):
        username = kwargs.get("username")

        if username:
            user_tuple = User.objects.get_or_create(username=username)
            print(f"------------------------- LOGIN 0 {user_tuple}")

            if len(user_tuple) > 0:
                user_data = user_tuple[0]
                # Portal user login check
                if is_portal:
                    if not user_data.is_portal_user:
                        raise JSONWebTokenError(_("Please enter valid credentials"))
                    if not user_data.i_user.is_verified:
                        raise JSONWebTokenError(_("User is not verified"))
                # FOSA user login check
                elif is_fosa_user:
                    if not user_data.is_fosa_user:
                        raise JSONWebTokenError(_("Please enter valid credentials"))
                    if not user_data.i_user.is_verified:
                        raise JSONWebTokenError(_("User is not verified"))
                # Normal user login check (if neither Portal nor FOSA)
                else:
                    if user_data.is_portal_user or user_data.is_fosa_user:
                        raise JSONWebTokenError(_("Please enter valid credentials"))

                print("------------------------- LOGIN 1")
                cls.update_profile_queue_for_approver(user_data)
            else:
                logger.debug(
                    "Authentication with %s failed and could not be fetched from tblUsers",
                    username,
                )
        return super().mutate(cls, info, **kwargs)

    def update_profile_queue_for_approver(user):
        try:
            print("------------------------- LOGIN 2")
            i_user = user[0].i_user
            logger.info(f"i_user retrieved: {i_user}")

            approver_role = Role.objects.filter(name=APPROVER_ROLE).first()
            logger.info(f"Approver role retrieved: {approver_role}")

            has_approver_role = UserRole.objects.filter(
                user=i_user, role=approver_role
            ).exists()
            print("------------------------- LOGIN 3")
            logger.info(f"User has approver role: {has_approver_role}")
            print("has_approver_role : ", has_approver_role)
            WF_Profile_Queue.objects.filter(
                is_action_taken=False, family__validity_to__isnull=False
            ).delete()
            WF_Profile_Queue.objects.filter(
                is_action_taken=False, family__head_insuree__validity_to__isnull=False
            ).delete()
            print("------------------------- LOGIN 4")
            if has_approver_role:
                # user_profile_queue = WF_Profile_Queue.objects.filter(
                #     user_id__pro_que_user=user[0].id,
                #     is_assigned=True,
                #     is_action_taken=False
                # )
                print("------------------------- LOGIN 5")
                user_profile_queue = WF_Profile_Queue.objects.filter(
                    user_id__id=user[0].id, is_assigned=True, is_action_taken=False
                ).first()
                print("user_profile_queue : ", user_profile_queue)
                logger.info(f"User profile queue found: {user_profile_queue}")

                print("------------------------- LOGIN 6")

                if not user_profile_queue:
                    records_with_null_user_id = WF_Profile_Queue.objects.filter(
                        user_id__pro_que_user__isnull=True,
                        is_assigned=False,
                        is_action_taken=False,
                    ).first()
                    print("------------------------- LOGIN 7")
                    print("records_with_null_user_id : ", records_with_null_user_id)
                    if records_with_null_user_id:
                        print("==========   profile assigned  ==============")
                        print("------------------------- LOGIN 8")
                        WF_Profile_Queue.objects.filter(
                            id=records_with_null_user_id.id
                        ).update(user_id_id=user[0].id, is_assigned=True)

                        Insuree.objects.filter(
                            family_id=records_with_null_user_id.family.id,
                            legacy_id__isnull=True,
                            status=STATUS_WAITING_FOR_QUEUE,
                        ).update(status=STATUS_WAITING_FOR_APPROVAL)
                        head_insuree = Insuree.objects.filter(
                            family_id=records_with_null_user_id.family.id,
                            legacy_id__isnull=True,
                            head=True,
                        ).first()
                        print("------------------------- LOGIN 9")
                        if head_insuree.status == STATUS_WAITING_FOR_APPROVAL:
                            print("------------------------- LOGIN 10")
                            Family.objects.filter(
                                id=records_with_null_user_id.family.id
                            ).update(status=STATUS_WAITING_FOR_APPROVAL)
                        # records_with_null_user_id.update(user_id=user[0].id, is_assigned=True)
                        print("------------------------- LOGIN 11")
                        logger.info("Records with null user_id updated")
            else:
                logger.info("This user does not have the 'approver' role.")

        except Role.DoesNotExist:
            logger.error("The 'approver' role does not exist.")
        except UserRole.DoesNotExist:
            logger.error("No user role found.")
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")


class ERPReSyncMutation(graphene.Mutation):
    class Arguments:
        ids = graphene.List(graphene.Int, required=True)

    success = graphene.Boolean()
    message = graphene.String()
    resync_status = graphene.String()

    def mutate(self, info, **kwargs):
        ids = kwargs.get("ids", [])
        user = info.context.user

        results = []

        def update_or_create_resync_wrapper(id, user):
            try:
                resync_status = update_or_create_resync(id, user)
                results.append(
                    (
                        True,
                        f"ERP API logs for ID {id} updated successfully.",
                        resync_status,
                    )
                )
            except Exception as e:
                logger.error(f"Failed to save ERP API logs for ID {id}: {str(e)}")
                results.append(
                    (False, f"Failed to save ERP API logs for ID {id}: {str(e)}", None)
                )

        threads = []
        for id in ids:
            thread = threading.Thread(
                target=update_or_create_resync_wrapper, args=(id, user)
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        success = all(res[0] for res in results)
        messages = "\n".join(res[1] for res in results)
        resync_status = "\n".join(str(res[2]) for res in results if res[2] is not None)

        return ERPReSyncMutation(
            success=success, resync_status=resync_status, message=messages
        )


class MarkNotificationAsRead(graphene.Mutation):
    class Arguments:
        user_id = graphene.String(required=True)
        notification_id = graphene.String(required=False)
        read_all = graphene.Boolean(required=False, default_value=False)

    success = graphene.Boolean()

    def mutate(self, info, user_id, notification_id=None, read_all=False):
        try:
            user = User.objects.get(id=user_id)

            if read_all:
                updated_count = CamuNotification.objects.filter(
                    user=user, is_read=False
                ).update(is_read=True)
                logger.info(
                    f"All notifications for user {user_id} marked as read. Total: {updated_count}"
                )
            elif notification_id:
                notification = CamuNotification.objects.get(
                    id=notification_id, user=user
                )
                notification.mark_as_read()
                logger.info(
                    f"Notification {notification_id} for user {user_id} marked as read."
                )
            else:
                logger.warning(
                    f"No action taken for user {user_id}: notification_id and read_all are both not set."
                )
                return MarkNotificationAsRead(success=False)

            return MarkNotificationAsRead(success=True)
        except User.DoesNotExist:
            logger.error(f"User {user_id} does not exist.")
            return MarkNotificationAsRead(success=False)
        except CamuNotification.DoesNotExist:
            logger.error(
                f"Notification {notification_id} does not exist for user {user_id}."
            )
            return MarkNotificationAsRead(success=False)


class BanksInput(graphene.InputObjectType):
    id = graphene.String()
    name = graphene.String()
    alt_lang_name = graphene.String()
    code = graphene.String()
    erp_id = graphene.Int()
    journaux_id = graphene.Int()


class CreateBanks(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    banks = graphene.Field(BanksType)

    class Arguments:
        input = BanksInput(required=True)

    def mutate(self, info, input):
        user = info.context.user
        try:
            banks = Banks(
                name=input.name,
                alt_lang_name=input.alt_lang_name,
                code=input.code,
                erp_id=input.erp_id,
                journaux_id=input.journaux_id,
            )
            banks.save(username=user.username)
            logger.info(f"Banks created by {user.username}: {banks}")
            return CreateBanks(
                success=True, message="Created Successfully.", banks=banks
            )
        except Exception as e:
            logger.error(f"Error creating Banks: {e}")
            raise GraphQLError("Failed to create Banks.")


class UpdateBanks(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    banks = graphene.Field(BanksType)

    class Arguments:
        input = BanksInput()

    def mutate(self, info, input):
        id = input.id
        user = info.context.user
        try:
            banks = Banks.objects.get(pk=id)
            if not banks:
                return UpdateBanks(
                    success=False,
                    message=f"Banks with ID {id} not found for update.",
                    banks=None,
                )
            reset_banks_before_save(banks)
            for key, value in input.items():
                if value is not None:
                    setattr(banks, key, value)

            banks.save(username=user.username)
            logger.info(f"Banks updated by {user.username}: {banks}")
            return UpdateBanks(
                success=True, message="Updated Successfully.", banks=banks
            )
        except ObjectDoesNotExist:
            logger.warning(f"Banks with ID {id} not found for update.")
            raise GraphQLError(f"Banks with ID {id} does not exist.")
        except Exception as e:
            logger.error(f"Error updating Banks: {e}")
            raise GraphQLError("Failed to update Banks.")


class DeleteBanks(graphene.Mutation):
    success = graphene.Boolean()

    class Arguments:
        input = BanksInput()

    def mutate(self, info, input):
        id = input.id
        try:
            user = info.context.user
            banks = Banks.objects.get(pk=id)
            banks.is_deleted = True
            banks.save(username=user.username)
            logger.info(f"Banks marked as deleted by {user.username}: {banks}")
            return DeleteBanks(success=True)
        except ObjectDoesNotExist:
            logger.warning(f"Banks with ID {id} not found for deletion.")
            raise GraphQLError(f"Banks with ID {id} does not exist.")
        except Exception as e:
            logger.error(f"Error deleting Banks: {e}")
            raise GraphQLError("Failed to delete Banks.")


class ErpOperationsInput(graphene.InputObjectType):
    id = graphene.String()
    name = graphene.String()
    alt_lang_name = graphene.String()
    erp_id = graphene.Int()
    access_id = graphene.String()
    accounting_id = graphene.Int()


class CreateErpOperations(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    erp_operations = graphene.Field(ErpOperationsType)

    class Arguments:
        input = ErpOperationsInput(required=True)

    def mutate(self, info, input):
        user = info.context.user
        try:
            erp_operations = ErpOperations(
                name=input.name,
                alt_lang_name=input.alt_lang_name,
                erp_id=input.erp_id,
                access_id=input.access_id,
                accounting_id=input.accounting_id,
            )
            erp_operations.save(username=user.username)
            logger.info(f"ErpOperations created by {user.username}: {erp_operations}")
            return CreateErpOperations(
                success=True,
                message="Created Successfully.",
                erp_operations=erp_operations,
            )
        except Exception as e:
            logger.error(f"Error creating ErpOperations: {e}")
            raise GraphQLError("Failed to create ErpOperations.")


class UpdateErpOperations(graphene.Mutation):
    success = graphene.Boolean()
    message = graphene.String()
    erp_operations = graphene.Field(ErpOperationsType)

    class Arguments:
        input = ErpOperationsInput()

    def mutate(self, info, input):
        id = input.id
        user = info.context.user
        try:
            erp_operations = ErpOperations.objects.get(pk=id)
            if not erp_operations:
                return UpdateErpOperations(
                    success=False,
                    message=f"ErpOperations with ID {id} not found for update.",
                    erp_operations=None,
                )
            reset_erp_op_before_save(erp_operations)
            for key, value in input.items():
                if value is not None:
                    setattr(erp_operations, key, value)
            erp_operations.save(username=user.username)
            logger.info(f"ErpOperations updated by {user.username}: {erp_operations}")
            return UpdateErpOperations(
                success=True,
                message="Updated Successfully.",
                erp_operations=erp_operations,
            )

        except ErpOperations.DoesNotExist:
            logger.warning(f"ErpOperations with ID {id} not found for update.")
            raise GraphQLError(f"ErpOperations with ID {id} does not exist.")
        except Exception as e:
            logger.error(f"Error updating ErpOperations: {e}")
            raise GraphQLError("Failed to update ErpOperations.")


class DeleteErpOperations(graphene.Mutation):
    success = graphene.Boolean()

    class Arguments:
        input = ErpOperationsInput()

    def mutate(self, info, input):
        id = input.id
        try:
            user = info.context.user
            erp_operations = ErpOperations.objects.get(pk=id)
            erp_operations.is_deleted = True
            erp_operations.save(username=user.username)
            logger.info(
                f"ErpOperations marked as deleted by {user.username}: {erp_operations}"
            )
            return DeleteErpOperations(success=True)
        except ObjectDoesNotExist:
            logger.warning(f"ErpOperations with ID {id} not found for deletion.")
            raise GraphQLError(f"ErpOperations with ID {id} does not exist.")
        except Exception as e:
            logger.error(f"Error deleting ErpOperations: {e}")
            raise GraphQLError("Failed to delete ErpOperations.")


class Mutation(graphene.ObjectType):
    create_role = CreateRoleMutation.Field()
    update_role = UpdateRoleMutation.Field()
    delete_role = DeleteRoleMutation.Field()
    duplicate_role = DuplicateRoleMutation.Field()

    create_user = CreateUserMutation.Field()
    update_user = UpdateUserMutation.Field()
    delete_user = DeleteUserMutation.Field()

    change_password = ChangePasswordMutation.Field()
    reset_password = ResetPasswordMutation.Field()
    set_password = SetPasswordMutation.Field()

    token_auth = OpenimisObtainJSONWebToken.Field()
    verify_token = graphql_jwt.mutations.Verify.Field()
    refresh_token = graphql_jwt.mutations.Refresh.Field()
    revoke_token = graphql_jwt.mutations.Revoke.Field()

    delete_token_cookie = graphql_jwt.DeleteJSONWebTokenCookie.Field()
    delete_refresh_token_cookie = graphql_jwt.DeleteRefreshTokenCookie.Field()
    check_assigned_profiles = CheckAssignedProfiles.Field()
    create_generic_config = CreateGenericConfig.Field()
    # update_generic_config = UpdateGenericConfig.Field()
    delete_generic_config = DeleteGenericConfig.Field()
    erp_resync_mutation = ERPReSyncMutation.Field()
    mark_notification_as_read = MarkNotificationAsRead.Field()
    create_erp_operations = CreateErpOperations.Field()
    update_erp_operations = UpdateErpOperations.Field()
    delete_erp_operations = DeleteErpOperations.Field()
    create_banks = CreateBanks.Field()
    update_banks = UpdateBanks.Field()
    delete_banks = DeleteBanks.Field()


def on_role_mutation(sender, **kwargs):
    uuid = kwargs["data"].get("uuid", None)
    if not uuid:
        return []

    # For duplicate log is created in the duplicate_role function, mutation log added here would reference original role
    if (
        "Role" in str(sender._mutation_class)
        and sender._mutation_class != "DuplicateRoleMutation"
    ):
        impacted = Role.objects.get(uuid=uuid)
        RoleMutation.objects.create(
            role=impacted, mutation_id=kwargs["mutation_log_id"]
        )

    return []


def on_user_mutation(sender, **kwargs):
    uuid = kwargs["data"].get("uuid", None)
    if not uuid:
        return []

    # For duplicate log is created in the duplicate_role function, mutation log added here would reference original role
    if "User" in str(sender._mutation_class):
        impacted = User.objects.get(id=uuid)
        UserMutation.objects.create(
            core_user=impacted, mutation_id=kwargs["mutation_log_id"]
        )

    return []


def bind_signals():
    signal_mutation_module_validate["core"].connect(on_role_mutation)
    signal_mutation_module_validate["core"].connect(on_user_mutation)
