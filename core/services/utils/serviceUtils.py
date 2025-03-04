import json
from typing import Union

from django.apps import apps
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict

from core.models import AuditLogs
import logging
logger = logging.getLogger(__name__)

def check_authentication(function):
    def wrapper(self, *args, **kwargs):
        if type(self.user) is AnonymousUser or not self.user.id:
            return {
                "success": False,
                "message": "Authentication required",
                "detail": "PermissionDenied",
            }
        else:
            result = function(self, *args, **kwargs)
            return result

    return wrapper


def check_permissions(permissions=None):
    def decorator(function):
        def wrapper(self, *args, **kwargs):
            if not self.user.has_perms(permissions):
                return {
                    "success": False,
                    "message": "Permissions required",
                    "detail": "PermissionDenied",
                }
            else:
                result = function(self, *args, **kwargs)
                return result

        return wrapper

    return decorator


def model_representation(model):
    uuid_string = str(model.id)
    dict_representation = model_to_dict(model)
    dict_representation["id"], dict_representation["uuid"] = (str(uuid_string), str(uuid_string))
    return dict_representation


def output_exception(model_name, method, exception):
    return {
        "success": False,
        "message": f"Failed to {method} {model_name}",
        "detail": str(exception),
        "data": "",
    }


def output_result_success(dict_representation):
    return {
        "success": True,
        "message": "Ok",
        "detail": "",
        "data": json.loads(json.dumps(dict_representation, cls=DjangoJSONEncoder)),
    }


def build_delete_instance_payload():
    return {
        "success": True,
        "message": "Ok",
        "detail": "",
    }


def get_generic_type(generic_type: Union[str, ContentType]):
    if isinstance(generic_type, ContentType):
        return generic_type
    elif isinstance(generic_type, str):
        return ContentType.objects.get(model=generic_type.lower())
    else:
        return ContentType.objects.get(model=str(generic_type).lower())


def save_audit_log(app_name, model_name, audit_for, action, new_obj, old_obj, audit_by_id):
    logger.info("Saving audit log")
    new_obj_id = None
    old_obj_id = None
    json_ext = None
    if audit_for == "insuree" and model_name == "Insuree":
        new_obj_id = new_obj.uuid if new_obj else None
        old_obj_id = old_obj.uuid if old_obj else None
        json_ext = {
            "chf_id": new_obj.chf_id,
            "camu_number": new_obj.camu_number,
            "other_names": new_obj.other_names,
            "last_name": new_obj.last_name,
        }
        logger.info("JSON extension created for insuree/Insuree audit log")
    elif audit_for == "family" and model_name == "Family":
        new_obj_id = new_obj.uuid if new_obj else None
        old_obj_id = old_obj.uuid if old_obj else None
        json_ext = {
            "chf_id": new_obj.head_insuree.chf_id,
            "camu_number": new_obj.head_insuree.camu_number,
            "other_names": new_obj.head_insuree.other_names,
            "last_name": new_obj.head_insuree.last_name,
        }
        logger.info("JSON extension created for family/Insuree audit log")
    elif audit_for == "family" and model_name == "Insuree":
        if new_obj and new_obj.family:
            new_obj_id = new_obj.family.uuid
        if old_obj and old_obj.family:
            old_obj_id = old_obj.family.uuid
        if not new_obj_id or new_obj_id is None:
            new_obj_id = old_obj_id
            
        json_ext = {
            "chf_id": new_obj.chf_id,
            "camu_number": new_obj.camu_number,
            "other_names": new_obj.other_names,
            "last_name": new_obj.last_name,
        }
        logger.info("JSON extension created for family/Family audit log")

    AuditLogs.objects.create(
        app_name=app_name,
        model_name=model_name,
        audit_for=audit_for,
        action=action,
        new_obj_id=new_obj_id,
        old_obj_id=old_obj_id,
        audit_by_id=audit_by_id,
        json_ext=json_ext,
    )
    logger.info("Audit log created successfully")
    return True
