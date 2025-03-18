import logging
import json
from datetime import datetime
from gettext import gettext as _

from dotenv import load_dotenv
import os

import uuid
from django.apps import apps
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError, ObjectDoesNotExist
from django.core.mail import send_mail, BadHeaderError
from django.template import loader
from django.utils.encoding import force_bytes
from django.utils.http import urlencode, urlsafe_base64_encode
import graphql_jwt
from django.http import JsonResponse

from core.apps import CoreConfig
from core.constants import APPROVER_ROLE
from core.models import User, InteractiveUser, Officer, UserAuditLog, UserRole, Role
from core.validation.obligatoryFieldValidation import (
    validate_payload_for_obligatory_fields,
)
from policyholder.models import PolicyHolderUser
from policyholder.portal_utils import (
    make_portal_reset_password_link,
    new_user_welcome_email,
)
from location.models import HealthFacility

logger = logging.getLogger(__file__)

load_dotenv()

PORTAL_SUBSCRIBER_URL = os.getenv("PORTAL_SUBSCRIBER_URL", "")
PORTAL_FOSA_URL = os.getenv("PORTAL_FOSA_URL", "")
IMIS_URL = os.getenv("IMIS_URL", "")


def create_or_update_interactive_user(user_id, data, audit_user_id, connected):
    i_fields = {
        "username": "login_name",
        "other_names": "other_names",
        "last_name": "last_name",
        "phone": "phone",
        "email": "email",
        "language": "language_id",
        "health_facility_id": "health_facility_id",
    }
    current_password = (
        data.pop("current_password") if data.get("current_password") else None
    )

    created = False

    data_subset = {v: data.get(k) for k, v in i_fields.items()}
    data_subset["audit_user_id"] = audit_user_id
    data_subset["role_id"] = data["roles"][
        0
    ]  # The actual roles are stored in their own table
    data_subset["is_associated"] = connected

    # IS VERIFIED FOR FOSA USERS
    is_fosa_user = (
        data.get("is_fosa_user") if data.get("is_fosa_user") is not None else False
    )
    if is_fosa_user:
        data_subset["is_verified"] = data.get("is_fosa_user")

    if user_id:
        # TODO we might want to update a user that has been deleted. Use Legacy ID ?
        i_user = InteractiveUser.objects.filter(
            validity_to__isnull=True, user__id=user_id
        ).first()
    else:
        i_user = InteractiveUser.objects.filter(
            validity_to__isnull=True, login_name=data_subset["login_name"]
        ).first()

    if i_user:
        i_user.save_history()
        [setattr(i_user, k, v) for k, v in data_subset.items()]
        if "password" in data and current_password:
            check_password = i_user.check_password(current_password)
            if not check_password or check_password is False:
                print("------------------------------ wrong_old_password")
                raise Exception("Current password is incorrect")
            i_user.set_password(data["password"])
            # refresh_token = True
        created = False
    else:
        i_user = InteractiveUser(**data_subset)
        token = uuid.uuid4().hex[:16].upper()
        i_user.stored_password = "locked"
        i_user.password_reset_token = token
        # No password provided for creation, will have to be set later.

        # if "password" in data:
        #     i_user.set_password(data["password"])
        # else:
        #     # No password provided for creation, will have to be set later.
        #     i_user.stored_password = "locked"
        created = True

    i_user.save()
    
    if created:
        verification_url = None

        # for subscriber portal the email is sent once the policyholderUser is created
        # The code can be found in policyholder module

        if data.get("is_fosa_user"):
            verification_url = f"{PORTAL_FOSA_URL}/fosa/verify-user-and-update-password?user_id={i_user.uuid}&token={token}&username={i_user.username}"
        else:
            verification_url = f"{IMIS_URL}/front/verify-user-and-update-password?user_id={i_user.uuid}&token={token}&username={i_user.username}"

        print("=====> send new_user_welcome_email Start")

        new_user_welcome_email(i_user, verification_url)

        print("=====> send new_user_welcome_email Done")
        
    create_audit_user_service(i_user, created, user_id, data)    

    create_or_update_user_roles(i_user, data["roles"], audit_user_id)
    if "districts" in data:
        create_or_update_user_districts(
            i_user, data["districts"], data_subset["audit_user_id"]
        )
    return i_user, created


def  create_audit_user_service(i_user, created, user_id, data):
        data = {
            "user_id": i_user.id,
            "details": json.dumps(data),
            "action": "Création d'un utilisateur" if created else "Modification d'un utilisateur"
        }
        if user_id:
            policy_holder = PolicyHolderUser.objects.filter(user_id=user_id).first()
            if policy_holder:
                data["policy_holder"] = policy_holder
        if i_user.health_facility_id:
            health_facility = HealthFacility.objects.filter(
                id=i_user.health_facility_id
            ).first()
            data["fosa"] = health_facility
            
        UserAuditLog.objects.create(**data)


def create_or_update_user_roles(i_user, role_ids, audit_user_id):
    from core import datetime

    now = datetime.datetime.now()
    UserRole.objects.filter(user=i_user, validity_to__isnull=True).update(
        validity_to=now
    )
    for role_id in role_ids:
        UserRole.objects.create(
            user=i_user, role_id=role_id, audit_user_id=audit_user_id
        )


# TODO move to location module ?
def create_or_update_user_districts(i_user, district_ids, audit_user_id):
    # To avoid a static dependency from Core to Location, we'll dynamically load this class
    user_district_class = apps.get_model("location", "UserDistrict")
    from core import datetime

    now = datetime.datetime.now()
    user_district_class.objects.filter(user=i_user, validity_to__isnull=True).update(
        validity_to=now.to_ad_datetime()
    )
    for district_id in district_ids:
        user_district_class.objects.update_or_create(
            user=i_user,
            location_id=district_id,
            defaults={"validity_to": None, "audit_user_id": audit_user_id},
        )


def create_or_update_officer_villages(officer, village_ids, audit_user_id):
    # To avoid a static dependency from Core to Location, we'll dynamically load this class
    officer_village_class = apps.get_model("location", "OfficerVillage")
    from core import datetime

    now = datetime.datetime.now()
    officer_village_class.objects.filter(
        officer=officer, validity_to__isnull=True
    ).update(validity_to=now)
    for village_id in village_ids:
        officer_village_class.objects.update_or_create(
            officer=officer,
            location_id=village_id,
            defaults={"validity_to": None, "audit_user_id": audit_user_id},
        )


@validate_payload_for_obligatory_fields(CoreConfig.fields_controls_eo, "data")
def create_or_update_officer(user_id, data, audit_user_id, connected):
    officer_fields = {
        "username": "code",
        "other_names": "other_names",
        "last_name": "last_name",
        "phone": "phone",
        "email": "email",
        "birth_date": "dob",
        "address": "address",
        "works_to": "works_to",
        "location_id": "location_id",
        # TODO veo_code, last_name, other_names, dob, phone
        "substitution_officer_id": "substitution_officer_id",
        "station_id": "station_id",
        "phone_communication": "phone_communication",
    }
    data_subset = {v: data.get(k) for k, v in officer_fields.items()}
    data_subset["audit_user_id"] = audit_user_id
    data_subset["has_login"] = connected

    if user_id:
        # TODO we might want to update a user that has been deleted. Use Legacy ID ?
        officer = Officer.objects.filter(
            validity_to__isnull=True, user__id=user_id
        ).first()
    else:
        officer = Officer.objects.filter(
            code=data_subset["code"], validity_to__isnull=True
        ).first()

    if officer:
        officer.save_history()
        [setattr(officer, k, v) for k, v in data_subset.items()]
        created = False
    else:
        officer = Officer(**data_subset)
        created = True

    officer.save()
    if data.get("village_ids"):
        create_or_update_officer_villages(
            officer, data["village_ids"], data_subset["audit_user_id"]
        )
    return officer, created


def create_or_update_claim_admin(user_id, data, audit_user_id, connected):
    ca_fields = {
        "username": "code",
        "other_names": "other_names",
        "last_name": "last_name",
        "phone": "phone",
        "email": "email_id",
        "birth_date": "dob",
        "health_facility_id": "health_facility_id",
    }

    data_subset = {v: data.get(k) for k, v in ca_fields.items()}
    data_subset["audit_user_id"] = audit_user_id
    data_subset["has_login"] = connected

    # Since ClaimAdmin is not in the core module, we have to dynamically load it.
    # If the Claim module is not loaded and someone requests a ClaimAdmin, this will raise an Exception
    claim_admin_class = apps.get_model("claim", "ClaimAdmin")
    if user_id:
        # TODO we might want to update a user that has been deleted. Use Legacy ID ?
        claim_admin = claim_admin_class.objects.filter(
            validity_to__isnull=True, user__id=user_id
        ).first()
    else:
        claim_admin = claim_admin_class.objects.filter(
            code=data_subset["code"], validity_to__isnull=True
        ).first()

    if claim_admin:
        claim_admin.save_history()
        [setattr(claim_admin, k, v) for k, v in data_subset.items()]
        created = False
    else:
        claim_admin = claim_admin_class(**data_subset)
        created = True

    # TODO update municipalities, regions
    claim_admin.save()
    return claim_admin, created


def create_or_update_core_user(
    user_uuid,
    username,
    i_user=None,
    t_user=None,
    officer=None,
    claim_admin=None,
    station=None,
    is_fosa_user=None,
):
    if user_uuid:
        # This intentionally fails if the provided uuid doesn't exist as we don't want clients to set it
        user = User.objects.get(id=user_uuid)
        # There is no history to save for User
        created = False
    elif username:
        user = User.objects.filter(username=username).first()
        created = False
    else:
        user = None
        created = False

    if not user:
        user = User(username=username)
        created = True
    if username:
        user.username = username
    if i_user:
        user.i_user = i_user
    if t_user:
        user.t_user = t_user
    if officer:
        user.officer = officer
    if claim_admin:
        user.claim_admin = claim_admin
    if station:
        user.station = station

    if is_fosa_user is not None:
        user.is_fosa_user = is_fosa_user
    user.save()
    return user, created


def change_user_password(
    logged_user, username_to_update=None, old_password=None, new_password=None
):
    if username_to_update and username_to_update != logged_user.username:
        if not logged_user.has_perms(CoreConfig.gql_mutation_update_users_perms):
            raise PermissionDenied("unauthorized")
        user_to_update = User.objects.get(username=username_to_update)
    else:
        user_to_update = logged_user
        if not old_password or not user_to_update.check_password(old_password):
            raise ValidationError(_("core.wrong_old_password"))

    user_to_update.set_password(new_password)
    user_to_update.save()


def set_user_password(request, username, token, password, is_portal=False):
    user = User.objects.get(username=username)

    if default_token_generator.check_token(user, token):
        user.set_password(password)
        user.save()
    elif is_portal:
        user.set_password(password)
        user.save()
    else:
        raise ValidationError("Invalid Token")


def check_user_unique_email(user_email):
    if InteractiveUser.objects.filter(
        email=user_email, validity_to__isnull=True
    ).exists():
        return [{"message": "User email %s already exists" % user_email}]
    return []


def reset_user_password(request, username, is_portal):
    user = User.objects.get(username=username)
    user.clear_refresh_tokens()

    if not user.email:
        raise ValidationError(
            f"User {username} cannot reset password because he has no email address"
        )

    token = default_token_generator.make_token(user)
    try:
        logger.info(f"Send mail to reset password for {user} with token '{token}'")
        params = urlencode({"token": token})
        reset_url = f"{settings.FRONTEND_URL}/set_password?{params}"
        if is_portal:
            token = default_token_generator.make_token(user.i_user)
            reset_url = make_portal_reset_password_link(user, token)
        message = loader.render_to_string(
            CoreConfig.password_reset_template,
            {
                "reset_url": reset_url,
                "user": user,
            },
        )
        logger.debug("Message sent: %s" % message)
        email_to_send = send_mail(
            subject="[OpenIMIS] Reset Password",
            message=message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return email_to_send
    except BadHeaderError:
        return ValueError("Invalid header found.")


def find_approvers():
    approver_role = Role.objects.filter(
        name__iexact=APPROVER_ROLE, legacy_id__isnull=True
    ).first()
    if approver_role:
        approver_interactive_users = InteractiveUser.objects.filter(
            id__in=UserRole.objects.filter(role=approver_role).values_list(
                "user_id", flat=True
            )
        ).distinct()
        approvers = User.objects.filter(
            i_user__in=approver_interactive_users
        ).distinct()
    else:
        approvers = []
    return approvers


def find_ph_approver(policy_holder):
    try:
        if not policy_holder:
            logger.error("Invalid policyholder object provided.")
            raise ValueError("Invalid policyholder object.")

        ph_user = PolicyHolderUser.objects.filter(
            policy_holder=policy_holder, is_deleted=False
        ).first()

        if not ph_user:
            logger.warning(
                f"No active PolicyHolderUser found for PolicyHolder ID {policy_holder.id}"
            )
            raise ObjectDoesNotExist(
                f"No approver found for PolicyHolder ID {policy_holder.id}"
            )

        return ph_user.user

    except ObjectDoesNotExist as e:
        logger.error(f"PolicyHolderUser not found: {e}")
        raise
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
        raise
